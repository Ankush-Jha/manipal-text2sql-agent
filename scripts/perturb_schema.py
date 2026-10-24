"""Make schema-drifted copies of a database and record, for every old table, a SELECT over the new schema that returns
the old table (old names, old columns). That one mapping rewrites gold SQL, builds compatibility views, and scores repair.
Usage: python -m scripts.perturb_schema <db_id> <kind>   kind: t_ren | c_abbr | t_vsplit | t_hsplit | combo"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/perturbed"
KINDS = ["t_ren", "c_abbr", "t_vsplit", "t_hsplit", "combo"]
q = lambda n: '"' + n.replace('"', '""') + '"'


def abbreviate(name: str, taken: set[str]) -> str:
    toks = re.findall(r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])|\d+", name) or [name]
    a = "_".join(t[:3] for t in toks)[:24]
    out, i = a, 1
    while out.lower() in taken or out == name:
        i += 1
        out = f"{a}{i}"
    return out


class State:
    """Per old table: where each old column lives now, and how to rebuild the old table."""
    def __init__(self, conn):
        self.conn = conn
        self.cols = {}   # old table -> {old col: (current table, current col)}
        self.src = {}    # old table -> ("one", t) | ("join", a, b, key_a, key_b) | ("union", [t...])
        for (t,) in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
            self.cols[t] = {r[1]: (t, r[1]) for r in conn.execute(f"pragma table_info({q(t)})")}
            self.src[t] = ("one", t)

    def retarget(self, old_t, new_t, which=None):
        for oc, (t, c) in self.cols[old_t].items():
            if which is None or t == which:
                self.cols[old_t][oc] = (new_t, c)

    def sql(self, old_t):
        s, cols = self.src[old_t], self.cols[old_t]
        sel = ", ".join(f"{q(t)}.{q(c)} AS {q(oc)}" if s[0] != "union" else f"{q(c)} AS {q(oc)}" for oc, (t, c) in cols.items())
        if s[0] == "one":
            return f"SELECT {sel} FROM {q(s[1])}"
        if s[0] == "join":
            return f"SELECT {sel} FROM {q(s[1])} JOIN {q(s[2])} ON {q(s[1])}.{q(s[3])} = {q(s[2])}.{q(s[4])}"
        return f"SELECT {sel} FROM (" + " UNION ALL ".join(f"SELECT * FROM {q(t)}" for t in s[1]) + ")"


def rename_tables(st):
    conn = st.conn
    for old in list(st.cols):
        new = f"{old}_data"
        conn.execute(f"alter table {q(old)} rename to {q(new)}")
        st.retarget(old, new)
        st.src[old] = ("one", new)


def abbreviate_columns(st):
    conn = st.conn
    for old in st.cols:
        t = st.src[old][1]
        taken = {c.lower() for _, c in st.cols[old].values()}
        for oc, (tt, c) in list(st.cols[old].items()):
            new = abbreviate(c, taken)
            conn.execute(f"alter table {q(t)} rename column {q(c)} to {q(new)}")
            taken.add(new.lower())
            st.cols[old][oc] = (tt, new)


def vertical_split(st, old):
    conn = st.conn
    t = st.src[old][1]
    info = conn.execute(f"pragma table_info({q(t)})").fetchall()
    key = info[0][1]
    n, d = conn.execute(f"select count(*), count(distinct {q(key)}) from {q(t)}").fetchone()
    if n != d or len(info) < 6:
        return False
    half = len(info) // 2
    a, b = f"{t}_core", f"{t}_ext"
    for name, cols in ((a, info[:half]), (b, [info[0]] + info[half:])):
        conn.execute(f"create table {q(name)} ({', '.join(q(c[1]) + ' ' + (c[2] or '') for c in cols)})")
        conn.execute(f"insert into {q(name)} select {', '.join(q(c[1]) for c in cols)} from {q(t)}")
    conn.execute(f"drop table {q(t)}")
    for oc, (tt, c) in list(st.cols[old].items()):
        st.cols[old][oc] = (a if c in [x[1] for x in info[:half]] else b, c)
    st.src[old] = ("join", a, b, key, key)
    return True


def horizontal_split(st, old):
    conn = st.conn
    t = st.src[old][1]
    for _, c, ty, *_ in conn.execute(f"pragma table_info({q(t)})").fetchall():
        vals = [v for (v,) in conn.execute(f"select distinct {q(c)} from {q(t)} where {q(c)} is not null limit 8")]
        if 2 <= len(vals) <= 6 and all(isinstance(v, str) for v in vals) and conn.execute(f"select count(*) from {q(t)} where {q(c)} is null").fetchone()[0] == 0:
            names = []
            for v in vals:
                nm = f"{t}_{re.sub(r'[^A-Za-z0-9]+', '_', v).strip('_')}"
                conn.execute(f"create table {q(nm)} as select * from {q(t)} where {q(c)} = ?", (v,))
                names.append(nm)
            conn.execute(f"drop table {q(t)}")
            for oc in st.cols[old]:
                st.cols[old][oc] = (names[0], st.cols[old][oc][1])
            st.src[old] = ("union", names)
            return True
    return False


def perturb(db_id: str, kind: str, src_root: Path = ROOT / "data/dev_databases") -> dict:
    out_dir = OUT / kind / db_id
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    dst = out_dir / f"{db_id}.sqlite"
    shutil.copyfile(src_root / db_id / f"{db_id}.sqlite", dst)
    if (src_root / db_id / "database_description").exists():
        shutil.copytree(src_root / db_id / "database_description", out_dir / "database_description")
    conn = sqlite3.connect(dst)
    st = State(conn)
    if kind in ("t_ren", "combo"):
        rename_tables(st)
    if kind in ("c_abbr", "combo"):
        abbreviate_columns(st)
    done = []
    if kind in ("t_vsplit", "combo"):
        done = [o for o in st.cols if vertical_split(st, o)]
    if kind == "t_hsplit":
        for o in sorted(st.cols, key=lambda t: -len(st.cols[t])):
            if horizontal_split(st, o):
                done = [o]
                break
    conn.commit()
    conn.execute("vacuum")
    conn.close()
    mapping = {"db_id": db_id, "kind": kind, "tables": {o: {"sql": st.sql(o), "now": sorted({t for t, _ in st.cols[o].values()}),
               "changed": st.src[o] != ("one", o) or any(c != oc or t != o for oc, (t, c) in st.cols[o].items())} for o in st.cols},
               "columns": {o: {oc: list(v) for oc, v in cols.items()} for o, cols in st.cols.items()}}
    (out_dir / "mapping.json").write_text(json.dumps(mapping, indent=1))
    return mapping


if __name__ == "__main__":
    m = perturb(sys.argv[1], sys.argv[2])
    print({o: v["now"] for o, v in m["tables"].items() if v["changed"]})
