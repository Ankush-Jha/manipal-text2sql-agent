from fastapi.testclient import TestClient

from api.server import app

c = TestClient(app)


def test_health_shape():
    assert set(c.get("/api/health").json()) == {"writer", "judge", "logprobs"}


def test_databases_lists_11():
    dbs = c.get("/api/databases").json()
    assert len(dbs) == 11 and all(d["profile"] == "ready" for d in dbs)


def test_examples():
    assert len(c.get("/api/examples?db=california_schools").json()) == 7

def test_rules_registry():
    r = c.get("/api/rules?db=california_schools").json()
    by = {x["id"]: x for x in r["rules"]}
    assert by["sat_math_avg"]["available"] and not by["graduation_rate"]["available"]


def test_profile():
    p = c.get("/api/profile?db=california_schools").json()
    assert {t["name"] for t in p["tables"]} == {"frpm", "satscores", "schools"}


def test_results_always_200():
    r = c.get("/api/results")
    assert r.status_code == 200 and "accuracy" in r.json()


def test_ask_unknown_db():
    assert c.post("/api/ask", json={"question": "x", "db": "nope"}).status_code == 404


def test_index_served():
    assert c.get("/").status_code == 200
