"""Accuracy before and after schema drift. Writer server only (benchmark mode, no judge). Resumable, shardable.
Conditions: A original schema | B drifted, caches NOT invalidated | C drifted, fresh profile | D drifted, fresh profile + migration map.
Score: the agent's SQL runs on the drifted database and must return what the ORIGINAL gold returns on the original database.
Usage: python -m eval.run_drift --db california_schools --kind t_vsplit --cond A,B,C,D [--n 5] [--limit N] [--shard i/N]"""
import argparse
import json
import time
from pathlib import Path

from agent.agent import ask
from agent.executor import execute
from agent.profiler import profile_db

ROOT = Path(__file__).resolve().parent.parent


def rows(db, sql):
    return sorted(map(repr, execute(db, sql, timeout_s=30, max_rows=100000).rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--kind", required=True)
    ap.add_argument("--cond", default="A,B,C,D"); ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--shard", default="0/1")
    a = ap.parse_args()
    pdir = ROOT / "data/perturbed" / a.kind / a.db
    qs = json.loads((pdir / "questions.json").read_text())["questions"][: a.limit or None]
    si, sn = map(int, a.shard.split("/")); qs = qs[si::sn]
    orig_db = ROOT / f"data/dev_databases/{a.db}/{a.db}.sqlite"
    new_db = pdir / f"{a.db}.sqlite"
    old_profile = profile_db(a.db)
    for cond in a.cond.split(","):
        out = ROOT / (f"results/drift_{a.db}_{a.kind}_{cond}_n{a.n}" + (f"_shard{si}of{sn}" if sn > 1 else "") + ".jsonl")
        done = {json.loads(l)["question_id"] for l in out.open()} if out.exists() else set()
        root = ROOT / "data/dev_databases" if cond == "A" else pdir.parent
        drift = {"B": {"from": old_profile, "mode": "stale"}, "D": {"from": old_profile, "mode": "repair"}}.get(cond)
        target = orig_db if cond == "A" else new_db
        for i, q in enumerate(qs):
            if q["question_id"] in done:
                continue
            t = time.time()
            r = ask(q["question"], a.db, "benchmark", a.n, db_root=root, drift=drift)
            hit, err = False, None
            if r["sql"]:
                try:
                    hit = rows(target, r["sql"]) == rows(orig_db, q["gold_sql"])
                except Exception as e:
                    err = str(e)[:120]
            errs = sum(1 for c in r["candidates"] if c["error"])
            rec = dict(question_id=q["question_id"], cond=cond, kind=a.kind, status=r["status"], correct=hit, sql=r["sql"], error=err,
                       candidate_errors=errs, repaired=sum(1 for c in r["candidates"] if c["repaired"]), seconds=round(time.time() - t, 1))
            with out.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            print(f"[{cond} {i + 1}/{len(qs)}] q{q['question_id']} correct={hit} {rec['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
