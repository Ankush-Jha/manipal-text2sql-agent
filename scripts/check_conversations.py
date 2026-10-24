"""Validate eval/sets/conversations_*.json: every gold_sql executes and returns rows (skips LIMIT 0 by design).
Usage: python -m scripts.check_conversations eval/sets/conversations_50.json"""
import json
import sys
from pathlib import Path

from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent


def check(path):
    data = json.loads(Path(path).read_text())
    bad = []
    for conv in data:
        db = ROOT / f"data/dev_databases/{conv['db_id']}/{conv['db_id']}.sqlite"
        for i, t in enumerate(conv["turns"]):
            try:
                r = execute(db, t["gold_sql"], timeout_s=20, max_rows=10000)
                if not r.rows:
                    bad.append((conv["conv_id"], i, "empty"))
            except Exception as e:
                bad.append((conv["conv_id"], i, str(e)[:100]))
    total = sum(len(c["turns"]) for c in data)
    print(f"{len(data)} conversations, {total} turns, {len(bad)} problems")
    for c, i, msg in bad:
        print(f"  {c} turn {i}: {msg}")
    return len(bad) == 0


if __name__ == "__main__":
    ok = check(sys.argv[1] if len(sys.argv) > 1 else ROOT / "eval/sets/conversations_50.json")
    sys.exit(0 if ok else 1)
