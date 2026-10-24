import sqlite3

import pytest

from agent import guard
from agent.executor import GuardError, execute


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.sqlite"
    c = sqlite3.connect(p)
    c.executescript("""
        create table schools (id integer, name text, county text, email text);
        insert into schools values (1,'A','Alameda','a@x.org'),(2,'B','Fresno','b@x.org');
        create table frpm (id integer, enroll integer);
        insert into frpm values (1,100),(2,200);
    """)
    c.commit()
    c.close()
    return p


POLICY = guard.Policy(
    tables={"schools": {"id": "public", "name": "public", "county": "public"}, "frpm": {"id": "public", "enroll": "aggregate_only"}},
    full_schema={"schools": ["id", "name", "county", "email"], "frpm": ["id", "enroll"]},
)

# every shape must be refused: the hidden column / table never reaches the caller
BYPASSES = [
    "select email from schools",
    "select s.email from schools s",
    "select * from schools",
    "select x.email from (select * from schools) x",
    "with t as (select email from schools) select * from t",
    "select name from schools union select email from schools",
    "select (select email from schools limit 1)",
    "select name from schools where email like 'a%'",
    "select name from schools order by email",
    "select group_concat(email) from schools",
    "select name from sqlite_master",
    "select sql from sqlite_master",
    "select enroll from frpm",
    "attach database '/tmp/x.db' as x",
    "pragma table_info(schools)",
    "select load_extension('x')",
    "delete from schools",
]


@pytest.mark.parametrize("sql", BYPASSES)
def test_bypass_denied(db, sql):
    with pytest.raises(GuardError):
        execute(db, sql, policy=POLICY)


def test_allowed_queries(db):
    assert execute(db, "select name from schools where county = 'Alameda'", policy=POLICY).rows == [("A",)]
    assert execute(db, "select count(*) from schools", policy=POLICY).rows == [(2,)]
    assert execute(db, "select sum(enroll) from frpm", policy=POLICY).rows == [(300,)]
    assert execute(db, "with t as (select name from schools) select * from t", policy=POLICY).rows == [("A",), ("B",)]


def test_authorizer_alone_blocks_columns_and_logs(db):
    # AST check skipped on purpose: the authorizer must catch what the parser misses
    audit = []
    import sqlite3 as s
    conn = s.connect(f"file:{db}?mode=ro", uri=True)
    conn.set_authorizer(guard.make_authorizer(audit, guard.allowed_map(POLICY)))
    with pytest.raises(s.DatabaseError):
        conn.execute("select name from (select * from schools) where email is not null").fetchall()
    assert any(not d["allowed"] and d["a2"] == "email" for d in audit)


def test_authorizer_denies_without_policy(db):
    for sql in ("select name from sqlite_master", "select load_extension('x')"):
        with pytest.raises(GuardError):
            execute(db, sql)


def test_constraints_and_diff():
    assert guard.constraints("select a from t where x.y = 1 and z > 2") == {"y = 1", "z > 2"}
    d = guard.diff("select a from t where y = 1", "select a from t where y = 1 and z > 2")
    assert d["constraints_only_b"] == ["z > 2"] and not d["constraints_only_a"]
