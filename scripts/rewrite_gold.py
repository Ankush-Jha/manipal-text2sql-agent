"""Rewrite gold SQL onto a perturbed schema by substituting each old table with its mapping SELECT, then keep only
questions whose rewritten gold returns the same rows on the perturbed database as the original gold on the original.
Usage: python -m scripts.rewrite_gold <db_id> <kind>  -> data/perturbed/<kind>/<db_id>/questions.json"""
import json
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp

from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent


from agent.schema_state import rewrite_sql as rewrite  # noqa: E402


def touched(sql: str, mapping: dict) -> bool:
    names = {t.name.lower() for t in sqlglot.parse_one(sql, read="sqlite").find_all(exp.Table)}
    return any(mapping["tables"][o]["changed"] for o in mapping["tables"] if o.lower() in names)


def rows(db, sql):
    return sorted(map(repr, execute(db, sql, timeout_s=30, max_rows=100000).rows))


def build(db_id: str, kind: str) -> list[dict]:
    d = ROOT / "data/perturbed" / kind / db_id
    mapping = json.loads((d / "mapping.json").read_text())
    orig = ROOT / f"data/dev_databases/{db_id}/{db_id}.sqlite"
    new = d / f"{db_id}.sqlite"
    out, stats = [], {"total": 0, "untouched": 0, "rewrite_failed": 0, "mismatch": 0}
    for qd in json.loads((ROOT / "data/mini_dev_sqlite.json").read_text()):
        if qd["db_id"] != db_id:
            continue
        stats["total"] += 1
        try:
            if not touched(qd["SQL"], mapping):
                stats["untouched"] += 1
                continue
            new_sql = rewrite(qd["SQL"], mapping)
            ok = rows(new, new_sql) == rows(orig, qd["SQL"])
        except Exception:
            stats["rewrite_failed"] += 1
            continue
        if not ok:
            stats["mismatch"] += 1
            continue
        out.append({"question_id": qd["question_id"], "question": qd["question"], "evidence": qd["evidence"],
                    "gold_sql": qd["SQL"], "gold_sql_perturbed": new_sql})
    (d / "questions.json").write_text(json.dumps({"stats": stats, "kept": len(out), "questions": out}, indent=1))
    print(db_id, kind, stats, "kept", len(out))
    return out


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
