from eval.risk_coverage import outcome, trustsql_score, summarize
from eval.unanswerable import needed_columns

def test_outcomes():
    assert outcome(True, "answered", True) == "correct"
    assert outcome(True, "answered", False) == "wrong"
    assert outcome(True, "refused", False) == "refused_answerable"
    assert outcome(False, "answered", True) == "answered_unanswerable"
    assert outcome(False, "needs_clarification", False) == "refused_unanswerable"

def test_score_penalises_wrong_answers():
    o = ["correct", "wrong", "refused_unanswerable", "answered_unanswerable"]
    assert trustsql_score(o, 1) == 0.0 and trustsql_score(o, 10) < trustsql_score(o, 1)

def test_summary_has_naive_baseline():
    s = summarize(["correct", "wrong"]); assert s["naive_refuse_all"] == 0.0 and s["n"] == 2

def test_needed_columns_skips_keys():
    schema = {"schools": {"cdscode", "county", "virtual"}}
    assert needed_columns("SELECT county FROM schools WHERE virtual = 'F'", schema) == [("schools", "county"), ("schools", "virtual")]
