// Line icons (24px grid, 1.6 stroke) and the colourful database tiles.
const s = (body, extra = "") =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}>${body}</svg>`;

export const ICONS = {
  logo: `<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M24 3 42.2 13.5v21L24 45 5.8 34.5v-21Z" fill="#111"/><path d="M15 16.5h18v15H15z" fill="#fff" transform="rotate(45 24 24)"/><path d="M19 19h10v10H19z" fill="#111" transform="rotate(45 24 24)"/></svg>`,
  logoTile: `<svg viewBox="0 0 36 36" aria-hidden="true"><rect x="7" y="7" width="22" height="3.4" rx="1.2" fill="#fff"/><rect x="7" y="26" width="22" height="3.4" rx="1.2" fill="#fff"/><rect x="10" y="12" width="3.4" height="12" rx="1.2" fill="#fff"/><rect x="16.3" y="12" width="3.4" height="12" rx="1.2" fill="#fff"/><rect x="22.6" y="12" width="3.4" height="12" rx="1.2" fill="#fff"/></svg>`,
  menu: s(`<path d="M4 7h16M4 12h16M4 17h16"/>`),
  grid: s(`<rect x="4" y="4" width="6.5" height="6.5" rx="2"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="2"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="2"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="2"/>`),
  chart: s(`<path d="M4 20h16"/><rect x="6" y="11" width="3" height="6.5" rx="1"/><rect x="11" y="6" width="3" height="11.5" rx="1"/><rect x="16" y="13" width="3" height="4.5" rx="1"/>`),
  table: s(`<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M3.5 9.5h17M9.5 9.5v10"/>`),
  more: s(`<circle cx="6" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="18" cy="12" r="1.2" fill="currentColor"/>`),
  shield: s(`<path d="M12 3.5 19 6v5.5c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6Z"/><path d="m9.2 12 2 2 3.8-4"/>`),
  lock: s(`<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5"/>`),
  plus: s(`<path d="M12 5v14M5 12h14"/>`, `stroke-width="1.8"`),
  keyboard: s(`<rect x="3" y="6" width="18" height="12" rx="3"/><path d="M7 10h.01M10.5 10h.01M14 10h.01M17.5 10h.01M8 14.5h8"/>`),
  chevronDown: s(`<path d="m6 9 6 6 6-6"/>`),
  search: s(`<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>`),
  home: s(`<path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19Z"/><path d="M10 20.5v-5h4v5"/>`),
  layers: s(`<path d="m12 4 8.5 4.5L12 13 3.5 8.5Z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5"/><path d="m3.5 16.5 8.5 4.5 8.5-4.5"/>`),
  sparkle: s(`<path d="M12 3.5 13.8 9a2 2 0 0 0 1.2 1.2l5.5 1.8-5.5 1.8a2 2 0 0 0-1.2 1.2L12 20.5 10.2 15A2 2 0 0 0 9 13.8L3.5 12 9 10.2A2 2 0 0 0 10.2 9Z"/>`),
  target: s(`<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.2"/><circle cx="12" cy="12" r=".9" fill="currentColor"/>`),
  branch: s(`<circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="8" r="2.2"/><path d="M6 8.2v7.6M18 10.2c0 4-5 3.4-10.4 6.6"/>`),
  clock: s(`<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>`),
  calendar: s(`<rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M9 3v4M15 3v4"/>`),
  diagram: s(`<rect x="3.5" y="4" width="7" height="6" rx="2"/><rect x="13.5" y="14" width="7" height="6" rx="2"/><path d="M7 10v4.5a2 2 0 0 0 2 2h4.5"/>`),
  code: s(`<path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.5 5.5l-3 13"/>`),
  list: s(`<path d="M9 7h11M9 12h11M9 17h11"/><circle cx="4.8" cy="7" r=".9" fill="currentColor"/><circle cx="4.8" cy="12" r=".9" fill="currentColor"/><circle cx="4.8" cy="17" r=".9" fill="currentColor"/>`),
  database: s(`<ellipse cx="12" cy="6" rx="7.5" ry="2.8"/><path d="M4.5 6v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8V6"/><path d="M4.5 12v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-6"/>`),
  copy: s(`<rect x="8.5" y="8.5" width="11" height="11" rx="2.5"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>`),
  download: s(`<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>`),
  x: s(`<path d="M6 6l12 12M18 6 6 18"/>`),
  check: s(`<path d="m5 12.5 4.5 4.5L19 7.5"/>`, `stroke-width="2"`),
  checkCircle: s(`<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.2 2.4 2.4 4.8-5"/>`),
  xCircle: s(`<circle cx="12" cy="12" r="8.5"/><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6"/>`),
  alert: s(`<path d="M12 4 21 19.5H3Z"/><path d="M12 10v4M12 17h.01"/>`),
  help: s(`<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2-2.4 3.6M12 17h.01"/>`),
  info: s(`<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>`),
  refresh: s(`<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 9"/><path d="M19.5 4.5V9H15"/>`),
  flag: s(`<path d="M5.5 20.5v-16"/><path d="M5.5 4.5h11l-2 4 2 4h-11"/>`, `fill="none"`),
  question: s(`<path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8.5A1.5 1.5 0 0 1 19 17h-8l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V7A1.5 1.5 0 0 1 5 5.5Z"/>`),
  link: s(`<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>`),
  lightbulb: s(`<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z"/>`),
  filter: s(`<path d="M4 5h16l-6 7.5V19l-4 1.5v-8Z"/>`),
  pen: s(`<path d="M14.5 5.5 18.5 9.5 9 19H5v-4Z"/><path d="m12.5 7.5 4 4"/>`),
  play: s(`<path d="M7 5v14l11-7Z"/>`),
  vote: s(`<rect x="4" y="11" width="16" height="9" rx="2"/><path d="M8 11V6.5a1.5 1.5 0 0 1 1.5-1.5h5A1.5 1.5 0 0 1 16 6.5V11M9.5 8.5l1.7 1.7 3.3-3.3"/>`),
  scale: s(`<path d="M12 4v16M7 20h10M5 8h14"/><path d="m5 8-2.5 6a3 3 0 0 0 5 0Zm14 0-2.5 6a3 3 0 0 0 5 0Z"/>`),
  gavel: s(`<path d="m14 5 5 5M11.5 7.5l5 5M12.8 6.2l3.5-3.5 5 5-3.5 3.5"/><path d="m9 11-5.5 5.5a2 2 0 0 0 2.8 2.8L12 13.8"/><path d="M4 21h9"/>`),
  star: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.7l5.9-.9Z" fill="#fbbf24" stroke="#f59e0b" stroke-width="1" stroke-linejoin="round"/></svg>`,
  spinner: s(`<path d="M12 3.5a8.5 8.5 0 1 1-8.5 8.5" />`, `class="spin"`),
  minus: s(`<path d="M6 12h12"/>`),
};

export function icon(name) { return ICONS[name] || ""; }

/** Replace every [data-icon] placeholder under root with its SVG. */
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    if (!el.firstElementChild) el.innerHTML = icon(el.dataset.icon);
  });
}

// ───── Database tiles: a soft, glossy shape per database (like the reference's app tiles) ─────
const GRAD = [
  ["#ffd36b", "#f59e0b"], ["#ff9a8b", "#f0566a"], ["#7ce3e1", "#22b8c9"], ["#9be58a", "#3fb950"],
  ["#c4a5ff", "#8b5cf6"], ["#ffb37a", "#f97316"], ["#93c5fd", "#3b82f6"], ["#f9a8d4", "#ec4899"],
  ["#a7f3d0", "#10b981"], ["#fde68a", "#eab308"], ["#c7d2fe", "#6366f1"],
];
const SHAPES = [
  // 4-square cluster
  (id) => `<rect x="5" y="5" width="12" height="12" rx="3.5" fill="url(#${id})"/><rect x="19" y="5" width="12" height="12" rx="3.5" fill="url(#${id})" opacity=".85"/><rect x="5" y="19" width="12" height="12" rx="3.5" fill="url(#${id})" opacity=".85"/><rect x="19" y="19" width="12" height="12" rx="3.5" fill="url(#${id})"/>`,
  // 4-petal flower
  (id) => `<path d="M18 4c4 0 6.5 3 6.5 6.5 3.5 0 6.5 2.5 6.5 6.5v2c0 4-3 6.5-6.5 6.5 0 3.5-2.5 6.5-6.5 6.5s-6.5-3-6.5-6.5C8 25.5 5 23 5 19v-2c0-4 3-6.5 6.5-6.5C11.5 7 14 4 18 4Z" fill="url(#${id})"/>`,
  // scalloped blob
  (id) => `<path d="M18 4.5c2 0 3 1.6 4.6 1.9 1.7.3 3.4-.6 4.8.6 1.3 1.2.7 3 1.2 4.6.6 1.7 2.4 2.6 2.4 4.6s-1.6 3-1.9 4.6c-.3 1.7.6 3.4-.6 4.8-1.2 1.3-3 .7-4.6 1.2-1.7.6-2.6 2.4-4.6 2.4s-3-1.6-4.6-1.9c-1.7-.3-3.4.6-4.8-.6-1.3-1.2-.7-3-1.2-4.6C4.2 20.5 2.5 19.6 2.5 17.6s1.6-3 1.9-4.6c.3-1.7-.6-3.4.6-4.8 1.2-1.3 3-.7 4.6-1.2C11.3 6.4 12.2 4.5 14 4.5Z" fill="url(#${id})" transform="translate(1 0) scale(.94)"/>`,
  // 8-point star
  (id) => `<path d="m18 3 3.3 5.3 6.1-1.4-1.4 6.1L31.3 16.3 26 19.6l1.4 6.1-6.1-1.4L18 29.6l-3.3-5.3-6.1 1.4 1.4-6.1L4.7 16.3 10 13l-1.4-6.1 6.1 1.4Z" fill="url(#${id})" stroke-linejoin="round"/>`,
  // pill stack
  (id) => `<rect x="6" y="6" width="24" height="7" rx="3.5" fill="url(#${id})"/><rect x="6" y="15" width="24" height="7" rx="3.5" fill="url(#${id})" opacity=".8"/><rect x="6" y="24" width="24" height="7" rx="3.5" fill="url(#${id})" opacity=".6"/>`,
  // soft triangle
  (id) => `<path d="M15.4 6.5a3 3 0 0 1 5.2 0l9.8 17a3 3 0 0 1-2.6 4.5H8.2a3 3 0 0 1-2.6-4.5Z" fill="url(#${id})"/>`,
];

let tileSeq = 0;
export function dbTile(dbId, index) {
  const [a, b] = GRAD[index % GRAD.length];
  const shape = SHAPES[index % SHAPES.length];
  const id = `g-${dbId}-${tileSeq++}`; // unique: the same tile renders in several places
  return `<svg viewBox="0 0 36 36" aria-hidden="true"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>${shape(id)}</svg>`;
}
