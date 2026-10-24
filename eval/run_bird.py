"""Plain Arctic-R1 greedy baseline on the 150 reporting questions. Resumable (jsonl).
Usage: python -m eval.run_bird --hints true|false [--split report|calibration] [--limit N]"""
import argparse, json, sqlite3, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from agent.executor import execute, GuardError
from agent.writer import build_prompt, sample

ROOT = Path(__file__).resolve().parent.parent
URL = "http://localhost:8081/v1"

def ddl(db):
    c = sqlite3.connect(f"file:{ROOT}/data/dev_databases/{db}/{db}.sqlite?mode=ro", uri=True)
    try:
        return "\n\n".join(r[0] for r in c.execute("select sql from sqlite_master where type='table' and sql is not null"))
    finally:
        c.close()

def rows_set(db, sql):
    return set(execute(f"{ROOT}/data/dev_databases/{db}/{db}.sqlite", sql, timeout_s=30, max_rows=100000).rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hints", required=True, choices=["true", "false"])
    ap.add_argument("--split", default="report")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="0/1", help="i/N: this machine runs every N-th question")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    a_workers = a.workers
    use_hints = a.hints == "true"
    qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
    ids = set(json.loads((ROOT / "eval/split.json").read_text())["report" if a.split == "report" else "calibration"])
    qs = [q for q in qs if q["question_id"] in ids]
    if a.limit: qs = qs[:a.limit]
    si, sn = map(int, a.shard.split("/")); qs = qs[si::sn]
    sfx = "" if sn == 1 else f"_shard{si}of{sn}"
    out = ROOT / f"results/baseline_{a.split}_hints_{a.hints}{sfx}.jsonl"
    base = ROOT / f"results/baseline_{a.split}_hints_{a.hints}.jsonl"  # questions already done unsharded count as done
    done = set()
    for f in {out, base}:
        if f.exists(): done |= {json.loads(l)["question_id"] for l in f.open()}
    lock, todo = threading.Lock(), [q for q in qs if q["question_id"] not in done]
    counter = [len(done)]

    def work(q):
        t = time.time()
        try:
            sql = sample(URL, build_prompt(ddl(q["db_id"]), q["question"], q["evidence"] if use_hints else ""), 1, 0, max_tokens=2048)[0]
        except Exception as e:
            sql, err = None, f"writer: {e}"
        else:
            err = None if sql else "no_sql_block"
        hit = False
        if sql:
            try: hit = rows_set(q["db_id"], sql) == rows_set(q["db_id"], q["SQL"])
            except (GuardError, sqlite3.Error) as e: err = str(e)[:200]
        rec = dict(question_id=q["question_id"], db_id=q["db_id"], difficulty=q["difficulty"], correct=hit, sql=sql, error=err, seconds=round(time.time() - t, 1))
        with lock:
            with out.open("a") as f: f.write(json.dumps(rec) + "\n")
            counter[0] += 1
            print(f"[{counter[0]}/{len(qs)}] q{q['question_id']} correct={hit} {rec['seconds']}s", flush=True)

    with ThreadPoolExecutor(max_workers=a_workers) as ex:
        list(ex.map(work, todo))
    recs = [json.loads(l) for l in out.open()]
    print(f"EX {sum(r['correct'] for r in recs)}/{len(recs)} = {100*sum(r['correct'] for r in recs)/len(recs):.1f}%")

main()
