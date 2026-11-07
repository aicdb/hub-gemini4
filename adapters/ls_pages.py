"""Report pages of the ls (level-shifter) hub adapter: one page per section of the old report.

Every JavaScript computation of the old index.html (KPIs, HV summary, unit-inverter node-scaling
model, appendix trajectories, DSE Pareto overlays …) is ported to Python here.  Pre-PEX and
post-PEX variants are emitted as stage alternatives so that the hub's global "Simulation stage"
option replaces the old Pre-PEX / Post-PEX toggle.
"""
from __future__ import annotations

import math
import re

from ls_lib import FJ, MHZ, NW, PS, fx, mul, to_md, tofixed

STAGES = (("pre", "Pre-PEX"), ("full", "Post-PEX"))
STAGE_TAG = {"pre": "Pre-PEX", "full": "Post-PEX"}


def fv(v):
    return f"{v:g}"


def karea(pm):
    """gLayout bbox area as printed by the old site (2 decimals; the hub's number formatter rounds values >= 1e4 to integers)."""
    return fx(pm["layout_area_um2"], 2) if (pm or {}).get("layout_area_um2") is not None else None


def st_cell(ok, text=None):
    return {"v": text or ("PASS" if ok else "FAIL"), "s": "good" if ok else "bad"}


def alts(fn, alt, **extra):
    """Build one block per stage via fn(stage) -> block|None, tagging stage + alt."""
    out = []
    for st, _ in STAGES:
        b = fn(st)
        if b:
            b = dict(b, stage=st, alt=alt, **extra)
            out.append(b)
    return out


def table_src(c, rel, title, columns, rows, **kw):
    b = {"type": "table", "src": c.o.put(rel, {"columns": columns, "rows": rows})}
    if title:
        b["title"] = title
    b.update(kw)
    return b


def short_tid(tid):
    return tid.split("_")[0]


# ===================================================================================== overview (sec 1 + header)
def kpis(c, st):
    S = c.S[st]
    topos = c.topos
    n_pex = sum(1 for t in topos if (t.get("pex_meta") or {}).get("has_pex"))
    safe = [r for r in S.get("hvt_grid") or [] if r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
    max_vh = max((r["vddh"] for r in safe), default=None)
    sp = [r for r in S.get("hvt_speed") or [] if r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
    best = sorted(sp, key=lambda r: (-r["freq_mhz"], r.get("tpd_ps") or 99999))[0] if sp else None
    sub = [r for r in S.get("pilot") or [] if r["domain_label"] == "subvt_0v6_to_3v3" and r["pass"] and r.get("tpd_ps") is not None]
    bsub = min(sub, key=lambda r: r["tpd_ps"]) if sub else None
    score = max(sum(1 for p in S["pilot"] if p["topology"] == t["id"] and p["pass"]) for t in topos) if S.get("pilot") else None
    top_vh = sorted([r for r in safe if r["vddh"] == max_vh], key=lambda r: r["topology"])[0]["topology"] if safe else None
    full6 = [short_tid(t["id"]) for t in topos if score and sum(1 for p in S["pilot"] if p["topology"] == t["id"] and p["pass"]) == 6]
    nm = lambda tid: f"{short_tid(tid)}" if tid else "—"  # noqa: E731
    if st == "full":
        it = [(f"{S['total_sims']:,}" if S.get("total_sims") else "N/A", "Total Post-PEX Compute-Farm Sims"),
              (f"{n_pex} / 11 Extracted", "gLayout + Magic RC-Extracted Topologies"),
              (f"{fx(max_vh, 2)} V Max VDDH" if max_vh is not None else "N/A", "Post-PEX |VGS|,|VGD| < 1.8V Max VDDH"),
              (f"{best['freq_mhz']} MHz / {fx(best.get('tpd_ps'), 0)} ps" if best else "N/A", "Post-PEX Fastest HV <1.8V Oxide Safe"),
              (f"{score} / 6 Domains" if score is not None else "N/A", "Post-PEX Flagship Domain Pass Score"),
              (f"{fx(bsub['tpd_ps'], 1)} ps" if bsub else "N/A", "Post-PEX Subthreshold 0.6V→3.3V Delay")]
    else:
        it = [(f"{S['total_sims']:,}", "Total Compute-Farm ngspice Sims"),
              ("11 Topologies", f"8 Multi-Domain + 3 HV ({n_pex} gLayout PEX)"),
              (f"{fx(max_vh, 2)} V Max VDDH" if max_vh is not None else "N/A", f"With |VGS|,|VGD| < 1.8V ({nm(top_vh)})"),
              (f"{best['freq_mhz']} MHz / {fx(best.get('tpd_ps'), 0)} ps" if best else "N/A",
               f"Fastest HV <1.8V Oxide Safe ({nm(best['topology'] if best else None)})"),
              (f"{score} / 6 Domains" if score is not None else "N/A", f"Passed by {' & '.join(full6) or '—'}"),
              (f"{fx(bsub['tpd_ps'], 1)} ps" if bsub else "N/A", f"Subthreshold 0.6V→3.3V Delay ({nm(bsub['topology'] if bsub else None)})")]
    return {"type": "stats", "title": "Key results", "items": [{"label": l, "value": v} for v, l in it],
            "caption": "Topology names in the labels are derived from the data (the old page hard-coded them; its "
                       "'Fastest HV' tile named TOP10 although the value belongs to TOP9)." if st == "pre" else None}


def p_overview(c):
    L = c.L
    hdr = c.dom.find("header")
    badges = " · ".join(to_md(x) for x in hdr.find("div", cls="badge-row").kids()) if hdr else ""
    subtitle = to_md(hdr.find("p", cls="subtitle")) if hdr else ""
    foot = c.dom.find("footer")
    blocks = [{"type": "markdown", "text": f"{badges}\n\n{subtitle}"},
              {"type": "note", "tone": "info", "text": "The old report's **Simulation Data View: Pre-PEX (Schematic) / Post-PEX (gLayout "
               "Extracted)** toggle is the hub's global **Simulation stage** option (Pre-PEX / Full post-PEX) in the bar above; with "
               "*fill from earlier stage* on, pre-PEX-only content is shown and marked as a fallback, with it off such content is "
               "reported as not available (the old [N/A])."}]
    blocks += alts(lambda st: kpis(c, st), "kpi")
    doms = [d for d, *_ in L.FLAG]
    dlab = {d: lab.split(" (")[0] for d, lab, _ in L.FLAG}

    def portfolio(st):
        pil = c.ix[st]["pilot"]
        rows = []
        for t in c.topos:
            a, pm = t.get("area") or {}, t.get("pex_meta") or {}
            cites = " · ".join(f"[{x['short']} ↗]({x['url']})" for x in t.get("citations") or [])
            row = {"topo": f"**{t['id']}**<br><small>{t['name']}</small>", "refs": f"<small>{cites}</small>" if cites else "",
                   "coupling": t.get("coupled_type"),
                   "sarea": {"v": a.get("total_area_um2"), "title": f"Transistors: {a.get('mos_area_um2')} µm² ({a.get('n_mos')} FETs) | "
                                                                    f"Resistors: {a.get('res_area_um2')} µm² | MIM Caps: {a.get('cap_area_um2')} µm²"},
                   "split": f"MOS {fx(a.get('mos_area_um2'))} + Pass {fx(a.get('passive_area_um2'))}",
                   "larea": {"v": karea(pm), "s": "good",
                             "title": f"gLayout BBox: {pm.get('width_um')} × {pm.get('height_um')} µm | Extracted Cp={pm.get('n_parasitic_caps')} "
                                      f"({pm.get('total_cap_ff')} fF), Rp={pm.get('n_parasitic_res')}"},
                   "ldim": f"{pm.get('width_um')}×{pm.get('height_um')}µm · Cpar={pm.get('total_cap_ff')}fF"}
            n = 0
            for d in doms:
                r = pil.get((t["id"], d))
                if not r:
                    row[d] = "—"
                    continue
                if r["pass"]:
                    n += 1
                    txt = f"**PASS**<br><small>{fx(r.get('tpd_ps'), 0)} ps · {fx(r.get('p_stat_nw'), 1)} nW</small>"
                else:
                    txt = f"**FAIL**<br><small>Swg {fx((r.get('swing_ratio') or 0) * 100, 0)}%</small>"
                row[d] = {"v": f"{t['id']}.{d}", "t": txt, "s": "good" if r["pass"] else "bad"}
            row["score"] = {"v": f"{n} / 6", "s": "good" if n == 6 else ("warn" if n < 4 else None)}
            rows.append(row)
        cols = [{"key": "topo", "label": "Topology", "md": True, "type": "text"}, {"key": "coupling", "label": "Coupling", "type": "text"},
                {"key": "sarea", "label": "Schematic area", "unit": "µm²", "digits": 4, "group": "Area"},
                {"key": "larea", "label": "gLayout & PEX area", "unit": "µm²", "type": "text", "group": "Area"}]
        cols += [{"key": d, "label": dlab[d], "type": "design", "md": True, "group": "Flagship domains (click a cell for the design page)"} for d in doms]
        cols += [{"key": "score", "label": "Pass score", "type": "text"},
                 {"key": "split", "label": "Schematic MOS + passive (µm²)", "type": "text"},
                 {"key": "ldim", "label": "gLayout BBox · Cpar", "type": "text"}, {"key": "refs", "label": "Literature", "md": True, "type": "text", "wrap": True}]
        return {"type": "table", "title": c.h3("1.1"), "columns": cols, "rows": rows, "search": False,
                "caption": "Cells: PASS · tpd · Pstat, or FAIL · output swing. Hover the area cells for the device / parasitic breakdown."}

    def pilot(st):
        rows = []
        for b in c.PRE["pilot"]:
            r = c.ix[st]["pilot"].get((b["topology"], b["domain_label"]))
            base = {"design": {"v": f"{b['topology']}.{b['domain_label']}", "t": b["topology"]},
                    "dom": f"{fx(b['vssl'], 1)}-{fx(b['vddl'], 2)}V → {fx(b['vssh'], 1)}-{fx(b['vddh'], 2)}V", "dl": b["domain_label"],
                    "vdd": b["vddh"]}
            if r:
                base.update(status=st_cell(r["pass"]), vol=r.get("vol"), voh=r.get("voh"), swing=mul(r.get("swing_ratio"), 100),
                            tplh=mul(r.get("tplh_ps"), PS), tphl=mul(r.get("tphl_ps"), PS), tpd=mul(r.get("tpd_ps"), PS),
                            trise=mul(r.get("trise_ps"), PS), tfall=mul(r.get("tfall_ps"), PS), pstat=mul(r.get("p_stat_nw"), NW),
                            edyn=mul(r.get("e_dyn_fj"), FJ), ptot=mul(r.get("p_tot_uw"), 1e-6))
            else:
                base["status"] = {"v": "N/A", "s": "muted"}
            rows.append(base)
        cols = [{"key": "design", "label": "Topology", "type": "design"}, {"key": "dom", "label": "Domain [VSSL,VDDL] → [VSSH,VDDH]", "type": "text"},
                {"key": "dl", "label": "Domain id", "type": "text"}, {"key": "vdd", "label": "VDDH", "unit": "V", "si": True},
                {"key": "status", "label": "Status", "type": "text"},
                {"key": "vol", "label": "VOL", "unit": "V", "si": True, "digits": 4}, {"key": "voh", "label": "VOH", "unit": "V", "si": True, "digits": 4},
                {"key": "swing", "label": "Swing", "unit": "%", "digits": 4},
                {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4}, {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4},
                {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4},
                {"key": "trise", "label": "t<sub>rise</sub>", "unit": "s", "si": True, "digits": 4},
                {"key": "tfall", "label": "t<sub>fall</sub>", "unit": "s", "si": True, "digits": 4},
                {"key": "pstat", "label": "P<sub>stat</sub>", "unit": "W", "si": True, "digits": 4},
                {"key": "edyn", "label": "E<sub>dyn</sub>", "unit": "J", "si": True, "digits": 4},
                {"key": "ptot", "label": "P<sub>tot</sub>", "unit": "W", "si": True, "digits": 4}]
        return {"type": "table", "title": c.h3("1.2"), "columns": cols, "rows": rows, "max_height": 720,
                "caption": "Use the filter box to select a domain (e.g. `subvt`) or a topology (e.g. `TOP8`) — it replaces the old "
                           "domain / topology dropdowns."}

    intro = c.sec_desc("sec-overview").replace(
        "When toggled to **Post-PEX**, any metric that has only Pre-PEX data is explicitly shown as [N/A].",
        "With the **Simulation** option at *Full post-PEX*, content that exists only pre-PEX is shown as a marked pre-PEX "
        "fallback (or reported as not available when *fill from earlier stage* is off).")
    blocks.append({"type": "section", "title": c.h2("sec-overview"), "intro": intro,
                   "blocks": alts(portfolio, "portfolio") + alts(pilot, "pilot")})
    if foot:
        ft = re.sub(r"\s*·\s*\[aicdb\.github\.io/[^\]]*\]\([^)]*\)", "", to_md(foot))
        blocks.append({"type": "note", "tone": "muted", "text": ft})
    return {"blocks": blocks}


# ===================================================================================== explore (sec 2)
EX_METRIC = {
    "p_sw_nw": ("switching power P<sub>sw</sub> (@ 10MHz)", "Switching Power Psw (nW @ 10MHz)", True),
    "fmax_mhz": ("maximum toggle speed F<sub>max</sub>", "Max Toggle Speed Fmax = 1/(2·tpd) (MHz)", True),
    "e_dyn_fj": ("dynamic switching energy E<sub>dyn</sub>", "Dynamic Energy per Transition Edyn (fJ)", True),
    "tpd_ps": ("mean propagation delay t<sub>pd</sub>", "Propagation Delay tpd (ps)", True),
    "area_um2": ("active silicon area (MOS + passives)", "Active Area (µm²)", True),
    "fom": ("Energy–Delay Figure of Merit FoM", "FoM = 1000 / (tpd[ns] · Edyn[fJ])", True),
    "p_stat_nw": ("static leakage power P<sub>stat</sub>", "Static Leakage Power Pstat (nW)", True),
    "tplh_ps": ("rising propagation delay t<sub>pLH</sub>", "Rising Delay tpLH (ps)", True),
    "tphl_ps": ("falling propagation delay t<sub>pHL</sub>", "Falling Delay tpHL (ps)", True),
    "s_drv": ("input / pull-down drive scale s<sub>drv</sub>", "Drive Sizing Multiplier s_drv (×)", False),
}
EX_PRESETS = [
    ("speed", "Speed vs power", "p_sw_nw", "fmax_mhz", "speed", "Maximise toggle speed Fmax = 1/(2·tpd), minimise switching power Psw."),
    ("energy", "Delay vs energy", "e_dyn_fj", "tpd_ps", "energy", "Minimise both propagation delay tpd and dynamic energy Edyn per transition."),
    ("area", "Area vs FoM", "area_um2", "fom", "area", "Maximise Energy–Delay Figure of Merit FoM = 1000/(tpd·Edyn), minimise active silicon area."),
    ("leakage", "Leakage vs delay", "p_stat_nw", "tpd_ps", "leakage", "Minimise both static leakage power Pstat and propagation delay tpd."),
    ("sym", "Rise vs fall", "tplh_ps", "tphl_ps", "sym", "Minimise both rising delay tpLH and falling delay tpHL (1:1 diagonal = symmetric edges)."),
    ("drv", "Drive vs FoM", "s_drv", "fom", None, "How input/pull-down drive strength s_drv shapes energy–delay efficiency."),
]
EX_ARCH_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#8c564b", "#8a8780", "#3b6ea5", "#b55d19", "#1a7f37", "#cf222e", "#8f7aa8"]
DSE_TO_DESIGN = {"1v2_to_3v3": "shared_1v2_to_3v3", "0v6_to_3v3": "subvt_0v6_to_3v3", "split_0_1v2_to_1v0_1v8": "split_0_1v2_to_1v0_1v8",
                 "disj_dn_1v8_3v3_to_0_1v0": "disjoint_dn_1v8_3v3_to_0_1v0", "hvt_1v2_to_4v5": "hv_1v2_to_4v5"}


def ex_hover(r):
    card = f" [{r['card_target']} TARGET CARD]" if r.get("card_target") else ""
    pvt = ((f"PVT-Robust (All Corners PASS · WC tpd={fx(r.get('wc_tpd_ps'))}ps)" if r.get("pvt_robust") else
            f"Fails an extreme PVT corner (WC tpd={fx(r.get('wc_tpd_ps'))}ps)") if r.get("pvt_checked") else "Nominal tt 27°C sample")
    return (f"<b>{r['topology']}{card}</b> ({r['domain']}) · {r.get('design_id')}<br>"
            f"tpd={fx(r.get('tpd_ps'))}ps (tpLH={fx(r.get('tplh_ps'))}ps, tpHL={fx(r.get('tphl_ps'))}ps) · Fmax={fx(r.get('fmax_mhz'))}MHz<br>"
            f"Edyn={fx(r.get('e_dyn_fj'), 2)}fJ · Psw={fx(r.get('p_sw_nw'))}nW · Pstat={fx(r.get('p_stat_nw'), 2)}nW · FoM={fx(r.get('fom'), 2)}<br>"
            f"Active Area={fx(r.get('area_um2'))}µm² (MOS={fx(r.get('mos_area_um2'))} + Passive={fx(r.get('passive_area_um2'))}µm²)<br>"
            f"Knobs: s_drv={r.get('s_drv')}× s_latch={r.get('s_latch')}× s_res={r.get('s_res')}× s_cap={r.get('s_cap')}× s_out={r.get('s_out')}×<br>{pvt}")


EX_HT = ("<b>%{customdata[16]}</b><br>tpd=%{customdata[0]:.1f}ps (tpLH=%{customdata[1]:.1f}ps, tpHL=%{customdata[2]:.1f}ps) · "
         "Fmax=%{customdata[3]:.1f}MHz<br>Edyn=%{customdata[4]:.2f}fJ · Psw=%{customdata[5]:.1f}nW · Pstat=%{customdata[6]:.2f}nW · "
         "FoM=%{customdata[7]:.2f}<br>Active Area=%{customdata[8]:.1f}µm² (MOS=%{customdata[9]:.1f} + Passive=%{customdata[10]:.1f}µm²)<br>"
         "Knobs: s_drv=%{customdata[11]}× s_latch=%{customdata[12]}× s_res=%{customdata[13]}× s_cap=%{customdata[14]}× "
         "s_out=%{customdata[15]}×<br>%{customdata[17]}<extra></extra>")


def ex_cd(r):
    """Compact per-point hover data (same content as the old exHoverText)."""
    card = f" [{r['card_target']} TARGET CARD]" if r.get("card_target") else ""
    pvt = ((f"PVT-Robust (All Corners PASS · WC tpd={fx(r.get('wc_tpd_ps'))}ps)" if r.get("pvt_robust") else
            f"Fails an extreme PVT corner (WC tpd={fx(r.get('wc_tpd_ps'))}ps)") if r.get("pvt_checked") else "Nominal tt 27°C sample")
    return [r.get(k) for k in ("tpd_ps", "tplh_ps", "tphl_ps", "fmax_mhz", "e_dyn_fj", "p_sw_nw", "p_stat_nw", "fom", "area_um2",
                                "mos_area_um2", "passive_area_um2", "s_drv", "s_latch", "s_res", "s_cap", "s_out")] + \
        [f"{r['topology']}{card} ({r['domain']}) · {r.get('design_id')}", pvt]


def ex_range(vals, log, pad=0.05):
    v = [x for x in vals if x is not None and math.isfinite(x) and (not log or x > 0)]
    if not v:
        return [0, 3] if log else [0, 10]
    lo, hi = min(v), max(v)
    if log:
        lo, hi = math.log10(lo), math.log10(hi)
    span = (hi - lo) or (1.0 if log else abs(hi) or 1.0)
    return [lo - pad * span, hi + pad * span]


def ex_overlay(c, dom, preset):
    D = c.PRE["dse"]
    key, label, xk, yk, front, cap = preset
    X, Y = EX_METRIC[xk], EX_METRIC[yk]
    feas = [r for r in D["records"] if r["domain"] == dom and r["pass"]]
    archs = D.get("archs") or [t["id"] for t in c.topos]
    ok = lambda r: r.get(xk) is not None and r.get(yk) is not None and r[xk] > 0 and r[yk] > 0  # noqa: E731
    cloud = [r for r in feas if ok(r)]
    tr = [{"type": "scatter", "mode": "markers", "name": "feasible sizing sample", "x": [r[xk] for r in cloud], "y": [r[yk] for r in cloud],
           "customdata": [ex_cd(r) for r in cloud], "marker": {"color": "theme:muted", "opacity": 0.4, "size": 4},
           "hovertemplate": EX_HT}]
    for k, topo in enumerate(archs):
        col = EX_ARCH_COLORS[k % len(EX_ARCH_COLORS)]
        if front:
            fr = [D["records"][i] for i in (D.get("fronts") or {}).get(f"{front}|{dom}|{topo}", []) if i < len(D["records"])]
        else:
            bins = {}
            for r in feas:
                if r["topology"] == topo and r.get(xk) is not None and r.get(yk) is not None:
                    b = round(r[xk] * 4) / 4
                    if b not in bins or r[yk] > bins[b][yk]:
                        bins[b] = r
            fr = list(bins.values())
        fr = [r for r in fr if ok(r)]
        fr.sort(key=lambda r: r[xk])
        nfeas = sum(1 for r in feas if r["topology"] == topo)
        tr.append({"type": "scatter", "mode": "lines+markers", "name": f"{topo.replace('_', ' ', 1)[:22]} ({nfeas})",
                   "x": [r[xk] for r in fr] or [None], "y": [r[yk] for r in fr] or [None], "legendgroup": topo,
                   "line": {"color": col, "width": 2, "dash": "dash" if k >= 6 else "solid", "shape": "hv" if front else "linear"},
                   "marker": {"size": 8, "color": [col if r.get("pvt_robust") is not False else "#ffffff" for r in fr],
                              "line": {"color": col, "width": 1.8}},
                   "text": [ex_hover(r) for r in fr], "hovertemplate": "%{text}<extra></extra>"})
    cards = [r for r in feas if r.get("card_target") and ok(r)]
    tr.append({"type": "scatter", "mode": "markers", "name": "delivered sizing card (ULP / BAL / HS)", "x": [r[xk] for r in cards],
               "y": [r[yk] for r in cards], "marker": {"symbol": "diamond", "size": 10, "color": "theme:ink", "line": {"color": "theme:paper", "width": 1.3}},
               "text": [ex_hover(r) for r in cards], "hovertemplate": "%{text}<extra></extra>"})
    xr, yr = ex_range([r[xk] for r in feas if r.get(xk) is not None], X[2]), ex_range([r[yk] for r in feas if r.get(yk) is not None], Y[2])
    lay = {"xaxis": {"type": "log" if X[2] else "linear", "range": xr, "title": {"text": X[1]}},
           "yaxis": {"type": "log" if Y[2] else "linear", "range": yr, "title": {"text": Y[1]}},
           "legend": {"orientation": "v", "x": 1.02, "xanchor": "left", "y": 1, "yanchor": "top", "font": {"size": 10}},
           "margin": {"r": 230, "t": 20}}
    src = c.o.put(f"data/dse/overlay_{dom}__{key}.json", {"data": tr, "layout": lay}, 5)
    return {"type": "chart", "src": src, "height": 470, "title": f"2.1 Pareto Fronts by Architecture — {Y[0]} vs. {X[0]} (`{dom}`)",
            "caption": f"{cap} Step/lines join each architecture's non-dominated designs (filled marker = PVT-robust, open = fails a PVT "
                       f"corner). Diamonds (◆) mark the 3 delivered speed/sizing cards (ULP, BAL, HS). Grey: all feasible samples "
                       f"(swing ≥ 85 %); legend counts = feasible samples per architecture."}


PVT_COLORS = {"PVT-robust": "#2a78d6", "fails a PVT corner": "#eb6834", "not PVT-checked": "#a8a6a0"}


def dse_vdd(c, dom):
    d = c.doms.get(DSE_TO_DESIGN.get(dom, ""))
    return d["vddh"] if d else None


def bal_link(c, r, dom):
    """Hub design id for a BAL (1x baseline) card, or (None, reason) when the DSE run disagrees with the linked pilot."""
    if r.get("card_target") != "BAL":
        return None, None
    did = f"{r['topology']}.{DSE_TO_DESIGN.get(dom, '')}"
    if did not in c.design_ids:
        return None, None
    d = c.doms[DSE_TO_DESIGN[dom]]
    nom = c.ix["pre"]["pilot"].get((r["topology"], d["id"])) if not d["hv"] else \
        c.L.hv_nominal(c.PRE, r["topology"], c.ix["pre"]["hvt_pvt"].get((r["topology"], d["src"])) or {"vddl": -1, "vddh": -1})
    a, b = r.get("tpd_ps"), (nom or {}).get("tpd_ps")
    if a and b and abs(a - b) / b > 0.05:
        return None, f"{r['topology']} ({fx(a, 0)} ps vs pilot {fx(b, 0)} ps)"
    return did, None


def ex_explorer(c, dom):
    D = c.PRE["dse"]
    recs = [r for r in D["records"] if r["domain"] == dom and r["pass"]]
    archs = D.get("archs") or [t["id"] for t in c.topos]
    pvt = lambda r: "PVT-robust" if r.get("pvt_robust") is True else ("fails a PVT corner" if r.get("pvt_checked") else "not PVT-checked")  # noqa: E731
    links, skipped = [], []
    for r in recs:
        did, why = bal_link(c, r, dom)
        links.append(did)
        if why:
            skipped.append(why)
    vdd = dse_vdd(c, dom)
    col = {"topology": [r["topology"] for r in recs], "card": [r.get("card_target") or "sample" for r in recs], "pvt": [pvt(r) for r in recs],
           "tpd": [mul(r.get("tpd_ps"), PS) for r in recs], "tplh": [mul(r.get("tplh_ps"), PS) for r in recs],
           "tphl": [mul(r.get("tphl_ps"), PS) for r in recs], "fmax": [mul(r.get("fmax_mhz"), MHZ) for r in recs],
           "edyn": [mul(r.get("e_dyn_fj"), FJ) for r in recs], "psw": [mul(r.get("p_sw_nw"), NW) for r in recs],
           "pstat": [mul(r.get("p_stat_nw"), NW) for r in recs], "area": [r.get("area_um2") for r in recs],
           "mos_area": [r.get("mos_area_um2") for r in recs], "passive_area": [r.get("passive_area_um2") for r in recs],
           "fom": [r.get("fom") for r in recs], "swing": [r.get("swing_pct") for r in recs],
           "s_drv": [r.get("s_drv") for r in recs], "s_latch": [r.get("s_latch") for r in recs], "s_res": [r.get("s_res") for r in recs],
           "s_cap": [r.get("s_cap") for r in recs], "s_out": [r.get("s_out") for r in recs], "wc_tpd": [mul(r.get("wc_tpd_ps"), PS) for r in recs],
           "design_id": [r.get("design_id") for r in recs], "linked": [bool(x) for x in links],
           "design": links, "stage": ["pre"] * len(recs), "vdd": [vdd] * len(recs)}
    dims = [{"key": "psw", "label": "Switching power Psw (@10 MHz)", "unit": "W", "si": True, "log": True, "better": "low"},
            {"key": "fmax", "label": "Max toggle speed Fmax = 1/(2·tpd)", "unit": "Hz", "si": True, "log": True, "better": "high"},
            {"key": "edyn", "label": "Dynamic energy Edyn", "unit": "J", "si": True, "log": True, "better": "low"},
            {"key": "tpd", "label": "Propagation delay tpd", "unit": "s", "si": True, "log": True, "better": "low"},
            {"key": "tplh", "label": "Rising delay tpLH", "unit": "s", "si": True, "log": True, "better": "low"},
            {"key": "tphl", "label": "Falling delay tpHL", "unit": "s", "si": True, "log": True, "better": "low"},
            {"key": "pstat", "label": "Static leakage Pstat", "unit": "W", "si": True, "log": True, "better": "low"},
            {"key": "area", "label": "Active area (MOS + passives)", "unit": "µm²", "log": True, "better": "low"},
            {"key": "mos_area", "label": "MOS area", "unit": "µm²", "log": True, "better": "low"},
            {"key": "passive_area", "label": "Passive area", "unit": "µm²", "better": "low"},
            {"key": "fom", "label": "FoM = 1000/(tpd[ns]·Edyn[fJ])", "log": True, "better": "high"},
            {"key": "wc_tpd", "label": "Worst extreme-corner tpd (PVT-checked only)", "unit": "s", "si": True, "log": True, "better": "low"},
            {"key": "swing", "label": "Output swing", "unit": "%"},
            {"key": "s_drv", "label": "s_drv (input/pull-down drive ×)"}, {"key": "s_latch", "label": "s_latch (latch/keeper ×)"},
            {"key": "s_res", "label": "s_res (split-node/bias R ×)"}, {"key": "s_cap", "label": "s_cap (MIM coupling/bootstrap C ×)"},
            {"key": "s_out", "label": "s_out (output buffer ×)"},
            {"key": "topology", "label": "Architecture", "type": "cat", "order": archs,
             "colors": {a: EX_ARCH_COLORS[k % len(EX_ARCH_COLORS)] for k, a in enumerate(archs)}},
            {"key": "card", "label": "Sizing card", "type": "cat", "order": ["ULP", "BAL", "HS", "sample"],
             "symbols": {"ULP": "triangle-down", "BAL": "diamond", "HS": "triangle-up", "sample": "circle"}},
            {"key": "pvt", "label": "PVT status", "type": "cat", "order": list(PVT_COLORS), "colors": PVT_COLORS}]
    src = c.o.put(f"data/dse/explorer_{dom}.json", {"columns": col}, 5)
    xmap = {"p_sw_nw": "psw", "fmax_mhz": "fmax", "e_dyn_fj": "edyn", "tpd_ps": "tpd", "area_um2": "area", "fom": "fom",
            "p_stat_nw": "pstat", "tplh_ps": "tplh", "tphl_ps": "tphl", "s_drv": "s_drv"}
    zero = [a for a in archs if not any(r["topology"] == a for r in recs)]
    zero_txt = (f" No panel for {', '.join(f'`{a}`' for a in zero)}: 0 feasible designs on `{dom}`." if zero else "")
    presets = [{"label": p[1], "x": xmap[p[2]], "y": xmap[p[3]], "color": "topology", "symbol": "card", "facet": "",
                "pareto": "color" if p[4] else "",
                "desc": f"{p[5]} Colour = architecture" + ("; each architecture's Pareto front for these axes is drawn as a line in its colour."
                                                         if p[4] else " (no Pareto front for the drive sweep).")} for p in EX_PRESETS]
    presets += [{"label": f"{p[1]} · 11 facets", "x": xmap[p[2]], "y": xmap[p[3]], "facet": "topology", "color": "pvt", "symbol": "card",
                 "pareto": "all" if p[4] else "",
                 "desc": f"Old 2.2 small-multiple grid for *{p[1]}*: one panel per architecture, shared axis limits, colour = PVT status "
                         f"of the sample, line = the panel's Pareto front{'' if p[4] else ' (none for the drive sweep)'}." + zero_txt}
                for p in EX_PRESETS]
    skipped_txt = (" BAL cards whose DSE delay differs by more than 5 % from the linked pilot design are not linked: "
                   + "; ".join(skipped) + " — the TOP4 DSE run (like its PVT/MC runs) used an earlier netlist revision.") if skipped else ""
    return {"type": "explorer", "title": "2.2 Per-Architecture Design Clouds — interactive explorer", "src": src, "dims": dims,
            "x": "psw", "y": "fmax", "color": "topology", "symbol": "card", "filters": ["topology", "card", "pvt", "tpd", "area"],
            "highlight": "linked", "highlight_label": "BAL card with a hub design page (click)", "design_key": "design",
            "label_key": "design_id", "hover": ["topology", "card", "pvt", "tpd", "tplh", "tphl", "fmax", "edyn", "psw", "pstat", "fom",
                                                "area", "mos_area", "passive_area", "s_drv", "s_latch", "s_res", "s_cap", "s_out", "wc_tpd"],
            "presets": presets, "preset_default": 0, "height": 520, "fixed_axes": True, "pareto_include_highlight": True,
            "intro": "Every feasible sizing sample (swing ≥ 85 %) of this domain. Points are coloured by architecture (or by PVT status in "
                     "the *11 facets* presets: blue = PVT-robust across the extreme corners, orange = fails a corner, grey = not "
                     "PVT-checked); lines are the Pareto fronts for the current axes (per architecture, or per panel). Symbols mark the "
                     "delivered sizing cards (▼ ULP, ◆ BAL, ▲ HS; ● = other samples); a ring marks a BAL card whose hub design page "
                     "opens on click. Hover a point for its knobs and metrics.",
            "caption": "Old-report legend of this figure: *" + c.sec_desc_by_id("ex-facets-p").replace("*", "") + "* — the *11 facets* presets "
                       "reproduce that grid (one per trade-off) with the encoding described above. Only ringed BAL cards (1× baseline "
                       "sizing, i.e. the benchmarked cell) open a hub design page; ULP / HS cards are listed in 2.3 and on each design "
                       "page's *DSE sizing cards* tab. DSE values come from the separate DSE run; for TOP7 / TOP8 the linked pilot "
                       "reports Edyn = 0 fJ while the DSE run reports a finite Edyn." + skipped_txt}


def p_explore(c):
    D = c.PRE.get("dse") or {}
    if not D.get("records"):
        return {"blocks": [{"type": "note", "tone": "muted", "text": "Design-Space Exploration data not yet generated."}]}
    tabs = []
    for dm in D.get("domains") or []:
        dom = dm["id"]
        recs = [r for r in D["records"] if r["domain"] == dom]
        feas = [r for r in recs if r["pass"]]
        nd4 = (D.get("nd4") or {}).get(dom, [])
        spd = {i for k, v in (D.get("fronts") or {}).items() if k.startswith(f"speed|{dom}|") for i in v}
        nrob = sum(1 for i in spd if i < len(D["records"]) and D["records"][i].get("pvt_robust") is True)
        b = [{"type": "stats", "items": [
            {"value": f"{D['n_total'] + (D.get('n_pvt_sims') or 0):,}", "label": "total DSE + Pareto PVT sims (vlsipool)"},
            {"value": f"{len(feas):,} / {len(recs):,}", "label": f"feasible designs on {dom}"},
            {"value": f"{len(nd4):,}", "label": "4-objective non-dominated (tpd·Edyn·Pstat·Area)"},
            {"value": f"{nrob} / {len(spd)}", "label": "speed–power Pareto front points PVT-robust"}]}]
        b.append({"type": "tabs", "label": "Trade-off", "id": "dse_trade",
                  "tabs": [{"label": p[1], "key": p[0], "blocks": [ex_overlay(c, dom, p)]} for p in EX_PRESETS]})
        b.append(ex_explorer(c, dom))
        # 2.2 per-panel captions of the old small multiples: feasible samples · front points (robust) · cards pass
        frs = D.get("fronts") or {}
        crow = []
        for topo in D.get("archs") or []:
            mine = [r for r in feas if r["topology"] == topo]
            row = {"topo": topo, "feas": len(mine), "cards": f"{sum(1 for r in mine if r.get('card_target'))}/3"}
            for p in EX_PRESETS:
                xk, yk = p[2], p[3]
                npl = sum(1 for r in mine if r.get(xk) is not None and r.get(yk) is not None and r[xk] > 0 and r[yk] > 0)
                if not mine:
                    row[p[0]] = "0 feasible designs"
                    continue
                txt = f"{npl} feasible"
                if p[4]:
                    ids = [i for i in frs.get(f"{p[4]}|{dom}|{topo}", []) if i < len(D["records"])]
                    if ids:
                        txt += f" · {len(ids)} on front ({sum(1 for i in ids if D['records'][i].get('pvt_robust') is True)} PVT-robust)"
                row[p[0]] = txt
            crow.append(row)
        b.append({"type": "table", "title": "2.2 Per-architecture panel summary", "search": False, "csv": True, "rows": crow,
                  "columns": [{"key": "topo", "label": "Architecture", "type": "text"}, {"key": "feas", "label": "Feasible samples", "digits": 0}] +
                             [{"key": p[0], "label": p[1], "type": "text", "group": "Old panel caption per trade-off (samples plotted · front)",
                               "wrap": True} for p in EX_PRESETS] + [{"key": "cards", "label": "Cards pass", "type": "text"}],
                  "caption": "The captions of the old 11-panel grid (\"N feasible samples · M on front (K PVT-robust) · n/3 cards pass\") "
                             "for every trade-off; the plotted sample count can be lower than *Feasible samples* when a metric "
                             "of that trade-off is missing or ≤ 0 (log axes)."})
        # 2.3 cards
        rows = []
        for topo in D.get("archs") or []:
            for tgt in ("ULP", "BAL", "HS"):
                r = next((x for x in recs if x["topology"] == topo and x.get("card_target") == tgt), None)
                if not r:
                    continue
                badge = {"ULP": "**ULP**<br><small>Compact/Low-Energy</small>", "HS": "**HS**<br><small>High-Speed</small>",
                         "BAL": "**BAL**<br><small>Balanced Baseline</small>"}[tgt]
                pv = ({"v": "Nominal Fail", "s": "bad"} if not r["pass"] else
                      {"v": f"PVT Robust (WC {fx(r.get('wc_tpd_ps'), 0)}ps)", "s": "good"} if r.get("pvt_robust") is True else
                      {"v": "Nominal Only", "s": "bad"} if r.get("pvt_checked") else {"v": "Nominal Pass", "s": "muted"})
                link, _why = bal_link(c, r, dom)
                rows.append({"topo": {"v": link, "t": topo} if link else topo, "card": badge,
                             "knobs": f"<small>{r['s_drv']}× · {r['s_latch']}× · {r['s_res']}×<br>{r['s_cap']}× · {r['s_out']}×</small>",
                             "area": r.get("area_um2"), "status": st_cell(r["pass"], f"{'PASS' if r['pass'] else 'FAIL'} ({fx(r.get('swing_pct'), 0)}%)"),
                             "tpd": mul(r.get("tpd_ps"), PS) if r["pass"] else None, "fmax": mul(r.get("fmax_mhz"), MHZ) if r["pass"] else None,
                             "edyn": mul(r.get("e_dyn_fj"), FJ) if r["pass"] else None, "psw": mul(r.get("p_sw_nw"), NW) if r["pass"] else None,
                             "pstat": mul(r.get("p_stat_nw"), NW), "fom": r.get("fom") if r["pass"] else None, "pvt": pv})
        b.append(table_src(c, f"data/dse/cards_{dom}.json", c.h3("2.3"), [
            {"key": "topo", "label": "Topology", "type": "design"}, {"key": "card", "label": "Target Card", "type": "text", "md": True},
            {"key": "knobs", "label": "Sizing Multipliers<br><small>drv·latch·res · cap·out</small>", "type": "text", "md": True},
            {"key": "area", "label": "Active Area", "unit": "µm²", "digits": 4}, {"key": "status", "label": "Status", "type": "text"},
            {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4}, {"key": "fmax", "label": "Fmax", "unit": "Hz", "si": True, "digits": 4},
            {"key": "edyn", "label": "Edyn", "unit": "J", "si": True, "digits": 4}, {"key": "psw", "label": "Psw", "unit": "W", "si": True, "digits": 4},
            {"key": "pstat", "label": "Pstat", "unit": "W", "si": True, "digits": 3}, {"key": "fom", "label": "FoM", "digits": 3},
            {"key": "pvt", "label": "PVT Robustness", "type": "text"}], rows,
            caption=c.card_p("2.3") + " BAL rows link to the hub design of the benchmarked cell when the DSE delay agrees with "
                                       "its pilot within 5 % (TOP4 used an earlier netlist revision in the DSE run).", page_size=60))
        # 2.4 non-dominated
        nrows = []
        for i in nd4:
            r = D["records"][i]
            pv = ({"v": "not on 2D front", "s": "muted"} if not r.get("pvt_checked") else
                  {"v": f"Robust ({fx(r.get('wc_tpd_ps'), 0)}ps)", "s": "good"} if r.get("pvt_robust") else {"v": "Corner Fail", "s": "bad"})
            nrows.append({"topo": r["topology"] + (f" [{r['card_target']}]" if r.get("card_target") else ""), "tpd": mul(r.get("tpd_ps"), PS),
                          "fmax": mul(r.get("fmax_mhz"), MHZ), "edyn": mul(r.get("e_dyn_fj"), FJ), "psw": mul(r.get("p_sw_nw"), NW),
                          "pstat": mul(r.get("p_stat_nw"), NW), "fom": r.get("fom"), "area": r.get("area_um2"),
                          "knobs": f"{r['s_drv']}·{r['s_latch']}·{r['s_res']}·{r['s_cap']}·{r['s_out']}", "pvt": pv,
                          "wc": mul(r.get("wc_tpd_ps"), PS), "id": r.get("design_id")})
        b.append(table_src(c, f"data/dse/nd4_{dom}.json", c.h3("2.4"), [
            {"key": "topo", "label": "Architecture", "type": "text"}, {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4, "better": "low"},
            {"key": "fmax", "label": "Fmax", "unit": "Hz", "si": True, "digits": 4, "better": "high"},
            {"key": "edyn", "label": "Edyn", "unit": "J", "si": True, "digits": 4, "better": "low"},
            {"key": "psw", "label": "Psw", "unit": "W", "si": True, "digits": 4, "better": "low"},
            {"key": "pstat", "label": "Pstat", "unit": "W", "si": True, "digits": 3, "better": "low"},
            {"key": "fom", "label": "FoM", "digits": 3, "better": "high"}, {"key": "area", "label": "Area", "unit": "µm²", "digits": 4, "better": "low"},
            {"key": "knobs", "label": "Sizing (drv·latch·res·cap·out)", "type": "text"}, {"key": "pvt", "label": "PVT Status", "type": "text"},
            {"key": "wc", "label": "WC tpd", "unit": "s", "si": True, "digits": 4}, {"key": "id", "label": "Sample id", "type": "text"}], nrows,
            sort={"key": "fom", "dir": "desc"}, page_size=60,
            caption=c.card_p("2.4") + " Type `robust` in the filter box for the old *Only PVT-checked & robust* option."))
        tabs.append({"label": dm["label"], "key": dom, "vdd": dse_vdd(c, dom), "blocks": b})
    return {"blocks": [{"type": "section", "title": c.h2("sec-explore"), "intro": c.sec_desc("sec-explore"), "blocks": [
        {"type": "tabs", "stage": "pre", "alt": "dse", "title": "Domain", "id": "dse_dom", "tabs": tabs,
         "caption": "The design-space exploration was run on the schematic netlist only (Pre-PEX); at the post-PEX stage this "
                    "content is a pre-PEX fallback (the old report showed [N/A])."}]}]}


# ===================================================================================== topologies (sec 3)
def p_topologies(c):
    L = c.L
    rows = []
    for t in c.topos:
        a, pm = t.get("area") or {}, t.get("pex_meta") or {}
        rows.append({"topo": f"**{t['id']}**<br><small>{t['short_name']}</small>", "sarea": a.get("total_area_um2"),
                     "split": f"{fx(a.get('mos_area_um2'), 2)} + {fx(a.get('passive_area_um2'), 2)}",
                     "dim": f"{fx(pm.get('width_um'))} × {fx(pm.get('height_um'))} µm", "larea": karea(pm),
                     "ndev": pm.get("n_extracted_devs"), "ncap": pm.get("n_parasitic_caps"), "cpar": mul(pm.get("total_cap_ff"), 1e-15),
                     "nres": pm.get("n_parasitic_res"), "rpar": pm.get("total_res_ohm"),
                     "status": st_cell(bool(pm.get("has_pex")), "PEX EXTRACTED" if pm.get("has_pex") else "N/A")})
    blocks = [{"type": "table", "title": c.h3("3.1"), "search": False, "rows": rows, "columns": [
        {"key": "topo", "label": "Topology", "md": True, "type": "text"},
        {"key": "sarea", "label": "Schematic Area (MOS + Pass)", "unit": "µm²", "digits": 5}, {"key": "split", "label": "MOS + passive (µm²)", "type": "text"},
        {"key": "dim", "label": "gLayout Dimensions (W × H)", "type": "text"}, {"key": "larea", "label": "gLayout BBox Area", "unit": "µm²", "type": "text"},
        {"key": "ndev", "label": "Extracted Devices", "digits": 0}, {"key": "ncap", "label": "Parasitic Caps (Cp)", "digits": 0},
        {"key": "cpar", "label": "Total Cpar", "unit": "F", "si": True, "digits": 4}, {"key": "nres", "label": "Parasitic Res (Rp)", "digits": 0},
        {"key": "rpar", "label": "Total Rpar", "unit": "Ω", "digits": 5}, {"key": "status", "label": "Post-PEX Status", "type": "text"}],
        "caption": "DRC / LVS results are not published by the repo (null in report_data.json)."}]
    tabs = []
    for i, t in enumerate(c.topos):
        pm = t.get("pex_meta") or {}
        lay = pm.get("layout_png") or f"assets/layout_{t['id']}.png"
        tb = [{"type": "markdown", "title": f"3.2 {t['id']} — {t['name']}", "text": L.topo_md(t)},
              {"type": "section", "cols": 2, "blocks": [
                  {"type": "image", "title": "Circuit Schematic (SVG)", "src": f"assets/schem_{t['id']}.svg", "bg": "white", "max_height": 560},
                  {"type": "image", "title": "Parameterized gLayout Physical Layout & PEX Metrics", "src": lay, "bg": "white", "max_height": 520,
                   "caption": f"BBox {fx(pm.get('width_um'))} × {fx(pm.get('height_um'))} µm · gLayout area {fx(pm.get('layout_area_um2'), 2)} µm² · "
                              f"extracted devs {pm.get('n_extracted_devs')} · parasitic caps {pm.get('n_parasitic_caps')} "
                              f"({fx(pm.get('total_cap_ff'), 2)} fF) · parasitic res {pm.get('n_parasitic_res')}"}]}]
        tb += L.netlist_blocks(t, f"net-{t['id']}")
        tb.append({"type": "note", "tone": "muted", "text": c.card_p("3.3 ").replace(
            "Toggle Post-PEX mode to inspect the Magic RC-extracted `.pex.spice` subcircuit.",
            "Switch the **Simulation** option in the top bar to *Full post-PEX* to see the Magic RC-extracted `.pex.spice` subcircuit.")})
        links = [{"design": {"v": d["id"], "t": c.doms[d["axes"]["domain"]]["title"]}} for d in c.by_topo.get(t["id"], [])]
        tb.append({"type": "table", "title": "Design pages of this topology", "columns": [{"key": "design", "label": "Crossing", "type": "design"}],
                   "rows": links, "search": False, "csv": False})
        tabs.append({"label": f"{i + 1}. {t['short_name']}{' ★' if pm.get('has_pex') else ''}", "key": t["id"], "blocks": tb})
    blocks.append({"type": "tabs", "label": "Topology", "id": "topo", "tabs": tabs})
    gal = []
    for t in c.topos:
        pm = t.get("pex_meta") or {}
        gal.append({"type": "markdown", "title": f"{t['id']} — {t['name']}", "text": L.topo_md(t)})
        gal.append({"type": "gallery", "style": "grid", "cols": 2, "items": [
            {"label": "Schematic", "src": f"assets/schem_{t['id']}.svg"},
            {"label": "gLayout render", "src": pm.get("layout_png") or f"assets/layout_{t['id']}.png", "bg": "white"}]})
    blocks.append({"type": "section", "title": "View All 11 Topologies Gallery (Schematics + gLayout Physical Previews)",
                   "collapsed": True, "open": False, "blocks": gal})
    return {"blocks": [{"type": "section", "title": c.h2("sec-schematics"), "intro": c.sec_desc("sec-schematics"), "blocks": blocks}]}


# ===================================================================================== HV-tolerant (sec 4)
def hv_summary(c, st):
    S = c.S[st]
    rows = []
    for tid, stack, _ in c.HVT_TOPOS:
        t = c.T.get(tid, {})
        a, pm = t.get("area") or {}, t.get("pex_meta") or {}
        g = [r for r in S.get("hvt_grid") or [] if r["topology"] == tid]
        row = {"topo": tid.replace("_", "\\_"), "stack": stack,
               "sarea": f"{fx(a.get('total_area_um2'))} µm²<br><small>{fx(a.get('mos_area_um2'))} + {fx(a.get('passive_area_um2'))}</small>",
               "larea": f"{karea(pm)} µm²<br><small>Cpar={pm.get('total_cap_ff')}fF</small>"}
        if not g:
            rows.append(row)
            continue
        safe = [r for r in g if r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
        maxvh = bestmax = mint = None
        if safe:
            maxvh = max(r["vddh"] for r in safe)
            bestmax = sorted([r for r in safe if abs(r["vddh"] - maxvh) < 0.01], key=lambda r: r.get("tpd_ps") or 99999)[0]
            mint = sorted(safe, key=lambda r: r.get("tpd_ps") or 99999)[0]
        sp = [r for r in S.get("hvt_speed") or [] if r["topology"] == tid and r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
        if sp:
            b = sorted(sp, key=lambda r: (-r["freq_mhz"], -r["vddh"]))[0]
            fmax = f"{b['freq_mhz']} MHz @ {fx(b['vddh'], 1)}V ({fx(b.get('tpd_ps'), 0)} ps)"
        elif mint:
            fmax = f"@ {fx(mint['vddh'], 1)}V ({fx(mint.get('tpd_ps'), 0)} ps)"
        else:
            fmax = "10 MHz (Grid)" if st == "pre" else "N/A"
        row.update(safe=f"{len(safe)} / {len(g)}", maxvh=maxvh, vox=bestmax.get("max_vox_v") if bestmax else None,
                   mos=f"<small>{bestmax.get('worst_mos')}</small>" if bestmax else None,
                   tpd=f"{fx(mint.get('tpd_ps'), 1)} ps<br><small>({fx(mint['vddl'], 2)}→{fx(mint['vddh'], 2)}V)</small>" if mint else None,
                   fmax=fmax.replace(" (", "<br><small>(").replace("ps)", "ps)</small>") if "(" in fmax else fmax)
        rows.append(row)
    return {"type": "table", "title": c.h3("4.1"), "search": False, "rows": rows, "columns": [
        {"key": "topo", "label": "Topology", "type": "text", "md": True}, {"key": "stack", "label": "Stack Architecture", "type": "text", "wrap": True},
        {"key": "sarea", "label": "Schematic Area<br><small>MOS + passive</small>", "type": "text", "md": True},
        {"key": "larea", "label": "gLayout Area", "type": "text", "md": True},
        {"key": "safe", "label": "Safe Grid Points (<1.80V)", "type": "text"}, {"key": "maxvh", "label": "Max Safe VDDH", "unit": "V", "si": True, "digits": 3},
        {"key": "vox", "label": "Peak |Vox| @ Max VDDH", "unit": "V", "si": True, "digits": 4},
        {"key": "mos", "label": "Worst MOSFET @ Max VDDH", "type": "text", "md": True},
        {"key": "tpd", "label": "Fastest Safe tpd", "type": "text", "md": True},
        {"key": "fmax", "label": "Max Safe f_max", "type": "text", "md": True}]}


def hv_freq_chart(c, st):
    S = c.S[st]
    if not S.get("hvt_speed"):
        return None
    curves = [("TOP9_HVT_CASC_DCVS", 1.5, 2.5, "#2a78d6", "TOP9 (2-Stack DCVS @ 1.5→2.5V)"),
              ("TOP10_HVT_BOOTSTRAP_DYNAMIC", 1.2, 3.0, "#1baf7a", "TOP10 (2-Stack Cap-Boost @ 1.2→3.0V)"),
              ("TOP10_HVT_BOOTSTRAP_DYNAMIC", 1.5, 3.5, "#eb6834", "TOP10 (2-Stack Cap-Boost @ 1.5→3.5V)"),
              ("TOP11_HVT_TRIPLE_STACK", 1.5, 4.5, "#8f7aa8", "TOP11 (3-Stack Cascode @ 1.5→4.5V)"),
              ("TOP11_HVT_TRIPLE_STACK", 1.5, 4.8, "#9a6700", "TOP11 (3-Stack Cascode @ 1.5→4.8V)")]
    tr = []
    for tid, vl, vh, col, lab in curves:
        pts = []
        for f in (25, 50, 100, 200, 333, 500):
            r = next((x for x in S["hvt_speed"] if x["topology"] == tid and abs(x["vddl"] - vl) < 0.01 and abs(x["vddh"] - vh) < 0.01
                      and x["freq_mhz"] == f and x["logic_pass"]), None)
            if r and r.get("max_vox_v") is not None:
                pts.append(r)
        tr.append({"type": "scatter", "mode": "lines+markers", "name": lab, "x": [r["freq_mhz"] for r in pts], "y": [r["max_vox_v"] for r in pts],
                   "line": {"color": col, "width": 2},
                   "marker": {"size": [8 if r["oxide_safe_1v8"] else 10 for r in pts], "color": [col if r["oxide_safe_1v8"] else "theme:bad" for r in pts],
                              "line": {"color": "#ffffff", "width": 1}},
                   "text": [f"{lab} @ {r['freq_mhz']}MHz | max(|Vox|)={fx(r['max_vox_v'], 3)}V | tpd={fx(r.get('tpd_ps'))}ps | Safe={str(r['pass']).lower()}"
                            for r in pts], "hovertemplate": "%{text}<extra></extra>"})
    tr.append({"type": "scatter", "mode": "lines", "name": "1.80V Gate-Oxide Limit", "x": [25, 500], "y": [1.8, 1.8],
               "line": {"color": "theme:bad", "dash": "dash", "width": 1.6}, "hoverinfo": "skip"})
    return {"type": "chart", "title": c.h3("4.3"), "height": 380, "data": tr, "layout": {
        "xaxis": {"title": {"text": "Operating Frequency f (MHz) [Valid Rail-to-Rail Output Swing >= 85%]"}, "range": [15, 510],
                  "tickvals": [25, 100, 200, 333, 500]},
        "yaxis": {"title": {"text": "Peak Oxide Stress max(|VGS|,|VGD|) (V)"}, "range": [1.2, 1.95]}, "margin": {"t": 20}},
        "caption": "Red markers = point exceeds the 1.8 V oxide limit; only points with a valid output swing are plotted."}


def hv_pvt_table(c, st):
    rows = []
    for b in c.PRE.get("hvt_pvt_summary") or []:
        r = c.ix[st]["hvt_pvt"].get((b["topology"], b["domain_label"]))
        did = f"{b['topology']}.{c.L.hv_id(b['domain_label'])}"
        row = {"design": {"v": did, "t": b["topology"]}, "dom": f"0-{fx(b['vddl'], 2)}V → 0-{fx(b['vddh'], 2)}V<br><small>({b['domain_label']})</small>",
               "vdd": b["vddh"]}
        if r:
            row.update(lp=f"{r['n_logic_pass']} / {r['n_total']}", ox=f"{r['n_oxide_safe']} / {r['n_total']}",
                       y={"v": f"{r['n_pass']}/{r['n_total']} ({fv(r['yield_pct'])}%)", "s": "good" if r["n_pass"] >= 12 else "bad"},
                       ntpd=mul(r.get("nom_tpd_ps"), PS), nvox=f"{fx(r.get('nom_vox_v'), 3)} V<br><small>{r.get('nom_worst_mos') or ''}</small>",
                       wcd=r.get("wc_dly_corner"), wtpd=mul(r.get("wc_tpd_ps"), PS), wco=r.get("wc_vox_corner"),
                       wvox=f"{fx(r.get('wc_vox_v'), 3)} V<br><small>({(r.get('wc_worst_mos') or '').split(':')[0]})</small>")
        else:
            row["y"] = {"v": "N/A", "s": "muted"}
        rows.append(row)
    return {"type": "table", "title": c.h3("4.5"), "search": False, "rows": rows, "columns": [
        {"key": "design", "label": "Topology", "type": "design"}, {"key": "dom", "label": "Domain (VDDL → VDDH)", "type": "text", "md": True},
        {"key": "vdd", "label": "VDDH", "unit": "V", "si": True},
        {"key": "lp", "label": "15-Corner Logic Pass", "type": "text"}, {"key": "ox", "label": "15-Corner Oxide Safe (<1.80V)", "type": "text"},
        {"key": "y", "label": "Combined Yield", "type": "text"}, {"key": "ntpd", "label": "Nom tpd", "unit": "s", "si": True, "digits": 5},
        {"key": "nvox", "label": "Nom Peak |Vox|<br><small>worst MOSFET</small>", "type": "text", "md": True},
        {"key": "wcd", "label": "Worst-Case Delay Corner", "type": "text"}, {"key": "wtpd", "label": "WC tpd", "unit": "s", "si": True, "digits": 5},
        {"key": "wco", "label": "Worst-Case Oxide Corner", "type": "text"}, {"key": "wvox", "label": "WC Peak |Vox|", "type": "text", "md": True}]}


HV_ROW_COLS = [{"key": "topo", "label": "Topology", "type": "text"}, {"key": "vddl", "label": "VDDL", "unit": "V", "si": True},
               {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}, {"key": "f", "label": "f", "unit": "Hz", "si": True},
               {"key": "safe", "label": "Pass (logic & oxide)", "type": "status"}, {"key": "lp", "label": "Logic pass", "type": "status"},
               {"key": "ox", "label": "Oxide safe", "type": "status"}, {"key": "vgs", "label": "max |VGS|", "unit": "V", "si": True, "digits": 4},
               {"key": "vgd", "label": "max |VGD|", "unit": "V", "si": True, "digits": 4}, {"key": "vox", "label": "max |Vox|", "unit": "V", "si": True, "digits": 4},
               {"key": "mos", "label": "Worst MOSFET", "type": "text"}, {"key": "swing", "label": "Swing", "unit": "%", "digits": 4},
               {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4}, {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4},
               {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4}, {"key": "pstat", "label": "Pstat", "unit": "W", "si": True},
               {"key": "edyn", "label": "Edyn", "unit": "J", "si": True}]


def hv_row(r):
    return {"topo": r["topology"], "vddl": r["vddl"], "vdd": r["vddh"], "f": r["freq_mhz"] * 1e6, "safe": bool(r["pass"]),
            "lp": bool(r["logic_pass"]), "ox": bool(r["oxide_safe_1v8"]), "vgs": r.get("max_vgs_v"), "vgd": r.get("max_vgd_v"),
            "vox": r.get("max_vox_v"), "mos": r.get("worst_mos"), "swing": mul(r.get("swing_ratio"), 100), "tplh": mul(r.get("tplh_ps"), PS),
            "tphl": mul(r.get("tphl_ps"), PS), "tpd": mul(r.get("tpd_ps"), PS), "pstat": mul(r.get("p_stat_nw"), NW), "edyn": mul(r.get("e_dyn_fj"), FJ)}


def p_hvt(c):
    blocks = alts(lambda st: hv_summary(c, st), "hvsum")
    def arch_label(tid, stack, st):
        S = c.S[st]
        safe = [r for r in S.get("hvt_grid") or [] if r["topology"] == tid and r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
        sp = [r for r in S.get("hvt_speed") or [] if r["topology"] == tid and r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]
        vh = max((r["vddh"] for r in safe), default=None)
        f = max((r["freq_mhz"] for r in sp), default=None)
        return (f"{short_tid(tid)} — {stack} (safe up to {fx(vh, 2)}V{f', {f}MHz' if f else ''})" if vh else
                f"{short_tid(tid)} — {stack} (no oxide-safe point)")
    tabs = [{"label": arch_label(tid, stack, "pre"), "labels": {st: arch_label(tid, stack, st) for st, _ in STAGES}, "key": tid,
             "blocks": c.hvgrid_blocks(tid)} for tid, stack, _ in c.HVT_TOPOS]
    blocks.append({"type": "section", "title": c.h3("4.2"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Select LV-to-HV Architecture", "id": "hv_arch", "tabs": tabs, "default": 1,
         "caption": "Option labels give the highest oxide-safe VDDH of the grid and the highest oxide-safe frequency of the speed sweep "
                    "at the selected stage (the old labels were hard-coded and claimed e.g. 500 MHz for TOP10)."}]})
    wt = c.hvwave_tabs()
    blocks.append({"type": "section", "cols": 2, "blocks": [
        {"type": "section", "blocks": alts(lambda st: hv_freq_chart(c, st), "hvfreq")},
        {"type": "section", "title": c.h3("4.4"), "blocks": [wt] if wt else []}]})
    blocks += alts(lambda st: hv_pvt_table(c, st), "hvpvt")
    raw = []
    for k, lab in (("hvt_grid", "Complete HV grid sweep (VDDL × VDDH, 25 MHz)"), ("hvt_speed", "Complete HV frequency sweep (25 → 500 MHz)")):
        raw += alts(lambda st, k=k, lab=lab: table_src(c, f"data/hv/{st}_{k}.json", lab, HV_ROW_COLS,
                                                        [hv_row(r) for r in c.S[st].get(k) or []], vdd_filter=True) if c.S[st].get(k) else None, f"raw-{k}")
    blocks.append({"type": "section", "title": "Raw HV sweep records (all simulated points behind 4.1–4.3)", "collapsed": True, "blocks": raw})
    return {"blocks": [{"type": "section", "title": c.h2("sec-hvt"), "intro": c.sec_desc("sec-hvt"), "blocks": blocks}]}


# ===================================================================================== unit inverter + node scaling (sec 5, 13)
NODE_ORDER = ["180nm", "130nm", "65nm", "28nm", "22nm", "16nm", "7nm"]
_NK = ["name", "tech_class", "l_nm", "k_L", "vdd_core", "vdd_io", "vth0_v", "ss_mv_dec", "s_area_mos", "c_mim_ff_um2", "s_area_cap",
       "s_area_res", "s_c_mos", "s_c_cap", "s_t_fo4", "s_t_rc", "s_leak", "phi_cont_lowv", "ref_note"]
_NV = {
    "180nm": ["180nm Bulk CMOS (GF180MCU Native Baseline)", "Planar Bulk CMOS (SiO₂)", 180, 1.00, 1.80, 3.30, 0.68, 90, 1.000, 2.0, 1.000,
              1.000, 1.000, 1.000, 1.000, 1.000, 1.00, 1.00, "Measured GF180MCU PDK SPICE Baseline (1.000× Reference)"],
    "130nm": ["130nm Bulk CMOS", "Planar Bulk CMOS (Cu BEOL)", 130, 1.38, 1.20, 2.50, 0.45, 85, 0.520, 3.0, 0.670, 0.720, 0.680, 0.760,
              0.680, 0.740, 1.65, 0.82, "Stillmaker & Baas (2017) 130nm node; 3.0 fF/µm² MIM"],
    "65nm": ["65nm LP/GP Bulk CMOS", "Strained-Si Bulk Planar", 65, 2.77, 1.00, 1.80, 0.36, 80, 0.140, 4.5, 0.440, 0.480, 0.340, 0.480,
             0.350, 0.440, 3.40, 0.62, "Stillmaker & Baas (2017) 65nm node; 4.5 fF/µm² MIM/MOM"],
    "28nm": ["28nm HKMG Planar CMOS", "High-k Metal Gate (HKMG) Planar", 28, 6.43, 0.90, 1.80, 0.30, 75, 0.032, 7.0, 0.285, 0.310, 0.160,
             0.290, 0.180, 0.250, 4.80, 0.46, "IRDS / HKMG 28nm node; 7.0 fF/µm² multi-finger MOM"],
    "22nm": ["22nm FDSOI / Ultra-Low-Leakage CMOS", "22nm Fully-Depleted SOI (FDSOI)", 22, 8.18, 0.80, 1.80, 0.26, 68, 0.019, 9.0, 0.222,
             0.250, 0.120, 0.240, 0.140, 0.200, 1.90, 0.36, "22FDX / Stillmaker 20nm–22nm; 68 mV/dec FDSOI slope; 9 fF/µm² HD-MOM"],
    "16nm": ["16nm FinFET CMOS", "3D Tri-Gate FinFET (16FF/14LPP)", 16, 11.25, 0.80, 1.80, 0.24, 65, 0.0095, 12.5, 0.160, 0.195, 0.088,
             0.195, 0.105, 0.160, 2.30, 0.30, "Stillmaker & Baas (2017) 16nm/14nm FinFET; 12.5 fF/µm² M1–M7 MOM"],
    "7nm": ["7nm EUV FinFET CMOS", "EUV 3D FinFET (N7 / 7LPP)", 7, 25.71, 0.75, 1.50, 0.21, 63, 0.0026, 18.0, 0.111, 0.150, 0.055, 0.145,
            0.072, 0.122, 2.90, 0.25, "Stillmaker & Baas (2017) 7nm FinFET & IRDS 2022; 18 fF/µm² deep-via MOM"],
}
NODES = {k: dict(zip(_NK, v), short=k) for k, v in _NV.items()}
NODE_OPT = {"180nm": "180nm — GF180MCU Native Baseline (1.00× Reference)", "130nm": "130nm — Bulk CMOS (κ_L = 1.38×, MOS Area 0.52×)",
            "65nm": "65nm — LP/GP Bulk CMOS (κ_L = 2.77×, MOS Area 0.14×)", "28nm": "28nm — HKMG Planar CMOS (κ_L = 6.43×, MOS Area 0.032×)",
            "22nm": "22nm — FDSOI / ULL CMOS (κ_L = 8.18×, MOS Area 0.019×)", "16nm": "16nm — FinFET CMOS (κ_L = 11.25×, MOS Area 0.0095×)",
            "7nm": "7nm — EUV FinFET CMOS (κ_L = 25.71×, MOS Area 0.0026×)"}
PROFILE = {
    "TOP1_DCVS": (0.00, 0.00, 0.00, 0.65, "Pure MOS DCVS latch (scales 1:1 with logic FETs)"),
    "TOP2_WILSON_CM": (0.00, 0.00, 0.00, 0.55, "Pure MOS Wilson current-mirror feedback"),
    "TOP3_NVT_CASC": (0.00, 0.00, 0.28, 0.25, "MOS + split-node poly resistor (no MIM caps)"),
    "TOP4_CAP_BOOST": (0.54, 0.38, 0.34, 0.22, "1× MIM bootstrap cap (72fF) + 2× poly resistors"),
    "TOP5_SPLITRAIL_CLAMP": (0.00, 0.00, 0.26, 0.40, "Complementary PMOS-input + 2× split-node resistors"),
    "TOP6_ENVELOPE_UNIVERSAL": (0.00, 0.00, 0.00, 0.45, "Pure MOS 66-FET dual-folded envelope universal LS"),
    "TOP7_AC_DIFF_KEEPER": (1.00, 0.58, 0.32, 0.15, "Pure AC-coupled differential 2× 162fF MIM caps"),
    "TOP8_AC_HYST_TRIP": (0.90, 0.54, 0.30, 0.12, "Pure AC-coupled 2× 162fF MIM caps + Schmitt R-divider"),
    "TOP9_HVT_CASC_DCVS": (0.00, 0.00, 0.24, 0.70, "2-stack HV cascode DCVS + bias resistor divider"),
    "TOP10_HVT_BOOTSTRAP_DYNAMIC": (0.89, 0.42, 0.32, 0.55, "2-stack HV + 4× MIM bootstrap/dynamic-gate caps + R-div"),
    "TOP11_HVT_TRIPLE_STACK": (0.87, 0.46, 0.38, 0.75, "3-stack HV + 5× MIM bootstrap/dynamic-gate caps + R-div"),
}
TOPO_COLORS = {"TOP1_DCVS": "#2a78d6", "TOP2_WILSON_CM": "#eb6834", "TOP3_NVT_CASC": "#1baf7a", "TOP4_CAP_BOOST": "#9a6700",
               "TOP5_SPLITRAIL_CLAMP": "#8c564b", "TOP6_ENVELOPE_UNIVERSAL": "#8a8780", "TOP7_AC_DIFF_KEEPER": "#cf222e",
               "TOP8_AC_HYST_TRIP": "#1a7f37", "TOP9_HVT_CASC_DCVS": "#3b6ea5", "TOP10_HVT_BOOTSTRAP_DYNAMIC": "#b55d19",
               "TOP11_HVT_TRIPLE_STACK": "#8f7aa8"}


def prof(tid):
    p = PROFILE.get(tid)
    return dict(zip(("cap_frac", "f_cap", "f_rc", "f_cont", "note"), p)) if p else {"cap_frac": 0.5, "f_cap": 0.0, "f_rc": 0.0, "f_cont": 0.3, "note": ""}


def node_area(c, tid, nk):
    """Port of computeTopoNodeArea (model)."""
    N = NODES.get(nk, NODES["180nm"])
    inv = (c.PRE.get("unit_inv_comp") or {}).get("inv_meta") or {}
    ia = (inv.get("area") or {}).get("total_area_um2") or 0.84
    ib = (inv.get("pex_meta") or {}).get("layout_area_um2") or 65.49
    act, bb = ia * N["s_area_mos"], ib * N["s_area_mos"]
    if tid == "REF_UNIT_INV":
        return {"mos_um2": act, "cap_um2": 0.0, "res_um2": 0.0, "passive_um2": 0.0, "total_um2": act, "bbox_um2": bb, "ge_active": 1.0}
    a = c.T.get(tid, {}).get("area") or {"mos_area_um2": 10.0, "passive_area_um2": 0.0}
    p = prof(tid)
    mos, pas = a.get("mos_area_um2") or 0.0, a.get("passive_area_um2") or 0.0
    cap, res = pas * p["cap_frac"], pas * (1.0 - p["cap_frac"])
    ms, cs, rs = mos * N["s_area_mos"], cap * N["s_area_cap"], res * N["s_area_res"]
    tot = ms + cs + rs
    return {"mos180": mos, "cap180": cap, "res180": res, "pas180": pas, "tot180": mos + pas, "mos_um2": ms, "cap_um2": cs, "res_um2": rs,
            "passive_um2": cs + rs, "total_um2": tot, "ge_active": tot / act if act > 0 else 1.0, "ge_180": (mos + pas) / ia if ia > 0 else 1.0}


def scale_base(b, nk):
    if not b:
        return None
    if not nk or nk == "180nm":
        return dict(b)
    N = NODES[nk]
    v = b.get("vdd") or 1.2
    ov = N["phi_cont_lowv"] ** (0.55 * (1.2 - v) / 0.6) if v <= 1.0 else 1.0
    d = N["s_t_fo4"] * ov
    out = dict(b)
    for k, s in (("e_dyn_fj", N["s_c_mos"]), ("p_sw_nw", N["s_c_mos"]), ("tplh_ps", d), ("tphl_ps", d), ("tpd_ps", d), ("p_stat_nw", N["s_leak"])):
        out[k] = None if b.get(k) is None else b[k] * s
    return out


def scale_topo(r, tid, nk, sb):
    """Port of scaleTopoRow (model): MOS vs passive capacitance, RC vs active delay, low-VDD contention."""
    if not r:
        return None
    if not nk or nk == "180nm":
        return dict(r)
    N, p = NODES[nk], prof(tid)
    v = r.get("vdd") or 1.2
    se = (1.0 - p["f_cap"]) * N["s_c_mos"] + p["f_cap"] * N["s_c_cap"]
    mp = se / N["s_c_mos"]
    cont = N["phi_cont_lowv"] ** (p["f_cont"] * (1.4 - v) / 0.8) if v <= 1.2 else N["phi_cont_lowv"] ** (0.15 * p["f_cont"])
    md = ((1.0 - p["f_rc"]) + p["f_rc"] * (N["s_t_rc"] / N["s_t_fo4"])) * cont
    m = lambda k, f, n: None if r.get(k) is None else tofixed(r[k] * f, n)  # noqa: E731
    psw, psw2, rise, rise2, fall, fall2 = m("psw_mult", mp, 1), m("psw_mult_2d", mp, 2), m("rise_mult", md, 1), m("rise_mult_2d", md, 2), \
        m("fall_mult", md, 1), m("fall_mult_2d", md, 2)
    itlh = sb.get("tplh_ps") if sb and sb.get("tplh_ps") else (r.get("tplh_ps") or 0) * N["s_t_fo4"]
    ithl = sb.get("tphl_ps") if sb and sb.get("tphl_ps") else (r.get("tphl_ps") or 0) * N["s_t_fo4"]
    tlh = rise2 * itlh if (r.get("pass") and rise2 is not None and itlh) else (None if r.get("tplh_ps") is None else r["tplh_ps"] * N["s_t_fo4"] * md)
    thl = fall2 * ithl if (r.get("pass") and fall2 is not None and ithl) else (None if r.get("tphl_ps") is None else r["tphl_ps"] * N["s_t_fo4"] * md)
    out = dict(r)
    out.update(e_dyn_fj=None if r.get("e_dyn_fj") is None else r["e_dyn_fj"] * se, p_sw_nw=None if r.get("p_sw_nw") is None else r["p_sw_nw"] * se,
               tplh_ps=tlh, tphl_ps=thl, tpd_ps=0.5 * (tlh + thl) if tlh is not None and thl is not None else None,
               p_stat_nw=None if r.get("p_stat_nw") is None else r["p_stat_nw"] * N["s_leak"], psw_mult=psw, psw_mult_2d=psw2,
               rise_mult=rise, rise_mult_2d=rise2, fall_mult=fall, fall_mult_2d=fall2, raw_180_psw_mult=r.get("psw_mult"),
               raw_180_rise_mult=r.get("rise_mult"), raw_180_fall_mult=r.get("fall_mult"))
    return out


class UI:
    """Unit-inverter view for one (node, stage)."""

    def __init__(self, c, nk, st):
        self.c, self.nk, self.st, self.N = c, nk, st, NODES[nk]
        comp = c.S[st].get("unit_inv_comp") or c.PRE.get("unit_inv_comp")
        self.vdds = comp.get("vdds") or [0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8]
        self.base = [scale_base(b, nk) for b in comp.get("baseline") or []]
        self.bv = {fx(b["vdd"], 1): b for b in self.base if b}
        self.raw = comp.get("rows") or []
        self.scaled = nk != "180nm"
        self.tag = f"{STAGE_TAG[st]} · {nk}"
        self.pre = f"data/unitinv/{nk}/{st}"

    def row(self, tid, v):
        r0 = next((x for x in self.raw if x["topology"] == tid and abs(x["vdd"] - v) < 0.01), None)
        return scale_topo(r0, tid, self.nk, self.bv.get(fx(v, 1))) if r0 else None

    def trend(self, key, title, ylab):
        tr, groups = [], []
        tids = [t["id"] for t in self.c.topos]
        for idx, tid in enumerate(tids):
            col = TOPO_COLORS.get(tid, "#2a78d6")
            pp, ff = [], []
            for v in self.vdds:
                r = self.row(tid, v)
                if not r:
                    continue
                val = r.get(key)
                if r.get("pass") and val is not None and val > 0:
                    pp.append((v, val, r))
                elif not r.get("pass") and key == "psw_mult" and val is not None and val > 0:
                    ff.append((v, val, r))
            tr.append({"type": "scatter", "mode": "lines+markers", "name": short_tid(tid), "legendgroup": tid, "x": [p[0] for p in pp],
                       "y": [p[1] for p in pp], "line": {"color": col, "width": 2, "dash": "dash" if idx >= 6 else "solid"},
                       "marker": {"size": 7, "color": col},
                       "text": [f"{tid} @ 0→{fx(v, 1)}V ({self.nk}): {fx(val, 1)}x (Psw={fx(r.get('psw_mult'), 1)}x [{fx(r.get('p_sw_nw'), 1)}nW], "
                                f"Rise={fx(r.get('rise_mult'), 1)}x [{fx(r.get('tplh_ps'), 1)}ps], Fall={fx(r.get('fall_mult'), 1)}x "
                                f"[{fx(r.get('tphl_ps'), 1)}ps])" for v, val, r in pp], "hovertemplate": "%{text}<extra></extra>"})
            groups.append(tid)
            if ff:
                tr.append({"type": "scatter", "mode": "markers", "name": f"{short_tid(tid)} FAIL", "legendgroup": tid, "showlegend": False,
                           "x": [p[0] for p in ff], "y": [p[1] for p in ff],
                           "marker": {"size": 8, "color": "rgba(0,0,0,0)", "line": {"color": "theme:bad", "width": 1.4}},
                           "text": [f"{tid} @ VDD={fx(v, 1)}V ({self.nk}): FAIL (180nm Swing={fx(r.get('swing_pct'), 1)}%, Psw={fx(val, 1)}x)"
                                    for v, val, r in ff], "hovertemplate": "%{text}<extra></extra>"})
                groups.append(tid)
        tr.append({"type": "scatter", "mode": "lines", "name": f"1.0x Unit Inverter ({self.nk})", "x": [0.6, 1.8], "y": [1, 1],
                   "line": {"color": "theme:good", "dash": "dash", "width": 1.5}, "hoverinfo": "skip"})
        groups.append("REF")
        hv = lambda t: t.startswith(("TOP9", "TOP10", "TOP11"))  # noqa: E731
        vis = lambda f: [True if g == "REF" else f(g) for g in groups]  # noqa: E731
        lay = {"xaxis": {"title": {"text": f"Single-Domain Supply Voltage VDD (V) [Both Domains 0 → VDD · {self.nk}]"}, "tickvals": self.vdds},
               "yaxis": {"title": {"text": ylab}, "type": "log"}, "margin": {"t": 50, "b": 130},
               "legend": {"orientation": "h", "x": 0, "xanchor": "left", "y": -0.24, "yanchor": "top", "font": {"size": 10}},
               "updatemenus": [
                   {"type": "buttons", "direction": "right", "x": 0, "xanchor": "left", "y": 1.02, "yanchor": "bottom", "showactive": True,
                    "font": {"size": 10}, "buttons": [{"label": "Log10 scale", "method": "relayout", "args": [{"yaxis.type": "log"}]},
                                                      {"label": "Linear scale", "method": "relayout", "args": [{"yaxis.type": "linear"}]}]},
                   {"type": "dropdown", "x": 0.42, "xanchor": "left", "y": 1.02, "yanchor": "bottom", "font": {"size": 10}, "buttons": [
                       {"label": "All 11 Topologies (TOP1..TOP11)", "method": "restyle", "args": ["visible", vis(lambda g: True)]},
                       {"label": "Multi-Domain & AC-Coupled (TOP1..TOP8)", "method": "restyle", "args": ["visible", vis(lambda g: not hv(g))]},
                       {"label": "HV-Tolerant Stacked Architectures (TOP9..TOP11)", "method": "restyle", "args": ["visible", vis(hv)]}]}]}
        src = self.c.o.put(f"{self.pre}/trend_{key}.json", {"data": tr, "layout": lay})
        return {"type": "chart", "title": f"{title} ({self.tag})", "src": src, "height": 460,
                "caption": "Buttons: Y-axis scale (log / linear) and the topology group filter of the old report. Open red circles = "
                           "attempted (failing) points, plotted for the power ratio only."}

    def bar(self, v):
        tids = [t["id"] for t in self.c.topos]
        labs = [tid.replace("_", " ", 1)[:18] for tid in tids]
        rows = [self.row(tid, v) for tid in tids]
        tr = []
        for key, name, col in (("psw_mult", "Switching Power (#.#x)", "#eb6834"), ("rise_mult", "Rise Delay tpLH (#.#x)", "#2a78d6"),
                               ("fall_mult", "Fall Delay tpHL (#.#x)", "#1baf7a")):
            tr.append({"type": "bar", "orientation": "h", "name": name, "y": labs,
                       "x": [(r.get(key) if r and r.get("pass") and (r.get(key) or 0) > 0 else None) for r in rows], "marker": {"color": col},
                       "hovertemplate": f"%{{y}} @ {fx(v, 1)}V ({self.nk}): %{{x:.1f}}x<extra>{name}</extra>"})
        tr.append({"type": "scatter", "mode": "lines", "name": "1.0x", "x": [1, 1], "y": [labs[0], labs[-1]], "showlegend": False,
                   "line": {"color": "theme:good", "dash": "dash", "width": 1.5}, "hoverinfo": "skip"})
        ann = []
        for lab, r in zip(labs, rows):
            if not r:
                continue
            if not r.get("pass"):
                t = f" (Attempted Psw={fx(r.get('psw_mult'), 1)}x, Swing={fx(r.get('swing_pct'), 1)}%)" if r.get("psw_mult") is not None else ""
                ann.append({"xref": "paper", "x": 0.01, "xanchor": "left", "y": lab, "showarrow": False, "text": f"FAIL @ {fx(v, 1)}V{t}",
                            "font": {"color": "theme:bad", "size": 10}})
            else:
                ann.append({"xref": "paper", "x": 1.01, "xanchor": "left", "y": lab, "showarrow": False,
                            "text": f"{fx(r.get('psw_mult'), 1)}x | {fx(r.get('rise_mult'), 1)}x | {fx(r.get('fall_mult'), 1)}x", "font": {"size": 9}})
        lay = {"barmode": "group", "xaxis": {"type": "log", "title": {"text": "#.#x vs. unit inverter (log)"}},
               "yaxis": {"autorange": "reversed", "type": "category"}, "annotations": ann, "margin": {"l": 150, "r": 140, "t": 40, "b": 110},
               "legend": {"orientation": "h", "x": 0, "xanchor": "left", "y": -0.14, "yanchor": "top"},
               "updatemenus": [{"type": "buttons", "direction": "right", "x": 0, "xanchor": "left", "y": 1.01, "yanchor": "bottom",
                                "font": {"size": 10}, "buttons": [{"label": "Log10", "method": "relayout", "args": [{"xaxis.type": "log"}]},
                                                                  {"label": "Linear", "method": "relayout", "args": [{"xaxis.type": "linear"}]}]}]}
        src = self.c.o.put(f"{self.pre}/bar_{fx(v, 1)}.json", {"data": tr, "layout": lay})
        return {"type": "chart", "title": f"Plot 2: All 11 Topologies @ VDD={fx(v, 1)}V ({self.tag}): #.#x Power / Rise / Fall", "src": src, "height": 520}

    def baseline_table(self):
        rows = []
        for v in self.vdds:
            b = next((x for x in self.base if x and abs(x["vdd"] - v) < 0.01), None)
            if not b:
                rows.append({"vdd_lbl": f"0 → {fx(v, 1)} V", "ratio": "1.0x"})
                continue
            rows.append({"vdd_lbl": f"0 → {fx(v, 1)} V", "swing": {"v": b.get("swing_pct"), "s": "good" if b.get("pass") else "bad"},
                         "psw": mul(b.get("p_sw_nw"), NW), "edyn": mul(b.get("e_dyn_fj"), FJ), "tplh": mul(b.get("tplh_ps"), PS),
                         "tphl": mul(b.get("tphl_ps"), PS), "tpd": mul(b.get("tpd_ps"), PS), "pstat": mul(b.get("p_stat_nw"), NW),
                         "ratio": {"v": "1.0x Psw · 1.0x Rise · 1.0x Fall", "s": "good"}})
        return {"type": "table", "search": False, "csv": True, "rows": rows,
                "title": f"5.1 Custom Baseline Unit-Sized CMOS Inverter (`REF_UNIT_INV` — "
                         f"{'Scaled to ' + self.N['name'] if self.scaled else '180nm Native `Wp=2.0µm / Wn=1.0µm, L=0.28µm`'})",
                "columns": [{"key": "vdd_lbl", "label": "VDD (0→VDD)", "type": "text"}, {"key": "swing", "label": "Swing", "unit": "%", "digits": 4},
                            {"key": "psw", "label": "Sw. Power Psw (@ 10MHz)", "unit": "W", "si": True, "digits": 4},
                            {"key": "edyn", "label": "Edyn", "unit": "J", "si": True, "digits": 4},
                            {"key": "tplh", "label": "Rise Delay tpLH", "unit": "s", "si": True, "digits": 5},
                            {"key": "tphl", "label": "Fall Delay tpHL", "unit": "s", "si": True, "digits": 5},
                            {"key": "tpd", "label": "Mean tpd", "unit": "s", "si": True, "digits": 5},
                            {"key": "pstat", "label": "Pstat", "unit": "W", "si": True, "digits": 3}, {"key": "ratio", "label": "Baseline Ratio", "type": "text"}]}

    def matrix(self, mode):
        ia = node_area(self.c, "REF_UNIT_INV", self.nk)
        cols = [{"key": "topo", "label": "Topology", "md": True, "type": "text"},
                {"key": "arch", "label": f"Architecture & {self.nk} Area", "md": True, "type": "text"}]
        cols += [{"key": f"v{fx(v, 1)}", "label": f"VDD = {fx(v, 1)} V<br><small>0→{fx(v, 1)}V ({self.nk})</small>", "md": True, "type": "text"}
                 for v in self.vdds]
        ref = {"topo": f"**REF_UNIT_INV**<br><small>Unit Inverter Baseline ({self.nk})</small>",
               "arch": {"v": f"1.0 GE ({fx(ia['mos_um2'], 3)} µm²)", "s": "good"}}
        for v in self.vdds:
            b = next((x for x in self.base if x and abs(x["vdd"] - v) < 0.01), None)
            if b:
                dp = 2 if self.scaled and (b.get("p_sw_nw") or 0) < 10 else 1
                ref[f"v{fx(v, 1)}"] = {"v": f"**1.0x Psw | 1.0x R | 1.0x F**<br>{fx(b.get('p_sw_nw'), dp)}nW · {fx(b.get('tplh_ps'), 1)}/{fx(b.get('tphl_ps'), 1)}ps",
                                       "s": "good"}
        rows = [ref]
        for t in self.c.topos:
            tid = t["id"]
            a = node_area(self.c, tid, self.nk)
            da = 2 if a["total_um2"] < 1.0 else 1
            row = {"topo": f"**{tid}**<br><small>{t['name']}</small>",
                   "arch": f"`{t.get('coupled_type')}`<br><small>{fx(a['total_um2'], da)} µm² ({fx(a['ge_active'], 1)} GE)</small>"}
            for v in self.vdds:
                r = self.row(tid, v)
                k = f"v{fx(v, 1)}"
                if not r:
                    row[k] = "N/A"
                    continue
                if not r.get("pass"):
                    ptry = f"{fx(r.get('psw_mult'), 1)}x Psw" if r.get("psw_mult") is not None else "—"
                    row[k] = {"v": f"FAIL ({fx(r.get('swing_pct'), 0)}%)<br><small>({ptry})</small>", "s": "bad",
                              "title": f"180nm Swing={fx(r.get('swing_pct'), 1)}%, Attempted Psw={ptry}"}
                    continue
                dp = 2 if self.scaled and (r.get("p_sw_nw") or 0) < 10 else 1
                de = 2 if self.scaled and (r.get("e_dyn_fj") or 0) < 10 else 1
                if mode == "psw":
                    row[k] = f"**{fx(r.get('psw_mult'), 1)}x**<br><small>{fx(r.get('p_sw_nw'), dp)} nW ({fx(r.get('e_dyn_fj'), de)} fJ)</small>"
                elif mode == "rise":
                    row[k] = f"**{fx(r.get('rise_mult'), 1)}x**<br><small>tpLH = {fx(r.get('tplh_ps'), 1)} ps</small>"
                elif mode == "fall":
                    row[k] = f"**{fx(r.get('fall_mult'), 1)}x**<br><small>tpHL = {fx(r.get('tphl_ps'), 1)} ps</small>"
                else:
                    row[k] = {"v": f"**{fx(r.get('psw_mult'), 1)}x** Psw<br>**{fx(r.get('rise_mult'), 1)}x** R · **{fx(r.get('fall_mult'), 1)}x** F",
                              "title": f"{self.nk}: Psw={fx(r.get('p_sw_nw'), dp)}nW ({fx(r.get('psw_mult_2d'), 2)}x; 180nm={fx(r.get('raw_180_psw_mult'), 1)}x) | "
                                       f"tpLH={fx(r.get('tplh_ps'), 1)}ps ({fx(r.get('rise_mult_2d'), 2)}x; 180nm={fx(r.get('raw_180_rise_mult'), 1)}x) | "
                                       f"tpHL={fx(r.get('tphl_ps'), 1)}ps ({fx(r.get('fall_mult_2d'), 2)}x; 180nm={fx(r.get('raw_180_fall_mult'), 1)}x)"}
            rows.append(row)
        return table_src(self.c, f"{self.pre}/matrix_{mode}.json", None, cols, rows, search=False)

    def long_table(self):
        rows = []
        for t in self.c.topos:
            for v in self.vdds:
                r = self.row(t["id"], v)
                if r:
                    rows.append({"topo": t["id"], "vdd_sd": v, "pass": bool(r.get("pass")), "swing": r.get("swing_pct"),
                                 "psw": mul(r.get("p_sw_nw"), NW), "pswx": r.get("psw_mult"), "pswx2": r.get("psw_mult_2d"),
                                 "edyn": mul(r.get("e_dyn_fj"), FJ), "tplh": mul(r.get("tplh_ps"), PS), "risex": r.get("rise_mult"),
                                 "tphl": mul(r.get("tphl_ps"), PS), "fallx": r.get("fall_mult"), "tpd": mul(r.get("tpd_ps"), PS),
                                 "pstat": mul(r.get("p_stat_nw"), NW), "ptotx": None if self.scaled else r.get("ptot_mult")})
        cols = [{"key": "topo", "label": "Topology", "type": "text"}, {"key": "vdd_sd", "label": "VDD", "unit": "V", "si": True},
                {"key": "pass", "label": "Pass", "type": "status"}, {"key": "swing", "label": "Swing (180 nm)", "unit": "%", "digits": 4},
                {"key": "psw", "label": "Psw", "unit": "W", "si": True, "digits": 4}, {"key": "pswx", "label": "Psw ×", "digits": 4},
                {"key": "pswx2", "label": "Psw × (2 dp)", "digits": 4}, {"key": "edyn", "label": "Edyn", "unit": "J", "si": True, "digits": 4},
                {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4}, {"key": "risex", "label": "Rise ×", "digits": 4},
                {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4}, {"key": "fallx", "label": "Fall ×", "digits": 4},
                {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4}, {"key": "pstat", "label": "Pstat", "unit": "W", "si": True}]
        if not self.scaled:
            cols.append({"key": "ptotx", "label": "Ptot ×", "digits": 4})
        return table_src(self.c, f"{self.pre}/long.json", f"All topology × VDD rows ({self.tag})", cols, rows, page_size=100)

    def cost(self, v):
        ia = node_area(self.c, "REF_UNIT_INV", self.nk)
        area = ((self.c.PRE.get("unit_inv_comp") or {}).get("inv_meta") or {}).get("area") or {}
        b = self.bv.get(fx(v, 1))
        rows = []
        if b:
            rows.append({"topo": "**REF_UNIT_INV** <small>(Baseline)</small>", "a180": area.get("total_area_um2"), "mos": ia["mos_um2"], "pas": 0.0,
                         "tot": ia["total_um2"], "ge": {"v": "1.0 GE", "s": "good"}, "edyn": mul(b.get("e_dyn_fj"), FJ), "psw": mul(b.get("p_sw_nw"), NW),
                         "dly": f"{fx(b.get('tplh_ps'), 1)} / {fx(b.get('tphl_ps'), 1)}", "mult": {"v": "1.0x | 1.0x | 1.0x", "s": "good"}})
        for t in self.c.topos:
            tid = t["id"]
            a = node_area(self.c, tid, self.nk)
            r = self.row(tid, v)
            if not r:
                rows.append({"topo": f"**{tid}**", "dly": "N/A"})
                continue
            g = a["ge_active"] / a["ge_180"] if a["ge_180"] > 0 else 1.0
            ge = f"{fx(a['ge_active'], 1)} GE" + (f" ({fx(g, 1)}× vs 180nm GE)" if self.scaled and g > 1.2 else "")
            rows.append({"topo": f"**{tid}**<br><small>{prof(tid)['note'] or t.get('coupled_type')}</small>",
                         "a180": a["tot180"], "ge180": a["ge_180"], "mos": a["mos_um2"], "pas": a["passive_um2"], "tot": a["total_um2"],
                         "ge": {"v": ge, "s": "warn" if g > 3.0 else None}, "edyn": mul(r.get("e_dyn_fj"), FJ), "psw": mul(r.get("p_sw_nw"), NW),
                         "dly": f"{fx(r.get('tplh_ps'), 1)} / {fx(r.get('tphl_ps'), 1)}" if r.get("pass") else
                         {"v": f"180nm FAIL ({fx(r.get('swing_pct'), 0)}%)", "s": "bad"},
                         "mult": f"{fx(r.get('psw_mult'), 1)}x | {fx(r.get('rise_mult'), 1)}x | {fx(r.get('fall_mult'), 1)}x" if r.get("pass") else
                         {"v": f"FAIL @ {fx(v, 1)}V ({fx(r.get('psw_mult'), 1)}x Psw)", "s": "bad"}})
        n = self.nk
        cols = [{"key": "topo", "label": "Topology", "md": True, "type": "text"}, {"key": "a180", "label": "180nm Area", "unit": "µm²", "digits": 4},
                {"key": "ge180", "label": "180nm GE", "digits": 3}, {"key": "mos", "label": f"{n} MOS Area", "unit": "µm²", "digits": 4},
                {"key": "pas", "label": f"{n} Passive Area", "unit": "µm²", "digits": 4}, {"key": "tot", "label": f"{n} Total Area", "unit": "µm²", "digits": 4},
                {"key": "ge", "label": f"{n} Gate-Equiv. Cost (GE)", "type": "text"}, {"key": "edyn", "label": "Scaled Edyn", "unit": "J", "si": True, "digits": 4},
                {"key": "psw", "label": "Scaled Psw", "unit": "W", "si": True, "digits": 4},
                {"key": "dly", "label": "Scaled tpLH / tpHL (ps)", "type": "text"}, {"key": "mult", "label": f"{n} #.#x (Psw | Rise | Fall)", "type": "text"}]
        return table_src(self.c, f"{self.pre}/cost_{fx(v, 1)}.json",
                         f"5.4 Node-Scaled Level Shifter Implementation Cost & Overhead Estimator at `VDD = {fx(v, 1)} V` ({self.N['name']} · {STAGE_TAG[self.st]})",
                         cols, rows, search=False, caption=self.c.card_p("5.4"))


def node_banner(c, nk):
    N = NODES[nk]
    sc = nk != "180nm"
    items = [{"label": "Target Node", "value": N["name"]}, {"label": "Linear κ_L", "value": f"{fx(N['k_L'], 2)}×"},
             {"label": "MOS Area Scale S_A,MOS", "value": f"{N['s_area_mos']}× ({fx(1 / N['s_area_mos'], 0)}× density)"},
             {"label": "MIM/MOM Density", "value": f"{fx(N['c_mim_ff_um2'], 1)} fF/µm² (S_A,cap={N['s_area_cap']}×)"},
             {"label": "FO4 Delay Scale S_t", "value": f"{N['s_t_fo4']}×"}, {"label": "MOS Energy Scale S_C,MOS", "value": f"{N['s_c_mos']}×"},
             {"label": "Passive Cap Scale S_C,cap", "value": f"{N['s_c_cap']}× (Cap/MOS Ratio = {fx(N['s_c_cap'] / N['s_c_mos'], 2)}×)"}]
    txt = (f"**Scaling Effect at {nk}:** Pure-MOS level shifters (`TOP1, TOP2, TOP6`) scale down in area by **{fx(1 / N['s_area_mos'], 0)}×** "
           f"and maintain ~constant Gate-Equivalent (`GE`) & `#.#x` power multipliers, whereas MIM/MOM capacitor-coupled topologies "
           f"(`TOP4, TOP7, TOP8, TOP10, TOP11`) experience a **{fx(N['s_c_cap'] / N['s_c_mos'], 2)}×** higher relative switching-power ratio and "
           f"a **{fx(N['s_area_cap'] / N['s_area_mos'], 1)}×** passive-to-MOS area penalty ([see derivation in Section 13 Appendix](#/ls?page=appendix))."
           if sc else
           "Showing unscaled native **180nm GF180MCU** SPICE measurements. Select `130nm`, `65nm`, `28nm`, `22nm`, `16nm`, or `7nm` in "
           "**Scale to:** above to project area, Gate-Equivalents, delay, and switching energy to newer nodes.")
    b = [{"type": "kv", "cols": 4, "items": items}, {"type": "markdown", "text": txt}]
    if sc:
        b.insert(0, {"type": "note", "tone": "warn", "text": f"**Model projection, not a simulation.** Every {nk} number on this tab is the "
                     "180 nm simulation scaled by the report's literature scaling model (Section 13 / *Scaling appendix* page); only the "
                     "180 nm tab shows simulated values."})
    return b


def inv_card(c, nk):
    comp = c.PRE.get("unit_inv_comp") or {}
    inv = comp.get("inv_meta") or {}
    pm, area = inv.get("pex_meta") or {}, inv.get("area") or {}
    ia = node_area(c, "REF_UNIT_INV", nk)
    items = [{"label": "180nm BBox", "value": f"{fx(pm.get('width_um'), 2)} × {fx(pm.get('height_um'), 2)} µm ({fx(pm.get('layout_area_um2'), 2)} µm²)"},
             {"label": "Active MOS", "value": f"{fx(area.get('mos_area_um2'), 2)} µm² (1.0 GE)"}]
    if nk != "180nm":
        items.append({"label": f"Scaled {nk} cell area (model)", "value": f"{fx(ia['bbox_um2'], 3)} µm² · Active MOS {fx(ia['mos_um2'], 4)} µm² (1.0 GE)"})
    items.append({"label": "Magic Post-PEX (180nm)", "value": f"{pm.get('n_extracted_devs') or 2} FETs, {pm.get('n_parasitic_caps') or 4} C_par "
                                                              f"({fx(pm.get('total_cap_ff'), 2)} fF), {pm.get('n_parasitic_res') or 2} R_par ({fx(pm.get('total_res_ohm'), 1)} Ω)"})
    lay = pm.get("layout_png") or "assets/layout_REF_UNIT_INV.png"
    out = [{"type": "image", "title": f"Custom gLayout Unit-Sized CMOS Inverter (REF_UNIT_INV {'· Scaled to ' + nk if nk != '180nm' else '· 180nm Native'})",
            "src": lay, "bg": "white", "max_height": 300}] if (c.docs / lay).is_file() else []
    return out + [{"type": "kv", "cols": 1, "items": items}]


def p_unitinv(c):
    comp = c.PRE.get("unit_inv_comp")
    if not comp:
        return {"blocks": []}
    inv = comp.get("inv_meta") or {}
    tabs = []
    for nk in NODE_ORDER:
        uis = {st: UI(c, nk, st) for st, _ in STAGES if c.S[st].get("unit_inv_comp")}
        b = node_banner(c, nk)
        net = [{"type": "code", "stage": "pre", "alt": "invnet", "title": "REF_UNIT_INV SPICE netlist", "text": inv.get("spice") or "", "max_height": 220},
               {"type": "code", "stage": "full", "alt": "invnet", "title": "REF_UNIT_INV post-PEX netlist",
                "text": (inv.get("pex_meta") or {}).get("pex_spice") or inv.get("spice") or "", "max_height": 220}]
        b.append({"type": "section", "cols": 2, "blocks": [
            {"type": "section", "blocks": [{"type": "markdown", "text": c.card_p("5.1").replace(
                "Toggle **Pre-PEX / Post-PEX** or", "Switch the **Simulation** option in the top bar (Pre-PEX / Full post-PEX) or")}] +
             inv_card(c, nk)[1:] +
             [{"type": "section", "title": "Inspect REF_UNIT_INV SPICE / Post-PEX Netlist", "collapsed": True, "blocks": net}]},
            {"type": "section", "blocks": inv_card(c, nk)[:1]}]})
        b += [dict(u.baseline_table(), stage=st, alt="base") for st, u in uis.items()]
        curves = []
        for key, title, yl in (("psw_mult", "Plot 1: Switching Power Multiplier (#.#x vs. Unit Inverter)", "Switching Power Ratio (#.#x)"),
                               ("rise_mult", "Plot 3: Rise Delay tpLH Multiplier (#.#x vs. Unit Inverter)", "Rise Delay Ratio (#.#x)"),
                               ("fall_mult", "Plot 4: Fall Delay tpHL Multiplier (#.#x vs. Unit Inverter)", "Fall Delay Ratio (#.#x)")):
            curves += [dict(u.trend(key, title, yl), stage=st, alt=f"tr-{key}") for st, u in uis.items()]
        vt = []
        for v in sorted(uis["pre"].vdds, reverse=True):
            vt.append({"label": f"VDD = {fx(v, 1)} V", "key": fx(v, 1), "blocks": [dict(u.bar(v), stage=st, alt="bar") for st, u in uis.items()] +
                       [dict(u.cost(v), stage=st, alt="cost") for st, u in uis.items()]})
        b.append({"type": "section", "title": c.h3("5.2"), "blocks": [{"type": "section", "cols": 2, "blocks": curves},
                  {"type": "tabs", "style": "select", "label": "Single-VDD comparison point", "id": "ui_vdd", "tabs": vt,
                   "caption": "Single-VDD Bar & Cost Comparison Point: selects the VDD of Plot 2 and of the 5.4 cost table."}]})
        mt = []
        for mode, lab in (("triplet", "All 3 Metrics: #.#x Power | #.#x Rise | #.#x Fall"), ("psw", "Switching Power Ratio (#.#x Psw + Scaled nW / fJ)"),
                          ("rise", "Rise Delay Ratio (#.#x tpLH + Scaled ps)"), ("fall", "Fall Delay Ratio (#.#x tpHL + Scaled ps)")):
            mt.append({"label": lab, "key": mode, "blocks": [dict(u.matrix(mode), stage=st, alt=f"mx-{mode}") for st, u in uis.items()]})
        b.append({"type": "section", "title": f"5.3 Complete 11 Topologies × 7 VDDs Normalized Comparison Matrix (`#.#x` vs. Unit Inverter · {NODES[nk]['name']})",
                  "blocks": [{"type": "tabs", "style": "select", "label": "Matrix Cell View", "id": "ui_cell", "tabs": mt},
                             {"type": "section", "title": "Sortable long-form table (all topology × VDD rows)", "collapsed": True,
                              "blocks": [dict(u.long_table(), stage=st, alt="long") for st, u in uis.items()]}]})
        tabs.append({"label": NODE_OPT[nk], "key": nk, "blocks": b})
    return {"blocks": [{"type": "section", "title": c.h2("sec-unitinv"), "intro": c.sec_desc("sec-unitinv"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Scale to:", "id": "ui_node", "tabs": tabs}]}]}


def p_appendix(c):
    cards = c.cards("sec-appendix")
    blocks = [{"type": "section", "cols": 3, "blocks": [{"type": "markdown", "title": h, "text": p} for h, p in cards]}]
    rows = []
    for nk in NODE_ORDER:
        N = NODES[nk]
        rows.append({"node": f"**{nk}**", "fam": f"{N['tech_class']}<br><small>{N['ref_note']}</small>", "kl": f"{fx(N['k_L'], 2)}×",
                     "vdd_cio": f"{fx(N['vdd_core'], 2)}V / {fx(N['vdd_io'], 2)}V", "vth": f"{fx(N['vth0_v'], 2)}V · {N['ss_mv_dec']}",
                     "sam": f"**{N['s_area_mos']}×** <small>({fx(1 / N['s_area_mos'], 0)}×)</small>", "mim": N["c_mim_ff_um2"],
                     "sac": f"{N['s_area_cap']}×", "sar": f"{N['s_area_res']}×", "st": f"**{N['s_t_fo4']}×**", "scm": f"{N['s_c_mos']}×",
                     "scc": f"{N['s_c_cap']}×", "sl": f"{fx(N['s_leak'], 2)}×", "strc": f"{N['s_t_rc']}×", "phi": N["phi_cont_lowv"]})
    T = lambda k, l, **kw: dict({"key": k, "label": l, "type": "text", "md": True}, **kw)  # noqa: E731
    blocks.append({"type": "table", "title": c.h3("13.1"), "caption": c.card_p("13.1") + " (S_t,RC and Φ_cont are the model's remaining "
                   "per-node parameters used by the scaling formulas.)", "search": False, "rows": rows,
                   "columns": [T("node", "Node"), T("fam", "Technology Family"), T("kl", "κ_L (180/L)"), T("vdd_cio", "Core / IO VDD (V)"),
                               T("vth", "Vth0 (V) & SS (mV/dec)"), T("sam", "MOS Area S_A,MOS"),
                               {"key": "mim", "label": "MIM/MOM Density (fF/µm²)", "digits": 3}, T("sac", "Cap Area S_A,cap"),
                               T("sar", "Res Area S_A,res"), T("st", "FO4 Delay S_t,FO4"), T("scm", "MOS Cap S_C,MOS"),
                               T("scc", "Coupling Cap S_C,cap"), T("sl", "Leakage S_leak"), T("strc", "RC Delay S_t,RC"),
                               {"key": "phi", "label": "Φ_cont (low-V)", "digits": 3}]})
    # 13.2 trajectories
    meta = {"ge": ("Gate-Equivalent Cost Trajectory Across Nodes: GE = Area_LS(Node) / Area_UnitInv(Node)", "Gate-Equivalent Cost (GE, Log10)", " GE",
                   "Gate-Equivalent Cost: GE = Area_LS(Node) / Area_UnitInv(Node) [Standard-Cell Cost]"),
            "area_um2": ("Total Active + Passive Silicon Area Trajectory Across Nodes (µm²)", "Total Area (µm², Log10)", " µm²",
                         "Absolute Active + Passive Silicon Area (µm²)"),
            "tpd_ps": ("Scaled Propagation Delay tpd @ VDD = 1.2V Across Nodes (ps)", "Propagation Delay tpd (ps, Log10)", " ps",
                       "Scaled Mean Propagation Delay tpd @ VDD = 1.2V (ps)"),
            "edyn_fj": ("Scaled Dynamic Switching Energy Edyn @ VDD = 1.2V Across Nodes (fJ)", "Dynamic Energy Edyn (fJ, Log10)", " fJ",
                        "Scaled Dynamic Energy per Transition Edyn @ VDD = 1.2V (fJ)"),
            "psw_mult": ("Normalized #.#x Switching Power Multiplier vs. Unit Inverter @ VDD = 1.2V", "Switching Power Ratio (#.#x, Log10)", "x",
                         "Scaled #.#x Switching Power Multiplier vs. Unit Inverter @ VDD = 1.2V")}

    def traj(mk, st):
        comp = c.S[st].get("unit_inv_comp") or c.PRE.get("unit_inv_comp") or {}
        b12 = next((x for x in comp.get("baseline") or [] if abs(x["vdd"] - 1.2) < 0.01), None)
        raw = comp.get("rows") or []
        tr = []
        for i, t in enumerate(c.topos):
            tid = t["id"]
            r12 = next((x for x in raw if x["topology"] == tid and abs(x["vdd"] - 1.2) < 0.01), None) or \
                next((x for x in raw if x["topology"] == tid and abs(x["vdd"] - 1.8) < 0.01), None)
            xs, ys = [], []
            for nk in NODE_ORDER:
                val = None
                if mk == "ge":
                    val = node_area(c, tid, nk)["ge_active"]
                elif mk == "area_um2":
                    val = node_area(c, tid, nk)["total_um2"]
                elif r12:
                    rs = scale_topo(r12, tid, nk, scale_base(b12, nk))
                    val = rs.get({"tpd_ps": "tpd_ps", "edyn_fj": "e_dyn_fj", "psw_mult": "psw_mult"}[mk])
                if val is not None and math.isfinite(val) and val > 0:
                    xs.append(nk), ys.append(val)
            last = f"{fx(ys[-1], 2 if ys[-1] < 1 else 1)}{meta[mk][2]}" if ys else ""
            tr.append({"type": "scatter", "mode": "lines+markers", "name": f"{tid[:14]} · 7nm: {last}", "x": xs, "y": ys,
                       "line": {"color": TOPO_COLORS.get(tid), "width": 2, "dash": "dash" if i >= 6 else "solid"}, "marker": {"size": 7},
                       "hovertemplate": f"{tid} @ %{{x}}: %{{y:.3g}}{meta[mk][2]}<extra></extra>"})
        lay = {"xaxis": {"type": "category", "tickvals": NODE_ORDER, "ticktext": [f"{nk}<br>κ_L={fx(NODES[nk]['k_L'], 1)}×" for nk in NODE_ORDER]},
               "yaxis": {"type": "log", "title": {"text": meta[mk][1]}},
               "legend": {"orientation": "v", "x": 1.02, "xanchor": "left", "y": 1, "yanchor": "top", "font": {"size": 10}},
               "margin": {"r": 220, "t": 20}}
        return {"type": "chart", "title": meta[mk][0], "src": c.o.put(f"data/appendix/traj_{mk}_{st}.json", {"data": tr, "layout": lay}),
                "height": 440, "caption": "Model projection from the 180 nm data (scaling laws of 13.1 and the per-topology profile of 13.3)."}

    tt = []
    for mk in ("ge", "area_um2", "tpd_ps", "edyn_fj", "psw_mult"):
        if mk in ("ge", "area_um2"):
            bl = [traj(mk, "pre")]
        else:
            bl = alts(lambda st, mk=mk: traj(mk, st), f"traj-{mk}")
        tt.append({"label": meta[mk][3], "key": mk, "blocks": bl})
    blocks.append({"type": "section", "title": c.h3("13.2"), "blocks": [{"type": "tabs", "style": "select", "id": "app_metric",
                                                                         "label": "Select Cross-Node Trajectory Metric", "tabs": tt}]})
    keys = ["180nm", "65nm", "22nm", "16nm", "7nm"]
    rows = [{"topo": "**REF_UNIT_INV** <small>(1.0 GE Reference)</small>", "mcr": "0.84 / 0.0 / 0.0", "fcap": 0.0, "frc": 0.0,
             **{nk: {"v": f"**{fx(node_area(c, 'REF_UNIT_INV', nk)['total_um2'], 4)} µm²**<br>1.0 GE", "s": "good"} for nk in keys}}]
    for t in c.topos:
        p, a = prof(t["id"]), node_area(c, t["id"], "180nm")
        row = {"topo": f"**{t['id']}**<br><small>{p['note']}</small>", "mcr": f"{fx(a['mos180'], 1)} / {fx(a['cap180'], 1)} / {fx(a['res180'], 1)}",
               "fcap": p["f_cap"], "frc": p["f_rc"], "fcont": p["f_cont"]}
        for nk in keys:
            x = node_area(c, t["id"], nk)
            row[nk] = f"**{fx(x['total_um2'], 3 if x['total_um2'] < 1.0 else 1)} µm²**<br><small>{fx(x['ge_active'], 1)} GE</small>"
        rows.append(row)
    blocks.append({"type": "table", "title": c.h3("13.3"), "caption": c.card_p("13.3"), "search": False, "rows": rows,
                   "columns": [T("topo", "Topology"), T("mcr", "180nm MOS / Cap / Res (µm²)"), {"key": "fcap", "label": "f_cap (Energy)", "digits": 3},
                               {"key": "frc", "label": "f_RC (Delay)", "digits": 3}, {"key": "fcont", "label": "f_cont (low-V contention)", "digits": 3}] +
                              [T(nk, f"{nk} Area (µm²)<br><small>& Gate-Equiv (GE)</small>") for nk in keys]})
    return {"blocks": [{"type": "section", "title": c.h2("sec-appendix"), "intro": c.sec_desc("sec-appendix"), "blocks": blocks}]}


# ===================================================================================== op-region / split / waves / vss2d / pvt / mc / insights
def p_opregion(c):
    tids = [t["id"] for t in c.topos]
    tabs = [{"label": f"{t['id']} — {t['name']}", "key": t["id"], "blocks": [c.opregion_tabs(t["id"])]} for t in c.topos]
    raw = alts(lambda st: table_src(c, f"data/opr/{st}_grid.json", "All 770 shared-ground grid simulations", [
        {"key": "topo", "label": "Topology", "type": "text"}, {"key": "vddl", "label": "VDDL", "unit": "V", "si": True},
        {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}] + c.L.CORNER_COLS[2:],
        [dict(c.L.corner_row(r), topo=r["topology"], vddl=r["vddl"], vdd=r["vddh"]) for r in c.S[st].get("shared_grid") or []], page_size=100,
        vdd_filter=True)
        if c.S[st].get("shared_grid") else None, "oprraw")
    return {"blocks": [{"type": "section", "title": c.h2("sec-opregion"), "intro": c.sec_desc("sec-opregion"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Topology", "id": "opr_topo", "tabs": tabs,
         "default": tids.index("TOP6_ENVELOPE_UNIVERSAL") if "TOP6_ENVELOPE_UNIVERSAL" in tids else 0},
        {"type": "section", "title": "Raw grid records", "collapsed": True, "blocks": raw}]}]}


def split_tables(c):
    doms = []
    for r in c.PRE.get("split_matrix") or []:
        if r["domain_label"] not in [d[0] for d in doms]:
            doms.append((r["domain_label"], r.get("domain_title") or r["domain_label"],
                         f"[{fx(r['vssl'], 1)}, {fx(r['vddl'], 1)}V] → [{fx(r['vssh'], 1)}, {fx(r['vddh'], 1)}V]", r["vddh"]))
    modes = [("status_tpd", "Pass/Fail + Propagation Delay tpd (ps)"), ("tplh_tphl", "Turn-On / Turn-Off Delay (tpLH / tpHL ps)"),
             ("p_stat_nw", "Static Power Pstat (nW)"), ("e_dyn_fj", "Dynamic Energy Edyn (fJ)")]
    tabs = []
    for mode, lab in modes:
        def tab(st, mode=mode):
            rows = []
            for did, title, rails, vh in doms:
                row = {"dom": f"**{title.replace('->', '→')}**", "rails": rails, "vdd": vh}
                for t in c.topos:
                    it = c.ix[st]["split_matrix"].get((t["id"], did))
                    if not it:
                        row[t["id"]] = "N/A" if st == "full" else "—"
                    elif not it["pass"]:
                        row[t["id"]] = {"v": "FAIL", "s": "bad"}
                    elif mode == "status_tpd":
                        row[t["id"]] = {"v": f"**PASS**<br>{fx(it.get('tpd_ps'), 0)} ps", "s": "good"}
                    elif mode == "tplh_tphl":
                        row[t["id"]] = {"v": f"{fx(it.get('tplh_ps'), 0)} /<br>{fx(it.get('tphl_ps'), 0)} ps", "s": "good"}
                    elif mode == "p_stat_nw":
                        row[t["id"]] = {"v": f"{fx(it.get('p_stat_nw'), 1)} nW", "s": "good"}
                    else:
                        row[t["id"]] = {"v": f"{fx(it.get('e_dyn_fj'), 1)} fJ", "s": "good"}
                rows.append(row)
            cols = [{"key": "dom", "label": "Split / Non-Overlapping Domain", "md": True, "type": "text"}, {"key": "rails", "label": "Rails", "type": "text"},
                    {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}]
            cols += [{"key": t["id"], "label": t["short_name"].replace(" ", "<br>", 1), "type": "text", "md": True, "title": t["id"]} for t in c.topos]
            return {"type": "table", "rows": rows, "columns": cols, "search": False, "title": lab, "vdd_filter": True}
        tabs.append({"label": lab, "key": mode, "blocks": alts(tab, f"split-{mode}")})
    raw = alts(lambda st: table_src(c, f"data/split/{st}_all.json", "All 176 split-rail simulations", [
        {"key": "topo", "label": "Topology", "type": "text"}, {"key": "dom", "label": "Domain", "type": "text"},
        {"key": "vssl", "label": "VSSL", "unit": "V", "si": True}, {"key": "vddl", "label": "VDDL", "unit": "V", "si": True},
        {"key": "vssh", "label": "VSSH", "unit": "V", "si": True}, {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}] + c.L.CORNER_COLS[2:],
        [dict(c.L.corner_row(r), topo=r["topology"], dom=(r.get("domain_title") or r["domain_label"]).replace("->", "→"),
              vssl=r["vssl"], vddl=r["vddl"], vssh=r["vssh"], vdd=r["vddh"]) for r in c.S[st].get("split_matrix") or []], page_size=100, vdd_filter=True), "splitraw")
    return tabs, raw


def p_splitrail(c):
    tabs, raw = split_tables(c)
    return {"blocks": [{"type": "section", "title": c.h2("sec-splitrail"), "intro": c.sec_desc("sec-splitrail"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Cell Metric", "id": "split_metric", "tabs": tabs},
        {"type": "section", "title": "Long-form table with every metric", "collapsed": True, "blocks": raw}]}]}


def p_waveforms(c):
    L = c.L
    tids = [t["id"] for t in c.topos]
    tabs = []
    for t in c.topos:
        inner = []
        for did, lab, _ in L.FLAG:
            b = c.wave_blocks(t["id"], did, f"{t['id']} — {did} transient response")
            if f"{t['id']}.{did}" in c.design_ids:
                b.append({"type": "markdown", "text": f"[Open the design page of {t['id']} · {lab} →](#/ls/{t['id']}.{did})"})
            inner.append({"label": lab, "key": did, "vdd": c.doms[did]["vddh"] if did in c.doms else None, "blocks": b})
        tabs.append({"label": f"{t['id']} ({t['short_name']})", "key": t["id"],
                     "blocks": [{"type": "tabs", "style": "select", "label": "Voltage Domain", "id": "wave_dom", "tabs": inner, "default": 1}]})
    return {"blocks": [{"type": "section", "title": c.h2("sec-waveforms"), "intro": c.sec_desc("sec-waveforms"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Topology", "id": "wave_topo", "tabs": tabs,
         "default": tids.index("TOP8_AC_HYST_TRIP") if "TOP8_AC_HYST_TRIP" in tids else 0}]}]}


def p_vss2d(c):
    tids = [t["id"] for t in c.topos]
    tabs = [{"label": f"{t['id']} ({t['short_name']})", "key": t["id"], "blocks": [c.vss2d_tabs(t["id"], with_analysis=True)]} for t in c.topos]
    return {"blocks": [{"type": "section", "title": c.h2("sec-vss2d"), "intro": c.sec_desc("sec-vss2d"), "blocks": [
        {"type": "tabs", "style": "select", "label": "Topology", "id": "v2_topo", "tabs": tabs,
         "default": tids.index("TOP8_AC_HYST_TRIP") if "TOP8_AC_HYST_TRIP" in tids else 0}]}]}


def p_pvt(c):
    L = c.L

    def heat(st):
        doms = [d for d, *_ in L.FLAG]
        z, txt = [], []
        for t in c.topos:
            zr, tr = [], []
            for d in doms:
                p = c.ix[st]["pvt_summary"].get((t["id"], d))
                zr.append(p["yield_pct"] if p else None)
                tr.append(f"{p['n_pass']}/{p['n_total']}" if p else "—")
            z.append(zr), txt.append(tr)
        return {"type": "chart", "title": "20-corner PVT yield per topology and flagship domain", "height": 460, "data": [
            {"type": "heatmap", "x": [lab.split(" (")[0] for _, lab, _ in L.FLAG], "y": [t["id"] for t in c.topos], "z": z, "text": txt,
             "texttemplate": "%{text}", "textfont": {"size": 10, "color": "#111111"}, "zmin": 0, "zmax": 100, "xgap": 2, "ygap": 2,
             "colorscale": [[0, "#ffd7d4"], [0.5, "#fff3c4"], [1, "#b7e4c4"]], "colorbar": {"title": {"text": "yield %"}, "thickness": 12},
             "hovertemplate": "%{y} · %{x}: %{text} corners pass (%{z}%)<extra></extra>"}],
            "layout": {"yaxis": {"autorange": "reversed"}, "margin": {"l": 200, "t": 20}},
            "caption": "Overview chart added by the hub (the old page reserved a chart slot here but did not draw one)."}

    mism = []
    for b in c.PRE.get("pvt_summary") or []:
        nom = c.ix["pre"]["pilot"].get((b["topology"], b["domain_label"]))
        if nom and (b.get("nom_tpd_ps") != nom.get("tpd_ps") or b.get("nom_pstat_nw") != nom.get("p_stat_nw")) and short_tid(b["topology"]) not in mism:
            mism.append(short_tid(b["topology"]))

    def summary(st):
        rows = []
        for b in c.PRE.get("pvt_summary") or []:
            r = c.ix[st]["pvt_summary"].get((b["topology"], b["domain_label"]))
            row = {"design": {"v": f"{b['topology']}.{b['domain_label']}", "t": b["topology"]}, "dom": (b.get("domain_title") or "").replace("->", "→"),
                   "dl": b["domain_label"], "vdd": b["vddh"]}
            if r:
                row.update(y={"v": f"{r['n_pass']}/{r['n_total']} ({fv(r['yield_pct'])}%)", "s": "good" if r["n_pass"] > 0 else "bad"},
                           ntlh=mul(r.get("nom_tplh_ps"), PS), nthl=mul(r.get("nom_tphl_ps"), PS), ntpd=mul(r.get("nom_tpd_ps"), PS),
                           wc=r.get("wc_corner"), wtlh=mul(r.get("wc_tplh_ps"), PS), wthl=mul(r.get("wc_tphl_ps"), PS), wtpd=mul(r.get("wc_tpd_ps"), PS),
                           wtr=mul(r.get("wc_trise_ps"), PS), wtf=mul(r.get("wc_tfall_ps"), PS), nps=mul(r.get("nom_pstat_nw"), NW),
                           wps=mul(r.get("wc_pstat_nw"), NW), wpc=r.get("wc_pstat_corner"), ned=mul(r.get("nom_edyn_fj"), FJ))
            else:
                row["y"] = {"v": "N/A", "s": "muted"}
            rows.append(row)
        return table_src(c, f"data/pvt/{st}_summary.json", "PVT summary (66 topology × domain configurations)", [
            {"key": "design", "label": "Topology", "type": "design"}, {"key": "dom", "label": "Domain", "type": "text"},
            {"key": "dl", "label": "Domain id", "type": "text"}, {"key": "vdd", "label": "VDDH", "unit": "V", "si": True},
            {"key": "y", "label": "20-Corner Yield", "type": "text"},
            {"key": "ntlh", "label": "Nom tpLH", "unit": "s", "si": True, "digits": 5}, {"key": "nthl", "label": "Nom tpHL", "unit": "s", "si": True, "digits": 5},
            {"key": "ntpd", "label": "Nom tpd", "unit": "s", "si": True, "digits": 5},
            {"key": "wc", "label": "Worst-Case Delay Corner", "type": "text"}, {"key": "wtlh", "label": "WC tpLH", "unit": "s", "si": True, "digits": 5},
            {"key": "wthl", "label": "WC tpHL", "unit": "s", "si": True, "digits": 5}, {"key": "wtpd", "label": "WC tpd", "unit": "s", "si": True, "digits": 5},
            {"key": "wtr", "label": "WC t<sub>rise</sub>", "unit": "s", "si": True}, {"key": "wtf", "label": "WC t<sub>fall</sub>", "unit": "s", "si": True},
            {"key": "nps", "label": "Nom Pstat", "unit": "W", "si": True}, {"key": "wps", "label": "WC Pstat", "unit": "W", "si": True},
            {"key": "wpc", "label": "WC Pstat corner", "type": "text"}, {"key": "ned", "label": "Nom Edyn", "unit": "J", "si": True}], rows,
            page_size=100, caption="Filter by typing a topology or domain id (replaces the old topology / domain dropdowns); the global "
                                   "V<sub>DD</sub> option filters on the output rail VDDH. The *Nom* columns are the tt/27 °C point of the "
                                   "PVT run" + (f"; for {', '.join(mism)} it differs from the newer pre-PEX pilot run of Section 1 "
                                                "(the PVT and Monte Carlo runs used an earlier netlist revision)." if mism else "."))

    def corners(st):
        rows = [dict(L.corner_row(r), topo=r["topology"], dom=r["domain_label"], vdd=r["vddh"]) for r in c.S[st].get("pvt_corners") or []]
        return table_src(c, f"data/pvt/{st}_corners.json", "All 1,320 PVT corner simulations",
                         [{"key": "topo", "label": "Topology", "type": "text"}, {"key": "dom", "label": "Domain", "type": "text"},
                          {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}] + L.CORNER_COLS,
                         rows, page_size=100) if rows else None

    return {"blocks": [{"type": "section", "title": c.h2("sec-pvt"), "intro": c.sec_desc("sec-pvt"),
                        "blocks": alts(heat, "pvtheat") + alts(summary, "pvtsum") +
                        [{"type": "section", "title": "Every PVT corner (raw records)", "collapsed": True, "blocks": alts(corners, "pvtcorners")}]}]}


def p_mc(c):
    L = c.L
    base = c.PRE.get("mc_summary") or []
    tabs = []
    for m in base:
        tid, did = m["topology"], m["domain_label"]
        kvs = alts(lambda st: ({"type": "kv", "cols": 4, "items": L.mc_kv(c.ix[st]["mc_summary"][(tid, did)])}
                               if (tid, did) in c.ix[st]["mc_summary"] else None), "mckv")
        def mlab(st):
            x = c.ix[st]["mc_summary"].get((tid, did))
            return (f"{tid} — {did} ({'3σ PASS' if x.get('pass_3sigma') else '3σ FAIL'}, µ+3σ={fx(x.get('tpd_3sigma_ps'), 0)}ps)" if x
                    else f"{tid} — {did} ([N/A] in {dict(STAGES)[st]})")
        tabs.append({"label": mlab("pre"), "labels": {st: mlab(st) for st, _ in STAGES}, "key": f"{tid}.{did}", "vdd": m["vddh"],
                     "blocks": [{"type": "section", "cols": 2, "blocks": c.mc_blocks(tid, did)}] + kvs +
                     [{"type": "markdown", "text": f"[Open the design page {tid} · {did} →](#/ls/{tid}.{did})"}]})

    def summary(st):
        rows = []
        for b in base:
            m = c.ix[st]["mc_summary"].get((b["topology"], b["domain_label"]))
            row = {"design": {"v": f"{b['topology']}.{b['domain_label']}", "t": b["topology"]}, "dom": b["domain_label"], "vdd": b["vddh"]}
            if m:
                row.update(acc=st_cell(m.get("pass_3sigma"), "3σ PASS" if m.get("pass_3sigma") else "3σ FAIL"),
                           y=f"{m['n_pass']}/{m['n_runs']} ({fv(m['yield_pct'])}%)",
                           sw={"v": m.get("swing_3sigma_low_pct"), "s": "good" if (m.get("swing_3sigma_low_pct") or 0) >= 85 else "bad"},
                           mu=mul(m.get("tpd_mean_ps"), PS), sd=mul(m.get("tpd_std_ps"), PS), t3=mul(m.get("tpd_3sigma_ps"), PS),
                           lh3=mul(m.get("tplh_3sigma_ps"), PS), hl3=mul(m.get("tphl_3sigma_ps"), PS), psm=mul(m.get("pstat_mean_nw"), NW),
                           ps3=mul(m.get("pstat_3sigma_nw"), NW), ed=mul(m.get("edyn_mean_fj"), FJ))
            else:
                row["acc"] = {"v": "N/A", "s": "muted"}
            rows.append(row)
        return {"type": "table", "title": c.h3("11.3"), "search": False, "rows": rows, "columns": [
            {"key": "design", "label": "Topology", "type": "design"}, {"key": "dom", "label": "Domain", "type": "text"},
            {"key": "vdd", "label": "VDDH", "unit": "V", "si": True}, {"key": "acc", "label": "3σ Acceptance", "type": "text"}, {"key": "y", "label": "MC Seed Yield", "type": "text"},
            {"key": "sw", "label": "3σ Min Swing (µ−3σ)", "unit": "%", "digits": 4}, {"key": "mu", "label": "tpd Mean µ", "unit": "s", "si": True, "digits": 5},
            {"key": "sd", "label": "tpd Std σ", "unit": "s", "si": True, "digits": 4}, {"key": "t3", "label": "3σ WC tpd µ+3σ", "unit": "s", "si": True, "digits": 5},
            {"key": "lh3", "label": "3σ WC tpLH µ+3σ", "unit": "s", "si": True, "digits": 5}, {"key": "hl3", "label": "3σ WC tpHL µ+3σ", "unit": "s", "si": True, "digits": 5},
            {"key": "psm", "label": "Pstat Mean µ", "unit": "W", "si": True}, {"key": "ps3", "label": "3σ WC Pstat µ+3σ", "unit": "W", "si": True},
            {"key": "ed", "label": "Edyn Mean", "unit": "J", "si": True}]}

    return {"blocks": [{"type": "section", "title": c.h2("sec-mc"), "intro": c.sec_desc("sec-mc"), "blocks": [
        {"type": "section", "title": f"{c.h3('11.1')} · {c.h3('11.2')}", "blocks": [
            {"type": "tabs", "style": "select", "label": "Select Monte Carlo Ensemble", "id": "mc_ens", "tabs": tabs}]}] + alts(summary, "mcsum")}]}


def p_insights(c):
    cards = c.cards("sec-insights")
    return {"blocks": [{"type": "section", "title": c.h2("sec-insights"), "intro": c.sec_desc("sec-insights"), "cols": 2,
                        "blocks": [{"type": "markdown", "title": h, "text": p} for h, p in cards]}]}


# ===================================================================================== per-topology tabs for detail docs
def topology_tabs(c, tid):
    L = c.L
    tabs = [{"label": "2D operating region (VDDL × VDDH)", "blocks": [c.opregion_tabs(tid)]}]

    def split(st):
        rows = []
        for r in c.S[st].get("split_matrix") or []:
            if r["topology"] == tid:
                rows.append(dict(L.corner_row(r), dom=(r.get("domain_title") or r["domain_label"]).replace("->", "→")))
        return {"type": "table", "title": "Split-rail / non-overlapping domain results", "rows": rows, "search": False,
                "columns": [{"key": "dom", "label": "Domain", "type": "text"}] + L.CORNER_COLS[2:]} if rows else None
    tabs.append({"label": "Split-rail matrix", "blocks": alts(split, "split")})
    tabs.append({"label": "VSS1 × VSS2 maps", "blocks": [c.vss2d_tabs(tid)]})

    def ui(st):
        u = UI(c, "180nm", st)
        rows = []
        for v in u.vdds:
            r = u.row(tid, v)
            if r:
                rows.append({"vdd_sd": v, "pass": bool(r.get("pass")), "swing": r.get("swing_pct"), "psw": mul(r.get("p_sw_nw"), NW),
                             "pswx": r.get("psw_mult"), "tplh": mul(r.get("tplh_ps"), PS), "risex": r.get("rise_mult"),
                             "tphl": mul(r.get("tphl_ps"), PS), "fallx": r.get("fall_mult"), "pstat": mul(r.get("p_stat_nw"), NW),
                             "ptotx": r.get("ptot_mult")})
        return {"type": "table", "title": "Single-domain 0→VDD comparison vs. the unit-sized inverter (native 180 nm)", "rows": rows, "search": False,
                "columns": [{"key": "vdd_sd", "label": "VDD", "unit": "V", "si": True}, {"key": "pass", "label": "Pass", "type": "status"},
                            {"key": "swing", "label": "Swing", "unit": "%", "digits": 4}, {"key": "psw", "label": "Psw", "unit": "W", "si": True},
                            {"key": "pswx", "label": "Psw ×"}, {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4},
                            {"key": "risex", "label": "Rise ×"}, {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4},
                            {"key": "fallx", "label": "Fall ×"}, {"key": "pstat", "label": "Pstat", "unit": "W", "si": True},
                            {"key": "ptotx", "label": "Ptot ×"}]} if rows else None
    tabs.append({"label": "vs unit inverter", "blocks": alts(ui, "ui")})
    D = c.PRE.get("dse") or {}
    crow = []
    for r in D.get("records") or []:
        if r["topology"] == tid and r.get("card_target"):
            crow.append({"dom": r["domain"], "card": r["card_target"], "knobs": f"{r['s_drv']}·{r['s_latch']}·{r['s_res']}·{r['s_cap']}·{r['s_out']}",
                         "pass": bool(r["pass"]), "tpd": mul(r.get("tpd_ps"), PS), "edyn": mul(r.get("e_dyn_fj"), FJ), "psw": mul(r.get("p_sw_nw"), NW),
                         "pstat": mul(r.get("p_stat_nw"), NW), "fom": r.get("fom"), "area": r.get("area_um2"),
                         "pvt": "robust" if r.get("pvt_robust") else ("corner fail" if r.get("pvt_checked") else "—"), "wc": mul(r.get("wc_tpd_ps"), PS)})
    if crow:
        tabs.append({"label": "DSE sizing cards", "blocks": [{"type": "table", "stage": "pre", "alt": "dsecards", "title": "Delivered ULP / BAL / HS sizing cards",
                     "rows": crow, "search": False, "columns": [
                         {"key": "dom", "label": "DSE domain", "type": "text"}, {"key": "card", "label": "Card", "type": "text"},
                         {"key": "knobs", "label": "drv·latch·res·cap·out", "type": "text"}, {"key": "pass", "label": "Pass", "type": "status"},
                         {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4}, {"key": "edyn", "label": "Edyn", "unit": "J", "si": True},
                         {"key": "psw", "label": "Psw", "unit": "W", "si": True}, {"key": "pstat", "label": "Pstat", "unit": "W", "si": True},
                         {"key": "fom", "label": "FoM"}, {"key": "area", "label": "Area", "unit": "µm²"}, {"key": "pvt", "label": "PVT", "type": "text"},
                         {"key": "wc", "label": "WC tpd", "unit": "s", "si": True, "digits": 4}],
                     "caption": "Design-space exploration (pre-PEX only); see the *Design space* page for the full clouds."}]})
    if tid in [x[0] for x in c.HVT_TOPOS]:
        tabs.append({"label": "HV grid (VDDL × VDDH)", "blocks": c.hvgrid_blocks(tid)})
        wt = c.hvwave_tabs(tid)
        if wt:
            tabs.append({"label": "HV waveforms", "blocks": [wt]})
    for t in tabs:
        t.setdefault("key", re.sub(r"[^a-z0-9]+", "_", t["label"].lower()).strip("_"))
    return {"type": "tabs", "id": "xr", "tabs": tabs}


# ===================================================================================== registry
PAGES = [("overview", "Portfolio & benchmark", p_overview), ("explore", "Design space", p_explore),
         ("topologies", "Schematics & layouts", p_topologies), ("hvt", "HV-tolerant", p_hvt), ("unitinv", "vs unit inverter", p_unitinv),
         ("opregion", "Operating regions", p_opregion), ("splitrail", "Split-rail matrix", p_splitrail),
         ("waveforms", "Waveforms", p_waveforms), ("vss2d", "VSS1×VSS2 maps", p_vss2d), ("pvt", "PVT corners", p_pvt),
         ("mc", "Monte Carlo", p_mc), ("insights", "Circuit insights", p_insights), ("appendix", "Scaling appendix", p_appendix)]


def build_pages(c):
    out = []
    for pid, title, fn in PAGES:
        doc = fn(c)
        if not doc.get("blocks"):
            continue
        out.append({"id": pid, "title": title, "src": c.o.put(f"pages/{pid}.json", doc)})
    return out
