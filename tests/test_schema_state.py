import sqlite3

from agent import linker
from agent.profiler import ROOT, profile_db
from agent.schema_state import schema_hash, snapshot


def _mk(root, db_id):
    d = root / db_id
    d.mkdir(parents=True)
    c = sqlite3.connect(d / f"{db_id}.sqlite")
    c.executescript("create table people (id integer, city text); insert into people values (1,'Pune'),(2,'Agra');")
    c.commit()
    c.close()
    return d / f"{db_id}.sqlite"


def test_ddl_change_invalidates_profile_and_value_index(tmp_path):
    db_id = "zz_schema_state_tmp"
    sq = _mk(tmp_path, db_id)
    made = []
    try:
        h1 = schema_hash(sq)
        assert "city" in profile_db(db_id, tmp_path)["tables"]["people"]
        assert "pune" in linker.value_index(db_id, tmp_path)
        c = sqlite3.connect(sq)
        c.execute("alter table people rename column city to town")
        c.commit()
        c.close()
        assert schema_hash(sq) != h1
        assert snapshot(sq)["people"] == ["id", "town"]
        assert "town" in profile_db(db_id, tmp_path)["tables"]["people"]
        assert "pune" in linker.value_index(db_id, tmp_path) and all(col == "town" for _, col, _ in linker.value_index(db_id, tmp_path)["pune"])
    finally:
        for f in (ROOT / "cache").glob(f"profile_{db_id}_*.json"):
            f.unlink()
