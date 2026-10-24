"""Schema linking: lexical column retrieval + exact stored-value lookup -> pruned schema.
(Embedding retrieval is a planned upgrade; add only if gold-table recall < 90% on calibration.)"""
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from agent.schema_state import schema_hash

ROOT = Path(__file__).resolve().parent.parent
STOP = set("the a an of in on at for to and or is are was were what which who how many much is by with from that this "
           "than then there their list give show name names all each per number total average highest lowest".split())
MAX_DISTINCT = 20000
MAX_TABLES = 5


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower()) if t not in STOP]


def stem(t: str) -> str:
    for suf in ("ing", "es", "s", "ed"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            t = t[: -len(suf)]
            break
    return re.sub(r"(.)\1", r"\1", t)  # enrolment == enrollment


def ngrams(words: list[str], maxn: int = 4):
    for n in range(maxn, 0, -1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i:i + n])


def value_index(db_id: str, db_root=None) -> dict[str, list[tuple[str, str, str]]]:
    root = Path(db_root or ROOT / "data/dev_databases")
    return _value_index(db_id, str(root), schema_hash(root / db_id / f"{db_id}.sqlite"))


@lru_cache(maxsize=None)
def _value_index(db_id: str, root: str, schema_hash: str) -> dict[str, list[tuple[str, str, str]]]:
    """lowercased stored value -> [(table, column, original value)] for text columns with modest cardinality."""
    p = Path(root) / db_id / f"{db_id}.sqlite"
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    idx: dict[str, list] = {}
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for _, c, ty, *_ in conn.execute(f'PRAGMA table_info("{t}")').fetchall():
            if "CHAR" not in (ty or "").upper() and "TEXT" not in (ty or "").upper():
                continue
            n = conn.execute(f'SELECT COUNT(DISTINCT "{c}") FROM "{t}"').fetchone()[0]
            if n > MAX_DISTINCT:
                continue
            for (v,) in conn.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL'):
                if isinstance(v, str) and 2 <= len(v) <= 60:
                    idx.setdefault(v.lower().strip(), []).append((t, c, v))
    conn.close()
    return idx


def _specific(g: str, original: str) -> bool:
    """Value match must look intentional: multi-word, contains a digit, or capitalised in the question."""
    if " " in g or any(ch.isdigit() for ch in g):
        return len(g) >= 4
    m = re.search(re.escape(g), original, re.I)
    if m and m.group(0).isupper() and len(g) >= 3:
        return True
    if re.search(r"[\"'“‘]" + re.escape(g) + r"[\"'”’]", original, re.I):
        return True  # the user quoted it
    return bool(m) and len(g) >= 4 and m.group(0)[0].isupper() and m.start() > 0


def link(question: str, evidence: str, profile: dict, db_id: str, top_cols: int = 14, db_root=None) -> dict:
    """Returns {tables: [...], columns: {table: [cols]}, values: [(table, col, value)], coverage: float}."""
    text = f"{question} {evidence}".strip()
    words = [stem(t) for t in tokens(text)]
    scores: dict[tuple[str, str], float] = {}
    table_words = {stem(t) for table in profile["tables"] for t in tokens(table)}
    for table, cols in profile["tables"].items():
        t_toks = {stem(t) for t in tokens(table)}
        for col, info in cols.items():
            d = info.get("description", {})
            c_toks = {stem(t) for t in tokens(col)} | {stem(t) for t in tokens(d.get("name", ""))}
            d_toks = {stem(t) for t in tokens(d.get("description", ""))}
            hits = c_toks & set(words)
            # a word that names a table ("schools") says little about which column of it is meant
            d_hits = d_toks & set(words)
            s = 2.0 * len(hits - table_words) + 0.3 * len(hits & table_words) \
                + 0.5 * len(d_hits - table_words) + 0.1 * len(d_hits & table_words) + 0.5 * len(t_toks & set(words))
            if s:
                scores[(table, col)] = s
    values = []
    low = text.lower()
    q_words = re.findall(r"[a-z0-9\.\-']+", low)
    idx = value_index(db_id, db_root)
    seen = set()
    for g in ngrams(q_words, 4):
        if g in idx and g not in STOP and g not in seen and _specific(g, text):
            seen.add(g)
            for t, c, v in idx[g][:3]:
                if c not in profile["tables"].get(t, {}):  # profile older than the database: not a column we know
                    continue
                values.append((t, c, v))
                scores[(t, c)] = scores.get((t, c), 0) + 3.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_cols]
    cols: dict[str, list[str]] = {}
    for (t, c), _ in ranked:
        cols.setdefault(t, []).append(c)
    core: dict[str, list[str]] = {}  # strongly matched columns only, used for hints
    for (t, c), sc in ranked:
        if sc >= 1.0:
            core.setdefault(t, []).append(c)
    # keep primary/foreign-key-looking columns of chosen tables so joins stay possible
    for t in list(cols):
        for c in profile["tables"][t]:
            if c.lower().endswith(("id", "code")) and c not in cols[t]:
                cols[t].append(c)
    covered = sum(1 for w in set(words) if any(w in {stem(x) for x in tokens(c)} | {stem(x) for x in tokens(t)}
                                               for t, cs in cols.items() for c in cs)) if words else 1
    # table ranking: total matched score per table, keep the top MAX_TABLES (all tables when the DB is small)
    t_score: dict[str, float] = {}
    for (t, _), sc in scores.items():
        t_score[t] = t_score.get(t, 0) + sc
    keep = [t for t, _ in sorted(t_score.items(), key=lambda kv: -kv[1])][:MAX_TABLES]
    for t in profile["tables"]:
        if len(keep) >= MAX_TABLES: break
        if t not in keep and len(profile["tables"]) <= MAX_TABLES: keep.append(t)
    return {"tables": keep, "columns": cols, "core": core, "values": values[:12],
            "coverage": round(covered / max(len(set(words)), 1), 3)}
