# Ambiguity Detection and Clarifying Questions in Text-to-SQL Agents (local models of 8B or smaller)

Context: Arctic-Text2SQL-R1-7B samples N=5 SQL candidates. Qwen3-8B handles triage (answerable / ambiguous / data missing / not SQL, read from letter probabilities) and judges results. In Phase 1, using triage as a hard gate caused 40% false refusals, so triage is now only a soft signal. The databases are BIRD SQLite. Phase 2 requirement: "Ask a clarifying question when a question is ambiguous instead of guessing."

## Benchmarks and ambiguity taxonomies

### Takeaway
There are now several benchmarks. AMBROSIA covers scope, attachment and vagueness. AmbiQT covers lexical (column) and structural (join) ambiguity. PRACTIQ has 4 ambiguous and 4 unanswerable categories in conversational form. BIRD-Interact separates intent-level from implementation-level ambiguity and comes with a user simulator. CLARITY covers column and value ambiguity, both lexical and semantic, on Spider and BIRD. All of them show that LLMs, small ones especially, rarely notice ambiguity unprompted: they commit to one reading and are biased toward one interpretation type.

### Cited Findings
- **AMBROSIA (Saparina & Lapata, NeurIPS 2024 D&B):** Three ambiguity types: scope, attachment and vagueness. It has 846 multi-table databases across 16 domains. The breakdown is 501 scope questions, 362 attachment questions (2 interpretations and 2 gold SQLs each) and 414 vague questions with 1,239 interpretations. The databases were generated so that the ambiguity survives even with the database in view. — [AMBROSIA arXiv 2406.19073](https://arxiv.org/pdf/2406.19073)
- AMBROSIA results:
  - The best model, Llama3-70B (Prompt), reaches only about 31% recall on ambiguous questions vs about 66% on unambiguous ones. AllFound (every interpretation recovered) is 1.9% at best.
  - The recall gap between unambiguous and ambiguous questions is 21 points for OpenChat-7B, 36 for GPT-4o and 38 for Llama3-70B.
  - Models "often predict a correct SQL query for one interpretation only."
  - Models tested: OpenChat-7B, Llama3-8B/70B, CodeLlama-70B, GPT-3.5, GPT-4o. Two methods: Prompt (temperature 0.5, 5 seeds) and Beam (top-5).
  - — [AMBROSIA](https://arxiv.org/pdf/2406.19073)
- AMBROSIA per-type recall on ambiguous questions (Llama3-70B Prompt): scope 41.5, attachment 12.7, vague 35.6. AllFound: scope 2.9, attachment 0.3, vague 4.6. Attachment is the hardest type. The paper finds "a clear bias towards one interpretation type" (e.g. collective vs distributive for scope). — [AMBROSIA](https://arxiv.org/pdf/2406.19073)
- **AmbiQT (Bhaskar et al., EMNLP 2023):**
  - More than 3,000 examples, each with two plausible SQLs. The ambiguity is lexical (overlapping column or table names) and/or structural (join paths, aggregates).
  - Beam search produces token-level diversity, not logically distinct SQL, so sampling and beam often miss the second interpretation.
  - LogicalBeam (plan-based template generation plus constrained infilling, on T5-3B) is 1.5–2.5x better at getting all candidates into the top-k.
  - — [ACL Anthology 2023.emnlp-main.436](https://aclanthology.org/2023.emnlp-main.436); [GitHub testzer0/AmbiQT](https://github.com/testzer0/AmbiQT)
- **PRACTIQ (AWS, NAQL 2025):**
  - Ambiguous categories: Ambiguous SELECT Column (171), Ambiguous WHERE Column (105), Ambiguous Values Within Column (122), Ambiguous Filter Criteria (303, vague terms such as "underage").
  - Unanswerable categories: Nonexistent SELECT Column (482), Nonexistent WHERE Column (236), Nonexistent Filter Value (170), Unsupported Join (213).
  - Total: 2,812 conversations, of which 1,034 are answerable, all from Spider dev. Each conversation has 4 turns: user question, assistant clarification request, user clarification, SQL plus an NL explanation.
  - Some ambiguous items are answered directly with SQL that covers several readings at once instead of asking.
  - — [PRACTIQ arXiv 2410.11076](https://arxiv.org/html/2410.11076v1)
- PRACTIQ results:
  - 9-way category classification: Claude 3.5 Sonnet 77.4% with oracle cell values and 3 shots, 74.3% without. Most models score under 60%. Llama-3.1-70B falls below 20% with 2 or more shots because it produces repetitive output.
  - Humans score 93.75% (binary) and 88.33% (9-way).
  - Clarified-SQL execution accuracy (DIN-SQL): Llama-3.1-8B 52.5%, Llama-3.1-70B 68.6%, Claude 3.5 Sonnet 72.2%.
  - The paper does not measure over-asking or false-clarification rates.
  - — [PRACTIQ](https://arxiv.org/html/2410.11076v1)
- **BIRD-Interact (ICLR 2026, arXiv 2510.05318):**
  - Size: 600 tasks; the Lite split has 300.
  - Injected ambiguity: user-query intent-level (vague wording, e.g. "elderly people") and implementation-level (e.g. unspecified decimal precision); knowledge ambiguity (one-shot removal, broken knowledge chains); environmental (NULLs in critical fields).
  - Each injected ambiguity is paired with a ground-truth SQL snippet, which is what the simulator uses to answer.
  - — [BIRD-Interact](https://arxiv.org/html/2510.05318v3)
- **CLARITY (arXiv 2604.22313, 2026):**
  - Covers column and value ambiguity (lexical or semantic) plus unanswerability. Items are uni-facet or multi-facet.
  - Size: Spider 6,392 single-turn and 12,098 multi-turn instances; BIRD 3,487 single-turn and 7,171 multi-turn.
  - — [CLARITY](https://arxiv.org/html/2604.22313v1)
- **"Two Surfaces of Ambiguity" (VLDB 2026 AIDB workshop):** Uses BIRD-Interact-Lite, which has 1,550 ground-truth ambiguity terms across 15 typed categories. Examples: vague (111, e.g. "recent"), lexical (15), syntactic (4), sort direction unspecified (130), rounding unspecified (115), plus null, join, divide-by-zero and knowledge-linking categories. — [Liu & Erdelt, AIDB'26](https://vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
- **Query Carefully (arXiv 2512.21345):** OncoMX-NAQ has 80 unanswerable questions in 8 categories: Non-SQL, columns missing, values missing, out-of-domain, and ambiguous by column, value, context or operator. — [Query Carefully](https://arxiv.org/html/2512.21345)
- **CLAMBER (ACL 2024, general LLM clarification, about 12K examples):** CoT and few-shot prompting "may result in overconfidence in LLMs and yield only marginal enhancements in identifying ambiguity." LLMs are also poor at generating high-quality clarifying questions. — [CLAMBER arXiv 2405.12063](https://arxiv.org/abs/2405.12063v2)
- **TACO (arXiv 2606.14201):** An open-domain benchmark with ambiguous and cross-database queries. I could not read its details. — [TACO](https://arxiv.org/pdf/2606.14201)

### Inferences
- For BIRD-style SQLite databases, the ambiguity types to target are:
  - column ambiguity (two plausible columns or tables);
  - value ambiguity (a fuzzy match to several cell values);
  - vague filter criteria ("recent", "top", "elderly", "high-rated") and a missing time range;
  - aggregation scope and attachment ("for each X" vs overall);
  - implementation choices (rounding, sort direction, NULL handling, join type, ties).

  The implementation-level choices are mostly better handled by a stated default than by asking.
- BIRD's `evidence` field already settles many vague terms. When evidence is present, the bar for asking should be higher.

### Gaps
- I could not find AmbigNLG details in a text-to-SQL context, or the TriageSQL numbers (TriageSQL is a 2020 question-intent dataset). I did not verify them, so none are included.
- I did not verify that AMBROSIA's databases ship as SQLite files.

## Detection methods and measured precision/recall; what works for small models; avoiding over-asking

### Takeaway
No single detector is enough. Introspection (prompting an LLM to flag ambiguous terms) catches intent-level ambiguity: vague terms, unclear schema references. Disagreement among sampled SQL candidates catches implementation-level choices: null handling, join type. The union of the two raises recall by at least 6 points for 3 LLM calls.

LLM classifiers tend to over-flag. AmbiSQL-style detectors have near-100% detection accuracy but only 5–60% localization accuracy. Asking is only worth it when the readings produce different results on the actual database. Execution-verified pruning of duplicate interpretations is the main way to avoid over-asking.

### Cited Findings
- **Two Surfaces (introspection vs sampling):**
  - Introspection catches "vague terms, missing formulas, and unclear schema references." Sampling "exposes choices the model silently commits to during SQL generation, such as null handling and join type."
  - On null and join ambiguities, sampling beats introspection "often by roughly a factor of two."
  - The union Si-1 ∪ Mcs-1 costs 3 LLM calls. It raises recall by at least 6 points over either method on 3 open models (GLM-4.5-Air, MiniMax-M2.5, Qwen3.5-122B) and by 4.8 points on Gemini 3.1 Flash Lite. It also improves BIRD-Interact normalized reward by about 3–7 points and AMBROSIA AllFound by 10.9 points.
  - Single-method recall is about 60–66%. For example, GLM: Si-1 61.5, Mcs-1 59.8, Mcs-10 61.7.
  - — [AIDB'26](https://vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
- Two Surfaces, further findings:
  - The sampled SQLs "visibly disagree on rounding in 44% of decimal-annotated tasks, yet 87% of the misses on those tasks emit no rounding-related question at all." The disagreement is detected but never becomes a question, so a structured diff-to-question step is needed.
  - Clustering samples by AST with a difference summary was "recall-neutral at best" for 122B-class models. The authors leave open whether it helps weaker models.
  - Ten samples of introspection (Si-10) still trail the 3-call union on both recall and precision.
  - — [AIDB'26](https://vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
- **AIR (arXiv 2610.24248), execution-verified interpretations:**
  - An Anchor agent proposes the most likely reading with a confidence score. An Adversary agent looks for an alternative reading, gated by an anchor threshold of 0.95 and an adversary threshold of 0.5. Each reading is compiled to SQL, and readings whose result sets are identical are pruned.
  - Only surviving readings become a contrastive question that lists each reading with its row count.
  - AMBROSIA, schema-only: F1 0.679 vs 0.618 for IntentRL. Perfect-match 46.4% vs 23.2%. AIR averages 1.76 outputs per query vs 5.00 for IntentRL. Queries with extra outputs: 33.0% vs 76.4%.
  - Adversary-threshold sweep: precision 0.705 / recall 0.827 at threshold 0, and precision 0.862 / recall 0.722 at threshold 1.0. This is a precision/recall knob for asking.
  - Models tested include Claude Sonnet 4.5, Gemma 4 26B-A4B and gpt-oss-20b. About 40 s per query.
  - — [AIR](https://arxiv.org/html/2610.24248)
- **AmbiSQL (arXiv 2508.15276):** An LLM with in-context learning analyzes the question against the schema, classifies ambiguities with a taxonomy and generates a multiple-choice question for each one. It reports 87.2% ambiguity-detection precision (the authors' own figure). — [AmbiSQL](https://arxiv.org/abs/2508.15276)
- **CLARITY's evaluation of AmbiSQL:**
  - Detection accuracy is 96.8–100%, but match accuracy (did it localize the right schema elements?) is 50–62% on uni-facet column ambiguity, 5–20% on multi-facet column ambiguity, and 22–41% on value ambiguity.
  - In other words, detectors flag "ambiguous" almost always but often point to the wrong thing.
  - CLARITY reports no over-clarification rate.
  - — [CLARITY](https://arxiv.org/html/2604.22313v1)
- **Query Carefully (llama3.3-70B, prompting only):**
  - Column-ambiguous questions reach at most 0.3 detection accuracy, the weakest category. Value ambiguity does better, and operator ambiguity reaches 0.9.
  - Overall unanswerable-question accuracy is 0.37 with rules only and about 0.8 with balanced few-shot (answerable plus unanswerable examples).
  - Answerable examples alone helped detection more than unanswerable examples alone.
  - The text-to-SQL model often "generated SQL referencing one fitting column" without noticing the ambiguity.
  - — [Query Carefully](https://arxiv.org/html/2512.21345)
- **Expected Information Gain (Qiu et al., arXiv 2507.06467):**
  - Keeps a distribution over candidate SQLs, treats SQL branching decisions as variables, and asks about the decision with the highest expected entropy reduction.
  - Stops asking when a candidate passes a confidence threshold.
  - Spider execution accuracy: 76.6% vs 73.4% (plain information gain), 72.1% (max probability) and 70.1% (random). Exact match: 38.3% vs 21.0%.
  - — [EIG arXiv 2507.06467](https://arxiv.org/pdf/2507.06467)
- **Over-asking:** "Beyond Correctness" (arXiv 2610.02739) reports that forcing agents to ask more questions improves execution accuracy. However, the ambiguities sit in early interactions, so brute-force questioning is inefficient, and a correct result does not prove the ambiguity was resolved. Source: search snippet only; I did not fetch the full paper. — [arXiv 2610.02739](https://arxiv.org/html/2610.02739)
- Soma-SQL (arXiv 2606.11424) resolves candidate disagreements by probing the database before asking the user. Source: search snippet only. — [Soma-SQL](https://arxiv.org/html/2606.11424v1)
- **AMBROSIA on precision:** When a model outputs several SQLs and only one is correct, precision can drop to about 0.1. Even GPT-4o "predicts SQL queries when it should not" on unambiguous questions. This is the multi-output analogue of over-asking. — [AMBROSIA](https://arxiv.org/pdf/2406.19073)

### Inferences (applied to our stack)
- **Disagreement alone will over-ask on BIRD.** On hard but answerable questions, a 7B model's N=5 samples also diverge because some candidates are simply wrong. These are model errors, not ambiguity. This is the same failure mode as the 40% false refusals from Phase 1 triage. Divergence is necessary but not sufficient. The ask gate should require all of:
  1. at least 2 execution clusters that each hold at least 2 of the 5 votes, or a top-cluster share of 0.6 or less;
  2. both cluster representatives execute without error and return non-empty results;
  3. the results differ materially (not just row order, rounding or column aliases);
  4. Qwen3-8B judges both SQLs to be "reasonable readings of the question" (letter probability), and the difference maps to a span in the question (a column, value, filter or scope choice).
- **Use the Qwen3 triage "ambiguous" probability only as a prior.** It raises or lowers the cluster threshold and never asks on its own. PRACTIQ and Query Carefully show that small models classify ambiguity categories poorly, and column ambiguity is the hardest.
- **Use cheap schema and value signals to boost recall:**
  - The question token fuzzy-matches 2 or more columns (via name/description embeddings), or a value appears in several columns or matches several distinct cell values. These map to PRACTIQ's column, WHERE-column and value categories.
  - The question asks for an aggregate or a top-k, a date column exists, there is no time constraint, and the BIRD evidence does not settle it.
- **Middle tier: answer and flag.** When divergence exists but is low-stakes (rounding, sort ties, NULL handling), answer with the majority cluster and state the assumption ("Assumed X; reply 'Y' for the other reading"). This avoids the cost of an unnecessary ask while staying transparent.
- **Raise effective N cheaply if divergence is borderline.** Five samples at τ>0 may not surface the second reading (AmbiQT). Add one "alternative interpretation" call, where Qwen or Arctic is told "write SQL for a different plausible reading than this one." This is AIR's adversary step, cheap at 8B.

### Gaps
- I found no published precision or false-ask rate for ambiguity detection using ≤8B models on BIRD specifically. We need to measure this ourselves.
- I found no published comparison of conformal or selective-prediction thresholds for ask-vs-answer in text-to-SQL. The AIR threshold sweep and the EIG stopping threshold are the closest analogues.

## Clarifying-question generation and resolution

### Takeaway
The best-supported format is a contrastive multiple-choice question built from the surviving interpretations. Each option is a one-line NL reading with a data preview or row count, plus "something else." Selecting an option maps directly to an already-executed SQL, so resolution needs no regeneration.

### Cited Findings
- AIR's Synthesizer lists each surviving reading with its execution results and row count, then asks which was meant. Clarifications are "grounded in actual data differences." — [AIR](https://arxiv.org/html/2610.24248)
- AmbiSQL produces a multiple-choice clarification per detected ambiguity. — [AmbiSQL](https://arxiv.org/abs/2508.15276)
- EIG asks about the single branching decision with the highest information gain, one targeted question at a time, and keeps going until one candidate is confident. — [EIG](https://arxiv.org/pdf/2507.06467)
- Snowflake Cortex Analyst returns a `suggestions` content type instead of SQL when "the user question was ambiguous." Example: "Your question is ambiguous, here are some alternatives: which company had the most revenue? / which company placed the most orders?" `suggestions` is mutually exclusive with `sql`. — [Cortex Analyst REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/rest-api)
- In Databricks Genie, clarification is author-configured. Each instruction gives a trigger condition, the missing details, the required action, and an example question such as "Please specify the time range and sales channel you are looking for." Databricks advises putting these instructions at the end of the general instructions, and warns that too many instructions reduce effectiveness. — [Databricks Genie best practices](https://docs.databricks.com/aws/en/genie-agents/best-practices)
- PRACTIQ dialogues take the form: question, clarification request, user reply, clarified SQL plus an NL explanation of the results. Human ratings of these responses on factuality, helpfulness and naturalness are 1.15, 1.41 and 1.57 on a 1–5 scale where lower is better. — [PRACTIQ](https://arxiv.org/html/2410.11076v1)
- BIRD-Interact found that communication itself is a weakness. GPT-5 underperformed in c-Interact despite strong SQL ability, and improved when given another model's ambiguity-resolution history ("memory grafting"). — [BIRD-Interact](https://arxiv.org/html/2510.05318v3)
- CLAMBER found that LLM-generated clarifying questions are low quality because of "a lack of conflict resolution." — [CLAMBER](https://arxiv.org/abs/2405.12063v2)

### Inferences (concrete design)
1. Take the representatives of the top 2–3 execution clusters (SQL A, SQL B).
2. Qwen3-8B gets a templated contrastive prompt: "These two SQLs answer the question differently. In ≤15 words each, name the one choice that differs (column/filter/time range/grouping)." This is constrained free-form text inside a fixed template.
3. Render the question with a fixed skeleton: "Your question can mean: (A) … [e.g. 12 rows, top: X] (B) … [3 rows, top: Y] (C) something else. Which one?" Using a template avoids the CLAMBER-style quality problems that free-form 8B questions would have.
4. Ask at most one clarification per question, about the highest-impact difference (largest result difference, i.e. a crude information-gain proxy). If the user picks A or B, return that cluster's already-executed result. If the user types free text, append "Clarification: …" to the question, regenerate N=5 and do not ask again.
5. For missing-time-range and vague-threshold cases (no SQL divergence, schema flag only), use a slot template: "Which time period? (all time / last year in data: 2023 / custom)". Pre-fill the options from MIN/MAX of the date column, which is cheap to query.

### Gaps
- I found no head-to-head user study of templated vs free-form clarification for text-to-SQL. The preference for templates here comes from my inference about small models.

## Evaluation: precision/recall of asking, accuracy after clarification, simulated users

### Takeaway
Two families of evaluation exist:
- Static multi-interpretation coverage: AMBROSIA recall/precision/AllFound; CLARITY detection accuracy plus match accuracy plus strict/lenient exact match.
- Interactive evaluation with a simulated user: BIRD-Interact success rate and normalized reward under an asking budget, with a function-driven simulator that refuses inappropriate requests.

None of them cleanly reports a false-ask rate on answerable questions, and that is the number we most need.

### Cited Findings
- AMBROSIA: recall on ambiguous questions is the primary metric, with AllFound = 100% recall per question. For unambiguous questions, recall equals execution accuracy. — [AMBROSIA](https://arxiv.org/pdf/2406.19073)
- CLARITY: Detection Accuracy and Match Accuracy (correct schema elements localized). For single-turn, Strict EM requires every interpretation and Lenient EM requires at least one. For multi-turn, execution accuracy after the conversation. Unanswerable questions must output null. — [CLARITY](https://arxiv.org/html/2604.22313v1)
- BIRD-Interact simulator design:
  - Stage 1: an LLM maps each agent question to AMB() (annotated ambiguity), LOC() (reasonable but unannotated, answered via AST retrieval) or UNA() (inappropriate, e.g. fishing for the answer, rejected).
  - Stage 2: the simulator answers from the gold SQL.
  - Baseline simulators failed on unanswerable requests up to 67.4% of the time vs 2.7% for the function-driven design (UserSim-Guard).
  - — [BIRD-Interact](https://arxiv.org/html/2510.05318v3); [UserSim-Guard](https://huggingface.co/datasets/birdsql/UserSim-Guard/blob/main/README.md)
- BIRD-Interact metrics and budgets:
  - Success rate per sub-task and normalized reward (70% priority sub-task, 30% follow-up).
  - c-Interact caps clarification turns at m_amb + patience (3). a-Interact uses a cost budget B = 6 + 2·m_amb + 2·patience, where asking the user costs ≥2 and environment probes cost ≤1.
  - Best results: c-Interact reward 20.92 (Gemini-2.5-Pro); a-Interact 25.52 (GPT-5).
  - Performance rises monotonically with more interaction turns (the "ITS law").
  - — [BIRD-Interact](https://arxiv.org/html/2510.05318v3)
- Two Surfaces scores each clarification question with the simulator encoder. recall = matched ground-truth terms / total. precision = (matched + valid-but-unannotated) / questions asked. This gives an operational "ask precision". — [AIDB'26](https://vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
- A 2026 study of chain ambiguity and intent drift calls LLM user simulators an "imperfect proxy." Source: search snippet. — [arXiv 2608.29543](https://arxiv.org/pdf/2608.29543)

### Inferences (concrete evaluation plan for our hackathon)
- **Eval set (SQLite, runnable locally):**
  - (a) About 150 answerable BIRD dev questions (negatives), stratified by difficulty. These are the critical set for false asks.
  - (b) About 100 synthetic ambiguous variants of BIRD dev questions, made with PRACTIQ-style edits: drop the time range, replace a column name with a term matching 2 columns, make a filter vague, strip the BIRD `evidence` that defines a term. Each gets 2 gold SQLs, one per reading.
  - (c) An AmbiQT and/or AMBROSIA sample (Spider-style SQLite) of about 100, for external validity.
  - (d) The existing column-removed and unanswerable set from Phase 1, so ambiguous vs data-missing confusion can be checked.
- **Metrics:**
  - Ask-precision and ask-recall on (a)+(b)+(c).
  - False-ask rate on (a). Target ≤10%, versus the 40% false-refusal baseline.
  - Coverage: does the gold reading appear among the offered options? This is AMBROSIA OneFound restricted to offered options.
  - Execution accuracy after one simulated clarification.
  - End-to-end utility = EX − λ·(asks on answerable), with λ around 0.3–0.5. Also report the asks-per-question budget.
  - Confusion matrix of {answer, answer+flag, ask, refuse} vs {answerable, ambiguous, missing}.
- **Simulated user:** Qwen3-8B is given the gold SQL/reading and the options. It must pick an option or give a one-line free-text answer, and it must not reveal SQL or answers. This mirrors BIRD-Interact's AMB/LOC/UNA design. Spot-check 30 dialogues by hand, because simulators are imperfect.
- **Ablations:**
  - never ask
  - Qwen triage only
  - divergence only
  - divergence + Qwen judge
  - divergence + Qwen judge + schema/time flags
  - each of the above with and without the "alternative-reading" extra sample

  Sweep the cluster-share threshold and plot the ask-precision/recall curve (as in AIR's threshold sweep), then pick the operating point.

### Gaps
- No public benchmark gives a ready-made "false clarification on answerable BIRD questions" number to compare against. Our own set (a) is the baseline.

## Production systems and their weaknesses

### Takeaway
Cortex Analyst refuses ambiguous questions and returns suggested rephrasings instead of SQL. Genie asks clarifying questions mainly where authors have written explicit trigger rules. Neither publishes accuracy for ambiguity detection. Both rely on curated semantic models, verified queries and instructions rather than general detection.

### Cited Findings
- Cortex Analyst: `suggestions` are returned only for ambiguous questions and are mutually exclusive with SQL. `confidence.verified_query_used` reports whether a verified query was matched. — [Snowflake REST API docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/rest-api)
- Cortex Analyst limitations from the docs: it "doesn't have access to results from previous SQL queries" and "might struggle to interpret the follow-up questions" in long or shifting conversations. The advice is to "reset the conversation." — [Cortex Analyst docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- Genie: clarification is configured through text instructions (trigger, missing details, action, example question). Databricks also recommends example SQL for common ambiguous prompts and treats text instructions as a last resort after SQL expressions and examples. — [Databricks docs](https://docs.databricks.com/aws/en/genie-agents/best-practices)
- A third-party Spider 2.0 write-up reports that Cortex Analyst refusals came from missing join metadata (24) and genuine inability to answer (2), with zero clarification requests. This is a secondary source and unverified. — [Agentic Fabriq blog](https://www.agenticfabriq.com/blog/cortex-analyst-vs-genie-accuracy)

### Inferences
- The weaknesses are a binary choice between refusing and suggesting (Cortex), and hand-authored trigger rules that do not generalize (Genie). Neither shows the user the actual data difference between readings. Our design can improve on both by asking contrastive, execution-grounded questions with result previews, and by answering-and-flagging for low-stakes divergence.

### Gaps
- I found no reliable primary source on ThoughtSpot Spotter's clarification behavior, and no vendor-published metrics on false clarification rates.

## Where prior work is weak / how to do better (summary)

### Takeaway
Prior work focuses on recall: catching ambiguity, listing interpretations. It rarely measures the cost of asking on answerable questions. It mostly uses models of 70B or more, or proprietary ones. It also tends to generate questions from perceived rather than execution-verified ambiguity. A small-model system can be competitive by putting execution grounding and a calibrated, corroborated ask gate first.

### Cited Findings
- No false-ask rates are reported in PRACTIQ or CLARITY. — [PRACTIQ](https://arxiv.org/html/2410.11076v1); [CLARITY](https://arxiv.org/html/2604.22313v1)
- Detection is close to 100% while localization accuracy is 5–62%, so detectors are trigger-happy. — [CLARITY](https://arxiv.org/html/2604.22313v1)
- Other approaches "generate clarifications from perceived ambiguity" without checking whether the interpretations return different data. AIR's execution pruning cuts extra outputs from 76% to 33% of queries. — [AIR](https://arxiv.org/html/2610.24248)
- Disagreement often fails to become a question: 87% of rounding misses produced no question even though the samples disagreed. — [AIDB'26](https://vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
- CoT and few-shot make LLMs overconfident about ambiguity. — [CLAMBER](https://arxiv.org/abs/2405.12063v2)

### Inferences
- Where we can do better:
  - Execution-cluster gating plus an 8B "are both readings reasonable?" judge. This separates ambiguity from model error, which is the key weakness for small models.
  - A deterministic diff-to-question template, so detected divergence always becomes a question.
  - A 3-way policy of answer / answer+flag / ask, instead of a binary choice.
  - Reporting false-ask rate and utility, not just recall.
- **Pitch line:** "We only ask when the database itself says the readings differ, and we show you the difference."

### Gaps
- None of these improvements have been validated yet. They must be measured with the evaluation plan above.
