/* AICDB Analog Hub — single-page catalog over aicdb-hub/2 component exports. Content blocks: blocks.js */
'use strict';

const STAGES = ['pre', 'partial', 'full'];
const STAGE_LABEL = { pre: 'Pre-PEX', partial: 'Partial post-PEX', full: 'Full post-PEX' };
const STAGE_SHORT = { pre: 'pre', partial: 'part', full: 'full' };
const GLOBAL_KEYS = ['tech', 'stage', 'fb', 'vdd', 'ver', 'q'];
const DEFAULTS = { tech: '', stage: 'full', fb: '1', vdd: '', ver: '', q: '', view: 'matrix', fam: '', sort: '', fig: '', page: '', mm: '', tm: '' };
const PAGE = 60;

let CAT = null;                 // data/catalog.json
const COMPS = new Map();        // id -> component (loaded lazily)
let S = {};                     // current route state
let limit = PAGE;

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ------------------------------------------------------------------ formatting */
const PREFIX = [[1e12, 'T'], [1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'µ'], [1e-9, 'n'], [1e-12, 'p'], [1e-15, 'f'], [1e-18, 'a']];
function num(v, digits = 3) {
  if (!isFinite(v)) return String(v);
  const a = Math.abs(v);
  if (Number.isInteger(v) && a < 1e15) return v.toLocaleString('en-US');
  if (a >= 10 ** Math.max(digits, 1)) return Math.round(v).toLocaleString('en-US');
  if (a >= 1e4) return (+v.toPrecision(digits)).toLocaleString('en-US', { maximumFractionDigits: 20 });
  if (a === 0) return '0';
  return String(+v.toPrecision(digits));
}
function fmt(v, m, withUnit = true) {
  if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return '—';
  if (typeof v !== 'number') return esc(v);
  const unit = m?.unit || '';
  if (m?.si) {
    const a = Math.abs(v);
    let p = PREFIX.find(([f]) => a >= f * 0.9995) || PREFIX[PREFIX.length - 1];
    if (a === 0) p = [1, ''];
    return `${num(v / p[0], m.digits || 3)}${withUnit ? ` ${p[1]}${unit}` : p[1]}`;
  }
  return `${num(v, m?.digits || 3)}${withUnit && unit ? (unit === '%' || unit === '°' ? unit : ` ${unit}`) : ''}`;
}
const fmtV = (v) => (v === null || v === undefined ? '—' : `${num(v, 3)} V`);
const techLabel = (t) => CAT.technologies?.[t] || t || '—';

/* ------------------------------------------------------------------ routing */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = h.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const qp = new URLSearchParams(query);
  const st = { ...DEFAULTS, tab: parts[0] || '', design: parts.slice(1).join('/') || '', f: {}, tabs: {} };
  for (const [k, v] of qp) {
    if (k.startsWith('f.')) st.f[k.slice(2)] = v;
    else if (k.startsWith('t.')) st.tabs[k.slice(2)] = v;
    else st[k] = v;
  }
  if (!STAGES.includes(st.stage)) st.stage = DEFAULTS.stage;
  return st;
}
function hashFor(st) {
  const qp = new URLSearchParams();
  for (const k of [...GLOBAL_KEYS, 'view', 'fam', 'sort', 'fig', 'page', 'mm', 'tm']) if (st[k] !== undefined && st[k] !== DEFAULTS[k]) qp.set(k, st[k]);
  for (const [k, v] of Object.entries(st.f || {})) if (v) qp.set(`f.${k}`, v);
  for (const [k, v] of Object.entries(st.tabs || {})) if (v !== undefined && v !== '') qp.set(`t.${k}`, v);
  const path = [st.tab, st.design].filter(Boolean).map(encodeURIComponent).join('/');
  const q = qp.toString();
  return `#/${path}${q ? `?${q}` : ''}`;
}
function go(patch, { keepLocal = true } = {}) {
  const next = { ...S, ...patch };
  if (!keepLocal) { next.view = S.view; next.fam = ''; next.sort = ''; next.f = {}; }
  const h = hashFor(next);
  if (h !== location.hash) location.hash = h; else render();
}
const tabHref = (tab, design = '', page = '') => {
  const st = { ...S, tab, design, page };
  if (tab !== S.tab) { st.fam = ''; st.sort = ''; st.f = {}; st.mm = ''; }
  st.fig = ''; st.tabs = {};
  return hashFor(st);
};

/* ------------------------------------------------------------------ data */
async function getJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}
async function loadComp(id) {
  if (!COMPS.has(id)) {
    const c = await getJSON(`data/components/${id}.json`);
    c._metric = Object.fromEntries(c.metrics.map((m) => [m.key, m]));
    c._fam = Object.fromEntries((c.families || []).map((f) => [f.id, f]));
    c._axisLabel = {};
    for (const [ak, a] of Object.entries(c.axes || {})) {
      c._axisLabel[ak] = Object.fromEntries(a.values.map((v, i) => [v.id, { label: v.label, i }]));
    }
    c.designs.forEach((d, i) => { d._i = i; });
    COMPS.set(id, c);
  }
  return COMPS.get(id);
}
const asset = (c, p) => (p ? c.base + p.split('/').map(encodeURIComponent).join('/') : '');
const JSON_CACHE = new Map();
let plotlyP = null;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (!plotlyP) plotlyP = new Promise((res, rej) => {
    const sc = document.createElement('script');
    sc.src = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js';
    sc.onload = () => res(window.Plotly);
    sc.onerror = () => { plotlyP = null; rej(new Error('could not load the plotting library')); };
    document.head.appendChild(sc);
  });
  return plotlyP;
}
/** add the current global options to an internal "#/comp/…" link that has none */
function keepGlobals(h) {
  if (!/^#\//.test(h)) return h;
  const [path, q = ''] = h.split('?');
  const qp = new URLSearchParams(q);
  for (const k of GLOBAL_KEYS) if (!qp.has(k) && S[k] !== undefined && S[k] !== DEFAULTS[k] && k !== 'q') qp.set(k, S[k]);
  const out = qp.toString();
  return `${path}${out ? `?${out}` : ''}`;
}
document.addEventListener('click', (e) => {
  const a = e.target.closest && e.target.closest('a[href^="#/"]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
  const h = keepGlobals(a.getAttribute('href'));
  if (h !== a.getAttribute('href')) { e.preventDefault(); location.hash = h; }
});
const repoUrl = (c, f) => (c.repo_raw && f ? c.repo_raw + f.split('/').map(encodeURIComponent).join('/') : '#');
const thumbFor = (c, g, cell) => (g ? c.thumbs?.[`${g}|${cell || ''}`] || null : null);
/** context handed to Blocks.render: global options + URL resolvers for this component */
function ctxFor(c) {
  if (!c._ids) c._ids = new Set(c.designs.map((d) => d.id));
  return {
    stage: S.stage, fb: S.fb === '1', vdd: S.vdd, tech: S.tech,
    vdds: [...new Set(CAT.components.flatMap((x) => x.rows.map((r) => r[1])).filter((v) => v != null).map(String))],
    src: (p) => asset(c, p),
    repo: (f) => repoUrl(c, f),
    thumb: (g, cell) => thumbFor(c, g, cell),
    json: (p) => { const u = asset(c, p); if (!JSON_CACHE.has(u)) JSON_CACHE.set(u, getJSON(u).catch((e) => { JSON_CACHE.delete(u); throw e; })); return JSON_CACHE.get(u); },
    designHref: (id) => (c._ids.has(id) ? tabHref(c.id, id) : null),
    plotly: loadPlotly,
    tabGet: (id) => (S.tabs?.[id] !== undefined ? S.tabs[id] : null),
    tabSet: (id, i) => { S.tabs = { ...(S.tabs || {}), [id]: String(i) }; history.replaceState(null, '', hashFor(S)); },
    keepGlobals,
  };
}

/* stage resolution: exact stage, or nearest earlier one when "fill" is on */
function resolve(d, stage = S.stage, fb = S.fb === '1') {
  const idx = STAGES.indexOf(stage);
  for (let i = idx; i >= (fb ? 0 : idx); i--) {
    const r = d.results?.[STAGES[i]];
    if (r) return { r, st: STAGES[i], fallback: i !== idx };
  }
  return null;
}
function resolveMask(mask, robustMask, verMask = mask) {
  const idx = STAGES.indexOf(S.stage);
  for (let i = idx; i >= (S.fb === '1' ? 0 : idx); i--) {
    if (!(mask & (1 << i))) continue;
    for (let j = i; j >= (S.fb === '1' ? 0 : i); j--) if (verMask & (1 << j)) return { i, robust: !!(robustMask & (1 << j)) };
    return { i, robust: false };
  }
  return null;
}
const physOk = (d) => !!(d.physical?.drc && d.physical?.lvs);
/** metric value with per-metric fallback (a metric missing at the resolved stage comes from an earlier stage) */
function mval(d, k, r = resolve(d)) {
  if (r && r.r.metrics?.[k] != null) return { v: r.r.metrics[k], st: r.st, fb: r.fallback };
  if (S.fb !== '1') return null;
  for (let i = (r ? STAGES.indexOf(r.st) : STAGES.indexOf(S.stage) + 1) - 1; i >= 0; i--) {
    const x = d.results?.[STAGES[i]]?.metrics?.[k];
    if (x != null) return { v: x, st: STAGES[i], fb: true };
  }
  return null;
}
/** verification fields (robust / pvt / mc) with the same per-field fallback */
function vinfo(d, r = resolve(d)) {
  const out = {};
  for (const f of ['robust', 'pvt', 'mc']) {
    if (r && r.r[f] != null) { out[f] = r.r[f]; out[`${f}St`] = r.st; continue; }
    if (S.fb !== '1') continue;
    for (let i = (r ? STAGES.indexOf(r.st) : STAGES.indexOf(S.stage) + 1) - 1; i >= 0; i--) {
      const x = d.results?.[STAGES[i]]?.[f];
      if (x != null) { out[f] = x; out[`${f}St`] = STAGES[i]; break; }
    }
  }
  return out;
}
const stTag = (st) => (st && st !== S.stage ? ` <span class="vfb" title="from ${STAGE_LABEL[st]}">${STAGE_SHORT[st]}</span>` : '');
const fmtM = (d, m, r) => { const x = mval(d, m.key, r); return x ? `${fmt(x.v, m)}${x.st !== (r?.st || S.stage) ? stTag(x.st) : ''}` : '—'; };

/* global filters shared by every tab */
function passGlobalRow(row) {
  const [tech, vdd, , mask, phys, robust, verMask = mask] = row;
  if (S.tech && tech !== S.tech) return false;
  if (S.vdd && String(vdd) !== S.vdd) return false;
  if (S.ver === 'clean' && !phys) return false;
  if (S.ver === 'robust') { const r = resolveMask(mask, robust, verMask); if (!r || !r.robust) return false; }
  return true;
}
function designText(c, d) {
  if (!d._txt) {
    const ax = Object.entries(d.axes || {}).map(([k, v]) => c._axisLabel[k]?.[v]?.label || v);
    d._txt = [d.id, d.title, ...(d.tags || []), ...ax, c.name, c.title, c.group || '', String(d.summary || '').replace(/[*_`#>|]/g, ' ')].join(' ').toLowerCase();
  }
  return d._txt;
}
function passGlobal(c, d) {
  if (S.tech && d.technology !== S.tech) return false;
  if (S.vdd && String(d.vdd) !== S.vdd) return false;
  if (S.ver === 'clean' && !physOk(d)) return false;
  if (S.ver === 'robust' && !vinfo(d).robust) return false;
  if (S.q) {
    const t = designText(c, d);
    if (!S.q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => t.includes(w))) return false;
  }
  return true;
}

/* ------------------------------------------------------------------ globals bar */
function segButtons(el, opts, cur, key) {
  el.innerHTML = opts.map(([v, l, title, dim]) => `<button type="button" data-v="${esc(v)}" class="${v === cur ? 'on' : ''}${dim ? ' dim' : ''}"${title ? ` title="${esc(title)}"` : ''}>${l}</button>`).join('');
  el.onclick = (e) => { const b = e.target.closest('button'); if (b) go({ [key]: b.dataset.v }); };
}
function renderGlobals() {
  const techs = [...new Set(CAT.components.flatMap((c) => c.rows.map((r) => r[0])))].filter(Boolean).sort();
  const sel = $('#g-tech');
  sel.innerHTML = `<option value="">All technologies</option>` + techs.map((t) => `<option value="${esc(t)}">${esc(techLabel(t))}</option>`).join('');
  sel.value = S.tech;
  sel.onchange = () => go({ tech: sel.value });

  const scope = S.tab ? CAT.components.filter((c) => c.id === S.tab) : CAT.components;
  const present = STAGES.map((_, i) => scope.some((c) => c.rows.some((r) => r[3] & (1 << i))));
  const STAGE_TIP = {
    pre: 'Schematic simulation, ideal wiring',
    partial: 'Part of the layout extracted (e.g. cap array or sub-blocks), rest ideal',
    full: 'Complete layout extracted and simulated',
  };
  segButtons($('#g-stage'), STAGES.map((s, i) => [s, STAGE_LABEL[s],
    `${STAGE_TIP[s]}${present[i] ? '' : ` — no design in ${S.tab ? 'this tab' : 'the hub'} has results at this stage`}`, !present[i]]), S.stage, 'stage');
  const fb = $('#g-fb');
  fb.checked = S.fb === '1';
  fb.onchange = () => go({ fb: fb.checked ? '1' : '0' });

  // supplies used by >= 2 generators get a button; the rest (e.g. level-shifter domains) go in a dropdown
  const used = new Map();
  for (const c of CAT.components) for (const v of new Set(c.rows.map((r) => r[1]))) if (v !== null) used.set(v, (used.get(v) || 0) + 1);
  const vdds = [...used.keys()].sort((a, b) => a - b);
  const common = vdds.filter((v) => used.get(v) >= 2 || CAT.components.length < 2);
  const rare = vdds.filter((v) => !common.includes(v));
  segButtons($('#g-vdd'), [['', 'All'], ...common.map((v) => [String(v), `${v} V`])], S.vdd, 'vdd');
  const v2 = $('#g-vdd2');
  v2.hidden = !rare.length;
  v2.innerHTML = `<option value="">other…</option>` + rare.map((v) => `<option value="${v}">${v} V</option>`).join('');
  v2.value = rare.map(String).includes(S.vdd) ? S.vdd : '';
  v2.classList.toggle('on', !!v2.value);
  v2.onchange = () => go({ vdd: v2.value });
  segButtons($('#g-ver'), [['', 'All'], ['clean', 'DRC+LVS', 'DRC and LVS clean layout'],
    ['robust', 'PVT-robust', "Meets the generator's own PVT/MC criterion at the selected stage"]], S.ver, 'ver');

  const q = $('#g-q');
  if (document.activeElement !== q) q.value = S.q;
  q.oninput = debounce(() => go({ q: q.value.trim() }), 250);
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

/** the one design count used everywhere (nav badges, overview cards, hierarchy nodes) */
const shownRows = (c) => c.rows.filter((r) => passGlobalRow(r) && resolveMask(r[3], r[5], r[6] ?? r[3]));
function renderTabs() {
  const counts = Object.fromEntries(CAT.components.map((c) => [c.id, shownRows(c).length]));
  let prevGroup = null;
  $('#tabs').innerHTML = `<a href="${tabHref('')}" class="${S.tab ? '' : 'on'}">Overview</a>` +
    CAT.components.map((c) => {
      let pre = '';
      if ((c.group || null) !== prevGroup) {
        if (prevGroup) pre += '<span class="tsep"></span>';
        if (c.group) pre += `<span class="tgroup" title="${esc(c.group)}: a collection of small generators from one repository">${esc(c.group)}</span>`;
        prevGroup = c.group || null;
      }
      return `${pre}<a href="${tabHref(c.id)}" class="${S.tab === c.id ? 'on' : ''}${c.group ? ' grouped' : ''}">${esc(c.name)}<span class="n">${counts[c.id]}</span></a>`;
    }).join('') + (prevGroup ? '<span class="tsep"></span>' : '');
  $('#tabs a.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}


/* ------------------------------------------------------------------ block hierarchy (overview) */
function hierarchyHtml() {
  const G = CAT.graph || [];
  if (!G.length) return '';
  const byId = Object.fromEntries(CAT.components.map((c) => [c.id, c]));
  const nodeKey = (id) => (byId[id]?.group ? `g:${byId[id].group}` : id);
  const nodes = new Map();
  for (const c of CAT.components) {
    const k = nodeKey(c.id);
    if (!nodes.has(k)) nodes.set(k, { key: k, label: c.group || c.name, sub: c.group ? [] : null, ids: [], href: tabHref(c.id) });
    const n = nodes.get(k); n.ids.push(c.id); if (n.sub) n.sub.push(c.name);
  }
  const edges = new Map();
  for (const e of G) {
    const a = nodeKey(e.from), b = nodeKey(e.to);
    if (a === b) continue;
    const k = `${a}>${b}`;
    if (!edges.has(k)) edges.set(k, { from: a, to: b, roles: new Set(), users: 0, targets: 0 });
    const x = edges.get(k); e.roles.forEach((r) => x.roles.add(r)); x.users += e.users; x.targets += e.targets;
  }
  const deps = (k) => [...edges.values()].filter((e) => e.from === k).map((e) => e.to);
  const lvl = new Map();
  const level = (k, seen = new Set()) => {
    if (lvl.has(k)) return lvl.get(k);
    if (seen.has(k)) return 0;
    seen.add(k);
    const d = deps(k);
    const v = d.length ? 1 + Math.max(...d.map((x) => level(x, seen))) : 0;
    lvl.set(k, v); return v;
  };
  [...nodes.keys()].forEach((k) => level(k));
  const L = Math.max(...lvl.values());
  const rows = Array.from({ length: L + 1 }, (_, i) => [...nodes.keys()].filter((k) => lvl.get(k) === i));
  const W = 1100, rowH = 118, boxH = 58, top = 24, gutter = 96;
  const pos = new Map();
  const place = (row, i) => { const n = row.length; const gap = (W - gutter) / n; row.forEach((k, j) => pos.set(k, { x: gutter + gap * (j + 0.5), y: top + (L - i) * rowH, w: Math.min(190, gap - 16) })); };
  place(rows[0], 0);
  for (let i = 1; i <= L; i++) {   // barycentric order: put users above the blocks they build on
    rows[i].sort((a, b) => { const bx = (k) => { const d = deps(k).filter((x) => pos.has(x)); return d.length ? d.reduce((s2, x) => s2 + pos.get(x).x, 0) / d.length : W / 2; }; return bx(a) - bx(b); });
    place(rows[i], i);
  }
  const count = (n) => n.ids.reduce((a, id) => a + shownRows(byId[id]).length, 0);
  const H = top + L * rowH + boxH + 26;
  const maxU = Math.max(1, ...[...edges.values()].map((e) => e.users));
  const ePaths = [...edges.values()].map((e) => {
    const a = pos.get(e.from), b = pos.get(e.to); if (!a || !b) return '';
    const y1 = a.y + boxH, y2 = b.y, my = (y1 + y2) / 2;
    const sw = 1.4 + 3 * Math.sqrt(e.users / maxU);
    const roles = [...e.roles];
    const tip = `${nodes.get(e.from).label} is built from ${nodes.get(e.to).label}` + (e.users ? `: ${e.users} design${e.users === 1 ? '' : 's'} reuse ${e.targets} ${nodes.get(e.to).label} design${e.targets === 1 ? '' : 's'}` : '') + (roles.length ? ` (${roles.join(', ')})` : '');
    return `<path class="h-edge" d="M${a.x},${y1} C${a.x},${my} ${b.x},${my} ${b.x},${y2 - 6}" stroke-width="${sw.toFixed(1)}" marker-end="url(#harrow)"><title>${esc(tip)}</title></path>`;
  }).join('');
  const nBoxes = [...nodes.values()].map((n) => {
    const p = pos.get(n.key);
    const sub = n.sub ? ` · ${n.sub.length} generators` : '';
    return `<a href="${n.href}" class="h-node"><title>${esc(n.label)}${n.sub ? `: ${n.sub.join(', ')}` : ` — ${esc(byId[n.ids[0]].title)}`}</title>
      <rect x="${p.x - p.w / 2}" y="${p.y}" width="${p.w}" height="${boxH}" rx="9"/>
      <rect class="h-bar" x="${p.x - p.w / 2}" y="${p.y}" width="5" height="${boxH}" rx="2"/>
      <text x="${p.x}" y="${p.y + 22}" class="h-name">${esc(n.label)}</text>
      <text x="${p.x}" y="${p.y + 40}" class="h-sub">${count(n).toLocaleString('en-US')} designs${esc(sub)}</text></a>`;
  }).join('');
  const lvlNames = rows.map((_, i) => (i === 0 ? 'cells' : i === L ? 'systems' : 'sub-systems'));
  const lvlLabels = rows.map((_, i) => `<text class="h-lvl" x="6" y="${top + (L - i) * rowH + boxH / 2 + 4}">${lvlNames[i]}</text>`).join('');
  return `<section class="panel hier"><div class="section-head"><h2>Block hierarchy</h2>
      <span class="subtle">arrow A → B: A is built from B · line width ∝ number of reusing designs · hover for details · counts follow the global options</span></div>
    <div class="table-scroll"><svg viewBox="0 0 ${W} ${H}" class="hsvg" role="img" aria-label="Which generators are built from which">
      <defs><marker id="harrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="h-arrow"/></marker></defs>
      ${lvlLabels}${ePaths}${nBoxes}</svg></div></section>`;
}

/* ------------------------------------------------------------------ overview */
async function renderOverview(main) {
  if (S.q) return renderSearch(main);
  let total = 0, shown = 0, exact = 0, clean = 0;
  let prevG = null;
  const cards = CAT.components.map((c) => {
    let gh = '';
    if ((c.group || null) !== prevG) { prevG = c.group || null; if (c.group) gh = `<h2 class="ovgroup">${esc(c.group)} <span class="subtle">— ${CAT.components.filter((x) => x.group === c.group).length} small generators from one repository</span></h2>`; else if (CAT.components.some((x) => x.group)) gh = '<h2 class="ovgroup"></h2>'; }
    const rows = c.rows.filter((r) => (!S.tech || r[0] === S.tech) && (!S.vdd || String(r[1]) === S.vdd));
    const pass = rows.filter(passGlobalRow);
    const withStage = pass.filter((r) => resolveMask(r[3], r[5]));
    const per = STAGES.map((_, i) => rows.filter((r) => r[3] & (1 << i)).length);
    total += rows.length; shown += withStage.length; clean += rows.filter((r) => r[4]).length;
    exact += rows.filter((r) => r[3] & (1 << STAGES.indexOf(S.stage))).length;
    const bars = STAGES.map((s, i) => `<div class="sb ${s === S.stage ? 'cur' : ''}"><span>${STAGE_LABEL[s]}</span>
      <div class="track"><div class="fill" style="width:${rows.length ? (100 * per[i]) / rows.length : 0}%"></div></div><span class="num">${per[i]}</span></div>`).join('');
    return `${gh}<a class="ovcard" href="${tabHref(c.id)}">
      <h3>${esc(c.name)}<small>${esc(c.title)}</small></h3>
      <p>${esc(c.summary)}</p>
      <div class="ovnums"><div><b>${withStage.length}</b>shown</div><div><b>${rows.length}</b>designs</div>
        <div><b>${rows.filter((r) => r[4]).length}</b>DRC+LVS clean</div>${c.families.length ? `<div><b>${c.families.length}</b>families</div>` : ''}</div>
      <div class="stagebars">${bars}</div>
      ${c.origin === 'adapter' ? '<span class="badge warn" title="Data converted by the hub\'s bootstrap adapter; the repo has not published its own hub export yet">bootstrap adapter</span>' : ''}
    </a>`;
  }).join('');
  main.innerHTML = `
    <section class="intro">
      <div>
        <div class="eyebrow">${esc(CAT.site?.subtitle || '')}</div>
        <h1>${esc(CAT.site?.title || 'Analog Hub')}</h1>
        <p>One catalog for every generator. Each tab is a component type. The options in the bar above
        (technology, simulation stage, supply, verification) apply to every tab, so you can compare
        e.g. only <b>full post-PEX</b> results at <b>1.8 V</b> across all blocks. Each tab also carries the generator's design-space
        explorer, methodology and analysis pages; layouts are previewed from the GDS and link to the raw files in the (private) source repositories.</p>
      </div>
      <div class="stats">
        <div class="stat"><b>${CAT.components.length}</b><span>component types</span></div>
        <div class="stat"><b>${total.toLocaleString('en-US')}</b><span>designs${S.tech || S.vdd ? ' (filtered)' : ''}</span></div>
        <div class="stat"><b>${exact.toLocaleString('en-US')}</b><span>with ${STAGE_LABEL[S.stage]} results</span></div>
        <div class="stat"><b>${clean.toLocaleString('en-US')}</b><span>DRC + LVS clean</span></div>
      </div>
    </section>
    ${hierarchyHtml()}
    <div class="ovgrid">${cards}</div>`;
}

async function renderSearch(main) {
  main.innerHTML = `<div class="empty-state">Searching all components…</div>`;
  const comps = await Promise.all(CAT.components.map((c) => loadComp(c.id)));
  const hits = [];
  for (const c of comps) for (const d of c.designs) if (passGlobal(c, d)) hits.push([c, d]);
  const rows = hits.slice(0, 300).map(([c, d]) => {
    const r = resolve(d);
    const m = c._metric[(c._fam[d.family]?.card_metrics || c.card_metrics)[0]];
    return `<tr data-href="${esc(tabHref(c.id, d.id))}"><td class="l">${esc(c.name)}</td><td class="l">${esc(d.title)}</td>
      <td>${fmtV(d.vdd)}</td><td>${m ? `${esc(m.label)}: ${r ? fmtM(d, m, r) : '—'}` : ''}</td>
      <td class="l">${r ? STAGE_LABEL[r.st] : '—'}</td></tr>`;
  }).join('');
  main.innerHTML = `<div class="panel"><div class="section-head"><h2>Search results for “${esc(S.q)}”</h2>
    <span class="subtle">${hits.length} designs across ${new Set(hits.map((h) => h[0].id)).size} components${hits.length > 300 ? ' — showing 300' : ''}</span></div>
    ${hits.length ? `<div class="table-scroll"><table class="list"><thead><tr><th class="l">Component</th><th class="l">Design</th><th>V<sub>DD</sub></th><th>Headline</th><th class="l">Stage</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="empty-state">No matches.</div>'}</div>`;
  main.querySelector('tbody')?.addEventListener('click', (e) => { const tr = e.target.closest('tr[data-href]'); if (tr) location.hash = tr.dataset.href; });
}

/* ------------------------------------------------------------------ component tab */
function viewCfg(c) {
  const f = c._fam[S.fam] || {};
  const card = f.card_metrics || c.card_metrics;
  const mx = f.matrix || c.matrix || { rows: Object.keys(c.axes).slice(0, 1), cols: [], metrics: card.slice(0, 2) };
  let metrics = mx.metrics?.length ? mx.metrics : card.slice(0, 2);
  const presets = mx.presets || [];
  if (S.mm.startsWith('p:') && presets[+S.mm.slice(2)]) metrics = presets[+S.mm.slice(2)].metrics;
  else if (S.mm.startsWith('m:') && c._metric[S.mm.slice(2)]) metrics = [S.mm.slice(2), ...metrics.filter((k) => k !== S.mm.slice(2))].slice(0, Math.max(2, metrics.length));
  return { card, presets, mx: { rows: mx.rows || [], cols: mx.cols || [], metrics, status: mx.status || null } };
}
function axisLabel(c, ak, v) { return c._axisLabel[ak]?.[v]?.label ?? v ?? '—'; }
function axisIdx(c, ak, v) { return c._axisLabel[ak]?.[v]?.i ?? 1e9; }

async function renderComponent(main) {
  const meta = CAT.components.find((x) => x.id === S.tab);
  if (!meta) { main.innerHTML = `<div class="empty-state">Unknown component “${esc(S.tab)}”. <a href="#/">Back to overview</a></div>`; return; }
  main.innerHTML = `<div class="empty-state">Loading ${esc(meta.name)}…</div>`;
  const c = await loadComp(S.tab);
  if (S.design) return renderDetail(main, c);
  const page = (c.pages || []).find((p) => p.id === S.page);
  if (c.families?.length && !c._fam[S.fam]) S.fam = c.families[0].id;

  const famDesigns = c.designs.filter((d) => !c.families?.length || d.family === S.fam);
  const base = famDesigns.filter((d) => passGlobal(c, d));
  // axis filters (only axes with >1 value present in this family)
  const axesUsed = Object.keys(c.axes).filter((ak) => new Set(famDesigns.map((d) => d.axes[ak]).filter((v) => v !== undefined)).size > 1);
  const list = base.filter((d) => axesUsed.every((ak) => !S.f[ak] || d.axes[ak] === S.f[ak]));
  const withStage = list.filter((d) => resolve(d));
  const exact = list.filter((d) => d.results?.[S.stage]).length;
  const robust = list.filter((d) => vinfo(d).robust).length;

  const fam = c._fam[S.fam];
  const famTabs = c.families?.length ? `<div class="subtabs">${c.families.map((f) => {
    const n = c.designs.filter((d) => d.family === f.id && passGlobal(c, d)).length;
    return `<button class="chip ${f.id === S.fam ? 'on' : ''}" data-fam="${esc(f.id)}">${esc(f.label)}<span class="n">${n}</span></button>`;
  }).join('')}</div>` : '';
  const filters = axesUsed.map((ak) => {
    const vals = c.axes[ak].values.filter((v) => famDesigns.some((d) => d.axes[ak] === v.id));
    const cnt = (v) => base.filter((d) => d.axes[ak] === v && axesUsed.every((o) => o === ak || !S.f[o] || d.axes[o] === S.f[o])).length;
    return `<div class="frow"><span class="lbl">${esc(c.axes[ak].label)}</span><div class="chips">
      <button class="chip ${S.f[ak] ? '' : 'on'}" data-ax="${esc(ak)}" data-v="">All</button>
      ${vals.map((v) => `<button class="chip ${S.f[ak] === v.id ? 'on' : ''}" data-ax="${esc(ak)}" data-v="${esc(v.id)}">${esc(v.label)}<span class="n">${cnt(v.id)}</span></button>`).join('')}
    </div></div>`;
  }).join('');
  const short = meta.commit ? meta.commit.slice(0, 7) : '';
  const extraStats = (c.stats || []).map((s) => `<div class="stat"><b>${esc(s.value)}</b><span>${esc(s.label)}</span></div>`).join('');
  const { card } = viewCfg(c);
  const sortOpts = [['', 'Generator order'], ...card.flatMap((k) => { const m = c._metric[k]; if (!m) return []; const best = m.better === 'low' ? 'asc' : 'desc'; return [[`${k}:${best}`, `Best ${m.label}`], [`${k}:${best === 'asc' ? 'desc' : 'asc'}`, `Worst ${m.label}`]]; })];

  main.innerHTML = `
    <section class="intro">
      <div>
        <div class="eyebrow">${c.group ? `${esc(c.group)} · ` : ''}${esc(techLabel(c.technology))}${short ? ` · ${esc(c.repo || '')}@${esc(short)}` : ''}${c.generated ? ` · exported ${esc(String(c.generated).slice(0, 10))}` : ''}</div>
        <h1>${esc(c.title)}</h1>
        <p>${esc(fam?.summary || c.summary || '')}</p>
        <div class="links">
          ${c.repo ? `<a href="https://github.com/${esc(c.repo)}" target="_blank" rel="noopener" title="Private repository; request access from the maintainers">Source repo ↗</a>` : ''}
          <a href="data/components/${esc(c.id)}.json" download>component.json ↓</a>
        </div>
        <div class="links hier-links">${(() => {
          const name = (id) => CAT.components.find((x) => x.id === id)?.name || id;
          const chip = (e, verb) => `<a class="badge acc" href="${tabHref(e.id)}" title="${esc(`${verb} ${name(e.id)}${e.users ? `: ${e.users} designs, ${e.targets} reused ${name(e.id)} designs` : ''}${e.roles.length ? ` (${e.roles.join(', ')})` : ''}`)}">${esc(name(e.id))}${e.users ? ` <span class="n">${e.users}</span>` : ''}</a>`;
          const b = (c.builds_on_resolved || []).map((e) => chip(e, 'built from'));
          const u = (c.used_in || []).map((e) => chip(e, 'used in'));
          return `${b.length ? `<span class="subtle">Built from</span> ${b.join(' ')}` : ''}${b.length && u.length ? ' <span class="subtle">·</span> ' : ''}${u.length ? `<span class="subtle">Used in</span> ${u.join(' ')}` : ''}`;
        })()}
          ${c.origin === 'adapter' ? '<span class="badge warn" title="Converted by the hub\'s bootstrap adapter; the generator repo has not published its own export yet">bootstrap adapter</span>' : ''}
        </div>
      </div>
      <div class="stats">
        <div class="stat"><b>${list.length}</b><span>designs shown</span></div>
        <div class="stat"><b>${exact}</b><span>with ${STAGE_LABEL[S.stage]}</span></div>
        <div class="stat"><b>${list.filter(physOk).length}</b><span>DRC + LVS clean</span></div>
        ${c.designs.some((d) => STAGES.some((st) => d.results?.[st]?.robust != null)) ? `<div class="stat"><b>${robust}</b><span>robust at shown stage</span></div>` : ''}
        ${extraStats}
      </div>
    </section>
    <nav class="pagenav">${[{ id: '', title: 'Designs' }, ...(c.pages || [])].map((p) => `<a href="${tabHref(c.id, '', p.id)}" class="${(page ? page.id : '') === p.id ? 'on' : ''}">${esc(p.title)}</a>`).join('')}</nav>
    <div id="pagebody">
    ${famTabs}
    <div class="panel">
      ${filters ? `<div class="filters">${filters}</div>` : ''}
      <div class="toolbar">
        <div class="seg" id="viewseg">${[['matrix', 'Matrix'], ['cards', 'Cards'], ['table', 'Table']].map(([v, l]) => `<button data-v="${v}" class="${S.view === v ? 'on' : ''}">${l}</button>`).join('')}</div>
        <span class="subtle">${withStage.length} of ${list.length} have ${S.fb === '1' ? `${STAGE_LABEL[S.stage]} or earlier` : STAGE_LABEL[S.stage]} results</span>
        ${S.view !== 'matrix' ? `<label class="subtle">Sort <select id="sortsel">${sortOpts.map(([v, l]) => `<option value="${esc(v)}" ${v === S.sort ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>` : `<label class="subtle">Cell metric <select id="mmsel"><option value="">Default</option>${viewCfg(c).presets.map((p, i) => `<option value="p:${i}" ${S.mm === `p:${i}` ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}${c.metrics.filter((m) => famDesigns.some((d) => STAGES.some((st) => d.results?.[st]?.metrics?.[m.key] != null))).map((m) => `<option value="m:${esc(m.key)}" ${S.mm === `m:${m.key}` ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}</select></label>`}
      </div>
      <div id="view"></div>
    </div></div>`;

  if (page) {
    const body = $('#pagebody');
    body.innerHTML = '<div class="empty-state">Loading…</div>';
    const doc = page.src ? await ctxFor(c).json(page.src) : page;
    body.innerHTML = doc.intro ? `<div class="panel md">${Blocks.md(doc.intro)}</div>` : '';
    await Blocks.render(body, doc.blocks || [], ctxFor(c));
    return;
  }

  main.querySelectorAll('[data-fam]').forEach((b) => b.onclick = () => go({ fam: b.dataset.fam, f: {}, sort: '', mm: '' }));
  main.querySelectorAll('[data-ax]').forEach((b) => b.onclick = () => go({ f: { ...S.f, [b.dataset.ax]: b.dataset.v } }));
  $('#viewseg').onclick = (e) => { const b = e.target.closest('button'); if (b) { limit = PAGE; go({ view: b.dataset.v }); } };
  const ss = $('#sortsel'); if (ss) ss.onchange = () => go({ sort: ss.value });
  const ms = $('#mmsel'); if (ms) ms.onchange = () => go({ mm: ms.value });

  const view = $('#view');
  if (!list.length) { view.innerHTML = `<div class="empty-state">No designs match the current options.</div>`; return; }
  if (S.view === 'cards') renderCards(view, c, sorted(c, list));
  else if (S.view === 'table') renderTable(view, c, sorted(c, list));
  else renderMatrix(view, c, list);
}

function sorted(c, list) {
  if (!S.sort) return list;
  const [k, dir] = S.sort.split(':');
  const val = (d) => mval(d, k)?.v;
  return [...list].sort((a, b) => {
    const x = val(a), y = val(b);
    if (x == null && y == null) return a._i - b._i;
    if (x == null) return 1; if (y == null) return -1;
    return dir === 'asc' ? x - y : y - x;
  });
}

function cellClass(d, r, status, c) {
  if (d.na) return 'nodata';
  if (d.physical?.drc === false || d.physical?.lvs === false) return 'bad';
  if (!r) return 'nodata';
  if (status && c._metric[status.metric]) {          // colour by metric thresholds
    const v = mval(d, status.metric, r)?.v;
    if (v == null) return 'nodata';
    const hi = (c._metric[status.metric].better || 'high') === 'high';
    const ok = (t) => (t == null ? true : hi ? v >= t : v <= t);
    return ok(status.good) ? '' : ok(status.warn) ? 'warn' : 'bad';
  }
  if (r.r.status === 'fail') return 'bad';
  const vi = vinfo(d, r);
  if (vi.robust === false) return 'warn';
  if (vi.robust === undefined && !vi.pvt) return 'noeval';
  return '';
}

function renderMatrix(view, c, list) {
  const { mx } = viewCfg(c);
  const keyOf = (d, axes) => axes.map((a) => d.axes[a] ?? '').join('\u0001');
  const sortKeys = (keys, axes) => keys.sort((p, q) => {
    const a = p.split('\u0001'), b = q.split('\u0001');
    for (let i = 0; i < axes.length; i++) { const r = axisIdx(c, axes[i], a[i]) - axisIdx(c, axes[i], b[i]); if (r) return r; }
    return 0;
  });
  const rows = sortKeys([...new Set(list.map((d) => keyOf(d, mx.rows)))], mx.rows);
  const vdds = [...new Set(list.map((d) => d.vdd))].sort((a, b) => (a ?? 1e9) - (b ?? 1e9));
  const groups = vdds.map((v) => ({ v, cols: sortKeys([...new Set(list.filter((d) => d.vdd === v).map((d) => keyOf(d, mx.cols)))], mx.cols) }));
  const cellMap = new Map();
  for (const d of list) {
    const k = `${keyOf(d, mx.rows)}|${d.vdd}|${keyOf(d, mx.cols)}`;
    if (!cellMap.has(k)) cellMap.set(k, []);
    cellMap.get(k).push(d);
  }
  const [m1, ...mRest] = mx.metrics.map((k) => c._metric[k]).filter(Boolean);
  const m2 = mRest[0];
  const colLabel = (key) => (mx.cols.length ? key.split('\u0001').map((v, i) => esc(axisLabel(c, mx.cols[i], v))).join('<br>') : 'design');
  const rowLabel = (key) => {
    const parts = key.split('\u0001').map((v, i) => axisLabel(c, mx.rows[i], v));
    return `${esc(parts[0])}${parts.length > 1 ? `<small>${parts.slice(1).map(esc).join(' · ')}</small>` : ''}`;
  };
  const head1 = `<tr><th></th>${groups.map((g) => `<th class="grp" colspan="${g.cols.length}">${c.vdd_labels?.[String(g.v)] ? Blocks.inline(c.vdd_labels[String(g.v)]) : `V<sub>DD</sub> = ${g.v ?? '—'}${g.v != null ? ' V' : ''}`}</th>`).join('')}</tr>`;
  const head2 = `<tr><th class="rowh">${mx.rows.map((a) => esc(c.axes[a]?.label || a)).join(' · ')}</th>${groups.map((g) => g.cols.map((k) => `<th>${colLabel(k)}</th>`).join('')).join('')}</tr>`;
  const body = rows.map((rk) => `<tr><th class="rowh">${rowLabel(rk)}</th>${groups.map((g) => g.cols.map((ck) => {
    const ds = cellMap.get(`${rk}|${g.v}|${ck}`);
    if (!ds) return '<td class="cell empty"></td>';
    const d = ds.find((x) => resolve(x)) || ds.find((x) => !x.na) || ds[0];
    const r = resolve(d);
    const vi = vinfo(d, r);
    const tip = `${d.title}${d.na ? ` — not applicable: ${d.na}` : r ? ` — ${STAGE_LABEL[r.st]}` : ` — no ${STAGE_LABEL[S.stage]} result`}${ds.length > 1 ? `\n+${ds.length - 1} more: ${ds.slice(1, 6).map((x) => x.id).join(', ')}` : ''}`;
    return `<td class="cell ${cellClass(d, r, mx.status, c)}" data-id="${esc(d.id)}" title="${esc(tip)}">
      ${r?.fallback ? `<span class="fb">${STAGE_SHORT[r.st]}</span>` : ''}
      <div class="v1">${d.na ? 'n/a' : r ? (m1 ? fmtM(d, m1, r) : '') : 'no data'}</div>
      ${mRest.slice(0, 4).map((mm) => `<div class="v2">${r ? `${esc(mm.label)} ${fmtM(d, mm, r)}` : '&nbsp;'}</div>`).join('')}
      <div class="v2">${r && vi.pvt ? `PVT ${vi.pvt.pass}/${vi.pvt.total}${stTag(vi.pvtSt)}` : ''}${physOk(d) ? `${r && vi.pvt ? ' · ' : ''}DRC/LVS ✓` : ''}${ds.length > 1 ? ` <span class="more">+${ds.length - 1}</span>` : ''}</div>
    </td>`;
  }).join('')).join('')}</tr>`).join('');
  view.innerHTML = `<div class="table-scroll"><table class="matrix"><thead>${head1}${head2}</thead><tbody>${body}</tbody></table></div>
    <div class="legend"><span>Cell: <b>${esc(m1?.label || '')}</b>${mRest.slice(0, 4).map((mm) => ` / ${esc(mm.label)}`).join('')} at <b>${STAGE_LABEL[S.stage]}</b></span>
      <span><i style="background:var(--goodbg)"></i>meets generator criteria</span><span><i style="background:var(--warnbg)"></i>not robust over PVT/MC</span><span><i style="background:var(--noevalbg);border:1px dashed var(--line)"></i>PVT/MC not evaluated</span>
      <span><i style="background:var(--badbg)"></i>${mx.status ? 'below threshold, ' : ''}failed screen or DRC/LVS</span><span><i style="background:var(--nonebg)"></i>no result at this stage</span>
      ${mx.status && c._metric[mx.status.metric] ? `<span>colour: ${esc(c._metric[mx.status.metric].label)} thresholds (green ${c._metric[mx.status.metric].better === 'low' ? '≤' : '≥'} ${fmt(mx.status.good, c._metric[mx.status.metric])}${mx.status.warn != null ? `, amber ${c._metric[mx.status.metric].better === 'low' ? '≤' : '≥'} ${fmt(mx.status.warn, c._metric[mx.status.metric])}` : ''})</span>` : ''}
      <span><b>PRE/PART</b> tag = value filled from an earlier stage (per cell or per value) · <b>n/a</b> = not applicable (hover for the reason)</span></div>`;
  view.querySelector('tbody').onclick = (e) => { const td = e.target.closest('td[data-id]'); if (td) location.hash = tabHref(c.id, td.dataset.id); };
}

function thumbOf(c, d) {
  const f = d.files || {};
  if (f.thumbnail) return asset(c, f.thumbnail);
  const t = thumbFor(c, f.gds);
  if (t) return Object.assign(new String(asset(c, t.src)), { dark: true });
  const p = f.schematic || d.images?.find((x) => x.src)?.src;
  return p ? asset(c, p) : '';
}
function badgesOf(d, r) {
  const p = d.physical || {};
  const b = (ok, name) => (ok === undefined || ok === null ? '' : `<span class="badge ${ok ? 'good' : 'bad'}">${name} ${ok ? '✓' : '✗'}</span>`);
  const st = d.na ? `<span class="badge" title="${esc(d.na)}">not applicable</span>` : r ? `<span class="badge ${r.fallback ? 'warn' : 'acc'}">${STAGE_LABEL[r.st]}</span>` : `<span class="badge">no ${STAGE_LABEL[S.stage]}</span>`;
  const vi = r ? vinfo(d, r) : {};
  const tg = (st) => (st && st !== r?.st ? ` (${STAGE_SHORT[st]})` : '');
  const rb = vi.robust === true ? `<span class="badge good">robust${tg(vi.robustSt)}</span>` : vi.robust === false ? `<span class="badge warn">not robust${tg(vi.robustSt)}</span>` : '';
  const pvt = vi.pvt ? `<span class="badge">PVT ${vi.pvt.pass}/${vi.pvt.total}${tg(vi.pvtSt)}</span>` : '';
  const fail = r?.r.status === 'fail' ? `<span class="badge bad" title="hard failure at ${STAGE_LABEL[r.st]}">failed</span>` : '';
  return st + fail + rb + pvt + b(p.drc, 'DRC') + b(p.lvs, 'LVS') + b(p.pex, 'PEX');
}
function renderCards(view, c, list) {
  const { card } = viewCfg(c);
  const gk = c._fam[S.fam]?.cards_group_by || c.cards_group_by;   // optional axis key (or array of keys)
  const gkeys = gk ? (Array.isArray(gk) ? gk : [gk]).filter((k) => c.axes[k]) : [];
  const gval = (d) => gkeys.map((k) => d.axes[k] ?? '').join('\u0001');
  if (gkeys.length) {
    const order = (d) => gkeys.map((k) => axisIdx(c, k, d.axes[k]));
    list = list.map((d, i) => [d, i]).sort((a, b) => { const x = order(a[0]), y = order(b[0]); for (let j = 0; j < x.length; j++) if (x[j] !== y[j]) return x[j] - y[j]; return a[1] - b[1]; }).map((x) => x[0]);
  }
  let lastG = null;
  const html = list.slice(0, limit).map((d) => {
    let head = '';
    if (gkeys.length && gval(d) !== lastG) {
      lastG = gval(d);
      const n = list.filter((x) => gval(x) === lastG).length;
      head = `<h3 class="cgroup">${gkeys.map((k) => `<span class="subtle">${esc(c.axes[k].label)}:</span> ${esc(axisLabel(c, k, d.axes[k]))}`).join(' · ')} <span class="n">${n}</span></h3>`;
    }
    const r = resolve(d);
    const t = thumbOf(c, d);
    const kv = card.slice(0, 12).map((k) => { const m = c._metric[k]; return m ? `<div><span>${esc(m.label)}</span><b>${r ? fmtM(d, m, r) : '—'}</b></div>` : ''; }).join('');
    return `${head}<a class="card" href="${tabHref(c.id, d.id)}">
      <div class="thumb${t?.dark ? ' dark' : ''}">${t ? `<img loading="lazy" decoding="async" src="${t}" alt="">` : '<span class="ph">no preview</span>'}</div>
      <div class="body"><h3>${esc(d.title)}</h3><div class="id">${esc(d.id)}</div>
        <div class="kv"><div><span>V<sub>DD</sub></span><b>${fmtV(d.vdd)}</b></div>${kv}</div>
        <div class="badges">${badgesOf(d, r)}${(d.tags || []).filter(Boolean).slice(0, 4).map((t) => `<span class="badge tag">${esc(t)}</span>`).join('')}</div></div></a>`;
  }).join('');
  view.innerHTML = `<div class="cards">${html}</div>${list.length > limit ? `<button class="plain more-btn" id="more">Show more (${list.length - limit} left)</button>` : ''}`;
  const mb = $('#more'); if (mb) mb.onclick = () => { limit += PAGE * 2; renderCards(view, c, list); };
}

function renderTable(view, c, list) {
  const axes = Object.keys(c.axes).filter((ak) => list.some((d) => d.axes[ak] !== undefined));
  const avail = c.metrics.filter((m) => list.some((d) => mval(d, m.key) != null));
  const tdef = c._fam[S.fam]?.table_metrics || c.table_metrics;
  const allCols = S.tm === 'all' || !tdef;
  const used = allCols ? avail : avail.filter((m) => tdef.includes(m.key));
  const [sk, sd] = (S.sort || ':').split(':');
  const head = `<tr><th class="l">Design</th><th>V<sub>DD</sub></th>${axes.map((a) => `<th class="l">${esc(c.axes[a].label)}</th>`).join('')}<th class="l">Stage</th>
    ${used.map((m) => `<th data-k="${esc(m.key)}" class="${sk === m.key ? 'sorted' : ''}" title="${esc(m.desc ? `${m.desc} — click to sort` : 'click to sort')}">${esc(m.label)}${m.unit && !m.si ? ` (${esc(m.unit)})` : m.si ? ` (${esc(m.unit)})` : ''}${sk === m.key ? (sd === 'asc' ? ' ↑' : ' ↓') : ''}</th>`).join('')}
    <th>PVT</th><th>MC</th><th class="l">Robust</th><th class="l">DRC/LVS</th></tr>`;
  const rows = list.map((d) => {
    const r = resolve(d);
    return `<tr data-id="${esc(d.id)}"><td class="l">${esc(d.title)}</td><td>${fmtV(d.vdd)}</td>
      ${axes.map((a) => `<td class="l">${esc(axisLabel(c, a, d.axes[a]))}</td>`).join('')}
      <td class="l ${r?.fallback ? 'fbv' : ''}">${r ? STAGE_LABEL[r.st] : '—'}</td>
      ${used.map((m) => { const x = mval(d, m.key, r); return `<td class="${x?.fb ? 'fbv' : ''}"${x?.fb ? ` title="from ${STAGE_LABEL[x.st]}"` : ''}>${x ? fmt(x.v, m) : '—'}</td>`; }).join('')}
      ${(() => { const vi = vinfo(d, r); const fbc = (st) => (st && st !== S.stage ? ' class="fbv"' : ''); return `<td${fbc(vi.pvtSt)}>${vi.pvt ? `${vi.pvt.pass}/${vi.pvt.total}` : '—'}</td><td${fbc(vi.mcSt)}>${vi.mc ? `${vi.mc.pass}/${vi.mc.total}` : '—'}</td><td class="l${r?.r.status === 'fail' ? ' s-bad' : vi.robust === true ? ' s-good' : vi.robust === false ? ' s-warn' : ''}${vi.robustSt && vi.robustSt !== S.stage ? ' fbv' : ''}">${r?.r.status === 'fail' ? 'failed' : vi.robust === true ? '✓' : vi.robust === false ? '✗' : '—'}</td>`; })()}<td class="l">${physOk(d) ? '✓' : d.physical?.drc === false || d.physical?.lvs === false ? '✗' : '—'}</td></tr>`;
  }).join('');
  view.innerHTML = `<div class="toolbar"><span class="subtle">Click a column to sort · values from an earlier stage in <i>italics</i>${tdef ? ` · <label class="check"><input type="checkbox" id="tmall" ${allCols ? 'checked' : ''}> all ${avail.length} metrics</label>` : ''}</span><button class="plain" id="csv">Download CSV ↓</button></div>
    <div class="table-scroll" style="max-height:70vh"><table class="list"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
  view.querySelector('thead').onclick = (e) => {
    const th = e.target.closest('th[data-k]'); if (!th) return;
    const k = th.dataset.k; const m = c._metric[k];
    const first = m.better === 'low' ? 'asc' : 'desc';
    go({ sort: `${k}:${sk === k ? (sd === 'asc' ? 'desc' : 'asc') : first}` });
  };
  view.querySelector('tbody').onclick = (e) => { const tr = e.target.closest('tr[data-id]'); if (tr) location.hash = tabHref(c.id, tr.dataset.id); };
  const tma = $('#tmall'); if (tma) tma.onchange = () => go({ tm: tma.checked ? 'all' : '' });
  $('#csv').onclick = () => {
    const q = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
    const lines = [['id', 'title', 'technology', 'vdd_V', ...axes, 'stage', ...used.map((m) => `${m.key} [${m.unit || ''}]`), 'pvt_pass', 'pvt_total', 'drc', 'lvs'].map(q).join(',')];
    for (const d of list) {
      const r = resolve(d);
      const vi = vinfo(d, r);
      lines.push([d.id, d.title, d.technology, d.vdd, ...axes.map((a) => d.axes[a]), r?.st, ...used.map((m) => mval(d, m.key, r)?.v),
        vi.pvt?.pass, vi.pvt?.total, d.physical?.drc, d.physical?.lvs].map(q).join(','));
    }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    a.download = `${c.id}${S.fam ? `-${S.fam}` : ''}-${S.stage}.csv`; a.click();
  };
}

/* ------------------------------------------------------------------ detail */
// repo-linked standard files (private source repo, raw file at the exported commit)
const FILE_LABEL = { gds: 'GDSII layout', netlist: 'Netlist (pre-PEX)', pex_netlist: 'Extracted netlist (PEX)', lvs_netlist: 'LVS reference netlist', data: 'Full evidence JSON' };
async function renderDetail(main, c) {
  const d = c.designs.find((x) => x.id === S.design);
  if (!d) { main.innerHTML = `<div class="empty-state">Design “${esc(S.design)}” not found in ${esc(c.name)}. <a href="${tabHref(c.id)}">Back</a></div>`; return; }
  const ctx = ctxFor(c);
  const r = resolve(d);
  const f = d.files || {};
  const figs = [];
  if (f.schematic) figs.push({ label: 'Schematic', src: f.schematic });
  if (f.gds) figs.push({ label: 'Layout', gds: f.gds });
  for (const im of d.images || []) figs.push({ label: im.label, src: im.src, gds: im.gds, cell: im.cell, caption: im.caption, bg: im.bg });
  const fam = c._fam[d.family];

  // only the stages that exist somewhere in this component (e.g. no empty 'Partial' column for aux)
  const DST = STAGES.filter((st) => c.designs.some((x) => x.results?.[st]));
  const metricsWith = c.metrics.filter((m) => DST.some((s) => d.results?.[s]?.metrics?.[m.key] != null));
  const stageHead = DST.map((s) => `<th class="${s === S.stage ? 'cur' : ''}">${STAGE_LABEL[s]}</th>`).join('');
  const preM = d.results?.pre?.metrics || {};
  const mrows = metricsWith.map((m) => `<tr><td${m.desc ? ` title="${esc(m.desc)}"` : ''}>${esc(m.label)}${m.desc ? ' <span class="subtle">ⓘ</span>' : ''}</td>${DST.map((s) => {
    const v = d.results?.[s]?.metrics?.[m.key];
    let delta = '';
    if (s !== 'pre' && v != null && preM[m.key] != null && preM[m.key] !== 0 && v !== preM[m.key]) {
      const pct = (100 * (v - preM[m.key])) / Math.abs(preM[m.key]);
      const good = m.better ? (m.better === 'high' ? pct > 0 : pct < 0) : null;
      if (Math.abs(pct) >= 0.05) delta = `<span class="delta ${good === null ? '' : good ? 'up' : 'down'}">${pct > 0 ? '+' : ''}${num(pct, 2)}%</span>`;
    }
    return `<td class="${s === S.stage ? 'cur' : ''}">${fmt(v, m)}${delta}</td>`;
  }).join('')}</tr>`).join('');
  const extraRow = (label, fn) => `<tr><td>${label}</td>${DST.map((s) => `<td class="${s === S.stage ? 'cur' : ''}">${d.results?.[s] ? fn(d.results[s]) : '—'}</td>`).join('')}</tr>`;
  const anyOf = (k) => DST.some((s) => d.results?.[s]?.[k] != null);
  const ver = (anyOf('pvt') ? extraRow('PVT corners passing', (x) => (x.pvt ? `${x.pvt.pass}/${x.pvt.total}` : '—')) : '') +
    (anyOf('mc') ? extraRow('Monte Carlo passing', (x) => (x.mc ? `${x.mc.pass}/${x.mc.total}` : '—')) : '') +
    (anyOf('robust') ? extraRow('Robust (generator criterion)', (x) => (x.robust === true ? '✓' : x.robust === false ? '✗' : '—')) : '');
  const notes = STAGES.filter((s) => d.results?.[s]?.note).map((s) => `<div><b>${STAGE_LABEL[s]}:</b> ${Blocks.inline(d.results[s].note)}</div>`).join('');
  const p = d.physical || {};
  const phys = [['DRC', p.drc], ['LVS', p.lvs], ['PEX', p.pex]].map(([n, v]) => `<span class="badge ${v === true ? 'good' : v === false ? 'bad' : ''}">${n} ${v === true ? '✓' : v === false ? '✗' : 'n/a'}</span>`).join('');
  const dims = [p.area_um2 != null ? `area ${num(p.area_um2, 4)} µm²` : '', p.width_um != null ? `${num(p.width_um, 4)} × ${num(p.height_um, 4)} µm` : ''].filter(Boolean).join(' · ');
  const params = Object.entries(d.params || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');
  const dls = [...Object.entries(FILE_LABEL).filter(([k]) => f[k]).map(([k, l]) => ({ label: l, file: f[k] })), ...(d.downloads || [])];
  const axesChips = Object.entries(d.axes || {}).map(([k, v]) => `<span class="badge acc" title="${esc(c.axes[k]?.label || k)}">${esc(axisLabel(c, k, v))}</span>`).join('');
  const axf = Object.entries(S.f || {}).filter(([, v]) => v);
  let navList = c.designs.filter((x) => (!d.family || x.family === d.family) && (x === d || (passGlobal(c, x) && axf.every(([k, v]) => x.axes?.[k] === v))));
  if (S.sort) navList = sorted(c, navList);
  const idx = navList.indexOf(d);
  const prev = navList[idx - 1], next = navList[idx + 1];

  main.innerHTML = `
    <div class="crumbs"><a href="${tabHref('')}">Hub</a> / <a href="${tabHref(c.id)}">${esc(c.name)}</a>${fam ? ` / <a href="${hashFor({ ...S, design: '', fam: fam.id, page: '' })}">${esc(fam.label)}</a>` : ''} / <span class="mono">${esc(d.id)}</span>
      <span class="dnav">${prev ? `<a href="${tabHref(c.id, prev.id)}" title="${esc(prev.title)}">← prev</a>` : ''}
        <select id="djump" title="Jump to another design (follows the global options)">${navList.map((x) => `<option value="${esc(x.id)}" ${x.id === d.id ? 'selected' : ''}>${esc(x.title)}</option>`).join('')}</select>
        ${next ? `<a href="${tabHref(c.id, next.id)}" title="${esc(next.title)}">next →</a>` : ''}</span></div>
    <section class="intro" style="grid-template-columns:1fr">
      <div>
        <div class="eyebrow">${esc(techLabel(d.technology))} · V<sub>DD</sub> ${fmtV(d.vdd)}${r ? ` · showing ${STAGE_LABEL[r.st]}${r.fallback ? ' (fallback)' : ''}` : ''}</div>
        <h1>${esc(d.title)}</h1>
        <div class="tags">${axesChips}${(d.tags || []).filter(Boolean).map((t) => `<span class="badge">${esc(t)}</span>`).join('')}</div>
        ${d.na ? `<div class="note muted"><b>Not applicable:</b> ${Blocks.inline(d.na)}</div>` : ''}
        ${d.summary ? `<div class="md">${Blocks.md(d.summary)}</div>` : ''}
      </div>
    </section>
    <div class="dgrid">
      <div class="panel" id="figs">${figs.length ? '' : '<div class="empty-state">No figures published</div>'}</div>
      <div>
        <div class="panel">
          <div class="section-head"><h2>Performance by simulation stage</h2><span class="subtle">Δ vs pre-PEX, green = better</span></div>
          <div class="table-scroll"><table class="mt"><thead><tr><th>Metric</th>${stageHead}</tr></thead><tbody>${mrows}${ver}</tbody></table></div>
          ${notes ? `<div class="subtle" style="margin-top:8px">${notes}</div>` : ''}
        </div>
        <div class="panel">
          <div class="section-head"><h2>Physical</h2><span class="subtle">${esc(dims)}</span></div>
          <div class="badges">${phys}</div>
        </div>
        ${params.length ? `<div class="panel"><div class="section-head"><h2>Parameters</h2></div><table class="mt"><tbody>${params.map(([k, v]) => `<tr><td>${Blocks.inline(k)}</td><td>${esc(typeof v === 'number' ? num(v, 4) : typeof v === 'object' ? JSON.stringify(v) : v)}</td></tr>`).join('')}</tbody></table></div>` : ''}
        ${(() => {
          const uses = (d.uses || []);
          const usedBy = c.used_by?.[d.id] || [];
          if (!uses.length && !usedBy.length) return '';
          const li = (x, comp, title) => `<li>${x.missing ? `<span class="subtle">${esc(comp)}/${esc(x.design)} (not on the hub)</span>` : `<a href="${tabHref(x.component, x.design)}">${esc(title)}</a> <span class="subtle">· ${esc(comp)}</span>`}${x.role ? ` — ${esc(x.role)}` : ''}</li>`;
          return `<div class="panel"><div class="section-head"><h2>Hierarchy</h2></div>
            ${uses.length ? `<div class="subtle">Built from</div><ul class="hlist">${uses.map((x) => li(x, x.component_name || x.component, x.title || x.design)).join('')}</ul>` : ''}
            ${usedBy.length ? `<div class="subtle">Used in ${usedBy.length} design${usedBy.length === 1 ? '' : 's'}</div><ul class="hlist">${usedBy.slice(0, 30).map((x) => li(x, x.component_name || x.component, x.title)).join('')}</ul>${usedBy.length > 30 ? `<details class="hmore"><summary>show all ${usedBy.length}</summary><ul class="hlist">${usedBy.slice(30).map((x) => li(x, x.component_name || x.component, x.title)).join('')}</ul></details>` : ''}` : ''}</div>`;
        })()}
        <div class="panel" id="dls"></div>
      </div>
    </div>
    <div id="detail-sections"></div>`;
  $('#djump').onchange = (e) => { location.hash = tabHref(c.id, e.target.value); };
  if (figs.length) await Blocks.render($('#figs'), [{ type: 'gallery', title: 'Figures', items: figs, max_height: 620, default: +S.fig || 0 }], ctx);
  if (dls.length) await Blocks.render($('#dls'), [{ type: 'downloads', title: 'Files', items: dls, caption: 'Files marked **repo** are in the private source repository at the exported commit; access must be requested.' }], ctx);
  else $('#dls').remove();
  if (d.detail) {
    const box = $('#detail-sections');
    box.innerHTML = '<div class="empty-state">Loading design details…</div>';
    try {
      const doc = await ctx.json(d.detail);
      if (S.design !== d.id) return; // navigated away meanwhile
      box.innerHTML = '';
      await Blocks.render(box, doc.blocks || [], ctx);
    } catch (e) {
      box.innerHTML = `<div class="note bad">Could not load design details: ${esc(e.message)}</div>`;
    }
  }
}

/* ------------------------------------------------------------------ main */
async function render() {
  const prevTab = S.tab, prevDesign = S.design, prevPage = S.page;
  const y = window.scrollY;
  S = parseHash();
  // navigation (another tab / design / page) starts at the top; changing options keeps the position
  const sameView = S.tab === prevTab && S.design === prevDesign && S.page === prevPage;
  if (!sameView) limit = PAGE;
  const cur = CAT.components.find((c) => c.id === S.tab);
  document.title = S.tab ? `${cur ? `${cur.group ? `${cur.group} · ` : ''}${cur.name}` : S.tab} · AICDB Analog Hub` : 'AICDB Analog Hub';
  renderGlobals();
  renderTabs();
  const main = $('#main');
  try {
    if (!S.tab) await renderOverview(main);
    else await renderComponent(main);
    window.scrollTo(0, sameView ? y : 0);
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="empty-state">Failed to load: ${esc(e.message)}</div>`;
  }
}

(async function init() {
  $('#theme').onclick = () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('hub-theme', root.dataset.theme); } catch (e) { /* ignore */ }
    if (CAT) render();   // re-plot charts with the new theme colours
  };
  try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (CAT && !document.documentElement.dataset.theme) render(); }); } catch (e) { /* old browsers */ }
  try {
    CAT = await getJSON('data/catalog.json');
  } catch (e) {
    $('#main').innerHTML = `<div class="empty-state">Could not load data/catalog.json — ${esc(e.message)}</div>`;
    return;
  }
  let built = '';
  try { const b = await getJSON('data/build.json'); built = b.generated; } catch (e) { /* optional */ }
  $('#foot').innerHTML = `Built ${esc((built || CAT.generated || '').replace('T', ' ').replace('Z', ' UTC'))} · ${CAT.components.length} generators ·
    <a href="https://github.com/${esc(CAT.site?.repo || 'aicdb/hub-gemini4')}" target="_blank" rel="noopener">hub source</a> ·
    <a href="https://github.com/${esc(CAT.site?.repo || 'aicdb/hub-gemini4')}/blob/main/BUILDERS.md" target="_blank" rel="noopener">publishing guide</a>`;
  window.addEventListener('hashchange', render);
  render();
})();
