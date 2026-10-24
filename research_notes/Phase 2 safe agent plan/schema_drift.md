# Schema drift robustness for the AI-02 text-to-SQL agent (renames and splits, no retraining)

Scope: Phase 2 requirement, "Recover after tables are renamed or split, without retraining; report accuracy before and after." Agent: Arctic-Text2SQL-R1-7B writer, Qwen3-8B helper, linker + profiler + per-DB rules file, SQLite BIRD DBs, 16 GB M4.

## Q1. Benchmarks and papers: what accuracy drops are reported for renames vs splits/merges?

### Takeaway
Renames cost little: about 1–6 EX points for modern LLMs in EvoSchema on BIRD. Table splits, merges and added tables cost far more: about 15–20 EX points for 7–8B models. In the older Dr.Spider work, synonym and abbreviation renames cost 10–17 points, because those models (2023 encoder-decoders) relied on string matching. Structural changes (split, merge, normalize vs. denormalize) are the hard part. Simple renames are mostly a cache and staleness problem.

### Cited Findings
**EvoSchema (Zhang et al., PVLDB vol. 18, 2025; arXiv 2603.10697), the closest match to our task, built on BIRD**
- It has 10 perturbation types. Column-level: add, remove, rename, split, merge. Table-level: add, remove, rename, split, merge. The question stays fixed and only the schema and gold SQL change — [arXiv HTML](https://arxiv.org/html/2603.10697); [VLDB](https://www.vldb.org/pvldb/vol18/p3655-zhang.pdf)
- How the gold SQL was rewritten:
  - Renames: names were string-updated.
  - Table split/merge: GPT-4 revised the gold SQL from the table/column mapping and JOIN paths, then the eval data was checked by hand.
  - Column split/merge on dev: rewritten by hand.
  - Removing a table or column used by the gold SQL: the gold answer becomes "insufficient information" — [arXiv HTML](https://arxiv.org/html/2603.10697)
- Execution accuracy, original → perturbed, models without perturbation training — [arXiv HTML](https://arxiv.org/html/2603.10697):
  - Code Llama-7B: original 58. Rename Columns 54, Rename Tables 56, Split Tables 38, Merge Tables 43, Add Tables 40, Split Columns 41.
  - Mistral-7B: original 59. Rename Columns 55, Rename Tables 55, Split Tables 36, Merge Tables 45, Add Tables 39.
  - Llama 3-8B: original 55. Rename Columns 49, Rename Tables 52, Split Tables 40, Merge Tables 42.
  - SQLCoder-7B: original 58. Rename Columns 56, Rename Tables 56, Split Tables 43, Merge Tables 47.
  - GPT-4 (prompted, no training): original 47. Rename Columns 45, Rename Tables 47, Split Tables 47, Merge Tables 45. A strong general model is nearly flat; the 7B fine-tunes are not.
- Diagnosis from Code Llama's Table Match F1:
  - Original 89.77. Add Tables 57.88, Split Tables 71.99, Merge Tables 85.29.
  - Column F1 for Merge Tables falls from 80.66 to 65.56.
  - In other words, splits and added tables break table selection, while merges break column selection — [arXiv HTML](https://arxiv.org/html/2603.10697)
- The paper's fix is training on perturbed schemas, which recovers split tables by about 6–12 points. It is out of scope for us (no retraining), but it shows the gap is structural — [arXiv HTML](https://arxiv.org/html/2603.10697)

**Dr.Spider (Chang et al., ICLR 2023; Spider dev, 17 perturbation sets; code in awslabs/diagnostic-robustness-text-to-sql)**
- DB perturbations:
  - Schema-synonym: rename columns to synonyms, e.g. country→nation. Only examples whose SQL mentions a renamed column are kept.
  - Schema-abbreviation: rename columns to abbreviations.
  - DBcontent-equivalence: change how content is represented — [paper PDF](https://arxiv.org/pdf/2301.08881); [search summary](https://arxiv.org/pdf/2301.08881)
- Execution accuracy, pre → post, from Table 3 — [paper PDF](https://arxiv.org/pdf/2301.08881):
  - PICARD (best model):
    - Schema-synonym: 73.0 → 56.5 (n=2,619)
    - Schema-abbreviation: 74.9 → 64.7 (n=2,853)
    - DBcontent-equivalence: 88.7 → 43.7 (n=382)
    - DB average: 78.9 → 55.0
  - RAT-SQL schema-synonym: 65.7 → 45.4. T5-3B LK abbreviation: 69.5 → 53.3.
  - Even PICARD loses 30.0% relative on DB perturbations, and 50.7% on DBcontent-equivalence — [paper PDF](https://arxiv.org/pdf/2301.08881)
- Later LLM numbers on DB-Schema-synonym EX: PICARD 56.5, CodeX 62.0, RESDSQL-3B 63.3, RESDSQL-3B+NatSQL 68.3 — [RESDSQL repo](https://github.com/ruckbreasoning/resdsql) (secondary, not re-verified)

**Spider-Syn (Gan et al., ACL 2021)**
- Synonyms are put into the question rather than the schema. Accuracy "dramatically drops" once the exact question-to-schema word match is gone — [arXiv 2106.01065](https://arxiv.org/pdf/2106.01065)
- RAT-SQL+BERT reportedly drops from 69.7 to 48.2 — [secondary review](https://liner.com/review/towards-robustness-texttosql-models-against-synonym-substitution) (unverified against the paper table)

**ADVETA (Pi et al., ACL 2022)**
- Adversarial Table Perturbation comes in two forms:
  - RPL: replace column names with natural, realistic alternatives.
  - ADD: add confusable columns.
- The motivation is that "table maintainers may rename columns due to business demands." All SOTA models drop dramatically — [MSR page](https://www.microsoft.com/en-us/research/?p=844144); [ar5iv](https://ar5iv.labs.arxiv.org/html/2212.09994)
- An aggregator lists Spider-ADVETA EM of 35.8 for RPL and 50.6 for ADD — [WizWand](https://www.wizwand.com/paper/68fa6e3a1e209131cea3e7d2) (unverified; the baseline model is unclear)

**SNAILS (Luoma & Kumar, SIGMOD 2025)**
- Less natural (cryptic, abbreviated) identifiers lower accuracy. Smaller and open models gain up to about 20% EX when names are made natural.
- Its proposed fix is "natural views" over the existing schema, not renaming the DB itself — [summary](https://rmarcus.info/dbscholar/papers/hd2b322bc9536f3a9); [ACM DOI](https://dl.acm.org/doi/pdf/10.1145/3709727) (full text blocked, 403)

**Same Data, Different Schemas (arXiv 2605.25838, 2026)**
- Ten logically equivalent schemas: inheritance as STI/CTI/concrete tables, JSON arrays vs. child tables, FK vs. junction tables.
- Frontier LLMs agree with themselves across schemas only 34–89% of the time. Examples: Media domain Gemini 81.6%, Claude 67.8%, ChatGPT 43.6%, DeepSeek 33.9%.
- Common failures:
  - Inner vs. LEFT JOIN when a relationship is absent
  - Forgetting the type filter on merged tables
  - A subtype treated as the full set
  - NULL foreign keys
- Fix: put the E/R model plus a text description of the design choices in the prompt. This improved all models — [arXiv HTML](https://arxiv.org/html/2605.25838v1)

**The Case for Text-to-SQL Friendly Logical Database Design (Zhang, Miao, Wang, arXiv 2606.03145, June 2026)**
- Three semantics-preserving model-facing transforms:
  - +A (abstraction): views that materialize recurring join paths
  - +P (partitioning): prune irrelevant tables
  - +R (renaming): descriptive identifiers, e.g. molecule.label → Chem_Molecules.carcinogenic_flag
- Up to +4.2% EX on BIRD-Union and Spider-Union. +A+P+R combined consistently improves results. Renaming also works zero-shot — [arXiv PDF](https://arxiv.org/pdf/2606.03145)

**Gaps in coverage**
- Spider 2.0 and BIRD-Interact concern enterprise or interactive complexity, not schema drift. No rename or split numbers were found for them — [BIRD-INTERACT](https://arxiv.org/pdf/2510.05318).

### Inferences
- Expect very different outcomes by perturbation type for our 7B agent:
  - Table rename: small drop, if the schema is re-read.
  - Column rename to an abbreviation: moderate drop. The writer loses lexical match, and the BIRD evidence hints break.
  - Vertical split: large drop, because a new JOIN is needed.
  - Horizontal split by year: large drop, because UNION ALL or the right partition is needed.
- Arctic-R1-7B is a fine-tune much like the EvoSchema 7B models. Its split/merge drops will probably look more like Code Llama's 15–20 points than GPT-4's 0–2.
- The biggest real-world risk for our agent is not the model. It is stale caches and rules that point at old names, which give hard "no such table" errors or, worse, silently wrong hints.

### Gaps
- The exact ADVETA and Spider-Syn table numbers were not verified from the primary PDFs.
- No paper found reports horizontal splits (by year or partition) specifically. EvoSchema's "split tables" is vertical or per-attribute. Our horizontal-split condition would be new.
- No published numbers exist for Arctic-Text2SQL-R1 under schema perturbation.

## Q2. Recovery approaches without retraining

### Takeaway
The proven no-retraining tools are:
- Re-introspect the live schema.
- Expose a model-facing compatibility or "natural" view layer.
- Retrieve over name plus description plus values, not name alone.
- Use execution-error feedback loops.

The strongest option for us is a **schema diff → migration map** that rewrites both the cached artifacts (rules, profiles, few-shots, evidence) and, optionally, the generated SQL. This is deterministic and can be checked, so it does not depend on the 7B model "figuring it out".

### Cited Findings
- **SQLite already carries renames into views and triggers.**
  - Since 3.25/3.26, `ALTER TABLE ... RENAME TO` rewrites references "within trigger bodies and view definitions", and FKs are always converted unless `legacy_alter_table=ON`.
  - `RENAME COLUMN` updates "indexes, triggers, and views". It fails if the rename would create an ambiguity — [SQLite docs](https://www.sqlite.org/lang_altertable.html)
  - Consequence: compatibility views must be created after the rename, under the old names. Views created before the rename get rewritten to the new names.
- **Natural/compatibility views.** SNAILS recommends virtual natural views instead of renaming production schemas — [SNAILS summary](https://rmarcus.info/dbscholar/papers/hd2b322bc9536f3a9). The +A abstraction views (pre-joined paths) and +R renaming give up to +4.2% EX zero-shot — [arXiv 2606.03145](https://arxiv.org/pdf/2606.03145).
- **E/R and design-choice descriptions in the prompt** reduce cross-schema disagreement for every model tested — [arXiv 2605.25838](https://arxiv.org/html/2605.25838v1)
- **Execution-error self-correction.**
  - LitE-SQL: "no such column" is the most common execution error, and it "decreases substantially after correction". The first correction pass gives the largest BIRD gain, with diminishing returns after that — [LitE-SQL](https://arxiv.org/pdf/2510.09014).
  - Self-correction without execution feedback gives only about 1–3 points (DIN-SQL: 67.3 → 69.9). Correction with execution or tool feedback helps reliably — [DIN-SQL](https://arxiv.org/pdf/2304.11015).
  - DIVER feeds non-existent table/column exceptions back to the LLM — [DIVER](https://arxiv.org/pdf/2602.12064).
- **Retrieval-based schema linking** raises linking recall. Dynamic-SQL raises strict schema-linking recall from 72.63% to 90.66% on BIRD, at 63.23% EX — [search summary of Dynamic-SQL](https://arxiv.org/pdf/2603.13390).
  - Caveat: for strong LLMs, schema linking can reduce EX, so RSL-SQL uses bidirectional linking — [RSL-SQL](https://arxiv.org/html/2411.00073v2).
- **Abbreviation expansion.** Columbo expands abbreviated column names in tabular data. It is a candidate approach for re-deriving natural descriptions of `cname`-style columns — [Columbo arXiv 2508.09403](https://arxiv.org/html/2508.09403v3) (not read in depth).
- **Solid-SQL** uses schema-linking-enhanced in-context learning for robustness. Its focus is perturbed questions, not perturbed schemas — [COLING 2025](https://aclanthology.org/2025.coling-main.654.pdf).

### Inferences: a recommended recovery stack for our agent, cheapest first
1. **Live introspection plus schema hash.** On every request, compute `sha1` of `SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name`. This costs well under 1 ms. Every cache is keyed on `(db_id, schema_hash)`. If the hash changed, invalidate and rebuild.
2. **Schema diff → migration map** (old→new for tables and columns), built automatically when the hash changes:
   - Match tables and columns by value fingerprints from the profiler: same row count, same distinct-value MinHash, same type, and the same PK/FK graph position.
   - Use name similarity only as a tiebreaker: abbreviation expansion, token Jaccard, embeddings.
   - Use Qwen3-8B only to confirm ambiguous pairs.
   - A vertical split shows up as one old table whose columns are covered by two new tables sharing a key.
   - A horizontal split shows up as N new tables with identical columns whose row counts sum to the old count.
3. **Rewrite stale artifacts through the map, rather than relearning them:**
   - `rules/<db>.json` terms and columns (e.g. `date_column: "schools.OpenDate"`)
   - BIRD evidence strings
   - few-shot SQL in `config/examples.json`
   - profiler cache

   Use sqlglot for the SQL-bearing fields and a word-boundary regex for the prose fields.
4. **Compatibility views (optional, "shim mode")** for splits:
   - Vertical split: `CREATE VIEW old AS SELECT ... FROM a JOIN b USING(key)`.
   - Horizontal split: `CREATE VIEW old AS SELECT * FROM t_2014 UNION ALL SELECT * FROM t_2015`.

   The agent can then keep writing the old SQL. Show this both ways: with views (near-zero drop) and without views (the agent must recover).

   Caveat: this changes the DB. The Phase 2 graders may consider this cheating unless it is done in a separate attached DB or a temp schema. Use `ATTACH ':memory:' AS compat` plus TEMP views, which SQLite allows to reference the main DB.
5. **Prompt-level description of the new structure.** For example, "frpm was split into frpm_core(CDSCode, …) and frpm_rates(CDSCode, …), join on CDSCode." This follows the E/R-description finding in 2605.25838.
6. **Error-feedback loop.**
   - On `no such table: X` or `no such column: X`, look up X in the migration map. On a hit, rewrite deterministically via sqlglot and re-run; no LLM call is needed.
   - Otherwise, re-link with the error text plus the top-k retrieved columns, and give the writer one retry.
   - Cap retries at one or two, because the first pass gives most of the gain (LitE-SQL).
7. **Post-hoc SQL rewrite with sqlglot** is the safety net for when the writer emits old names copied from stale few-shots or evidence.

### Gaps
- No published ablation found measures a "migration map" or "auto-patched rules" approach. This looks like a gap in prior work: the papers either retrain (EvoSchema) or redesign the schema (2606.03145, SNAILS). None of them repair agent caches.

## Q3. Building the before/after experiment (perturb schemas and rewrite gold SQL)

### Takeaway
Generate perturbed copies of the BIRD dev SQLite DBs with a script that applies DDL and records a mapping. Rewrite gold SQL deterministically with sqlglot from that mapping. Validate each rewritten gold by **execution equivalence**: the old gold on the old DB and the new gold on the new DB must return the same result set. Keep only examples that touch a perturbed object, as Dr.Spider does.

### Cited Findings
- Dr.Spider keeps only examples whose SQL mentions a replaced column, and reports pre, post and "relative robustness" (correct on both / correct on pre) — [paper PDF](https://arxiv.org/pdf/2301.08881)
- EvoSchema rewrote renames by string, splits/merges by GPT-4 from mapping plus join paths, then checked by hand — [arXiv HTML](https://arxiv.org/html/2603.10697)
- sqlglot supports SQLite as an official dialect and supports AST transforms through `expression.transform(fn)` (example: replacing `exp.Column` nodes) — [sqlglot README](https://github.com/tobymao/sqlglot). The optimizer accepts a `schema=` dict, and `qualify` is opt-in — [sqlglot README](https://github.com/tobymao/sqlglot)

### Inferences: concrete harness
- **Perturbation suite.** Apply each perturbation to all 11 BIRD dev DBs, or at least california_schools, financial, formula_1, debit_card_specializing and student_club:
  1. `T-REN`: rename 1–2 core tables to synonyms. Example: `schools` → `institutions`, `frpm` → `meal_eligibility`. Use `ALTER TABLE RENAME TO`.
  2. `C-ABBR`: rename the columns used by gold SQL to abbreviations, e.g. `County Name` → `cnty_nm`, `Free Meal Count (K-12)` → `frm_cnt_k12`. Use `ALTER TABLE RENAME COLUMN`. This mirrors Dr.Spider's schema-abbreviation set.
  3. `C-SYN`: rename columns to synonyms, e.g. `Enrollment (K-12)` → `student_headcount_k12`.
  4. `T-VSPLIT`: vertical split. `CREATE TABLE a AS SELECT pk, c1..ck FROM t; CREATE TABLE b AS SELECT pk, ck+1..cn FROM t; DROP TABLE t`. Re-declare the PK and FKs by building the tables with explicit DDL (CTAS loses constraints).
  5. `T-HSPLIT`: horizontal split by year or category, e.g. `schools_open_pre2000`/`schools_open_2000plus`, or by `County`. Gold needs `UNION ALL` or partition pruning.
  6. (Optional) `T-MERGE`: denormalize two 1:1 tables into one. Optionally add `T-ADD` distractors: a copy table with similar names. EvoSchema shows "Add Tables" alone costs 18 EX points for Code Llama.
  7. `COMBO`: rename + split together. This is the realistic "migration" case.
- **Gold rewrite via sqlglot.**
  - Parse with `read="sqlite"` and qualify columns against the old schema so every column carries its table.
  - Rename: map `exp.Table.name` and `exp.Column.name` through the map with `transform`. sqlglot also provides `exp.replace_tables(expr, mapping)`; this is from memory and not checked this session — verify with `pip install sqlglot`.
  - Vertical split: for each table reference T split into A and B, replace T with `A JOIN B ON A.pk = B.pk AS T`. The simplest robust trick is to replace the `exp.Table` with a subquery `(SELECT * FROM A JOIN B USING(pk)) AS T`, which keeps the column qualifiers valid. This makes the gold provably equivalent. For a "natural" gold, hand-check a sample or let Qwen3-8B produce the flattened join and accept it only if it is result-equal.
  - Horizontal split: replace T with `(SELECT * FROM T_a UNION ALL SELECT * FROM T_b) AS T`.
  - Validate every pair by executing old gold on the old DB and new gold on the new DB and comparing multisets. Drop any example that fails.
- **Conditions to report** (a single table per DB and perturbation; columns = EX):
  - A. Original DB, original agent: the baseline.
  - B. Perturbed DB, agent with stale caches (as-is): shows the failure.
  - C. Perturbed DB, agent with hash-invalidation + re-introspection only: the "naive recovery".
  - D. C + migration map that patches rules, evidence and few-shots, plus the error-feedback rewrite: "full recovery".
  - E. (Optional) D + compatibility/natural views: an upper bound.
  - Also report relative robustness (Dr.Spider's metric), the "no such table/column" error rate, the mean retries, and latency.
- **Evidence handling.** BIRD evidence strings mention old column names (e.g. "`Free Meal Count (K-12)` / `Enrollment (K-12)`"). Report two variants: evidence left stale (realistic) and evidence rewritten through the map. Otherwise the experiment is confounded.
- **Sample size.** Use about 100–200 affected questions per perturbation, fitted to the 16 GB M4 budget and sharded across the Macs. Dr.Spider's filter keeps only questions that touch the perturbed objects, so every sample is informative.

### Gaps
- `exp.replace_tables` and the exact `qualify` signature were not verified this session: sqlglot is not installed locally and the docs page fetch failed.

## Q4. Which agent caches break on schema change, and how to detect staleness

### Takeaway
In the current code, every cache is keyed on `db_id` only, so a schema change passes silently:
- the profiler JSON is keyed by `db_id`
- `linker`'s `@lru_cache(maxsize=None)` over `sqlite_master`
- the `rules` loader's `@lru_cache`
- `rules/california_schools.json` (it hard-codes `schools.OpenDate`)
- `config/examples.json` few-shots

Key every cache on a schema hash.

### Cited Findings (from the local codebase, read this session)
- `agent/profiler.py:65-67`: `cache = ROOT / f"cache/profile_{db_id}.json"`; `if cache.exists() and not force: return json.loads(...)`. This never notices DDL changes. (local file /Users/ankushjha/College/hackathons/manipal/agent/profiler.py)
- `agent/linker.py:37-45`: `@lru_cache(maxsize=None)` wraps the read of `sqlite_master` and `PRAGMA table_info`. In a long-running API process it keeps serving the old schema until restart. (local file /Users/ankushjha/College/hackathons/manipal/agent/linker.py)
- `agent/rules.py:21-24`: `@lru_cache(maxsize=32)` loads `rules/<db>.json`. The rules contain `"date_column": "schools.OpenDate"` and term→column lists. (local files /Users/ankushjha/College/hackathons/manipal/agent/rules.py, /Users/ankushjha/College/hackathons/manipal/rules/california_schools.json)
- SQLite's own `sqlite_master.sql` text changes on every RENAME and CREATE, so a hash of it reliably detects DDL change — [SQLite docs](https://www.sqlite.org/lang_altertable.html)

### Inferences
- **Inventory of what goes stale:**
  - Profile: names, top values, null rates. Values survive a rename; keys do not.
  - Linker index: names and embeddings.
  - Rules: terms→columns, `date_column`, joins.
  - Hints/evidence that mention columns.
  - Few-shot SQL.
  - Any cached SQL or answers for repeat questions.
  - The confidence/decider thresholds, if they are tuned per DB.
- **Detection.** `schema_hash = sha1("\n".join(sql for sql in sqlite_master ORDER BY type,name))`. Also hash `PRAGMA user_version` and `PRAGMA schema_version`. `PRAGMA schema_version` is an integer SQLite increments on every schema change, so it is an even cheaper check. Store the hash inside each cache file and in the rules file's `"schema_hash"` field.
- **Auto-repair instead of rebuild.** Value-level profiles are expensive on large BIRD DBs, so do not drop them. Re-key them through the migration map, and re-profile only the tables that are new or have changed row counts.
- **Rules validation step.** After loading the rules, check that every referenced `table.column` exists in the live schema:
  - Missing refs that resolve through the migration map get patched.
  - Unresolvable refs are disabled and logged as "rule quarantined", so the agent never injects hints pointing at objects that do not exist. This is the "safe agent" angle.

### Gaps
- The few-shot selection mechanics and any SQL-answer cache in `agent/` were not inspected in detail. Check `hints.py`, `writer.py` and `runner.py` for more name-bearing state.

## Q5. Where prior work is weak, and how to do better

### Takeaway
Prior work measures drops and fixes them with retraining (EvoSchema, ADVETA) or a schema redesign (SNAILS, 2606.03145). Almost none of it treats drift as an **operational** problem: noticing that the schema changed, repairing the agent's own knowledge (rules, evidence, examples), and reporting recovery cost. That is where a hackathon entry can stand out.

### Cited Findings
- EvoSchema's remedy is perturbation-augmented fine-tuning on 4×A100 — [arXiv HTML](https://arxiv.org/html/2603.10697). This is not usable under our no-retraining constraint.
- Dr.Spider and ADVETA are diagnostic only, or use adversarial training — [Dr.Spider](https://arxiv.org/pdf/2301.08881); [ADVETA](https://www.microsoft.com/en-us/research/?p=844144)
- "Same Data, Different Schemas" has no gold SQL. It uses cross-schema agreement, which gives a lower bound on inconsistency, and it tests only 15 questions — [arXiv HTML](https://arxiv.org/html/2605.25838v1)
- The schema-design paper assumes the designer controls the model-facing schema. Its gains are modest, up to +4.2% — [arXiv PDF](https://arxiv.org/pdf/2606.03145)
- No paper found covers horizontal (row-partition) splits. EvoSchema's split-table rewrite used GPT-4 plus a manual check rather than a provably equivalent rewrite — [arXiv HTML](https://arxiv.org/html/2603.10697)

### Inferences: how to do better (the pitch)
1. **Deterministic, verifiable gold rewriting.** Subquery-substitution rewrites (old table → equivalent derived table over the new tables) are provably result-equivalent. Then confirm every pair by execution. This is stricter than EvoSchema's GPT-4 rewrite.
2. **Data-fingerprint schema matching.** Match old to new objects by profiled value distributions, not names. It is robust to arbitrary or obfuscated renames, which is exactly where name-based linking fails (Dr.Spider abbreviation, SNAILS).
3. **Self-healing knowledge layer.** The migration map auto-patches rules, evidence and few-shots, and quarantines anything it cannot resolve. Report "rules auto-repaired: k/n".
4. **Cover horizontal splits and combined rename+split**, which are under-studied.
5. **Report more than EX:** relative robustness, hard-error rate, silent-wrong rate (executes but wrong), retries, added latency, and time-to-recover after a schema change (first query after DDL).
6. **Safety framing.** When a mapping is ambiguous, the agent should abstain or ask ("I see `frpm` was split into X and Y; which is 'free meal rate'?") rather than guess. The abstention rate goes in the report.

### Concrete plan (ordered, about 1–2 days of work)
1. `scripts/perturb_schema.py`: input `db_id`, `kind` ∈ {T-REN, C-ABBR, C-SYN, T-VSPLIT, T-HSPLIT, COMBO}. Copy the DB to `data/perturbed/<kind>/<db>.sqlite`, apply the DDL, and write `mapping.json` (the old→new table/column map plus split specs).
2. `scripts/rewrite_gold.py`: use sqlglot to qualify, transform renames, and substitute derived tables for splits. Execution-validate each pair. Output `dev_<kind>.json` with only the affected questions. Write rewritten evidence beside it, with a flag.
3. `agent/schema_state.py`: add `schema_hash(conn)`, `diff(old_snapshot, new_snapshot) → migration map` (fingerprint matching + name similarity + optional Qwen3-8B confirmation), and `apply_map_to_rules/evidence/examples/profile`.
4. Change `profiler.py`, `linker.py` and `rules.py` caches to key on `(db_id, schema_hash)`. Add a rules validator with quarantine.
5. Add an executor hook: on `no such table/column`, run the map-based sqlglot rewrite, then one LLM retry with the error and the re-linked schema.
6. Run conditions A–E per perturbation, sharded across the Macs, and produce a before/after table plus error-category bars.
