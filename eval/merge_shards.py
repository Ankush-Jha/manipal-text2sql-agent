"""Merge results/*_shard{i}of{N}.jsonl from several machines into the unsharded file name.
Usage: copy every machine's results/*.jsonl into this results/ folder, then: python -m eval.merge_shards"""
import re
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent.parent / "results"
groups = defaultdict(list)
for f in R.glob("*_shard*of*.jsonl"):
    groups[re.sub(r"_shard\d+of\d+", "", f.name)].append(f)
for name, files in groups.items():
    seen, lines = set(), []
    import json
    existing = R / name
    for f in ([existing] if existing.exists() else []) + sorted(files):
        for l in f.open():
            if l.strip() and (qid := json.loads(l).get("question_id", json.loads(l).get("id"))) not in seen:
                seen.add(qid); lines.append(l if l.endswith("\n") else l + "\n")
    (R / name).write_text("".join(lines))
    print(f"{name}: merged {len(files)} shards -> {len(lines)} records")
