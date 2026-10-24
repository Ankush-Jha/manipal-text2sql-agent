"""Deterministic literal repair: a string the model wrote in an equality filter that exists nowhere in that column.

The model writes values the way a person would ('Blonde', '2016/6/23'); the database stores them differently
('Blond', '2016-06-23 00:00:00'). The query still runs and returns zero rows: a wrong answer that looks clean.
No model is used. A literal is only touched when it is NOT a stored value of its column, and only in = / IN
(never !=, NOT IN or LIKE). Fixes: a case/space-insensitive match, a date written with another separator
against a timestamp column, or one unambiguous close spelling."""
import difflib
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parent.parent
MAX_DISTINCT = 20000
CUTOFF = 0.88      # similarity for a close spelling ('Blonde' -> 'Blond')
MARGIN = 0.05      # the best match must beat the runner-up by this much, else it is ambiguous: do nothing
_DATE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(s).lower())).strip()


@lru_cache(maxsize=None)
def column_values(db_path: str, table: str, col: str) -> tuple | None:
    """Distinct stored text values of a column, or None when it is too large or not text."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    try:
        n = conn.execute(f'SELECT COUNT(DISTINCT "{col}") FROM "{table}"').fetchone()[0]
        if n > MAX_DISTINCT:
            return None
        vals = [v for (v,) in conn.execute(f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL')]
        return tuple(v for v in vals if isinstance(v, str)) or None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _scope(tree, profile):
    """alias -> real table name, and column -> tables of the query that own it."""
    tables = {t.name.lower(): t.name for t in tree.find_all(exp.Table)}
    alias = {(t.alias_or_name or t.name).lower(): t.name for t in tree.find_all(exp.Table)}
    real = {k.lower(): k for k in profile["tables"]}
    return {a: real.get(n.lower(), n) for a, n in alias.items()}, {n.lower() for n in tables}


def _resolve(col, alias, used, profile):
    if col.table:
        t = alias.get(col.table.lower())
    else:
        owners = [t for t in profile["tables"] if t.lower() in used and col.name.lower() in {c.lower() for c in profile["tables"][t]}]
        t = owners[0] if len(owners) == 1 else None  # ambiguous or unknown: do nothing
    if not t or t not in profile["tables"]:
        return None
    real = next((c for c in profile["tables"][t] if c.lower() == col.name.lower()), None)
    return (t, real) if real else None


def _suggest(lit: str, values: tuple, info: dict) -> tuple[str, str] | None:
    """(replacement, reason) for a literal that is not a stored value, or None."""
    n = _norm(lit)
    exact_ci = [v for v in values if _norm(v) == n] if n else []
    if len(exact_ci) == 1:
        return exact_ci[0], "same value, different case or punctuation"
    close = difflib.get_close_matches(n, [_norm(v) for v in values], n=2, cutoff=CUTOFF)
    if close:
        best = close[0]
        r1 = difflib.SequenceMatcher(None, n, best).ratio()
        r2 = difflib.SequenceMatcher(None, n, close[1]).ratio() if len(close) > 1 else 0
        cand = [v for v in values if _norm(v) == best]
        if len(cand) == 1 and r1 - r2 >= MARGIN:
            return cand[0], f"closest stored spelling ({r1:.2f})"
    return None


def repair_literals(sql: str, db_path: str | Path, profile: dict) -> tuple[str, list[dict]]:
    """Returns (possibly rewritten SQL, list of fixes). Never raises: on any problem the SQL is returned unchanged."""
    if not sql:
        return sql, []
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return sql, []
    alias, used = _scope(tree, profile)
    fixes: list[dict] = []
    db_path = str(db_path)

    def handle(col, lit_node):
        key = _resolve(col, alias, used, profile)
        if not key:
            return None
        t, c = key
        info = profile["tables"][t][c]
        if not any(k in (info.get("type") or "").upper() for k in ("CHAR", "TEXT", "DATE", "CLOB")):
            return None
        values = column_values(db_path, t, c)
        lit = lit_node.name
        if values is None or lit in values:
            return None
        # a date with another separator, against a timestamp column ('2016/6/23' vs '2016-06-23 00:00:00')
        m = _DATE.match(lit)
        if m and any(len(v) > 10 and re.match(r"^\d{4}-\d{2}-\d{2}", v) for v in values[:50]):
            iso = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            return ("date", iso, f"{t}.{c}", lit, "date written differently from the stored timestamps")
        s = _suggest(lit, values, info)
        return ("snap", s[0], f"{t}.{c}", lit, s[1]) if s else ("unknown", None, f"{t}.{c}", lit, "not a stored value of this column")

    for node in list(tree.find_all(exp.EQ, exp.In)):
        if node.find_ancestor(exp.Not):
            continue  # NOT IN / NOT (col = 'x') say "is not that value": a missing literal there is not a mistake
        if isinstance(node, exp.EQ):
            pairs = [(node.this, node.expression)] if isinstance(node.this, exp.Column) else [(node.expression, node.this)]
            pairs = [(c, l) for c, l in pairs if isinstance(c, exp.Column) and isinstance(l, exp.Literal) and l.is_string]
        else:
            pairs = [(node.this, l) for l in node.expressions if isinstance(node.this, exp.Column) and isinstance(l, exp.Literal) and l.is_string]
        for col, lit_node in pairs:
            r = handle(col, lit_node)
            if not r:
                continue
            kind, new, where, old, why = r
            fixes.append({"column": where, "was": old, "now": new, "kind": kind, "why": why})
            if kind == "snap":
                lit_node.replace(exp.Literal.string(new))
            elif kind == "date" and isinstance(node, exp.EQ):
                col_sql = col.copy()
                # SUBSTR (not SUBSTRING): older SQLite builds only know the short name
                node.replace(exp.EQ(this=exp.Anonymous(this="SUBSTR", expressions=[col_sql, exp.Literal.number(1), exp.Literal.number(10)]),
                                    expression=exp.Literal.string(new)))
    changed = [f for f in fixes if f["kind"] in ("snap", "date")]
    return (tree.sql(dialect="sqlite") if changed else sql), fixes
