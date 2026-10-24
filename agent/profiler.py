"""Per-column profile of a SQLite DB -> cache/profile_<db>.json.
Stores type, null rate, distinct count, top values, dirty tokens, and the BIRD description CSV text."""
import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRTY = {"", "n/a", "na", "none", "null", "-", "--", "unknown", "?", "nan"}
DATE_FORMATS = {
    "iso": re.compile(r"^\d{4}-\d{2}-\d{2}"),
    "slash": re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),
    "text": re.compile(r"^[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}$"),
    "yyyymm": re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$"),
}


def read_descriptions(db_dir: Path) -> dict[tuple[str, str], dict]:
    """{(table, original_column_name_lower): {name, description, values}} from database_description/*.csv"""
    out = {}
    for f in (db_dir / "database_description").glob("*.csv"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                text = f.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        for r in csv.DictReader(text.splitlines()):
            col = (r.get("original_column_name") or "").strip()
            if not col:
                continue
            out[(f.stem.lower(), col.lower())] = {
                "name": (r.get("column_name") or "").strip(),
                "description": (r.get("column_description") or "").strip(),
                "values": (r.get("value_description") or "").strip(),
            }
    return out


def profile_column(conn, table: str, col: str, ctype: str) -> dict:
    q = f'"{table}"'
    c = f'"{col}"'
    total, nulls, distinct, lo, hi = conn.execute(
        f"SELECT COUNT(*), SUM({c} IS NULL), COUNT(DISTINCT {c}), MIN({c}), MAX({c}) FROM {q}").fetchone()
    top = conn.execute(
        f"SELECT {c}, COUNT(*) n FROM {q} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY n DESC LIMIT 20").fetchall()
    dirty = sorted({str(v) for v, _ in top if isinstance(v, str) and v.strip().lower() in DIRTY})
    fmts = set()
    if "CHAR" in ctype.upper() or "TEXT" in ctype.upper() or "DATE" in ctype.upper():
        for (v,) in conn.execute(f"SELECT {c} FROM {q} WHERE {c} IS NOT NULL LIMIT 200"):
            for name, rx in DATE_FORMATS.items():
                if isinstance(v, str) and rx.match(v):
                    fmts.add(name)
    return {
        "type": ctype, "rows": total, "null_rate": round((nulls or 0) / total, 4) if total else 0,
        "distinct": distinct, "top_values": [[v, n] for v, n in top],
        "dirty_tokens": dirty, "date_formats": sorted(fmts),
        "mixed_date_formats": len(fmts) > 1, "min": lo, "max": hi,
    }


def profile_db(db_id: str, db_root: Path | None = None, force: bool = False) -> dict:
    db_root = db_root or ROOT / "data/dev_databases"
    cache = ROOT / f"cache/profile_{db_id}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    db_dir = db_root / db_id
    desc = read_descriptions(db_dir)
    conn = sqlite3.connect(f"file:{db_dir / (db_id + '.sqlite')}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    prof = {"db_id": db_id, "tables": {}}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        cols = {}
        for _, col, ctype, *_ in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            p = profile_column(conn, table, col, ctype or "")
            p["description"] = desc.get((table.lower(), col.lower()), {})
            cols[col] = p
        prof["tables"][table] = cols
    conn.close()
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(prof, indent=1, default=str))
    return prof


if __name__ == "__main__":
    import sys
    import time
    t = time.time()
    for d in sorted(p.name for p in (ROOT / "data/dev_databases").iterdir() if p.is_dir()):
        profile_db(d, force="--force" in sys.argv)
        print(f"{d} profiled ({time.time() - t:.0f}s)", flush=True)
