"""Unanswerable set.
1) Human set: eval/unanswerable.jsonl, one JSON per line {"db_id","question","type"} written blind by a teammate.
2) Auto set: take REPORT-split questions, drop a column the gold SQL needs from a COPY of the DB (ALTER TABLE DROP COLUMN);
   the right behaviour is to refuse. Copies live in data/unanswerable_dbs/<db_id>/ (id = v<qid>_<db>).
Usage: python -m eval.unanswerable build [--max 40]"""
import json, shutil, sqlite3, sys
from pathlib import Path
import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "data/dev_databases", ROOT / "data/unanswerable_dbs"
MAX_MB = 70
TYPES = ["ambiguous", "schema_mismatch", "outside_sql", "outside_knowledge"]


def needed_columns(sql: str, schema: dict[str, set[str]]) -> list[tuple[str, str]]:
    """(table, column) pairs the gold SQL reads, excluding id/code-style keys and join columns."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    aliases = {(t.alias_or_name).lower(): t.name.lower() for t in tree.find_all(exp.Table)}
    join_cols = {c.name.lower() for j in tree.find_all(exp.Join) for c in j.find_all(exp.Column)}
    out = []
    for c in tree.find_all(exp.Column):
        name = c.name.lower()
        if name in join_cols or name.endswith(("id", "code")):
            continue
        tables = [aliases.get((c.table or "").lower())] if c.table else list(set(aliases.values()))
        for t in tables:
            if t and name in schema.get(t, set()) and (t, name) not in out:
                out.append((t, name))
    return out


def build(max_n: int = 40):
    qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
    report = set(json.loads((ROOT / "eval/split.json").read_text())["report"])
    OUT.mkdir(exist_ok=True)
    manifest, seen_db = [], {}
    for q in qs:
        if len(manifest) >= max_n: break
        if q["question_id"] not in report: continue
        src = SRC / q["db_id"]
        if sum(f.stat().st_size for f in src.rglob("*") if f.is_file()) > MAX_MB * 2**20: continue
        if q["db_id"] not in seen_db:
            c = sqlite3.connect(f"file:{src / (q['db_id'] + '.sqlite')}?mode=ro", uri=True)
            seen_db[q["db_id"]] = {t.lower(): {r[1].lower() for r in c.execute(f'PRAGMA table_info("{t}")')}
                                   for (t,) in c.execute("select name from sqlite_master where type='table'")}
            c.close()
        try:
            cands = needed_columns(q["SQL"], seen_db[q["db_id"]])
        except Exception:
            continue
        for table, col in cands:
            vid = f"v{q['question_id']}_{q['db_id']}"
            dst = OUT / vid
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src, dst)
            (dst / f"{q['db_id']}.sqlite").rename(dst / f"{vid}.sqlite")
            conn = sqlite3.connect(dst / f"{vid}.sqlite")
            real = next(r[1] for r in conn.execute(f'PRAGMA table_info("{table}")') if r[1].lower() == col) if True else col
            try:
                conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{real}"'); conn.commit(); ok = True
            except sqlite3.Error:
                ok = False
            conn.close()
            if ok:
                manifest.append({"id": vid, "question_id": q["question_id"], "db_id": vid, "source_db": q["db_id"],
                                 "question": q["question"], "type": "schema_mismatch", "dropped": f"{table}.{real}"})
                break
            shutil.rmtree(dst)
    (ROOT / "eval/unanswerable_auto.json").write_text(json.dumps(manifest, indent=1))
    print(f"built {len(manifest)} column-removed variants -> eval/unanswerable_auto.json")


def load_human() -> list[dict]:
    p = ROOT / "eval/unanswerable.jsonl"
    return [json.loads(l) for l in p.open() if l.strip()] if p.exists() else []


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "build":
    build(int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 40)
