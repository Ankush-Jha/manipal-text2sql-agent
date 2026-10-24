import pytest
from agent.agent import ask

GOOD = "SELECT COUNT(*) FROM schools"
def deps(triage=None, judge_yes=0.9, sqls=None):
    triage = triage or {"answerable": 0.9, "ambiguous": 0.05, "data_missing": 0.03, "not_sql": 0.02}
    def decide(q, opts, ctx="", desc=None):
        if opts[0] == "answerable": return triage
        return {"yes": judge_yes, "no": 1 - judge_yes, "ambiguous": 0.0}
    return {"sample": lambda p, n, t: (sqls or [GOOD] * n)[:n] if (sqls or n) else [], "decide": decide}

def test_answers_with_agreement():
    r = ask("How many schools are there?", "california_schools", deps=deps(), n_samples=5)
    assert r["status"] == "answered" and r["sql"] == GOOD and r["answer_rows"][0][0] > 0
    assert [t["step"] for t in r["trace"]][:2] == ["link", "triage"] or r["trace"][0]["step"] == "link"

def test_refuses_missing_data(monkeypatch):
    monkeypatch.setattr("agent.agent.REFUSE_P", 0.85)
    r = ask("What is teacher satisfaction?", "california_schools",
            deps=deps({"answerable": .1, "ambiguous": .1, "data_missing": .9, "not_sql": .05}))
    assert r["status"] == "refused" and "can't answer" in r["reason"]

def test_ambiguous_clarifies(monkeypatch):
    monkeypatch.setattr("agent.agent.REFUSE_P", 0.85)
    r = ask("best schools", "california_schools", deps=deps({"answerable": .1, "ambiguous": .9, "data_missing": .03, "not_sql": .02}))
    assert r["status"] == "needs_clarification"

def test_low_confidence_refused_in_product_mode():
    r = ask("How many schools?", "california_schools", deps=deps(judge_yes=0.0,
            sqls=[GOOD, "SELECT COUNT(*) FROM frpm", "SELECT 1", "SELECT 2", "SELECT 3"]))
    assert r["status"] == "refused" and r["sql"]

def test_triage_and_judge_together_veto_agreeing_attempts():
    r = ask("How many students are happy?", "california_schools",
            deps=deps({"answerable": 0.0, "ambiguous": 0.0, "data_missing": 1.0, "not_sql": 0.0}, judge_yes=0.0))
    assert r["status"] == "refused" and "does not seem to contain" in r["reason"]

def test_triage_alone_does_not_refuse():
    r = ask("How many schools are there?", "california_schools",
            deps=deps({"answerable": 0.05, "ambiguous": 0.05, "data_missing": 0.9, "not_sql": 0.0}, judge_yes=0.9))
    assert r["status"] == "answered"

def test_benchmark_always_answers():
    r = ask("How many schools?", "california_schools", mode="benchmark",
            deps=deps(sqls=[GOOD, "SELECT COUNT(*) FROM frpm", "SELECT 1", "SELECT 2", "SELECT 3"]))
    assert r["status"] == "answered"

def test_blocked_sql_never_executes():
    r = ask("drop it", "california_schools", mode="benchmark", deps=deps(sqls=["DROP TABLE schools"] * 5))
    assert r["status"] == "refused" and r["answer_rows"] == []
