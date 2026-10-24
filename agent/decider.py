"""decide(question, options) -> {option: prob}. Local = Qwen3-8B letter logprobs. Jev branch is gated."""
import math
import os
import string

import httpx


class DeciderError(RuntimeError):
    pass


def _prompt(question: str, options: list[str], context: str, descriptions: dict | None = None) -> str:
    letters = string.ascii_uppercase
    d = descriptions or {}
    opts = "\n".join(f"{letters[i]}. {o}" + (f": {d[o]}" if o in d else "") for i, o in enumerate(options))
    return (f"{context}\n\nQuestion: {question}\n\nOptions:\n{opts}\n\n"
            "Answer with a single letter only.")


def decide_local(url: str, question: str, options: list[str], context: str = "", descriptions: dict | None = None) -> dict[str, float]:
    """Reads the first-token probabilities of each option letter. Fails loudly if logprobs are missing."""
    r = httpx.post(f"{url}/chat/completions", timeout=120, json={
        "model": "judge", "messages": [{"role": "user", "content": _prompt(question, options, context, descriptions)}],
        "max_tokens": 1, "temperature": 0, "logprobs": True, "top_logprobs": 20,
        "chat_template_kwargs": {"enable_thinking": False}})
    r.raise_for_status()
    ch = r.json()["choices"][0]
    content = (ch.get("logprobs") or {}).get("content")
    if not content:
        raise DeciderError("judge server returned no logprobs; use llama-server or vLLM")
    letters = string.ascii_uppercase
    # sum every spelling of the same capital letter ("A", " A"); never fold case, or the article "a" overwrites the letter A
    mass = {}
    for t in content[0]["top_logprobs"]:
        k = t["token"].strip()
        if len(k) == 1 and k in letters:
            mass[k] = mass.get(k, 0.0) + math.exp(t["logprob"])
    probs = {o: mass.get(letters[i], 0.0) for i, o in enumerate(options)}
    total = sum(probs.values())
    if total <= 0:
        raise DeciderError("none of the option letters appeared in top logprobs")
    return {o: p / total for o, p in probs.items()}


def decide(question: str, options: list[str], context: str = "", kind: str | None = None,
           judge_url: str | None = None, descriptions: dict | None = None) -> dict[str, float]:
    kind = kind or os.getenv("DECIDER", "local")
    if kind == "jev":
        if not os.getenv("TYPESAFE_API_KEY"):
            raise DeciderError("DECIDER=jev needs TYPESAFE_API_KEY (and organiser approval)")
        raise NotImplementedError("Jev branch is a stretch goal; use DECIDER=local")
    return decide_local(judge_url or os.getenv("JUDGE_URL", "http://localhost:8082/v1"), question, options, context, descriptions)


REWRITE_PROMPT = (
    "Fix the spelling in the user's question and rewrite it as one short, precise question. Do not add details the user did not give.\n"
    "Then copy the exact quantity being computed or listed (the noun phrase after words like average/total/count/highest/list). "
    "If the question gives no such noun phrase, write NONE.\n"
    "Answer in exactly this format:\nREWRITTEN: <question>\nQUANTITY: <phrase or NONE>\n\nUser question: {q}")


def rewrite(question: str, judge_url: str | None = None) -> tuple[str, str]:
    """(spelling-fixed question, quantity phrase or 'NONE') from the judge model. Extraction, not judgment: an 8B model
    copies a phrase far more reliably than it rates vagueness."""
    url = judge_url or os.getenv("JUDGE_URL", "http://localhost:8082/v1")
    r = httpx.post(f"{url}/chat/completions", timeout=60, json={
        "model": "judge", "messages": [{"role": "user", "content": REWRITE_PROMPT.format(q=question)}],
        "max_tokens": 80, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}})
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    field = lambda k: next((ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.upper().startswith(k + ":")), "")
    return field("REWRITTEN") or question, field("QUANTITY") or "NONE"


def chat_json(prompt: str, judge_url: str | None = None, max_tokens: int = 220) -> dict:
    """One short Qwen3-8B call that must answer with a JSON object; {} when it does not."""
    import json
    import re
    url = judge_url or os.getenv("JUDGE_URL", "http://localhost:8082/v1")
    r = httpx.post(f"{url}/chat/completions", timeout=90, json={
        "model": "judge", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False}})
    r.raise_for_status()
    m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}
