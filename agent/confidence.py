"""Calibrated P(correct) from cheap signals. Logistic regression fit on the CALIBRATION split only."""
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ["vote_share", "n_groups", "n_flags", "link_coverage", "judge_yes", "triage_ok", "error_rate"]
MODEL_PATH = ROOT / "results/confidence_model.json"


def vectorize(s: dict) -> list[float]:
    return [float(s.get(k, 0.0)) for k in FEATURES]


def fit(signals: list[dict], correct: list[bool]) -> dict:
    from sklearn.linear_model import LogisticRegression
    X, y = np.array([vectorize(s) for s in signals]), np.array(correct, dtype=int)
    m = LogisticRegression(max_iter=1000, class_weight=None).fit(X, y)
    return {"features": FEATURES, "coef": m.coef_[0].tolist(), "intercept": float(m.intercept_[0])}


def predict(model: dict, s: dict) -> float:
    z = model["intercept"] + sum(c * v for c, v in zip(model["coef"], vectorize(s)))
    return float(1 / (1 + np.exp(-z)))


def choose_threshold(probs: list[float], correct: list[bool], max_error: float = 0.15) -> float:
    """Lowest threshold whose answered-set error rate <= max_error (maximises coverage)."""
    order = sorted(set(probs))
    for t in order:
        kept = [(p, c) for p, c in zip(probs, correct) if p >= t]
        if kept and 1 - sum(c for _, c in kept) / len(kept) <= max_error:
            return float(t)
    return 1.01  # nothing is safe: refuse everything


def risk_coverage(probs: list[float], correct: list[bool]) -> list[dict]:
    pts = []
    for t in sorted(set(probs)):
        kept = [c for p, c in zip(probs, correct) if p >= t]
        pts.append({"threshold": float(t), "coverage": len(kept) / len(probs), "error": 1 - sum(kept) / len(kept)})
    return pts


def save(model: dict, threshold: float, path: Path = MODEL_PATH):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({**model, "threshold": threshold}, indent=1))


def load(path: Path = MODEL_PATH) -> tuple[dict, float] | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return d, d["threshold"]


def heuristic(s: dict) -> float:
    """Used only until a model is fitted on the calibration split."""
    p = (0.1 + 0.45 * s.get("vote_share", 0) + 0.3 * s.get("judge_yes", 0.5) + 0.1 * s.get("triage_ok", 1.0)
         - 0.15 * s.get("n_flags", 0) - 0.3 * s.get("error_rate", 0))
    return max(0.0, min(1.0, p))


def veto(s: dict) -> bool:
    """Triage and judge both say the data can't answer it: refuse even when every attempt agrees.
    Attempts can agree on the same wrong column; triage alone gave 40% false refusals, so it never gates by itself."""
    return (s.get("triage_ok", 1.0) <= float(os.getenv("VETO_TRIAGE_MAX", "0.15"))
            and s.get("judge_yes", 1.0) < float(os.getenv("VETO_JUDGE_MAX", "0.5")))
