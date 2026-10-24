"""Ask only when the database says the readings differ: at least two result groups each backed by several of the
N sampled queries, both returning rows, and a judge that finds both reasonable. Everything else is answered."""
import sqlglot

from agent import guard

MIN_VOTES = 2


def describe(side: dict, key: str) -> str:
    proj, cons = side[f"projections_only_{key}"], side[f"constraints_only_{key}"]
    parts = []
    if proj:
        parts.append("returning " + ", ".join(proj[:3]))
    if cons:
        parts.append("where " + " and ".join(cons[:3]))
    return " ".join(parts) or "the same query without the extra conditions"


def preview(res, n: int = 3) -> str:
    return f"{len(res.rows)} row(s), e.g. " + "; ".join(", ".join(str(v)[:30] for v in r[:4]) for r in res.rows[:n])


def gate(run: dict, question: str, decide, min_votes: int = MIN_VOTES) -> dict | None:
    """Returns {"options": [{"label","sql","preview","votes"}...]} when the question should be asked back, else None."""
    strong = [(g, rep) for g, rep in zip(run["groups"], run["reps"]) if g["size"] >= min_votes and g["rows"] > 0]
    if len(strong) < 2:
        return None
    (ga, (sa, ra)), (gb, (sb, rb)) = strong[:2]
    try:
        d = guard.diff(sa, sb)
    except sqlglot.errors.SqlglotError:
        return None
    if not any(d[k] for k in d):  # same tables, conditions and columns: rounding or ordering, answer and let the checks speak
        return None
    ctx = (f"Two ways to read the question, each run on the database:\nA: {describe(d, 'a')} ({preview(ra)})\n"
           f"B: {describe(d, 'b')} ({preview(rb)})\nAre both readings reasonable answers to the question below?")
    if decide(question, ["yes", "no"], ctx).get("yes", 0.0) < 0.5:
        return None
    return {"options": [{"label": describe(d, k), "sql": s, "preview": preview(r), "votes": g["size"]}
                        for k, s, r, g in (("a", sa, ra, ga), ("b", sb, rb, gb))]}
