"""Validate eval/sets/ambiguous_*.json: every reading executes, and the readings of one question differ in result.
Usage: python -m scripts.check_ambiguous eval/sets/ambiguous_100.json"""
import json
import sys
from pathlib import Path

from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent


def rowset(db, sql):
    return set(map(repr, execute(db, sql, timeout_s=20, max_rows=10000).rows))


def check(path):
    data = json.loads(Path(path).read_text())
    bad = []
    for q in data:
        db = ROOT / f"data/dev_databases/{q['db_id']}/{q['db_id']}.sqlite"
        try:
            sets = [rowset(db, r["gold_sql"]) for r in q["readings"]]
        except Exception as e:
            bad.append((q["question_id"], str(e)[:100]))
            continue
        if any(not s for s in sets):
            bad.append((q["question_id"], "a reading returned nothing"))
        elif len(set(map(frozenset, sets))) < 2:
            bad.append((q["question_id"], "readings return the same rows: not actually ambiguous"))
    print(f"{len(data)} questions, {len(bad)} problems")
    for qid, msg in bad:
        print(f"  {qid}: {msg}")
    return len(bad) == 0


if __name__ == "__main__":
    ok = check(sys.argv[1] if len(sys.argv) > 1 else ROOT / "eval/sets/ambiguous_100.json")
    sys.exit(0 if ok else 1)
