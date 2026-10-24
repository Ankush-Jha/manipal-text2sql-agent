"""Offline test of agent/literals.py (no model).
1) Precision: run it over all 500 GOLD queries. Gold literals are correct, so any rewrite that changes a gold
   result is a false positive. 2) Effect: re-score the saved plain and agent predictions on the report split."""
import json
from pathlib import Path
from agent.executor import execute
from agent.literals import repair_literals
from agent.profiler import profile_db

ROOT = Path(__file__).resolve().parent.parent
qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
dbp = lambda db: ROOT / f"data/dev_databases/{db}/{db}.sqlite"
def rows(db, sql):
    try: return set(execute(dbp(db), sql, 30, 100000).rows)
    except Exception: return None

changed = fp = flagged = 0
for q in qs:
    new, fixes = repair_literals(q["SQL"], dbp(q["db_id"]), profile_db(q["db_id"]))
    flagged += any(f["kind"] == "unknown" for f in fixes)
    if new != q["SQL"]:
        changed += 1
        if rows(q["db_id"], new) != rows(q["db_id"], q["SQL"]):
            fp += 1; print("  FALSE POSITIVE q%s: %s" % (q["question_id"], [f for f in fixes if f["kind"] != "unknown"]))
print(f"gold queries: {len(qs)} | rewritten: {changed} | rewrites that changed the result (false positives): {fp} | with an unknown literal: {flagged}")

split = set(json.loads((ROOT / "eval/split.json").read_text())["report"])
by = {q["question_id"]: q for q in qs}
for name, f in (("plain", "baseline_report_hints_false.jsonl"), ("agent", "agent_report_benchmark_hints_false_n5.jsonl")):
    recs = [json.loads(l) for l in open(ROOT / "results" / f)]
    fixed = broke = rewritten = 0; ex = []
    for r in recs:
        q = by[r["question_id"]]
        new, fixes = repair_literals(r["sql"], dbp(q["db_id"]), profile_db(q["db_id"]))
        if new == r["sql"]: continue
        rewritten += 1
        ok = rows(q["db_id"], new) == rows(q["db_id"], q["SQL"])
        fixed += ok and not r["correct"]; broke += (not ok) and r["correct"]
        if ok != r["correct"]: ex.append((r["question_id"], "fixed" if ok else "BROKE", [f["was"] + "->" + str(f["now"]) for f in fixes if f["kind"] != "unknown"]))
    base = sum(r["correct"] for r in recs)
    print(f"{name}: rewrote {rewritten} predictions -> fixed {fixed}, broke {broke}; {base}/150 -> {base + fixed - broke}/150   {ex}")
