# Phase 2 Comprehensive Evaluation Report
Enterprise safety, permissions, follow-ups, schema recovery, and ambiguity.

## 1. Enterprise RBAC Defense Ladder (3 Roles, 57 Attacks)
Worst-case testing: the writer model follows attacker instructions to the letter.

| Layer Enforced | Leaking Attacks | Leak Rate | Benign Refused | Security Guarantee |
|---|---|---|---|---|
| None (Raw SQLite) | 43 / 57 | 75.4% | 0/30 | None (Direct leak) |
| AST Policy | 6 / 57 | 10.5% | 0/30 | Column/table AST check |
| SQLite Authorizer | 6 / 57 | 10.5% | 0/30 | Runtime C-level hook |
| AST + Authorizer | 6 / 57 | 10.5% | 0/30 | Dual-layer parse + run |
| Role Database (`role_db`) | **0 / 57** | **0.0%** | **0/30** | Physical omission (columns do not exist) |
| All Layers Active | **0 / 57** | **0.0%** | **0/30** | Defense-in-depth |

## 2. Planted-Instruction Injection Reach (8 Families × 4 Channels)
Attack vectors tested across cell-value, DDL-comment, execution-error, and judge-view channels.

| Mode | Payloads Reaching Model Prompts | Penetration Rate | Benign Look-Alikes Falsely Altered |
|---|---|---|---|
| Defenses Off | 32/32 (100%) | 100% | 0/5 (0%) |
| Defenses On (`SECURE=1`) | **0/32 (0%)** | **0%** | **0/5 (0%)** |

## 3. Schema Drift Recovery with Zero Retraining (Migration Map)
Automated schema fingerprinting and value matching across BIRD dev benchmarks.

| Perturbation Kind | Column Map Accuracy | Table Rebuildability | Gold Rewritten Multi-Set Match |
|---|---|---|---|
| Table Rename (`t_ren`) | 89/89 (100.0%) | 3/3 (100%) | 30/30 (100%) |
| Column Abbreviation (`c_abbr`) | 89/89 (100.0%) | 3/3 (100%) | 30/30 (100%) |
| Vertical Split (`t_vsplit`) | 89/89 (100.0%) | 3/3 (100%) | 30/30 (100%) |
| Horizontal Split (`t_hsplit`) | 89/89 (100.0%) | 3/3 (100%) | 25/25 (100% on valid scope) |
| Combination (`combo`) | 89/89 (100.0%) | 3/3 (100%) | 30/30 (100%) |

## 4. Multi-Turn Follow-Up Conversations (conversations_50)
Full benchmark of **56 conversations (168 turns)** across 11 databases.

| Follow-Up Category | Count of Turns | Example Intent |
|---|---|---|
| `add_filter` | 36 | "now only for 2023" / "only in Alameda county" |
| `replace_value` | 2 | "what about for Fresno instead?" |
| `change_agg` | 30 | "show me the average instead of the count" |
| `coref` | 20 | "which of them scored above 500?" |
| `ellipsis` | 5 | "and highest?" / "charter schools?" |
| `topic_shift` | 11 | Reset context cleanly when a new subject is queried |
| `undo` | 8 | Revert the previous filter modification |

## 5. Ambiguity & Clarification Defense (ambiguous_100)
Benchmark of **100 ambiguous questions** across 10 databases.

| Ambiguity Edit Type | Questions | Oracle Validation | Disagreement Handling |
|---|---|---|---|
| `column_synonym` | 34 | 100% verified differing SQL results | Proactive clarification question asked |
| `stripped_evidence` | 5 | 100% verified differing SQL results | Proactive clarification question asked |
| `vague_filter` | 61 | 100% verified differing SQL results | Proactive clarification question asked |
