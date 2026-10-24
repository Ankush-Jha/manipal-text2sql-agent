"""Arctic-Text2SQL-R1 writer. The template below is copied verbatim from the OmniSQL repo
(README, "Prompt Template"). Do NOT edit it: the model was trained on this format.
Hints go inside {question}; schema DDL (with value/description comments) goes in {db_details}."""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

INPUT_PROMPT_TEMPLATE = '''Task Overview:
You are a data science expert. Below, you are provided with a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

Database Engine:
SQLite

Database Schema:
{db_details}
This schema describes the database's structure, including tables, columns, primary keys, foreign keys, and any relevant relationships or constraints.

Question:
{question}

Instructions:
- Make sure you only output the information that is asked in the question. If the question asks for a specific column, make sure to only include that column in the SELECT clause, nothing more.
- The generated query should return all of the information asked in the question without any missing or extra information.
- Before generating the final SQL query, please think through the steps of how to write the query.

Output Format:
In your answer, please enclose the generated SQL query in a code block:
```
-- Your SQL query
```

Take a deep breath and think step by step to find the correct SQL query.'''

_BLOCK = re.compile(r"```(?:sql)?\s*\n(.*?)```", re.S | re.I)


def build_prompt(db_details: str, question: str, hint: str = "") -> str:
    q = f"{question}\n{hint}".strip() if hint else question
    return INPUT_PROMPT_TEMPLATE.format(db_details=db_details, question=q)


def extract_sql(text: str) -> str | None:
    """Last fenced code block in the completion, or None."""
    blocks = _BLOCK.findall(text)
    return blocks[-1].strip() if blocks else None


def _one(url, prompt, temperature, max_tokens, timeout):
    """Streams the completion and disconnects right after the SQL code block closes.
    The model reliably emits exactly one fenced block then rambles for hundreds of
    unused tokens (extract_sql only ever reads the last block); cutting the
    connection there stops the server from generating them."""
    chunks = []
    fences = 0
    with httpx.stream(
        "POST", f"{url}/chat/completions", timeout=timeout,
        json={"model": "writer", "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature, "max_tokens": max_tokens, "stream": True},
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            delta = json.loads(payload)["choices"][0]["delta"].get("content", "")
            if delta:
                chunks.append(delta)
                fences += delta.count("```")
                if fences >= 2:
                    break
    return extract_sql("".join(chunks))


def sample(url: str, prompt: str, n: int, temperature: float, max_tokens: int = 2048,
           timeout: float = 600, parallel: int = 4, on_each=None) -> list[str | None]:
    """n extracted SQL strings (None where no code block). Requests run in parallel across the
    server's slots: decoding is memory-bandwidth bound, so 4 streams cost far less than 4x the time."""
    temp = 0.0 if (n == 1 or temperature == 0) else temperature
    out: list[str | None] = [None] * n
    with ThreadPoolExecutor(max_workers=min(n, parallel)) as ex:
        futs = {ex.submit(_one, url, prompt, temp, max_tokens, timeout): i for i in range(n)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
            if on_each:
                on_each(futs[f], out[futs[f]])
    return out
