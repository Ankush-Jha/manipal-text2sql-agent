"""Recompute `correct` for stored baseline/agent jsonl files from their saved SQL (no model needed).
Use after fixing the executor or the scoring rule. Usage: python -m eval.rescore results/<file>.jsonl ..."""
import json, sys
from pathlib import Path
from agent.executor import execute
ROOT = Path(__file__).resolve().parent.parent
qs = {q["question_id"]: q for q in json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())}

def rows(db, sql):
    return set(execute(ROOT / f"data/dev_databases/{db}/{db}.sqlite", sql, 30, 100000).rows)

for path in sys.argv[1:]:
    recs = [json.loads(l) for l in open(path)]
    changed = 0
    for r in recs:
        q = qs[r["question_id"]]
        try: hit = bool(r["sql"]) and rows(q["db_id"], r["sql"]) == rows(q["db_id"], q["SQL"])
        except Exception: hit = False
        changed += hit != r["correct"]; r["correct"] = hit
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in recs))
    print(f"{path}: {sum(r['correct'] for r in recs)}/{len(recs)} correct ({changed} changed)")
