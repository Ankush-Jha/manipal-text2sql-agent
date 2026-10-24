"""Follow-up questions on a writer that only reads one standalone question: rewrite the follow-up into a standalone
question (Qwen3-8B, grounded in the SQL that actually ran), let the unchanged writer answer it, then check in code
that the filters of the previous turn survived unless the user dropped them."""
import re

from agent import guard
from agent.sanitize import clean_value

PROMPT = """You turn a follow-up message into one standalone question about a database. Reply with JSON only.
Keys: "depends" (true if the message needs the earlier turn), "standalone" (the full question, repeating every condition from the earlier turn that still applies), "drop" (list of column or condition names the user removed or replaced; [] if none).
Never invent conditions the user did not give. If the message is a new topic, depends is false and standalone is the message itself.

Example
Earlier question: How many schools are in Alameda county?
Earlier SQL conditions: county = 'alameda'
Follow-up: now only the charter ones
{{"depends": true, "standalone": "How many charter schools are in Alameda county?", "drop": []}}

Example
Earlier question: List the cards with power above 5 in set 10E.
Earlier SQL conditions: power > 5; setcode = '10e'
Follow-up: same but for set 2ED
{{"depends": true, "standalone": "List the cards with power above 5 in set 2ED.", "drop": ["setcode"]}}

Earlier question: {prev_q}
Earlier SQL conditions: {conds}
Follow-up: {msg}
"""


def rewrite(message: str, history: list[dict], chat_json=None) -> dict:
    """{"depends": bool, "standalone": str, "drop": [str]}. Falls back to the message alone when the model gives nothing usable."""
    from agent.decider import chat_json as default_chat
    prev = history[-1]
    conds = "; ".join(sorted(guard.constraints(prev.get("sql") or ""))) or "none"
    out = (chat_json or default_chat)(PROMPT.format(prev_q=clean_value(prev["standalone"], "history"), conds=conds, msg=clean_value(message, "history")))
    standalone = str(out.get("standalone") or "").strip()
    # guard against the 8B repeating the previous question instead of answering the new one
    if not out.get("depends") or not standalone or standalone.strip().lower() == prev["standalone"].strip().lower():
        return {"depends": False, "standalone": message, "drop": []}
    return {"depends": True, "standalone": standalone, "drop": [str(x).lower() for x in out.get("drop") or []]}


def kept_constraints(prev_sql: str, drop: list[str]) -> set[str]:
    """Previous turn's WHERE/HAVING atoms that should still be in the new query."""
    out = set()
    for atom in guard.constraints(prev_sql or ""):
        names = set(re.findall(r"[a-z_][a-z0-9_ ]*", atom.replace('"', "").split("=")[0].split(">")[0].split("<")[0].split(" in ")[0]))
        if not any(d and (d in atom or any(d == n.strip() for n in names)) for d in drop):
            out.add(atom)
    return out


def carry_score(sql: str, kept: set[str]) -> float:
    if not kept:
        return 1.0
    have = guard.constraints(sql)
    return sum(a in have for a in kept) / len(kept)


def pick(reps: list[tuple[str, object]], kept: set[str]) -> int:
    """Index of the best group representative: highest carry score, ties go to the group with more votes (earlier)."""
    scores = [carry_score(sql, kept) for sql, _ in reps]
    best = max(scores, default=0)
    return scores.index(best) if scores else 0
