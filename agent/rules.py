"""Business Rules Registry: approved metric definitions per database, read from rules/<db_id>.json.

Every word list lives in the registry (business-owned config), never in code. Per question:
1. the judge model fixes spelling and extracts the quantity being asked for ("students avg" -> quantity "average"),
2. candidates = rules behind a business term the question uses ("performance"), or every approved rule when the
   quantity is missing or vague ("average", "NONE"),
3. rule keywords found in the question and the user's earlier answers narrow the candidates ("subject" -> 3 SAT subjects),
4. one candidate left: apply it. Several: ask the user, offering only rules the database can compute, and repeat
   until one is left or max_clarify_rounds is reached (then proceed on the user's own words)."""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT / "rules"
FIELDS = ("metric", "definition", "formula", "aggregation", "include", "exclude", "time_basis", "tables", "joins", "owner", "version", "approval")


@lru_cache(maxsize=32)
def _raw(db_id: str) -> dict:
    p = RULES_DIR / f"{db_id}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load(db_id: str, profile: dict) -> dict:
    """Registry with each rule marked `available` (approved and every column present in the profile)."""
    raw = _raw(db_id)
    cols = {f"{t}.{c}".lower() for t, cs in profile["tables"].items() for c in cs}
    rules = {}
    for rid, r in raw.get("rules", {}).items():
        missing = [c for c in r.get("columns", []) if c.lower() not in cols]
        rules[rid] = {**r, "id": rid, "missing_columns": missing,
                      "available": r.get("approval") == "approved" and not missing}
    return {"conventions": raw.get("conventions", {}), "rules": rules, "terms": raw.get("terms", {}),
            "vague": [v.lower() for v in raw.get("vague_quantities", [])],
            "max_rounds": int(raw.get("max_clarify_rounds", os.getenv("MAX_CLARIFY_ROUNDS", "3")))}


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", text) is not None


def _vague(quantity: str, vague: list[str]) -> bool:
    words = re.findall(r"[a-z0-9]+", quantity.lower())
    return not words or quantity.lower().strip() in vague or all(w in vague for w in words)


def resolve(question: str, registry: dict, rewrite_fn=None, choice: str | None = None, rounds: int = 0) -> dict:
    """-> {"applied", "clarify", "rewritten", "quantity", "lines"}. choice: a rule id the user picked.
    rounds: clarification questions already asked for this question (the user's typed answers are in `question`)."""
    rules = registry.get("rules", {})
    out = {"applied": [], "clarify": None, "rewritten": None, "quantity": None, "lines": []}
    if choice in rules and rules[choice]["available"]:
        out["applied"] = [rules[choice]]
    elif any(r["available"] for r in rules.values()):
        rewritten, quantity = rewrite_fn(question) if rewrite_fn else (question, question)
        out["rewritten"], out["quantity"] = rewritten, quantity
        text = f"{question} {rewritten}".lower()
        cands = [rules[i] for term, ids in registry.get("terms", {}).items() if _has(text, term)
                 for i in ids if i in rules and rules[i]["available"]]
        if not cands and (rounds > 0 or _vague(quantity, registry.get("vague", []))):  # a follow-up keeps the conversation going
            cands = [r for r in rules.values() if r["available"]]
        cands = list({r["id"]: r for r in cands}.values())
        hits = {r["id"]: sum(_has(text, k) for k in r.get("keywords", [])) for r in cands}
        best = max(hits.values(), default=0)
        named = [r for r in cands if best and hits[r["id"]] == best]  # most keyword hits win: "SAT writing" -> writing
        pool = named or cands
        if len(pool) == 1:
            out["applied"] = pool
        elif pool and rounds < registry.get("max_rounds", 3):
            out["clarify"] = {"narrowed": bool(named) or rounds > 0, "round": rounds + 1,
                              "options": [{"id": r["id"], "label": r["label"], "detail": r["definition"]} for r in pool]}
    out["lines"] = [rule_line(r) for r in out["applied"]]
    if out["rewritten"] and out["rewritten"].strip().lower() != question.strip().lower():
        out["lines"].append(f"The question with spelling fixed: {out['rewritten']}")
    return out


def rule_line(r: dict) -> str:
    return (f"Business rule '{r['metric']}' (v{r['version']}, {r['approval']}): {r['definition']} "
            f"Compute as {r['formula']}; {r['aggregation']}. Include {r['include']}; exclude {r['exclude']}. "
            f"Join {r['joins']}. Time basis: {r['time_basis']}.")


def summary(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", *FIELDS)}
