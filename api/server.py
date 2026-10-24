"""FastAPI server: the agent API plus the web UI in ui/.
Run: .venv/bin/uvicorn api.server:app --port 8000   then open http://localhost:8000"""
import asyncio
import json
import os
import queue
import re
import threading
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agent import agent as agent_mod, roles as roles_mod, rules as rules_mod, sanitize
from agent.profiler import ROOT, profile_db
from eval import summarize

sanitize.enable(os.getenv("SECURE", "1") == "1")  # the served agent treats database text as data
app = FastAPI(title="Text-to-SQL analyst")
DB_DIR = ROOT / "data/dev_databases"
UI_DIR = ROOT / "ui"
EXAMPLES = json.loads((ROOT / "config/examples.json").read_text())  # demo questions per database
_cancel = threading.Event()


class AskBody(BaseModel):
    question: str
    db: str
    mode: str = Field("product", pattern="^(product|benchmark)$")
    n_samples: int = Field(5, ge=1, le=8)
    decider: str = Field("local", pattern="^(local|jev)$")
    hint: str = ""
    choice: str | None = None  # rule id picked after a clarification question
    rounds: int = Field(0, ge=0, le=10)  # clarification questions already asked for this question
    role: str | None = None  # stands in for the logged-in user's role; resolved here, never read from the question text
    history: list[dict] | None = None  # [{"standalone": str, "sql": str | None}, ...] previous turns for follow-up rewriting


def _up(url: str) -> bool:
    try:
        return httpx.get(url.replace("/v1", "") + "/health", timeout=1.5).status_code == 200
    except Exception:
        return False


@app.get("/api/health")
def health():
    judge = _up(os.getenv("JUDGE_URL", "http://localhost:8082/v1"))
    # llama-server returns token logprobs (verified, with thinking disabled), so a live judge means logprobs work
    return {"writer": _up(os.getenv("WRITER_URL", "http://localhost:8081/v1")), "judge": judge, "logprobs": judge}


@app.get("/api/databases")
def databases():
    out = []
    for p in sorted(DB_DIR.iterdir()):
        if p.is_dir():
            cached = (ROOT / f"cache/profile_{p.name}.json").exists()
            prof = profile_db(p.name) if cached else None
            out.append({"id": p.name, "tables": len(prof["tables"]) if prof else None,
                        "columns": sum(len(c) for c in prof["tables"].values()) if prof else None,
                        "profile": "ready" if cached else "building", "progress": 1.0 if cached else 0.0,
                        "examples": len(EXAMPLES.get(p.name, []))})
    return out


@app.get("/api/roles")
def role_list(db: str = "california_schools"):
    r = roles_mod.load(db)["roles"]
    return [{"id": k, "description": v["description"]} for k, v in r.items()]


@app.get("/api/examples")
def examples(db: str = "california_schools"):
    return EXAMPLES.get(db, [])


@app.get("/api/profile")
def profile(db: str):
    if not (DB_DIR / db).is_dir():
        raise HTTPException(404, "unknown database")
    prof = profile_db(db)
    tables = []
    for t, cols in prof["tables"].items():
        rows = max((c["rows"] for c in cols.values()), default=0)
        tables.append({"name": t, "rows": rows, "columns": [
            {"name": c, "type": i["type"], "null_rate": i["null_rate"], "distinct": i["distinct"],
             "dirty": i["dirty_tokens"], "date_formats": i["date_formats"], "mixed_dates": i["mixed_date_formats"],
             "top": [str(v)[:40] for v, _ in i["top_values"][:5]],
             "description": i.get("description", {}).get("description", ""),
             "values": i.get("description", {}).get("values", "")[:200]} for c, i in cols.items()]})
    return {"db": db, "tables": tables}


@app.get("/api/rules")
def rules(db: str):
    """The Business Rules Registry for a database, with each rule checked against the actual columns."""
    if not (DB_DIR / db).is_dir():
        raise HTTPException(404, "unknown database")
    reg = rules_mod.load(db, profile_db(db))
    return {"db": db, "conventions": reg["conventions"],
            "rules": [{**rules_mod.summary(r), "label": r.get("label"), "available": r["available"],
                       "missing_columns": r["missing_columns"]} for r in reg["rules"].values()]}


@app.post("/api/ask")
async def ask(body: AskBody):
    if not (DB_DIR / body.db).is_dir():
        raise HTTPException(404, "unknown database")
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    try:
        run_db, run_root = roles_mod.resolve(body.db, body.role)
    except KeyError:
        raise HTTPException(403, "unknown role")
    except roles_mod.PolicyInvalid as e:
        raise HTTPException(409, f"role disabled until its policy is fixed: {e}")
    q: queue.Queue = queue.Queue()
    _cancel.clear()
    os.environ["DECIDER"] = body.decider
    t0 = time.time()

    def emit(step, state, seconds, detail):
        q.put(("step", {"step": step, "state": state, "seconds": seconds, "t": round(time.time() - t0, 2), "detail": detail}))

    def work():
        try:
            if body.role:
                policy = roles_mod.load(body.db)["roles"].get(body.role)
                if policy:
                    role_title = body.role.replace("_", " ").title()
                    # check if restricted table requested in question
                    prof = profile_db(body.db)
                    full_tables = set(prof["tables"].keys())
                    allowed_tables = set(policy.get("tables", {}).keys())
                    disallowed_tables = full_tables - allowed_tables
                    for dt in disallowed_tables:
                        if re.search(rf"\b{re.escape(dt)}\b", body.question, re.I):
                            q.put(("result", {
                                "status": "permission",
                                "reason": f"Table '{dt}' is restricted for role '{role_title}'.",
                                "role": body.role, "role_title": role_title, "restricted_item": dt,
                                "sql": None, "answer_rows": [], "columns": [], "total_seconds": 0.01
                            }))
                            q.put(None)
                            return
                    for tbl, spec in policy.get("tables", {}).items():
                        for exc_col in spec.get("except", []):
                            if re.search(rf"\b{re.escape(exc_col)}\b", body.question, re.I):
                                q.put(("result", {
                                    "status": "permission",
                                    "reason": f"Column '{exc_col}' is restricted for role '{role_title}'.",
                                    "role": body.role, "role_title": role_title, "restricted_item": exc_col,
                                    "sql": None, "answer_rows": [], "columns": [], "total_seconds": 0.01
                                }))
                                q.put(None)
                                return

            r = agent_mod.ask(body.question, run_db, body.mode, body.n_samples, hint=body.hint, emit=emit,
                              choice=body.choice, rounds=body.rounds, db_root=run_root,
                              history=body.history or None)
            r["total_seconds"] = round(time.time() - t0, 2)

            # post-check: if refused due to role-restricted column/table
            if body.role and r.get("status") == "refused":
                policy = roles_mod.load(body.db)["roles"].get(body.role)
                if policy:
                    role_title = body.role.replace("_", " ").title()
                    errors = [c.get("error") or "" for c in r.get("candidates", [])]
                    for err in errors:
                        m_col = re.search(r"no such column:\s*(?:[\w\.]+\.)?(\w+)", err, re.I)
                        if m_col:
                            col_name = m_col.group(1)
                            for tbl, spec in policy.get("tables", {}).items():
                                if any(c.lower() == col_name.lower() for c in spec.get("except", [])):
                                    r["status"] = "permission"
                                    r["reason"] = f"Column '{col_name}' is restricted for role '{role_title}'."
                                    r["role"] = body.role
                                    r["role_title"] = role_title
                                    r["restricted_item"] = col_name
                                    break
                        m_tbl = re.search(r"no such table:\s*(\w+)", err, re.I)
                        if m_tbl:
                            tbl_name = m_tbl.group(1)
                            full_tables = set(profile_db(body.db)["tables"].keys())
                            if tbl_name.lower() in {t.lower() for t in full_tables} and tbl_name.lower() not in {t.lower() for t in policy.get("tables", {})}:
                                r["status"] = "permission"
                                r["reason"] = f"Table '{tbl_name}' is restricted for role '{role_title}'."
                                r["role"] = body.role
                                r["role_title"] = role_title
                                r["restricted_item"] = tbl_name
                                break

            q.put(("result", r))
        except httpx.ConnectError:
            need = "the writer" + (" and the judge" if body.mode == "product" else "")
            q.put(("error", {"code": "models_down", "message": f"A model server isn't running. Start {need} and try again."}))
        except Exception as e:
            msg = str(e)
            if body.role and ("no such column" in msg.lower() or "restricted" in msg.lower() or "guard" in msg.lower() or "policy" in msg.lower()):
                role_title = body.role.replace("_", " ").title()
                m_col = re.search(r"no such column:\s*(?:[\w\.]+\.)?(\w+)", msg, re.I)
                clean_msg = f"Column '{m_col.group(1)}' is restricted for role '{role_title}'." if m_col else f"Access restricted for role '{role_title}': {msg[:120]}"
                q.put(("result", {"status": "permission", "reason": clean_msg, "role": body.role, "role_title": role_title, "total_seconds": round(time.time() - t0, 2)}))
            else:
                q.put(("error", {"code": "internal", "message": "Something went wrong while answering. Try rephrasing.", "debug": msg[:300]}))
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    async def gen():
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None or _cancel.is_set():
                break
            yield {"event": item[0], "data": json.dumps(item[1], default=str)}
    return EventSourceResponse(gen())


@app.post("/api/cancel")
def cancel():
    _cancel.set()
    return {}


@app.get("/api/results")
def results():
    return summarize.build()


app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(UI_DIR / "index.html")
