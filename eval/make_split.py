"""Fixed split of BIRD Mini-Dev: 150 reporting / 350 calibration, stratified by difficulty, seed 42.
Never tune on the reporting set."""
import json
import random
from collections import defaultdict
from pathlib import Path

SEED, N_REPORT = 42, 150
ROOT = Path(__file__).resolve().parent.parent


def make_split(questions: list[dict]) -> dict:
    by_diff = defaultdict(list)
    for q in questions:
        by_diff[q["difficulty"]].append(q["question_id"])
    rng = random.Random(SEED)
    report: list[int] = []
    diffs = sorted(by_diff)
    quotas = {d: round(N_REPORT * len(by_diff[d]) / len(questions)) for d in diffs}
    quotas[diffs[-1]] += N_REPORT - sum(quotas.values())  # absorb rounding drift
    for d in diffs:
        ids = sorted(by_diff[d])
        rng.shuffle(ids)
        report += ids[: quotas[d]]
    rset = set(report)
    calib = sorted(q["question_id"] for q in questions if q["question_id"] not in rset)
    return {"seed": SEED, "report": sorted(report), "calibration": calib}


if __name__ == "__main__":
    qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
    split = make_split(qs)
    out = ROOT / "eval/split.json"
    out.write_text(json.dumps(split, indent=1))
    print(f"report={len(split['report'])} calibration={len(split['calibration'])} -> {out}")
