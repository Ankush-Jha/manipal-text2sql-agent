import sqlite3
import pytest
from agent.literals import repair_literals, column_values

PROFILE = {"tables": {"colour": {"id": {"type": "INTEGER"}, "colour": {"type": "TEXT"}},
                      "ev": {"id": {"type": "INTEGER"}, "date": {"type": "TEXT"}, "rating": {"type": "INTEGER"}}}}

@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.sqlite"; c = sqlite3.connect(p)
    c.execute("CREATE TABLE colour (id INTEGER, colour TEXT)"); c.execute("CREATE TABLE ev (id INTEGER, date TEXT, rating INTEGER)")
    c.executemany("INSERT INTO colour VALUES (?,?)", [(1, "Blond"), (2, "Blue"), (3, "Black"), (4, "Brown")])
    c.executemany("INSERT INTO ev VALUES (?,?,?)", [(1, "2016-06-23 00:00:00", 77), (2, "2016-06-24 00:00:00", 80)])
    c.commit(); c.close(); column_values.cache_clear(); return str(p)

def fix(db, sql): return repair_literals(sql, db, PROFILE)

def test_close_spelling_is_snapped(db):
    new, f = fix(db, "SELECT id FROM colour WHERE colour = 'Blonde'")
    assert "'Blond'" in new and f[0]["kind"] == "snap"

def test_case_difference_is_snapped(db):
    assert "'Blue'" in fix(db, "SELECT id FROM colour WHERE colour = 'blue'")[0]

def test_stored_value_is_never_touched(db):
    sql = "SELECT id FROM colour WHERE colour = 'Blue'"
    assert fix(db, sql) == (sql, [])

def test_not_equal_and_like_are_never_touched(db):
    for sql in ("SELECT id FROM colour WHERE colour != 'Blonde'", "SELECT id FROM colour WHERE colour LIKE 'Blonde%'",
                "SELECT id FROM colour WHERE colour NOT IN ('Blonde')"):
        assert fix(db, sql)[0] == sql

def test_in_list_is_repaired_per_item(db):
    new, f = fix(db, "SELECT id FROM colour WHERE colour IN ('blue', 'Blonde')")
    assert "'Blue'" in new and "'Blond'" in new and len(f) == 2

def test_date_written_with_slashes_matches_timestamps(db):
    new, f = fix(db, "SELECT id FROM ev WHERE date = '2016/6/23'")
    assert "SUBSTR(date, 1, 10) = '2016-06-23'" in new
    c = sqlite3.connect(db); assert c.execute(new).fetchall() == [(1,)]

def test_unrelated_value_is_flagged_not_changed(db):
    sql = "SELECT id FROM colour WHERE colour = 'Purple'"
    new, f = fix(db, sql)
    assert new == sql and f[0]["kind"] == "unknown"

def test_ambiguous_close_match_does_nothing(db):
    c = sqlite3.connect(db); c.execute("INSERT INTO colour VALUES (5, 'Greenisha')"); c.execute("INSERT INTO colour VALUES (6, 'Greenishb')"); c.commit(); c.close(); column_values.cache_clear()
    sql = "SELECT id FROM colour WHERE colour = 'Greenish'"
    new, f = fix(db, sql)
    assert new == sql and f[0]["kind"] == "unknown"  # two equally close spellings: do not guess

def test_negated_conditions_are_never_touched(db):
    for sql in ("SELECT id FROM colour WHERE NOT (colour = 'Blonde')", "SELECT id FROM colour WHERE NOT colour IN ('blue')"):
        assert fix(db, sql) == (sql, [])

def test_numbers_and_bad_sql_are_safe(db):
    assert fix(db, "SELECT id FROM ev WHERE rating = 77") == ("SELECT id FROM ev WHERE rating = 77", [])
    assert fix(db, "this is not sql") == ("this is not sql", [])
    assert fix(db, "") == ("", [])
