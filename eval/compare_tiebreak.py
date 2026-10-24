"""Paired comparison on IDENTICAL samples: default winner (first of the tied groups) vs greedy-tiebreak winner.
Reads the run saved with --tag tiebreak (it keeps all candidates + the tiebreak info). No model needed.
Usage: python -m eval.compare_tiebreak [results/agent_report_benchmark_hints_false_n5_tiebreak.jsonl]"""
import json, sys
from pathlib import Path
from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent
f = sys.argv[1] if len(sys.argv) > 1 else ROOT / "results/agent_report_benchmark_hints_false_n5_tiebreak.jsonl"
qs = {q["question_id"]: q for q in json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())}
old = {}
for l in open(ROOT / "results/agent_report_benchmark_hints_false_n5.jsonl"):
    r = json.loads(l); old[r["question_id"]] = r

def rows(db, sql):
    return set(execute(ROOT / f"data/dev_databases/{db}/{db}.sqlite", sql, 30, 100000).rows)

def is_correct(q, sql):
    try: return bool(sql) and rows(q["db_id"], sql) == rows(q["db_id"], q["SQL"])
    except Exception: return False

n = tied = matched = same = gain = loss = 0
default_ok = tb_ok = prev_ok = 0
for l in open(f):
    r = json.loads(l); q = qs[r["question_id"]]; tb = r.get("tiebreak") or {}
    n += 1
    # the runner saved the winner it WOULD have picked without the tiebreak (same samples)
    default_sql = tb.get("default_sql") or r["sql"]
    d, t = is_correct(q, default_sql), is_correct(q, r["sql"])
    default_ok += d; tb_ok += t; prev_ok += bool(old.get(r["question_id"], {}).get("correct"))
    tied += bool(tb.get("tied")); matched += bool(tb.get("matched"))
    if tb.get("tied") and tb.get("matched"):
        gain += (t and not d); loss += (d and not t); same += (t == d)
print(f"questions re-run: {n}   tied: {tied}   greedy matched a tied group: {matched}")
print(f"SAME samples, default rule : {default_ok}/{n} correct")
print(f"SAME samples, greedy tiebreak: {tb_ok}/{n} correct   -> fixed {gain}, broke {loss}, unchanged {same}")
print(f"(for reference, the original run on these questions: {prev_ok}/{n}; differs because the samples were redrawn)")
