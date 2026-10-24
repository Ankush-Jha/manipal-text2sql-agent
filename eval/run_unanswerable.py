"""Run the agent (product mode) on the unanswerable sets; log whether it refused. Needs model servers.
Usage: python -m eval.run_unanswerable [--limit N]"""
import json, sys, time
from pathlib import Path
from agent.agent import ask
from eval.unanswerable import OUT, load_human

ROOT = Path(__file__).resolve().parent.parent
items = json.loads((ROOT / "eval/unanswerable_auto.json").read_text()) + load_human()
if "--limit" in sys.argv: items = items[: int(sys.argv[sys.argv.index("--limit") + 1])]
out = ROOT / "results/unanswerable_product.jsonl"
done = {json.loads(l)["id"] for l in out.open()} if out.exists() else set()
for i, it in enumerate(items):
    iid = it.get("id") or f"h{i}_{it['db_id']}"
    if iid in done: continue
    t = time.time()
    root = OUT if it.get("source_db") else None
    r = ask(it["question"], it["db_id"], "product", 5, db_root=root)
    rec = dict(id=iid, type=it.get("type"), status=r["status"], reason=r["reason"], confidence=r["confidence"], signals=r["signals"], sql=r["sql"], seconds=round(time.time() - t, 1))
    with out.open("a") as f: f.write(json.dumps(rec) + "\n")
    print(f"[{i+1}/{len(items)}] {iid} -> {r['status']}", flush=True)
