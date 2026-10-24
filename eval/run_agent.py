"""Run the full agent on a split and log signals + correctness (resumable jsonl). Needs the model servers.
Usage: python -m eval.run_agent --split calibration|report --mode benchmark|product --hints true|false [--n 5] [--limit N]
Calibration runs use product mode so judge/triage signals are recorded; report accuracy uses benchmark mode."""
import argparse, json, sqlite3, time
from pathlib import Path
from agent.agent import ask
from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent

def rows_set(db, sql):
    return set(execute(f"{ROOT}/data/dev_databases/{db}/{db}.sqlite", sql, timeout_s=30, max_rows=100000).rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="calibration"); ap.add_argument("--mode", default="benchmark")
    ap.add_argument("--hints", default="false"); ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="0/1", help="i/N: this machine runs every N-th question")
    ap.add_argument("--ids-from", help="jsonl of a previous run; only questions with vote_share <= --max-vote are re-run")
    ap.add_argument("--max-vote", type=float, default=0.4)
    ap.add_argument("--tag", default="", help="suffix for the output file, so experiments never overwrite a main run")
    a = ap.parse_args()
    qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
    ids = set(json.loads((ROOT / "eval/split.json").read_text())["report" if a.split == "report" else "calibration"])
    qs = [q for q in qs if q["question_id"] in ids][: a.limit or None]
    if a.ids_from:
        prev = [json.loads(l) for l in open(a.ids_from) if l.strip()]
        low = {r["question_id"] for r in prev if r["signals"].get("vote_share", 1) <= a.max_vote}
        qs = [q for q in qs if q["question_id"] in low]
    si, sn = map(int, a.shard.split("/")); qs = qs[si::sn]
    sfx = "" if sn == 1 else f"_shard{si}of{sn}"
    out = ROOT / f"results/agent_{a.split}_{a.mode}_hints_{a.hints}_n{a.n}{sfx}{('_' + a.tag) if a.tag else ''}.jsonl"
    done = {json.loads(l)["question_id"] for l in out.open()} if out.exists() else set()
    for i, q in enumerate(qs):
        if q["question_id"] in done: continue
        t = time.time()
        r = ask(q["question"], q["db_id"], a.mode, a.n, hint=q["evidence"] if a.hints == "true" else "")
        hit = False
        if r["sql"]:  # score refused SQL too: calibration needs the true label; outcome() applies status
            try: hit = rows_set(q["db_id"], r["sql"]) == rows_set(q["db_id"], q["SQL"])
            except Exception: hit = False
        rec = dict(question_id=q["question_id"], difficulty=q["difficulty"], status=r["status"], correct=hit,
                   confidence=r["confidence"], signals=r["signals"], seconds=round(time.time() - t, 1), sql=r["sql"],
                   candidates=[{"sql": c["sql"], "group": c.get("group"), "error": c["error"]} for c in r.get("candidates", [])],
                   tiebreak=next((t_["detail"].get("tiebreak") for t_ in r.get("trace", []) if t_["step"] == "run"), None))
        with out.open("a") as f: f.write(json.dumps(rec, default=str) + "\n")
        print(f"[{i+1}/{len(qs)}] q{q['question_id']} {r['status']} correct={hit} {rec['seconds']}s", flush=True)

main()
