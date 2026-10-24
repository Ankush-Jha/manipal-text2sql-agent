import sqlite3
import pytest
from agent.runner import run_candidates

@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.sqlite"; c = sqlite3.connect(p)
    c.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    c.executemany("INSERT INTO t VALUES (?,?)", [(1,"x"),(2,"y"),(3,"z")]); c.commit(); c.close()
    return p

def test_majority_vote_groups_equal_results(db):
    r = run_candidates(db, ["SELECT a FROM t", "SELECT a FROM t ORDER BY a DESC", "SELECT b FROM t", "SELECT a FROM t WHERE a>0"])
    assert r["n_groups"] == 3 or r["n_groups"] == 2  # ordered result differs from set result
    assert r["groups"][0]["size"] >= 2
    assert r["winner_sql"] in ("SELECT a FROM t", "SELECT a FROM t WHERE a>0")

def test_order_insensitive_without_order_by(db):
    r = run_candidates(db, ["SELECT a FROM t", "SELECT a FROM t WHERE a IN (3,2,1)"])
    assert r["n_groups"] == 1 and r["vote_share"] == 1.0

def test_repair_on_error(db):
    r = run_candidates(db, ["SELECT nope FROM t"], repair=lambda sql, err: "SELECT a FROM t")
    assert r["candidates"][0]["repaired"] and r["winner_sql"] == "SELECT a FROM t"

def test_guard_error_not_repaired(db):
    r = run_candidates(db, ["DROP TABLE t"], repair=lambda s, e: "SELECT 1")
    assert r["winner_sql"] is None and not r["candidates"][0]["repaired"]

def test_none_candidate_is_logged(db):
    r = run_candidates(db, [None, "SELECT a FROM t"])
    assert r["candidates"][0]["error"] == "no_sql" and r["vote_share"] == 0.5


def test_tiebreak_picks_the_group_the_greedy_sample_agrees_with(db):
    sqls = ["SELECT a FROM t", "SELECT a FROM t", "SELECT b FROM t", "SELECT b FROM t", "SELECT 1"]
    plain = run_candidates(db, sqls)
    assert plain["winner_sql"] == "SELECT a FROM t"  # tie: first group wins
    r = run_candidates(db, sqls, tiebreak=lambda: "SELECT b FROM t WHERE 1")
    assert r["winner_sql"] == "SELECT b FROM t" and r["tiebreak"] == {"tied": True, "matched": True, "greedy_sql": "SELECT b FROM t WHERE 1", "default_sql": "SELECT a FROM t"}


def test_tiebreak_never_overrides_a_strict_majority(db):
    calls = []
    r = run_candidates(db, ["SELECT a FROM t"] * 3 + ["SELECT b FROM t"] * 2, tiebreak=lambda: calls.append(1) or "SELECT b FROM t")
    assert r["winner_sql"] == "SELECT a FROM t" and not calls and r["tiebreak"]["tied"] is False


def test_tiebreak_unmatched_keeps_default_order(db):
    sqls = ["SELECT a FROM t", "SELECT a FROM t", "SELECT b FROM t", "SELECT b FROM t", "SELECT 1"]
    r = run_candidates(db, sqls, tiebreak=lambda: "SELECT 42")
    assert r["winner_sql"] == "SELECT a FROM t" and r["tiebreak"]["matched"] is False
