"""Score a conversations_*.json file live, turn by turn, chaining real history (not gold) into the next turn.
Usage: python -m eval.run_conversations eval/sets/conversations_dev_20.json [--n 5]"""
import argparse
import json
import time
from pathlib import Path

from agent.agent import ask
from agent.executor import execute

ROOT = Path(__file__).resolve().parent.parent


def rows(db, sql):
    return sorted(map(repr, execute(db, sql, timeout_s=30, max_rows=100000).rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?", default="eval/sets/conversations_dev_20.json")
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    data = json.loads((ROOT / a.set).read_text())
    out = ROOT / f"results/conversations_{Path(a.set).stem}_n{a.n}.jsonl"
    done = {json.loads(l)["key"] for l in out.open()} if out.exists() else set()
    for conv in data:
        db = ROOT / f"data/dev_databases/{conv['db_id']}/{conv['db_id']}.sqlite"
        history = []
        for i, turn in enumerate(conv["turns"]):
            key = f"{conv['conv_id']}:{i}"
            if key in done:
                # replay from the recorded result so later turns still chain correctly on resume
                prev = next(json.loads(l) for l in out.open() if json.loads(l)["key"] == key)
                history.append({"standalone": turn["standalone"] if prev["correct"] else turn["question"], "sql": prev["sql"]})
                continue
            t0 = time.time()
            r = ask(turn["question"], conv["db_id"], "benchmark", a.n, history=history or None)
            try:
                hit = bool(r["sql"]) and rows(db, r["sql"]) == rows(db, turn["gold_sql"])
            except Exception:
                hit = False
            rec = dict(key=key, conv_id=conv["conv_id"], turn=i, type=turn["type"], question=turn["question"],
                       interpreted_as=r.get("interpreted_as"), gold_standalone=turn["standalone"], sql=r["sql"],
                       correct=hit, status=r["status"], seconds=round(time.time() - t0, 1))
            with out.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            print(f"[{conv['conv_id']} t{i} {turn['type']}] correct={hit} interp={r.get('interpreted_as')!r} {rec['seconds']}s", flush=True)
            history.append({"standalone": r.get("interpreted_as") or turn["question"], "sql": r["sql"]})

    recs = [json.loads(l) for l in out.open()]
    per_turn = {}
    for r in recs:
        per_turn.setdefault(r["turn"], []).append(r["correct"])
    conv_ok = {}
    for r in recs:
        conv_ok.setdefault(r["conv_id"], []).append(r["correct"])
    lines = [f"# Follow-up conversations: {Path(a.set).name} (n={a.n})", "",
             "| Turn | EX |", "|---|---|"] + [f"| {t + 1} | {100 * sum(v) / len(v):.0f}% ({sum(v)}/{len(v)}) |" for t, v in sorted(per_turn.items())]
    whole = sum(all(v) for v in conv_ok.values())
    lines += ["", f"Whole-conversation EX (all turns correct): {whole}/{len(conv_ok)} ({100 * whole / len(conv_ok):.0f}%)"]
    Path(f"results/conversations_{Path(a.set).stem}_n{a.n}.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
