"""Aggregate results/*.jsonl into results/summary.json (served by GET /results) and results/summary.md.
Missing runs are skipped, so this is safe to run at any point."""
import json
from collections import defaultdict
from pathlib import Path

from eval.risk_coverage import outcome, summarize

R = Path(__file__).resolve().parent.parent / "results"
RUNS = {
    "plain_no_hints": "baseline_report_hints_false", "plain_hints": "baseline_report_hints_true",
    "agent_no_hints": "agent_report_benchmark_hints_false_n5", "agent_hints": "agent_report_benchmark_hints_true_n5",
}


def load(stem: str) -> list[dict]:
    """The merged file plus any shards not merged yet, de-duplicated by question."""
    seen = {}
    for f in [R / f"{stem}.jsonl", *sorted(R.glob(f"{stem}_shard*of*.jsonl"))]:
        if f.exists():
            for l in f.open():
                if l.strip():
                    r = json.loads(l)
                    seen.setdefault(r.get("question_id", r.get("id")), r)
    return list(seen.values())


def acc(recs):
    if not recs:
        return None
    by = defaultdict(list)
    for r in recs:
        by[r.get("difficulty", "all")].append(r["correct"])
    return {"ex": round(100 * sum(r["correct"] for r in recs) / len(recs), 1), "n": len(recs),
            "by_difficulty": {d: round(100 * sum(v) / len(v), 1) for d, v in by.items()},
            "seconds_mean": round(sum(r.get("seconds", 0) for r in recs) / len(recs), 1)}


def build() -> dict:
    accuracy = {k: acc(load(v)) for k, v in RUNS.items()}
    def gain(agent_run, plain_run):
        """Points gained on the questions BOTH runs answered (a partial run must not be compared to the full set)."""
        ag = {r["question_id"]: r["correct"] for r in load(RUNS[agent_run])}
        pl = {r["question_id"]: r["correct"] for r in load(RUNS[plain_run])}
        both = ag.keys() & pl.keys()
        if not both:
            return None
        return round(100 * (sum(ag[q] for q in both) - sum(pl[q] for q in both)) / len(both), 1)
    prod, unans = load("agent_report_product_hints_false_n5"), load("unanswerable_product")
    outs = [outcome(True, r["status"], r["correct"]) for r in prod] + [outcome(False, r["status"], False) for r in unans]
    by_type = defaultdict(list)
    for r in unans:
        by_type[r.get("type") or "unknown"].append(r["status"] != "answered")
    rc = R / "risk_coverage_calibration.json"
    return {
        "accuracy": accuracy, "gain": {"no_hints": gain("agent_no_hints", "plain_no_hints"), "hints": gain("agent_hints", "plain_hints"),
                 "n_no_hints": len({r["question_id"] for r in load(RUNS["agent_no_hints"])} & {r["question_id"] for r in load(RUNS["plain_no_hints"])})},
        "risk_coverage": json.loads(rc.read_text()) if rc.exists() else [],
        "refusal": {**summarize(outs), "unanswerable_refused_by_type": {t: f"{sum(v)}/{len(v)}" for t, v in by_type.items()}} if outs else None,
        "latency": {"where": "local, Apple M4, Q4_K_M, llama.cpp",
                    "plain_seconds_mean": accuracy["plain_no_hints"]["seconds_mean"] if accuracy["plain_no_hints"] else None,
                    "agent_seconds_mean": accuracy["agent_no_hints"]["seconds_mean"] if accuracy["agent_no_hints"] else None},
        "split": {"report": 150, "calibration": 350, "seed": 42},
    }


def main():
    out = build()
    (R / "summary.json").write_text(json.dumps(out, indent=1))
    md = ["# Results (auto-generated)", "", "| Run | EX % | n |", "| --- | --- | --- |"]
    md += [f"| {k} | {v['ex'] if v else '-'} | {v['n'] if v else 0} |" for k, v in out["accuracy"].items()]
    md += ["", f"Gain without hints: {out['gain']['no_hints']} points; with hints: {out['gain']['hints']} points"]
    if out["refusal"]:
        r = out["refusal"]
        md += [f"TrustSQL-style score (c=1): {r['score_c1']:.3f} vs refuse-everything {r['naive_refuse_all']:.3f}; n={r['n']}"]
    (R / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
