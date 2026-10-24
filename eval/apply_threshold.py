"""Re-decide product-mode runs with the fitted confidence model (no model servers needed).
Runs recorded before calibration used the heuristic and threshold 0.5; this replays the decide step on their saved signals.
Only records that reached the decide step (signals carry "flags") change; triage refusals and no-runnable-SQL refusals stay.
Usage: python -m eval.apply_threshold results/agent_report_product_hints_false_n5.jsonl results/unanswerable_product.jsonl"""
import json, sys
from pathlib import Path
from agent import confidence

loaded = confidence.load()
if not loaded:
    sys.exit("no results/confidence_model.json: run eval.calibrate first")
model, thr = loaded
for path in sys.argv[1:]:
    recs = [json.loads(l) for l in open(path) if l.strip()]
    changed = 0
    for r in recs:
        s = r.get("signals") or {}
        if not r.get("sql") or "flags" not in s:
            continue
        r["confidence"] = confidence.predict(model, s | {"n_flags": len(s["flags"])})
        status = "answered" if r["confidence"] >= thr and not confidence.veto(s) else "refused"
        changed += status != r["status"]; r["status"] = status
    Path(path).write_text("".join(json.dumps(r, default=str) + "\n" for r in recs))
    print(f"{path}: threshold {thr:.3f}; answered {sum(r['status'] == 'answered' for r in recs)}/{len(recs)} ({changed} changed)")
