"""M0 check: greedy writer on 5 questions, with BIRD evidence, compare result sets to gold."""
import json, sqlite3, sys, time
from pathlib import Path
from agent.executor import execute
from agent.writer import build_prompt, sample

ROOT = Path(__file__).resolve().parent.parent
qs = json.loads((ROOT / "data/mini_dev_sqlite.json").read_text())
split = json.loads((ROOT / "eval/split.json").read_text())
calib = [q for q in qs if q["question_id"] in set(split["calibration"])][:5]  # never the reporting set

def ddl(db):
    c = sqlite3.connect(f"file:{ROOT}/data/dev_databases/{db}/{db}.sqlite?mode=ro", uri=True)
    return "\n\n".join(r[0] for r in c.execute("select sql from sqlite_master where type='table' and sql is not null"))

ok = 0
for q in calib:
    db = f"{ROOT}/data/dev_databases/{q['db_id']}/{q['db_id']}.sqlite"
    t = time.time()
    sql = sample("http://localhost:8081/v1", build_prompt(ddl(q["db_id"]), q["question"], q["evidence"]), 1, 0, max_tokens=3000)[0]
    try:
        got = sorted(map(repr, execute(db, sql).rows)) if sql else None
        gold = sorted(map(repr, execute(db, q["SQL"]).rows))
        hit = got == gold
    except Exception as e:
        hit, got = False, f"ERR {e}"
    ok += hit
    print(f"q{q['question_id']} {q['db_id']} parsed={sql is not None} correct={hit} {time.time()-t:.0f}s", flush=True)
print(f"{ok}/5 correct")
