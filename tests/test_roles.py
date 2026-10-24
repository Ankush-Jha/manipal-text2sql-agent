import sqlite3

import pytest

from agent import roles
from agent.executor import GuardError, execute

DB = "california_schools"
pytestmark = pytest.mark.skipif(not (roles.SRC_ROOT / DB).exists(), reason="BIRD data not present")


def _all_text(path):
    c = sqlite3.connect(path)
    out = []
    for (t,) in c.execute("select name from sqlite_master where type='table'").fetchall():
        for row in c.execute(f'select * from "{t}"'):
            out.extend(str(v) for v in row)
    return out


@pytest.mark.parametrize("role", roles.role_names(DB))
def test_canary_role_db_contains_no_marker(role):
    p = roles.build(DB, role, canary=True)
    cells = _all_text(p)
    assert cells and not any("CANARY" in v or v == str(roles.OOS_NUMBER) for v in cells)


def test_county_analyst_rows_and_columns():
    p = roles.build(DB, "county_analyst")
    assert execute(p, "select distinct County from schools").rows == [("Alameda",)]
    with pytest.raises(Exception):
        execute(p, "select AdmEmail1 from schools")
    with pytest.raises(GuardError):
        execute(p, "select name from sqlite_master")


def test_canary_source_has_markers_for_forbidden_cells():
    roles.build(DB, "county_analyst", canary=True)
    src = roles.CANARY_ROOT / "california_schools__county_analyst/source_with_canaries.sqlite"
    assert execute(src, "select AdmEmail1 from schools limit 1").rows[0][0].startswith("CANARY_")


def test_stale_policy_is_quarantined(monkeypatch):
    bad = {"roles": {"r": {"tables": {"schools": {"except": ["NoSuchColumn"]}}}}}
    monkeypatch.setattr(roles, "load", lambda db_id: bad)
    with pytest.raises(roles.PolicyInvalid):
        roles.build(DB, "r")
