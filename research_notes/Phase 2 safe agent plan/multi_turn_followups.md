# Multi-turn / Conversational Text-to-SQL: Follow-ups and Evaluation (for a fixed single-turn writer)

Context: Arctic-Text2SQL-R1-7B (single-turn, fixed OmniSQL prompt we cannot edit) as SQL writer, Qwen3-8B as helper, SQLite BIRD DBs, 16 GB M4. Phase 2: "Answer three-turn follow-ups; report on a 50-conversation test set." Research done 2026-10-24.

## 1. Benchmarks and metrics: which are usable (3-turn, SQLite), and can BIRD dev DBs be reused?

### Takeaway
SParC (about 3.0 turns per conversation on average) is the closest public match to "three-turn follow-ups". It uses the Spider SQLite DBs and has the standard QM/IM metrics. CoSQL (5.2 turns) and MMSQL (6.0 turns) are longer and add clarification or unanswerable turns. BIRD-Interact is PostgreSQL-only, has 2 sub-tasks plus clarification, and is far too hard and heavy for us. No public multi-turn set runs on the BIRD dev SQLite DBs, so a BIRD-based 50-conversation set has to be built by hand. That is the credible route, since our writer is tuned on BIRD-style schemas.

### Cited Findings
- SParC: 4,298 dialogues, 12,726 turns, 3.0 average question turns, 200 DBs / 1,020 tables. CoSQL: 3,007 dialogues, 15,598 turns, 5.2 average question turns, same 200 DBs (Spider DBs) — [QDA-SQL table, arXiv 2406.10593](https://arxiv.org/pdf/2406.10593). A second table gives CoSQL as 15,498, and the CoSQL paper says 11,039 of its user utterances are SQL-convertible — [CoSQL paper](https://arxiv.org/pdf/1909.05378). The count varies by source.
- Metrics on SParC/CoSQL:
  - Question Match (QM) is per-turn correctness.
  - Interaction Match (IM) counts a conversation as correct only if every turn's SQL is correct — [CoSQL paper](https://arxiv.org/pdf/1909.05378).
  - Modern papers report each as EM (exact set match), EX (execution) and TS (test-suite) — [CoE-SQL](https://arxiv.org/html/2405.02712v1); [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- MMSQL (arXiv 2412.17867):
  - Data: built from refined CoSQL plus QDA-SQL-generated dialogues. 6,493 training dialogues, 149 test dialogues, 6.0 average question turns.
  - Question types: Answerable, Ambiguous, Unanswerable, Improper.
  - Metrics: EM, EX, IEX (interaction EX, meaning all turns correct), TDEX (EX on answerable/ambiguous averaged with type-classification accuracy), and RQS (LLM-judged response quality, 0–10) — [MMSQL](https://arxiv.org/html/2412.17867v4).
- MMSQL zero-shot test results, small models next to big ones:

  | Model | EX | IEX | TDEX |
  |---|---|---|---|
  | Llama3-8B | 66.1 | 20.1 | 64.0 |
  | SQLCoder-8B | 63.2 | 24.8 | — |
  | GPT-4 Turbo | 70.0 | 30.2 | 67.0 |
  | Mistral-7B | 13.7 | 0.7 | — |

  Per-turn EX of about 66–70% collapses to about 20–30% when every turn must be right — [MMSQL](https://arxiv.org/html/2412.17867v4).
- BIRD-Interact (ICLR 2026):
  - Built on LiveSQLBench and runs on PostgreSQL 14 in Docker, not SQLite. 600 Full + 300 Lite tasks.
  - Each task has an ambiguous priority sub-task plus a dependent follow-up sub-task, and averages about 13.6 interactions.
  - Metrics: success rate per sub-task, and a normalized reward weighted 70% priority / 30% follow-up — [BIRD-Interact](https://arxiv.org/html/2510.05318v3).
- BIRD-Interact headline numbers: GPT-5 reaches only 8.67% follow-up success in c-Interact and 17.00% in a-Interact. The best c-Interact follow-up SR is Gemini-2.5-Pro at 16.33%. Follow-ups are consistently harder than priority sub-tasks because of longer context and changed DB state. No models of 8B or smaller were evaluated — [BIRD-Interact](https://arxiv.org/html/2510.05318v3).
- The BIRD-Interact authors criticise earlier multi-turn benchmarks for relying on static transcripts and SELECT-only operations — [ICLR 2026 abstract](https://proceedings.iclr.cc/paper_files/paper/2026/hash/496b549556509bbb9770bf9d335c5800-Abstract-Conference.html).

### Inferences
- SParC dev is the best public sanity set: SQLite, about 3 turns, Spider-difficulty SQL. Filtering SParC dev to interactions with exactly 3 turns should give enough candidates for 50, but I did not count them.
- CoSQL and MMSQL test things we are not asked for, such as clarification and unanswerable turns. They are worth a footnote, not the main report.
- BIRD-Interact is not reusable. It is PostgreSQL, needs a user simulator, and frontier models score under 30%.
- The BIRD dev SQLite DBs can be reused for a self-built set. No public multi-turn BIRD set exists, so all gold SQL must be authored and verified by executing it.

### Gaps
- CHASE (Chinese cross-domain context-dependent benchmark, 2021) was not verified in this session. It is Chinese-language, so it is likely irrelevant here.
- I could not confirm the exact number of 3-turn interactions in the SParC dev set.

## 2. Methods: rewrite-to-standalone vs edit-previous-SQL vs full history. Measured accuracy, small models, fit to a fixed writer

### Takeaway
Published evidence is mixed. With GPT-3.5, naive question rewriting (ACT-SQL) does worse than simply passing all questions, and much worse than editing the previous SQL (CoE-SQL). The likely reason is that rewrite errors propagate. With a fine-tuned 7B model, rewriting and full-history were roughly comparable. In production, Snowflake ships rewrite-to-standalone in front of an unchanged pipeline, which is exactly our constraint. For a fixed single-turn writer, rewriting is the only option that does not touch the Arctic prompt. It should be done with an SQL-aware rewriter: Qwen3-8B sees the previous question(s), the previous SQL, and the schema, and must explicitly carry over filters.

### Cited Findings
- CoE-SQL (NAACL 2024, GPT-3.5-turbo-16k), dev-set EX:

  | Method | SParC QM | SParC IM | CoSQL QM | CoSQL IM |
  |---|---|---|---|---|
  | ACT-SQL (rewriting into single-turn questions) | 63.8 | 38.9 | 63.7 | 30.7 |
  | Plain baseline (schema + all questions) | 67.0 | 46.7 | 69.4 | 38.9 |
  | CoE-SQL (edit chain over the previous SQL) | 70.3 | 50.5 | 69.6 | 39.6 |

  The authors blame rewriting's weak results on error propagation, and say LLM paraphrasing "performs even worse than the baseline" — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- CoE-SQL generates each SQL from the previously generated SQL plus an AST-diff "edit chain". On SParC dev, only 7.9% of non-first turns needed SQL generated from scratch rather than edited — [CoE-SQL](https://arxiv.org/pdf/2405.02712).
- CoE-SQL with small open models is poor. On SParC dev, Vicuna-7B gets QM EX 36.0 and IM EX 19.4, so the edit-chain prompting does not transfer well to weak 7B chat models — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- CoE-SQL on the test set (EX): SParC QM 74.1 / IM 51.9, CoSQL QM 71.1 / IM 42.9, comparable to fine-tuned RASAT+PICARD (74.0/52.6, 66.3/37.4) — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- CodeS-7B fine-tuned on CoSQL with (a) full-history concatenation vs (b) GPT-based question rewriting. Each alone was competitive, and averaging the two fine-tuned models' weights beat both. I only saw the summary in a search snippet and could not fetch the numbers (MDPI returned 403) — [Future Internet 17(11):527, 2025](https://doi.org/10.3390/fi17110527).
- Rose-SQL (2026, training-free, small Qwen3):

  | Benchmark (dev EX) | Qwen3-8B baseline QM / IM | Qwen3-8B + Rose-SQL QM / IM |
  |---|---|---|
  | SParC | 66.99 / 41.94 | 78.72 / 62.56 |
  | CoSQL | 65.32 / 34.57 | 74.48 / 50.85 |

  Its pipeline includes a per-question rewrite with M-schema, dependency scoring of prior turns, and retrieval of similar trajectories — [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- Plain Qwen3-8B prompting already gets about 67% QM EX on SParC, roughly equal to GPT-3.5 CoE-SQL on per-turn accuracy, but IM is far lower: 41.9 vs 50.5 — [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- QURG and CQR-SQL are pre-LLM fine-tuned parsers. They use question rewriting as guidance (an edit matrix) or as an auxiliary consistency task, which is useful for coreference, ellipsis and focus change. QURG reports its largest gains on hard and long-turn questions — [QURG](https://cs.paperswithcode.com/paper/qurg-question-rewriting-guided-context); [CQR-SQL](https://www.alphaxiv.org/abs/2205.07686).
- MTSQL-R1 (Oct 2025) is an agentic RL method: propose, execute, verify against DB execution and dialogue memory, refine. It reports beating baselines on CoSQL/SParC, but the abstract gives no numbers — [MTSQL-R1](https://arxiv.org/abs/2510.12831).
- Snowflake Cortex Analyst:
  - Adds one LLM "summarization" agent in front of the unchanged single-turn pipeline. It rewrites the current question into a standalone one, guided by few-shot examples of both dependent follow-ups (rewrite) and independent questions (ignore history).
  - Snowflake rejected passing full history to every agent because of more tokens, more nondeterminism, and per-step degradation — [Snowflake engineering blog](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support).
- Snowflake's rewriter was Llama 3.1 70B, with 96.5% of rewrites judged self-contained by a Mistral Large 2 judge. Llama 3.1 8B was tested. About 5% of its poorly rated rewrites were history errors, for example returning the second-to-last user question instead of the current one — [Snowflake engineering blog](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support).

### Inferences
- Our constraint forces rewriting: the Arctic OmniSQL template only takes schema plus one question. The literature's main warning about rewriting is that errors propagate. So the effort should go into making the rewrite reliable and checkable, not into abandoning it.
- Recommended pipeline (cheap, fits 16 GB, sequential model loading):
  1. **Turn classifier plus rewriter (Qwen3-8B, one call, JSON output).**
     - Input: schema summary, turn history (questions plus the final SQL actually executed for each), and the current utterance.
     - Output: `{dependent: bool, standalone_question, carried_constraints: [...], changed_constraints: [...], dropped_constraints: [...]}`.
     - Use few-shot examples for each follow-up type: add filter ("now only 2023"), replace filter, change aggregation or grouping, coreference ("those schools"), ellipsis ("what about X?"), and topic shift (independent).
     - Put the previous SQL in the rewriter context. That is how filters like `County = 'Alameda'` get stated explicitly in the standalone question instead of being lost (a CoE-SQL insight applied on the rewriter side).
  2. **Arctic generates SQL from the standalone question** with the unchanged template. Beam or self-consistency, if already used for single-turn, still applies.
  3. **Carryover verifier (deterministic plus optional Qwen3):**
     - Parse the new and previous SQL with sqlglot.
     - If `dependent=true`, check that every `carried_constraint` literal or column appears in the new SQL's WHERE/HAVING, and that changed constraints changed.
     - On failure, re-prompt the rewriter with a more explicit restatement, for example listing constraints as "where X and Y and Z", and regenerate.
  4. **Optional edit fallback:** have Qwen3-8B directly edit the previous SQL (CoE-style) for simple "add or replace one filter" follow-ups. Use it when Arctic's output fails the verifier twice, or pick between the two by execution sanity (non-empty result, row count plausibly a subset when a filter was added).
- To guard against the 8B rewriter history error that Snowflake reports, check that the standalone question has meaningful token overlap with the current utterance, not the previous one. Disable Qwen3 thinking mode for latency, or keep it short.
- Don't paste history into Arctic's question field. Arctic is RL-tuned on single standalone questions, and long multi-question inputs are out of distribution. That is an inference, not tested.

### Gaps
- No published head-to-head of "LLM rewrite then strong single-turn writer" vs edit-chain using modern (2025–26) small models and BIRD-style schemas. ACT-SQL's poor result is GPT-3.5 era with an Spider-level writer. We should measure this ourselves on the 50-conversation set: rewrite-only vs rewrite plus verifier vs Qwen3 edit.
- Exact CodeS-7B rewrite vs history numbers are unavailable (paywall or 403).

## 3. Error modes

### Takeaway
The dominant failures are: filter carryover lost or wrongly kept, state-tracking errors (not replacing an old value with the new one), coreference and ellipsis resolution, topic shift misdetected as a follow-up, and compounding. Per-turn accuracy decays steadily with turn index, and requiring every turn to be right roughly halves conversation-level accuracy.

### Cited Findings
- Per-turn EX decay for plain Qwen3-8B:
  - CoSQL: 70.0 (turn 1), 63.5 (turn 2), 59.4 (turn 3), 56.1 (turn 4), 42.3 (turn >4).
  - SParC: 73.2, 64.7, 56.7 for turns 1–3.
  - With Rose-SQL's state tracking, the CoSQL decay shrinks to 78.8 → 77.0 at turn 3 — [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- Rose-SQL's case study shows three failures: the model failed to update a country filter from Germany to Japan (state tracking), used INTERSECT where EXCEPT was needed for a subtractive follow-up, and added redundant joins or guessed column names — [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- Ambiguous follow-ups, such as whether a condition from an earlier turn should carry over, are the hardest category in MMSQL. GPT-4 Turbo EX falls from 51.0% on answerable to 41.3% on ambiguous questions. Asking for clarification raised GPT-3.5 accuracy from 34.5% to 49.0% — [MMSQL](https://arxiv.org/html/2412.17867v4).
- Conversation-level collapse:
  - MMSQL: per-turn EX of about 66–70% gives IEX of about 20–30% (6-turn dialogues) — [MMSQL](https://arxiv.org/html/2412.17867v4).
  - CoE-SQL: SParC QM 70.3 vs IM 50.5 (3-turn average) — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- Error propagation from rewriting is the reason CoE-SQL gives for ACT-SQL's weaker IM — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- CQR-SQL explicitly targets coreference, ellipsis and changes in user focus as the core context phenomena — [CQR-SQL](https://www.alphaxiv.org/abs/2205.07686).
- The 8B rewriter in Snowflake's test sometimes returned the previous question instead of the current one, a history-confusion error — [Snowflake](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support).

### Inferences
- For 3 turns, per-turn EX of p gives IM of roughly p³ if errors were independent. At p=0.6 that is about 0.22. Errors are correlated (turn 1 is usually the hardest), which is why SParC IM is higher than that.
- So report both conversation-level (all 3 right) and per-turn numbers. Also separate writer errors from rewrite errors by evaluating with the gold standalone question (oracle rewrite).

### Gaps
- No public taxonomy gives frequency percentages per error type (carryover vs coreference vs shift) for LLM systems. Our own 50-conversation annotation would be novel data.

## 4. Building and scoring a credible 50-conversation x 3-turn test set

### Takeaway
Primary set: 50 hand-verified conversations on BIRD dev SQLite DBs. Seed turn 1 from BIRD dev questions with gold SQL. Write turns 2–3 from a fixed follow-up-type taxonomy, with gold SQL executed and checked, plus a gold standalone rewrite for each turn. Secondary sanity set: 50 three-turn interactions sampled from SParC dev, which makes the numbers comparable to the literature. Score per-turn EX, conversation-level all-turns EX (IM-style), per-turn-index curves, and an oracle-history vs predicted-history ablation.

### Cited Findings
- The standard scoring pair is QM (per turn) and IM (all turns correct) — [CoSQL paper](https://arxiv.org/pdf/1909.05378).
- The execution variants are EX and IEX (all turns execution-correct) — [MMSQL](https://arxiv.org/html/2412.17867v4).
- Test-suite (TS) accuracy is used to reduce false positives of single-DB EX — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- Data synthesis precedent: QDA-SQL and MMSQL generated multi-turn dialogues with LLMs from SParC/CoSQL seeds and then refined them — [MMSQL](https://arxiv.org/html/2412.17867v4); [QDA-SQL](https://arxiv.org/pdf/2406.10593).
- Snowflake evaluated the rewrite step separately with an LLM judge ("is it self-contained and does it capture all needed info") and multi-turn SQL with execution-based evaluation — [Snowflake](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support).
- BIRD-Interact reports success per sub-task plus a weighted reward, with the follow-up weighted lower (30%) — [BIRD-Interact](https://arxiv.org/html/2510.05318v3).

### Inferences (concrete protocol)
- **Construction (BIRD dev, about 11 DBs).**
  - Spread across DBs, about 4–5 conversations each.
  - Pick turn-1 seeds of easy or moderate difficulty with numeric, date or category columns.
  - Turn types, aiming for an even mix over the 100 follow-up turns:
    - (a) add filter: "now only for 2023"
    - (b) replace value: "what about Fresno instead?"
    - (c) change aggregation or ordering: "show the top 5 instead" / "the average instead"
    - (d) coreference drill-down: "list those schools' phone numbers"
    - (e) ellipsis or projection change: "and their addresses?"
    - (f) topic shift or independent question on the same DB, which tests that history is dropped
    - (g) undo or remove a constraint: "ignore the year filter"
  - Have Qwen3-8B or a larger offline model draft the follow-ups. A human then writes or edits the gold SQL, executes it, and rejects empty or 1e6-row results.
  - Store for each turn: utterance, gold standalone question, gold SQL, follow-up type, `depends_on` turn.
  - Freeze the set before tuning prompts. Keep a separate dev split (for example, 20 extra conversations) for prompt iteration so the 50 stay held out.
- **Scoring.**
  1. Per-turn EX, as set-equality of results, order-sensitive only if the gold has ORDER BY.
  2. Turn-index breakdown (T1/T2/T3).
  3. Conversation EX: all 3 correct (IM-style).
  4. Per-follow-up-type EX.
  5. Rewrite accuracy: either the predicted standalone question's SQL (via Arctic) matches gold EX, or an LLM/human judge rates it self-contained and faithful.
  6. Oracle ablations:
     - Gold standalone question fed to Arctic gives the writer-only ceiling.
     - Gold previous turns vs predicted previous turns measures compounding.
  7. Latency per turn on the M4.
  - Report 95% bootstrap CIs. With n=50 conversations (150 turns), a ±7–13 point CI is expected, so state this honestly.
- **SParC subset.** Sample 50 dev interactions with exactly 3 turns (Spider SQLite DBs). Report QM/IM EX with the official evaluator (test-suite-sql-eval) for comparison with Rose-SQL's Qwen3-8B numbers (QM EX 66.99 / IM EX 41.94 baseline).

### Gaps
- No published BIRD-based 3-turn conversational set found. Inter-annotator agreement or validation methodology must be designed by us.

## 5. Production tools (Snowflake Cortex Analyst, Databricks Genie, ThoughtSpot): how they handle follow-ups, and published weaknesses

### Takeaway
Snowflake documents a rewrite-to-standalone front agent, the same design we need. Databricks Genie keeps thread-scoped context and asks clarifying questions when a request is ambiguous, but does not publish its mechanism or accuracy. I found no technical detail for ThoughtSpot in this session.

### Cited Findings
- Snowflake Cortex Analyst: multi-turn shipped in preview on 14 Nov 2024 — [release note](https://docs.snowflake.com/release-notes/2024/other/2024-11-14-cortex-analyst).
  - API: prior turns go in a `messages` array — [Cortex Analyst docs](https://docs.snowflake.com/user-guide/snowflake-cortex/cortex-analyst).
  - Design: a rewriter agent (Llama 3.1 70B) runs in front of an unchanged pipeline, with few-shot examples for both dependent and independent questions. It reaches 96.5% self-contained rewrites. The 8B rewriter showed history confusion. There is no stated cap on history length — [Snowflake blog](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support).
- Databricks Genie:
  - Context is retained only within a chat thread, and a new chat resets it.
  - Genie may ask a clarifying question or say it can't answer.
  - Users can define terms mid-conversation.
  - — [Databricks docs](https://docs.databricks.com/aws/genie/talk-to-genie).
  - The Conversation API keeps prior-message context but does not manage retries — [Genie Conversation API](https://docs.databricks.com/aws/genie/conversation-api).

### Inferences
- Both vendors converge on two things: thread-scoped state, and either a standalone rewrite or clarification before SQL. A "clarify when ambiguous" option (MMSQL shows big gains) would be a differentiator for our demo. That is still worth doing even though the Phase 2 metric is EX, for example ask only when the rewriter's confidence is low.

### Gaps
- ThoughtSpot (Spotter) follow-up mechanism and accuracy were not researched or verified.
- Neither Snowflake nor Databricks publishes before-and-after multi-turn accuracy numbers. Snowflake's "90%+" claim is single-turn, internal, and not multi-turn specific.

## 6. Where prior work is weak / what could be better

### Takeaway
Prior work evaluates mainly on Spider-domain SParC/CoSQL with simple SQL. It rarely studies "rewrite then strong frozen single-turn writer" with modern models. It also does not verify carryover explicitly, and rarely separates rewrite errors from writer errors. Our pipeline can add a deterministic SQL-diff carryover check, oracle ablations, and a BIRD-difficulty multi-turn set, which together form a small but defensible contribution.

### Cited Findings
- Rewriting was judged harmful (ACT-SQL < baseline) only with GPT-3.5 as both rewriter and writer, on Spider-level SQL — [CoE-SQL](https://arxiv.org/html/2405.02712v1).
- BIRD-Interact argues that static-transcript, SELECT-only multi-turn benchmarks miss real interaction — [BIRD-Interact](https://proceedings.iclr.cc/paper_files/paper/2026/hash/496b549556509bbb9770bf9d335c5800-Abstract-Conference.html).
- Even frontier models get under 17% on BIRD-Interact c-Interact follow-ups, so dependent follow-ups over realistic DBs are still unsolved — [BIRD-Interact](https://arxiv.org/html/2510.05318v3).
- Small-model results are rare. CoE-SQL with Vicuna-7B collapses (IM EX 19.4). Rose-SQL shows that small Qwen3 models can reach 62.6 SParC IM EX with structured state tracking — [CoE-SQL](https://arxiv.org/html/2405.02712v1); [Rose-SQL](https://arxiv.org/html/2605.03720v1).
- MMSQL finds that existing systems often abstain passively instead of resolving ambiguity — [MMSQL](https://arxiv.org/html/2412.17867v4).

### Inferences
- Opportunities for us:
  1. Make the rewriter "SQL-grounded": it sees the previous executed SQL and emits a structured constraint list, which the SQL-diff verifier checks. This is a hybrid of the CoE-SQL edit idea and the Snowflake rewrite architecture.
  2. Report oracle-rewrite vs predicted-rewrite to attribute errors.
  3. Show the standalone rewrite to the user in the UI ("Interpreting as: ...") for transparency and quick correction. This is cheap and also reduces the impact of compounding.
  4. Use execution sanity checks between turns: a filter-add turn should return a subset of the previous result's row count.

### Gaps
- No empirical data yet on how Arctic-R1-7B behaves on rewritten follow-ups. This must be measured.
- Rose-SQL is a 2026 preprint, and its numbers have not been independently reproduced.
