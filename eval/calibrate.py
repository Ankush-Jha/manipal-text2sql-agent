"""Fit the confidence model on CALIBRATION-split agent runs (product mode), choose the threshold, save to results/.
Usage: python -m eval.calibrate results/agent_calibration_product_hints_false_n5.jsonl [--max-error 0.15]"""
import json, sys
from agent import confidence

path = sys.argv[1]
max_err = float(sys.argv[sys.argv.index("--max-error") + 1]) if "--max-error" in sys.argv else 0.15
recs = [json.loads(l) for l in open(path)]
recs = [r for r in recs if r["sql"] and r["signals"]]
sig, y = [r["signals"] | {"n_flags": len(r["signals"].get("flags", []))} for r in recs], [r["correct"] for r in recs]
model = confidence.fit(sig, y)
probs = [confidence.predict(model, s) for s in sig]
thr = confidence.choose_threshold(probs, y, max_err)
confidence.save(model, thr)
print(f"fit on {len(recs)} questions; base accuracy {sum(y)/len(y):.1%}; threshold {thr:.3f}")
json.dump(confidence.risk_coverage(probs, y), open("results/risk_coverage_calibration.json", "w"), indent=1)
