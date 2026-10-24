# Frontend brief: "The analyst that shows its work and knows when to say no"

Paste this whole file to whoever builds the frontend. Theme/visual style comes separately; do NOT invent branding, only follow the structure and behaviour below. Use neutral placeholder styling and make colours/fonts/spacing theme tokens so a theme can be dropped in later.

## 1. What the product is

A web app where a person types a plain-English question about a database and gets either:
- an **answer** with the SQL, a confidence score and a visible step-by-step trace, or
- a **refusal** with a clear reason ("the data has no teacher-satisfaction column"), or
- a **clarifying question** ("best by test scores or by enrolment?").

Everything runs locally (open-weight models, no data leaves the machine). The product's promise is trust: the user can always see *why* an answer is right, and the app says "I can't answer that" instead of guessing.

## 2. Who uses it, and what they want

| User | Situation | What they look for |
| --- | --- | --- |
| **Business analyst / non-technical user** (primary) | Has a question, no SQL skills | Type a question, get a number they can trust, in under a minute. Clear words, no jargon. |
| **Data-savvy reviewer** | Wants to verify before using the number | See the exact SQL, tables used, filters, checks passed. Copy SQL. |
| **Hackathon judge / demo audience** (secondary, very important) | 3-minute live demo | Instantly see: answer, trace, refusal, consistency, and the metrics. Nothing confusing or broken. |

Top user jobs, in priority order:
1. Ask a question and get an answer quickly.
2. Know whether to trust it (confidence + checks + refusal).
3. See how the answer was produced.
4. Ask a follow-up or fix a misunderstanding (clarification buttons).
5. Switch database.
6. See proof the system works (results screen).

Design principles: one primary action per screen; plain language over jargon ("Not sure enough to answer" not "P(correct) below threshold"); never show a raw error or stack trace; always say what is happening during waits; every answer is self-explaining (mode and models visible).

## 3. App structure

Top bar: app name, two tabs **Ask** and **Results**, a small status indicator (models ready / not ready), settings button.

### Screen A: Ask (default)

Layout (desktop): left sidebar 280px, main area. On mobile the sidebar collapses into a "Settings" sheet above the question box.

**Sidebar ("Setup"), grouped and collapsed by default except Database:**
1. **Database**: dropdown of available databases (default `california_schools`). Under it: table count, and profile status ("Ready" / "Preparing… 40%").
2. **How careful should it be?** (this is the Mode toggle, user-friendly wording) segmented control:
   - **Careful** = product mode: may refuse or ask a question. Default.
   - **Always answer** = benchmark mode: always returns its best guess.
   Helper text under each, one line.
3. **Advanced** (collapsed): number of attempts slider 1-6 (label "Attempts per question", default 5), "Use BIRD hint text" toggle (off, shows hint field only for evaluation questions), "Decision engine: Local / Jev" (Jev disabled unless configured; label Local as "Open-weight, on this machine").
4. **Try an example** list (5 clickable chips): falling enrolment · a coded-value question · an ambiguous question ("best schools") · a question the data can't answer · repeat-3-times check. Clicking fills the question box.

**Main area, top to bottom:**
1. **Question box**: large multi-line input, placeholder "Ask anything about this database…", primary button **Ask**, secondary **Ask 3 times** (consistency check; shows 3 results side by side, with a banner "Same answer all 3 times" or "Answers differed").
2. **Progress stepper** (visible only while running): 9 steps with plain labels: Understanding the question → Finding the right tables → Preparing hints → Writing SQL attempts → Running them → Voting on results → Sanity checks → Double-checking → Deciding. Current step animated, finished steps show seconds. Cancel button.
3. **Verdict card** (the hero), three variants:
   - **Answered**: big answer (single value large; tables as a table), confidence shown as a labelled level ("High confidence 91%") with a plain-language one-liner of why ("4 of 5 attempts agreed; all checks passed").
   - **Can't answer**: icon-neutral heading "I can't answer this reliably", the reason in plain words, what's missing, and a suggestion for how to rephrase.
   - **Need a detail**: the clarifying question plus 2-3 clickable option buttons plus "type your own". Clicking re-runs with that choice.
4. **Result table** (answered only): columns + rows, sortable, "Download CSV", note "Showing first 1,000 rows" if capped.
5. **"How I got this"** section, tabs:
   - **SQL**: formatted, copy button; toggle to see other candidate queries and which result each produced.
   - **Steps** (the trace): accordion, one entry per pipeline step with a one-line summary and details on expand (tables/columns chosen, hint lines used, each attempt's SQL, vote groups with sizes, each sanity check pass/fail, judge verdict). Highlight the auto-generated hint lines, since they are what makes it work without hand-written hints.
   - **Confidence**: signal list (attempt agreement, sanity checks, schema match, double-check verdict) with small bars, and the threshold used.
   - **Raw JSON** with copy.
6. **History** strip: last 10 questions of this session as chips; click to reload that answer.

### Screen B: Results (read-only proof page)
Five blocks, each with a one-sentence takeaway sentence at the top (generated from the data):
1. **Accuracy gain**: table/bar comparing plain model vs full agent, with and without hints, on the 150 test questions. Highlight the no-hints gain in points.
2. **Answered vs wrong (risk–coverage)**: line chart, x = % of questions answered, y = % of those answered that were wrong; draggable threshold marker shows coverage and error at that point.
3. **Saying no correctly**: stacked bar of the 5 outcomes, filterable by 4 question types (ambiguous, missing data, not a SQL question, needs outside knowledge).
4. **Speed**: seconds per question, and where it ran.
5. **Honest note** (fixed text): "About half of BIRD Mini-Dev labels have known errors, so we report gains, not rankings." plus a small expander with 2 label-error examples.
Empty state if no results exist yet: "No evaluation runs yet."

## 4. States to design (every one, no blanks)
Empty first visit · typing · running (stepper) · answered · can't answer · need a detail · models not ready (disable Ask, show which one) · blocked query ("That query was blocked for safety") · timeout ("Took longer than 10 seconds, try a narrower question") · profile still preparing · no results yet · 3x run: consistent / inconsistent · network lost.

## 5. Behaviour rules
- Mode and decision engine are shown on every verdict card ("Careful mode · local models").
- Accuracy numbers on the Results screen come only from "Always answer" runs, never from "Careful".
- Must work fully offline.
- Waits are 20-60s: never freeze, always show stepper; stream steps as they arrive.
- Keyboard: Cmd/Ctrl+Enter submits. Accessible: labelled inputs, focus states, colour never the only signal for status, reduced-motion respected.
- Responsive from 360px to projector widths; verdict card readable from the back of a room (large type for the answer).

## 6. Backend contract (I will build this; code against it, mock it until ready)

Base URL `http://localhost:8000`.

- `GET /health` → `{"writer": true, "judge": false, "logprobs": false}`
- `GET /databases` → `[{"id": "california_schools", "tables": 3, "profile": "ready|building", "progress": 1.0}]`
- `GET /examples?db=california_schools` → `[{"label": "...", "question": "..."}]`
- `POST /ask` body `{"question": "", "db": "", "mode": "product|benchmark", "n_samples": 5, "use_hints": false, "decider": "local|jev", "hint": ""}`; response is **Server-Sent Events**:
  - `event: step` data `{"step": "triage|link|hints|write|run|vote|checks|judge|decide", "state": "start|done", "seconds": 1.2, "detail": {}}`
  - `event: result` data:
    ```json
    {"status": "answered|refused|needs_clarification",
     "answer_rows": [["..."]], "columns": ["..."], "truncated": false,
     "sql": "SELECT ...", "candidates": [{"sql": "", "group": 0, "error": null}],
     "confidence": 0.0, "reason": "", "options": ["...", "..."],
     "signals": {"agreement": 0.8, "groups": 2, "flags": [], "link_coverage": 1.0, "judge_yes": 0.9},
     "threshold": 0.6, "mode": "product", "decider": "local",
     "trace": [{"step": "", "detail": {}}]}
    ```
  - `event: error` data `{"code": "blocked|timeout|models_down", "message": "plain-language text"}`
- `POST /cancel` → `{}`
- `GET /results` → `{"summary": {...}, "risk_coverage": [{"coverage": 0.2, "error": 0.05, "threshold": 0.9}], "refusal": {...}, "latency": {...}}` (404 until evaluation has run)

## 7. Deliverable
A single-page app (any framework) with the two screens, all states above, mock data for `/ask` and `/results` that follows the contract exactly, and a theme file of tokens (colours, type scale, spacing, radii) that is the only place styling values live.
