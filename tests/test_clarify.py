from agent import clarify
from agent.agent import ask
from agent.executor import ExecResult


def _run(groups):
    return {"groups": [{"size": n, "rows": len(r.rows)} for _, r, n in groups], "reps": [(s, r) for s, r, _ in groups]}


R1, R2 = ExecResult(["n"], [(10,)]), ExecResult(["n"], [(7,)])
A, B = "SELECT COUNT(*) FROM schools", "SELECT COUNT(*) FROM schools WHERE Charter = 1"
yes = lambda q, o, c="": {"yes": 0.9, "no": 0.1}
no = lambda q, o, c="": {"yes": 0.1, "no": 0.9}


def test_asks_when_two_strong_groups_differ_and_judge_agrees():
    g = clarify.gate(_run([(A, R1, 3), (B, R2, 2)]), "how many schools", yes)
    assert [o["votes"] for o in g["options"]] == [3, 2] and "charter = 1" in g["options"][1]["label"]


def test_no_ask_when_one_group_dominates_or_judge_disagrees():
    assert clarify.gate(_run([(A, R1, 4), (B, R2, 1)]), "q", yes) is None
    assert clarify.gate(_run([(A, R1, 3), (B, R2, 2)]), "q", no) is None


def test_no_ask_when_readings_differ_only_in_order():
    assert clarify.gate(_run([("SELECT a FROM t ORDER BY a", R1, 3), ("SELECT a FROM t ORDER BY a DESC", R2, 2)]), "q", yes) is None


def test_ask_returns_interpretations_once():
    deps = {"sample": lambda p, n, t, on_each=None: [A] * 3 + [B] * 2, "decide": lambda q, o, c="", d=None: {x: 1 / len(o) for x in o} if "yes" not in o else {"yes": 0.9, "no": 0.1},
            "rewrite": lambda q: (q, "school names")}
    r = ask("list the school names in Alameda county", "california_schools", "product", 5, deps=deps)
    assert r["status"] == "needs_clarification" and len(r["interpretations"]) == 2
    again = ask("list the school names in Alameda county (I mean the ones returning names only)", "california_schools", "product", 5, deps=deps, rounds=1, choice="enrollment_k12")
    assert again["status"] != "needs_clarification"
