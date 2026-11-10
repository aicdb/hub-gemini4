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
const techLabel = (t) => (Array.isArray(t) ? t.map((x) => CAT.technologies?.[x] || x).filter(Boolean).join(' · ') : CAT.technologies?.[t] || t || '—');
const techShort = (t) => techLabel(t).replace(/\s*\([^)]*\)\s*/g, '');
const compTechs = (c, ds = c.designs) => {
  const order = Object.keys(CAT.technologies || {});
  const set = new Set((ds.length ? ds : c.designs).map((d) => d.technology || c.technology).filter(Boolean));
  if (!set.size && c.technology) set.add(c.technology);
  return [...set].sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99));
};

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
  if (st.tab === 'aux-cml_ro') { st.tab = 'aux-ro'; if (!st.fam) st.fam = 'cml_ro'; }
  if (st.tab === 'aux-cml_dco_vco') { st.tab = 'aux-dco_vco'; if (!st.fam) st.fam = 'cml_dco_vco'; }
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
async function getPack(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json();
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
    c._packOf = {};
    (c.packs || []).forEach((rels, i) => rels.forEach((p) => { c._packOf[p] = i; }));
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
  const techVdds = {};
  for (const x of CAT.components) for (const r of x.rows) if (r[0] && r[1] != null) (techVdds[r[0]] ||= new Set()).add(String(r[1]));
  return {
    stage: S.stage, fb: S.fb === '1', vdd: S.vdd, tech: S.tech,
    techs: Object.keys(CAT.technologies || {}),
    techVdds: Object.fromEntries(Object.entries(techVdds).map(([k, s]) => [k, [...s]])),
    vdds: [...new Set(CAT.components.flatMap((x) => x.rows.map((r) => r[1])).filter((v) => v != null).map(String))],
    src: (p) => asset(c, p),
    repo: (f) => repoUrl(c, f),
    thumb: (g, cell) => thumbFor(c, g, cell),
    json: (p) => {
      if (c._packOf?.[p] !== undefined) {
        const u = asset(c, `_pack_${c._packOf[p]}.bin`);
        if (!JSON_CACHE.has(u)) JSON_CACHE.set(u, getPack(u).catch((e) => { JSON_CACHE.delete(u); throw e; }));
        return JSON_CACHE.get(u).then((pk) => {
          if (!(p in pk)) throw new Error(`${p}: not found in pack`);
          return pk[p];
        });
      }
      const u = asset(c, p);
      if (!JSON_CACHE.has(u)) JSON_CACHE.set(u, getJSON(u).catch((e) => { JSON_CACHE.delete(u); throw e; }));
      return JSON_CACHE.get(u);
    },
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
  const hasVdd = (v) => scope.some((c) => c.rows.some((r) => (!S.tech || r[0] === S.tech) && r[1] === v));
  segButtons($('#g-vdd'), [['', 'All'], ...common.map((v) => [String(v), `${v} V`,
    hasVdd(v) ? '' : `No ${v} V designs in ${S.tab ? 'this tab' : 'the hub'}${S.tech ? ` for ${techLabel(S.tech)}` : ''}`, !hasVdd(v)])], S.vdd, 'vdd');
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
/* Layered stack: one full-width band per tier (systems … building blocks) above the foundation tier, the
   technology libraries (PDK PCells, standard cells) drawn as a platform. An arrow A → B means "A is built
   from B". Connectors are orthogonal, leave and enter on ports spread along the boxes and run on
   crossing-minimised tracks; a link that skips a tier passes through a free gap of it, and the links of
   several blocks to one library merge into one trunk. Pointing at or focusing a block traces its links
   and spells them out in the caption under the drawing; the <details> list repeats everything as text. */
const HIER = { ctx: null, font: '', avail: 0, info: new Map(), hint: '', quiet: false };
/** width the diagram may use without scrolling: #main minus the panel's padding and border */
function hierAvail() {
  const m = $('#main');
  if (!m) return 1100;
  const cs = getComputedStyle(m);
  return Math.floor(m.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 38);
}
/** rendered text width (px) in the page font, so boxes are sized before the SVG exists */
function hierTextW(s, px, wt = 400) {
  if (!HIER.ctx) { HIER.ctx = document.createElement('canvas').getContext('2d'); HIER.font = getComputedStyle(document.body).fontFamily; }
  HIER.ctx.font = `${wt} ${px}px ${HIER.font}`;
  return HIER.ctx.measureText(String(s)).width;
}
function hierFit(s, px, wt, max) {
  s = String(s);
  if (hierTextW(s, px, wt) <= max) return s;
  while (s.length > 1 && hierTextW(`${s}…`, px, wt) > max) s = s.slice(0, -1);
  return `${s.trimEnd()}…`;
}
function hierWrap(s, px, wt, max, lines = 2) {
  // words; one too long for a line breaks at its camel-case humps / digits, as a last resort anywhere
  const parts = [];
  for (const w of String(s).split(/\s+/).filter(Boolean)) {
    if (hierTextW(w, px, wt) <= max) { parts.push([w, ' ']); continue; }
    w.replace(/([a-z])(?=[A-Z0-9])|([A-Za-z])(?=[0-9])/g, '$1$2\u0000').split('\u0000').forEach((p, i) => {
      for (let q = p; q;) {
        let k = q.length;
        while (k > 1 && hierTextW(q.slice(0, k), px, wt) > max) k--;
        parts.push([q.slice(0, k), i || q !== p ? '' : ' ']);
        q = q.slice(k);
      }
    });
  }
  const out = [];
  let cur = '';
  for (const [w, sp] of parts) {
    const t = cur ? `${cur}${sp}${w}` : w;
    if (!cur || hierTextW(t, px, wt) <= max) cur = t; else { out.push(cur); cur = w; }
  }
  if (cur) out.push(cur);
  if (out.length > lines) out.splice(lines - 1, out.length, out.slice(lines - 1).join(' '));
  return out.map((l) => hierFit(l, px, wt, max));
}
/** narrowest width (4 px steps) at which s wraps onto `lines` lines between whole words without being cut */
function hierWrapW(s, px, wt, lines) {
  const full = Math.ceil(hierTextW(s, px, wt)), word = Math.max(...String(s).split(/\s+/).map((w) => Math.ceil(hierTextW(w, px, wt))));
  for (let w = Math.max(word, Math.ceil(full / lines)); w < full; w += 4) if (!hierWrap(s, px, wt, w, lines).some((l) => l.endsWith('…'))) return w;
  return full;
}
/** span of a horizontal run in an inter-tier gap. A run has upper legs (ups: x where it comes down from the tier
    above) and lower legs (downs: x where it continues to the tier below); a trunk shared by several links is one
    run with several upper legs. s.src / s.dst: the block of each upper / lower leg (none for a pass-through),
    s.from / s.to: the blocks the run leaves from / goes into */
function hierSpan(s) {
  const all = s.ups.concat(s.downs);
  s.lo = Math.min(...all); s.hi = Math.max(...all);
  s.u = s.ups.reduce((x, y) => x + y, 0) / s.ups.length; s.d = s.downs.reduce((x, y) => x + y, 0) / s.downs.length;
  return s;
}
const hierNear = (a, b, m) => a.lo < b.hi + m && b.lo < a.hi + m;
/** crossings when run a lies on a track above run b: b's upper legs / a's lower legs cut through the other run.
    Cutting a leg of the block the run itself leaves from (or goes into) counts double: next to the box it reads as
    a bus joining those ports. An arriving leg right beside a departing one costs extra (they read as one line). */
function hierRunCost(a, b) {
  if (!hierNear(a, b, 2)) return 0;
  const inside = (x, s) => x > s.lo + 0.5 && x < s.hi - 0.5;
  let c = 0;
  for (const x of b.ups) if (inside(x, a)) c += a.from?.has(b.src?.get(x)) ? 2 : 1;
  for (const x of a.downs) { if (inside(x, b)) c += b.to?.has(a.dst?.get(x)) ? 2 : 1; for (const y of b.ups) if (Math.abs(x - y) < 10) c += 3; }
  return c;
}
/** order the horizontal runs of one inter-tier gap so few connectors cross, then pack them on tracks.
    Sets s.lv on every run that moves sideways, segs.cost (the crossings), and returns the number of tracks. */
function hierTracks(segs) {
  segs.forEach(hierSpan);
  const T = segs.filter((s) => s.hi - s.lo > 0.5);
  const near = hierNear, cost = hierRunCost;
  const total = (o) => { let c = 0; for (let i = 0; i < o.length; i++) for (let j = i + 1; j < o.length; j++) c += cost(o[i], o[j]); return c; };
  const improve = (ord) => {
    for (let it = 0, moved = true; moved && it < 40; it++) {
      moved = false;
      for (let i = 0; i < ord.length; i++) {
        const s = ord[i], rest = ord.slice(0, i).concat(ord.slice(i + 1));
        let c = rest.reduce((t, r) => t + cost(s, r), 0), cur = c, best = 0, bestC = c;
        for (let p = 1; p <= rest.length; p++) {
          c += cost(rest[p - 1], s) - cost(s, rest[p - 1]);
          if (p === i) cur = c;
          if (c < bestC) { bestC = c; best = p; }
        }
        if (bestC < cur) { rest.splice(best, 0, s); ord.splice(0, ord.length, ...rest); moved = true; }
      }
    }
    return ord;
  };
  // a few deterministic starts (local search alone can stall), keep the order with the fewest crossings
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const dir = (s) => (s.d > s.u ? -s.u : s.u - 1e6);
  const starts = [(a, b) => dir(a) - dir(b), (a, b) => a.u - b.u, (a, b) => b.u - a.u, (a, b) => a.d - b.d, (a, b) => b.d - a.d,
    (a, b) => (a.hi - a.lo) - (b.hi - b.lo)].map((f) => T.slice().sort(f));
  for (let k = 0; k < 8; k++) starts.push(T.map((x) => [rnd(), x]).sort((a, b) => a[0] - b[0]).map((x) => x[1]));
  // pack: a run takes the first track below every earlier run it overlaps (28 px apart, so runs never read as one line)
  const pack = (o) => { o.forEach((s, i) => { s.lv = 0; for (let j = 0; j < i; j++) if (near(o[j], s, 28)) s.lv = Math.max(s.lv, o[j].lv + 1); }); return o.length ? 1 + Math.max(...o.map((s) => s.lv)) : 0; };
  let ord = [], score = Infinity;
  for (const st of starts) { const o = improve(st), sc = total(o) * 100 + pack(o); if (sc < score) { score = sc; ord = o; } }
  segs.cost = total(ord);
  return pack(ord);
}
/** orthogonal polyline with rounded corners */
function hierPath(pts, r) {
  const P = [];
  for (const p of pts) { const q = P[P.length - 1]; if (!q || Math.abs(q[0] - p[0]) > 0.01 || Math.abs(q[1] - p[1]) > 0.01) P.push(p); }
  for (let i = P.length - 2; i > 0; i--) {
    const [a, b, c] = [P[i - 1], P[i], P[i + 1]];
    if ((Math.abs(a[0] - b[0]) < 0.01 && Math.abs(b[0] - c[0]) < 0.01) || (Math.abs(a[1] - b[1]) < 0.01 && Math.abs(b[1] - c[1]) < 0.01)) P.splice(i, 1);
  }
  const f = (v) => +v.toFixed(1);
  let d = `M${f(P[0][0])},${f(P[0][1])}`;
  for (let i = 1; i < P.length - 1; i++) {
    const [x0, y0] = P[i - 1], [x1, y1] = P[i], [x2, y2] = P[i + 1];
    const l1 = Math.hypot(x1 - x0, y1 - y0), l2 = Math.hypot(x2 - x1, y2 - y1), rr = Math.min(r, l1 / 2, l2 / 2);
    d += ` L${f(x1 - ((x1 - x0) / l1) * rr)},${f(y1 - ((y1 - y0) / l1) * rr)} Q${f(x1)},${f(y1)} ${f(x1 + ((x2 - x1) / l2) * rr)},${f(y1 + ((y2 - y1) / l2) * rr)}`;
  }
  const z = P[P.length - 1];
  return `${d} L${f(z[0])},${f(z[1])}`;
}

function hierarchyHtml() {
  const FD = (CAT.foundations || []).filter((f) => f && f.id);
  if (!(CAT.graph || []).length && !FD.length) return '';
  const comps = CAT.components;
  const byId = Object.fromEntries(comps.map((c) => [c.id, c]));
  const nodeKey = (id) => (byId[id]?.group ? `g:${byId[id].group}` : id);
  const fmtN = (v) => v.toLocaleString('en-US');
  const plural = (n, w, pl = `${w}s`) => `${fmtN(n)} ${n === 1 ? w : pl}`;
  const and = (a) => (a.length < 3 ? a.join(' and ') : `${a.slice(0, -1).join(', ')} and ${a[a.length - 1]}`);
  const cut = (s, n) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
  const names = (ids) => ids.map((id) => byId[id]?.name || id);
  const f1 = (v) => +v.toFixed(1);

  /* ---- model: component nodes (a group collapses into one), "built from" edges, foundation tier */
  const N = new Map();
  comps.forEach((c, i) => {
    const k = nodeKey(c.id);
    if (!N.has(k)) N.set(k, { key: k, kind: 'c', label: c.group || c.name, group: c.group || null, ids: [], ord: i });
    N.get(k).ids.push(c.id);
  });
  for (const n of N.values()) n.count = n.ids.reduce((a, id) => a + shownRows(byId[id]).length, 0);
  const E = [], EK = new Map();
  const edgeOf = (a, b, kind) => {
    const k = `${a}>${b}`;
    if (!EK.has(k)) { const e = { a, b, kind, roles: new Set(), users: 0, targets: 0, byFrom: new Map(), mem: new Map(), xs: {}, lv: {} }; EK.set(k, e); E.push(e); }
    return EK.get(k);
  };
  for (const g of CAT.graph || []) {
    const a = nodeKey(g.from), b = nodeKey(g.to);
    if (a === b || !N.has(a) || !N.has(b)) continue;
    const e = edgeOf(a, b, 'c');
    (g.roles || []).forEach((r) => e.roles.add(r));
    const maxFrom = byId[g.from]?.rows?.length || Infinity;
    e.byFrom.set(g.from, Math.min(maxFrom, Math.max(e.byFrom.get(g.from) || 0, g.users || 0)));
    e.users = [...e.byFrom.values()].reduce((s, v) => s + v, 0);
    e.targets += g.targets || 0;
  }
  const CE = E.slice();
  // level = longest "built from" chain below a block (0 = cells)
  const lvl = new Map();
  const level = (k, seen = new Set()) => {
    if (lvl.has(k)) return lvl.get(k);
    if (seen.has(k)) return 0;
    seen.add(k);
    const d = CE.filter((e) => e.a === k).map((e) => e.b);
    const v = d.length ? 1 + Math.max(...d.map((x) => level(x, seen))) : 0;
    lvl.set(k, v);
    return v;
  };
  [...N.keys()].forEach((k) => level(k));
  for (let i = CE.length - 1; i >= 0; i--) {     // a cycle in the data would point a link upwards: leave it out of the drawing
    const e = CE[i];
    if (lvl.get(e.a) <= lvl.get(e.b)) { CE.splice(i, 1); E.splice(E.indexOf(e), 1); EK.delete(`${e.a}>${e.b}`); }
  }
  const L = Math.max(0, ...lvl.values());
  let RL = L, FL = L + 1;              // last component row, foundation row (a tier that wraps adds a row)
  const F = FD.map((f, i) => ({ key: `f:${f.id}`, kind: 'f', label: f.name || f.id, f, ord: i, use: new Map(), t: FL }));
  for (const fn of F) {
    for (const u of fn.f.users || []) {
      const ids = byId[u.component] ? [u.component] : comps.filter((c) => c.source === u.component).map((c) => c.id);
      for (const id of ids) {
        if (!fn.use.has(id)) fn.use.set(id, new Set());
        if (u.role) fn.use.get(id).add(u.role);
        const e = edgeOf(nodeKey(id), fn.key, 'f');
        if (!e.mem.has(id)) e.mem.set(id, new Set());
        if (u.role) { e.mem.get(id).add(u.role); e.roles.add(u.role); }
      }
    }
  }
  const FE = E.filter((e) => e.kind === 'f');
  E.forEach((e, i) => { e.id = `e${i}`; });
  let tiers = L + 1 + (F.length ? 1 : 0);            // rows, foundation included
  const byKey = (k) => N.get(k) || F.find((f) => f.key === k);
  for (const fn of F) {           // what a library slab says: short title, users and their designs (global options)
    const used = [...fn.use.keys()];
    fn.designs = used.reduce((a, id) => a + shownRows(byId[id]).length, 0);
    fn.desc = String(fn.f.title || '').split(' — ')[0];
    fn.cnt = used.length ? `${plural(used.length, 'generator')} · ${plural(fn.designs, 'design')}` : 'not used yet';
    fn.who = used.length && used.length <= 3 ? `used by ${and(names(used))}` : '';
  }

  /* ---- tiers and a crossing-minimised order (barycentre sweeps over the component edges) */
  const R = Array.from({ length: L + 1 }, () => []);
  for (const n of N.values()) { n.t = L - lvl.get(n.key); R[n.t].push(n); }
  R.forEach((row) => row.sort((a, b) => a.ord - b.ord));
  const linked = new Set(CE.flatMap((e) => [e.a, e.b]));
  const rel = () => R.forEach((row) => row.forEach((n, i) => { n.r = (i + 0.5) / row.length; }));
  const crossings = () => {
    rel();
    let c = 0;
    for (let i = 0; i < CE.length; i++) for (let j = i + 1; j < CE.length; j++) {
      const p = CE[i], q = CE[j];
      if (p.a !== q.a && p.b !== q.b && (N.get(p.a).r - N.get(q.a).r) * (N.get(p.b).r - N.get(q.b).r) < 0) c++;
    }
    return c;
  };
  const sweep = (row, up) => {
    rel();
    const key = new Map(row.map((n) => {
      const nb = CE.filter((e) => (up ? e.a === n.key : e.b === n.key)).map((e) => N.get(up ? e.b : e.a));
      return [n, !linked.has(n.key) ? 2 + n.ord / 1e4 : nb.length ? nb.reduce((s, m) => s + m.r, 0) / nb.length : n.r];
    }));
    row.sort((a, b) => key.get(a) - key.get(b) || a.ord - b.ord);
  };
  sweep(R[L], true);
  let best = crossings(), snap = R.map((r) => r.slice());
  for (let it = 0; it < 6 && best > 0; it++) {
    for (let t = 1; t <= L; t++) sweep(R[t], false);
    for (let t = L - 1; t >= 0; t--) sweep(R[t], true);
    const c = crossings();
    if (c < best) { best = c; snap = R.map((r) => r.slice()); }
  }
  snap.forEach((r, t) => { R[t] = r; });
  // blocks nobody links to go to both ends, so the shared ones sit under the tier that uses them
  R.forEach((row, t) => {
    const iso = row.filter((n) => !linked.has(n.key));
    if (!iso.length || iso.length === row.length) return;
    const core = row.filter((n) => linked.has(n.key));
    iso.forEach((n, i) => (i % 2 ? core.unshift(n) : core.push(n)));
    R[t] = core;
  });
  const band = R.map((_, t) => t);      // row -> tier (the rows of a wrapped tier share one band)

  /* ---- sizes: wide layout with a label gutter, or a compact one (rotated tier names) for phones */
  const avail = hierAvail();
  HIER.avail = avail;
  const span = (e) => [byKey(e.a).t, byKey(e.b).t];
  const trunkAt = (fn, t) => FE.filter((e) => e.b === fn.key && e.bun && byKey(e.a).t < t);   // links in fn's trunk at tier t
  let pass = [];
  const relevel = () => {
    R.forEach((row, t) => row.forEach((n) => { n.t = t; }));
    RL = R.length - 1; FL = RL + 1; tiers = RL + 1 + (F.length ? 1 : 0);
    F.forEach((fn) => { fn.t = FL; });
    // a library link that skips a row joins its library's trunk (one line per library through each row)
    for (const e of FE) e.bun = byKey(e.a).t < RL;
    pass = Array(tiers).fill(0);        // links that cross each row
    for (const e of CE) { const [ta, tb] = span(e); for (let t = ta + 1; t < tb; t++) pass[t]++; }
    for (const fn of F) for (let t = 1; t <= RL; t++) if (trunkAt(fn, t).length) pass[t]++;
  };
  relevel();
  const subOf = (n, P) => `${plural(n.count, 'design')}${n.group && P.wide ? ` · ${n.ids.length} generators` : ''}`;
  const MODES = {
    wide: { wide: true, gut: 188, padL: 22, padR: 20, nodeH: 54, nameFs: 13.5, subFs: 11.5, minW: 132, maxW: 220, gapMin: 40, gapMax: 132, pitch: 8, depth: 7, gapH: 46, r: 6 },
    medium: { wide: true, gut: 142, padL: 18, padR: 16, nodeH: 54, nameFs: 13.5, subFs: 11.5, minW: 118, maxW: 200, gapMin: 30, gapMax: 110, pitch: 8, depth: 7, gapH: 44, r: 6 },
    compact: { wide: false, gut: 30, padL: 14, padR: 14, nodeH: 50, nameFs: 12.5, subFs: 11, minW: 104, maxW: 172, gapMin: 30, gapMax: 84, pitch: 7, depth: 6, gapH: 40, r: 5 },
  };
  const mk = (mode, tight = false) => {
    const P = { ...MODES[mode] }, wide = P.wide;
    if (tight) Object.assign(P, { padL: 8, padR: 8, gapMin: P.gapMin - 8, minW: P.minW - 8 });   // to avoid a short scroll
    const room = avail - P.gut - P.padL - P.padR;
    // a name too long for the widest box wraps onto two lines (and makes its tier's boxes taller)
    P.names = (n) => (hierTextW(n.label, P.nameFs, 700) + 30 <= P.maxW ? [n.label] : hierWrap(n.label, P.nameFs, 700, P.maxW - 30, 2));
    const need = (n) => Math.min(P.maxW, Math.max(P.minW, ...P.names(n).map((s) => hierTextW(s, P.nameFs, 700) + 30), hierTextW(subOf(n, P), P.subFs) + 28));
    P.h = R.map((row) => P.nodeH + (row.some((n) => P.names(n).length > 1) ? P.nameFs + 2.5 : 0));
    // one width per tier (tidy columns) when the tier fits that way, else each box its own width;
    // a collapsed group sizes itself (its subtitle is longer)
    P.w = R.map((row) => Math.max(P.minW, ...row.filter((n) => !n.group).map(need)));
    P.uni = R.map(() => true);
    P.nw = (n) => (!P.uni[n.t] ? need(n) : n.group ? Math.max(P.w[n.t], need(n)) : P.w[n.t]);
    const stack = (row) => (row.some((n) => n.group) ? 8 : 0);
    const capMin = Math.floor((P.gapMin - 20) / P.pitch) + 1;
    const rowW = (row, t) => row.reduce((a, n) => a + P.nw(n), 0) + (row.length - 1) * P.gapMin + stack(row) + 20 + Math.max(0, pass[t] - (row.length + 1) * capMin) * P.pitch;
    R.forEach((row, t) => { if (rowW(row, t) > room) P.uni[t] = false; });
    P.rowW = R.map(rowW);
    // a slab fits its name and counts on one line and its description / users on one line each (wrapped beyond
    // that); when the libraries are what makes the stage too wide, the counts go under the name and the texts
    // wrap onto two lines instead
    const line = (s) => (s ? Math.min(hierTextW(s, P.subFs), wide ? 380 : 250) + 32 : 0);
    const slabRow = (ws) => (F.length ? ws.reduce((a, b) => a + b, 0) + (F.length - 1) * 16 : 0);
    P.slabMin = F.map((fn) => Math.max(wide ? 200 : 150, hierTextW(fn.label, P.nameFs + 0.5, 700) + hierTextW(fn.cnt, P.subFs) + 56, line(fn.desc), line(fn.who)));
    if (slabRow(P.slabMin) > Math.max(room, ...P.rowW)) {
      const two = (s) => (s ? Math.min(hierWrapW(s, P.subFs, 400, 2), wide ? 380 : 250) + 32 : 0);
      P.slabMin = F.map((fn) => Math.max(wide ? 170 : 130, hierTextW(fn.label, P.nameFs + 0.5, 700) + 32, hierTextW(fn.cnt, P.subFs) + 32, two(fn.desc), two(fn.who)));
    }
    P.slabW = slabRow(P.slabMin);
    P.need = Math.max(...P.rowW, P.slabW);
    P.W = P.gut + P.padL + P.need + P.padR;
    return P;
  };
  let P = mk('wide');
  if (P.W > avail) P = mk('medium');
  if (P.W > avail) { const c = mk('compact'); if (c.W <= avail) P = c; }      // smaller boxes, one row per tier
  // on a desktop a tier still too wide for the panel wraps onto two rows (bracketed as one tier in the gutter),
  // rather than everything shrinking and scrolling (unless the libraries alone are too wide: no wrap helps then)
  if (P.W > avail && avail >= 900 && P.slabW <= avail - P.gut - P.padL - P.padR) {
    const room = avail - P.gut - P.padL - P.padR;
    let split = false;
    for (let t = R.length - 1; t >= 0; t--) {
      if (P.rowW[t] <= room || R[t].length < 2) continue;
      // the blocks that tiers above are built from go on the first row, so their links need not pass the second
      const inUse = (n) => CE.some((e) => e.b === n.key);
      const first = new Set(R[t].filter(inUse).concat(R[t].filter((n) => !inUse(n))).slice(0, Math.ceil(R[t].length / 2)));
      R.splice(t, 1, R[t].filter((n) => first.has(n)), R[t].filter((n) => !first.has(n)));
      band.splice(t, 1, band[t], band[t]);
      split = true;
    }
    if (split) { relevel(); P = mk('wide'); if (P.W > avail) P = mk('medium'); }
  }
  if (P.W > avail) P = mk('compact');
  if (P.W > avail && P.W - avail < 80) { const c = mk('compact', true); if (c.W <= avail) P = c; }
  const W = Math.max(avail, Math.ceil(P.W));
  const sx0 = P.gut + P.padL, sx1 = W - P.padR, S = sx1 - sx0;

  /* ---- x: each tier centred in its band, gaps capped */
  R.forEach((row) => {
    const n = row.length, sw = row.reduce((a, nd) => a + P.nw(nd), 0);
    const g = n > 1 ? Math.max(P.gapMin, Math.min(P.gapMax, (S - sw) / n)) : 0;
    let x = sx0 + (S - (sw + (n - 1) * g)) / 2;
    row.forEach((nd) => { nd.w = P.nw(nd); nd.x = x; nd.cx = x + nd.w / 2; x += nd.w + g; });
  });
  // foundation slabs: one platform across the stage; order and boundaries chosen so most links drop straight down
  // cost of one slab: sideways jogs (a link arriving beside it; any jog costs, a small one looks like a mistake),
  // a jogging link landing right next to a straight one, and a trunk that finds no free gap above the slab
  const rowGaps = (dx) => {              // free x ranges of the tier right above the slabs, where a trunk can pass
    const out = [];
    let l = sx0 - P.padL + 10;
    for (const nd of R[RL]) { out.push([l, nd.x + dx - 10]); l = nd.x + dx + nd.w + (nd.group ? 8 : 0) + 10; }
    out.push([l, sx1 + P.padR - 10]);
    return out.filter(([g0, g1]) => g1 >= g0);
  };
  const slabUsers = (fn, dx = 0) => {    // where its links arrive from: the blocks right above, and the trunk (if any)
    const es = FE.filter((e) => e.b === fn.key), bun = es.filter((e) => e.bun);
    return { us: es.filter((e) => !e.bun).map((e) => byKey(e.a).cx + dx), trunk: bun.length ? bun.reduce((a, e) => a + byKey(e.a).cx, 0) / bun.length : null, dx };
  };
  const slabCost = (lo, hi, { us, trunk, dx }, perPx = 1) => {
    const jogL = us.some((u) => u < lo), jogR = us.some((u) => u > hi);
    let c = 0;
    for (const u of us) {
      const off = Math.max(0, lo - u, u - hi);
      if (off > 0) c += 20 + off * perPx;
      else if ((jogL && u < lo + 26) || (jogR && u > hi - 26)) c += 12;
    }
    if (trunk !== null) {
      let best = Infinity;
      for (const [g0, g1] of rowGaps(dx)) {
        const l = Math.max(g0, lo + 6), r = Math.min(g1, hi - 6);       // the part of this gap over the slab
        const run = 0.1 * Math.max(0, g0 - trunk, trunk - g1);           // the trunk's run sideways to the gap
        best = Math.min(best, run + (l <= r ? 0 : 20 + (l - r) * perPx));
      }
      c += best;
    }
    return c;
  };
  const placeSlabs = () => {
    const gap = 16, k = F.length;
    const users = F.map((fn) => slabUsers(fn));
    const weight = users.map((u) => 1 + u.us.length + (u.trunk === null ? 0 : 1)), totW = weight.reduce((a, b) => a + b, 0);
    const rest = S - (k - 1) * gap - P.slabMin.reduce((a, b) => a + b, 0);
    const prop = F.map((fn, i) => P.slabMin[i] + (rest * weight[i]) / totW);
    const cost = (order, ws) => {          // + drift from the proportional widths
      let x = sx0, c = 0;
      for (const i of order) { c += slabCost(x + 16, x + ws[i] - 16, users[i]) + 0.15 * Math.abs(ws[i] - prop[i]); x += ws[i] + gap; }
      return c;
    };
    const fitWidths = (order) => {
      const ws = prop.slice();
      for (let it = 0; it < 3; it++) for (let b = 0; b < k - 1; b++) {
        const i = order[b], j = order[b + 1], tot = ws[i] + ws[j];
        let bw = ws[i], bc = cost(order, ws);
        for (let wi = P.slabMin[i]; wi <= tot - P.slabMin[j]; wi += 4) {
          ws[i] = wi; ws[j] = tot - wi;
          const c = cost(order, ws);
          if (c < bc - 1e-6) { bc = c; bw = wi; }
        }
        ws[i] = bw; ws[j] = tot - bw;
      }
      return ws;
    };
    const perms = (a) => (a.length <= 1 ? [a] : a.flatMap((v, i) => perms(a.filter((_, j) => j !== i)).map((q) => [v, ...q])));
    let pick = null;
    for (const o of k <= 4 ? perms(F.map((_, i) => i)) : [F.map((_, i) => i)]) {
      const ws = fitWidths(o), c = cost(o, ws);
      if (!pick || c < pick.c - 0.5) pick = { o, ws, c };
    }
    let x = sx0;
    for (const i of pick.o) { F[i].x = x; F[i].w = pick.ws[i]; F[i].cx = x + F[i].w / 2; x += F[i].w + gap; }
  };
  // the tier right above the slabs may also slide sideways (within the stage, only as far as it removes a jog or a
  // cramped landing) so its blocks sit over their slab
  const slideRow = () => {
    const row = R[RL], last = row[row.length - 1];
    const d0 = sx0 - row[0].x, d1 = sx1 - (last.x + last.w + (last.group ? 8 : 0));
    let bestD = 0, bestC = Infinity;
    for (let d = Math.ceil(d0); d <= d1; d += 2) {
      const c = F.reduce((a, fn) => a + slabCost(fn.x + 16, fn.x + fn.w - 16, slabUsers(fn, d), 0.1), 0) + 0.3 * Math.abs(d);
      if (c < bestC - 1e-6) { bestC = c; bestD = d; }
    }
    row.forEach((nd) => { nd.x += bestD; nd.cx += bestD; });
  };
  if (F.length) for (let round = 0; round < 2; round++) { placeSlabs(); slideRow(); }
  // a link that skips a tier crosses it through a free gap, on the way to its target and near its source;
  // the links of several blocks to one library share one trunk there (placed over that library's slab)
  const PG = [];                         // row -> its gaps, with the pass-throughs placed in each
  for (let t = 1; t <= RL; t++) {
    const row = R[t];
    const gaps = (PG[t] = []);
    let l = sx0 - P.padL + 10;
    for (const nd of row) { gaps.push({ l, r: nd.x - 10, used: [], inner: gaps.length > 0 }); l = nd.x + nd.w + (nd.group ? 8 : 0) + 10; }
    gaps.push({ l, r: sx1 + P.padR - 10, used: [], inner: false });
    gaps.forEach((g) => { g.cap = Math.max(0, Math.floor((g.r - g.l) / P.pitch) + 1); });
    const items = CE.filter((e) => { const [ta, tb] = span(e); return ta < t && t < tb; }).map((e) => {
      const [ta, tb] = span(e), a = byKey(e.a), b = byKey(e.b);
      const w = a.cx + ((b.cx - a.cx) * (t - ta)) / (tb - ta);
      return { es: [e], want: w, lo: w, hi: w, o: a.ord + b.ord / 100 };
    });
    for (const fn of F) {
      const es = trunkAt(fn, t);
      if (!es.length) continue;
      const from = [...new Set(es.map((e) => (byKey(e.a).t === t - 1 ? byKey(e.a).cx : e.xs[t - 1])))];
      items.push({ es, want: from.reduce((a, b) => a + b, 0) / from.length, lo: fn.x + 22, hi: fn.x + fn.w - 22, o: 100 + fn.ord });
    }
    items.forEach((it) => { it.aim = Math.min(it.hi, Math.max(it.lo, it.want)); });
    items.sort((p, q) => p.want - q.want || p.aim - q.aim || p.o - q.o);
    const dist = (g, x) => (x < g.l ? g.l - x : x > g.r ? x - g.r : 0);
    for (const it of items) {
      const cost = (g) => dist(g, it.want) + 2 * Math.max(0, it.lo - g.r, g.l - it.hi);
      const g = gaps.filter((x) => x.used.length < x.cap).sort((p, q) => cost(p) - cost(q) || dist(p, it.want) - dist(q, it.want))[0] || gaps[0];
      g.used.push(it);
    }
    for (const g of gaps) {
      if (!g.used.length) continue;
      // straight through where the link is aimed; otherwise mid-gap (an outer gap: near the aim), within the target's span
      const at = (it) => {
        const want = it.aim >= g.l && it.aim <= g.r ? it.aim : g.inner ? (g.l + g.r) / 2 : Math.min(g.r - 14, Math.max(g.l + 14, it.aim));
        const l = Math.max(g.l, it.lo), r = Math.min(g.r, it.hi);
        return l <= r ? Math.min(r, Math.max(l, want)) : Math.min(g.r, Math.max(g.l, want));
      };
      // left to right in the order of where they head (a trunk bound for a slab on the left passes left of one
      // bound for a slab further right, so the two do not cross under the gap)
      const u = g.used.map((it) => ({ it, x: at(it) })).sort((p, q) => p.it.aim - q.it.aim || p.x - q.x || p.it.want - q.it.want || p.it.o - q.it.o);
      for (let i = 1; i < u.length; i++) u[i].x = Math.max(u[i].x, u[i - 1].x + P.pitch);
      if (u[u.length - 1].x > g.r) { u[u.length - 1].x = g.r; for (let i = u.length - 2; i >= 0; i--) u[i].x = Math.min(u[i].x, u[i + 1].x - P.pitch); }
      u.forEach(({ it, x }) => it.es.forEach((e) => { e.xs[t] = x; }));
    }
  }

  /* ---- ports, links and tracks: out-links leave from ports spread along the bottom of a block, in-links arrive on
     ports spread along its top, each ordered by where it goes; then the runs in every gap are put on tracks */
  const spread = (list, n, inset) => {
    const k = list.length;
    const sp = k > 1 ? Math.min(26, (n.w - 2 * inset) / (k - 1)) : 0;
    list.forEach((it, i) => { it.e.xs[n.t] = n.cx + (i - (k - 1) / 2) * sp; });
  };
  const clampF = (fn, x) => Math.min(fn.x + fn.w - 16, Math.max(fn.x + 16, x));
  const xs0 = new Map(E.map((e) => [e, { ...e.xs }]));      // pass-throughs only, before any port is placed
  let gapTracks = [], gapSegs = [];
  // a straight link (no run in a gap) crosses every run that spans it
  const straightCost = (segs) => {
    let c = 0;
    for (const s of segs) {
      if (s.hi - s.lo > 0.5) continue;
      for (const r of segs) if (r.hi - r.lo > 0.5 && s.ups[0] > r.lo + 0.5 && s.ups[0] < r.hi - 0.5) c += r.from.has(s.src.get(s.ups[0])) ? 2 : 1;
    }
    return c;
  };
  /** place every port, then the tracks; returns the crossings. order: block key -> its out-links, left to right */
  const route = (order = new Map()) => {
    E.forEach((e) => { e.xs = { ...xs0.get(e) }; e.lv = {}; });
    for (const n of N.values()) {
      const outs = E.filter((e) => e.a === n.key).map((e) => {
        const b = byKey(e.b);
        const nx = b.t === n.t + 1 ? (e.kind === 'f' ? clampF(b, n.cx) : b.cx) : e.xs[n.t + 1];
        return { e, k: nx, o: b.ord + (e.kind === 'f' ? 100 : 0) };
      }).sort((p, q) => p.k - q.k || p.o - q.o);
      const o = order.get(n.key);
      if (o) outs.sort((p, q) => o.indexOf(p.e) - o.indexOf(q.e));
      spread(outs, n, 16);
    }
    for (const n of N.values()) {
      const ins = E.filter((e) => e.b === n.key).map((e) => ({ e, k: e.xs[n.t - 1], o: byKey(e.a).ord })).sort((p, q) => p.k - q.k || p.o - q.o);
      spread(ins, n, 18);
    }
    // a pass-through must not run on top of another link's leg: keep it a pitch away from the legs that come down
    // to the gap right above it (ports of the tier above, other pass-throughs) and go on from the gap right below
    // it (ports of the tier below); the ports were spread after the gaps were filled, so nudge it within its gap
    for (let t = 1; t <= RL; t++) {
      for (const g of PG[t]) {
        const its = g.used.map((it) => {
          const own = new Set(it.es), legs = [];
          for (const e of E) {
            if (own.has(e)) continue;
            const [ta, tb] = span(e);
            if (ta <= t - 1 && tb > t - 1) legs.push(e.xs[t - 1]);
            if (t + 1 <= RL && ta < t + 1 && tb >= t + 1) legs.push(e.xs[t + 1]);
          }
          return { it, x: it.es[0].xs[t], ok: (x) => legs.every((b) => Math.abs(b - x) >= P.pitch) };
        }).sort((p, q) => p.x - q.x);
        if (its.every((u) => u.ok(u.x))) continue;
        // nearest free spot for each, left to right; right to left if that runs out of room
        const place = (list, dir) => {
          let prev = dir * -Infinity;
          for (const u of list) {
            const lo = dir > 0 ? Math.max(g.l, prev + P.pitch) : g.l, hi = dir > 0 ? g.r : Math.min(g.r, prev - P.pitch);
            if (lo > hi) return false;
            let best = Math.min(hi, Math.max(lo, u.x));
            for (let d = 0; d <= g.r - g.l; d++) {
              const c = [u.x - d, u.x + d].find((x) => x >= lo && x <= hi && u.ok(x));
              if (c !== undefined) { best = c; break; }
            }
            u.nx = best; prev = best;
          }
          return true;
        };
        if (place(its, 1) || place(its.slice().reverse(), -1)) its.forEach((u) => u.it.es.forEach((e) => { e.xs[t] = u.nx; }));
      }
    }
    // a library port sits right under the arriving line whenever that is over the slab (no jog; a trunk is one port);
    // a link arriving beside the slab lands at the nearest free spot, never pushing a straight one aside
    for (const fn of F) {
      const lo = fn.x + 16, hi = fn.x + fn.w - 16, routes = new Map();
      for (const e of FE.filter((x) => x.b === fn.key)) {
        const k = e.bun ? 'trunk' : e.id;
        if (!routes.has(k)) routes.set(k, { x: e.xs[RL], es: [] });
        routes.get(k).es.push(e);
      }
      const rs = [...routes.values()], taken = [];
      const free = (x, m) => taken.every((t) => Math.abs(t - x) >= m);
      for (const r of rs.filter((q) => q.x >= lo && q.x <= hi)) { r.p = r.x; taken.push(r.x); }
      for (const r of rs.filter((q) => q.p === undefined).sort((p, q) => Math.abs(p.x - fn.cx) - Math.abs(q.x - fn.cx))) {
        const t = Math.min(hi, Math.max(lo, r.x)), dir = r.x > hi ? -1 : 1;
        r.p = t;
        for (let x = t; x >= lo && x <= hi; x += 2 * dir) if (free(x, 16)) { r.p = x; break; }
        taken.push(r.p);
      }
      rs.forEach((r) => r.es.forEach((e) => { e.xs[FL] = r.p; }));
    }
    // a link arriving on a block must not run down right beside another link leaving the tier above (the two read
    // as one line that seems to flow into the wrong block): slide the block's ports along its top, together if that
    // clears them, else one by one in order, until every arriving leg is a pitch clear of the departing ones; a
    // small jog of a link onto its own departure line is straightened while at it
    for (let t = 0; t < tiers - 1; t++) {
      const thru = E.filter((e) => { const [ta, tb] = span(e); return ta <= t && tb >= t + 1; });
      for (const n of t + 1 === FL ? F : R[t + 1]) {
        const slab = n.kind === 'f', lo = n.x + (slab ? 16 : 10), hi = n.x + n.w - (slab ? 16 : 10), gap = slab ? 16 : P.pitch;
        const ports = [];                  // links on one port (a library trunk) move together
        for (const e of thru.filter((x) => x.b === n.key)) {
          let p = ports.find((q) => Math.abs(q.x - e.xs[t + 1]) < 0.5);
          if (!p) ports.push((p = { x: e.xs[t + 1], es: [] }));
          p.es.push(e);
        }
        if (!ports.length) continue;
        ports.sort((a, b) => a.x - b.x);
        for (const p of ports) {
          p.deps = thru.filter((e) => !p.es.includes(e)).map((e) => e.xs[t]);
          p.own = p.es[0].xs[t];
        }
        const clear = (p, x) => p.deps.every((d) => Math.abs(d - x) >= P.pitch);
        const snap = (p) => Math.abs(p.own - p.x) < P.pitch && clear(p, p.own);
        if (ports.every((p) => clear(p, p.x) && (Math.abs(p.own - p.x) < 0.5 || Math.abs(p.own - p.x) >= P.pitch))) continue;
        // together: the smallest shift that clears every port (a straight port is not bent)
        let best = null;
        for (let d = 0; d <= 26 && !best; d += 0.5) {
          for (const s of d ? [-d, d] : [0]) {
            const xs = ports.map((p) => p.x + s);
            if (xs[0] < lo || xs[xs.length - 1] > hi) continue;
            if (ports.every((p, i) => clear(p, xs[i]) && (!s || Math.abs(p.own - p.x) >= 0.5))) { best = xs; break; }
          }
        }
        if (best) ports.forEach((p, i) => { p.x = best[i]; });
        else {                             // one by one, nearest clear spot, keeping the order and a gap between ports
          let prev = -Infinity;
          ports.forEach((p, i) => {
            const a = Math.max(lo, prev + gap), b = hi - (ports.length - 1 - i) * gap;
            let x = Math.min(b, Math.max(a, p.x));
            for (let d = 0; d <= hi - lo; d += 0.5) {
              const c = [p.x - d, p.x + d].find((v) => v >= a && v <= b && clear(p, v));
              if (c !== undefined) { x = c; break; }
            }
            p.x = x; prev = x;
          });
        }
        ports.forEach((p, i) => {           // straighten a small jog when its own line is clear and in order
          if (snap(p) && (i === 0 || p.own - ports[i - 1].x >= gap) && (i === ports.length - 1 || ports[i + 1].x - p.own >= gap) && p.own >= lo && p.own <= hi) p.x = p.own;
          p.es.forEach((e) => { e.xs[t + 1] = p.x; });
        });
      }
    }
    gapTracks = []; gapSegs = [];
    for (let t = 0; t < tiers - 1; t++) {
      const groups = new Map();          // one run per link, or per library trunk
      for (const e of E) {
        const [ta, tb] = span(e);
        if (ta > t || tb < t + 1) continue;
        const k = e.bun ? `b${e.b}` : e.id;
        if (!groups.has(k)) groups.set(k, { key: k, es: [], ups: [], downs: [], src: new Map(), dst: new Map() });
        const g = groups.get(k);
        g.es.push(e);
        if (!g.ups.some((x) => Math.abs(x - e.xs[t]) < 0.5)) { g.ups.push(e.xs[t]); if (ta === t) g.src.set(e.xs[t], e.a); }
        if (!g.downs.some((x) => Math.abs(x - e.xs[t + 1]) < 0.5)) { g.downs.push(e.xs[t + 1]); if (tb === t + 1) g.dst.set(e.xs[t + 1], e.b); }
      }
      const segs = [...groups.values()];
      segs.forEach((s) => { s.from = new Set(s.src.values()); s.to = new Set(s.dst.values()); });
      gapTracks.push(hierTracks(segs));
      segs.forEach((s) => { if (s.lv !== undefined) s.es.forEach((e) => { e.lv[t] = s.lv; }); });
      gapSegs.push(segs);
    }
    return gapSegs.reduce((a, segs) => a + segs.cost + straightCost(segs), 0);
  };
  // second pass: re-order each block's out-ports by the tracks their runs took (a run on a high track should leave
  // from the end of the row it heads for, not pass right under the box through its siblings' legs); kept only if
  // the drawing crosses less overall
  const crossed = route(), order = new Map();
  for (const n of N.values()) {
    const t = n.t, segs = gapSegs[t] || [];
    const outs = E.filter((e) => e.a === n.key).sort((p, q) => p.xs[t] - q.xs[t]);
    const segOf = new Map(outs.map((e) => [e, segs.find((s) => s.es.includes(e))]));
    const mov = outs.filter((e) => segOf.get(e)?.lv !== undefined);       // links that run sideways in this gap
    if (mov.length < 2 || mov.length > 6) continue;
    const slots = mov.map((e) => e.xs[t]);
    const costOf = (perm) => {
      const mod = new Map();
      perm.forEach((e, i) => {
        const s0 = segOf.get(e);
        if (!mod.has(s0)) mod.set(s0, { ...s0, ups: s0.ups.slice(), src: new Map(s0.src) });
        const m = mod.get(s0), j = m.ups.findIndex((x) => Math.abs(x - e.xs[t]) < 0.5);
        m.src.delete(m.ups[j]); m.ups[j] = slots[i]; m.src.set(slots[i], n.key);
      });
      mod.forEach(hierSpan);
      const all = segs.map((x) => mod.get(x) || x), done = new Set();
      let c = 0;
      for (const a of mod.values()) {
        done.add(a);
        for (const b of all) {
          if (done.has(b)) continue;
          if (b.lv === undefined) { if (b.hi - b.lo <= 0.5 && b.ups[0] > a.lo + 0.5 && b.ups[0] < a.hi - 0.5) c += a.from.has(b.src.get(b.ups[0])) ? 2 : 1; continue; }
          c += a.lv < b.lv ? hierRunCost(a, b) : b.lv < a.lv ? hierRunCost(b, a) : 0;
        }
      }
      return c;
    };
    const perms = (a) => (a.length <= 1 ? [a] : a.flatMap((v, i) => perms(a.filter((_, j) => j !== i)).map((q) => [v, ...q])));
    let best = mov, bestC = costOf(mov);
    for (const pm of perms(mov)) { const c = costOf(pm); if (c < bestC) { bestC = c; best = pm; } }
    if (best !== mov) { let i = 0; order.set(n.key, outs.map((e) => (segOf.get(e)?.lv !== undefined ? best[i++] : e))); }
  }
  if (order.size && route(order) > crossed) route();
  // slab text: name (+ counts when they fit beside it), description in up to two lines, users when only a few
  for (const fn of F) {
    const tw = fn.w - 32;
    fn.lines = [];
    fn.cntFits = hierTextW(fn.label, P.nameFs + 0.5, 700) + hierTextW(fn.cnt, P.subFs) + 40 <= fn.w;
    if (!fn.cntFits) fn.lines.push(['h-fdesc', hierFit(fn.cnt, P.subFs, 400, tw)]);
    if (fn.desc) hierWrap(fn.desc, P.subFs, 400, tw, 2).forEach((s) => fn.lines.push(['h-fdesc', s]));
    if (fn.who) hierWrap(fn.who, P.subFs, 400, tw, 2).forEach((s) => fn.lines.push(['h-fwho', s]));
  }
  const slabBody = (n) => 36 + 17 * n;               // name line + n more lines
  P.slabH = slabBody(Math.max(1, ...F.map((fn) => fn.lines.length)));

  /* ---- y: rows and the routing gaps between them */
  const ALL_TOP_TIERS = [
    { lv: 3, key: 'p:soc', name: 'SOC', desc: 'System-on-chip integration', meta: '0 generators · placeholder', boxName: 'SoC placeholder', boxSub: 'Full-chip mixed-signal SoC — no generators yet' },
    { lv: 2, key: 'p:ip', name: 'IP', desc: 'Subsystem & macro IP cores', meta: '0 generators · placeholder', boxName: 'IP placeholder', boxSub: 'Multi-module analog/mixed-signal IP — no generators yet' },
  ];
  const TOP_TIERS = ALL_TOP_TIERS.filter((tp) => tp.lv > L);
  const topBandH = P.nodeH + 28;
  const topH = TOP_TIERS.length * topBandH;
  const rowH = (t) => (t === FL ? P.slabH + P.depth : P.h[t] + (R[t].some((n) => n.group) ? 8 : 0));
  const top = topH + 22, bot = 22, padT = 18, padB = 24;
  const rowTop = [], gapH = [];
  let y = top;
  for (let t = 0; t < tiers; t++) {
    rowTop[t] = y; y += rowH(t);
    if (t < tiers - 1) { const nl = gapTracks[t]; gapH[t] = Math.max(P.gapH, padT + padB + Math.max(0, nl - 1) * P.pitch); y += gapH[t]; }
  }
  const H = Math.ceil(y + bot);
  const trackY = (t, lv) => {
    const nl = gapTracks[t], free = gapH[t] - (nl - 1) * P.pitch;
    return rowTop[t] + rowH(t) + (free * padT) / (padT + padB) + lv * P.pitch;
  };
  const yIn = (k) => rowTop[byKey(k).t];
  const yOut = (n) => rowTop[n.t] + P.h[n.t] + (n.group ? 8 : 0);

  /* ---- texts shared by tooltips, the caption and the list */
  const lvOf = (t) => L - band[t];
  const tierName = (t) => (t === FL ? 'Foundation' : L === 0 ? 'Generators' : lvOf(t) === 0 ? 'Building blocks' : lvOf(t) === 1 ? 'Module' : lvOf(t) === 2 ? 'IP' : 'SOC');
  const techs = [...new Set(F.flatMap((fn) => [fn.f.technology].flat()).filter(Boolean))].map((x) => techLabel(x).replace(/\s*\(.*\)\s*$/, '')).join(', ');
  const tierDesc = (t) => (t === FL ? 'Technology libraries' : L === 0 ? 'Standalone generators' : lvOf(t) === 0 ? 'Reusable analog cells' : lvOf(t) === 1 ? 'Built from blocks below' : lvOf(t) === 2 ? 'Subsystem & macro IP cores' : 'System-on-chip integration');
  const tierMeta = (t) => {
    if (t === FL) return `${techs ? `${techs} · ` : ''}${plural(F.length, 'library', 'libraries')}`;
    const ns = R.filter((_, r) => band[r] === band[t]).flat(), gens = ns.reduce((a, n) => a + n.ids.length, 0);
    return `${plural(gens, 'generator')} · ${fmtN(ns.reduce((a, n) => a + n.count, 0))} designs`;
  };
  // roles of library links, grouped role -> component ids (the members of a group may differ)
  const byRole = (use) => {
    const m = new Map();
    for (const [id, s] of use) for (const r of s.size ? s : ['no role given']) { if (!m.has(r)) m.set(r, []); m.get(r).push(id); }
    return m;
  };
  const why = (e) => {             // how A is built from B, in one line
    if (e.kind === 'c') return `${e.users ? `${plural(e.users, 'design')} reuse ${fmtN(e.targets)}` : 'reused'}${e.roles.size ? ` — ${[...e.roles].join('; ')}` : ''}`;
    const a = byKey(e.a), m = byRole(e.mem);
    const roles = [...m].map(([r, ids]) => (a.group && m.size > 1 ? `${names(ids).join(', ')}: ${r}` : r)).join('; ');
    return a.group ? `${e.mem.size === a.ids.length ? 'all' : `${e.mem.size} of`} ${plural(a.ids.length, 'generator')}: ${roles}` : roles;
  };
  const edgeTip = (e) => {
    const a = byKey(e.a), b = byKey(e.b);
    if (e.kind === 'c') {
      const roles = [...e.roles];
      return `${a.label} · built from ${b.label}${e.users ? `: ${plural(e.users, 'design')} reuse ${plural(e.targets, `${b.label} design`)} (whole catalog)` : ''}${roles.length ? `\nroles: ${roles.join('; ')}` : ''}`;
    }
    const mem = [...e.mem.entries()], roleTxt = (s) => ([...s].length ? [...s].join('; ') : 'no role given');
    if (a.group) return `${a.label} · built from ${b.label} (${mem.length} of ${plural(a.ids.length, 'generator')})\n${mem.map(([id, s]) => `• ${byId[id]?.name || id}: ${roleTxt(s)}`).join('\n')}`;
    return `${a.label} · built from ${b.label}${mem.length ? `\nrole: ${roleTxt(mem[0][1])}` : ''}`;
  };
  const info = (HIER.info = new Map());   // caption per block / link / trunk (shown on hover and keyboard focus)
  const item = (label, txt) => `<b>${esc(label)}</b>${txt ? `: ${esc(txt)}` : ''}`;
  const items = (list, max = 600) => {     // " · "-joined caption items, cut (whole items) when they get long
    let out = '', n = 0;
    for (const [label, txt] of list) {
      if (n && n + label.length + txt.length > max) return `${out} · …`;
      out += `${n ? ' · ' : ''}${item(label, txt)}`; n += label.length + txt.length + 3;
    }
    return out;
  };

  /* ---- markup: bands and tier labels (the gutter is its own SVG, pinned while the panel scrolls sideways) */
  const edgeY = (t) => {      // band boundary: mid-gap, nudged so it falls between two routing tracks rather than on one
    const mid = rowTop[t] + rowH(t) + gapH[t] / 2, nl = gapTracks[t];
    if (!nl) return mid;
    let b = mid, d = Infinity;
    for (let i = -1; i < nl; i++) { const yy = trackY(t, i) + P.pitch / 2; if (Math.abs(yy - mid) < d) { d = Math.abs(yy - mid); b = yy; } }
    return Math.abs(trackY(t, 0) - mid) < P.pitch / 2 || Math.abs(trackY(t, nl - 1) - mid) < P.pitch / 2 || (trackY(t, 0) < mid && trackY(t, nl - 1) > mid) ? b : mid;
  };
  const bandTop = (t) => (t === 0 ? topH : edgeY(t - 1));
  const bandBot = (t) => (t === tiers - 1 ? H : edgeY(t));
  const groups = [];                    // bands: [first row, last row] of each tier
  for (let t = 0; t < tiers; t++) {
    if (t && t < FL && band[t] === band[t - 1]) groups[groups.length - 1][1] = t; else groups.push([t, t]);
  }
  const bands = (sfx, hatch) => {
    let s = F.length && hatch ? `<defs><pattern id="h-hatch-${sfx}" class="h-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0,0 V7"/></pattern></defs>` : '';
    TOP_TIERS.forEach((_, i) => {
      const y0 = i * topBandH, y1 = (i + 1) * topBandH, box = `x="0" y="${f1(y0)}" width="${W}" height="${f1(y1 - y0)}"`;
      s += `<rect class="h-band${i % 2 ? ' alt' : ''}" ${box}/>`;
      if (i) s += `<line class="h-sep" x1="0" x2="${W}" y1="${f1(y0)}" y2="${f1(y0)}"/>`;
    });
    groups.forEach(([t, t1], gi) => {
      const i = TOP_TIERS.length + gi;
      const y0 = bandTop(t), y1 = bandBot(t1), box = `x="0" y="${f1(y0)}" width="${W}" height="${f1(y1 - y0)}"`;
      s += `<rect class="h-band${t === FL ? ' base' : i % 2 ? ' alt' : ''}" ${box}/>`;
      if (t === FL && hatch) s += `<rect fill="url(#h-hatch-${sfx})" ${box}/>`;      // faint substrate hatch under the libraries
      if (i) s += `<line class="h-sep" x1="0" x2="${W}" y1="${f1(y0)}" y2="${f1(y0)}"/>`;
    });
    return s;
  };
  const gutterBlock = (y0, y1, cy, name, descStr, meta) => {
    if (P.wide) {
      const gw = P.gut - 34;
      const desc = hierWrap(descStr, 12, 400, gw, 2);
      const metas = hierTextW(meta, 11) <= gw ? [meta] : meta.split(' · ').map((m) => hierFit(m, 11, 400, gw));
      const lines = [[hierFit(name, 11, 700, gw - 12), 'h-tier'], ...desc.map((d) => [d, 'h-tdesc']), ...metas.map((m) => [m, 'h-tmeta'])];
      const lh = (l) => (l[1] === 'h-tier' ? 17 : 15);
      let yy = cy - lines.reduce((a, l) => a + lh(l), 0) / 2 + 11;
      return lines.map((l) => { const s = `<text class="${l[1]}" x="20" y="${f1(yy)}">${esc(l[0])}</text>`; yy += lh(l); return s; }).join('');
    }
    return `<text class="h-tier" transform="translate(${P.gut / 2 + 4},${f1((y0 + y1) / 2)}) rotate(-90)" text-anchor="middle">${esc(hierFit(name, 10.5, 700, y1 - y0 - 12))}</text>`;
  };
  let gutter = '';
  TOP_TIERS.forEach((tp, i) => {
    const y0 = i * topBandH, y1 = (i + 1) * topBandH;
    gutter += gutterBlock(y0, y1, (y0 + y1) / 2, tp.name, tp.desc, tp.meta);
  });
  for (const [t, t1] of groups) {
    const y0 = bandTop(t), y1 = bandBot(t1), cy = (rowTop[t] + rowTop[t1] + (t === FL ? P.slabH : P.h[t1])) / 2;
    gutter += gutterBlock(y0, y1, cy, tierName(t), tierDesc(t), tierMeta(t));
    // a tier wrapped onto several rows: a bracket spans its rows, so the lower one does not read as a deeper tier
    if (t1 > t && t !== FL) {
      const bx = P.wide ? 9 : 5, b0 = rowTop[t] - 2, b1 = rowTop[t1] + rowH(t1) + 2;
      gutter += `<path class="h-brace" d="M${bx + 4},${f1(b0)} H${bx} V${f1(b1)} H${bx + 4}"/>`;
    }
  }
  gutter += `<line class="h-gline" x1="${P.gut - 0.5}" x2="${P.gut - 0.5}" y1="${P.wide ? 14 : 10}" y2="${H - (P.wide ? 14 : 10)}"/>`;

  // edges: library links underneath, generator links on top (stroke width grows with the designs that reuse the block)
  const maxU = Math.max(1, ...CE.map((e) => e.users));
  const edgeSvg = (e) => {
    const [ta, tb] = span(e), a = byKey(e.a);
    const pts = [[e.xs[ta], yOut(a)]];
    for (let t = ta; t < tb; t++) {
      const x1 = e.xs[t], x2 = e.xs[t + 1];
      if (Math.abs(x1 - x2) > 0.5) { const yy = trackY(t, e.lv[t] || 0); pts.push([x1, yy], [x2, yy]); }
    }
    const xe = e.xs[tb], ye = yIn(e.b), d = hierPath([...pts, [xe, ye - 6.5]], P.r);
    const sw = e.kind === 'c' ? ` style="--sw:${f1(1.25 + Math.sqrt(e.users / maxU))}px"` : '';
    info.set(e.id, `<b>${esc(a.label)}</b> · built from <b>${esc(byKey(e.b).label)}</b>: ${esc(why(e))}`);
    return `<g class="h-edge${e.kind === 'f' ? ' f' : ''}" data-id="${e.id}" data-a="${esc(e.a)}" data-b="${esc(e.b)}"${sw}><title>${esc(edgeTip(e))}</title>
      <path class="h-hit" d="${d}"/><path class="h-e" d="${d}"/><circle class="h-pin" cx="${f1(pts[0][0])}" cy="${f1(pts[0][1])}" r="2.3"/>
      <path class="h-ah" d="M${f1(xe - 3.6)},${f1(ye - 7.5)} L${f1(xe + 3.6)},${f1(ye - 7.5)} L${f1(xe)},${f1(ye - 0.5)} Z"/></g>`;
  };
  // a library trunk: pointing at the shared part traces every link in it
  const trunkSvg = (fn) => {
    const es = FE.filter((e) => e.b === fn.key && e.bun);
    if (es.length < 2) return '';
    const t0 = Math.min(...es.map((e) => byKey(e.a).t)), seg = (t) => gapSegs[t].find((s) => s.key === `b${fn.key}`);
    const runs = [];
    let s = seg(t0), yy = s.lv !== undefined ? trackY(t0, s.lv) : rowTop[t0] + rowH(t0);
    if (s.lv !== undefined) runs.push(`M${f1(s.lo)},${f1(yy)} H${f1(s.hi)}`);
    const pts = [[s.downs[0], yy]];
    for (let t = t0 + 1; t <= RL; t++) {
      s = seg(t);
      if (s.lv === undefined) continue;
      yy = trackY(t, s.lv);
      runs.push(`M${f1(s.lo)},${f1(yy)} H${f1(s.hi)}`);
      pts.push([pts[pts.length - 1][0], yy], [s.downs[0], yy]);
    }
    pts.push([es[0].xs[FL], rowTop[FL] - 6.5]);
    const who = es.map((e) => byKey(e.a).label);
    info.set(`b${fn.key}`, `<b>${esc(and(who))}</b> are built from <b>${esc(fn.label)}</b> (one shared trunk)<br>${items(es.map((e) => [byKey(e.a).label, cut(why(e), 110)]))}`);
    const tip = `${and(who)} are built from ${fn.label} (one shared trunk)\n${es.map((e) => `• ${byKey(e.a).label}: ${why(e)}`).join('\n')}`;
    return `<g class="h-bun" data-id="b${esc(fn.key)}" data-es="${es.map((e) => e.id).join(' ')}"><title>${esc(tip)}</title><path class="h-hit" d="${runs.join(' ')} ${hierPath(pts, P.r)}"/></g>`;
  };
  const edgesSvg = [...FE, ...CE].map(edgeSvg).join('') + F.map(trunkSvg).join('');

  // component nodes (links to their tab; a group opens its first member, the caption and list name them all)
  const outsOf = (k) => E.filter((e) => e.a === k);
  const insOf = (k) => E.filter((e) => e.b === k);
  const nodeSvg = (n) => {
    const c0 = byId[n.ids[0]], y0 = rowTop[n.t], h = P.h[n.t], w = n.w, x = n.x;
    const from = outsOf(n.key), usedE = insOf(n.key), used = usedE.map((e) => byKey(e.a).label);
    const tip = (n.group ? `${n.label}: ${plural(n.ids.length, 'generator')}\n${names(n.ids).join(', ')}` : `${n.label} — ${c0.title}`) +
      `\n${fmtN(n.count)} designs with the current options` + (from.length ? `\nbuilt from: ${from.map((e) => byKey(e.b).label).join(', ')}` : '') + (used.length ? `\nused in: ${used.join(', ')}` : '');
    // the screen-reader label carries what the link tooltips show on hover (reuse counts, roles)
    const fromTxt = from.map((e) => `${byKey(e.b).label} (${why(e)})`);
    const aria = `${n.label}, ${tierName(n.t)} tier: ${fmtN(n.count)} designs${n.group ? `, ${n.ids.length} generators (${names(n.ids).join(', ')})` : ''}.` +
      (fromTxt.length ? ` Built from ${fromTxt.join('; ')}.` : '') + (used.length ? ` Used in ${and(used)}.` : '');
    info.set(n.key, [`<b>${esc(n.label)}</b> · ${n.group ? `${plural(n.ids.length, 'generator')} (${esc(names(n.ids).join(', '))}) · ` : ''}${plural(n.count, 'design')}`,
      from.length ? `Built from ${items(from.map((e) => [byKey(e.b).label, cut(why(e), 120)]))}` : '',
      used.length ? `Used in ${items(usedE.map((e) => [byKey(e.a).label, cut(why(e), 80)]))}` : ''].filter(Boolean).join('<br>'));
    const stack = n.group ? `<rect class="h-stack" x="${f1(x + 8)}" y="${f1(y0 + 8)}" width="${f1(w)}" height="${h}" rx="9"/><rect class="h-stack" x="${f1(x + 4)}" y="${f1(y0 + 4)}" width="${f1(w)}" height="${h}" rx="9"/>` : '';
    const nm = P.names(n), lh = P.nameFs + 2.5, ny = y0 + h / 2 - 2 - ((nm.length - 1) * lh) / 2, sy = ny + (nm.length - 1) * lh + 16;
    return `<a class="h-node t${band[n.t] === 0 && L > 0 ? ' top' : ''}" data-k="${esc(n.key)}" href="${tabHref(n.ids[0])}" aria-label="${esc(aria)}"><title>${esc(tip)}</title>
      <rect class="h-ring" x="${f1(x - 4)}" y="${f1(y0 - 4)}" width="${f1(w + 8 + (n.group ? 8 : 0))}" height="${h + 8 + (n.group ? 8 : 0)}" rx="12"/>${stack}
      <rect class="h-box" x="${f1(x)}" y="${f1(y0)}" width="${f1(w)}" height="${h}" rx="9"/>
      ${nm.map((s, i) => `<text class="h-name" x="${f1(n.cx)}" y="${f1(ny + i * lh)}">${esc(hierFit(s, P.nameFs, 700, w - 18))}</text>`).join('')}
      <text class="h-sub" x="${f1(n.cx)}" y="${f1(sy)}">${esc(hierFit(subOf(n, P), P.subFs, 400, w - 16))}</text></a>`;
  };
  // foundation slabs (not tabs: focusable for the trace, tooltip and caption list the users and their roles)
  const slabSvg = (fn) => {
    const y0 = rowTop[FL], h = P.slabH, x = fn.x, w = fn.w, used = [...fn.use.keys()];
    const tech = fn.f.technology ? techLabel(fn.f.technology) : '';
    const tip = `${fn.label} — ${fn.f.title || ''}${tech ? `\ntechnology: ${tech}` : ''}\n` +
      (used.length ? `used by ${plural(used.length, 'generator')}, which ${used.length === 1 ? 'has' : 'have'} ${plural(fn.designs, 'design')} with the current options:\n${[...fn.use].map(([id, s]) => `• ${byId[id]?.name || id}${byId[id]?.group ? ` (${byId[id].group})` : ''}: ${[...s].join('; ') || 'no role given'}`).join('\n')}` : 'not used by any generator yet');
    const aria = `${fn.label}, foundation library${tech ? ` (${tech})` : ''}${fn.desc ? `: ${fn.desc}` : ''}. ${used.length ? `Used by ${plural(used.length, 'generator')} with ${plural(fn.designs, 'design')}: ${[...fn.use].map(([id, s]) => `${byId[id]?.name || id}${s.size ? ` as ${[...s].join('; ')}` : ''}`).join(', ')}` : 'Not used by any generator yet'}.`;
    info.set(fn.key, `<b>${esc(fn.label)}</b>${fn.desc ? ` · ${esc(fn.desc)}` : ''} · ${used.length ? `used by ${plural(used.length, 'generator')} (${plural(fn.designs, 'design')})<br>${items([...byRole(fn.use)].map(([r, ids]) => [names(ids).join(', '), r]), 420)}` : 'not used by any generator yet'}`);
    let yy = y0 + 23 + (h - slabBody(fn.lines.length)) / 2;
    let txt = `<text class="h-fname" x="${f1(x + 16)}" y="${f1(yy)}">${esc(hierFit(fn.label, P.nameFs + 0.5, 700, w - 32))}</text>`;
    if (fn.cntFits) txt += `<text class="h-fcount" x="${f1(x + w - 16)}" y="${f1(yy)}">${esc(fn.cnt)}</text>`;
    for (const [cls, s] of fn.lines) { yy += 17; txt += `<text class="${cls}" x="${f1(x + 16)}" y="${f1(yy)}">${esc(s)}</text>`; }
    return `<g class="h-node h-found${used.length ? '' : ' unused'}" data-k="${esc(fn.key)}" tabindex="0" role="graphics-symbol" aria-label="${esc(aria)}"><title>${esc(tip)}</title>
      <rect class="h-ring" x="${f1(x - 4)}" y="${f1(y0 - 4)}" width="${f1(w + 8)}" height="${h + P.depth + 8}" rx="12"/>
      <rect class="h-slab-side" x="${f1(x)}" y="${f1(y0 + P.depth)}" width="${f1(w)}" height="${h}" rx="8"/>
      <rect class="h-slab" x="${f1(x)}" y="${f1(y0)}" width="${f1(w)}" height="${h}" rx="8"/>${txt}</g>`;
  };
  const emptySvg = (tp, i) => {
    const h = P.nodeH, y0 = i * topBandH + (topBandH - h) / 2;
    const w = Math.min(S - 20, Math.max(P.minW, hierTextW(tp.boxName, P.nameFs, 700) + 36, hierTextW(tp.boxSub, P.subFs) + 32));
    const x = sx0 + (S - w) / 2, cx = x + w / 2, ny = y0 + h / 2 - 2, sy = ny + 16;
    const tip = `${tp.name} tier — ${tp.desc}\n${tp.boxSub}`;
    const aria = `${tp.name} tier (${tp.desc}): ${tp.boxSub}.`;
    info.set(tp.key, `<b>${esc(tp.name)} tier</b> · ${esc(tp.desc)} — ${esc(tp.boxSub)}`);
    return `<g class="h-node empty" data-k="${esc(tp.key)}" tabindex="0" role="graphics-symbol" aria-label="${esc(aria)}"><title>${esc(tip)}</title>
      <rect class="h-ring" x="${f1(x - 4)}" y="${f1(y0 - 4)}" width="${f1(w + 8)}" height="${h + 8}" rx="12"/>
      <rect class="h-box" x="${f1(x)}" y="${f1(y0)}" width="${f1(w)}" height="${h}" rx="9"/>
      <text class="h-name" x="${f1(cx)}" y="${f1(ny)}">${esc(hierFit(tp.boxName, P.nameFs, 700, w - 18))}</text>
      <text class="h-sub" x="${f1(cx)}" y="${f1(sy)}">${esc(hierFit(tp.boxSub, P.subFs, 400, w - 16))}</text></g>`;
  };
  const nodesSvg = TOP_TIERS.map(emptySvg).join('') + R.flat().map(nodeSvg).join('') + F.map(slabSvg).join('');

  /* ---- legend, caption and the same content as a list */
  const key = (cls) => `<svg class="h-key${cls}" viewBox="0 0 30 10" width="30" height="10" aria-hidden="true"><path class="h-e" d="M3,5 H22"/><circle class="h-pin" cx="3" cy="5" r="2.3"/><path class="h-ah" d="M22,1.4 L29,5 L22,8.6 Z"/></svg>`;
  const widths = `<svg class="h-key" viewBox="0 0 30 10" width="30" height="10" aria-hidden="true"><path class="h-e" d="M1,2.5 H29" style="--sw:1.25px"/><path class="h-e" d="M1,7.5 H29" style="--sw:2.25px"/></svg>`;
  const legend = (CE.length ? `<span>${key('')}built from a generator</span>` : '') +
    (CE.length > 1 && new Set(CE.map((e) => e.users)).size > 1 ? `<span>${widths}thicker: more designs reuse it</span>` : '') +
    (FE.length ? `<span>${key(' f')}built from a foundation library</span>` : '');
  HIER.hint = `${W > avail + 1 ? 'Scroll sideways for the whole diagram. ' : ''}Point at a block or a link, or Tab to a block, to trace it and read how it is built here; click a block to open its tab. Design counts follow the global options${CE.length ? '; reuse counts on links cover the whole catalog' : ''}.`;
  const lnk = (n) => (n.kind === 'f' ? `<b>${esc(n.label)}</b>` : `<a href="${tabHref(n.ids[0])}">${esc(n.label)}</a>`);
  const listNode = (n) => {
    const from = outsOf(n.key), used = insOf(n.key);
    return `<li>${lnk(n)} <span class="subtle">${n.group ? `${plural(n.ids.length, 'generator')} · ` : ''}${plural(n.count, 'design')}</span>` +
      (n.group ? `<div>${n.ids.map((id) => `<a href="${tabHref(id)}">${esc(byId[id].name)}</a> <span class="subtle">${fmtN(shownRows(byId[id]).length)}</span>`).join(', ')}</div>` : '') +
      (from.length ? `<div>built from ${from.map((e) => `${lnk(byKey(e.b))} <span class="subtle">(${esc(why(e))})</span>`).join(', ')}</div>` : '') +
      (used.length ? `<div>used in ${used.map((e) => `${lnk(byKey(e.a))} <span class="subtle">(${esc(why(e))})</span>`).join(', ')}</div>` : '') + '</li>';
  };
  const listSlab = (fn) => `<li><b>${esc(fn.label)}</b> <span class="subtle">${esc(fn.f.title || '')}${fn.f.technology ? ` · ${esc(techLabel(fn.f.technology))}` : ''}</span>` +
    `<div>${fn.use.size ? `used by ${plural(fn.use.size, 'generator')} (${plural(fn.designs, 'design')}):` : 'not used by any generator yet'}</div>` +
    (fn.use.size ? `<ul>${[...byRole(fn.use)].map(([r, ids]) => `<li>${ids.map((id) => `<a href="${tabHref(id)}">${esc(byId[id]?.name || id)}</a>`).join(', ')}: ${esc(r)}</li>`).join('')}</ul>` : '') + '</li>';
  const tierRows = groups.filter(([t]) => t !== FL).map(([t, t1]) => [tierName(t), R.slice(t, t1 + 1).flat()]);
  const list = TOP_TIERS.map((tp) => `<li class="h-lt">${esc(tp.name)}<ul class="hlist"><li class="subtle">${esc(tp.boxSub)}</li></ul></li>`).join('') +
    tierRows.map(([name, ns]) => `<li class="h-lt">${name}<ul class="hlist">${ns.map(listNode).join('')}</ul></li>`).join('') +
    (F.length ? `<li class="h-lt">Foundation<ul class="hlist">${F.map(listSlab).join('')}</ul></li>` : '');
  const label = `Block hierarchy diagram, ${TOP_TIERS.length + groups.length} tiers from top to bottom: ${TOP_TIERS.map((tp) => `${tp.name} (placeholder)`).join('; ')}; ${tierRows.map(([name, ns]) => `${name} (${ns.map((n) => n.label).join(', ')})`).join('; ')}${F.length ? `; Foundation (${F.map((f) => f.label).join(', ')})` : ''}. Arrows point from a block to what it is built from; focus a block for details.`;
  requestAnimationFrame(hierCaptionFit);        // once the section is on the page
  return `<section class="panel hier"><div class="section-head"><h2>Block hierarchy</h2><span class="subtle h-legend">${legend}</span></div>
    <div class="table-scroll h-scroll" style="scroll-padding-left:${P.gut}px"><div class="h-wrap" style="width:${W}px">
      <svg class="h-gsvg${P.wide ? '' : ' compact'}" viewBox="0 0 ${P.gut} ${H}" width="${P.gut}" height="${H}" aria-hidden="true" focusable="false">${bands('g', false)}${gutter}</svg>
      <svg class="hsvg${P.wide ? '' : ' compact'}" viewBox="${P.gut} 0 ${W - P.gut} ${H}" width="${W - P.gut}" height="${H}" role="group" aria-label="${esc(label)}">${bands('m', true)}<g class="h-edges">${edgesSvg}</g><g class="h-lit" aria-hidden="true"></g>${nodesSvg}</svg>
    </div></div>
    <p class="h-info">${HIER.hint}</p>
    <details class="hmore h-more"><summary>Read the hierarchy as a list</summary>
      <p class="subtle h-note">Design counts follow the global options; “N designs reuse M” counts every design in the catalog.</p><ul class="h-list">${list}</ul></details></section>`;
}
/** with a mouse, the caption keeps room for its longer texts at the current width (up to three lines), so the page
    below rarely moves while the pointer crosses the diagram; touch screens keep the CSS minimum */
function hierCaptionFit() {
  const cap = document.querySelector('section.hier .h-info');
  if (!cap || !matchMedia('(any-hover: hover)').matches) return;
  const probe = cap.cloneNode(false);
  probe.style.cssText = `position:absolute;left:0;top:0;visibility:hidden;min-height:0;margin:0;width:${cap.getBoundingClientRect().width}px`;
  cap.after(probe);
  let h = 0;
  for (const html of [HIER.hint, ...HIER.info.values()]) { probe.innerHTML = html; h = Math.max(h, probe.getBoundingClientRect().height); }
  probe.remove();
  if (h) cap.style.minHeight = `${Math.ceil(Math.min(h, 3 * (parseFloat(getComputedStyle(cap).lineHeight) || 19)))}px`;
}
/* hover / keyboard focus on a block, link or trunk highlights its links and neighbours and fills the caption;
   re-layout on width changes */
(function hierInit() {
  let hov = null, foc = null;
  const pick = (el) => (el && el.closest ? el.closest('svg.hsvg .h-node, svg.hsvg .h-edge, svg.hsvg .h-bun') : null);
  const paint = () => {
    for (const svg of document.querySelectorAll('svg.hsvg')) {
      const el = hov && svg.contains(hov) ? hov : foc && svg.contains(foc) ? foc : null;
      svg.querySelectorAll('.on, .nb').forEach((x) => x.classList.remove('on', 'nb'));
      svg.classList.toggle('hl', !!el);
      const cap = svg.closest('.hier')?.querySelector('.h-info'), top = svg.querySelector('.h-lit');
      if (cap) cap.innerHTML = (el && HIER.info.get(el.dataset.k || el.dataset.id)) || HIER.hint;
      top?.replaceChildren();
      if (!el) continue;
      el.classList.add('on');
      const edges = [...svg.querySelectorAll('.h-edges .h-edge')];
      const node = (k) => svg.querySelector(`.h-node[data-k="${CSS.escape(k)}"]`);
      const lit = (g) => { if (!g) return; g.classList.add('on'); node(g.dataset.a)?.classList.add('nb'); node(g.dataset.b)?.classList.add('nb'); };
      if (el.classList.contains('h-bun')) { const ids = el.dataset.es.split(' '); edges.filter((g) => ids.includes(g.dataset.id)).forEach(lit); }
      else if (el.classList.contains('h-edge')) lit(el);
      else {
        const k = el.dataset.k;
        edges.forEach((g) => {
          if (g.dataset.a !== k && g.dataset.b !== k) return;
          g.classList.add('on');
          node(g.dataset.a === k ? g.dataset.b : g.dataset.a)?.classList.add('nb');
        });
      }
      // the whole link layer dims at once (a trunk drawn by several links fades like one line) and the traced
      // links are drawn again on top of it
      top?.replaceChildren(...edges.filter((g) => g.classList.contains('on')).map((g) => {
        const c = g.cloneNode(true);
        c.querySelectorAll('title, .h-hit').forEach((x) => x.remove());
        return c;
      }));
    }
  };
  document.addEventListener('mouseover', (e) => { const t = pick(e.target); if (t !== hov) { hov = t; paint(); } });
  document.addEventListener('mouseout', (e) => { if (!e.relatedTarget && hov) { hov = null; paint(); } });
  document.addEventListener('focusin', (e) => {
    const t = pick(e.target);
    // the browser scrolls a focused SVG element into view only when it is completely hidden: bring a block that the
    // panel's sideways scroll cuts off fully into view (the scroll padding keeps it clear of the pinned gutter)
    const sc = t && !HIER.quiet && t.closest('.h-scroll');
    // a block wider than the visible part shows its left end (its name) rather than its right end
    if (sc) t.scrollIntoView({ block: 'nearest', inline: t.getBoundingClientRect().width > sc.clientWidth - 40 ? 'start' : 'nearest' });
    if (t !== foc) { foc = t; paint(); }
  });
  document.addEventListener('focusout', (e) => { if (!e.relatedTarget && foc) { foc = null; paint(); } });
  const relayout = debounce(() => {
    const sec = document.querySelector('section.hier');
    if (!sec || !CAT || Math.abs(hierAvail() - HIER.avail) < 1) return;
    const sl = sec.querySelector('.h-scroll')?.scrollLeft || 0, open = sec.querySelector('details')?.open;
    const fk = sec.contains(document.activeElement) ? document.activeElement.dataset?.k : null;
    sec.outerHTML = hierarchyHtml();
    const ns = document.querySelector('section.hier');
    if (!ns) return;
    const sc = ns.querySelector('.h-scroll');
    if (sc) sc.scrollLeft = sl;
    if (open) ns.querySelector('details').open = true;
    HIER.quiet = true;                    // put focus back where it was, without scrolling
    if (fk) ns.querySelector(`.h-node[data-k="${CSS.escape(fk)}"]`)?.focus({ preventScroll: true });
    HIER.quiet = false;
  }, 80);
  try { new ResizeObserver(relayout).observe($('#main')); } catch (e) { window.addEventListener('resize', relayout); }
})();

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
        <div class="eyebrow">${c.group ? `${esc(c.group)} · ` : ''}${esc(techLabel(compTechs(c, list.length ? list : famDesigns)))}${short ? ` · ${esc(c.repo || '')}@${esc(short)}` : ''}${c.generated ? ` · exported ${esc(String(c.generated).slice(0, 10))}` : ''}</div>
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
  const multiTech = compTechs(c).length > 1;
  const techOrder = Object.keys(CAT.technologies || {});
  const dTech = (d) => (multiTech ? d.technology || c.technology || '' : '');
  const gMap = new Map();
  for (const d of list) {
    const gk = `${d.vdd ?? ''}\u0001${dTech(d)}`;
    if (!gMap.has(gk)) gMap.set(gk, { k: gk, v: d.vdd, t: dTech(d), ds: [] });
    gMap.get(gk).ds.push(d);
  }
  const groups = [...gMap.values()]
    .sort((a, b) => ((a.v ?? 1e9) - (b.v ?? 1e9)) || ((techOrder.indexOf(b.t) + 1 || 0) - (techOrder.indexOf(a.t) + 1 || 0)))
    .map((g) => ({ ...g, cols: sortKeys([...new Set(g.ds.map((d) => keyOf(d, mx.cols)))], mx.cols) }));
  const cellMap = new Map();
  for (const d of list) {
    const k = `${keyOf(d, mx.rows)}|${d.vdd ?? ''}\u0001${dTech(d)}|${keyOf(d, mx.cols)}`;
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
  const grpLabel = (g) => {
    if (c.vdd_labels?.[String(g.v)]) return Blocks.inline(c.vdd_labels[String(g.v)]);
    return `V<sub>DD</sub> = ${g.v ?? '—'}${g.v != null ? ' V' : ''}${g.t ? ` · <span class="subtle">${esc(techShort(g.t))}</span>` : ''}`;
  };
  const head1 = `<tr><th></th>${groups.map((g) => `<th class="grp" colspan="${g.cols.length}">${grpLabel(g)}</th>`).join('')}</tr>`;
  const head2 = `<tr><th class="rowh">${mx.rows.map((a) => esc(c.axes[a]?.label || a)).join(' · ')}</th>${groups.map((g) => g.cols.map((k) => `<th>${colLabel(k)}</th>`).join('')).join('')}</tr>`;
  const body = rows.map((rk) => `<tr><th class="rowh">${rowLabel(rk)}</th>${groups.map((g) => g.cols.map((ck) => {
    const ds = cellMap.get(`${rk}|${g.k}|${ck}`);
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
  const b = (ok, name) => (ok === undefined || ok === null ? '' : ok === 'partial' ? `<span class="badge warn" title="only part of the layout extracted">${name} partial</span>` : `<span class="badge ${ok ? 'good' : 'bad'}">${name} ${ok ? '✓' : '✗'}</span>`);
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
    return `<tr data-id="${esc(d.id)}"><td class="l wrapt">${esc(d.title)}</td><td>${fmtV(d.vdd)}</td>
      ${axes.map((a) => `<td class="l wrapa">${esc(axisLabel(c, a, d.axes[a]))}</td>`).join('')}
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
  const phys = [['DRC', p.drc], ['LVS', p.lvs], ['PEX', p.pex]].map(([n, v]) => `<span class="badge ${v === true ? 'good' : v === false ? 'bad' : v === 'partial' ? 'warn' : ''}">${n} ${v === true ? '✓' : v === false ? '✗' : v === 'partial' ? 'partial' : 'n/a'}</span>`).join('');
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
  document.title = S.tab ? `${cur ? `${cur.group ? `${cur.group} · ` : ''}${cur.name}` : S.tab} · Analog IC DB` : 'Analog IC DB';
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
