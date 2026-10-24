"""Orchestration: link, hints, triage, write, run/vote, checks, judge, decide. Returns the output contract.
Model calls are injectable (deps) so the whole flow is testable without servers."""
import inspect
import os
import re
import sqlite3
import time
from pathlib import Path

import sqlglot
from sqlglot import exp

from agent import confidence, dates, decider as decider_mod, rules as rules_mod, writer
from agent.checks import run_checks
from agent.hints import hint_lines, hint_text
from agent.linker import link
from agent.profiler import profile_db
from agent.runner import run_candidates

ROOT = Path(__file__).resolve().parent.parent
TRIAGE = ["answerable", "ambiguous", "data_missing", "not_sql"]
TRIAGE_DESC = {
    "answerable": "every column and value the question needs is present in the tables above (codes are explained in the notes)",
    "ambiguous": "the question could mean several different measures or columns and the user has not said which",
    "data_missing": "the question needs a column or fact that is NOT in the tables above",
    "not_sql": "the question needs a forecast, an opinion, an action, or world knowledge that no table can give",
}
# Measured on 40 answerable vs 40 column-removed questions the 8B triage did not separate them
# (40% false refusals), so it is a soft feature by default. Set TRIAGE_REFUSE_P=0.85 to use it as a gate.
REFUSE_P = float(os.getenv("TRIAGE_REFUSE_P", "1.01"))


def triage(question, lk, lines, decide_fn):
    cols = "; ".join(f"{t}({', '.join(cs[:10])})" for t, cs in lk["columns"].items())
    notes = "\n".join(f"- {x}" for x in lines[:8])
    ctx = f"Database tables and columns: {cols}\nNotes about the data:\n{notes}\n\nCan this database answer the question below?"
    return decide_fn(question, TRIAGE, ctx, TRIAGE_DESC)


def schema_ddl(db_path, tables: list[str]) -> str:
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = c.execute("select name, sql from sqlite_master where type='table' and sql is not null").fetchall()
        return "\n\n".join(s for n, s in rows if n in tables)
    finally:
        c.close()


def check_context(sql: str, profile: dict) -> tuple[int | None, tuple[int, int] | None]:
    """(largest base-table row count in the query, (min_year, max_year) over the DB's ISO date columns)."""
    sizes = {t.lower(): max((c["rows"] for c in cols.values()), default=0) for t, cols in profile["tables"].items()}
    try:
        used = {t.name.lower() for t in sqlglot.parse_one(sql, read="sqlite").find_all(exp.Table)}
    except Exception:
        used = set()
    base_rows = max((sizes[t] for t in used if t in sizes), default=None)
    years = [int(str(v)[:4]) for cols in profile["tables"].values() for c in cols.values()
             if "iso" in c.get("date_formats", []) for v in (c.get("min"), c.get("max"))
             if v and re.match(r"^\d{4}", str(v))]
    return base_rows, ((min(years), max(years)) if years else None)


def default_deps():
    wurl = os.getenv("WRITER_URL", "http://localhost:8081/v1")
    return {
        "sample": lambda prompt, n, temp, on_each=None: writer.sample(wurl, prompt, n, temp, on_each=on_each),
        "decide": lambda q, opts, ctx="", desc=None: decider_mod.decide(q, opts, ctx, kind=os.getenv("DECIDER", "local"), descriptions=desc),
        "rewrite": decider_mod.rewrite,
    }


def ask(question: str, db_id: str, mode: str = "product", n_samples: int = 5, temperature: float = 0.8,
        hint: str = "", emit=None, deps: dict | None = None, db_root: Path | None = None, choice: str | None = None, rounds: int = 0) -> dict:
    """choice: a rule id the user picked after a clarification question. rounds: clarifications already asked;
    the user's typed answers are appended to `question`."""
    deps = deps or default_deps()
    db_path = (db_root or ROOT / "data/dev_databases") / db_id / f"{db_id}.sqlite"
    trace: list[dict] = []

    def step(name, fn):
        """fn() -> (value, detail). Emits start/done events and records the trace."""
        if emit: emit(name, "start", 0.0, {})
        t = time.time()
        value, detail = fn()
        secs = round(time.time() - t, 2)
        trace.append({"step": name, "seconds": secs, "detail": detail})
        if emit: emit(name, "done", secs, detail)
        return value

    def result(status, **kw):
        base = dict(status=status, answer_rows=[], columns=[], truncated=False, sql=None, candidates=[],
                    confidence=0.0, reason="", options=[], signals={}, threshold=None, mode=mode,
                    decider=os.getenv("DECIDER", "local"), trace=trace)
        base.update(kw)
        return base

    profile = profile_db(db_id, db_root)
    sig: dict = {"triage_ok": 1.0, "judge_yes": 0.5}

    def do_link():
        r = link(question, hint, profile, db_id, db_root=db_root)
        return r, {k: r[k] for k in ("tables", "core", "values", "coverage")}
    lk = step("link", do_link)
    sig["link_coverage"] = lk["coverage"]

    def do_hints():
        lines = hint_lines(lk, profile)
        return lines, {"lines": lines}
    lines = step("hints", do_hints)

    # business rules + time windows: product mode only, so benchmark numbers stay comparable with the plain model
    rules_res = {"applied": [], "lines": [], "windows": []}
    if mode == "product":
        registry = rules_mod.load(db_id, profile)

        def do_rules():
            r = rules_mod.resolve(question, registry, deps.get("rewrite"), choice, rounds)
            conv = registry["conventions"]
            r["windows"] = dates.windows(question, conv, profile)
            r["lines"] += [dates.window_line(w, conv) for w in r["windows"]]
            return r, {"rewritten": r["rewritten"], "quantity": r["quantity"], "applied": [rules_mod.summary(x) for x in r["applied"]], "clarify": r["clarify"],
                       "windows": r["windows"], "lines": r["lines"], "registry": bool(registry["rules"]),
                       "conventions": {k: conv[k] for k in ("timezone", "reference_date", "fiscal_year_start_month") if k in conv}}
        rules_res = step("rules", do_rules)
        if rules_res["clarify"]:
            c = rules_res["clarify"]
            return result("needs_clarification", signals=sig, choices=c["options"], options=[o["label"] for o in c["options"]],
                          clarify_round=c["round"],
                          reason=(f"Got it. That still matches {len(c['options'])} measures. Which one?" if c["narrowed"]
                                  else "The question doesn't say exactly what to measure. Which of these do you mean? "
                                       "Only measures this database can actually compute are listed; you can also type your own."))
        lines = rules_res["lines"] + lines

    if mode == "product":
        def do_triage():
            p = triage(question, lk, lines, deps["decide"])
            return p, {"probs": p}
        tri = step("triage", do_triage)
        sig["triage_ok"] = tri["answerable"]
        if tri["data_missing"] + tri["not_sql"] >= REFUSE_P:
            why = "the data does not contain what this question needs" if tri["data_missing"] >= tri["not_sql"] else "this needs a forecast, opinion or outside knowledge that SQL cannot provide"
            return result("refused", reason=f"I can't answer this: {why}.", signals=sig)
        if tri["ambiguous"] >= REFUSE_P:
            opts = [f"by {c}" for cs in lk["core"].values() for c in cs][:3]
            return result("needs_clarification", reason="The question is ambiguous. Which measure do you mean?", options=opts, signals=sig)

    full_hint = "\n".join(x for x in (hint, hint_text(lines)) if x)
    tables = lk["tables"] + [t for r in rules_res["applied"] for t in r.get("tables", []) if t not in lk["tables"]]
    ddl = schema_ddl(db_path, list(dict.fromkeys(tables)))
    prompt = writer.build_prompt(ddl, question, full_hint)
    sample = deps["sample"]
    streams = "on_each" in inspect.signature(sample).parameters

    def do_write():
        progress = (lambda i, sql: emit("write", "progress", 0.0, {"i": i, "sql": sql})) if emit and streams else None
        sqls = sample(prompt, n_samples, temperature, on_each=progress) if streams else sample(prompt, n_samples, temperature)
        return sqls, {"sqls": sqls}
    sqls = step("write", do_write)

    def repair(sql, err):
        p = writer.build_prompt(ddl, f"{question}\nA previous attempt:\n{sql}\nfailed with: {err}\nWrite a corrected query.", full_hint)
        return sample(p, 1, 0.0)[0]

    def do_run():
        r = run_candidates(db_path, sqls, repair)
        return r, {"groups": r["groups"], "candidates": r["candidates"]}
    run = step("run", do_run)
    cand_view = [{"sql": c["sql"], "error": c["error"], "repaired": c["repaired"], "rows": c["rows"],
                  "group": next((gi for gi, g in enumerate(run["groups"]) if c["sql"] in g["sqls"]), None)}
                 for c in run["candidates"]]
    step("vote", lambda: (None, {"vote_share": run["vote_share"], "n_groups": run["n_groups"], "winner": run["winner_sql"]}))
    bad = sum(1 for c in run["candidates"] if c["error"] or c["repaired"])
    sig.update(vote_share=run["vote_share"], n_groups=run["n_groups"], error_rate=bad / max(len(run["candidates"]), 1))

    if run["winner_sql"] is None:
        return result("refused", reason="None of the attempts produced a runnable query.", candidates=cand_view, signals=sig)
    res = run["winner_result"]

    def do_checks():
        base_rows, data_range = check_context(run["winner_sql"], profile)
        flags = run_checks(res.columns, res.rows, run["winner_sql"], base_rows=base_rows, data_range=data_range)
        return flags, {"flags": flags, "base_rows": base_rows, "data_range": data_range}
    flags = step("checks", do_checks)
    sig["n_flags"] = len(flags)
    out = dict(answer_rows=[list(r) for r in res.rows], columns=res.columns, truncated=res.truncated,
               sql=run["winner_sql"], candidates=cand_view)

    if mode == "benchmark":
        return result("answered", confidence=confidence.heuristic(sig), signals={**sig, "flags": flags}, **out)

    def do_judge():
        p = deps["decide"](question, ["yes", "no", "ambiguous"],
                           ("Agreed definitions:\n" + "\n".join(rules_res["lines"]) + "\n" if rules_res["lines"] else "")
                           + f"SQL: {run['winner_sql']}\nFirst rows: {res.rows[:5]}\nDoes this result correctly answer the question?")
        return p, {"probs": p}
    sig["judge_yes"] = step("judge", do_judge)["yes"]
    loaded = confidence.load()
    conf = confidence.predict(loaded[0], sig) if loaded else confidence.heuristic(sig)
    thr = loaded[1] if loaded else 0.5
    vetoed = confidence.veto(sig)
    ok = step("decide", lambda: (conf >= thr and not vetoed, {"confidence": conf, "threshold": thr, "calibrated": bool(loaded), "veto": vetoed}))
    signals = {**sig, "flags": flags}
    if ok:
        return result("answered", confidence=conf, threshold=thr, signals=signals, **out)
    out.update(answer_rows=[], columns=[])
    reason = ("I can't answer this: the data does not seem to contain what this question needs, and the double-check agreed."
              if vetoed else "I'm not confident enough in this result to give it to you. "
              + (f"Sanity checks flagged: {', '.join(flags)}." if flags else "The attempts disagreed or the double-check was unsure."))
    return result("refused", confidence=conf, threshold=thr, signals=signals, reason=reason, **out)
