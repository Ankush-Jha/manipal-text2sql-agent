// The live pipeline canvas: nodes, phase rail and wires. Driven by step events from /api/ask.
import { icon, hydrateIcons } from "./icons.js";
import { esc, fmtSec, pct, GROUP_COLORS } from "./util.js";

const PHASES = [
  { id: "understand", label: "Understand", icon: "search", nodes: ["question", "link", "hints", "triage"] },
  { id: "generate", label: "Generate", icon: "pen", nodes: ["write", "run", "vote"] },
  { id: "verify", label: "Verify", icon: "shield", nodes: ["checks", "judge", "decide", "verdict"] },
];
const ORDER = PHASES.flatMap((p) => p.nodes);

const NODES = {
  question: { title: "Your question", by: "You", icon: "question", desc: "Type a question in plain English. No SQL, no hints needed." },
  link: { title: "Find tables & values", by: "Linker · no model", icon: "link", desc: "Picks the tables and columns your question is about, and finds the exact stored spelling of values you mention." },
  hints: { title: "Auto-hints", by: "Profiler · no model", icon: "lightbulb", desc: "Explains codes and messy formats from the data itself, e.g. “F = exclusively virtual”. Replaces hand-written BIRD hints." },
  triage: { title: "Can the data answer?", by: "Qwen3-8B · judge", icon: "filter", desc: "Reads the question against the schema: answerable, ambiguous, data missing, or not a SQL question.", productOnly: true },
  write: { title: "Write SQL attempts", by: "Arctic-Text2SQL-R1-7B · writer", icon: "pen", desc: "Writes several independent SQL attempts. Agreement between them is a strong trust signal.", span: 2 },
  run: { title: "Run safely", by: "SQLite · read-only", icon: "play", desc: "Runs every attempt read-only, SELECT only, 10 s timeout, 1,000-row cap. One repair try on errors." },
  vote: { title: "Vote on results", by: "Majority by result set", icon: "vote", desc: "Groups attempts that return the same rows. The biggest group wins." },
  checks: { title: "Sanity checks", by: "6 rules · no model", icon: "shield", desc: "Flags empty results, all-NULL columns, % over 100, negative counts, join explosions, dates out of range." },
  judge: { title: "Double-check", by: "Qwen3-8B · judge", icon: "scale", desc: "Reads the question, SQL and first rows: does this actually answer it?", productOnly: true },
  decide: { title: "Decide", by: "Calibrated confidence", icon: "target", desc: "Combines every signal into one confidence and compares it to the threshold.", productOnly: true },
  verdict: { title: "Verdict", by: "What you get", icon: "gavel", desc: "An answer you can trust, an honest “I can’t answer”, or a clarifying question." },
};

const CHECK_LABELS = {
  zero_rows: "Has rows", all_null_column: "No empty columns", percentage_over_100: "Percent ≤ 100",
  negative_count: "No negative counts", row_explosion: "No join explosion", date_out_of_range: "Dates in range",
};

export class Pipeline {
  constructor(canvas) {
    this.canvas = canvas;
    this.flow = canvas.querySelector("#flow");
    this.rail = canvas.querySelector("#phaseRail");
    this.wires = canvas.querySelector("#wires");
    this.state = {};
    this.attempts = [];
    this.build();
    const ro = new ResizeObserver(() => this.layout());
    ro.observe(canvas);
    ro.observe(this.flow); // node heights change as steps fill in
  }

  build() {
    this.flow.innerHTML = PHASES.map((p) => `
      <div class="flow-row" data-row="${p.id}">
        ${p.nodes.map((id) => {
          const n = NODES[id];
          return `<article class="node${n.span ? " span-2" : ""}" data-node="${id}" data-state="waiting">
            <div class="node-head">
              <span class="node-ic">${icon(n.icon)}</span>
              <div><div class="node-title">${n.title}</div><div class="node-by">${n.by}</div></div>
              <span class="node-state">Waiting</span>
            </div>
            <div class="node-body"><div class="node-desc">${n.desc}</div></div>
          </article>`;
        }).join("")}
      </div>`).join("");
    this.rail.innerHTML = PHASES.map((p) => `<div class="phase" data-phase="${p.id}"><span>${p.label}</span>${icon(p.icon)}</div>`).join("");
    this.nodes = Object.fromEntries([...this.flow.querySelectorAll(".node")].map((el) => [el.dataset.node, el]));
    this.reset();
  }

  reset(mode = "product") {
    this.mode = mode;
    this.canvas.dataset.run = "idle";
    this.attempts = [];
    this.lastHints = this.lastRules = null;
    for (const id of ORDER) {
      const n = NODES[id];
      const skipped = n.productOnly && mode === "benchmark";
      this.set(id, skipped ? "skipped" : "waiting");
      this.body(id, `<div class="node-desc">${skipped ? "Skipped in “Always answer” mode: it never refuses." : n.desc}</div>`);
    }
    this.layout();
  }

  set(id, state, seconds) {
    const el = this.nodes[id];
    if (!el) return;
    this.state[id] = state;
    el.dataset.state = state;
    const tag = el.querySelector(".node-state");
    tag.innerHTML = {
      waiting: "Waiting",
      running: `${icon("spinner")}Working`,
      done: `${icon("check")}${seconds != null ? fmtSec(seconds) : "Done"}`,
      skipped: "Skipped",
      stopped: "Not needed",
      error: `${icon("x")}Failed`,
    }[state] || state;
    this.paintRail();
    this.paintWires();
  }

  body(id, html) {
    const b = this.nodes[id]?.querySelector(".node-body");
    if (b) { b.innerHTML = html; hydrateIcons(b); }
  }

  // ───── event handling ─────
  start(question, mode, n) {
    this.reset(mode);
    this.canvas.dataset.run = "running";
    this.n = n;
    this.set("question", "done");
    this.body("question", `<div class="node-question">${esc(question)}</div>
      <div class="node-foot">${icon("shield")}<b>${mode === "product" ? "Careful" : "Always answer"}</b> mode · <b>${n}</b> attempt${n > 1 ? "s" : ""}</div>`);
  }

  onStep(ev) {
    const { step, state, seconds, detail } = ev;
    if (step === "rules" && state === "done") return this.render("rules", detail);
    if (!this.nodes[step]) return;
    if (state === "start") {
      this.set(step, "running");
      if (step === "write") { this.attempts = Array(this.n).fill(undefined); this.renderWrite(); }
      return;
    }
    if (state === "progress" && step === "write") {
      this.attempts[detail.i] = detail.sql ?? null;
      this.renderWrite();
      return;
    }
    if (state === "done") {
      this.set(step, "done", seconds);
      this.render(step, detail);
    }
  }

  finish(result) {
    this.canvas.dataset.run = "finished";
    for (const id of ORDER) if (this.state[id] === "waiting" || this.state[id] === "running") this.set(id, id === "verdict" ? "done" : "stopped");
    this.set("verdict", "done");
    this.renderVerdict(result);
  }

  fail(message) {
    for (const id of ORDER) if (this.state[id] === "running") this.set(id, "error");
    this.body("verdict", `<div class="node-desc">${esc(message)}</div>`);
  }

  /** Re-draw a finished run from its trace (history). */
  replay(question, result, n) {
    this.start(question, result.mode, n || (result.candidates || []).length || 1);
    for (const t of result.trace || []) {
      if (t.step === "write") this.attempts = t.detail.sqls || [];
      this.set(t.step, "done", t.seconds);
      this.render(t.step, t.detail);
    }
    this.finish(result);
  }

  // ───── node renderers ─────
  render(step, d = {}) {
    const fn = {
      link: () => {
        const tables = (d.tables || []).map((t) => `<span class="chip">${icon("table")}${esc(t)}</span>`).join("");
        const cols = Object.entries(d.core || {}).flatMap(([t, cs]) => cs.map((c) => `<span class="chip accent mono">${esc(t)}.${esc(c)}</span>`)).slice(0, 6).join("");
        const vals = (d.values || []).slice(0, 3).map(([t, c, v]) => `<span class="chip good mono">'${esc(v)}'</span>`).join("");
        return `<div class="node-k">Tables kept</div><div class="chips">${tables || "<span class='chip'>none</span>"}</div>
          ${cols ? `<div class="node-k" style="margin-top:9px">Columns matched</div><div class="chips">${cols}</div>` : ""}
          ${vals ? `<div class="node-k" style="margin-top:9px">Stored values found</div><div class="chips">${vals}</div>` : ""}
          <div class="node-foot">Question words covered <b>${pct(d.coverage)}</b></div>`;
      },
      hints: () => {
        this.lastHints = d;
        return this.hintsHtml();
      },
      rules: () => {
        this.lastRules = d;
        this.body("hints", this.hintsHtml());
      },
      triage: () => probs(d.probs, { answerable: "Answerable", ambiguous: "Ambiguous", data_missing: "Data missing", not_sql: "Not SQL" })
        + `<div class="node-foot">Used as a soft signal only</div>`,
      write: () => this.renderWrite(true),
      run: () => {
        const c = d.candidates || [];
        const ok = c.filter((x) => !x.error).length, rep = c.filter((x) => x.repaired).length;
        return `<div class="node-grid"><div><span class="node-k">Ran</span><b>${ok}/${c.length}</b></div>
          <div><span class="node-k">Repaired</span><b>${rep}</b></div><div><span class="node-k">Failed</span><b>${c.length - ok}</b></div></div>
          ${c.filter((x) => x.error).slice(0, 2).map((x) => `<div class="chip bad mono" style="margin-top:8px">${esc(String(x.error).slice(0, 60))}</div>`).join("")}
          ${literalChips(d.literal_fixes)}
          <div class="node-foot">${icon("shield")} read-only · SELECT only · 10 s · 1,000 rows</div>`;
      },
      vote: () => {
        const total = this.n || 1;
        const run = groupsFromTrace(this);
        if (!run.length) return `<div class="node-desc">No attempt produced rows.</div>`;
        return `<div class="groups">${run.map((g, i) => `
          <div class="group"><span class="star">${i === 0 ? icon("star") : ""}</span>
            <div class="group-track">${Array.from({ length: total }, (_, k) => `<span class="group-seg" style="background:${k < g.size ? (GROUP_COLORS[i] || "#c9c9d2") : "transparent"}"></span>`).join("")}</div>
            <em>${g.size}/${total}</em></div>`).join("")}</div>
          <div class="node-foot">Winner: <b>${run[0].size}/${total}</b> attempts agree · ${run.length} distinct answer${run.length > 1 ? "s" : ""}</div>`;
      },
      checks: () => {
        const flags = new Set(d.flags || []);
        const na = { row_explosion: d.base_rows == null, date_out_of_range: d.data_range == null };
        return `<div class="checks">${Object.entries(CHECK_LABELS).map(([k, label]) =>
          `<span class="check ${flags.has(k) ? "fail" : "pass"}" ${na[k] ? 'style="opacity:.55" title="Not applicable to this query"' : ""}>${icon(flags.has(k) ? "xCircle" : "checkCircle")}${label}</span>`).join("")}</div>
          <div class="node-foot">${flags.size ? `<b>${flags.size}</b> flag${flags.size > 1 ? "s" : ""} raised` : "All checks passed"}</div>`;
      },
      judge: () => probs(d.probs, { yes: "Yes, answers it", no: "No", ambiguous: "Unsure" }),
      decide: () => {
        const c = d.confidence ?? 0, t = d.threshold ?? 0.5;
        return `<div class="decision">
          <div style="display:flex;justify-content:space-between;font-size:12px"><span>Confidence <b style="color:var(--text)">${pct(c)}</b></span><span>Threshold ${pct(t)}</span></div>
          <div class="decision-bar"><div class="decision-fill" style="width:${c * 100}%"></div><div class="decision-thr" style="left:calc(${t * 100}% - 1px)"></div></div>
          ${d.veto ? `<span class="chip bad" style="white-space:normal">${icon("xCircle")}Vetoed: triage and double-check both say the data can't answer</span>` : ""}
          <div class="node-foot">${d.calibrated ? "Calibrated on held-out questions" : "Heuristic until the calibration run is fitted"}</div></div>`;
      },
    }[step];
    if (fn) { const html = fn(); if (html !== undefined) this.body(step, html); }
    if (step === "run") this.lastRun = d;
    if (step === "vote") this.lastVote = d;
  }

  // auto-hints plus, in Careful mode, the business rules and time windows that were applied
  hintsHtml() {
    const lines = this.lastHints?.lines || [];
    const r = this.lastRules;
    const rules = (r?.applied || []).map((x) => `<li class="rule-item"><b>Rule</b> ${esc(x.metric)} · <span class="mono">${esc(x.formula)}</span> · v${esc(x.version)} ${esc(x.approval)}</li>`);
    const wins = (r?.windows || []).map((w) => `<li class="rule-item time"><b>“${esc(w.phrase)}”</b> = [${esc(w.start)}, ${esc(w.end)}) · ref ${esc(w.reference)}</li>`);
    const ask = r?.clarify ? `<li class="rule-item" style="background:var(--warning-soft);color:var(--warning-ink);border-left-color:var(--warning)"><b>Question ${r.clarify.round}:</b> what to measure is unclear, ${r.clarify.options.length} candidates left</li>` : "";
    const top = rules.length || wins.length || ask ? `<ul class="rule-list" style="list-style:none;margin:0 0 6px;padding:0">${rules.join("")}${wins.join("")}${ask}</ul>` : "";
    if (!lines.length) return top + `<div class="node-desc">No special codes or messy formats for the matched columns.</div>`;
    return `${top}<ul class="hint-list">${lines.filter((l) => !l.startsWith("Business rule") && !l.startsWith("Time window")).slice(0, 8).map((l) => {
          const m = l.match(/^([\w$ ().\/-]+?\.[\w$ ()\/-]+?)(:| )(.*)$/);
          return `<li>${m ? `<b>${esc(m[1])}</b>${esc(m[2] === ":" ? ":" : "")} ${esc(m[3])}` : esc(l)}</li>`;
        }).join("")}</ul><div class="node-foot"><b>${lines.length}</b> hint${lines.length > 1 ? "s" : ""} written from the data${rules.length ? `, <b>${rules.length}</b> business rule${rules.length > 1 ? "s" : ""}` : ""}</div>`;
  }

  renderWrite(final = false) {
    const n = this.attempts.length || this.n || 0;
    const groupOf = (sql) => {
      const gs = this.lastRun?.groups || [];
      const gi = gs.findIndex((g) => g.sqls.includes(sql));
      return gi;
    };
    const rows = Array.from({ length: n }, (_, i) => {
      const sql = this.attempts[i];
      const gi = sql ? groupOf(sql) : -1;
      const color = sql === undefined ? "var(--text-4)" : sql === null ? "#b9b9c2" : (gi >= 0 ? GROUP_COLORS[gi] || "#9d9da8" : "var(--accent)");
      return `<div class="attempt"><span class="attempt-n" style="background:${color}">${i + 1}</span>
        ${sql === undefined ? `<span class="loading"></span>` : sql === null ? `<code style="color:var(--text-3)">no SQL block in the output</code>` : `<code title="${esc(sql)}">${esc(oneLine(sql))}</code>`}
        <span class="attempt-tag">${sql === undefined ? "writing…" : sql === null ? "empty" : "ready"}</span></div>`;
    }).join("");
    const html = `<div class="attempt-list">${rows}</div>
      <div class="node-foot">${this.attempts.filter((x) => x !== undefined).length}/${n} written · temperature 0.8 · verbatim OmniSQL prompt</div>`;
    if (final) return html;
    this.body("write", html);
  }

  renderVerdict(r) {
    const el = this.nodes.verdict;
    el.classList.add("verdict-node");
    el.dataset.status = r.status;
    const label = { answered: "Answered", refused: "Can’t answer reliably", needs_clarification: "Needs a detail" }[r.status];
    const ic = { answered: "checkCircle", refused: "xCircle", needs_clarification: "help" }[r.status];
    this.body("verdict", `<span class="verdict ${r.status}">${icon(ic)}${label}</span>
      <div class="node-desc" style="margin-top:8px;color:var(--text-2)">${r.status === "answered"
        ? `${(r.answer_rows || []).length} row${(r.answer_rows || []).length === 1 ? "" : "s"} · confidence ${pct(r.confidence)}`
        : esc(r.reason || "")}</div>
      <div class="node-foot">${r.total_seconds ? `Total <b>${fmtSec(r.total_seconds)}</b>` : ""}</div>`);
    // re-render write rows now that groups are known
    if (this.attempts.length) this.body("write", this.renderWrite(true));
  }

  // ───── layout: phase rail + wires ─────
  layout() {
    requestAnimationFrame(() => { this.placeRail(); this.paintWires(); });
  }

  placeRail() {
    const c = this.canvas.getBoundingClientRect();
    for (const p of PHASES) {
      const row = this.flow.querySelector(`[data-row="${p.id}"]`);
      const seg = this.rail.querySelector(`[data-phase="${p.id}"]`);
      if (!row || !seg) continue;
      const r = row.getBoundingClientRect();
      const railTop = this.rail.getBoundingClientRect().top;
      seg.style.top = `${r.top - railTop}px`;
      seg.style.height = `${r.height}px`;
    }
    this.paintRail();
    void c;
  }

  paintRail() {
    for (const p of PHASES) {
      const seg = this.rail.querySelector(`[data-phase="${p.id}"]`);
      if (!seg) continue;
      const st = p.nodes.map((id) => this.state[id]);
      seg.classList.toggle("on", st.includes("running"));
      seg.classList.toggle("done", !st.includes("running") && st.every((s) => s === "done" || s === "skipped" || s === "stopped") && st.includes("done"));
    }
  }

  paintWires() {
    const c = this.canvas.getBoundingClientRect();
    if (!c.width) return;
    this.wires.setAttribute("viewBox", `0 0 ${c.width} ${c.height}`);
    const box = (id) => {
      const r = this.nodes[id].getBoundingClientRect();
      return { l: r.left - c.left, r: r.right - c.left, t: r.top - c.top, b: r.bottom - c.top, cx: r.left - c.left + r.width / 2, cy: r.top - c.top + Math.min(r.height / 2, 34) };
    };
    const rowOf = (id) => PHASES.findIndex((p) => p.nodes.includes(id));
    let out = "";
    for (let i = 0; i < ORDER.length - 1; i++) {
      const a = ORDER[i], b = ORDER[i + 1];
      const A = box(a), B = box(b);
      const sa = this.state[a], sb = this.state[b];
      const cls = sb === "running" ? "on" : (sa !== "waiting" && sb !== "waiting" && sb !== "running") ? "done" : "";
      let d, p1, p2;
      if (rowOf(a) === rowOf(b) && Math.abs(A.cy - B.cy) < 60) {
        p1 = [A.r + 6, A.cy]; p2 = [B.l - 6, B.cy];
        d = `M${p1[0]},${p1[1]} H${p2[0]}`;
      } else {
        // route through the gap between the two rows, below the tallest card of the upper row
        const rowA = this.flow.querySelector(`[data-row="${PHASES[rowOf(a)].id}"]`).getBoundingClientRect();
        const rowB = this.flow.querySelector(`[data-row="${PHASES[rowOf(b)].id}"]`).getBoundingClientRect();
        const mid = (rowA.bottom - c.top + rowB.top - c.top) / 2, r = 10;
        p1 = [A.cx, A.b + 6]; p2 = [B.cx, B.t - 6];
        const dir = p2[0] < p1[0] ? -1 : 1;
        d = `M${p1[0]},${p1[1]} V${mid - r} Q${p1[0]},${mid} ${p1[0] + dir * r},${mid} H${p2[0] - dir * r} Q${p2[0]},${mid} ${p2[0]},${mid + r} V${p2[1]}`;
      }
      out += `<path class="${cls}" d="${d}"/><circle class="${cls}" cx="${p1[0]}" cy="${p1[1]}" r="3"/><circle class="${cls}" cx="${p2[0]}" cy="${p2[1]}" r="3"/>`;
    }
    this.wires.innerHTML = out;
  }
}

// values the model invented that were corrected to the stored spelling (no model involved)
function literalChips(list = []) {
  const seen = new Map();
  for (const a of list) for (const f of a.fixes) seen.set(`${f.column}|${f.was}|${f.now}`, f);
  if (!seen.size) return "";
  return `<div class="node-k" style="margin-top:9px">Value fixed to the stored spelling</div><div class="chips">${[...seen.values()].slice(0, 3).map((f) =>
    `<span class="chip good mono" title="${esc(f.column)}: ${esc(f.why)}">${esc(f.was)} → ${esc(f.now)}</span>`).join("")}</div>`;
}

function probs(p = {}, labels) {
  const best = Object.entries(p).sort((a, b) => b[1] - a[1])[0]?.[0];
  return `<div class="probs">${Object.entries(labels).map(([k, label]) => `
    <div class="prob"><span style="${k === best ? "color:var(--text);font-weight:500" : ""}">${label}</span>
      <div class="prob-track"><div class="prob-fill" style="width:${(p[k] || 0) * 100}%"></div></div><em>${pct(p[k] || 0)}</em></div>`).join("")}</div>`;
}

function groupsFromTrace(pipe) { return pipe.lastRun?.groups || []; }
function oneLine(sql) { return String(sql).replace(/\s+/g, " ").trim(); }
