/*! gdsview.js — standalone in-browser GDSII viewer (no dependencies).
 *
 *   GDSView.mount(containerElement, "path/to/cell.gds.gz", { tech: "gf180mcuD" })
 *
 * Fetches a .gds or .gds.gz (gunzipped with the browser's DecompressionStream), parses the
 * GDSII stream, flattens the hierarchy of the chosen cell and renders it on a canvas with
 * pan (drag), zoom (wheel / pinch / buttons), cell picker, layer toggles and pin labels.
 * Copy this single file into any report that needs to show layouts.
 */
(function (global) {
  'use strict';

  /* ---------------------------------------------------------------- layer maps */
  // [layer, datatype, name, color, alpha, kind] kind: 'fill' | 'cut' | 'mark' (hidden by default) | 'text'
  const LAYERMAPS = {
    gf180mcuD: [
      [12, 0, 'DNWELL', '#334155', 0.25, 'mark'],
      [21, 0, 'NWELL', '#1e3a8a', 0.45, 'fill'],
      [22, 0, 'COMP', '#15803d', 0.75, 'fill'],
      [55, 0, 'DUALGATE', '#64748b', 0.18, 'mark'],
      [32, 0, 'NPLUS', '#854d0e', 0.38, 'fill'],
      [31, 0, 'PPLUS', '#701a75', 0.38, 'fill'],
      [49, 0, 'SAB', '#94a3b8', 0.25, 'mark'],
      [30, 0, 'POLY2', '#dc2626', 0.85, 'fill'],
      [62, 0, 'RES_MK', '#a3e635', 0.3, 'mark'],
      [33, 0, 'CONT', '#f8fafc', 1, 'cut'],
      [34, 0, 'MET1', '#0284c7', 0.72, 'fill'],
      [35, 0, 'VIA1', '#e2e8f0', 1, 'cut'],
      [36, 0, 'MET2', '#ec4899', 0.7, 'fill'],
      [38, 0, 'VIA2', '#fde047', 1, 'cut'],
      [42, 0, 'MET3', '#10b981', 0.68, 'fill'],
      [40, 0, 'VIA3', '#c084fc', 1, 'cut'],
      [46, 0, 'MET4', '#f59e0b', 0.62, 'fill'],
      [41, 0, 'VIA4', '#fb7185', 1, 'cut'],
      [81, 0, 'MET5', '#a78bfa', 0.55, 'fill'],
      [82, 0, 'VIA5', '#fda4af', 1, 'cut'],
      [53, 0, 'METTOP', '#22d3ee', 0.5, 'fill'],
      [75, 0, 'MIM_TOP', '#facc15', 0.45, 'fill'],
      [117, 5, 'CAP_MK', '#fef08a', 0.15, 'mark'],
      [117, 10, 'MIM_L_MK', '#fef08a', 0.15, 'mark'],
      [204, 0, 'PR_BNDRY', '#94a3b8', 0.08, 'mark'],
      [0, 0, 'BOUNDARY', '#94a3b8', 0.08, 'mark'],
    ],
  };
  const TEXT_LAYER_HINT = new Set([10]); // datatype 10 = label layers in GF180 (e.g. 34/10 MET1 label)

  /* ---------------------------------------------------------------- parsing */
  function real8(dv, o) {
    const b0 = dv.getUint8(o);
    const sign = b0 & 0x80 ? -1 : 1;
    const exp = (b0 & 0x7f) - 64;
    let mant = 0;
    for (let i = 1; i < 8; i++) mant = mant * 256 + dv.getUint8(o + i);
    return sign * (mant / 2 ** 56) * 16 ** exp;
  }
  function str(u8, o, n) {
    let s = '';
    for (let i = 0; i < n; i++) { const c = u8[o + i]; if (c) s += String.fromCharCode(c); }
    return s;
  }
  function parse(buf) {
    const dv = new DataView(buf), u8 = new Uint8Array(buf);
    const cells = new Map();
    let cell = null, el = null, units = [1e-3, 1e-9];
    let i = 0;
    while (i + 4 <= u8.length) {
      const n = dv.getUint16(i), rt = u8[i + 2];
      if (n < 4) break;
      const o = i + 4, len = n - 4;
      switch (rt) {
        case 0x03: units = [real8(dv, o), real8(dv, o + 8)]; break; // UNITS
        case 0x06: cell = { name: str(u8, o, len), polys: [], paths: [], texts: [], refs: [] }; cells.set(cell.name, cell); break;
        case 0x07: cell = null; break;
        case 0x08: case 0x2d: el = { t: 'b', l: 0, d: 0 }; break; // BOUNDARY / BOX
        case 0x09: el = { t: 'p', l: 0, d: 0, w: 0, pt: 0 }; break; // PATH
        case 0x0a: el = { t: 's', mag: 1, ang: 0, refl: false }; break; // SREF
        case 0x0b: el = { t: 'a', mag: 1, ang: 0, refl: false }; break; // AREF
        case 0x0c: el = { t: 't', l: 0, d: 0, s: '' }; break; // TEXT
        case 0x0d: if (el) el.l = dv.getInt16(o); break;
        case 0x0e: case 0x16: case 0x2e: if (el) el.d = dv.getInt16(o); break; // DATATYPE/TEXTTYPE/BOXTYPE
        case 0x0f: if (el) el.w = Math.abs(dv.getInt32(o)); break;
        case 0x21: if (el) el.pt = dv.getInt16(o); break;
        case 0x12: if (el) el.sname = str(u8, o, len); break;
        case 0x13: if (el) { el.cols = dv.getInt16(o); el.rows = dv.getInt16(o + 2); } break;
        case 0x19: if (el) el.s = str(u8, o, len); break;
        case 0x1a: if (el) el.refl = !!(dv.getUint16(o) & 0x8000); break;
        case 0x1b: if (el) el.mag = real8(dv, o); break;
        case 0x1c: if (el) el.ang = real8(dv, o); break;
        case 0x10: if (el) { const k = len >> 2, xy = new Float64Array(k); for (let j = 0; j < k; j++) xy[j] = dv.getInt32(o + 4 * j); el.xy = xy; } break;
        case 0x11: // ENDEL
          if (el && cell && el.xy) {
            if (el.t === 'b') cell.polys.push(el);
            else if (el.t === 'p') cell.paths.push(el);
            else if (el.t === 't') cell.texts.push(el);
            else cell.refs.push(el);
          }
          el = null; break;
        default: break;
      }
      i += n;
    }
    // top cells = never referenced
    const refd = new Set();
    for (const c of cells.values()) for (const r of c.refs) refd.add(r.sname);
    const tops = [...cells.keys()].filter((k) => !refd.has(k));
    return { cells, tops, dbu_m: units[1] };
  }

  /* ---------------------------------------------------------------- flattening */
  // affine [a, b, c, d, e, f]: x' = a x + c y + e ; y' = b x + d y + f
  const mul = (m, n) => [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
  function refMatrix(r, x, y) {
    const a = (r.ang * Math.PI) / 180, c = Math.cos(a) * r.mag, s = Math.sin(a) * r.mag;
    const ry = r.refl ? -1 : 1;
    return [c, s, -s * ry, c * ry, x, y];
  }
  function flatten(lib, top, limit = 4e6) {
    const layers = new Map(); // key "l/d" -> { polys: [Float32Array], boxes: Float32Array per poly (minx,miny,maxx,maxy), paths: [] }
    const texts = [];
    let pts = 0, truncated = false;
    const bb = [Infinity, Infinity, -Infinity, -Infinity];
    const L = (l, d) => { const k = `${l}/${d}`; let e = layers.get(k); if (!e) { e = { l, d, polys: [], boxes: [], paths: [] }; layers.set(k, e); } return e; };
    const xfPts = (m, xy, n) => {
      const out = new Float32Array(n * 2);
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let j = 0; j < n; j++) {
        const x = xy[2 * j], y = xy[2 * j + 1];
        const X = m[0] * x + m[2] * y + m[4], Y = m[1] * x + m[3] * y + m[5];
        out[2 * j] = X; out[2 * j + 1] = Y;
        if (X < x0) x0 = X; if (X > x1) x1 = X; if (Y < y0) y0 = Y; if (Y > y1) y1 = Y;
      }
      if (x0 < bb[0]) bb[0] = x0; if (y0 < bb[1]) bb[1] = y0; if (x1 > bb[2]) bb[2] = x1; if (y1 > bb[3]) bb[3] = y1;
      return [out, x0, y0, x1, y1];
    };
    const walk = (name, m, depth) => {
      const c = lib.cells.get(name);
      if (!c || depth > 64 || truncated) return;
      const scale = Math.hypot(m[0], m[1]);
      for (const p of c.polys) {
        let n = p.xy.length >> 1;
        if (n > 1 && p.xy[0] === p.xy[2 * n - 2] && p.xy[1] === p.xy[2 * n - 1]) n--; // drop closing point
        const [out, ...box] = xfPts(m, p.xy, n);
        const e = L(p.l, p.d); e.polys.push(out); e.boxes.push(box);
        pts += n;
      }
      for (const p of c.paths) {
        const n = p.xy.length >> 1;
        const [out, ...box] = xfPts(m, p.xy, n);
        L(p.l, p.d).paths.push({ pts: out, w: p.w * scale, ext: p.pt === 2, box });
        pts += n;
      }
      for (const t of c.texts) {
        const X = m[0] * t.xy[0] + m[2] * t.xy[1] + m[4], Y = m[1] * t.xy[0] + m[3] * t.xy[1] + m[5];
        texts.push({ x: X, y: Y, s: t.s, l: t.l, d: t.d, depth });
      }
      if (pts > limit) { truncated = true; return; }
      for (const r of c.refs) {
        if (r.t === 's') walk(r.sname, mul(m, refMatrix(r, r.xy[0], r.xy[1])), depth + 1);
        else {
          const cols = r.cols || 1, rows = r.rows || 1;
          const [x0, y0, xc, yc, xr, yr] = r.xy;
          const dcx = (xc - x0) / cols, dcy = (yc - y0) / cols, drx = (xr - x0) / rows, dry = (yr - y0) / rows;
          for (let ci = 0; ci < cols; ci++) for (let ri = 0; ri < rows; ri++) {
            walk(r.sname, mul(m, refMatrix(r, x0 + ci * dcx + ri * drx, y0 + ci * dcy + ri * dry)), depth + 1);
          }
        }
      }
    };
    walk(top, [1, 0, 0, 1, 0, 0], 0);
    return { layers, texts, bbox: bb, pts, truncated };
  }

  /* ---------------------------------------------------------------- colors */
  function layerStyle(tech, l, d) {
    const map = LAYERMAPS[tech] || LAYERMAPS.gf180mcuD;
    const hit = map.find((x) => x[0] === l && x[1] === d);
    if (hit) return { name: hit[2], color: hit[3], alpha: hit[4], kind: hit[5], order: map.indexOf(hit) };
    const h = (l * 47 + d * 101) % 360;
    return { name: `L${l}`, color: `hsl(${h} 70% 60%)`, alpha: 0.35, kind: TEXT_LAYER_HINT.has(d) ? 'mark' : 'fill', order: 500 + l };
  }

  /* ---------------------------------------------------------------- viewer */
  const CSS = `
  .gdsv{position:relative;width:100%;height:100%;background:#0b1020;color:#cbd5e1;font:12px system-ui,sans-serif;overflow:hidden;user-select:none;touch-action:none}
  .gdsv canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab}
  .gdsv canvas.drag{cursor:grabbing}
  .gdsv .bar{position:absolute;left:8px;top:8px;right:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;pointer-events:none}
  .gdsv .bar>*{pointer-events:auto}
  .gdsv button,.gdsv select,.gdsv summary{background:#162032e6;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:3px 8px;font:inherit;cursor:pointer}
  .gdsv select{max-width:240px}
  .gdsv details{position:relative}
  .gdsv summary{list-style:none}
  .gdsv summary::-webkit-details-marker{display:none}
  .gdsv .layers{position:absolute;top:28px;left:0;background:#0f172af2;border:1px solid #334155;border-radius:8px;padding:6px 8px;max-height:320px;overflow:auto;min-width:190px;z-index:2}
  .gdsv .layers label{display:flex;gap:6px;align-items:center;padding:1px 0;white-space:nowrap;cursor:pointer}
  .gdsv .sw{width:12px;height:12px;border-radius:2px;border:1px solid #475569;flex:none}
  .gdsv .info{position:absolute;left:8px;bottom:6px;font:11px ui-monospace,monospace;color:#94a3b8;pointer-events:none;text-shadow:0 0 3px #000}
  .gdsv .msg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#94a3b8;padding:20px;text-align:center}
  `;
  let cssDone = false;

  async function fetchGDS(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    let buf = await r.arrayBuffer();
    const u8 = new Uint8Array(buf, 0, 2);
    if (u8[0] === 0x1f && u8[1] === 0x8b) {
      if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot gunzip (no DecompressionStream)');
      buf = await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    }
    return buf;
  }

  function mount(container, url, opts = {}) {
    if (!cssDone) { const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st); cssDone = true; }
    const tech = opts.tech || 'gf180mcuD';
    container.innerHTML = '';
    const root = document.createElement('div');
    root.className = 'gdsv';
    root.innerHTML = `<canvas></canvas><div class="bar"></div><div class="info"></div><div class="msg">Loading layout…</div>`;
    container.appendChild(root);
    const canvas = root.querySelector('canvas'), bar = root.querySelector('.bar'), info = root.querySelector('.info'), msg = root.querySelector('.msg');
    const ctx = canvas.getContext('2d');
    let lib = null, flat = null, view = { s: 1, x: 0, y: 0 }, hidden = new Set(), layerList = [], dbu_um = 1e-3;
    let raf = 0, alive = true;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = root.clientWidth, h = root.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      return [w, h, dpr];
    };
    const fit = () => {
      if (!flat) return;
      const [w, h] = resize();
      const [x0, y0, x1, y1] = flat.bbox;
      const bw = Math.max(x1 - x0, 1), bh = Math.max(y1 - y0, 1);
      view.s = Math.min((w - 24) / bw, (h - 50) / bh);
      view.x = w / 2 - ((x0 + x1) / 2) * view.s;
      view.y = h / 2 + 14 + ((y0 + y1) / 2) * view.s; // y flipped
      draw();
    };
    const draw = () => { if (!raf) raf = requestAnimationFrame(paint); };
    function paint() {
      raf = 0;
      if (!flat || !alive) return;
      const [w, h, dpr] = resize();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#0b1020'; ctx.fillRect(0, 0, w, h);
      const s = view.s, ox = view.x, oy = view.y;
      // visible world box
      const wx0 = -ox / s, wx1 = (w - ox) / s, wy1 = oy / s, wy0 = (oy - h) / s;
      const minPx = 0.6 / s;
      for (const L of layerList) {
        if (hidden.has(L.key)) continue;
        const e = flat.layers.get(L.key);
        ctx.globalAlpha = L.alpha; ctx.fillStyle = L.color; ctx.strokeStyle = L.color;
        ctx.beginPath();
        for (let i = 0; i < e.polys.length; i++) {
          const b = e.boxes[i];
          if (b[2] < wx0 || b[0] > wx1 || b[3] < wy0 || b[1] > wy1) continue;
          if (b[2] - b[0] < minPx && b[3] - b[1] < minPx) continue;
          const p = e.polys[i];
          ctx.moveTo(ox + p[0] * s, oy - p[1] * s);
          for (let j = 2; j < p.length; j += 2) ctx.lineTo(ox + p[j] * s, oy - p[j + 1] * s);
          ctx.closePath();
        }
        ctx.fill();
        if (L.kind === 'mark') { ctx.globalAlpha = Math.min(1, L.alpha * 4); ctx.lineWidth = 1; ctx.stroke(); }
        for (const p of e.paths) {
          const b = p.box;
          if (b[2] + p.w < wx0 || b[0] - p.w > wx1 || b[3] + p.w < wy0 || b[1] - p.w > wy1) continue;
          ctx.globalAlpha = L.alpha; ctx.lineWidth = Math.max(p.w * s, 0.5); ctx.lineCap = p.ext ? 'square' : 'butt'; ctx.lineJoin = 'miter';
          ctx.beginPath();
          ctx.moveTo(ox + p.pts[0] * s, oy - p.pts[1] * s);
          for (let j = 2; j < p.pts.length; j += 2) ctx.lineTo(ox + p.pts[j] * s, oy - p.pts[j + 1] * s);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
      if (!hidden.has('__text')) {
        ctx.font = '600 11px system-ui,sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const shown = new Set();
        const maxDepth = flat.texts.length > 400 ? 0 : 99;
        for (const t of flat.texts) {
          if (t.depth > maxDepth || hidden.has(`${t.l}/${t.d}`)) continue;
          const X = ox + t.x * s, Y = oy - t.y * s;
          if (X < 0 || X > w || Y < 0 || Y > h) continue;
          const k = `${t.s}@${Math.round(X / 30)},${Math.round(Y / 14)}`;
          if (shown.has(k)) continue; shown.add(k);
          ctx.lineWidth = 3; ctx.strokeStyle = '#0b1020'; ctx.strokeText(t.s, X, Y);
          ctx.fillStyle = '#f8fafc'; ctx.fillText(t.s, X, Y);
        }
      }
      // scale bar
      const um = dbu_um / s; // µm per screen px
      const target = 100 * um, pow = 10 ** Math.floor(Math.log10(target));
      const nice = [1, 2, 5, 10].map((k) => k * pow).find((v) => v >= target * 0.6) || pow;
      const px = nice / um;
      ctx.fillStyle = '#e2e8f0'; ctx.fillRect(w - 20 - px, h - 14, px, 3);
      ctx.font = '11px ui-monospace,monospace'; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
      ctx.fillText(`${nice >= 1 ? nice : nice.toPrecision(1)} µm`, w - 20, h - 17);
    }

    const toWorld = (cx, cy) => [(cx - view.x) / view.s, (view.y - cy) / view.s];
    const zoomAt = (cx, cy, f) => {
      const [wx, wy] = toWorld(cx, cy);
      view.s *= f;
      view.x = cx - wx * view.s; view.y = cy + wy * view.s;
      draw();
    };
    // pointer interaction (pan + pinch)
    const ptrs = new Map(); let pinch = 0;
    canvas.addEventListener('pointerdown', (e) => { canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.offsetX, e.offsetY]); canvas.classList.add('drag'); });
    canvas.addEventListener('pointermove', (e) => {
      if (flat) { const [x, y] = toWorld(e.offsetX, e.offsetY); info.textContent = `x ${(x * dbu_um).toFixed(3)}  y ${(y * dbu_um).toFixed(3)} µm`; }
      const p = ptrs.get(e.pointerId); if (!p) return;
      if (ptrs.size === 1) { view.x += e.offsetX - p[0]; view.y += e.offsetY - p[1]; draw(); }
      ptrs.set(e.pointerId, [e.offsetX, e.offsetY]);
      if (ptrs.size === 2) {
        const [a, b] = [...ptrs.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (pinch) zoomAt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, d / pinch);
        pinch = d;
      }
    });
    const up = (e) => { ptrs.delete(e.pointerId); pinch = 0; if (!ptrs.size) canvas.classList.remove('drag'); };
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('wheel', (e) => { e.preventDefault(); zoomAt(e.offsetX, e.offsetY, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015))); }, { passive: false });
    canvas.addEventListener('dblclick', fit);
    const ro = new ResizeObserver(() => draw()); ro.observe(root);

    function load(top) {
      msg.style.display = 'flex'; msg.textContent = `Flattening ${top}…`;
      setTimeout(() => {
        flat = flatten(lib, top);
        layerList = [...flat.layers.values()].map((e) => ({ key: `${e.l}/${e.d}`, ...layerStyle(tech, e.l, e.d) }))
          .sort((a, b) => a.order - b.order);
        hidden = new Set(layerList.filter((L) => L.kind === 'mark').map((L) => L.key));
        buildBar(top);
        msg.style.display = flat.truncated ? 'flex' : 'none';
        if (flat.truncated) msg.textContent = 'Layout truncated (too many shapes) — pick a sub-cell';
        fit();
      }, 10);
    }
    function buildBar(top) {
      const cellOpts = [...lib.tops, ...[...lib.cells.keys()].filter((k) => !lib.tops.includes(k)).sort()];
      bar.innerHTML = `
        <select title="Cell">${cellOpts.map((k) => `<option ${k === top ? 'selected' : ''}>${k.replace(/</g, '&lt;')}</option>`).join('')}</select>
        <button data-a="fit" title="Fit (double-click)">Fit</button><button data-a="in">+</button><button data-a="out">−</button>
        <details><summary>Layers ▾</summary><div class="layers">
          ${layerList.map((L) => `<label><input type="checkbox" data-k="${L.key}" ${hidden.has(L.key) ? '' : 'checked'}><span class="sw" style="background:${L.color};opacity:${Math.max(L.alpha, 0.5)}"></span>${L.name} <span style="opacity:.6">${L.key}</span></label>`).join('')}
          <label><input type="checkbox" data-k="__text" ${hidden.has('__text') ? '' : 'checked'}><span class="sw" style="background:#f8fafc"></span>Labels</label>
        </div></details>`;
      bar.querySelector('select').onchange = (e) => load(e.target.value);
      bar.onclick = (e) => {
        const a = e.target.dataset?.a; if (!a) return;
        const [w, h] = resize();
        if (a === 'fit') fit(); else zoomAt(w / 2, h / 2, a === 'in' ? 1.5 : 1 / 1.5);
      };
      bar.querySelector('.layers').onchange = (e) => { const k = e.target.dataset.k; if (e.target.checked) hidden.delete(k); else hidden.add(k); draw(); };
    }

    fetchGDS(url).then((buf) => {
      if (!alive) return;
      lib = parse(buf);
      dbu_um = lib.dbu_m * 1e6;
      if (!lib.cells.size) throw new Error('no cells found in GDS');
      const top = opts.cell && lib.cells.has(opts.cell) ? opts.cell
        : lib.tops.slice().sort((a, b) => (lib.cells.get(b).refs.length + lib.cells.get(b).polys.length) - (lib.cells.get(a).refs.length + lib.cells.get(a).polys.length))[0];
      load(top);
    }).catch((e) => { msg.style.display = 'flex'; msg.textContent = `Could not render layout: ${e.message}`; });

    return { destroy() { alive = false; ro.disconnect(); container.innerHTML = ''; }, fit };
  }

  global.GDSView = { mount, parse, flatten, LAYERMAPS };
})(typeof window !== 'undefined' ? window : globalThis);
