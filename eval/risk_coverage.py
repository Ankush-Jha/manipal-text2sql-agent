"""TrustSQL-style reliability scoring + risk-coverage helpers.
Outcomes: correct (+1), refused_answerable (0), wrong (-c), answered_unanswerable (-c), refused_unanswerable (+1)."""
from collections import Counter


def outcome(answerable: bool, status: str, correct: bool) -> str:
    refused = status != "answered"
    if answerable:
        return "refused_answerable" if refused else ("correct" if correct else "wrong")
    return "refused_unanswerable" if refused else "answered_unanswerable"


def trustsql_score(outcomes: list[str], penalty: float = 1.0) -> float:
    pts = {"correct": 1, "refused_unanswerable": 1, "refused_answerable": 0, "wrong": -penalty, "answered_unanswerable": -penalty}
    return sum(pts[o] for o in outcomes) / max(len(outcomes), 1)


def summarize(outcomes: list[str]) -> dict:
    n = len(outcomes)
    return {"n": n, "counts": dict(Counter(outcomes)),
            "score_c1": trustsql_score(outcomes, 1), "score_c5": trustsql_score(outcomes, 5), "score_c10": trustsql_score(outcomes, 10),
            "naive_refuse_all": trustsql_score(["refused_answerable" if o in ("correct", "wrong", "refused_answerable") else "refused_unanswerable" for o in outcomes], 1)}
