"""Schema identity: a hash of the live table definitions keys every cache, so a rename or split is noticed."""
import hashlib
import sqlite3
from functools import lru_cache
from pathlib import Path


def _connect(db_path):
    return sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)


def snapshot(db_path) -> dict[str, list[str]]:
    """{table: [columns]} read from the live database."""
    c = _connect(db_path)
    try:
        tables = [n for (n,) in c.execute("select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%' order by name")]
        return {t: [r[1] for r in c.execute(f'pragma table_info("{t}")')] for t in tables}
    finally:
        c.close()


@lru_cache(maxsize=64)
def _hash(db_path: str, mtime_ns: int) -> str:
    c = _connect(db_path)
    try:
        rows = c.execute("select type, name, sql from sqlite_master where name not like 'sqlite_%' order by type, name").fetchall()
    finally:
        c.close()
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:12]


def schema_hash(db_path) -> str:
    """12-hex digest of CREATE statements; recomputed when the file changes (mtime is part of the memo key)."""
    p = Path(db_path).resolve()
    return _hash(str(p), p.stat().st_mtime_ns)


# ---- migration map: which new table/column holds each old one, found from column statistics, not names ----
import difflib


def _sig(info: dict):
    return (info.get("rows"), info.get("distinct"), round(info.get("null_rate", 0), 4), repr(info.get("min")), repr(info.get("max")),
            tuple((repr(v), n) for v, n in info.get("top_values", [])[:3] if n > 1))  # ties at count 1 come back in arbitrary order


def _q(n):
    return '"' + n.replace('"', '""') + '"'


def derive_map(old_profile: dict, new_profile: dict) -> dict:
    """Old (table, column) -> new (table, column), matched on column statistics (counts, range, most frequent values).
    Names only break ties. Returns {"tables": {old: {"sql", "now", "changed", "unmapped"}}, "columns": {...}, "ambiguous": [...]}.
    `sql` selects the old table back out of the new schema, so SQL written for the old names can be rewritten or run through views."""
    by_sig: dict = {}
    for nt, cols in new_profile["tables"].items():
        for nc, info in cols.items():
            by_sig.setdefault(_sig(info), []).append((nt, nc))
    new_names = {nt: list(cols) for nt, cols in new_profile["tables"].items()}
    taken, columns, ambiguous, keys = set(), {}, [], {}
    for ot, cols in old_profile["tables"].items():
        columns[ot] = {}
        for oc, info in cols.items():
            cands = [c for c in by_sig.get(_sig(info), []) if c not in taken]
            if not cands:
                continue
            score = lambda c: difflib.SequenceMatcher(None, oc.lower(), c[1].lower()).ratio() + 0.5 * difflib.SequenceMatcher(None, ot.lower(), c[0].lower()).ratio()
            cands.sort(key=score, reverse=True)
            same_name = [c for c in cands if c[1] == cands[0][1]]
            if len(same_name) > 1 and len({c[0] for c in same_name}) == len(same_name):  # one column present in several parts: the join key
                keys.setdefault(ot, {})[oc] = [c[0] for c in same_name]
                columns[ot][oc] = list(same_name[0])
                taken.add(tuple(same_name[0]))
                continue
            if len(cands) > 1 and score(cands[0]) - score(cands[1]) < 0.05:
                ambiguous.append({"old": [ot, oc], "candidates": cands[:3]})
            columns[ot][oc] = list(cands[0])
            taken.add(tuple(cands[0]))
    # horizontal split: an old table with nothing matched whose full column list now appears in several tables
    for ot, cols in old_profile["tables"].items():
        if columns[ot]:
            continue
        parts = [nt for nt, ncs in new_names.items() if [c.lower() for c in ncs] == [c.lower() for c in cols]]
        if len(parts) > 1:
            columns[ot] = {oc: [parts[0], oc] for oc in cols}
            keys.setdefault(ot, {})["__union__"] = parts
    tables = {}
    for ot, cmap in columns.items():
        now = sorted({t for t, _ in cmap.values()} | {t for ks in keys.get(ot, {}).values() for t in ks if ks is not None})
        if keys.get(ot, {}).get("__union__"):
            parts = keys[ot]["__union__"]
            sel = ", ".join(f"{_q(c)} AS {_q(oc)}" for oc, (_, c) in cmap.items())
            sql = f"SELECT {sel} FROM (" + " UNION ALL ".join(f"SELECT * FROM {_q(t)}" for t in parts) + ")"
            now = sorted(parts)
        elif len(now) <= 1:
            sel = ", ".join(f"{_q(t)}.{_q(c)} AS {_q(oc)}" for oc, (t, c) in cmap.items()) or "1"
            sql = f"SELECT {sel} FROM {_q(now[0])}" if now else ""
        else:
            ks = [(oc, parts) for oc, parts in keys.get(ot, {}).items() if oc != "__union__"]
            a, b = now[0], now[1]
            key = next((c for oc, parts in ks for (t, c) in [cmap[oc]] if a in parts and b in parts), None)
            sel = ", ".join(f"{_q(t)}.{_q(c)} AS {_q(oc)}" for oc, (t, c) in cmap.items())
            sql = f"SELECT {sel} FROM {_q(a)} JOIN {_q(b)} ON {_q(a)}.{_q(key)} = {_q(b)}.{_q(key)}" if key else ""
        same = len(now) == 1 and now[0] == ot and all(c == oc and t == ot for oc, (t, c) in cmap.items())
        tables[ot] = {"sql": sql, "now": now, "changed": not same, "unmapped": [c for c in old_profile["tables"][ot] if c not in cmap]}
    return {"tables": tables, "columns": columns, "ambiguous": ambiguous}


def map_accuracy(derived: dict, truth: dict) -> dict:
    """Share of old columns mapped to the right place, and tables whose rebuilt SELECT matches the ground-truth table set."""
    ok = tot = 0
    for ot, cols in truth["columns"].items():
        for oc, (tt, tc) in cols.items():
            tot += 1
            got = derived["columns"].get(ot, {}).get(oc)
            ok += bool(got) and got[1] == tc and (got[0] == tt or got[0] in truth["tables"][ot]["now"])
    return {"columns": f"{ok}/{tot}", "column_acc": round(ok / tot, 4), "tables_with_sql": sum(bool(t["sql"]) for t in derived["tables"].values()),
            "ambiguous": len(derived["ambiguous"])}


def rewrite_sql(sql: str, mapping: dict) -> str:
    """SQL written for the old schema -> SQL for the new one: each changed old table becomes its mapping SELECT."""
    import sqlglot
    from sqlglot import exp
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    by_name = {t.lower(): v for t, v in mapping["tables"].items()}
    for t in list(tree.find_all(exp.Table)):
        key = t.name.lower()
        if key in ctes or key not in by_name or not by_name[key]["changed"] or not by_name[key]["sql"]:
            continue
        inner = sqlglot.parse_one(by_name[key]["sql"], read="sqlite")
        t.replace(exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(t.alias or t.name, quoted=True))))
    return tree.sql(dialect="sqlite")


def carry_over(new_profile: dict, old_profile: dict, dmap: dict) -> dict:
    """Give each new column the description the old column had, so code meanings survive a rename or split."""
    import copy
    out = copy.deepcopy(new_profile)
    for ot, cols in dmap["columns"].items():
        for oc, (nt, nc) in cols.items():
            info = out["tables"].get(nt, {}).get(nc)
            old = old_profile["tables"].get(ot, {}).get(oc, {}).get("description")
            if info is not None and old and not info.get("description"):
                info["description"] = old
    return out


def migration_hints(dmap: dict, max_lines: int = 6) -> list[str]:
    """Plain-language notes for the writer about what moved. Identifiers come from the database, so they pass the value filter."""
    from agent.sanitize import clean_value
    lines = []
    for ot, t in dmap["tables"].items():
        if not t["changed"] or not t["now"]:
            continue
        renames = [f"{oc} is now {c}" for oc, (nt, c) in dmap["columns"][ot].items() if oc != c][:8]
        if len(t["now"]) > 1:
            where = "; ".join(f"{nt}({', '.join(c for oc, (n2, c) in dmap['columns'][ot].items() if n2 == nt)[:90]})" for nt in t["now"])
            lines.append(f"Old table {ot} is now split across {' and '.join(t['now'])}: {where}")
        elif t["now"][0] != ot:
            lines.append(f"Old table {ot} is now {t['now'][0]}")
        if renames and len(t["now"]) == 1:
            lines.append(f"In {t['now'][0]} renamed columns: " + ", ".join(renames))
    return [clean_value(x, "drift") for x in lines[:max_lines]]
