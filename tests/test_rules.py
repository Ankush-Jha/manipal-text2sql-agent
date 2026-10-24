from agent import dates, rules
from agent.agent import ask
from agent.profiler import profile_db
from tests.test_agent import deps

REG = rules.load("california_schools", profile_db("california_schools"))
REF = {"reference_date": "2026-10-24", "fiscal_year_start_month": 4, "week_start": "monday"}


def rw(quantity, rewritten=None):
    """Fake judge rewrite: fixed (rewritten question, quantity)."""
    return lambda q: (rewritten or q, quantity)


def test_vague_quantity_asks_with_only_data_supported_options():
    r = rules.resolve("what is studeeents avg?", REG, rw("average", "What is the students' average?"))
    ids = [o["id"] for o in r["clarify"]["options"]]
    assert "sat_math_avg" in ids and "frpm_rate" in ids and not r["applied"]
    assert "graduation_rate" not in ids  # draft rule on a column the database does not have


def test_business_term_asks_among_its_rules():
    r = rules.resolve("What was the average student performance?", REG, rw("student performance"))
    assert {o["id"] for o in r["clarify"]["options"]} == {"sat_math_avg", "sat_reading_avg", "sat_writing_avg", "sat_1500_rate"}


def test_follow_up_answers_narrow_then_apply():
    r1 = rules.resolve("what is students avg? (I mean: subject wise)", REG, rw("average score by subject"), rounds=1)
    assert {o["id"] for o in r1["clarify"]["options"]} == {"sat_math_avg", "sat_reading_avg", "sat_writing_avg"}
    r2 = rules.resolve("what is students avg? (I mean: subject wise; math)", REG, rw("average math score"), rounds=2)
    assert r2["clarify"] is None and r2["applied"][0]["id"] == "sat_math_avg"


def test_most_keyword_hits_wins():
    r = rules.resolve("how did students do on the SAT writing test?", REG, rw("NONE"))
    assert r["applied"][0]["id"] == "sat_writing_avg" and "AVG(satscores.AvgScrWrite)" in r["lines"][0]


def test_stops_asking_after_max_rounds():
    r = rules.resolve("students avg? (I mean: no idea; dunno; whatever)", REG, rw("average"), rounds=3)
    assert r["clarify"] is None


def test_choice_skips_the_model():
    r = rules.resolve("What was the average student performance?", REG, None, choice="sat_1500_rate")
    assert r["clarify"] is None and r["applied"][0]["id"] == "sat_1500_rate"


def test_specific_question_passes_through():
    r = rules.resolve("How many schools are exclusively virtual?", REG, rw("schools"))
    assert r["applied"] == [] and r["clarify"] is None and r["lines"] == []


def test_spelling_fix_reaches_the_writer():
    r = rules.resolve("how many studnets in alameda?", REG, rw("students", "How many students are in Alameda?"))
    assert any("spelling fixed" in l for l in r["lines"])


def test_date_windows_half_open():
    w = {x["phrase"]: (x["start"], x["end"]) for x in dates.windows("orders in the last 30 days vs last calendar month", REF)}
    assert w["last 30 days"] == ("2026-09-24", "2026-10-24")
    assert w["last calendar month"] == ("2026-09-01", "2026-10-01")


def test_fiscal_year_and_last_year_do_not_collide():
    w = {x["phrase"]: (x["start"], x["end"]) for x in dates.windows("revenue last fiscal year and last year", REF)}
    assert w["last fiscal year"] == ("2025-04-01", "2026-04-01")
    assert w["last year"] == ("2025-01-01", "2026-01-01")


def test_reference_date_from_data():
    ref, source = dates.reference(REG["conventions"], profile_db("california_schools"))
    assert ref.isoformat() == "2017-09-22" and "OpenDate" in source


def rule_deps(quantity="average"):
    d = deps()
    d["rewrite"] = rw(quantity)
    return d


def test_agent_clarifies_in_product_mode_only():
    r = ask("What was the average student performance?", "california_schools", deps=rule_deps("student performance"))
    assert r["status"] == "needs_clarification" and r["choices"][0]["id"] and r["clarify_round"] == 1
    b = ask("What was the average student performance?", "california_schools", mode="benchmark", deps=rule_deps())
    assert b["status"] == "answered" and "rules" not in [t["step"] for t in b["trace"]]


def test_agent_applies_choice_and_adds_rule_tables():
    seen = {}
    d = rule_deps()
    sample = d["sample"]
    d["sample"] = lambda p, n, t: (seen.setdefault("prompt", p), sample(p, n, t))[1]
    r = ask("What was the average student performance?", "california_schools", deps=d, choice="sat_math_avg")
    assert r["status"] == "answered" and "AvgScrMath" in seen["prompt"] and "CREATE TABLE satscores" in seen["prompt"]


def test_agent_second_round_narrows():
    r = ask("students avg? (I mean: subject wise)", "california_schools", deps=rule_deps("average by subject"), rounds=1)
    assert r["status"] == "needs_clarification" and len(r["choices"]) == 3 and "still matches" in r["reason"]
