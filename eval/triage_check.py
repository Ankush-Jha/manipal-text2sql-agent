"""How well does the judge separate answerable questions from their column-removed twins? (judge server only)"""
import json
from pathlib import Path
from agent import decider
from agent.agent import triage, TRIAGE
from agent.hints import hint_lines
from agent.linker import link
from agent.profiler import profile_db
from eval.unanswerable import OUT

ROOT = Path(__file__).resolve().parent.parent
auto = json.loads((ROOT / "eval/unanswerable_auto.json").read_text())
qs = {q["question_id"]: q for q in json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())}
dec = lambda q, o, c, d=None: decider.decide_local("http://localhost:8082/v1", q, o, c, d)
res = {"answerable": [], "unanswerable": []}
for it in auto:
    for kind, db, root in (("answerable", it["source_db"], None), ("unanswerable", it["db_id"], OUT)):
        p = profile_db(db, root); lk = link(it["question"], "", p, db, db_root=root)
        pr = triage(it["question"], lk, hint_lines(lk, p), dec)
        res[kind].append(pr)
for kind, rows in res.items():
    ok = [r["answerable"] for r in rows]
    print(f"{kind:13} n={len(rows)} mean P(answerable)={sum(ok)/len(ok):.2f}  argmax=answerable in {sum(max(r, key=r.get)=='answerable' for r in rows)}/{len(rows)}  refused@0.85 {sum(r['data_missing']+r['not_sql']>=0.85 for r in rows)}/{len(rows)}")
