// Small shared helpers.
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const pct = (x) => (x == null || Number.isNaN(x) ? "–" : `${Math.round(x * 100)}%`);
export const fmtSec = (s) => (s == null ? "–" : s < 1 ? `${Math.round(s * 1000)} ms` : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);
export const fmtNum = (v) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 3 })) : v === null ? "NULL" : String(v));
export const titleCase = (id) => id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const timeAgo = (t) => {
  const s = Math.round((Date.now() - t) / 1000);
  return s < 60 ? "now" : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`;
};
// winner group, runner-up, third; anything later is neutral
export const GROUP_COLORS = ["#7c5cf0", "#eb6834", "#1baf7a"];

const KW = /\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|AS|ON|JOIN|INNER|LEFT|RIGHT|OUTER|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|DISTINCT|UNION|ALL|EXCEPT|INTERSECT|WITH|CASE|WHEN|THEN|ELSE|END|ASC|DESC|LIKE|BETWEEN|CAST|EXISTS)\b/gi;
const FN = /\b(COUNT|SUM|AVG|MIN|MAX|ROUND|SUBSTR|STRFTIME|IIF|COALESCE|IFNULL|LENGTH|UPPER|LOWER|ABS|REAL|INTEGER|TEXT)\s*(?=\()/gi;

export function prettySql(sql) {
  if (!sql) return "";
  let s = String(sql).replace(/\s+/g, " ").trim();
  s = s.replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|INNER JOIN|LEFT JOIN|JOIN|UNION|EXCEPT|INTERSECT)\b/gi, "\n$1");
  s = s.replace(/\s+(AND|OR)\b/g, "\n  $1");
  return s;
}

export function highlightSql(sql) {
  // tokenise strings first so keywords inside quotes are left alone
  return prettySql(sql).split(/('(?:[^']|'')*')/g).map((part, i) => {
    if (i % 2) return `<span class="str">${esc(part)}</span>`;
    return esc(part)
      .replace(FN, (m) => `<span class="fn">${m}</span>`)
      .replace(KW, (m) => `<span class="kw">${m.toUpperCase()}</span>`)
      .replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="num">$1</span>');
  }).join("");
}

let toastTimer;
export function toast(msg, ms = 2600) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), ms);
}

export function tooltip(html, x, y) {
  const el = document.getElementById("tooltip");
  if (!html) { el.hidden = true; return; }
  el.innerHTML = html;
  el.hidden = false;
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, x + 12))}px`;
  el.style.top = `${Math.max(8, y - h - 12)}px`;
}

export const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode or full */ } },
};

export function downloadCsv(name, columns, rows) {
  const cell = (v) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = [columns.map(cell).join(","), ...rows.map((r) => r.map(cell).join(","))].join("\n");
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
