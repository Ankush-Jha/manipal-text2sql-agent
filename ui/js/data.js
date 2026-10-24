// Data view: what the profiler learned about the selected database.
import { icon } from "./icons.js";
import { esc } from "./util.js";

const cache = {};
const rulesCache = {};

export async function renderData(root, db, filter = "") {
  if (!cache[db]) {
    root.innerHTML = `<div class="r-empty">${icon("spinner")}</div>`;
    try {
      [cache[db], rulesCache[db]] = await Promise.all([
        fetch(`/api/profile?db=${encodeURIComponent(db)}`).then((r) => r.json()),
        fetch(`/api/rules?db=${encodeURIComponent(db)}`).then((r) => r.json()).catch(() => null),
      ]);
    } catch { root.innerHTML = `<div class="r-empty">Couldn’t load the profile.</div>`; return; }
  }
  const f = filter.trim().toLowerCase();
  const tables = cache[db].tables.map((t) => ({
    ...t, columns: t.columns.filter((c) => !f || c.name.toLowerCase().includes(f) || c.description.toLowerCase().includes(f) || t.name.toLowerCase().includes(f)),
  })).filter((t) => t.columns.length);
  const issues = cache[db].tables.flatMap((t) => t.columns).filter((c) => c.dirty.length || c.mixed_dates || c.null_rate > .5).length;
  root.innerHTML = `
    <div class="legend-row" style="margin-bottom:16px">
      <span>${icon("table")} ${cache[db].tables.length} tables</span>
      <span>${icon("layers")} ${cache[db].tables.reduce((s, t) => s + t.columns.length, 0)} columns</span>
      <span style="color:var(--warning-ink)">${icon("alert")} ${issues} messy column${issues === 1 ? "" : "s"} flagged</span>
    </div>
    ${rulesBlock(rulesCache[db])}
    ${tables.length ? `<div class="d-grid">${tables.map((t) => `
      <section class="d-table">
        <header><span class="node-ic">${icon("table")}</span><h3>${esc(t.name)}</h3><span>${t.rows.toLocaleString()} rows · ${t.columns.length} columns</span></header>
        ${t.columns.map((c) => `
          <div class="d-col" title="${esc(c.values || c.description)}">
            <div style="min-width:0"><div class="d-name">${esc(c.name)}</div><div class="d-desc">${esc(c.description || "—")}</div></div>
            <div><div class="null-bar"><i style="width:${Math.round(c.null_rate * 100)}%"></i></div><div class="d-null">${Math.round(c.null_rate * 100)}% empty</div></div>
            <div class="chips">
              <span class="chip mono">${esc(c.type || "?")}</span>
              <span class="chip">${c.distinct.toLocaleString()} distinct</span>
              ${c.values ? `<span class="chip accent">coded</span>` : ""}
              ${c.dirty.map((d) => `<span class="chip warn">“${esc(d)}”</span>`).join("")}
              ${c.mixed_dates ? `<span class="chip warn">mixed dates</span>` : c.date_formats.length ? `<span class="chip">${esc(c.date_formats[0])} date</span>` : ""}
            </div>
          </div>`).join("")}
      </section>`).join("")}</div>` : `<div class="r-empty">No columns match “${esc(filter)}”.</div>`}`;
}

// Business Rules Registry: approved metric definitions, checked against the real columns
function rulesBlock(reg) {
  if (!reg || !reg.rules?.length) return "";
  const conv = reg.conventions || {};
  return `<section class="d-table rules-block">
    <header><span class="node-ic">${icon("shield")}</span><h3>Business rules</h3>
      <span>${reg.rules.filter((r) => r.available).length} approved and computable · the judge model picks the measure, no keyword lists · applied in Careful mode</span></header>
    <div class="rules-conv">${[
      conv.reference_date && `Relative dates count from <b>${conv.reference_date === "data_max" ? `latest ${esc(conv.date_column || "date")}` : esc(conv.reference_date)}</b>`,
      conv.timezone && `timezone <b>${esc(conv.timezone)}</b>`,
      conv.fiscal_year_start_month && `fiscal year starts month <b>${conv.fiscal_year_start_month}</b>`,
      conv.end_exclusive && `ranges are <b>[start, end)</b>`,
    ].filter(Boolean).join(" · ")}</div>
    <table class="mini-table rules-table"><tr><th>Metric</th><th>Formula</th><th>Owner · version</th><th>Status</th></tr>
      ${reg.rules.map((r) => `<tr title="${esc(r.definition)}">
        <td><b>${esc(r.metric)}</b><div class="d-desc">${esc(r.time_basis || "")}</div></td>
        <td><code>${esc(r.formula)}</code></td>
        <td>${esc(r.owner)} · v${esc(r.version)}</td>
        <td>${r.available ? `<span class="chip good">approved</span>` : r.missing_columns?.length ? `<span class="chip bad" title="Missing: ${esc(r.missing_columns.join(", "))}">no such column</span>` : `<span class="chip warn">${esc(r.approval)}</span>`}</td>
      </tr>`).join("")}
    </table>
  </section>`;
}
