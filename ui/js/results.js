// Results view: the measured numbers, read live from /api/results.
import { icon, hydrateIcons } from "./icons.js";
import { esc, tooltip } from "./util.js";

const AGENT = "var(--series-1)";
const PLAIN = "var(--series-2)";
const OUTCOMES = [
  ["correct", "Correct answer", "var(--good)", "checkCircle"],
  ["refused_unanswerable", "Rightly refused", "var(--series-3)", "shield"],
  ["refused_answerable", "Refused, could have answered", "#c9c9d2", "minus"],
  ["wrong", "Wrong answer", "var(--critical)", "xCircle"],
  ["answered_unanswerable", "Answered the unanswerable", "var(--serious)", "alert"],
];

export async function renderResults(root) {
  root.innerHTML = `<div class="r-empty">${icon("spinner")}</div>`;
  let d;
  try { d = await (await fetch("/api/results")).json(); }
  catch { root.innerHTML = `<div class="r-empty">Couldn’t load results.</div>`; return; }
  const a = d.accuracy || {};
  const ex = (k) => a[k]?.ex;
  const n = (k) => a[k]?.n || 0;
  const pending = (k) => (n(k) && n(k) < (d.split?.report || 150) ? ` <small>n=${n(k)}, still running</small>` : n(k) ? ` <small>n=${n(k)}</small>` : "");

  const gain = d.gain?.no_hints;
  root.innerHTML = `
  <div class="r-grid">
    <div class="r-card w3"><h3>No-hint gain</h3>
      <div class="kpi ${gain > 0 ? "pos" : ""}">${gain == null ? "–" : `${gain > 0 ? "+" : ""}${gain}`}<small>points</small></div>
      <div class="kpi-sub">${gain == null ? "Needs the agent run on the same 150 questions" : `Full agent vs plain model on the same ${d.gain.n_no_hints} questions, no hand-written hints`}</div></div>
    <div class="r-card w3"><h3>Plain model · no hints</h3>
      <div class="kpi">${ex("plain_no_hints") ?? "–"}<small>% EX</small></div><div class="kpi-sub">Arctic-R1-7B, one greedy pass${pending("plain_no_hints")}</div></div>
    <div class="r-card w3"><h3>Full agent · no hints</h3>
      <div class="kpi">${ex("agent_no_hints") ?? "–"}<small>% EX</small></div><div class="kpi-sub">5 attempts, auto-hints, vote${pending("agent_no_hints")}</div></div>
    <div class="r-card w3"><h3>Reliability score</h3>
      <div class="kpi">${d.refusal ? d.refusal.score_c1.toFixed(2) : "–"}</div>
      <div class="kpi-sub">${d.refusal ? `TrustSQL-style, c=1 · refuse-everything scores ${d.refusal.naive_refuse_all.toFixed(2)}` : "Needs the Careful-mode and unanswerable runs"}</div></div>

    <div class="r-card w8"><h3>Accuracy on the 150 reporting questions</h3>
      <p class="takeaway">${takeaway(a, d.gain)}</p>
      <div class="legend-row"><span><i style="background:${AGENT}"></i>Full agent</span><span><i style="background:${PLAIN}"></i>Plain model</span><span><i style="border:1.5px dashed var(--text-4)"></i>Not run yet</span></div>
      <div class="chart" id="accChart"></div></div>
    <div class="r-card w4"><h3>By difficulty</h3><p class="takeaway">Execution accuracy (%), no hints.</p>${difficultyTable(a)}</div>

    <div class="r-card w8"><h3>Answered vs wrong</h3>
      <p class="takeaway">${d.risk_coverage?.length ? "Raise the bar and the agent answers fewer questions, but gets fewer of them wrong. Drag to pick a threshold." : "This risk–coverage curve appears once the confidence model is fitted on the 350 calibration questions."}</p>
      <div class="chart" id="rcChart"></div>
      ${d.risk_coverage?.length ? `<div class="slider-row"><span>Threshold</span><input type="range" id="thr" min="0" max="${d.risk_coverage.length - 1}" value="${Math.floor(d.risk_coverage.length / 2)}"><span id="thrOut" style="min-width:210px;text-align:right"></span></div>` : ""}</div>
    <div class="r-card w4"><h3>Saying no correctly</h3>${refusalBlock(d.refusal)}</div>

    <div class="r-card w6"><div class="note">${icon("alert")}<div><b style="color:var(--text)">An honest note on the benchmark</b><br>
      About half of BIRD Mini-Dev labels have known errors (Jin et al.), so we report <b>gains over the plain model on the same questions</b>, not leaderboard ranks.
      <details class="more"><summary>Example of a questionable label</summary>
      <p>Q1399 “Did Maya Mclean attend the Women’s Soccer event?” The gold query returns 14 rows of “YES” and NULL, while a direct yes/no answer scores as wrong.</p></details></div></div></div>
    <div class="r-card w6"><h3>Speed and where it runs</h3>
      <table class="mini-table"><tr><th>Run</th><th>Seconds / question</th></tr>
        <tr><td>Plain model, 1 attempt</td><td>${d.latency?.plain_seconds_mean ?? "–"}</td></tr>
        <tr><td>Full agent, 5 attempts</td><td>${d.latency?.agent_seconds_mean ?? "–"}</td></tr></table>
      <div class="kpi-sub" style="margin-top:10px">${icon("shield")} ${esc(d.latency?.where || "")}. No data leaves the machine.</div></div>
  </div>`;
  hydrateIcons(root);
  accuracyChart(root.querySelector("#accChart"), a);
  if (d.risk_coverage?.length) riskCoverage(root.querySelector("#rcChart"), d.risk_coverage, root.querySelector("#thr"), root.querySelector("#thrOut"));
  else root.querySelector("#rcChart").innerHTML = `<div class="r-empty">No calibration run yet.</div>`;
  const badge = document.getElementById("resultsBadge");
  if (badge) badge.textContent = gain != null ? `${gain > 0 ? "+" : ""}${gain} pts` : n("plain_no_hints") ? "Running" : "";
}

function takeaway(a, g) {
  if (g?.no_hints != null) return `Without hand-written hints the agent scores ${g.no_hints > 0 ? `${g.no_hints} points higher` : `${Math.abs(g.no_hints)} points lower`} than the plain model on the same questions.`;
  if (a.plain_no_hints) return `The plain model scores ${a.plain_no_hints.ex}% with no hints so far. The agent bars fill in when its run finishes.`;
  return "Bars fill in as the evaluation runs finish.";
}

function difficultyTable(a) {
  const rows = ["simple", "moderate", "challenging"];
  const p = a.plain_no_hints?.by_difficulty || {}, g = a.agent_no_hints?.by_difficulty || {};
  return `<table class="mini-table"><tr><th>Difficulty</th><th>Plain</th><th>Agent</th></tr>
    ${rows.map((r) => `<tr><td>${r[0].toUpperCase() + r.slice(1)}</td><td>${p[r] ?? "–"}</td><td>${g[r] ?? "–"}</td></tr>`).join("")}</table>`;
}

function refusalBlock(r) {
  if (!r) return `<p class="takeaway">Scored the TrustSQL way: a correct answer or a correct refusal earns a point, a wrong answer loses one. Appears after the Careful-mode run on the 150 questions plus the unanswerable set.</p><div class="r-empty">Not run yet.</div>`;
  const total = r.n || 1;
  return `<p class="takeaway">${r.n} questions: answerable ones plus questions the data can’t answer.</p>
    <div class="outcomes">${OUTCOMES.map(([k, label, c]) => r.counts[k] ? `<div style="flex:${r.counts[k]};background:${c}" title="${label}: ${r.counts[k]}"></div>` : "").join("")}</div>
    <table class="mini-table">${OUTCOMES.map(([k, label, c, ic]) => `<tr><td><span style="display:inline-flex;align-items:center;gap:6px"><i style="width:9px;height:9px;border-radius:3px;background:${c};display:inline-block"></i>${label}</span></td><td style="text-align:right">${r.counts[k] || 0} <span class="muted">(${Math.round(100 * (r.counts[k] || 0) / total)}%)</span></td></tr>`).join("")}</table>
    <table class="mini-table" style="margin-top:12px"><tr><th>Penalty for a wrong answer</th><th style="text-align:right">Score</th></tr>
      <tr><td>c = 1</td><td style="text-align:right">${r.score_c1.toFixed(3)}</td></tr><tr><td>c = 5</td><td style="text-align:right">${r.score_c5.toFixed(3)}</td></tr>
      <tr><td>c = 10</td><td style="text-align:right">${r.score_c10.toFixed(3)}</td></tr><tr><td class="muted">Refuse everything</td><td style="text-align:right" class="muted">${r.naive_refuse_all.toFixed(3)}</td></tr></table>`;
}

// ───── grouped bars: condition (no hints / with hints) × system ─────
function accuracyChart(el, a) {
  const W = el.clientWidth || 640, H = 260, m = { t: 22, r: 10, b: 34, l: 40 };
  const groups = [["No hints", "agent_no_hints", "plain_no_hints"], ["With BIRD hints", "agent_hints", "plain_hints"]];
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const y = (v) => m.t + ih - (v / 100) * ih;
  const gw = iw / groups.length, bw = Math.min(56, gw / 4), gap = 2;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Execution accuracy by system and hint condition">`;
  for (const t of [0, 25, 50, 75, 100]) svg += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--text-3)">${t}%</text>`;
  svg += `<line class="axis" x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}"/>`;
  groups.forEach(([label, ak, pk], gi) => {
    const cx = m.l + gw * gi + gw / 2;
    [[ak, AGENT, "Full agent"], [pk, PLAIN, "Plain model"]].forEach(([k, color, name], bi) => {
      const x = cx - bw - gap / 2 + bi * (bw + gap);
      const v = a[k]?.ex;
      if (v == null) {
        svg += `<rect x="${x + .75}" y="${y(100) + .75}" width="${bw - 1.5}" height="${ih - 1.5}" rx="4" fill="none" stroke="var(--text-4)" stroke-dasharray="4 4"/>
          <text x="${x + bw / 2}" y="${y(50)}" text-anchor="middle" font-size="10.5" fill="var(--text-3)" transform="rotate(-90 ${x + bw / 2} ${y(50)})">not run yet</text>`;
      } else {
        const h = Math.max(1, ih - (y(v) - m.t));
        svg += `<path class="hit" data-tip="<b>${name}</b> · ${label}<br>${v}% EX on ${a[k].n} questions" d="M${x},${y(0)} V${y(v) + 4} Q${x},${y(v)} ${x + 4},${y(v)} H${x + bw - 4} Q${x + bw},${y(v)} ${x + bw},${y(v) + 4} V${y(0)} Z" fill="${color}"/>
          <text x="${x + bw / 2}" y="${y(v) - 7}" text-anchor="middle" font-size="12" font-weight="600" fill="var(--text)">${v}%</text>`;
        void h;
      }
    });
    svg += `<text x="${cx}" y="${H - 10}" text-anchor="middle" font-size="12.5" fill="var(--text-2)">${label}</text>`;
  });
  el.innerHTML = svg + "</svg>";
  el.querySelectorAll(".hit").forEach((p) => {
    p.addEventListener("mousemove", (e) => tooltip(p.dataset.tip, e.clientX, e.clientY));
    p.addEventListener("mouseleave", () => tooltip(null));
  });
}

// ───── risk–coverage line with crosshair + threshold marker ─────
function riskCoverage(el, pts, slider, out) {
  const data = [...pts].sort((p, q) => p.coverage - q.coverage);
  const W = el.clientWidth || 640, H = 260, m = { t: 16, r: 14, b: 36, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const ymax = Math.max(.2, Math.ceil(Math.max(...data.map((d) => d.error)) * 10) / 10);
  const x = (v) => m.l + v * iw, y = (v) => m.t + ih - (v / ymax) * ih;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Error rate against share of questions answered">`;
  for (let t = 0; t <= ymax + 1e-9; t += ymax / 4) svg += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--text-3)">${Math.round(t * 100)}%</text>`;
  for (const t of [0, .25, .5, .75, 1]) svg += `<text x="${x(t)}" y="${H - 16}" text-anchor="middle" font-size="11" fill="var(--text-3)">${t * 100}%</text>`;
  svg += `<text x="${m.l + iw / 2}" y="${H - 2}" text-anchor="middle" font-size="11" fill="var(--text-2)">share of questions answered →</text>`;
  svg += `<path d="${data.map((d, i) => `${i ? "L" : "M"}${x(d.coverage)},${y(d.error)}`).join(" ")}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>`;
  svg += `<line id="rcX" y1="${m.t}" y2="${m.t + ih}" stroke="var(--text-4)" stroke-dasharray="3 3" visibility="hidden"/>`;
  svg += `<circle id="rcDot" r="5" fill="var(--series-1)" stroke="#fff" stroke-width="2"/>`;
  el.innerHTML = svg + "</svg>";
  const s = el.querySelector("svg"), dot = el.querySelector("#rcDot"), cross = el.querySelector("#rcX");
  const byThr = [...pts].sort((p, q) => p.threshold - q.threshold);
  const place = (d) => { dot.setAttribute("cx", x(d.coverage)); dot.setAttribute("cy", y(d.error)); };
  const show = () => { const d = byThr[slider.value]; place(d); out.innerHTML = `answers <b>${Math.round(d.coverage * 100)}%</b>, wrong on <b>${Math.round(d.error * 100)}%</b> of those`; };
  slider?.addEventListener("input", show);
  show();
  s.addEventListener("mousemove", (e) => {
    const r = s.getBoundingClientRect();
    const cov = Math.min(1, Math.max(0, (e.clientX - r.left - m.l) / iw));
    const d = data.reduce((b, p) => (Math.abs(p.coverage - cov) < Math.abs(b.coverage - cov) ? p : b), data[0]);
    cross.setAttribute("x1", x(d.coverage)); cross.setAttribute("x2", x(d.coverage)); cross.setAttribute("visibility", "visible");
    tooltip(`Threshold <b>${d.threshold.toFixed(2)}</b><br>Answers ${Math.round(d.coverage * 100)}% · wrong on ${Math.round(d.error * 100)}%`, e.clientX, e.clientY);
  });
  s.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); tooltip(null); });
}
