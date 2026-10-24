# Orchestration: who builds what, in what order

Source of truth for scope: the "Build spec for Claude Code" section of `AI-02 Research — Text-to-SQL Agent on Messy Databases.md`. This file only covers how the build work is run.

## Two different "agents"

1. **The product** (what we ship): a pipeline run per question: triage → link → hints → write ×N → run/vote → checks → judge → decide. Models: Arctic-R1-7B writes SQL (N=5 samples), Qwen3-8B triages and judges. Only 2 model servers, 1 request stream at a time on the laptop.
2. **The build crew** (Claude Code agents that write the code): below.

## Build crew: 4 roles, max 3 running at once

| Role | Who | Owns | Never does |
| --- | --- | --- | --- |
| Product agent (PM) | Lead session (me) | Scope, cut line, milestone gates, `results/summary.md`, pitch numbers, merging work | Writes big modules itself while lanes are open |
| Coding agent A: data lane | Subagent | `profiler.py`, `hints.py`, `linker.py` | Touches writer prompt |
| Coding agent B: generation lane | Subagent | `writer.py`, `runner.py`, `checks.py` | Edits the Arctic template |
| Coding agent C: eval lane | Subagent | `eval/*`, split file, baselines, risk-coverage | Tunes on the 150 reporting questions |
| Reviewer | Fresh subagent, read-only | Checks every merged lane against the spec's "Done when" and hard rules | Writes feature code |

Lead builds `executor.py`, `decider.py`, `confidence.py`, `agent.py`, `ui/` (the integration-critical pieces).

## Parallelism by milestone

| Milestone | Running in parallel | Gate to pass |
| --- | --- | --- |
| M0 (now) | Lead: executor + servers. Background: model + DB downloads | executor tests green; logprobs confirmed |
| M1 | Eval lane C alone (needs the GPU/CPU for baseline) | baseline EX on 150, ± hints, in `results/` |
| M2 | A and B in parallel (disjoint files), C idle | Reviewer pass; benchmark-mode EX on 150 |
| M3 | Lead: decider/confidence; C: unanswerable + risk-coverage; reviewer on A/B | product mode returns contract for every question |
| M4–M5 | Lead: UI; C: charts; reviewer: final audit | demo script runs end to end |

Total: 1 lead + up to 3 concurrent subagents + 1 reviewer at gate time. Compute is the real limit: one local model request stream, so agents write code in parallel but model-heavy eval runs are serialized by the lead.

## Rules of engagement

- Lanes own disjoint files; interface = the dataclasses/signatures in the spec. No lane edits another's files.
- Every lane ships tests with the "Done when" condition from the spec.
- Reviewer checks hard rules: model ≤8B, writer template untouched, guardrails on every query, no tuning on the 150-question split.
- Anything that changes scope goes through the lead; cut line order: Jev → OmniSQL → GEPA → unseen dataset.

## Environment facts (checked)

- M4, 16 GB RAM: Arctic Q4_K_M (~4.8 GB) + Qwen3-8B Q4_K_M (~5 GB) fit together; no second writer locally.
- Writer template is the OmniSQL one (copied verbatim into `agent/writer.py`).
- Mini-Dev package: `bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip`.
