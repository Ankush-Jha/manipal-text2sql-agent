"""Roles as physical databases. A role's database holds only the rows and columns the role may see, so a
forbidden cell cannot be returned by any SQL the model writes. The role is resolved by the server, never from chat text."""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from agent import guard
from agent.schema_state import schema_hash, snapshot

ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = ROOT / "roles"
SRC_ROOT = ROOT / "data/dev_databases"
ROLE_ROOT = ROOT / "data/role_dbs"
CANARY_ROOT = ROOT / "data/role_dbs_canary"
OOS_NUMBER = 987654321


class PolicyInvalid(Exception):
    """The policy names a table or column that no longer exists: the role is quarantined, not silently widened."""


def load(db_id: str) -> dict:
    p = ROLES_DIR / f"{db_id}.json"
    return json.loads(p.read_text()) if p.exists() else {"roles": {}}


def role_names(db_id: str) -> list[str]:
    return list(load(db_id)["roles"])


def role_db_id(db_id: str, role: str) -> str:
    return f"{db_id}__{role}"


def resolve(db_id: str, role: str | None) -> tuple[str, Path]:
    """(db_id to run against, db_root). role None = the unrestricted database."""
    if not role:
        return db_id, SRC_ROOT
    if role not in load(db_id)["roles"]:
        raise KeyError(f"unknown role '{role}'")
    ensure_built(db_id, role)
    return role_db_id(db_id, role), ROLE_ROOT


def allowed_columns(policy: dict, schema: dict[str, list[str]]) -> dict[str, list[str]]:
    """{table: [allowed columns]} for the tables the role has; raises PolicyInvalid on unknown names."""
    out = {}
    live = {t.lower(): (t, cols) for t, cols in schema.items()}
    for tname, spec in policy["tables"].items():
        if tname.lower() not in live:
            raise PolicyInvalid(f"table '{tname}' not in database")
        real, cols = live[tname.lower()]
        names = {c.lower() for c in cols}
        bad = [c for c in spec.get("except", []) + spec.get("only", []) if c.lower() not in names]
        if bad:
            raise PolicyInvalid(f"{tname}: unknown column(s) {bad}")
        keep = [c for c in cols if (not spec.get("only") or c.lower() in {x.lower() for x in spec["only"]})
                and c.lower() not in {x.lower() for x in spec.get("except", [])}]
        out[real] = keep
    return out


def to_guard_policy(db_id: str, role: str, schema: dict[str, list[str]]) -> guard.Policy:
    """Column policy for the full database (the weaker layers of the ablation ladder)."""
    allowed = allowed_columns(load(db_id)["roles"][role], schema)
    return guard.Policy({t: {c: guard.PUBLIC for c in cols} for t, cols in allowed.items()}, full_schema=schema)


def policy_hash(db_id: str, role: str) -> str:
    return hashlib.sha256(json.dumps(load(db_id)["roles"][role], sort_keys=True).encode()).hexdigest()[:12]


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _canary_source(src: Path, dst: Path, db_id: str, role: str) -> None:
    """Copy of the database where everything this role must not see is replaced by recognisable markers."""
    import shutil
    shutil.copyfile(src, dst)
    policy = load(db_id)["roles"][role]
    schema = snapshot(src)
    allowed = allowed_columns(policy, schema)
    conn = sqlite3.connect(dst)
    for table, cols in schema.items():
        spec = policy["tables"].get(table)
        info = {r[1]: r for r in conn.execute(f"pragma table_info({_q(table)})")}
        keep = {c for c, r in info.items() if r[5]} | {c for c in cols if spec and c.lower() in (spec.get("where", "").lower())}
        keep |= {c for c in cols if c.lower() in ("cdscode", "cds")}
        for c in cols:
            if c in keep:
                continue
            numeric = "INT" in (info[c][2] or "").upper() or "REAL" in (info[c][2] or "").upper()
            forbidden_col = spec is None or c not in allowed.get(table, [])
            marker = str(OOS_NUMBER) if numeric else f"'CANARY_{role}_{table}_{c}_' || rowid"
            if forbidden_col:
                conn.execute(f"update {_q(table)} set {_q(c)} = {marker}")
            elif spec and spec.get("where"):
                conn.execute(f"update {_q(table)} set {_q(c)} = {marker} where not ({spec['where']})")
    conn.commit()
    conn.close()


def build(db_id: str, role: str, canary: bool = False) -> Path:
    policy = load(db_id)["roles"][role]
    src = SRC_ROOT / db_id / f"{db_id}.sqlite"
    out_root = CANARY_ROOT if canary else ROLE_ROOT
    rid = role_db_id(db_id, role)
    out_dir = out_root / rid
    out = out_dir / f"{rid}.sqlite"
    out_dir.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    schema = snapshot(src)
    allowed = allowed_columns(policy, schema)  # validates before anything is written
    source = src
    if canary:
        source = out_dir / "source_with_canaries.sqlite"
        _canary_source(src, source, db_id, role)
    conn = sqlite3.connect(out)
    conn.execute("attach database ? as src", (str(source),))
    for table, cols in allowed.items():
        sconn_cols = {r[1]: r for r in conn.execute(f"pragma src.table_info({_q(table)})")}
        defs = [f"{_q(c)} {sconn_cols[c][2] or ''}".strip() + (" primary key" if sconn_cols[c][5] == 1 and sum(r[5] > 0 for r in sconn_cols.values()) == 1 else "") for c in cols]
        pks = [c for c in cols if sconn_cols[c][5] > 0]
        if len(pks) > 1:
            defs.append("primary key (" + ", ".join(_q(c) for c in pks) + ")")
        for fk in conn.execute(f"pragma src.foreign_key_list({_q(table)})").fetchall():
            _, _, ref_t, frm, to, *_ = fk
            if ref_t in allowed and frm in cols and to in allowed[ref_t]:
                defs.append(f"foreign key ({_q(frm)}) references {_q(ref_t)}({_q(to)})")
        conn.execute(f"create table {_q(table)} ({', '.join(defs)})")
    for table, cols in allowed.items():
        where = policy["tables"][table].get("where")
        sel = ", ".join(_q(c) for c in cols)
        # the predicate is policy-author text read from roles/*.json, never user input
        conn.execute(f"insert into main.{_q(table)} select {sel} from src.{_q(table)}" + (f" where {where}" if where else ""))
    conn.commit()
    conn.execute("detach database src")
    conn.close()
    _copy_descriptions(SRC_ROOT / db_id / "database_description", out_dir / "database_description", allowed)
    (out_dir / "meta.json").write_text(json.dumps({"schema_hash": schema_hash(src), "policy_hash": policy_hash(db_id, role), "canary": canary}))
    return out


def _copy_descriptions(src: Path, dst: Path, allowed: dict[str, list[str]]) -> None:
    if not src.exists():
        return
    dst.mkdir(exist_ok=True)
    keep = {t.lower(): {c.lower() for c in cols} for t, cols in allowed.items()}
    for f in src.glob("*.csv"):
        if f.stem.lower() not in keep:
            continue
        for enc in ("utf-8-sig", "latin-1"):
            try:
                text = f.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        rows = list(csv.DictReader(text.splitlines()))
        if not rows:
            continue
        with open(dst / f.name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(r for r in rows if (r.get("original_column_name") or "").strip().lower() in keep[f.stem.lower()])


def ensure_built(db_id: str, role: str) -> Path:
    """Build the role database if it is missing or if the source schema or the policy changed since."""
    rid = role_db_id(db_id, role)
    out = ROLE_ROOT / rid / f"{rid}.sqlite"
    meta = ROLE_ROOT / rid / "meta.json"
    src = SRC_ROOT / db_id / f"{db_id}.sqlite"
    if out.exists() and meta.exists():
        m = json.loads(meta.read_text())
        if m["schema_hash"] == schema_hash(src) and m["policy_hash"] == policy_hash(db_id, role):
            return out
    return build(db_id, role)
