# Phase 2 build status

Plan: `reports/Phase 2 safe agent plan.md`. Research notes: `research_notes/Phase 2 safe agent plan/`.

## Built and tested (117 offline unit tests pass: `.venv/bin/python -m pytest tests -q`)

| Component | File | What it does |
|---|---|---|
| AST policy + authorizer | `agent/guard.py` | sqlglot column/table check; SQLite authorizer factory; shared `constraints()`/`diff()` helpers used by follow-ups, clarification and drift |
| Guarded executor | `agent/executor.py` | read-only, single-SELECT, authorizer-backed, optional policy + audit log |
| Schema identity | `agent/schema_state.py` | schema hash (keys profiler/linker/rules caches); `derive_map` (stats-matched migration map, no retraining); `rewrite_sql`; `carry_over`; `migration_hints` |
| Role databases | `agent/roles.py`, `roles/california_schools.json`, `scripts/build_role_dbs.py` | one physical read-only SQLite per role (public_viewer, county_analyst, state_auditor); forbidden cells don't exist; canary mode for the leak oracle |
| Injection filters | `agent/sanitize.py` | cell-value/DDL-comment/error/judge-view filters, gated by `SECURE=1` (default on in the API; eval defaults preserve Phase 1 byte-for-byte prompts) |
| Follow-ups | `agent/conversation.py` | Qwen3 rewrite-to-standalone grounded in the SQL that ran, fallback on repeat-the-previous-question, carried-filter check across sampled candidate groups |
| Clarification | `agent/clarify.py` | asks only when ≥2 sampled-SQL groups disagree in results AND the judge says both are reasonable |
| Wiring | `agent/agent.py`, `api/server.py` | `ask()` takes `history=`/`drift=`; API resolves `role` server-side (never from question text) |

## Results so far

- **RBAC ladder** (`results/rbac_ladder.md`, `eval/run_rbac.py`, offline, worst case = writer obeys the attacker): 57 attacks, 3 roles. `none` layer leaks 75.4%; `role_db` and `role_db+AST` leak **0%**; benign controls 0/30 over-refused.
- **Live confirmation**: asked the live Arctic writer for admin emails against the `county_analyst` role DB — the real column doesn't exist in that DB, so the model fabricated a look-alike from the allowed name columns. No real leak, but **recommend also hiding `AdmFName1`/`AdmLName1`** in `roles/california_schools.json` if admin names count as PII for the demo (not yet changed — product-policy call).
- **Injection reach** (`results/injection_reach.md`, offline, `eval/run_injection.py`): 8 payload families × 4 channels. Defenses off: 32/32 payloads reach a model prompt. Defenses on: **0/32**. 0/5 benign look-alikes falsely altered.
- **Migration map recovery** (`results/migration_map.md`, `eval/run_map.py`): tested on california_schools, student_club, financial, superhero. Column mapping accuracy **100%** on all perturbation kinds after fixing a tie-breaking bug (unique-valued columns all hashed the same before the fix). Gold-SQL round-trip (rewritten gold == original gold's answer) is 100% except `t_hsplit`, where only the questions touching the split table count (correctly fewer "kept" questions, not a map failure).
- **Live drift smoke** (`eval/run_drift.py`, 2 questions, condition C vs D on `t_vsplit`): condition `C` (fresh profile, no map) returns "no such table" and refuses; condition `D` (fresh profile + migration map) **answers correctly** on the easy question. The one miss (q11) is the writer's own mistake (it used one enrollment column where gold sums two), reproduced identically in both conditions — drift repair did not introduce it.
- **Live follow-up smoke** (confirmed, ran in background while Phase 1 jobs were on the models): turn 1 "How many schools are in Alameda county?" → `WHERE County = 'Alameda'`; turn 2 "now only the charter ones" → Qwen3 rewrote to "How many charter schools are in Alameda county?" and the winning SQL correctly carried **both** `Charter = 1 AND County = 'Alameda'` — the carry-check in `conversation.py` picked the group that kept the earlier filter over a group that dropped it.
- **conversations_dev_20.json** (`eval/sets/`): 5 hand-written, hand-verified 3-turn conversations (15 turns) across 7 follow-up types (add_filter, replace_value, change_agg, coref, ellipsis, topic_shift, undo), all on california_schools, checked with `scripts/check_conversations.py`. This is a starter slice of the planned 50; the other 45 are pure authoring work, no more code needed.

## Not yet done (see "Build in the order that makes later parts cheaper" in the report)

- RBAC: hand-expand the 57 generated attacks with more paraphrase/jailbreak variants to clear 30+ per the brief with margin (already well past 30); run the **adaptive** injection round; wire `roles.py` behind the UI role switcher.
- Follow-ups: finish `conversations_50.json` (45 more conversations, spread across more DBs) and run `eval/run_agent`-style scoring of the live pipeline against it (per-turn EX, conversation EX, oracle-rewrite ablation) — needs model time, deliberately not run yet given Phase 1 jobs were on the servers.
- Ambiguity: `eval/sets/ambiguous_100.json` (schema + validator ready in `eval/sets/ambiguous_schema.md` / `scripts/check_ambiguous.py`, no questions authored yet) and the false-ask-rate run on Phase 1's 150 answerable questions.
- Policy follow-up from the live RBAC check: consider hiding `AdmFName1`/`AdmLName1` too in `roles/california_schools.json` (admin names let the model fabricate a look-alike email even though the real `AdmEmail1` column is gone) — not changed, needs a product-policy decision.
- `eval/report_phase2.py` aggregating all five tables for the slide deck.
- Full (not 2-question) `eval/run_drift.py` and `eval/run_rbac.py` live passes once the Mac has spare model capacity.
