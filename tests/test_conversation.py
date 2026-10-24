from agent import conversation
from agent.agent import ask

HIST = [{"standalone": "How many schools are in Alameda county?", "sql": "SELECT COUNT(*) FROM schools WHERE County = 'Alameda'"}]


def test_rewrite_falls_back_when_model_repeats_previous_question():
    out = conversation.rewrite("now only charter", HIST, lambda p: {"depends": True, "standalone": "how many schools are in alameda county?", "drop": []})
    assert out == {"depends": False, "standalone": "now only charter", "drop": []}


def test_rewrite_ok_and_prompt_is_grounded_in_sql():
    seen = []
    out = conversation.rewrite("now only charter", HIST, lambda p: seen.append(p) or {"depends": True, "standalone": "How many charter schools are in Alameda county?", "drop": ["County "]})
    assert out["depends"] and "alameda" in seen[0] and out["drop"] == ["county "]


def test_kept_constraints_respects_drop():
    prev = "SELECT * FROM t WHERE x.Power > 5 AND SetCode = '10E'"
    assert conversation.kept_constraints(prev, []) == {"power > 5", "setcode = '10e'"}
    assert conversation.kept_constraints(prev, ["setcode"]) == {"power > 5"}


def test_pick_prefers_group_that_kept_filters():
    reps = [("SELECT COUNT(*) FROM schools WHERE Charter = 1", None), ("SELECT COUNT(*) FROM schools WHERE County = 'Alameda' AND Charter = 1", None)]
    assert conversation.pick(reps, {"county = 'alameda'"}) == 1


def test_ask_uses_standalone_question_and_reports_it():
    seen = {}
    deps = {"sample": lambda prompt, n, temp, on_each=None: seen.setdefault("p", prompt) and
            ["SELECT COUNT(*) FROM schools WHERE Charter = 1"] * 2 + ["SELECT COUNT(*) FROM schools WHERE Charter = 1 AND County = 'Alameda'"] * 3,
            "decide": lambda *a, **k: {}, "rewrite": None,
            "chat_json": lambda p: {"depends": True, "standalone": "How many charter schools are in Alameda county?", "drop": []}}
    r = ask("now only the charter ones", "california_schools", "benchmark", 5, deps=deps, history=HIST)
    assert r["interpreted_as"] == "How many charter schools are in Alameda county?"
    assert "charter schools are in Alameda county" in seen["p"]
    assert "county = 'alameda'" in r["sql"].lower()  # 2-vote group lost the carry check to the 3-vote group that kept the filter
