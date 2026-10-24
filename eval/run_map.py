"""How well does the migration map recover each drift kind? Offline: compares the derived map with the ground truth.
Run: .venv/bin/python -m eval.run_map california_schools"""
import json
import sys
from pathlib import Path

from agent.profiler import profile_db
from agent.schema_state import derive_map, map_accuracy
from scripts.rewrite_gold import rewrite, rows
from scripts.perturb_schema import KINDS

ROOT = Path(__file__).resolve().parent.parent


def main(db_id):
    old = profile_db(db_id)
    lines = [f"# Migration map recovery on {db_id}", "", "| Drift | Columns mapped correctly | Tables rebuildable | Ambiguous | Rewritten gold == original |", "|---|---|---|---|---|"]
    for kind in KINDS:
        d = ROOT / "data/perturbed" / kind / db_id
        new = profile_db(db_id, d.parent)
        derived = derive_map(old, new)
        truth = json.loads((d / "mapping.json").read_text())
        acc = map_accuracy(derived, truth)
        qs = json.loads((d / "questions.json").read_text())["questions"]
        ok = 0
        for q in qs:
            try:
                ok += rows(d / f"{db_id}.sqlite", rewrite(q["gold_sql"], derived)) == rows(ROOT / f"data/dev_databases/{db_id}/{db_id}.sqlite", q["gold_sql"])
            except Exception:
                pass
        lines.append(f"| {kind} | {acc['columns']} ({100 * acc['column_acc']:.1f}%) | {acc['tables_with_sql']}/{len(derived['tables'])} | {acc['ambiguous']} | {ok}/{len(qs)} |")
    Path("results/migration_map.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
