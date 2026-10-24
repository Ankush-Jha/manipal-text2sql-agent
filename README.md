# Analyst: text-to-SQL that shows its work and knows when to say no

A local text-to-SQL agent for messy SQLite databases (BIRD Mini-Dev). Every model is open-weight and 8B or smaller, and nothing leaves the machine.

## Run the demo

```bash
scripts/start.sh            # writer + web app at http://localhost:8000 ("Always answer" mode)
scripts/start.sh --judge    # also the judge, needed for "Careful" mode (refusals)
scripts/start.sh --stop     # stop everything
```

The models are looked up in `models/` and then `~/Downloads`:
- `Arctic-Text2SQL-R1-7B.Q4_K_M.gguf` (SQL writer)
- `Qwen3-8B-Q4_K_M.gguf` (judge)

On a 16 GB Mac, run the judge only when you need Careful mode, and close other heavy apps first.

First-time setup:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python sqlglot pytest httpx scikit-learn fastapi uvicorn sse-starlette numpy
.venv/bin/python -m pytest -q
```

## How a question flows

The UI's Pipeline tab shows these steps live.

| Phase | Step | What it does | Model |
| --- | --- | --- | --- |
| Understand | Find tables & values | Lexical column match plus the exact stored values; keeps the top 5 tables | none |
| | Value check | Literals the model invented ('Blonde', '2016/6/23') are swapped for the stored spelling; `LITERAL_REPAIR=0` turns it off | none |
| | Auto-hints | Codes, stored values and date formats from the profiler; replaces BIRD's hand-written hints | none |
| | Can the data answer? | Answerable / ambiguous / data missing / not SQL, read from letter probabilities | Qwen3-8B |
| Generate | Write SQL attempts | N samples with the verbatim OmniSQL prompt | Arctic-R1-7B |
| | Run safely | Read-only, single SELECT/WITH, 10 s timeout, 1,000-row cap, one repair pass | SQLite |
| | Vote | Groups attempts by identical result set; the biggest group wins | none |
| Verify | Sanity checks | Empty result, all-NULL column, % over 100, negative counts, join explosion, dates out of range | none |
| | Double-check | Does this result answer the question? Yes / no / unsure | Qwen3-8B |
| | Decide | Calibrated confidence against a threshold; answer, refuse, or clarify | logistic regression |

There are two modes:
- **Always answer** (`benchmark`) never refuses, and is the only mode used for BIRD accuracy.
- **Careful** (`product`) may refuse or ask a clarifying question.

## Evaluation

```bash
.venv/bin/python -m eval.run_bird --hints false|true [--shard i/N]      # plain-model baseline, 150 reporting questions
.venv/bin/python -m eval.run_agent --split report --mode benchmark --hints false [--shard i/N]
.venv/bin/python -m eval.run_agent --split calibration --mode product   # signals for the confidence model
.venv/bin/python -m eval.calibrate results/agent_calibration_product_hints_false_n5.jsonl
.venv/bin/python -m eval.unanswerable build && .venv/bin/python -m eval.run_unanswerable
.venv/bin/python -m eval.merge_shards && .venv/bin/python -m eval.rescore results/*.jsonl && .venv/bin/python -m eval.summarize
```

- **Split:** `eval/split.json` is fixed at 150 reporting and 350 calibration questions, seed 42. Never tune on the reporting set.
- **Several Macs:** each runs `--shard i/N`. See `SETUP_MAC2.md`.
- **Results:** they appear in the app's **Results** view (`GET /api/results`) and in `results/summary.md`.

## Measured so far (honest status)

| Finding | Value |
| --- | --- |
| Plain Arctic-R1, no hints | 34.9% EX on 86 of 150 questions; Mac 2's half is still running |
| Gold-table recall, calibration split | 92.3% with BIRD evidence, 88.0% without |
| Qwen3-8B triage as a hard gate | Did not separate answerable from column-removed questions (40% false refusals), so it is a soft signal only |
| Judge logprobs | Need `chat_template_kwargs: {enable_thinking: false}`; Qwen3 ignores `/no_think` |

## Layout

```text
agent/   executor, profiler, linker, hints, writer, runner, checks, decider, confidence, agent
api/     FastAPI server (/api/*) that also serves the UI
ui/      no-build web app: index.html, css/app.css, js/{app,pipeline,results,data,icons,util}.js
eval/    split, baselines, agent runs, unanswerable set, calibration, rescoring, summary
tests/   pytest suite (no models needed)
```

## Business rules and dates (Careful mode)

- **Rules registry:** `rules/<db_id>.json` holds approved metric definitions (formula, aggregation, include/exclude, time basis, tables and joins, owner, version, approval). The judge model fixes typos and extracts what is being measured; if it is vague ("students avg") the agent asks which measure, narrows the options from each reply, and offers only rules whose columns exist in the database. The user can also answer in their own words. All business words and thresholds live in the JSON and `.env`, not in code.
- **Dates:** "last 30 days", "last fiscal year" and similar phrases are resolved once to explicit `[start, end)` ranges from the database's conventions (reference date, timezone, fiscal-year start) before any SQL is written.
- **Benchmark mode** skips both, so BIRD numbers stay comparable with the plain model.

## Data and models (not in the repo)

- `data/dev_databases/<db>/<db>.sqlite`, `data/mini_dev_sqlite.json`, `data/dev_tables.json`: BIRD Mini-Dev and the dev databases (see `AI-02 Research ...md`, Setup).
- `models/*.gguf`: the two models listed above.
- Copy `.env.example` to `.env`.
