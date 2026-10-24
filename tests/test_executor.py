import sqlite3

import pytest

from agent.executor import GuardError, execute


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.sqlite"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE t (a INTEGER)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(2000)])
    c.commit()
    c.close()
    return p


def test_select_ok(db):
    assert execute(db, "SELECT COUNT(*) FROM t").rows == [(2000,)]


def test_with_ok(db):
    assert execute(db, "WITH x AS (SELECT a FROM t) SELECT COUNT(*) FROM x").rows == [(2000,)]


@pytest.mark.parametrize("sql", [
    "DROP TABLE t", "INSERT INTO t VALUES (1)", "DELETE FROM t",
    "SELECT 1; DROP TABLE t", "PRAGMA writable_schema=1",
])
def test_refused(db, sql):
    with pytest.raises(GuardError):
        execute(db, sql)


def test_row_cap(db):
    r = execute(db, "SELECT a FROM t", max_rows=1000)
    assert len(r.rows) == 1000 and r.truncated


def test_timeout(db):
    slow = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x < 500000000) "
            "SELECT COUNT(*) FROM c")
    with pytest.raises(GuardError, match="timeout"):
        execute(db, slow, timeout_s=1)


def test_readonly_even_if_guard_bypassed(db):
    import sqlite3 as s
    c = s.connect(f"file:{db}?mode=ro", uri=True)
    with pytest.raises(s.OperationalError):
        c.execute("INSERT INTO t VALUES (1)")


@pytest.mark.parametrize("sql", [
    "SELECT a FROM t EXCEPT SELECT a FROM t WHERE a > 5",
    "SELECT a FROM t INTERSECT SELECT a FROM t WHERE a < 5",
    "SELECT a FROM t UNION ALL SELECT a FROM t",
])
def test_set_operations_allowed(db, sql):
    assert execute(db, sql).rows is not None
