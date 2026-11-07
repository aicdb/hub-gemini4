/* blocks.js — renders aicdb-hub/2 content blocks (see BUILDERS.md §4).
 *
 *   Blocks.render(containerEl, blocks[], ctx)
 *
 * ctx = {
 *   stage, fb, vdd, tech,                 // global options (strings)
 *   src(path) -> URL of a hosted file,     // "hub/x.json", "designs/a/schematic.svg"
 *   repo(file) -> URL of a raw file in the source repo,
 *   thumb(gds, cell) -> {src, cell, width_um, height_um} | null,
 *   json(path) -> Promise<object>,         // cached fetch of a hosted JSON
 *   designHref(id) -> "#/comp/id" | null,  // null when id unknown
 *   plotly() -> Promise<Plotly>,
 * }
 */
(function (global) {
  'use strict';

  const STAGES = ['pre', 'partial', 'full'];
  const STAGE_LABEL = { pre: 'Pre-PEX', partial: 'Partial post-PEX', full: 'Full post-PEX' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };

  /* ------------------------------------------------------------ numbers */
  const PREFIX = [[1e12, 'T'], [1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'µ'], [1e-9, 'n'], [1e-12, 'p'], [1e-15, 'f'], [1e-18, 'a']];
  function num(v, digits = 3) {
    if (typeof v !== 'number' || !isFinite(v)) return String(v);
    const a = Math.abs(v);
    if (Number.isInteger(v) && a < 1e15) return v.toLocaleString('en-US');
    if (a >= 1e4) return Math.round(v).toLocaleString('en-US');
    if (a === 0) return '0';
    return String(+v.toPrecision(digits));
  }
  function fmt(v, spec = {}) {
    if (v === null || v === undefined || v === '') return '—';
    if (typeof v === 'boolean') return v ? '✓' : '✗';
    if (typeof v !== 'number') return esc(v);
    if (isNaN(v)) return '—';
    const unit = spec.unit || '';
    if (spec.si) {
      const a = Math.abs(v);
      let p = PREFIX.find(([f]) => a >= f * 0.9995) || PREFIX[PREFIX.length - 1];
      if (a === 0) p = [1, ''];
      return `${num(v / p[0], spec.digits || 3)} ${p[1]}${esc(unit)}`.trim();
    }
    const n = spec.digits === 0 ? Math.round(v).toLocaleString('en-US') : num(v, spec.digits || 3);
    if (!unit) return n;
    return unit === '%' || unit === '°' ? `${n}${unit}` : `${n} ${esc(unit)}`;
  }

  /* ------------------------------------------------------------ markdown (safe subset) */
  const ALLOWED_TAGS = /&lt;(\/?)(sub|sup|br|b|i|em|strong|code|u|small|kbd)\s*\/?&gt;/g;
  function emph(t) {
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/(^|[^\w])__([^_]+)__(?!\w)/g, '$1<strong>$2</strong>');
    return t.replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<em>$2</em>').replace(/(^|[^_\w])_([^_\s][^_]*?)_(?!\w)/g, '$1<em>$2</em>');
  }
  function inline(s) {
    let t = esc(s);
    const tok = [];
    const put = (html) => { tok.push(html); return `\u0000${tok.length - 1}\u0000`; };
    t = t.replace(/\\([\\`*_[\]()#+\-.!|{}~])/g, (_, c) => put(c));             // backslash escapes
    t = t.replace(/`([^`]+)`/g, (_, c) => put(`<code>${c}</code>`));
    t = t.replace(ALLOWED_TAGS, '<$1$2>');
    t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, u) => put(`<img alt="${alt}" src="${safeUrl(u)}" style="max-width:100%">`));
    t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, txt, u) => put(`<a href="${safeUrl(u)}"${/^https?:/.test(u) ? ' target="_blank" rel="noopener"' : ''}>${emph(txt)}</a>`));
    t = emph(t);
    for (let k = 0; k < 3 && t.includes('\u0000'); k++) t = t.replace(/\u0000(\d+)\u0000/g, (_, i) => tok[+i]);
    return t;
  }
  function safeUrl(u) {
    u = u.replace(/&amp;/g, '&');
    if (/^(https?:|#|\.{0,2}\/|[\w.-]+(\/|$))/.test(u) && !/^javascript:/i.test(u)) return esc(u);
    return '#';
  }
  function md(src) {
    const lines = String(src ?? '').replace(/\r/g, '').split('\n');
    const out = [];
    let i = 0;
    const isTable = (l, n) => /^\s*\|.*\|\s*$/.test(l) && n !== undefined && /^\s*\|?\s*:?-{2,}/.test(n);
    while (i < lines.length) {
      const l = lines[i];
      if (/^\s*$/.test(l)) { i++; continue; }
      let m;
      if ((m = l.match(/^```(\w*)/))) {
        const buf = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        i++;
        out.push(`<pre class="code"><code>${esc(buf.join('\n'))}</code></pre>`);
        continue;
      }
      if ((m = l.match(/^(#{1,5})\s+(.*)$/))) { const n = Math.min(m[1].length + 2, 6); out.push(`<h${n}>${inline(m[2])}</h${n}>`); i++; continue; }
      if (/^\s*(---|\*\*\*)\s*$/.test(l)) { out.push('<hr>'); i++; continue; }
      if (isTable(l, lines[i + 1])) {
        const row = (x) => x.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        const head = row(l); i += 2;
        const body = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) body.push(row(lines[i++]));
        out.push(`<div class="table-scroll"><table class="mt md"><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
        continue;
      }
      if (/^\s*>/.test(l)) {
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
        out.push(`<blockquote>${md(buf.join('\n'))}</blockquote>`);
        continue;
      }
      if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
        const ordered = /^\s*\d+[.)]/.test(l);
        const items = [];
        while (i < lines.length && (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
          const x = lines[i++];
          if (/^\s*([-*+]|\d+[.)])\s+/.test(x) && !/^\s{2,}/.test(x)) items.push(x.replace(/^\s*([-*+]|\d+[.)])\s+/, ''));
          else if (/^\s{2,}([-*+]|\d+[.)])\s+/.test(x)) items[items.length - 1] += `\n${x.replace(/^\s{2}/, '')}`;
          else items[items.length - 1] += ` ${x.trim()}`;
        }
        const tag = ordered ? 'ol' : 'ul';
        out.push(`<${tag}>${items.map((it) => {
          const [first, ...rest] = it.split('\n');
          return `<li>${inline(first)}${rest.length ? md(rest.join('\n')) : ''}</li>`;
        }).join('')}</${tag}>`);
        continue;
      }
      const buf = [];
      while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,5}\s|```|\s*>|\s*([-*+]|\d+[.)])\s+)/.test(lines[i]) && !isTable(lines[i], lines[i + 1])) buf.push(lines[i++]);
      out.push(`<p>${buf.map(inline).join('<br>')}</p>`);
    }
    return out.join('');
  }

  /* ------------------------------------------------------------ visibility (global options) */
  function pickStage(stages, ctx) {
    const idx = STAGES.indexOf(ctx.stage);
    for (let i = idx; i >= (ctx.fb ? 0 : idx); i--) if (stages.includes(STAGES[i])) return STAGES[i];
    return null;
  }
  function passGlobal(b, ctx) {
    if (b.vdd !== undefined && b.vdd !== null && ctx.vdd && String(b.vdd) !== ctx.vdd) return false;
    if (b.tech && ctx.tech && b.tech !== ctx.tech) return false;
    return true;
  }
  /** choose which sibling blocks are visible; stage alternatives share an `alt` key */
  function visibleBlocks(blocks, ctx) {
    const keep = [], groups = new Map(), missing = [];
    (blocks || []).forEach((b, i) => {
      if (!b || typeof b !== 'object' || !passGlobal(b, ctx)) return;
      if (!b.stage) { keep.push([i, b]); return; }
      const k = b.alt || `#${i}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push([i, b]);
    });
    for (const [, list] of groups) {
      const st = pickStage(list.map((x) => x[1].stage), ctx);
      if (st) {
        const e = list.find((x) => x[1].stage === st);
        keep.push([e[0], Object.assign({}, e[1], { _stage: st, _fallback: st !== ctx.stage })]);
      } else if (list[0][1].alt || list[0][1].title) {
        missing.push([list[0][0], { type: '_missing', title: list[0][1].title, stages: list.map((x) => x[1].stage) }]);
      }
    }
    return keep.concat(missing).sort((a, b) => a[0] - b[0]).map((x) => x[1]);
  }

  /* ------------------------------------------------------------ rendering */
  async function render(container, blocks, ctx) {
    const list = visibleBlocks(blocks, ctx);
    for (const b of list) {
      const wrap = document.createElement('div');
      wrap.className = `blk blk-${String(b.type || 'x').replace(/[^\w-]/g, '')}`;
      if (b.span) wrap.style.gridColumn = `span ${b.span}`;
      if (b.id) wrap.id = `blk-${b.id}`;
      container.appendChild(wrap);
      try {
        await renderOne(wrap, b, ctx);
      } catch (e) {
        console.error('block render failed', b, e);
        wrap.innerHTML = `<div class="note bad">Could not render “${esc(b.title || b.type)}”: ${esc(e.message)}</div>`;
      }
    }
  }

  function head(b) {
    const badge = b._stage ? `<span class="badge ${b._fallback ? 'warn' : 'acc'}" title="${b._fallback ? 'Shown from an earlier stage (fallback)' : 'Simulation stage'}">${STAGE_LABEL[b._stage]}</span>` : '';
    return b.title ? `<div class="blk-head"><h3>${inline(b.title)}</h3>${badge}</div>` : (badge ? `<div class="blk-head">${badge}</div>` : '');
  }
  const caption = (b) => (b.caption ? `<div class="blk-cap">${md(b.caption)}</div>` : '');

  const R = {};

  R.section = async (el, b, ctx) => {
    const inner = document.createElement('div');
    inner.className = 'sec-body' + (b.cols > 1 ? ` grid-${Math.min(b.cols, 4)}` : '');
    if (b.collapsed) {
      const d = h(`<details class="sec panel"${b.open ? ' open' : ''}><summary><h2>${inline(b.title || '')}</h2></summary></details>`);
      if (b.intro) d.appendChild(h(`<div class="sec-intro">${md(b.intro)}</div>`));
      d.appendChild(inner); el.appendChild(d);
      let done = false;
      const go = async () => { if (!done) { done = true; await render(inner, b.blocks, ctx); } };
      if (b.open) await go(); else d.addEventListener('toggle', () => d.open && go());
      return;
    }
    const p = h(`<section class="sec panel">${b.title ? `<div class="section-head"><h2>${inline(b.title)}</h2>${b._stage ? `<span class="badge ${b._fallback ? 'warn' : 'acc'}">${STAGE_LABEL[b._stage]}</span>` : ''}</div>` : ''}</section>`);
    if (b.intro) p.appendChild(h(`<div class="sec-intro">${md(b.intro)}</div>`));
    p.appendChild(inner);
    el.appendChild(p);
    await render(inner, b.blocks, ctx);
  };

  R.markdown = async (el, b) => { el.innerHTML = `${head(b)}<div class="md">${md(b.text)}</div>${caption(b)}`; };
  R.note = async (el, b) => { el.innerHTML = `<div class="note ${esc(b.tone || 'info')}">${b.title ? `<b>${inline(b.title)}</b> ` : ''}${md(b.text)}</div>`; };
  R.code = async (el, b) => { el.innerHTML = `${head(b)}<pre class="code" style="max-height:${+b.max_height || 420}px"><code>${esc(b.text)}</code></pre>${caption(b)}`; };
  R._missing = async (el, b, ctx) => {
    el.innerHTML = `<div class="note muted">${b.title ? `<b>${inline(b.title)}</b>: ` : ''}not available at ${STAGE_LABEL[ctx.stage]}${ctx.fb ? ' or earlier' : ''} (available: ${b.stages.map((s) => STAGE_LABEL[s]).join(', ')}).</div>`;
  };

  R.stats = async (el, b) => {
    el.innerHTML = `${head(b)}<div class="stats">${(b.items || []).map((x) => `<div class="stat"><b>${typeof x.value === 'number' ? fmt(x.value, x) : esc(x.value)}</b><span>${inline(x.label)}</span>${x.sub ? `<small>${inline(x.sub)}</small>` : ''}</div>`).join('')}</div>${caption(b)}`;
  };

  R.kv = async (el, b) => {
    const items = (b.items || []).map((x) => (Array.isArray(x) ? { label: x[0], value: x[1], unit: x[2] } : x));
    el.innerHTML = `${head(b)}<dl class="kvgrid" style="--kvcols:${+b.cols || 2}">${items.map((x) => {
      const s = x.s ? ` class="s-${esc(x.s)}"` : '';
      return `<div${s}><dt>${inline(x.label)}</dt><dd>${typeof x.value === 'number' || typeof x.value === 'boolean' ? fmt(x.value, x) : inline(x.value ?? '—')}${typeof x.value !== 'number' && x.unit ? ` ${esc(x.unit)}` : ''}</dd></div>`;
    }).join('')}</dl>${caption(b)}`;
  };

  function imgHtml(src, alt, b = {}) {
    const bg = b.bg === 'dark' ? ' dark' : b.bg === 'none' ? ' nobg' : '';
    const raster = !/\.svg(\?|$)/i.test(src) ? ' raster' : '';
    return `<a class="fig${bg}" href="${src}" target="_blank" rel="noopener"><img class="${raster}" loading="lazy" decoding="async" src="${src}" alt="${esc(alt || '')}" style="max-height:${+b.max_height || 640}px"></a>`;
  }
  function layoutHtml(item, ctx) {
    const t = ctx.thumb(item.gds, item.cell);
    const link = ctx.repo(item.gds);
    const dims = t && t.width_um ? `${num(t.width_um, 4)} × ${num(t.height_um, 4)} µm` : '';
    const cell = t?.cell || item.cell || '';
    return `<div class="layout-thumb">${t ? `<a class="fig dark" href="${link}" target="_blank" rel="noopener" title="Open the GDS file in the source repository (requires repo access)"><img class="raster" loading="lazy" src="${ctx.src(t.src)}" alt="Layout ${esc(cell)}" style="max-height:${+item.max_height || 560}px"></a>` : '<div class="fig ph">no layout preview</div>'}
      <div class="lt-meta"><span class="mono">${esc(cell)}</span>${dims ? ` · ${dims}` : ''} · <a href="${link}" target="_blank" rel="noopener">GDS in repo ↗</a></div></div>`;
  }

  R.image = async (el, b, ctx) => {
    if (b.gds) { el.innerHTML = `${head(b)}${layoutHtml(b, ctx)}${caption(b)}`; return; }
    el.innerHTML = `${head(b)}${imgHtml(ctx.src(b.src), b.alt || b.title, b)}${caption(b)}`;
  };
  R.layout = async (el, b, ctx) => { el.innerHTML = `${head(b)}${layoutHtml(b, ctx)}${caption(b)}`; };

  R.gallery = async (el, b, ctx) => {
    const items = b.items || [];
    const one = (it) => (it.gds ? layoutHtml(it, ctx) : imgHtml(ctx.src(it.src), it.caption || it.label, Object.assign({}, b, it))) + (it.caption ? `<div class="blk-cap">${md(it.caption)}</div>` : '');
    if (b.style === 'grid') {
      el.innerHTML = `${head(b)}<div class="gal-grid" style="--galcols:${+b.cols || 3}">${items.map((it) => `<figure>${it.label ? `<figcaption>${inline(it.label)}</figcaption>` : ''}${one(it)}</figure>`).join('')}</div>${caption(b)}`;
      return;
    }
    el.innerHTML = `${head(b)}<div class="subtabs gal-tabs">${items.map((it, i) => `<button class="chip ${i ? '' : 'on'}" data-i="${i}">${inline(it.label || `#${i + 1}`)}</button>`).join('')}</div><div class="gal-view"></div>${caption(b)}`;
    const view = el.querySelector('.gal-view');
    const show = (i) => { view.innerHTML = one(items[i]); el.querySelectorAll('.gal-tabs .chip').forEach((c) => c.classList.toggle('on', +c.dataset.i === i)); };
    el.querySelector('.gal-tabs').onclick = (e) => { const c = e.target.closest('[data-i]'); if (c) show(+c.dataset.i); };
    if (items.length) show(Math.max(0, Math.min(items.length - 1, +b.default || 0)));
  };

  R.downloads = async (el, b, ctx) => {
    el.innerHTML = `${head(b)}<div class="dl">${(b.items || []).map((x) => {
      const href = x.file ? ctx.repo(x.file) : x.src ? ctx.src(x.src) : x.url ? esc(x.url) : '#';
      const where = x.file ? 'repo' : x.src ? '' : 'external';
      return `<a href="${href}" target="_blank" rel="noopener"${x.src ? ' download' : ''}>${inline(x.label || x.file || x.src)} <span class="subtle mono">${esc((x.file || x.src || '').split('/').pop())}</span>${where === 'repo' ? ' <span class="badge" title="Stored in the private source repository; requires access">repo ↗</span>' : ''}${x.note ? ` <span class="subtle">— ${inline(x.note)}</span>` : ''}</a>`;
    }).join('')}</div>${caption(b)}`;
  };

  R.tabs = async (el, b, ctx) => {
    const stageLabel = (t) => { if (!t.labels) return t.label; const st = pickStage(Object.keys(t.labels), ctx); return st ? t.labels[st] : t.label; };
    const tabs = (b.tabs || []).filter((t) => passGlobal(t, ctx)).map((t) => Object.assign({}, t, { label: stageLabel(t) }));
    const sel = b.style === 'select' || tabs.length > 12;
    el.innerHTML = `${head(b)}${sel
      ? `<label class="tabsel">${esc(b.label || 'Show')} <select>${tabs.map((t, i) => `<option value="${i}">${esc(String(t.label).replace(/<[^>]+>/g, ''))}</option>`).join('')}</select></label>`
      : `<div class="subtabs tabs-bar">${tabs.map((t, i) => `<button class="chip ${i ? '' : 'on'}" data-i="${i}">${inline(t.label)}</button>`).join('')}</div>`}<div class="tab-view"></div>${caption(b)}`;
    const view = el.querySelector('.tab-view');
    let first = true;
    const show = async (i) => {
      view.innerHTML = '';
      el.querySelectorAll('.tabs-bar .chip').forEach((c) => c.classList.toggle('on', +c.dataset.i === i));
      if (b.id && ctx.tabSet && !first) ctx.tabSet(b.id, tabs[i]?.key != null ? tabs[i].key : i);
      first = false;
      if (tabs[i]) await render(view, tabs[i].blocks, ctx);
    };
    if (sel) el.querySelector('select').onchange = (e) => show(+e.target.value);
    else el.querySelector('.tabs-bar').onclick = (e) => { const c = e.target.closest('[data-i]'); if (c) show(+c.dataset.i); };
    const saved = b.id && ctx.tabGet ? ctx.tabGet(b.id) : null;
    // tabs may carry a stable `key`; URLs store the key (robust to tabs hidden by filters), else the index
    let savedIdx = saved == null ? null : tabs.findIndex((t) => t.key != null && String(t.key) === String(saved));
    if (saved != null && savedIdx < 0) savedIdx = /^\d+$/.test(String(saved)) ? +saved : null;
    const start = Math.max(0, Math.min(tabs.length - 1, savedIdx != null ? savedIdx : +b.default || 0));
    if (sel) el.querySelector('select').value = String(start);
    await show(start);
  };

  /* ------------------------------------------------------------ table */
  const cellV = (c) => (c !== null && typeof c === 'object' && !Array.isArray(c) ? c.v : c);
  R.table = async (el, b, ctx) => {
    const data = b.src ? await ctx.json(b.src) : b;
    const cols = (b.columns || data.columns || []).map((c) => (typeof c === 'string' ? { key: c, label: c } : c));
    let rows = (data.rows || []).map((r) => (Array.isArray(r) ? Object.fromEntries(cols.map((c, i) => [c.key, r[i]])) : r));
    // follow the global VDD only for real design supplies: opt-in via vdd_filter:true, or automatic when
    // every value of the 'vdd' column is one of the hub's supplies (corner supplies like 1.62 V never match)
    const isSupplyCol = (vals) => vals.every((v) => v == null || (ctx.vdds || []).includes(String(v)));
    if (ctx.vdd && b.vdd_filter !== false && cols.some((c) => c.key === 'vdd') && (b.vdd_filter === true || isSupplyCol(rows.map((r) => cellV(r.vdd)))))
      rows = rows.filter((r) => cellV(r.vdd) == null || String(cellV(r.vdd)) === ctx.vdd);
    if (ctx.tech && cols.some((c) => c.key === 'tech')) rows = rows.filter((r) => !cellV(r.tech) || cellV(r.tech) === ctx.tech);
    let stageNote = '';
    if (b.stage_column && b.stage_group) {
      // per entity (e.g. design id): keep the row with the best available stage <= selected
      const best = new Map();
      for (const r of rows) { const g = cellV(r[b.stage_group]); const sv = cellV(r[b.stage_column]); if (g == null || !sv) continue; if (!best.has(g)) best.set(g, new Set()); best.get(g).add(sv); }
      const pickFor = new Map([...best].map(([g, set]) => [g, pickStage([...set], ctx)]));
      const fbN = [...pickFor.values()].filter((p) => p && p !== ctx.stage).length;
      rows = rows.filter((r) => { const g = cellV(r[b.stage_group]); const sv = cellV(r[b.stage_column]); return g == null || !sv || sv === pickFor.get(g); });
      stageNote = `best available stage ≤ ${STAGE_LABEL[ctx.stage]}${fbN ? ` (${fbN} from an earlier stage)` : ''}`;
    } else if (b.stage_column) {
      const avail = [...new Set(rows.map((r) => cellV(r[b.stage_column])))].filter(Boolean);
      const st = pickStage(avail, ctx);
      rows = rows.filter((r) => !cellV(r[b.stage_column]) || cellV(r[b.stage_column]) === st);
      stageNote = st ? `${STAGE_LABEL[st]}${st !== ctx.stage ? ' (fallback)' : ''}` : 'no rows at this stage';
    }
    const groups = cols.some((c) => c.group);
    const searchable = b.search ?? rows.length > 15;
    let sortK = b.sort?.key || null, sortD = b.sort?.dir || 'asc', q = '', limit = +b.page_size || 400;
    el.innerHTML = `${head(b)}${(searchable || b.csv !== false) ? `<div class="toolbar tbl-tools">${searchable ? '<input type="search" class="tsearch" placeholder="Filter rows…">' : '<span></span>'}<span class="subtle tcount"></span>${b.csv !== false ? '<button class="plain tcsv">CSV ↓</button>' : ''}</div>` : ''}
      <div class="table-scroll" style="${b.max_height ? `max-height:${+b.max_height}px` : rows.length > 25 ? 'max-height:640px' : ''}"><table class="list blist"><thead></thead><tbody></tbody></table></div><div class="tmore"></div>${caption(b)}`;
    const thead = el.querySelector('thead'), tbody = el.querySelector('tbody');
    const textCol = Object.fromEntries(cols.map((c) => { const v = rows.map((r) => cellV(r[c.key])).find((x) => x !== null && x !== undefined && x !== ''); return [c.key, typeof v === 'string']; }));
    const align = (c) => c.align || (c.type === 'text' || c.type === 'design' || c.type === 'link' || (!c.type && textCol[c.key]) ? 'l' : '');
    const cellHtml = (c, raw) => {
      const v = cellV(raw);
      const s = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
      let inner;
      if (c.type === 'design') {
        const href = v != null ? ctx.designHref(String(v)) : null;
        const txt = c.md ? inline(s.t || v) : esc(s.t || v);
        inner = href ? `<a href="${href}">${txt}</a>` : (c.md ? inline(v ?? '—') : esc(v ?? '—'));
      } else if (c.type === 'link' && s.href) inner = `<a href="${esc(s.href)}" target="_blank" rel="noopener">${esc(v)}</a>`;
      else if (c.type === 'status' || typeof v === 'boolean') inner = v === true ? '✓' : v === false ? '✗' : esc(v ?? '—');
      else if (typeof v === 'number') inner = fmt(v, c);
      else inner = c.md ? inline(v ?? '') : esc(v ?? '—');
      const cls = [align(c), c.wrap ? 'wrap' : '', s.s ? `s-${s.s}` : (c.type === 'status' || typeof v === 'boolean') ? (v === true ? 's-good' : v === false ? 's-bad' : '') : ''].filter(Boolean).join(' ');
      return `<td${cls ? ` class="${cls}"` : ''}${s.title ? ` title="${esc(s.title)}"` : ''}>${inner}</td>`;
    };
    const drawHead = () => {
      let g = '';
      if (groups) {
        const spans = [];
        for (const c of cols) { if (spans.length && spans[spans.length - 1].g === (c.group || '')) spans[spans.length - 1].n++; else spans.push({ g: c.group || '', n: 1 }); }
        g = `<tr class="grp">${spans.map((x) => `<th colspan="${x.n}" class="${x.g ? 'g' : ''}">${inline(x.g)}</th>`).join('')}</tr>`;
      }
      thead.innerHTML = g + `<tr>${cols.map((c) => `<th data-k="${esc(c.key)}" class="${align(c)} ${sortK === c.key ? 'sorted' : ''}" title="${esc(c.title || 'Click to sort')}">${inline(c.label ?? c.key)}${c.unit && !c.si ? `<span class="u"> (${esc(c.unit)})</span>` : c.si && c.unit ? `<span class="u"> (${esc(c.unit)})</span>` : ''}${sortK === c.key ? (sortD === 'asc' ? ' ↑' : ' ↓') : ''}</th>`).join('')}</tr>`;
    };
    const current = () => {
      let r = rows;
      if (q) { const w = q.toLowerCase().split(/\s+/).filter(Boolean); r = r.filter((x) => { const t = cols.map((c) => cellV(x[c.key])).join(' ').toLowerCase(); return w.every((y) => t.includes(y)); }); }
      if (sortK) {
        r = [...r].sort((a, b2) => {
          const x = cellV(a[sortK]), y = cellV(b2[sortK]);
          if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
          const d = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
          return sortD === 'asc' ? d : -d;
        });
      }
      return r;
    };
    const draw = () => {
      drawHead();
      const r = current();
      if (!rows.length && b.stage_column) { tbody.innerHTML = `<tr><td colspan="${cols.length}" class="l s-muted">No rows at ${STAGE_LABEL[ctx.stage]}${ctx.fb ? ' or earlier' : ''} — switch the Simulation option.</td></tr>`; return; }
      tbody.innerHTML = r.slice(0, limit).map((x) => {
        const href = x._design ? ctx.designHref(String(x._design)) : x._href ? esc(x._href) : null;
        return `<tr${href ? ` class="click" data-href="${href}"` : ''}${x._s ? ` data-s="${esc(x._s)}"` : ''}>${cols.map((c) => cellHtml(c, x[c.key])).join('')}</tr>`;
      }).join('');
      const cnt = el.querySelector('.tcount'); if (cnt) cnt.textContent = `${r.length} row${r.length === 1 ? '' : 's'}${stageNote ? ` · ${stageNote}` : ''}`;
      el.querySelector('.tmore').innerHTML = r.length > limit ? `<button class="plain more-btn">Show ${Math.min(r.length - limit, 1000)} more of ${r.length - limit}</button>` : '';
      const mb = el.querySelector('.tmore button'); if (mb) mb.onclick = () => { limit += 1000; draw(); };
    };
    thead.onclick = (e) => { const th = e.target.closest('th[data-k]'); if (!th) return; const k = th.dataset.k; if (sortK === k) sortD = sortD === 'asc' ? 'desc' : 'asc'; else { sortK = k; const c = cols.find((x) => x.key === k); sortD = c?.better === 'high' ? 'desc' : 'asc'; } draw(); };
    tbody.onclick = (e) => { if (e.target.closest('a')) return; const tr = e.target.closest('tr[data-href]'); if (!tr) return; const h = tr.dataset.href; if (/^https?:/.test(h)) window.open(h, '_blank', 'noopener'); else location.hash = ctx.keepGlobals ? ctx.keepGlobals(h) : h; };
    const si = el.querySelector('.tsearch'); if (si) si.oninput = () => { q = si.value.trim(); draw(); };
    const cb = el.querySelector('.tcsv'); if (cb) cb.onclick = () => {
      const qq = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
      const lines = [cols.map((c) => qq(`${c.label ?? c.key}${c.unit ? ` [${c.unit}]` : ''}`.replace(/<[^>]+>/g, ''))).join(',')];
      for (const x of current()) lines.push(cols.map((c) => qq(cellV(x[c.key]))).join(','));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
      a.download = `${(b.csv_name || b.title || 'table').replace(/<[^>]+>/g, '').replace(/[^\w.-]+/g, '_').slice(0, 60)}.csv`; a.click();
    };
    draw();
  };

  /* ------------------------------------------------------------ charts (Plotly) */
  function themeColors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n, d) => (cs.getPropertyValue(n) || d).trim();
    return { ink: v('--ink', '#2b1a17'), muted: v('--muted', '#7a5c52'), line: v('--line', '#f0dccd'), paper: v('--paper', '#fff'),
      brand: v('--brand', '#d9423a'), accent: v('--accent', '#c4372f'), soft: v('--soft', '#fff1e6'), good: v('--good', '#166534'), warn: v('--warn', '#854d0e'), bad: v('--bad', '#991b1b') };
  }
  /** replace "theme:<token>" strings anywhere in a figure with the current theme colour */
  function themeify(x, t = themeColors()) {
    if (typeof x === 'string') return x.startsWith('theme:') ? (t[x.slice(6)] || x) : x;
    if (Array.isArray(x)) return x.map((y) => themeify(y, t));
    if (x && typeof x === 'object') { const o = {}; for (const [k, v] of Object.entries(x)) o[k] = themeify(v, t); return o; }
    return x;
  }
  const COLORWAY = ['#d9423a', '#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd', '#17becf', '#e377c2', '#8c564b', '#bcbd22', '#7f7f7f', '#393b79', '#637939', '#a55194', '#6b6ecf'];
  function deepMerge(base, over) {
    if (!over || typeof over !== 'object' || Array.isArray(over)) return over === undefined ? base : over;
    const out = Array.isArray(base) ? [...base] : Object.assign({}, base);
    for (const [k, v] of Object.entries(over)) out[k] = v && typeof v === 'object' && !Array.isArray(v) && base && typeof base[k] === 'object' ? deepMerge(base[k], v) : v;
    return out;
  }
  function baseLayout(height) {
    const t = themeColors();
    const ax = { gridcolor: t.line, zerolinecolor: t.line, linecolor: t.line, tickcolor: t.line, automargin: true, exponentformat: 'SI', title: { font: { size: 12 } } };
    return {
      height, autosize: true, margin: { l: 60, r: 20, t: 40, b: 50 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', colorway: COLORWAY,
      font: { family: 'Inter, system-ui, sans-serif', size: 12, color: t.ink },
      xaxis: ax, yaxis: ax, xaxis2: ax, yaxis2: ax, xaxis3: ax, yaxis3: ax, xaxis4: ax, yaxis4: ax,
      legend: { orientation: 'h', x: 0, xanchor: 'left', y: 1.02, yanchor: 'bottom', font: { size: 11 } }, hoverlabel: { font: { size: 11 } },
      modebar: { orientation: 'v', bgcolor: 'rgba(0,0,0,0)' },   // vertical, so it never covers the top legend
    };
  }
  function filterTraces(traces, ctx) {
    const meta = (t) => (t.meta && typeof t.meta === 'object' && !Array.isArray(t.meta) ? t.meta : {});
    const stages = [...new Set((traces || []).map((t) => meta(t).stage).filter(Boolean))];
    const pick = stages.length ? pickStage(stages, ctx) : null;
    return (traces || []).filter((t) => {
      const m = meta(t);
      if (m.vdd != null && ctx.vdd && String(m.vdd) !== ctx.vdd) return false;
      if (m.stage && m.stage !== pick) return false;   // trace-level stage alternatives
      return true;
    });
  }
  async function plot(div, traces, layout, b, ctx) {
    const P = await ctx.plotly();
    await P.newPlot(div, traces, layout, Object.assign({ responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d'] }, b.config || {}));
    if (b.link_designs) {
      div.on('plotly_click', (ev) => {
        const p = ev.points?.[0]; if (!p) return;
        const id = Array.isArray(p.customdata) ? p.customdata[0] : p.customdata;
        const href = id != null ? ctx.designHref(String(id)) : null;
        if (href) location.hash = href;
      });
    }
    return div;
  }
  R.chart = async (el, b, ctx) => {
    const fig = b.src ? await ctx.json(b.src) : b;
    el.innerHTML = `${head(b)}<div class="chart"></div>${caption(b)}`;
    const div = el.querySelector('.chart');
    const height = +b.height || +fig.layout?.height || 380;
    const layout = deepMerge(baseLayout(height), themeify(fig.layout || {}));
    layout.height = height;
    for (const [k, ax] of Object.entries(layout)) if (/^[xy]axis\d*$/.test(k) && ax && ax.type === 'log' && ax.dtick === undefined && ax.tickvals === undefined) ax.dtick = 'D2';
    const traces = themeify(filterTraces(fig.data, ctx));
    if (!traces.length) { div.innerHTML = '<div class="note muted">No data for the current options.</div>'; return; }
    await plot(div, traces, layout, b, ctx);
  };

  /* ------------------------------------------------------------ explorer (design-space) */
  const SYMBOLS = ['circle', 'x', 'diamond', 'square', 'triangle-up', 'cross', 'star', 'triangle-down', 'pentagon', 'hexagon'];
  R.explorer = async (el, b, ctx) => {
    const pnorm = (v) => (v === true ? 'all' : v === false || v == null ? '' : String(v));
    const data = await ctx.json(b.src);
    const dims = (b.dims || data.dims || []).map((d) => Object.assign({ type: 'num' }, d));
    const D = Object.fromEntries(dims.map((d) => [d.key, d]));
    let C = data.columns;
    if (!C && data.rows) { C = {}; for (const d of dims) C[d.key] = data.rows.map((r) => r[d.key]); }
    const extra = [b.design_key, b.highlight, b.label_key].filter(Boolean);
    if (data.rows) for (const k of extra) if (!C[k]) C[k] = data.rows.map((r) => r[k]);
    const N = Math.max(0, ...Object.values(C).map((a) => a.length));
    const num = dims.filter((d) => d.type !== 'cat'), cat = dims.filter((d) => d.type === 'cat');
    const st = {
      x: b.x || num[0]?.key, y: b.y || num[1]?.key, color: b.color ?? (cat[0]?.key || ''), symbol: b.symbol || '',
      facet: b.facet_default || '', logx: D[b.x]?.log ?? false, logy: D[b.y]?.log ?? false, pareto: pnorm(b.pareto_default),
      f: {}, r: {},
    };
    for (const k of b.filters || []) if (D[k]?.type === 'cat') st.f[k] = new Set();
    const applyShow = (show) => { for (const [k, vals] of Object.entries(show || {})) if (st.f[k]) st.f[k] = new Set((C[k] ? [...new Set(C[k])] : []).filter((v) => v != null).map(String).filter((v) => !vals.map(String).includes(v))); };
    applyShow(b.filters_default);
    // global options
    let base = new Uint8Array(N).fill(1);
    if (ctx.vdd && C.vdd && b.vdd_filter !== false && (b.vdd_filter === true || C.vdd.every((v) => v == null || (ctx.vdds || []).includes(String(v)))))
      for (let i = 0; i < N; i++) if (C.vdd[i] != null && String(C.vdd[i]) !== ctx.vdd) base[i] = 0;
    if (ctx.tech && C.tech) for (let i = 0; i < N; i++) if (C.tech[i] && C.tech[i] !== ctx.tech) base[i] = 0;
    let stageNote = '';
    if (C.stage && b.stage_group && C[b.stage_group]) {
      // per entity (e.g. design id): keep the row of the best available stage <= selected
      const groups = new Map();
      for (let i = 0; i < N; i++) { const g = C[b.stage_group][i]; if (g == null) continue; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(i); }
      let fbN = 0;
      for (const idxs of groups.values()) {
        const pick = pickStage([...new Set(idxs.map((i) => C.stage[i]).filter(Boolean))], ctx);
        if (pick && pick !== ctx.stage) fbN++;
        for (const i of idxs) if (C.stage[i] != null && C.stage[i] !== pick) base[i] = 0;
      }
      const pickAll = pickStage([...new Set(C.stage.filter(Boolean))], ctx);
      for (let i = 0; i < N; i++) if (C[b.stage_group][i] == null && C.stage[i] != null && C.stage[i] !== pickAll) base[i] = 0;
      stageNote = ` · best available stage ≤ ${STAGE_LABEL[ctx.stage]}${fbN ? ` (${fbN} from an earlier stage)` : ''}`;
    } else if (C.stage) {
      const pick = pickStage([...new Set(C.stage)], ctx);
      for (let i = 0; i < N; i++) if (C.stage[i] != null && C.stage[i] !== pick) base[i] = 0;
      stageNote = pick ? ` · ${STAGE_LABEL[pick]}${pick !== ctx.stage ? ' (fallback)' : ''}` : ' · no data at this stage';
    }
    const label = (k, v) => (D[k]?.labels?.[v] ?? v);
    const catLabels = (k) => catVals(k).map((v) => label(k, v));
    const catVals = (k) => {
      const order = D[k]?.order || Object.keys(D[k]?.labels || {});
      const seen = [...new Set(C[k] || [])].filter((v) => v != null);
      return [...order.filter((v) => seen.includes(v)), ...seen.filter((v) => !order.includes(v)).sort()];
    };
    const opt = (list, cur, none) => (none ? `<option value="">${none}</option>` : '') + list.map((d) => `<option value="${esc(d.key)}" ${d.key === cur ? 'selected' : ''}>${esc(d.label || d.key)}${d.unit ? ` (${esc(d.unit)})` : ''}</option>`).join('');
    el.innerHTML = `${head(b)}${b.intro ? `<div class="md">${md(b.intro)}</div>` : ''}
      ${b.presets?.length ? `<div class="subtabs ex-presets">${b.presets.map((p, i) => `<button class="chip" data-p="${i}">${inline(p.label)}</button>`).join('')}</div><div class="md ex-desc subtle"></div>` : ''}
      <div class="ex-controls">
        <label>X <select data-c="x">${opt(num.concat(b.cat_axes ? cat : []), st.x)}</select></label>
        <label class="check"><input type="checkbox" data-c="logx" ${st.logx ? 'checked' : ''}> log</label>
        <label>Y <select data-c="y">${opt(num.concat(b.cat_axes ? cat : []), st.y)}</select></label>
        <label class="check"><input type="checkbox" data-c="logy" ${st.logy ? 'checked' : ''}> log</label>
        <label>Color <select data-c="color">${opt(dims, st.color, 'none')}</select></label>
        ${cat.length ? `<label>Symbol <select data-c="symbol">${opt(cat, st.symbol, 'none')}</select></label>` : ''}
        ${cat.length ? `<label>Facet <select data-c="facet">${opt(cat, st.facet, 'none')}</select></label>` : ''}
        <label title="Non-dominated (Pareto) points for the current axes (direction from each metric's 'better')">Pareto <select data-c="pareto"><option value="">off</option><option value="all" ${st.pareto === 'all' ? 'selected' : ''}>overall front</option><option value="color" ${st.pareto === 'color' ? 'selected' : ''}>front per colour group</option></select></label>
      </div>
      <div class="ex-filters">${(b.filters || []).map((k) => {
        const d = D[k]; if (!d) return '';
        if (d.type === 'cat') return `<div class="frow"><span class="lbl">${esc(d.label || k)}</span><div class="chips">${catVals(k).map((v) => `<button class="chip ${st.f[k]?.has(String(v)) ? '' : 'on'}" data-f="${esc(k)}" data-v="${esc(v)}">${esc(label(k, v))}</button>`).join('')}</div></div>`;
        return `<div class="frow"><span class="lbl">${esc(d.label || k)}${d.unit ? ` (${esc(d.unit)})` : ''}</span><div class="chips"><input type="number" step="any" placeholder="min" data-r="${esc(k)}" data-e="0"> – <input type="number" step="any" placeholder="max" data-r="${esc(k)}" data-e="1"></div></div>`;
      }).join('')}</div>
      <div class="subtle ex-count"></div><div class="ex-plots"></div>${caption(b)}`;
    const plots = el.querySelector('.ex-plots');
    const keyOf = (k, i) => C[k]?.[i];
    const pass = (i) => {
      if (!base[i]) return false;
      for (const [k, set] of Object.entries(st.f)) if (set.size && set.has(String(keyOf(k, i)))) return false;
      for (const [k, [lo, hi]] of Object.entries(st.r)) { const v = keyOf(k, i); if (v == null || (lo != null && v < lo) || (hi != null && v > hi)) return false; }
      const x = keyOf(st.x, i), y = keyOf(st.y, i);
      if (x == null || y == null) return false;
      if ((st.logx && D[st.x]?.type !== 'cat' && !(x > 0)) || (st.logy && D[st.y]?.type !== 'cat' && !(y > 0))) return false;
      return true;
    };
    const axisTitle = (k) => { const d = D[k] || {}; return `${d.label || k}${d.unit ? ` (${d.unit})` : ''}`; };
    const hoverKeys = [...new Set([st.x, st.y, ...(b.hover || [])])];
    const hoverText = (i) => (b.label_key && C[b.label_key] ? `<b>${esc(C[b.label_key][i])}</b><br>` : '') + hoverKeys.filter((k) => C[k]).map((k) => { const d = D[k] || {}; const v = C[k][i]; return `${esc(d.label || k)}: ${typeof v === 'number' ? fmt(v, d) : esc(label(k, v))}`; }).join('<br>');
    const pareto = (idx) => {
      const dx = D[st.x]?.better === 'high' ? -1 : 1, dy = D[st.y]?.better === 'low' ? 1 : -1; // default: minimise x, maximise y
      const pts = idx.map((i) => [C[st.x][i] * dx, C[st.y][i] * dy, i]).sort((a, c) => a[0] - c[0] || a[1] - c[1]);
      const front = []; let best = Infinity;
      for (const p of pts) if (p[1] < best) { front.push(p[2]); best = p[1]; }
      return front;
    };
    const logTicks = (r) => (r && r[1] - r[0] >= 1.5 ? { dtick: 1, minor: { dtick: 'D1', showgrid: false } } : {});
    const draw = async () => {
      const P = await ctx.plotly();
      const idx = []; for (let i = 0; i < N; i++) if (pass(i)) idx.push(i);
      const total = base.reduce((a, v) => a + v, 0);
      el.querySelector('.ex-count').textContent = `${idx.length.toLocaleString('en-US')} of ${total.toLocaleString('en-US')} points${stageNote}${b.design_key && b.highlight ? ' · click a ringed point to open the design' : b.design_key ? ' · click a point with a design to open it' : ''}`;
      const facets = st.facet ? catVals(st.facet).filter((v) => idx.some((i) => C[st.facet][i] === v)) : [null];
      const multi = facets.length > 1;
      // axis ranges: shared across facets; with fixed_axes over every point of the block (stable when filtering)
      const rIdx = b.fixed_axes ? [...Array(N).keys()].filter((i) => C[st.x]?.[i] != null && C[st.y]?.[i] != null) : idx;
      const xr = D[st.x]?.type === 'cat' ? [] : rIdx.map((i) => C[st.x][i]).filter((v) => typeof v === 'number' && (!st.logx || v > 0));
      const yr = D[st.y]?.type === 'cat' ? [] : rIdx.map((i) => C[st.y][i]).filter((v) => typeof v === 'number' && (!st.logy || v > 0));
      const rng = (arr, log) => { if (!arr.length) return undefined; let lo = Infinity, hi = -Infinity; for (const v of arr) { if (v < lo) lo = v; if (v > hi) hi = v; } if (log) { lo = Math.log10(lo); hi = Math.log10(hi); } const p = (hi - lo) * 0.04 || 1; return [lo - p, hi + p]; };
      const xR = rng(xr, st.logx), yR = rng(yr, st.logy);
      plots.innerHTML = '';
      plots.className = `ex-plots${multi ? ' facets' : ''}`;
      const colorD = D[st.color];
      const isHi = (i) => (b.highlight ? !!C[b.highlight]?.[i] : false);
      const paretoOk = (i) => (b.pareto_include_highlight || !isHi(i)) && Object.entries(b.pareto_on || {}).every(([k, vals]) => vals.map(String).includes(String(C[k]?.[i])));
      const ink = themeColors().ink, muted = themeColors().muted;
      const colOf = (v, ci) => colorD?.colors?.[v] || COLORWAY[ci % COLORWAY.length];
      // facet grids get one HTML legend instead of a Plotly legend per facet
      if (multi) {
        const sw = [];
        if (colorD && colorD.type === 'cat') catVals(st.color).forEach((v, ci) => sw.push(`<span><i style="background:${colOf(v, ci)}"></i>${esc(label(st.color, v))}</span>`));
        if (st.symbol) catVals(st.symbol).forEach((v, si) => sw.push(`<span><b class="sym">${['●', '✕', '◆', '■', '▲', '✚', '★', '▼', '⬟', '⬢'][si % 10]}</b>${esc(label(st.symbol, v))}</span>`));
        if (b.highlight) sw.push(`<span><b class="sym">◯</b>${esc(b.highlight_label || 'Delivered designs')}</span>`);
        if (st.pareto) sw.push(`<span><b class="sym">┈</b>${st.pareto === 'color' ? 'Pareto front per colour group' : 'Pareto front'}</span>`);
        plots.insertAdjacentHTML('beforebegin', '');
        const lg = document.createElement('div'); lg.className = 'ex-legend'; lg.innerHTML = sw.join('');
        plots.appendChild(lg);
      }
      for (const fv of facets) {
        const fi = fv === null ? idx : idx.filter((i) => C[st.facet][i] === fv);
        const traces = [];
        const showL = !multi;
        const mk = (sub, name, extraMarker = {}) => {
          const sy = st.symbol ? sub.map((i) => SYMBOLS[catVals(st.symbol).indexOf(C[st.symbol][i]) % SYMBOLS.length]) : undefined;
          return {
            type: sub.length > 4000 ? 'scattergl' : 'scatter', mode: 'markers', name,
            x: sub.map((i) => (D[st.x]?.type === 'cat' ? label(st.x, C[st.x][i]) : C[st.x][i])), y: sub.map((i) => (D[st.y]?.type === 'cat' ? label(st.y, C[st.y][i]) : C[st.y][i])),
            text: sub.map(hoverText), hovertemplate: '%{text}<extra></extra>',
            customdata: b.design_key ? sub.map((i) => C[b.design_key][i]) : undefined,
            marker: Object.assign({ size: sub.length > 3000 ? 4 : 6, opacity: 0.75, symbol: sy }, extraMarker),
            showlegend: showL, legendgroup: name,
          };
        };
        if (colorD && colorD.type === 'cat') {
          catVals(st.color).forEach((v, ci) => {
            const sub = fi.filter((i) => C[st.color][i] === v);
            if (sub.length) traces.push(mk(sub, String(label(st.color, v)), { color: colOf(v, ci) }));
          });
        } else if (colorD) {
          traces.push(mk(fi, 'points', { color: fi.map((i) => C[st.color][i]), colorscale: 'Viridis', showscale: !multi || fv === facets[0], colorbar: { title: { text: axisTitle(st.color), side: 'right' }, thickness: 12 } }));
        } else traces.push(mk(fi, 'points', { color: COLORWAY[0] }));
        // symbol legend entries (the point traces are split by colour, so symbols need their own key)
        if (st.symbol && showL) catVals(st.symbol).forEach((v, si) => traces.push({ type: 'scatter', mode: 'markers', x: [null], y: [null], name: `${D[st.symbol]?.label || st.symbol}: ${label(st.symbol, v)}`, marker: { symbol: SYMBOLS[si % SYMBOLS.length], color: muted, size: 8 }, hoverinfo: 'skip', legendgroup: `sym-${v}` }));
        const hi = fi.filter(isHi);
        if (hi.length) traces.push(Object.assign(mk(hi, b.highlight_label || 'Delivered designs', { size: 12, opacity: 1, color: ink, symbol: 'circle-open', line: { width: 2, color: ink } }), { type: 'scatter' }));
        let frontN = 0;
        if (st.pareto && fi.length && D[st.x]?.type !== 'cat' && D[st.y]?.type !== 'cat') {
          const cand = fi.filter(paretoOk);
          const groups = st.pareto === 'color' && colorD?.type === 'cat' ? catVals(st.color).map((v, ci) => [v, cand.filter((i) => C[st.color][i] === v), colOf(v, ci)]) : [[null, cand, ink]];
          for (const [gv, gi, gc] of groups) {
            if (!gi.length) continue;
            const fr = pareto(gi).sort((a, c) => C[st.x][a] - C[st.x][c]);
            frontN += fr.length;
            traces.push({ type: 'scatter', mode: 'lines', name: gv === null ? 'Pareto front' : `front: ${label(st.color, gv)}`, x: fr.map((i) => C[st.x][i]), y: fr.map((i) => C[st.y][i]), line: { color: gc, width: 2, dash: gv === null ? 'dot' : 'solid', shape: 'hv' }, text: fr.map(hoverText), hovertemplate: '%{text}<extra>Pareto</extra>', customdata: b.design_key ? fr.map((i) => C[b.design_key][i]) : undefined, showlegend: showL && gv === null, legendgroup: gv === null ? 'pareto' : String(label(st.color, gv)) });
          }
        }
        const div = document.createElement('div');
        div.className = 'chart';
        plots.appendChild(div);
        const xa = D[st.x]?.type === 'cat' ? { title: { text: axisTitle(st.x) }, type: 'category', categoryorder: 'array', categoryarray: catLabels(st.x) } : Object.assign({ title: { text: axisTitle(st.x) }, type: st.logx ? 'log' : 'linear', range: xR }, st.logx ? logTicks(xR) : {});
        const ya = D[st.y]?.type === 'cat' ? { title: { text: axisTitle(st.y) }, type: 'category', categoryorder: 'array', categoryarray: catLabels(st.y) } : Object.assign({ title: { text: axisTitle(st.y) }, type: st.logy ? 'log' : 'linear', range: yR }, st.logy ? logTicks(yR) : {});
        const layout = deepMerge(baseLayout(multi ? 300 : (+b.height || 520)), {
          title: fv !== null ? { text: `${esc(label(st.facet, fv))} <span style="font-size:11px">· ${fi.length.toLocaleString('en-US')} pts${st.pareto ? ` · ${frontN} on front` : ''}</span>`, font: { size: 13 }, y: 0.98 } : undefined,
          xaxis: xa, yaxis: ya,
          margin: multi ? { l: 55, r: 10, t: 34, b: 45 } : undefined,
          showlegend: showL,
        });
        await P.newPlot(div, traces, layout, { responsive: true, displaylogo: false, displayModeBar: multi ? false : 'hover' });
        if (b.design_key) div.on('plotly_click', (ev) => { const id = ev.points?.[0]?.customdata; const href = id != null ? ctx.designHref(String(id)) : null; if (href) location.hash = href; });
      }
    };
    el.querySelector('.ex-controls').onchange = (e) => {
      const c = e.target.dataset.c; if (!c) return;
      st[c] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
      if (c === 'x') { st.logx = !!D[st.x]?.log; el.querySelector('[data-c=logx]').checked = st.logx; }
      if (c === 'y') { st.logy = !!D[st.y]?.log; el.querySelector('[data-c=logy]').checked = st.logy; }
      draw();
    };
    el.querySelector('.ex-filters').onclick = (e) => {
      const c = e.target.closest('[data-f]'); if (!c) return;
      const set = st.f[c.dataset.f];
      if (set.has(c.dataset.v)) set.delete(c.dataset.v); else set.add(c.dataset.v);
      c.classList.toggle('on', !set.has(c.dataset.v));
      draw();
    };
    el.querySelector('.ex-filters').oninput = (e) => {
      const k = e.target.dataset.r; if (!k) return;
      const r = st.r[k] || [null, null];
      r[+e.target.dataset.e] = e.target.value === '' ? null : +e.target.value;
      st.r[k] = r; draw();
    };
    const pr = el.querySelector('.ex-presets');
    if (pr) pr.onclick = (e) => {
      const c = e.target.closest('[data-p]'); if (!c) return;
      const p = b.presets[+c.dataset.p];
      Object.assign(st, { x: p.x ?? st.x, y: p.y ?? st.y, color: p.color ?? st.color, facet: p.facet ?? '', symbol: p.symbol ?? st.symbol, logx: p.logx ?? !!D[p.x ?? st.x]?.log, logy: p.logy ?? !!D[p.y ?? st.y]?.log, pareto: pnorm(p.pareto) });
      if (p.show) {
        for (const k of Object.keys(st.f)) st.f[k] = new Set();
        for (const [k, vals] of Object.entries(p.show)) if (st.f[k]) st.f[k] = new Set(catVals(k).map(String).filter((v) => !vals.map(String).includes(v)));
        el.querySelectorAll('.ex-filters [data-f]').forEach((c) => c.classList.toggle('on', !st.f[c.dataset.f]?.has(c.dataset.v)));
      }
      for (const k of ['x', 'y', 'color', 'symbol', 'facet', 'pareto']) { const s = el.querySelector(`[data-c=${k}]`); if (s) s.value = st[k]; }
      for (const k of ['logx', 'logy']) { const s = el.querySelector(`[data-c=${k}]`); if (s) s.checked = st[k]; }
      pr.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === c));
      const dsc = el.querySelector('.ex-desc'); if (dsc) dsc.innerHTML = p.desc ? md(p.desc) : '';
      draw();
    };
    if (b.preset_default != null && pr) { const c0 = pr.querySelector(`[data-p="${+b.preset_default}"]`); if (c0) { c0.click(); return; } }
    await draw();
  };

  async function renderOne(el, b, ctx) {
    const fn = R[b.type];
    if (!fn) { el.innerHTML = `<div class="note warn">Unknown block type “${esc(b.type)}”.</div>`; return; }
    await fn(el, b, ctx);
  }

  global.Blocks = { render, md, inline, fmt, num, esc, visibleBlocks, pickStage, TYPES: Object.keys(R).filter((k) => !k.startsWith('_')) };
})(window);
