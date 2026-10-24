# What we learned from the questions (and from our own mistakes)

Based on the 150 reporting questions of BIRD Mini-Dev, run twice: the **plain model** (Arctic-R1-7B, one greedy pass, full schema, no hints) and the **agent** (5 attempts, linked schema, auto-hints, vote), both without BIRD's hand-written evidence. All numbers below are measured, not estimated. Where I guessed, it says so.

## 0. The numbers in one table

| | Correct | EX |
| --- | --- | --- |
| Plain model | 54 / 150 | 36.0% |
| Agent | 58 / 150 | 38.7% |

- Agent fixed **15** questions the plain model got wrong, and broke **11** it got right. Net **+4**, so **+2.7 points**.
- 43 questions both got right, **81 both got wrong**.
- Exact McNemar test on the 15-vs-11 split: **p = 0.56**. The gain is positive but **not distinguishable from chance** at this sample size. Do not present it as a win. Present it as "no worse, and here is where it helps".
- The two Macs disagreed: Mac 1's half gained +6.7, Mac 2's half −1.3. That spread is what luck looks like at n = 75.
- Time: plain about 42 s/question (measured while the machine was shared, so rough), agent about 119 s/question.

**We never modify data.** The databases are opened read-only and only a single SELECT/WITH is allowed. All 11 original database files were checksum-compared to the downloaded zip: byte-for-byte identical. The only place columns are dropped is `data/unanswerable_dbs/` (copies) to build questions the data cannot answer.

## 1. Where the wrong answers come from

Each wrong answer was auto-classified by comparing its SQL to the gold SQL (tables used, string literals, number of output columns, result emptiness). This is a **heuristic, not hand-labelled**: categories overlap and "wrong tables" can include a legitimate alternative path.

| Cause | Plain (96 wrong) | Agent (92 wrong) |
| --- | --- | --- |
| Different tables than the gold query | 37 | 38 |
| A string literal that differs from the gold's | 15 | 16 |
| Returned zero rows where gold has rows | 11 | 14 |
| Same tables and shape, different logic | 14 | 11 |
| Extra or missing output columns | 12 | 7 |
| Aggregation / DISTINCT differs | 5 | 5 |
| SQL error / ranking | 2 | 1 |

The agent reduced "extra columns" (12 → 7) but did not move the biggest bucket (wrong tables) or the value/format buckets. That matches the sections below.

## 2. The failure patterns, with the questions that show them

### A. The hidden business rule (the biggest single cause)
BIRD gives every question an *evidence* sentence that maps words to columns and formulas. We deliberately hide it, because real users never write it. Of the 81 questions both systems got wrong, **77 have evidence that maps a phrase to a column or value** and **61 contain a formula**.

- **q1156** "patient with positive degree of coagulation": evidence says `RVVT = '+'`. The agent chose `KCT`, another plausible coagulation test. Nothing in the schema says which one the business means.
- **q407** "all types of cards": evidence says `subtypes, supertypes`. The agent used the `types` column.
- **q877** "drivers who finished": evidence says `time IS NOT NULL`. The agent skipped that filter.
- **q954** "race completion": evidence defines it as `time` not null. The agent invented `position > 0`.

**Lesson:** without the rule, the model guesses a plausible column. This is the real-world problem in the pitch ("business metrics the model can't interpret"), and it is exactly what the rules registry (Careful mode) is for. It also explains why a no-hint score is low whatever the model: part of the answer is not in the database.

### B. The model invents the stored format of a value
The model writes the value the way a human would. The database stores it differently, the filter matches nothing, and the query returns zero rows. A wrong answer that **runs cleanly**.

- **q1102** date written as `'2016/6/23'`; stored as `2016-06-23 00:00:00` (gold uses `SUBSTR(date,1,10)`).
- **q872** time written `'0:01:33'`; stored as `1:33.xxx` (gold uses `LIKE '1:33%'`).
- **q724** hair colour `'Blonde'`; the stored value is `'Blond'`.
- **q1484 / q1509** `'Czech Republic'`; stored as `'CZE'`.
- **q533** compared a timestamp column directly; gold wraps it in `date()`.

Several of these had **all 5 attempts agreeing** (vote 1.0), because all five made the same guess. See section 3.

**Lesson / idea (not built yet):** this is detectable without any model. If an equality filter's literal does not exist among the column's stored values, flag it and try the nearest stored value. Our hints already show stored values for some columns, but only for columns the question words matched; dates and times were the gap.

### C. Wrong table or column when two are plausible
- **q1344** looked in `event.notes`; the answer was in `income.notes`.
- **q1389** "lowest cost": used `budget.spent`; gold uses `expense.cost`.
- **q1479** used `transactions_1k`; gold uses `yearmonth`.
- **q892** "driver with the most points": the agent **summed** points across all races. The gold takes the single highest value. The question is genuinely ambiguous; the evidence resolves it.
- **q906** returned `raceId`; gold returns the race `name`.

**A cause we measured:** our linker keeps only the top 5 tables. In **21 of 150 questions it dropped a table the gold query needs**, and in those the agent got **2/21 right**, versus **56/129** when every gold table was kept. Worst databases: `financial` 8/14 kept, `formula_1` 13/21, `superhero` 14/17, `card_games` 12/14.
So pruning is a real source of loss on databases with many tables, not just on hard questions.

### D. Output shape: BIRD compares the whole result set
Returning one extra column makes the answer wrong, even if it is better for a person.

- **q1149** returned both counts plus the percentage; gold returns only the percentage.
- **q1323, q1225** similar.
- **q23** "school names and full street address": the agent returned street + city + state joined together. Gold returns only the street. Arguably the agent's answer is the more useful one.

**Lesson:** part of the "error" is a benchmark artifact, not a model mistake. We cannot edit the writer's prompt (it must match its training template), so we do not chase this one.

### E. Gold labels that are questionable
- **q1399** "Did Maya Mclean attend the Women's Soccer event?" gold returns 14 rows of `YES`/NULL. A direct "Yes" is scored wrong.
- **q892** and **q23** above.

Keep two or three of these ready for the slides: they support "we report gains, not ranks".

## 3. Voting: what it tells us, and what it cannot

Agent accuracy by how many of the 5 attempts agreed:

| Agreement | Questions | Agent correct |
| --- | --- | --- |
| Low (< 50%) | 32 | **22%** |
| Middle (50-80%) | 32 | **28%** |
| High (>= 80%) | 86 | **49%** |

- Agreement is a **real signal**: it separates the easy from the hard. That is what Careful mode's refusal is built on.
- It is **not enough on its own**. **26 of the 60 questions where all 5 attempts agreed were wrong (43%).** When the model has a systematic misunderstanding (sections 2A, 2B), five samples repeat it. The research notes warned about exactly this ("raw self-consistency is over-confident").
- Of the 11 answers the agent broke, **7 had split votes** (the tie went to whichever group came first, while the plain greedy answer was right) and **4 were unanimous but wrong**. The first kind is fixable with a better tie-break (experiment running now). The second kind needs better hints or value checks, not more samples.

## 4. By database (small samples, read as hints, not facts)

| Database | n | Plain | Agent |
| --- | --- | --- | --- |
| debit_card_specializing | 5 | 40% | 80% |
| thrombosis_prediction | 14 | 14% | 36% |
| toxicology | 10 | 0% | 20% |
| california_schools | 8 | 25% | 38% |
| european_football_2 | 16 | 56% | 62% |
| financial | 14 | 7% | 14% |
| student_club | 11 | 36% | 36% |
| card_games | 14 | 43% | 36% |
| formula_1 | 21 | 38% | 33% |
| codebase_community | 20 | 45% | 35% |
| superhero | 17 | 65% | 53% |

The agent helped where **codes and formats matter** (coded flags, text columns, messy schemas) and lost on databases with **many tables and clean, self-explanatory names**. My hypothesis, **not verified**, is that table pruning costs more there than hints give back (see 2C). Each cell has 5 to 21 questions, so one question moves a percentage by 5 to 20 points.

## 5. Mistakes we made while building, and how each was caught

| Mistake | How it showed up | Fix |
| --- | --- | --- |
| Executor refused `EXCEPT` / `INTERSECT` | A gold query was reported "not allowed" while I was reading failures | Allowed set operations, added tests, built `eval/rescore.py`. Earlier scores were slightly under-counted |
| Two sanity checks never ran | Reviewing the code: the inputs they need were never passed | Now computed from the profile |
| Used the 8B model to decide "can the data answer this?" | Measured on 40 answerable vs 40 column-removed questions: 40% false refusals, no separation | Made it a soft signal only (switch to re-enable) |
| Judge model started with `<think>` | First token was never a letter | `enable_thinking: false` in the request (`/no_think` is ignored) |
| Assumed 4 parallel streams would be ~3× faster | Measured about 1.7×, and the Mac got hotter | Cap at 2 workers, shard across several Macs instead |
| Compared a partial agent run to the full plain run | Showed +7.8; the like-for-like number was +4.7 | Gain is now computed on the questions both runs answered |
| Hints were noisy (surname matched "Free", irrelevant columns) | Printing hints for real questions | Value matches must look intentional; hints use only strongly matched columns |
| "Phone" screenshot was really 500 px wide | Headless Chrome has a minimum width, so my mobile check was wrong | Re-tested with device emulation at 390 px |
| Literal repair rewrote `NOT IN ('x')` | A unit test I wrote for it failed: sqlglot stores `NOT IN` as `NOT(IN(...))`, so the inner `IN` was matched | Skip anything under a `NOT`; added tests |
| Ran both model servers at once on 16 GB | 6% free memory, heavy swap | Judge only when needed; smaller context for the judge |
| Duplicate result files after AirDrop | Finder renamed them with " 2" | Compared bytes, confirmed identical, left the real copies in `results/` |

## 6. What to do next (ordered by expected gain per effort)

1. **Literal repair: BUILT** (`agent/literals.py`, no model). If an equality filter's literal is not a stored value of its column, it is swapped for the stored spelling (`'Blonde'` becomes `'Blond'`, `'blue'` becomes `'Blue'`) or a date written as `2016/6/23` is matched against `2016-06-23 00:00:00` timestamps. It never touches `!=`, `NOT IN`, `LIKE`, or a literal that is already stored, and it does nothing when two spellings are equally close.
   - **Precision:** run over all 500 gold queries it rewrote **0** of them, so **0 false positives** (`python -m eval.literal_check`).
   - **Effect, re-scoring the saved predictions with no model:** plain **54 to 59 / 150**, agent **58 to 63 / 150**, and **0 broken**. The same component helps the plain model by the same amount, so report it as a *component*, not as the agent's own gain.
   - **Caveat:** I designed it after reading q1102 and q724, so those two are not an independent test. The other fixes (q1435, q1113, q383, q228, q797) I had not looked at, and the 500-gold precision test is independent.
   - **Not measured yet:** applying it *before* voting, as the agent now does, may help more, since attempts that returned zero rows can then join the right group. That needs a fresh agent run.
2. **Keep more tables for databases with many tables** and measure whether accuracy follows the recall. Targets 2C (21 questions lost to pruning).
3. **Greedy tie-break** (experiment already running on the 32 low-agreement questions; the result is compared on identical samples).
4. **Run the "with BIRD hints" columns.** That gives the upper bound and the second row of the slide.
5. **Careful-mode numbers** (refusal quality, risk-coverage). This is the actual differentiator, and the weakest part of what we have measured so far.

## 7. What we have NOT verified

- The failure categories are heuristic, not human-labelled.
- Whether table pruning is the cause of the per-database losses (a hypothesis).
- Whether the "invented literal" check would fix the questions it targets (a plan, not a result).
- Anything about Careful mode with a real judge on the 150 questions.
- Whether the hint-aware agent beats plain at all: the gain is +2.7 points with p = 0.56.
