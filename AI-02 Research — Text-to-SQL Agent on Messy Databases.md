# AI-02 Research — Text-to-SQL Agent on Messy Databases

Oct 24, 2026 · @Super DevAccount

## TL;DR

Build a small-model analyst agent that works without BIRD's hand-written hints, samples several SQLs, checks them, and refuses only when a calibrated confidence score says so. It runs in two modes: a benchmark mode that always answers, and a product mode that can refuse. Lead the pitch with measured gains over the plain model, not absolute scores.

- **Models:** Arctic-Text2SQL-R1-7B as the single SQL writer, sampled 4–6 times (68.9% on BIRD dev with hints, one pass). Qwen3-8B as triage and judge. OmniSQL-7B only if memory and time allow.
- **Numbers to expect:** the published 69% assumes hints; without them expect 10–20 points lower. Mini-Dev labels are about half wrong, so report the gain over plain Arctic-R1 on the same questions, with and without hints.
- **Edge over other teams:** works on hint-free questions via auto-generated hints, a calibrated refusal score, and a visible trace for every answer.
- **GEPA:** only on the triage and judge prompts, only after everything else works; first thing to cut.
- **Jev:** optional in product mode if organisers allow it; every reported number uses the local Qwen3-8B decider.
- **Pitch line:** "The analyst that shows its work and knows when to say no."

## Build spec for Claude Code

Claude Code: build from this section. Everything after it is background and evidence; read the critique table before changing scope. If anything here conflicts with a later section, this section wins.

### Goal and hard rules

Build a Python agent that answers plain-English questions over a SQLite database, checks its own SQL, and either answers or refuses with a reason. It is judged at Round 1 (3:00 AM IST, Sun 25 Oct 2026) on a slide deck, a working prototype and a presentation.

1. **Model rule.** Every model in any reported number must be open-weight with 8B parameters or fewer: Arctic-Text2SQL-R1-7B (SQL writer), Qwen3-8B (triage and judge), optionally OmniSQL-7B, and a small embedding model. Jev is allowed only behind `DECIDER=jev`, off by default.
2. **Two modes.** `MODE=benchmark` always returns the best-voted SQL and is the only mode scored on BIRD. `MODE=product` may refuse or ask a clarifying question.
3. **Guardrails on every query.** Open SQLite read-only (`file:...?mode=ro` URI), allow a single SELECT or WITH statement only (check with `sqlglot`), 10-second timeout, at most 1,000 rows returned.
4. **Never edit the writer's prompt template.** Arctic-R1 was trained on a modified OmniSQL prompt ([paper](https://arxiv.org/html/2505.20315v2)). Copy it from the OmniSQL repository ([GitHub](https://github.com/RUCKBReasoning/OmniSQL)) or Snowflake's ArcticTraining repository, then confirm it on 5 questions before building on it.
5. **Never tune on the reporting subset.** See Evaluation protocol.

### Stack

- Python 3.11, `sqlite3`, `sqlglot`, `datasketch` (MinHash LSH for value lookup), `sentence-transformers` with a small embedding model, `scikit-learn` (logistic regression), `streamlit` (UI), `httpx`, `pydantic`.
- Model serving: `llama-server` from llama.cpp (OpenAI-compatible) for local runs; vLLM on a rented GPU or Featherless ([hosts Arctic-R1](https://featherless.ai/models/Snowflake/Arctic-Text2SQL-R1-7B)) for the evaluation runs.
- Optional, only after the cut line: `dspy` for GEPA, TypeSafe SDK for Jev.

### Setup

```bash
# Questions (SQLite split) from Hugging Face; databases from the "Complete Package" link on the same dataset card
python -c "from datasets import load_dataset; load_dataset('birdsql/bird_mini_dev')['mini_dev_sqlite'].to_json('data/mini_dev_sqlite.json')"
# Unzip the complete package so databases sit at data/dev_databases/<db_id>/<db_id>.sqlite

# Local models (verify the quant tags exist before relying on them)
llama-server -hf mradermacher/Arctic-Text2SQL-R1-7B-GGUF:Q4_K_M --port 8081 -c 16384
llama-server -hf Qwen/Qwen3-8B-GGUF:Q4_K_M --port 8082 -c 8192
```

The dataset card for `birdsql/bird_mini_dev` links the complete database package ([dataset](https://huggingface.co/datasets/birdsql/bird_mini_dev)). Each database folder also holds `database_description` CSVs; the profiler should read them.

### Configuration (`.env`)

```bash
WRITER_URL=http://localhost:8081/v1
JUDGE_URL=http://localhost:8082/v1
DECIDER=local            # local | jev
TYPESAFE_API_KEY=        # only if DECIDER=jev
MODE=product             # benchmark | product
N_SAMPLES=5
TEMPERATURE=0.8
QUERY_TIMEOUT_S=10
MAX_ROWS=1000
DB_DIR=data/dev_databases
USE_BIRD_HINTS=false     # true only for the with-hints comparison run
```

### Repository layout

```text
agent/
  executor.py      # read-only, SELECT-only, timeout, row cap
  profiler.py      # per-column stats, dirty tokens, description CSVs -> cache/profile_<db>.json
  hints.py         # auto-generated BIRD-style hints from the profile
  linker.py        # embedding column retrieval + LSH value lookup -> pruned schema
  writer.py        # Arctic-R1 prompt, N samples, extract final sql code block
  runner.py        # execute candidates, one repair pass on error, group by result, vote
  checks.py        # deterministic result checks
  decider.py       # decide(question, options) -> {option: prob}; local or jev
  confidence.py    # features -> calibrated P(correct); threshold
  agent.py         # orchestration; returns AgentResult
eval/
  make_split.py    # fixed 150 reporting / 350 calibration split, seed 42, stratified by difficulty
  run_bird.py      # baseline vs agent, with and without hints, EX
  unanswerable.py  # loads the human-written set; makes column-removed variants
  risk_coverage.py # curve + TrustSQL-style reliability score
ui/app.py          # Streamlit demo with trace panel
results/           # JSON per run + summary.md
```

### Output contract

```json
{
  "status": "answered | refused | needs_clarification",
  "answer_rows": [["..."]],
  "sql": "SELECT ...",
  "confidence": 0.0,
  "reason": "why refused or what to clarify",
  "trace": [{"step": "triage|link|hints|write|run|vote|checks|judge|decide", "detail": {}}]
}
```

### Component requirements

| Module | Must do | Done when |
| --- | --- | --- |
| `executor.py` | Read-only URI; `sqlglot` rejects anything but one SELECT/WITH; timeout via `set_progress_handler`; cap rows | A DROP, an INSERT and a 30-second query are all refused in tests |
| `profiler.py` | Type, null rate, distinct count, top 20 values, dirty tokens ("N/A", "-", blanks, mixed date formats), descriptions from CSVs | Profiles all 11 Mini-Dev DBs into cache in under 5 minutes |
| `hints.py` | Turn profile entries for linked columns into short hint lines, e.g. "gender: 'F' = female" | Hint text appears in the trace for every question |
| `linker.py` | Embed column names and descriptions; LSH lookup of question keywords against stored values; keep top tables and columns | Gold tables kept for at least 90% of calibration questions |
| `writer.py` | Exact Arctic-R1 template; N samples at TEMPERATURE; extract the last sql code block | Greedy output parses on 5 sample questions |
| `runner.py` | Run all candidates; one repair prompt with the error text; group by result set (order-insensitive unless the SQL has ORDER BY); majority vote | Vote and group sizes logged in the trace |
| `checks.py` | Flags: zero rows, all-NULL column, percentage over 100, negative count, row explosion after a join, date outside data range | Each flag has a unit test |
| `decider.py` | Ask a lettered multiple-choice question; read token probabilities for each letter; `jev` branch calls TypeSafe | Returns probabilities summing to about 1; fails loudly if logprobs are missing |
| `confidence.py` | Features: vote share, number of groups, check flags, link coverage, judge P(yes), triage label; logistic regression fit on calibration split | Saved model and threshold in `results/` |
| `agent.py` | Triage, link, hints, write, run, vote, checks, judge, decide; respects MODE | Returns the output contract for every question without crashing |
| `ui/app.py` | Question box, DB picker, mode toggle, answer, expandable trace, refusal reason | Demo script below runs end to end |

### Evaluation protocol

1. `make_split.py` fixes 150 Mini-Dev questions for reporting and 350 for calibration, stratified by difficulty, seed 42. Commit the split file.
2. Fit the confidence model, choose thresholds and run any GEPA tuning on the 350 calibration questions only.
3. On the 150 reporting questions, benchmark mode, record EX for: plain Arctic-R1 greedy and the full agent, each with `USE_BIRD_HINTS=true` and `false`.
4. EX matches BIRD's rule: the predicted and gold result sets must be equal.
5. Product mode: risk–coverage curve on the 150 questions, plus TrustSQL-style scores on the unanswerable set.
6. Write every run to `results/<run>.json` and update `results/summary.md` with one table.

### Milestones

- [ ] **M0 (hour 0–1):** both servers up; logprobs confirmed from the judge server; data loaded; `executor.py` with tests
- [ ] **M1 (hour 1–2):** split file; baseline EX on 150, with and without hints
- [ ] **M2 (hour 2–5):** profiler, hints, linker, writer sampling, runner with repair and vote; benchmark-mode EX on 150
- [ ] **M3 (hour 5–8):** checks, decider (local), confidence model, product mode; risk–coverage curve
- [ ] **M4 (hour 8–10):** Streamlit UI and demo on `california_schools`; unanswerable set scored
- [ ] **M5 (hour 10–12):** `results/summary.md` and charts for the slides; two demo rehearsals
- [ ] **Stretch, only if ahead:** Jev decider, OmniSQL second writer, GEPA on triage and judge prompts, an unseen messy dataset

### Human tasks (not for Claude Code)

- A teammate who did not build the judge writes 40–50 unanswerable questions for the Mini-Dev databases, covering TrustSQL's four types, into `eval/unanswerable.jsonl`.
- Ask organisers whether Jev may be used in product mode.
- Build the slide deck from `results/summary.md`.

## Brutal critique: what breaks this plan

The first draft of this plan would have lost. Its headline numbers assumed hints real users never give, its refusal feature scores zero on the benchmark it is judged by, and it tried to build a research paper in 13 hours. Each problem below is fixed in the section named in the last column.

| # | What's wrong | Evidence | Fix (where) |
| --- | --- | --- | --- |
| 1 | **The benchmark punishes our main feature.** BIRD only checks execution results, so every refusal scores 0. | EX gives 1 only for an identical result set ([Agentar-Scale-SQL](https://arxiv.org/pdf/2509.24403)) | Two modes: benchmark mode always answers; product mode refuses. Report both (What we offer) |
| 2 | **Every headline number assumes BIRD's hand-written hints.** Each BIRD question ships with an "evidence" line such as "female refers to gender = 'F'". Real users and the live demo have none. | GPT-4 fell from 54.89% to 34.88% on BIRD test without hints ([BIRD review](https://liner.com/review/can-llm-already-serve-as-a-database-interface-a-big)); systems lose over 10 points, and only 5 of 52 leaderboard methods report no-hint results ([DIVER](https://arxiv.org/html/2602.12064)) | Auto-generate hints from the profiler, as SEED does ([SEED](https://arxiv.org/html/2506.07423v1)); report with and without hints (Techniques) |
| 3 | **68.9% is a BIRD number, not a real-world number.** | Arctic-R1-7B's own card: 36.7% on EHRSQL, 15.6% on Spider2.0-DK ([model card](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)); models scoring 67–69% on BIRD dev fell to 19–28% on BIRD-History ([BIRD-History](https://arxiv.org/pdf/2608.29345)) | Demo on BIRD's own `california_schools` DB first; unseen Indian data is a stretch goal (What we offer) |
| 4 | **BIRD Mini-Dev is about half mislabeled.** Absolute scores on it are noise. | Annotation errors in 52.8% of Mini-Dev examples; corrected labels moved agent scores by −7% to +31% ([Jin et al., VLDB](https://vldb.org/pvldb/volumes/19/paper/Pervasive%20Annotation%20Errors%20Break%20Text-to-SQL%20Benchmarks%20and%20Leaderboards)) | Report the gain over the plain model on the same questions, not an absolute score (TL;DR, What we offer) |
| 5 | **The "65–70% on Mini-Dev" target was made up.** | On Mini-Dev, GPT-4o zero-shot scored 28% without hints and 63% with a strong method plus hints ([Multi-Turn T2S](https://arxiv.org/pdf/2408.11062)) | Target removed; measure the baseline in hour 1 (TL;DR) |
| 6 | **Voting agreement is a poor refusal signal.** Wrong answers can agree with each other. | Raw self-consistency is over-confident; it could not form a low-risk subset at any threshold, while a calibrated mix of signals could ([selective-prediction study](https://arxiv.org/pdf/2607.06799)) | Combine signals and calibrate on held-out questions (Verification) |
| 7 | **An 8B judge is weak and inconsistent.** | The same query can get different verdicts across judge calls ([Agent-Agnostic Eval](https://arxiv.org/pdf/2604.28049)); the best verifiers that generalise are large reasoning models ([same study](https://arxiv.org/pdf/2607.06799)) | Judge is one signal among several, never the only gate (Verification) |
| 8 | **Massively overscoped for 13 hours.** Profiler, value search, 2 writers, voting, repair, checks, judge, Jev, GEPA, UI, unanswerable set, new dataset and a 500-question eval. | — | Strict build order with a cut line (What we offer) |
| 9 | **Compute doesn't fit.** 500 questions × 6 samples from a long-reasoning model on a laptop takes hours; three models crowd 16 GB of RAM. Arctic-R1-7B isn't on mainstream inference APIs. | Hugging Face lists no inference provider for it ([model card](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)); Featherless hosts it ([Featherless](https://featherless.ai/models/Snowflake/Arctic-Text2SQL-R1-7B)); GGUF quants are 4.8 GB at Q4\_K\_M ([GGUF](https://huggingface.co/mradermacher/Arctic-Text2SQL-R1-7B-GGUF/blob/main/README.md)) | One writer sampled several times; 150-question eval subset; OmniSQL optional (Models) |
| 10 | **Jev adds four risks:** rule violation, access in flux, venue Wi-Fi, and only self-reported accuracy (67.8%). | TypeSafe paused direct signups for a period after launch ([flaviocopes](https://flaviocopes.com/jev-api-key/)); OpenRouter, Vercel and Cloudflare serve it without a waitlist ([Apidog](https://apidog.com/blog/how-to-access-jev/)) | Local mode is the default for every reported number; Jev only in product mode if organisers agree (Verification) |
| 11 | **GEPA's wins came from terrible baselines or big models.** Fine-tuned SQL writers expect their own prompt template, so rewriting it can hurt. | Amity started from 5.7% ([Amity](https://www.amity.co/ai-labs/gepa-text-to-sql)); Fireworks used Qwen3-32B and DeepSeek V3 ([Fireworks](https://fireworks.ai/blog/self-improving-agent)) | GEPA only on triage and judge prompts, last, first to cut (Techniques) |
| 12 | **Nothing here is new.** CHESS, XiYan and CSC-SQL already do linking, candidates and selection; strong teams will copy them too. | See Techniques sources | Differentiate on no-hint robustness, calibrated refusal and the trace (TL;DR) |
| 13 | **A self-written unanswerable set looks rigged.** | — | Written blind by a teammate who didn't build the judge, plus BIRD questions with the needed column removed (Verification) |
| 14 | **Customer evidence leans on vendor marketing.** Querio, Promethium, Atlan and AtScale sell the fix they describe. | See Customers section | Vendor claims labelled; lead with Snowflake's own 51% and Omni's analysis (Customers) |
| 15 | **The model chart is not apples to apples.** Papers differ on prompts, voting and hints. | See chart sources | Caveat added to the chart (Models) |
| 16 | **Model-written SQL runs with no guardrails.** One bad query can lock or wipe a database. | The Arctic model card itself says to validate generated SQL ([model card](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)) | Read-only connection, SELECT-only, timeout, row cap (What we offer) |
| 17 | **The local judge needs token probabilities.** Not every local server returns them reliably. | — | Use llama.cpp server or vLLM; verify in hour 1 (Risks) |

## What the judges will actually test

The statement scores four things: right tables and columns, handling dirty values and hidden business rules, checking results before answering, and refusing questions the data cannot answer. Two hard rules frame everything: open-weight models of 8B parameters or fewer, and scoring on the BIRD benchmark by execution results.

- **BIRD scores by execution, not by SQL text.** Your query is run; it scores 1 only if its result set is identical to the gold query's result, and 0 for any mismatch or error ([Agentar-Scale-SQL, appendix C](https://arxiv.org/pdf/2509.24403)).
- **BIRD is built to be messy.** 12,751 question–SQL pairs over 95 real databases (33.4 GB) in 37 domains, unlike older toy-schema benchmarks ([BIRD paper review](https://beancount.io/bean-labs/research-logs/2026/06/06/bird-benchmark-text-to-sql-real-database-gap)). The dev set has 1,534 questions.
- **Human ceiling is 92.96%** execution accuracy, set by data engineers and DB students ([analysis of top BIRD systems](https://medium.com/@adnanmasood/pushing-towards-human-level-text-to-sql-an-analysis-of-top-systems-on-bird-benchmark-666efd211a2d)).
- **"A plausible wrong answer is worse than none"** is in the statement itself. BIRD alone does not score abstention, so you must bring your own measurement for it (Section: Verification and abstention).

What this means for scoring in a 36-hour room: judges cannot run the full BIRD test set on your laptop. They will look at (1) a credible measured number on a BIRD dev subset, (2) a live demo on a messy DB, and (3) whether the agent visibly checks itself and says "I can't answer this" correctly.

## State of the art: where the ceiling is

The best systems sit around 80–82% on BIRD test; humans sit at 93%. Everything at the top uses huge models plus many SQL candidates and a selector, which is exactly the recipe you can shrink to 8B.

| System | Model size | BIRD EX | Note |
| --- | --- | --- | --- |
| Human (data engineers + DB students) | — | 92.96% test | the ceiling |
| [Huawei DataGallery-Text2SQL](https://technologymagazine.com/news/huawei-datagallery-tops-benchmark-for-enterprise-text2sql-ai) | large, multi-path | 82.39% test | #1 as of 9 Sep 2026 |
| [Agentar-Scale-SQL](https://arxiv.org/pdf/2509.24403) | large, test-time scaling | 81.67% test | orchestrated candidates + selection |
| [Gemini-SQL2](https://aiweekly.co/alerts/googles-gemini-sql2-tops-bird-text-to-sql-at-8004) (Google, Jun 2026) | Gemini 3.1 Pro | 80.04% test | #1 single-model; no paper or API |
| [Arctic-Text2SQL-R1-32B](https://arxiv.org/html/2505.20315v2) (Snowflake) | 32B open | 71.83% test | best open single model, greedy |
| [ReViSQL](https://arxiv.org/abs/2603.20004v1) | 235B MoE | 93.2% on expert-verified Mini-Dev | first to beat human proxy, on cleaned labels |

Three findings matter for you:

- **How the winners win.** Huawei's #1 system runs several reasoning strategies in parallel (few-shot, skeleton-first, self-reflection, top-down), then picks one SQL by majority vote, pairwise LLM comparison or a lightweight 8B classifier; the same framework adds 8–12 points over the bare model ([source](https://technologymagazine.com/news/huawei-datagallery-tops-benchmark-for-enterprise-text2sql-ai)). That architecture fits inside an 8B budget.
- **BIRD's own labels are noisy.** ReViSQL found that training on an expert-cleaned "BIRD-Verified" set alone added 8.2–13.9 points ([source](https://arxiv.org/abs/2603.20004v1)). Some of your "errors" on BIRD dev will be gold-label errors; say so in the pitch with 2–3 examples.
- **Enterprise is much harder than BIRD.** On Spider 2.0 (real enterprise DBs, often 1,000+ columns), the best o1-preview agent solved 21.3% versus 73.0% on BIRD for comparable methods ([Spider 2.0, ICLR 2025](https://www.arxiv.org/pdf/2411.07763)). This is your story for why verification and abstention matter more than raw accuracy.

Two caveats undercut every number in the table above:

- **They use BIRD's hand-written hints.** Each question ships with an "evidence" sentence. Without it, GPT-4 dropped from 54.89% to 34.88% on BIRD test ([review](https://liner.com/review/can-llm-already-serve-as-a-database-interface-a-big)), and only 5 of 52 leaderboard methods even report hint-free results ([DIVER](https://arxiv.org/html/2602.12064)).
- **The labels are noisy.** Experts found annotation errors in 52.8% of BIRD Mini-Dev examples, and correcting a dev subset changed agent rankings by up to 9 places ([Jin et al.](https://arxiv.org/pdf/2601.08778)). Use BIRD to measure your own improvement, not to claim a rank.

## Best open models at 8B or below

Use Arctic-Text2SQL-R1-7B as your main SQL writer. It scores 68.9% on BIRD dev with a single greedy pass, nearly 20 points above the plain Qwen2.5-Coder-7B it is built from. Tuning, not size, is what separates the 7B models.

&#91;embedded content: BIRD dev EX from Arctic-Text2SQL-R1, CSC-SQL, GradeSQL, Progress-SQL, LIMIT and CogniSQL papers; reference lines from BIRD test leaderboard\]

| Model | What it is | Role in your agent |
| --- | --- | --- |
| [Arctic-Text2SQL-R1-7B](https://arxiv.org/html/2505.20315v2) (Snowflake) | Qwen2.5-Coder-7B trained with RL, rewarded only for correct execution; matches 70B-class models | Primary SQL writer |
| [OmniSQL-7B](https://arxiv.org/pdf/2503.02240) | Trained on 2.5M synthetic samples over 16,000+ databases; gains about 8 points over its base model | Optional second writer, only if memory and time allow |
| Qwen3-8B | General reasoning model; 59.5% greedy, 62.3% with 8 votes ([Progress-SQL](https://arxiv.org/pdf/2606.06825)) | Checker, refusal judge and answer explainer |
| [CSC-SQL](https://arxiv.org/pdf/2505.13271) recipe | Samples several SQLs, then a trained reviser merges the top two answers; 69.19% at 7B | Selection method to copy, not a model you need |

Practical notes, including what the chart hides:

- **The chart is not apples to apples.** Papers differ in prompts, voting and decoding, and all use BIRD's hints.
- **BIRD scores don't transfer.** Arctic-R1-7B's own card lists 36.7% on EHRSQL and 15.6% on Spider2.0-DK ([model card](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)). Models at 67–69% on BIRD dev fell to 19–28% on BIRD-History ([BIRD-History](https://arxiv.org/pdf/2608.29345)).
- **Use the model's own prompt template.** Fine-tuned writers expect the prompt format they were trained on; don't let GEPA or your own edits rewrite it.
- **Hosting.** Hugging Face lists no inference provider for Arctic-R1-7B, but Featherless hosts it ([Featherless](https://featherless.ai/models/Snowflake/Arctic-Text2SQL-R1-7B)) and GGUF quants run locally at 4.8 GB (Q4\_K\_M) ([GGUF](https://huggingface.co/mradermacher/Arctic-Text2SQL-R1-7B-GGUF/blob/main/README.md)).
- **Memory.** Two 7B writers plus an 8B judge at 4-bit is about 15 GB, too tight for a 16 GB laptop; run one writer locally.
- **Votes and value lookups add little on a strong model.** Arctic's paper shows about 0.7–1 point from both on its 14B and 32B models ([source](https://arxiv.org/html/2505.20315v2)).
- **Stay on SQLite.** On BIRD Mini-Dev, Llama-3-8B scored 24.4% on SQLite but 18.4% on PostgreSQL ([BIRD Mini-Dev](https://github.com/bird-bench/mini_dev)).

## Techniques that move the needle (and GEPA)

The biggest wins for small models come from feeding them a smaller, correct slice of the schema and from picking among several candidates using execution results. GEPA is the cheapest way to tune the prompts inside that pipeline in the time you have.

| Technique | What it does | Evidence | Do it in 13 h? |
| --- | --- | --- | --- |
| Schema linking (prune tables/columns) | Give the model only the tables and columns it needs | Schema-linking mistakes caused over 60% of failures in one error analysis ([LinkAlign](https://arxiv.org/pdf/2503.18596v4)); small models degrade sharply without pruning ([LitE-SQL](https://arxiv.org/pdf/2510.09014)) | Yes, core |
| Value retrieval (LSH + embeddings) | Find the real stored spelling of "Delhi", "N/A", "Govt." before writing WHERE clauses | Used by CHESS and XiYan-SQL ([XiYan](https://arxiv.org/pdf/2411.08599)); CHESS reached 61.5% on BIRD dev with open models ([CHESS](https://arxiv.org/pdf/2405.16755v1)) | Yes, core |
| Multiple candidates + execution-based pick | Sample several SQLs, run them, group by identical result, pick the winner | Huawei's #1 system does this; reward-model pick adds 5 points to OmniSQL-7B ([GradeSQL](https://arxiv.org/pdf/2509.01308)) | Yes, core |
| Execution-guided repair | Feed SQL errors and empty results back to the model to fix | Standard in LitE-SQL and CHESS | Yes |
| RL fine-tuning (GRPO) | Train with "did it execute correctly" as the reward | How Arctic-R1 and CSC-SQL got their scores | No, use their weights |
| **GEPA prompt optimisation** | An LLM reads failure traces and rewrites the prompts, keeping a diverse set of best prompts | See below | Yes, 1–2 h run |

**The missing technique: generate your own hints.** Most published scores lean on BIRD's hand-written hints, and systems lose over 10 points without them ([DIVER](https://arxiv.org/html/2602.12064)). SEED builds hints automatically from the schema, description files and sampled values, and sometimes beats the hand-written ones ([SEED](https://arxiv.org/abs/2506.07423v1)). Your profiler already collects this: for each column, store its meaning, code values ("F means female") and units, then pass the relevant ones to the writer as a hint. This is what makes the live demo work on questions with no hints.

**What GEPA is.** GEPA (Genetic-Pareto) is a prompt optimiser from Agrawal et al., accepted as an ICLR 2026 oral ([summary](https://www.morphllm.com/gepa-prompt-optimization)). It reads full execution traces, writes a plain-language diagnosis of each failure, and proposes a targeted prompt fix. It keeps a Pareto set of prompts that each win on different questions, instead of one "best" prompt ([paper](https://www.alphaxiv.org/abs/2507.19457v2)).

**Why it suits you.** It reports beating MIPROv2 by 13% and GRPO by 20% while using 35× fewer rollouts, roughly 100–500 evaluations instead of 10,000+ ([summary](https://www.morphllm.com/gepa-prompt-optimization)). It runs through DSPy's `dspy.GEPA` optimizer.

**Text-to-SQL results so far:**

- Amity AI Labs lifted a DSPy text-to-SQL agent from 5.7% to over 41% accuracy just by letting GEPA rewrite the instruction ([Amity](https://www.amity.co/ai-labs/gepa-text-to-sql)).
- Fireworks used GEPA on a 243-question DuckDB set and reported about +10% test accuracy in roughly 45 minutes of search; the learned prompt encoded concrete output and naming rules ([Fireworks](https://fireworks.ai/blog/self-improving-agent)).

**How to use it, if at all.** Tune only the triage and judge prompts, never the SQL writer's prompt, which must match its training template. Run it last, on the 350-question calibration split, after the core pipeline works. The reflection model must also be 8B or smaller, which weakens GEPA, since the published wins came from terrible starting prompts (5.7%) or 32B-plus models. Never tune on the questions you report. It is the first thing to cut.

## Verification and abstention: the gap nobody has closed

Refusing correctly is an open research problem, and that is your opening. In the TrustSQL benchmark, no tested method beat the naive baseline of refusing every question once wrong answers were penalised ([TrustSQL](https://www.paperswithcode.com/paper/trustsql-a-reliability-benchmark-for-text-to)). A team that shows a measurable refusal score is doing something the papers have not solved.

**How TrustSQL scores reliability.** Every question ends in one of five outcomes ([TrustSQL](https://arxiv.org/pdf/2403.15879v3)):

| Outcome | Score |
| --- | --- |
| Correct SQL on an answerable question | reward |
| Refused an answerable question | neutral |
| Wrong SQL on an answerable question | penalty |
| Any SQL on an unanswerable question | penalty |
| Refused an unanswerable question | reward |

Copy this scoring for your demo slide. It turns "a plausible wrong answer is worse than none" into a number.

**The four kinds of unanswerable question** to put in your own test set ([TrustSQL](https://arxiv.org/html/2403.15879v4)):

- **Ambiguous** — refers to a column or value without saying which ("top schools" by what?).
- **Schema mismatch** — asks for data the tables do not hold ("teacher satisfaction" when there is no such column).
- **Outside SQL** — needs a forecast, opinion or action SQL cannot do.
- **Outside knowledge** — needs world facts not in the database.

**Signals your agent can use to decide to refuse** (all cheap at 8B):

1. **Candidate agreement.** If 5 of 6 sampled SQLs return the same result, confidence is high; if they split 2-2-2, refuse or ask. Huawei's top system uses confidence-based selection the same way ([source](https://technologymagazine.com/news/huawei-datagallery-tops-benchmark-for-enterprise-text2sql-ai)).
2. **Schema coverage.** If no column links to a key noun in the question after value and column search, it is likely a schema mismatch.
3. **Result sanity checks.** Zero rows, all-NULL columns, a percentage above 100, negative counts, a date range outside the data, or a row count that explodes after a join.
4. **Judge pass.** Qwen3-8B reads the question, SQL and first rows and answers "does this answer the question? yes / no / ambiguous".

**Don't trust any one signal.** A recent study found raw self-consistency over-confident: it could not pick out a low-risk set of questions at any threshold. A calibrated combination of signals could, answering 27% of questions at 24% error ([selective-prediction study](https://arxiv.org/pdf/2607.06799)). LLM judges also give different verdicts to the same query across calls ([Agent-Agnostic Eval](https://arxiv.org/pdf/2604.28049)).

So: run the deterministic checks first, then feed agreement, schema coverage, check results and the judge's P(yes) into a small logistic regression. Fit it on one half of a held-out set, choose the refusal threshold, and report on the other half. Show a risk–coverage curve: error rate against share of questions answered.

**Make the unanswerable set honest.** A teammate who didn't build the judge writes 40–50 questions blind, following the four types above. Add BIRD questions made unanswerable by deleting the column they need. Report refusal results on this set separately from BIRD.

### Jev as the decision layer, with a local fallback

Jev (TypeSafe AI) is built exactly for this step, so we use it for the agent's yes/no decisions and keep an identical Qwen3-8B version behind one switch in case organisers rule it out.

**What Jev is.** TypeSafe AI, founded by former OpenAI researcher Diogo Almeida, released Jev on 15 September 2026 with $40M in funding ([Winzheng](https://www.winzheng.com/en/article/typesafe-ai-jev-system-one-model-launch)). It does not write text. It picks from answers you define and returns choices, scores or yes/no probabilities ([Towards AI](https://pub.towardsai.net/the-ai-model-that-doesnt-generate-text-is-up-to-200x-faster-9d2c6da82e51)).

| Fact | Value |
| --- | --- |
| Claimed speed and cost | about 200× faster and 400× cheaper than frontier LLMs (company claim) ([Level Up](https://levelup.gitconnected.com/the-risks-of-using-jev-ai-in-enterprise-software-5d39ffc72842)) |
| Price | $0.042 per 1M input tokens; output free ([DigitalMarketer KR](https://www.digitalmarketer.co.kr/class/coding-agents-basics/what-is-jev-ai)) |
| Own reported accuracy | 67.8% average over 4 workflows, 0.4 s per call ([same](https://www.digitalmarketer.co.kr/class/coding-agents-basics/what-is-jev-ai)) |
| Access | Direct signups were paused for a period after launch ([flaviocopes](https://flaviocopes.com/jev-api-key/)); OpenRouter, Vercel AI Gateway and Cloudflare serve it without a waitlist ([Apidog](https://apidog.com/blog/how-to-access-jev/)); hosted, not open-weight |
| Adoption | Used by 35% of paid teams within two weeks ([Pluang/TechCrunch](https://pluang.com/en/news-feed/jev-model-ai-tercepat-diadopsi-versel)) |

**The rule risk.** AI-02 allows only open-weight models of 8B or smaller. The statement does not ban APIs, but Jev's weights are not released and its size is unpublished, so it fails the rule however you call it. Hosted APIs serving open 8B models (Groq, Together, Fireworks) are fine. One report also calls it early beta with production calibration unproven ([Digg](https://digg.com/ai/b1p67j8x)), and another warns it returns answers whether or not it is set up correctly ([Level Up](https://levelup.gitconnected.com/the-risks-of-using-jev-ai-in-enterprise-software-5d39ffc72842)).

**Where Jev runs in the agent.** Each step is a closed question with a fixed answer set, which is what Jev is for; a recent paper, [JEV-as-a-Judge](https://arxiv.org/pdf/2609.26550), argues for this accept-when-confident, escalate-when-unsure pattern.

| Step | Question to Jev | Answers |
| --- | --- | --- |
| Triage, before any SQL | Can this database answer the question? | answerable / ambiguous / data missing / not a SQL question |
| Table relevance | How relevant is each table to the question? | a score per table, used to prune the schema |
| Final judge | Does this result answer the question? | yes / no / ambiguous, with probability |

Combine the judge's P(yes) with candidate agreement into one confidence score, and refuse below the threshold.

**The fallback switch.** Put every Jev call behind one interface, `decide(question, options)`, with a setting `DECIDER=jev` or `DECIDER=local`. The local version asks Qwen3-8B the same closed question and reads its probabilities for each option instead of generated text. Every reported number uses the local decider. Jev runs only in product mode, only if the organisers say yes before Round 1. It also needs venue Wi-Fi, and its only published accuracy (67.8%) is TypeSafe's own.

On stage: "Jev makes our decisions in under half a second; flip one switch and the whole agent is open-weight and on this laptop."

## What real customers face today

Business users don't fail because the SQL won't run; they fail because it runs and returns a confident wrong number. Vendors fix this with months of hand-built semantic models, which smaller teams cannot afford. A tool that checks itself and refuses on raw, messy data addresses the gap.

Read the evidence with care. Querio, Promethium, Atlan and AtScale each sell the fix they describe, so their figures are marketing. The strongest sources here are Snowflake's own 51% figure for GPT-4o and Omni's failure analysis; quote those on stage.

**Who uses what, and where it breaks**

| Tool | Who buys it | What it needs to work | Where it breaks |
| --- | --- | --- | --- |
| [Snowflake Cortex Analyst](https://snowflake.com/?p=458942) | Snowflake-first companies | A YAML semantic model of metrics, synonyms and verified queries | Snowflake says GPT-4o alone scored 51% on its internal set; it claims 90%+ only with the semantic model |
| [Databricks Genie](https://querio.ai/articles/best-ai-analytics-tools-connect-snowflake-bigquery-databricks) | Databricks-first companies | Curated "Genie spaces" and Unity Catalog metadata | Capped at 30 tables per space; accuracy relies on manual tuning |
| Semantic-layer BI (dbt, Omni, Looker) | Companies with a data team | Metric definitions maintained by analysts | Answers drift when definitions change and the model isn't updated ([comparison](https://querio.ai/articles/snowflake-cortex-vs-databricks-genie-warehouse-ai-compared)) |
| [Gemini-SQL2](https://aiweekly.co/alerts/googles-gemini-sql2-tops-bird-text-to-sql-at-8004) (Google) | Google Cloud customers | Cloud API | At 80% accuracy, about 1 in 5 queries still needs human correction |

**The pains, with evidence**

- **Silent, confident errors.** Omni's analysis says text-to-SQL fails quietly: the output looks right even when wrong. It names three causes: business metrics the model can't interpret, different answers to the same question across runs, and wrong joins ([Omni](https://omni.co/blog/why-text-to-sql-fails)).
- **Errors are about meaning, not syntax.** Omni's analysis puts 81.2% of failures at the schema or semantic level ([via Atlan](https://atlan.com/know/ai-agent/data-for-ai/text-to-sql-for-enterprise.md)).
- **Semantic models are expensive to maintain.** One Snowflake customer's semantic model grew past 1,255 lines of YAML, 57,000+ words and 497 synonyms, and slowed responses ([Snowflake Medium](https://medium.com/snowflake/optimizing-snowflake-cortex-analyst-performance-48ae4735c8e1)). A third-party comparison quotes 3–6 months of setup and 19.2% accuracy without the semantic model ([Querio](https://querio.ai/articles/best-text-to-sql-tools-ranked-real-accuracy)); treat that as a vendor claim.
- **Users can't see why.** Users get no view of which tables or fields produced a number; one industry write-up cites a survey where over 60% of business users don't trust NL2SQL results ([DEV](https://dev.to/arisyn/text-to-sql-penetration-tops-30-how-enterprises-build-trusted-nl2sql-deployment-frameworks-1pb0)).
- **Validation bottleneck.** Promethium, which sells a fix, estimates a typical enterprise has 200+ would-be users and only 3–5 people who can validate SQL ([Promethium](https://promethium.ai/guides/why-text-to-sql-tools-give-wrong-answers-how-to-fix/)).
- **Data can't leave the building.** Organisations that cannot send data to a cloud API are asking how far on-premise open models can go ([arXiv 2606.29733](https://arxiv.org/abs/2606.29733)). OmniSQL's authors make the same argument: local open models are cheaper and keep data private ([OmniSQL](https://arxiv.org/html/2503.02240v2)).

**What they want, in their words translated into features**

1. A number they can trust, or an honest "I can't answer that, here's why".
2. To see the tables, filters and joins behind every answer.
3. Same question, same answer, every time.
4. Works on the data as it is, without a 3-month modelling project.
5. Runs where the data lives, with no data sent out.

## What we offer: the build, the demo, the pitch

Pitch it as "the analyst that shows its work and knows when to say no", with a fully local mode for data that can't leave. Raw accuracy is table stakes; the refusal score and the visible trace are what nobody else in the room will have.

&#91;embedded content: agent architecture · 7 steps, 1 decision\]

The offline step before all this: profile each database once. Record each column's type, null rate, distinct values, and dirty tokens ("N/A", "-", mixed date formats), and index values for lookup. This profile feeds schema linking and the sanity checks.

**Mapping customer pains to features**

| Customer pain | Our feature | How we prove it on stage |
| --- | --- | --- |
| Confident wrong numbers | Candidate voting + sanity checks + refusal | TrustSQL-style reliability score vs plain model |
| Can't see why | Trace panel: tables, filters, joins, checks passed | Click any answer to show its SQL and checks |
| Different answer each time | Execution-result vote fixes the final answer | Ask the same question 3 times live |
| Months of semantic modelling | Auto-profiler builds the context in minutes | Load a new messy CSV/DB live |
| Data can't leave | Local mode: every model 8B or smaller, on device | Switch to local mode and turn Wi-Fi off |

**Two modes, because BIRD scores refusals as wrong.** Benchmark mode always returns the best-voted SQL and is what you score on BIRD. Product mode can refuse and is what the demo and the refusal metrics use. Never report a BIRD score from product mode.

**Guardrails on every query.** Open the database read-only, allow only SELECT statements, set a 10-second timeout and cap results at 1,000 rows. The Arctic model card itself warns to validate generated SQL ([model card](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)).

**Build order (cut from the bottom).** Each step must work end to end before the next starts.

1. **Hour 0–1:** Arctic-R1-7B serving with token probabilities checked; BIRD Mini-Dev SQLite loaded; read-only executor with guardrails.
2. **Hour 1–2:** Baseline: plain Arctic-R1 greedy on a fixed 150-question stratified subset, with and without hints. These are the "before" numbers.
3. **Hour 2–5:** Profiler and auto-hints; schema pruning; 4–6 samples, run, vote by result; repair on errors. Benchmark mode is now complete; rerun the 150 questions.
4. **Hour 5–8:** Deterministic checks, triage and judge on local Qwen3-8B, calibrated confidence, refusal. Product mode is complete.
5. **Hour 8–10:** Trace UI and demo on `california_schools`; blind unanswerable set scored.
6. **Hour 10–12:** Slides with real numbers; rehearse the demo twice.
7. **Cut line — only if ahead:** Jev in product mode, second writer (OmniSQL), GEPA on judge prompts, unseen Indian dataset.

**Metrics slide (measure these tonight)**

1. **Gain over the plain model**, same 150 Mini-Dev questions, benchmark mode: plain Arctic-R1 vs full agent, both with and without hints. The no-hint gain is the headline.
2. **Risk–coverage curve**, product mode: error rate on answered questions against the share of questions answered.
3. **Refusal quality** on the blind unanswerable set, scored the TrustSQL way.
4. **Latency per question** and where it runs.
5. **One honest line:** "About half of Mini-Dev labels have known errors ([Jin et al.](https://arxiv.org/pdf/2601.08778)), so we report gains, not ranks."

**Demo script (3 minutes)**

1. Open BIRD's `california_schools` database; ask "Which schools had falling enrolment?" with no hint; open the trace and the auto-generated hint.
2. Ask a question needing a dirty or coded value; show value lookup and the hint fixing it.
3. Ask an ambiguous question ("best schools"); the agent refuses and asks "best by test scores or enrolment?".
4. Ask something the data can't answer; it refuses and names the missing data.
5. Ask the same question three times; same answer every time.
6. Show the metrics slide.
7. Stretch, only if built: load an unseen messy Indian dataset live.

**Risks and fallbacks**

- **Laptop too slow.** Run the 150-question evaluation on Featherless or a rented GPU with vLLM; keep only the live demo local. Drop to 4 samples.
- **Local server returns no token probabilities.** Test in hour 1. Use llama.cpp server or vLLM; if neither works, use the judge's yes/no text plus agreement, and say so.
- **Scores much lower than papers.** Expected without hints. Present the gain, not the absolute number.
- **Running out of time.** Follow the cut line; benchmark mode plus refusal plus trace is the minimum viable story.
- **Judges call the agent "just CHESS again".** Answer with the no-hint gain and the risk–coverage curve; most teams won't have either.
- **Judges rule Jev out.** It was never in the reported numbers; switch the product demo to local.
- **Gold-label noise.** Keep two examples of wrong BIRD labels ready rather than over-tuning to them ([Jin et al.](https://arxiv.org/pdf/2601.08778)).

## Sources

- [BIRD Mini-Dev (GitHub)](https://github.com/bird-bench/mini_dev)
- [Agentar-Scale-SQL (arXiv 2509.24403)](https://arxiv.org/pdf/2509.24403)
- [Huawei DataGallery tops BIRD (Technology Magazine)](https://technologymagazine.com/news/huawei-datagallery-tops-benchmark-for-enterprise-text2sql-ai)
- [Gemini-SQL2 on BIRD (AI Weekly)](https://aiweekly.co/alerts/googles-gemini-sql2-tops-bird-text-to-sql-at-8004)
- [ReViSQL (arXiv 2603.20004)](https://arxiv.org/abs/2603.20004v1)
- [Arctic-Text2SQL-R1 (arXiv 2505.20315)](https://arxiv.org/html/2505.20315v2)
- [OmniSQL (arXiv 2503.02240)](https://arxiv.org/pdf/2503.02240)
- [CSC-SQL (arXiv 2505.13271)](https://arxiv.org/pdf/2505.13271)
- [GradeSQL (arXiv 2509.01308)](https://arxiv.org/pdf/2509.01308)
- [Progress-SQL (arXiv 2606.06825)](https://arxiv.org/pdf/2606.06825)
- [LIMIT (arXiv 2609.24186)](https://arxiv.org/pdf/2609.24186)
- [CogniSQL-R1-Zero (arXiv 2507.06013)](https://arxiv.org/pdf/2507.06013)
- [Spider 2.0 (arXiv 2411.07763)](https://www.arxiv.org/pdf/2411.07763)
- [CHESS (arXiv 2405.16755)](https://arxiv.org/pdf/2405.16755v1)
- [XiYan-SQL (arXiv 2411.08599)](https://arxiv.org/pdf/2411.08599)
- [LinkAlign (arXiv 2503.18596)](https://arxiv.org/pdf/2503.18596v4)
- [LitE-SQL (arXiv 2510.09014)](https://arxiv.org/pdf/2510.09014)
- [GEPA paper (alphaXiv 2507.19457)](https://www.alphaxiv.org/abs/2507.19457v2)
- [GEPA overview (Morph)](https://www.morphllm.com/gepa-prompt-optimization)
- [GEPA for text-to-SQL (Amity AI Labs)](https://www.amity.co/ai-labs/gepa-text-to-sql)
- [Self-improving agent with GEPA (Fireworks)](https://fireworks.ai/blog/self-improving-agent)
- [TrustSQL (arXiv 2403.15879)](https://arxiv.org/html/2403.15879v4)
- [Snowflake Cortex Analyst accuracy (Snowflake)](https://snowflake.com/?p=458942)
- [Optimizing Cortex Analyst performance (Snowflake on Medium)](https://medium.com/snowflake/optimizing-snowflake-cortex-analyst-performance-48ae4735c8e1)
- [Text-to-SQL tools ranked (Querio)](https://querio.ai/articles/best-text-to-sql-tools-ranked-real-accuracy)
- [Cortex vs Genie (Querio)](https://querio.ai/articles/snowflake-cortex-vs-databricks-genie-warehouse-ai-compared)
- [Why text-to-SQL fails (Omni)](https://omni.co/blog/why-text-to-sql-fails)
- [Text-to-SQL for enterprise (Atlan)](https://atlan.com/know/ai-agent/data-for-ai/text-to-sql-for-enterprise.md)
- [Why text-to-SQL gives wrong answers (Promethium)](https://promethium.ai/guides/why-text-to-sql-tools-give-wrong-answers-how-to-fix/)
- [Trusted NL2SQL deployment (DEV)](https://dev.to/arisyn/text-to-sql-penetration-tops-30-how-enterprises-build-trusted-nl2sql-deployment-frameworks-1pb0)
- [On-prem open LLMs on BIRD (arXiv 2606.29733)](https://arxiv.org/abs/2606.29733)
- [Jev launch and funding (Winzheng)](https://www.winzheng.com/en/article/typesafe-ai-jev-system-one-model-launch)
- [The AI model that doesn't generate text (Towards AI)](https://pub.towardsai.net/the-ai-model-that-doesnt-generate-text-is-up-to-200x-faster-9d2c6da82e51)
- [Risks of using Jev in enterprise software (Level Up Coding)](https://levelup.gitconnected.com/the-risks-of-using-jev-ai-in-enterprise-software-5d39ffc72842)
- [What is Jev AI (DigitalMarketer KR)](https://www.digitalmarketer.co.kr/class/coding-agents-basics/what-is-jev-ai)
- [Jev adoption (Pluang, via TechCrunch)](https://pluang.com/en/news-feed/jev-model-ai-tercepat-diadopsi-versel)
- [Jev early-beta report (Digg)](https://digg.com/ai/b1p67j8x)
- [JEV-as-a-Judge (arXiv 2609.26550)](https://arxiv.org/pdf/2609.26550)
- [BIRD paper review: hints vs no hints (Liner)](https://liner.com/review/can-llm-already-serve-as-a-database-interface-a-big)
- [DIVER (arXiv 2602.12064)](https://arxiv.org/html/2602.12064)
- [SEED (arXiv 2506.07423)](https://arxiv.org/abs/2506.07423v1)
- [Multi-Turn Interactions for Text-to-SQL (arXiv 2408.11062)](https://arxiv.org/pdf/2408.11062)
- [BIRD-History (arXiv 2608.29345)](https://arxiv.org/pdf/2608.29345)
- [Pervasive annotation errors in text-to-SQL benchmarks (arXiv 2601.08778)](https://arxiv.org/pdf/2601.08778)
- [What predicts correctness in text-to-SQL? (arXiv 2607.06799)](https://arxiv.org/pdf/2607.06799)
- [Agent-agnostic evaluation of SQL accuracy (arXiv 2604.28049)](https://arxiv.org/pdf/2604.28049)
- [Arctic-Text2SQL-R1-7B model card (Hugging Face)](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)
- [Arctic-Text2SQL-R1-7B GGUF quants (Hugging Face)](https://huggingface.co/mradermacher/Arctic-Text2SQL-R1-7B-GGUF/blob/main/README.md)
- [Arctic-Text2SQL-R1-7B on Featherless](https://featherless.ai/models/Snowflake/Arctic-Text2SQL-R1-7B)
- [Jev API key and access history (flaviocopes)](https://flaviocopes.com/jev-api-key/)
- [Ways to access Jev (Apidog)](https://apidog.com/blog/how-to-access-jev/)
