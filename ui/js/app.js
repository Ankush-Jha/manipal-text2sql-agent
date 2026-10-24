import { icon, hydrateIcons, dbTile } from "./icons.js";
import { Pipeline } from "./pipeline.js";
import { renderResults } from "./results.js";
import { renderData } from "./data.js";
import { esc, pct, fmtSec, fmtNum, titleCase, timeAgo, highlightSql, toast, store, downloadCsv, GROUP_COLORS } from "./util.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  dbs: [], db: store.get("db", "california_schools"), mode: store.get("mode", "product"), n: 5,
  running: false, controller: null, current: null, history: store.get("history", []),
  health: { writer: false, judge: false }, view: "ask", stepTimes: {},
  dialog: null, // clarification chat in progress: { question, turns, answers, rounds }
};

const pipeline = new Pipeline($("#canvas"));

// ───────────────────────── boot ─────────────────────────
hydrateIcons();
bind();
setMode(state.mode, false);
renderCards(null);
renderPanes(null);
renderHistory();
init();

async function init() {
  try {
    state.dbs = await (await fetch("/api/databases")).json();
  } catch {
    showNotice("error", "Can’t reach the local server. Start it with <code>uvicorn api.server:app --port 8000</code>.");
    return;
  }
  if (!state.dbs.find((d) => d.id === state.db)) state.db = state.dbs[0]?.id;
  renderDbMenu();
  selectDb(state.db);
  pollHealth();
  setInterval(pollHealth, 6000);
}

// ───────────────────────── databases ─────────────────────────
function dbIndex(id) { return Math.max(0, state.dbs.findIndex((d) => d.id === id)); }

function renderDbMenu() {
  $("#dbMenu").innerHTML = state.dbs.map((d, i) => `
    <button class="db-opt" role="option" data-db="${d.id}">
      <span class="mini">${dbTile(d.id, i)}</span>
      <span><b>${titleCase(d.id)}</b><small>${d.tables} tables · ${d.columns} columns</small></span>
    </button>`).join("");
}

async function selectDb(id) {
  state.db = id;
  store.set("db", id);
  const d = state.dbs.find((x) => x.id === id);
  if (!d) return;
  $("#dbAvatar").innerHTML = dbTile(id, dbIndex(id));
  $("#dbName").textContent = titleCase(id);
  $("#dbSub").textContent = `${d.tables} tables · ${d.columns} columns`;
  $("#dbAvatar").title = d.profile === "ready" ? "Profiled and ready" : "Profiling…";
  $("#question").placeholder = window.innerWidth < 760 ? "Ask a question…" : `Ask anything about ${titleCase(id)}…`;
  $$(".db-opt").forEach((b) => b.classList.toggle("is-active", b.dataset.db === id));
  closeDbMenu();
  const ex = await (await fetch(`/api/examples?db=${id}`)).json();
  renderExamples(ex);
  if (state.view === "data") renderData($("#dataBody"), id, $("#colSearch").value);
}

function renderExamples(list) {
  const ic = { answer: "sparkle", clarify: "help", refuse: "xCircle" };
  const tag = { answer: "", clarify: "clarify", refuse: "refuse" };
  $("#examples").innerHTML = list.length ? list.map((e) => `
    <button class="ex-item" data-q="${esc(e.question)}" title="${esc(e.question)}">
      <span class="ex-icon">${icon(ic[e.kind] || "sparkle")}</span>
      <span class="ex-text">${esc(e.label)}</span>${tag[e.kind] ? `<span class="ex-tag ${tag[e.kind]}">${tag[e.kind] === "refuse" ? "should refuse" : "should ask"}</span>` : ""}
    </button>`).join("") : `<div class="side-empty">No examples for this database yet. Type your own.</div>`;
}

function openDbMenu() { $("#dbMenu").hidden = false; $("#dbCard").setAttribute("aria-expanded", "true"); }
function closeDbMenu() { $("#dbMenu").hidden = true; $("#dbCard").setAttribute("aria-expanded", "false"); }

// ───────────────────────── health ─────────────────────────
async function pollHealth() {
  try {
    state.health = await (await fetch("/api/health")).json();
  } catch { state.health = { writer: false, judge: false }; }
  const set = (el, ok, name) => {
    el.querySelector(".dot").className = `dot ${ok ? "ok" : "down"}`;
    el.title = `${name}: ${ok ? "running" : "not running"}`;
  };
  set($("#hWriter"), state.health.writer, "Writer (Arctic-Text2SQL-R1-7B)");
  set($("#hJudge"), state.health.judge, "Judge (Qwen3-8B)");
  updateReadiness();
}

function updateReadiness() {
  if (state.running) return;
  const h = state.health;
  if (!h.writer) {
    showNotice("warn", `The SQL writer isn’t running, so questions can’t be answered yet. Start <code>llama-server</code> on port 8081.`);
  } else if (state.mode === "product" && !h.judge) {
    showNotice("warn", "Careful mode needs the judge model (port 8082), which isn’t running.", "Use Always answer", () => setMode("benchmark"));
  } else hideNotice();
  $("#askBtn").disabled = !h.writer || (state.mode === "product" && !h.judge);
}

function showNotice(kind, html, actionLabel, action) {
  const n = $("#notice");
  n.className = `notice ${kind === "error" ? "error" : kind === "info" ? "info" : ""}`;
  n.innerHTML = `${icon(kind === "info" ? "info" : "alert")}<span>${html}</span>${actionLabel ? `<button type="button">${esc(actionLabel)}</button>` : ""}`;
  if (action) n.querySelector("button").onclick = action;
  n.hidden = false;
}
function hideNotice() { $("#notice").hidden = true; }

// ───────────────────────── asking ─────────────────────────
function setMode(mode, persist = true) {
  state.mode = mode;
  if (persist) store.set("mode", mode);
  $$(".seg-btn").forEach((b) => { const on = b.dataset.mode === mode; b.classList.toggle("is-active", on); b.setAttribute("aria-checked", on); });
  if (!state.running && !state.current) pipeline.reset(mode);
  updateReadiness();
}

async function ask(question, { silent = false, choice = null, rounds = 0 } = {}) {
  question = question.trim();
  if (!question || state.running) return null;
  state.running = true;
  state.stepTimes = {};
  state.n = Math.min(8, Math.max(1, Number($("#attempts").value) || 5));
  state.current = { question, result: null };
  hideNotice();
  setRunningUi(true);
  switchTab("pipeline");
  pipeline.start(question, state.mode, state.n);
  renderCards("running", question);
  // on short screens the canvas sits below the cards: bring it into view so the run can be watched
  const canvasTop = $("#canvas").getBoundingClientRect().top;
  if (canvasTop > window.innerHeight * 0.6) setTimeout(() => $(".tabbar").scrollIntoView({ behavior: "smooth", block: "start" }), 350);
  renderPanes(null);

  const ctrl = new AbortController();
  state.controller = ctrl;
  const t0 = performance.now();
  const clock = setInterval(() => {
    const el = $("#statTime");
    if (el && state.running) el.textContent = fmtSec((performance.now() - t0) / 1000);
  }, 200);
  let result = null;
  try {
    const res = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
      body: JSON.stringify({ question, db: state.db, mode: state.mode, n_samples: state.n, choice, rounds }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : "The request was rejected. Check the settings and try again.");
    }
    for await (const ev of sse(res)) {
      if (ev.event === "step") onStep(ev.data);
      else if (ev.event === "result") result = ev.data;
      else if (ev.event === "error") throw Object.assign(new Error(ev.data.message), { code: ev.data.code });
    }
    if (!result) throw new Error("The answer stream ended early.");
    state.current.result = result;
    if (result.status === "needs_clarification" && result.choices?.length) {
      state.dialog ??= { question, turns: [], answers: [], rounds: 0 };
      state.dialog.rounds += 1;
      state.dialog.turns.push({ role: "agent", text: result.reason });
    } else state.dialog = null;
    pipeline.finish(result);
    renderCards(result, question);
    renderPanes(result);
    addHistory(question, result);
  } catch (e) {
    if (e.name === "AbortError") { pipeline.fail("Cancelled."); renderCards(null); }
    else { pipeline.fail(e.message); renderCards({ status: "error", reason: e.message }, question); showNotice("error", esc(e.message)); }
  } finally {
    clearInterval(clock);
    state.running = false;
    state.controller = null;
    setRunningUi(false);
    updateReadiness();
  }
  if (!silent && result) document.title = `${result.status === "answered" ? "✓" : "•"} ${question.slice(0, 40)} · Analyst`;
  return result;
}

async function* sse(res) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
      const raw = buf.slice(0, i);
      buf = buf.slice(i).replace(/^\r?\n\r?\n/, "");
      let event = "message", data = "";
      for (const line of raw.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) yield { event, data: JSON.parse(data) };
    }
  }
}

function onStep(ev) {
  pipeline.onStep(ev);
  if (ev.state === "done") state.stepTimes[ev.step] = ev.seconds;
  if (ev.step === "write" && ev.state === "progress") renderStats({ live: pipeline.attempts }, true);
  if (ev.step === "run" && ev.state === "done") renderStats({ candidates: ev.detail.candidates.map((c) => ({ ...c, group: ev.detail.groups.findIndex((g) => g.sqls.includes(c.sql)) })) }, true);
}

function setRunningUi(on) {
  const b = $("#askBtn");
  b.classList.toggle("is-running", on);
  b.querySelector("span").textContent = on ? "Working…" : "Ask";
  b.disabled = on;
  $("#cancelBtn").hidden = !on;
}

// ───────────────────────── cards ─────────────────────────
function renderCards(r, question) {
  renderAnswer(r, question);
  renderConfidence(r);
  renderStats(r && r !== "running" ? r : null, r === "running");
}

function renderAnswer(r, question) {
  const body = $("#answerBody");
  const meta = $("#answerMeta");
  meta.textContent = "";
  if (!r) {
    body.innerHTML = `<div class="card-empty">${icon("sparkle")}<span>Ask a question or pick an example.<br>The answer and the work behind it show here.</span></div>`;
    return;
  }
  if (r === "running") {
    body.innerHTML = `<span class="verdict running">${icon("spinner")}Working on it</span>
      <div class="answer-reason" style="color:var(--text-2)">${esc(question)}</div>
      <div class="answer-foot">${icon("shield")}${state.mode === "product" ? "Careful mode · may refuse instead of guessing" : "Always-answer mode"}</div>`;
    hydrateIcons(body);
    return;
  }
  if (r.status === "error") {
    body.innerHTML = `<span class="verdict refused">${icon("alert")}Something went wrong</span><div class="answer-reason">${esc(r.reason)}</div>`;
    return;
  }
  const modeLine = `${r.mode === "product" ? "Careful" : "Always answer"} · ${r.decider === "jev" ? "Jev decider" : "local models"}`;
  meta.textContent = modeLine;
  if (r.status === "answered") {
    const rows = r.answer_rows || [], cols = r.columns || [];
    const single = rows.length === 1 && cols.length === 1;
    let main;
    if (single) {
      const v = fmtNum(rows[0][0]);
      main = `<div class="answer-value ${String(v).length > 14 ? "sm" : ""}">${esc(v)}</div><div class="sub">${esc(cols[0])}</div>`;
    } else if (!rows.length) {
      main = `<div class="answer-value">0 <small>rows</small></div><div class="sub">The query ran and matched nothing.</div>`;
    } else {
      const shown = cols.slice(0, 3);
      main = `<div class="answer-value">${rows.length.toLocaleString()}${r.truncated ? "+" : ""} <small>row${rows.length > 1 ? "s" : ""}</small></div>
        <div class="answer-rows"><table><thead><tr>${shown.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>${rows.slice(0, 50).map((row) => `<tr>${row.slice(0, 3).map((v) => `<td title="${esc(fmtNum(v))}">${esc(fmtNum(v))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }
    const more = rows.length > 50 || cols.length > 3;
    const rd = r.trace?.find((t) => t.step === "rules")?.detail;
    const defs = [...(rd?.applied || []).map((x) => `${esc(x.metric)} <span class="muted">(rule v${esc(x.version)})</span>`),
      ...(rd?.windows || []).map((w) => `“${esc(w.phrase)}” = ${esc(w.start)} to ${esc(w.end)} <span class="muted">(end exclusive)</span>`)];
    body.innerHTML = `<span class="verdict answered">${icon("checkCircle")}Answered · ${pct(r.confidence)} sure</span>${main}
      ${defs.length ? `<div class="sub" style="margin-top:6px">${icon("shield")} ${defs.join(" · ")}</div>` : ""}
      <div class="answer-foot">${icon("table")}<button class="link-btn" data-goto="table">${more ? "See every row and column" : "Open as table"}</button></div>`;
  } else if (r.status === "refused") {
    body.innerHTML = `<span class="verdict refused">${icon("xCircle")}Can’t answer reliably</span>
      <div class="answer-reason">${esc(r.reason)}</div>
      <div class="answer-foot">${icon("info")}A plausible wrong answer is worse than none.</div>`;
  } else {
    body.innerHTML = `<span class="verdict needs_clarification">${icon("help")}Needs a detail</span>
      ${threadHtml()}
      <div class="answer-reason">${esc(r.reason)}</div>
      ${r.choices?.length
        ? `<div class="choices">${r.choices.map((c) => `<button class="choice" data-choice="${esc(c.id)}"><b>${esc(c.label)}</b><span>${esc(c.detail)}</span></button>`).join("")}</div>
           <form class="own-meaning" id="ownMeaning"><input id="ownMeaningText" placeholder="Or reply in your own words, e.g. “subject wise”…" autocomplete="off"><button class="btn-primary" type="submit">Use this</button></form>`
        : `<div class="opts">${(r.options || []).map((o) => `<button class="opt" data-opt="${esc(o)}">${esc(o)}</button>`).join("")}</div>`}`;
  }
  hydrateIcons(body);
}

// the user's own definition instead of a registry option: no rule is applied and the question is not asked again
function submitOwnMeaning() {
  const text = $("#ownMeaningText")?.value.trim();
  if (!text || !state.dialog) return;
  state.dialog.answers.push(text);
  state.dialog.turns.push({ role: "user", text });
  ask(dialogQuestion(), { rounds: state.dialog.rounds });
}

// clarification chat: the original question plus every answer the user typed, until the measure is pinned down
function dialogQuestion() {
  const d = state.dialog;
  return d.answers.length ? `${d.question} (I mean: ${d.answers.join("; ")})` : d.question;
}

function threadHtml() {
  const turns = state.dialog?.turns || [];
  return turns.length > 1 ? `<div class="thread">${turns.slice(0, -1).map((t) =>
    `<div class="turn ${t.role}">${esc(t.text)}</div>`).join("")}</div>` : "";
}

function renderConfidence(r) {
  const body = $("#confBody");
  const meta = $("#confMeta");
  if (!r || r === "running" || r.status === "error" || (r.status === "needs_clarification" && !r.sql)) {
    meta.textContent = r?.status === "needs_clarification" ? "computed after you pick a measure" : "P(correct) from every signal";
    body.innerHTML = `<div class="big" style="color:var(--text-4)">${r === "running" ? "…" : "–"}</div>
      <div class="gauge"><div class="gauge-fill"></div><div class="gauge-mask" style="left:0"></div></div>
      ${legend({})}`;
    return;
  }
  const s = r.signals || {};
  const c = r.confidence ?? 0, t = r.threshold;
  meta.textContent = r.mode === "benchmark" ? "estimate · this mode never refuses"
    : t != null ? `answers above ${pct(t)} · ${r.trace?.find((x) => x.step === "decide")?.detail?.calibrated ? "calibrated" : "not calibrated yet"}` : "";
  body.innerHTML = `<div class="big">${Math.round(c * 100)}<small>%</small></div>
    <div class="gauge"><div class="gauge-fill"></div><div class="gauge-mask" style="left:${c * 100}%"></div>
      ${t != null ? `<div class="gauge-thr" style="left:${t * 100}%" title="Threshold ${pct(t)}"></div>` : ""}</div>
    ${legend(s, r.mode)}`;
}

function legend(s, mode) {
  const has = (k) => s[k] != null;
  const tone = (v, good, bad) => (v == null ? "var(--text-4)" : v >= good ? "var(--good)" : v <= bad ? "var(--critical)" : "var(--warning)");
  const flags = s.flags ? s.flags.length : s.n_flags;
  const items = [
    ["Agreement", has("vote_share") ? pct(s.vote_share) : "–", tone(s.vote_share, .6, .4)],
    ["Checks", flags == null ? "–" : flags ? `${flags} flag${flags > 1 ? "s" : ""}` : "passed", flags == null ? "var(--text-4)" : flags ? "var(--critical)" : "var(--good)"],
    ["Coverage", has("link_coverage") ? pct(s.link_coverage) : "–", tone(s.link_coverage, .5, .2)],
    ["Judge", mode === "benchmark" ? "skipped" : has("judge_yes") && s.n_groups != null ? pct(s.judge_yes) : "–", mode === "benchmark" ? "var(--text-4)" : tone(s.judge_yes, .6, .4)],
    ["Errors", has("error_rate") ? pct(s.error_rate) : "–", s.error_rate == null ? "var(--text-4)" : s.error_rate > .4 ? "var(--critical)" : s.error_rate > 0 ? "var(--warning)" : "var(--good)"],
    ["Groups", has("n_groups") ? String(s.n_groups) : "–", s.n_groups == null ? "var(--text-4)" : s.n_groups <= 1 ? "var(--good)" : s.n_groups >= 3 ? "var(--critical)" : "var(--warning)"],
  ];
  return `<div class="legend">${items.map(([k, v, c]) => `<span><i style="background:${c}"></i>${k}<em>${v}</em></span>`).join("")}</div>`;
}

// one-line run summary in the tab bar: attempts → distinct answers, agreement, repairs, total time
function renderStats(r, running = false) {
  const el = $("#stats");
  const n = state.n;
  let cands = [];
  if (r?.live) cands = r.live.map((sql) => ({ sql, pending: sql === undefined }));
  else if (r?.candidates) cands = r.candidates.map((c) => ({ ...c, group: c.group ?? -1 }));
  const finished = Boolean(r?.candidates?.length);
  const distinct = new Set(cands.filter((c) => c.group >= 0).map((c) => c.group)).size;
  const agree = cands.filter((c) => c.group === 0).length;
  const repaired = cands.filter((c) => c.repaired).length, failed = cands.filter((c) => c.error).length;
  const written = cands.filter((c) => !c.pending).length;
  const attempts = finished ? `<b>${cands.length}</b> attempts → <b>${distinct}</b> answer${distinct === 1 ? "" : "s"}`
    : r?.live ? `writing <b>${written}/${cands.length}</b>` : `<b>${n}</b> attempts`;
  const time = r?.total_seconds != null ? fmtSec(r.total_seconds) : running || r?.live || finished ? $("#statTime")?.textContent || "–" : "–";
  el.innerHTML = `<span>${icon("vote")}${attempts}</span>
    ${finished && distinct ? `<span>${icon("target")}<b>${agree}/${cands.length}</b> agree</span>` : ""}
    ${finished && (repaired || failed) ? `<span>${icon("flag")}${repaired} repaired · ${failed} failed</span>` : ""}
    <span>${icon("clock")}<b id="statTime">${time}</b></span>`;
}

// ───────────────────────── panes ─────────────────────────
function renderPanes(r) {
  const empty = (ic, text) => `<div class="empty-pane"><div>${icon(ic)}<div>${text}</div></div></div>`;
  if (!r || !r.status || r.status === "error") {
    $("#sqlPane").innerHTML = empty("code", "The SQL behind the answer will show here.");
    $("#tablePane").innerHTML = empty("table", "Result rows will show here.");
    $("#tracePane").innerHTML = empty("list", "The full step-by-step trace will show here.");
    return;
  }
  // SQL
  const cands = r.candidates || [];
  $("#sqlPane").innerHTML = r.sql ? `
    <div class="pane-head"><h4>Winning query</h4><span class="chip accent">${icon("star")}chosen by vote</span><span class="spacer"></span>
      <button class="btn-ghost" data-copy="sql">${icon("copy")}Copy</button></div>
    <pre class="code">${highlightSql(r.sql)}</pre>
    ${cands.length > 1 ? `<div class="pane-head" style="margin-top:14px"><h4>All ${cands.length} attempts</h4></div><div class="cand-list">${cands.map((c, i) => `
      <div class="cand"><div class="cand-head"><span class="attempt-n" style="background:${c.group >= 0 ? GROUP_COLORS[c.group] || "#9d9da8" : "#b9b9c2"}">${i + 1}</span>
        ${c.group === 0 ? `<span class="chip accent">winner group</span>` : c.group > 0 ? `<span class="chip">group ${c.group + 1}</span>` : ""}
        ${c.error ? `<span class="chip bad">${esc(String(c.error).slice(0, 80))}</span>` : `<span class="chip">${c.rows} row${c.rows === 1 ? "" : "s"}</span>`}
        ${c.repaired ? `<span class="chip warn">repaired</span>` : ""}</div>
        ${c.sql ? `<pre class="code">${highlightSql(c.sql)}</pre>` : `<div class="muted">No SQL in the model output.</div>`}</div>`).join("")}</div>` : ""}`
    : empty("code", "No query was produced for this question.");
  // table
  const rows = r.answer_rows || [], cols = r.columns || [];
  $("#tablePane").innerHTML = rows.length ? `
    <div class="pane-head"><h4>${rows.length.toLocaleString()} row${rows.length > 1 ? "s" : ""}</h4>${r.truncated ? `<span class="chip warn">Showing the first 1,000 rows</span>` : ""}
      <span class="spacer"></span><button class="btn-ghost" data-csv>${icon("download")}Download CSV</button></div>
    <table class="data"><thead><tr>${cols.map((c, i) => `<th data-col="${i}">${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${rows.slice(0, 1000).map((row) => `<tr>${row.map((v) => `<td>${esc(fmtNum(v))}</td>`).join("")}</tr>`).join("")}</tbody></table>`
    : empty("table", r.status === "answered" ? "The query returned no rows." : "No rows: the agent did not give an answer for this one.");
  // trace
  $("#tracePane").innerHTML = `<div class="pane-head"><h4>Trace</h4><span class="spacer"></span><button class="btn-ghost" data-copy="trace">${icon("copy")}Copy JSON</button></div>
    <pre class="code">${esc(JSON.stringify(r, null, 2))}</pre>`;
}

function sortTable(th) {
  const table = th.closest("table");
  const i = Number(th.dataset.col);
  const dir = th.dataset.dir === "asc" ? "desc" : "asc";
  $$("th", table).forEach((x) => delete x.dataset.dir);
  th.dataset.dir = dir;
  const rows = $$("tbody tr", table);
  const val = (tr) => { const t = tr.children[i].textContent.replace(/,/g, ""); const n = Number(t); return Number.isNaN(n) || t === "" ? t : n; };
  rows.sort((a, b) => { const x = val(a), y = val(b); const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y)); return dir === "asc" ? c : -c; });
  rows.forEach((r) => table.tBodies[0].appendChild(r));
}

// ───────────────────────── history ─────────────────────────
function addHistory(question, r) {
  const slim = { ...r, answer_rows: (r.answer_rows || []).slice(0, 50), trace: (r.trace || []).map((t) => ({ ...t, detail: t.step === "run" ? { ...t.detail } : t.detail })) };
  state.history = [{ id: Date.now(), q: question, db: state.db, n: state.n, status: r.status, t: Date.now(), result: slim }, ...state.history].slice(0, 25);
  store.set("history", state.history);
  renderHistory();
}

function renderHistory() {
  const items = state.history;
  $("#history").innerHTML = items.length ? items.slice(0, 25).map((h) => `
    <button class="hist-item" data-hist="${h.id}" title="${esc(h.q)}">
      <span class="status-dot ${h.status}"></span><span class="ex-text">${esc(h.q)}</span><span class="hist-time">${timeAgo(h.t)}</span>
    </button>`).join("") : `<div class="side-empty">Questions you ask appear here.</div>`;
}

function openHistory(id) {
  const h = state.history.find((x) => String(x.id) === String(id));
  if (!h) return;
  if (h.db !== state.db) selectDb(h.db);
  setView("ask");
  $("#question").value = h.q;
  autosize();
  state.n = h.n || 5;
  state.current = { question: h.q, result: h.result };
  pipeline.replay(h.q, h.result, h.n);
  renderCards(h.result, h.q);
  renderPanes(h.result);
  $$(".hist-item").forEach((b) => b.classList.toggle("is-active", b.dataset.hist === String(id)));
}

// ───────────────────────── views & tabs ─────────────────────────
function setView(v) {
  state.view = v;
  $$(".view").forEach((el) => (el.hidden = el.id !== `view-${v}`));
  $$("[data-view]").forEach((b) => b.classList.toggle("is-active", b.dataset.view === v));
  if (v === "results") renderResults($("#resultsBody"));
  if (v === "data") { $("#dataTitle").textContent = `${titleCase(state.db)}: what the profiler learned`; renderData($("#dataBody"), state.db, $("#colSearch").value); }
  if (v === "ask") pipeline.layout();
  $("#sidebar").classList.remove("is-open");
  $$(".view-scroll").forEach((el) => (el.scrollTop = 0));
}

function switchTab(t) {
  $$(".tab[data-tab]").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === t));
  $$(".pane").forEach((p) => p.classList.toggle("is-active", p.dataset.pane === t));
  if (t === "pipeline") pipeline.layout();
}

function newQuestion() {
  if (state.running) return;
  state.current = null;
  state.dialog = null;
  $("#question").value = "";
  autosize();
  pipeline.reset(state.mode);
  renderCards(null);
  renderPanes(null);
  setView("ask");
  $("#question").focus();
  $$(".hist-item").forEach((b) => b.classList.remove("is-active"));
}

function autosize() { const t = $("#question"); t.style.height = "auto"; t.style.height = `${Math.min(140, t.scrollHeight)}px`; }

// ───────────────────────── events ─────────────────────────
function bind() {
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); state.dialog = null; ask($("#question").value); });
  document.addEventListener("submit", (e) => { if (e.target.id === "ownMeaning") { e.preventDefault(); submitOwnMeaning(); } });
  $("#question").addEventListener("input", autosize);
  $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); state.dialog = null; ask($("#question").value); } });
  $("#cancelBtn").addEventListener("click", () => { state.controller?.abort(); fetch("/api/cancel", { method: "POST" }); });
  $$(".seg-btn").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  $$("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $$(".tab[data-tab]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#newQuestion").addEventListener("click", newQuestion);
  $("#dbCard").addEventListener("click", (e) => { e.stopPropagation(); $("#dbMenu").hidden ? openDbMenu() : closeDbMenu(); });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#dbMenu")) closeDbMenu();
    const db = e.target.closest("[data-db]");
    if (db && !state.running) selectDb(db.dataset.db);
    const ex = e.target.closest(".ex-item");
    if (ex) { setView("ask"); $("#question").value = ex.dataset.q; autosize(); $("#question").focus(); $$(".ex-item").forEach((b) => b.classList.toggle("is-active", b === ex)); }
    const hi = e.target.closest(".hist-item");
    if (hi) openHistory(hi.dataset.hist);
    const opt = e.target.closest("[data-opt]");
    if (opt && state.current) { const q = `${state.current.question} (${opt.dataset.opt})`; $("#question").value = q; autosize(); ask(q); }
    const ch = e.target.closest("[data-choice]");
    if (ch && state.dialog) {
      state.dialog.turns.push({ role: "user", text: ch.querySelector("b").textContent });
      ask(dialogQuestion(), { choice: ch.dataset.choice, rounds: state.dialog.rounds });
    }
    const go = e.target.closest("[data-goto]");
    if (go) switchTab(go.dataset.goto);
    const th = e.target.closest("table.data th");
    if (th) sortTable(th);
    const cp = e.target.closest("[data-copy]");
    if (cp && state.current?.result) copy(cp.dataset.copy === "sql" ? state.current.result.sql : JSON.stringify(state.current.result, null, 2));
    if (e.target.closest("[data-csv]") && state.current?.result) downloadCsv("answer.csv", state.current.result.columns, state.current.result.answer_rows);
  });
  $("#clearHistory").addEventListener("click", () => { state.history = []; store.set("history", []); renderHistory(); });
  $("#colSearch").addEventListener("input", (e) => renderData($("#dataBody"), state.db, e.target.value));
  $("#refreshResults").addEventListener("click", () => renderResults($("#resultsBody")));
  $("#menuBtn").addEventListener("click", () => $("#sidebar").classList.toggle("is-open"));
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setView("ask"); $("#question").focus(); return; }
    if (e.key === "Escape") { closeDbMenu(); $("#sidebar").classList.remove("is-open"); }
    if (e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "?") $("#shortcuts").showModal();
    if (e.key === "n") { e.preventDefault(); newQuestion(); }
    if (e.key === "1") setView("ask");
    if (e.key === "2") setView("results");
    if (e.key === "3") setView("data");
  });
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied"); } catch { toast("Couldn’t copy"); }
}
