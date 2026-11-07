#!/usr/bin/env python3
"""Bootstrap hub adapter for ls-gen-gemini4 (level shifters) — schema aicdb-hub/2.

usage: ls.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/):
  * report_data.json  — two parallel result sets, "pre" (schematic netlist) and "pex" (Magic RC
                        extraction of the complete gLayout cell, i.e. hub stage "full");
  * index.html        — static prose of the old single-page report (section intros, insight and
                        appendix cards), converted to markdown;
  * assets/schem_*.svg, assets/layout_*.png — schematics and gLayout renders (hosted as-is; the
                        repo publishes no GDS, so the PNG renders are the only layout visuals).
Writes OUT_DIR/component.json plus pages/, designs/ and data/ under OUT_DIR.

A design = one topology operated in one voltage-domain crossing:
  * 11 topologies x 6 flagship crossings (nominal tt/27 °C pilot @ 10 MHz / 20 fF, 20-corner PVT,
    80-run Monte Carlo where the repo ran it);
  * + 6 HV-tolerant operating points of TOP9-11 (25 MHz, 15-corner PVT with the 1.8 V oxide check).
`vdd` is the OUTPUT-domain top rail VDDH. All crossings of one topology share one cell.
Everything else of the old report (design-space exploration, HV explorer, unit-inverter comparison
and its node-scaling model, 2-D operating regions, split-rail matrix, waveform/VSS2D viewers,
PVT/MC tables, insights, appendix) is reproduced as pages (see ls_pages.py).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ls_lib import (FJ, NW, PS, UW, Keep, Out, band_scale, blue_color, custom_scale, delay_color, fx,  # noqa: E402
                    heat_trace, mul, norm, parse_html, to_md, wave_fig)

STAGES = (("pre", "Pre-PEX"), ("full", "Post-PEX"))
FLAG = [  # flagship crossings in report order: id, label (waveform viewer), short axis label
    ("shared_1v2_to_3v3", "0-1.2V → 0-3.3V (Core to IO)", "0–1.2 → 0–3.3 V"),
    ("subvt_0v6_to_3v3", "0-0.6V → 0-3.3V (Subthreshold Step-Up)", "0–0.6 → 0–3.3 V"),
    ("split_0_1v2_to_1v0_1v8", "0-1.2V → 1.0-1.8V (Split Forward)", "0–1.2 → 1.0–1.8 V"),
    ("split_1v0_1v8_to_0_1v2", "1.0-1.8V → 0-1.2V (Split Reverse)", "1.0–1.8 → 0–1.2 V"),
    ("disjoint_up_0_1v0_to_1v8_3v3", "0-1.0V → 1.8-3.3V (Disjoint Up)", "0–1.0 → 1.8–3.3 V"),
    ("disjoint_dn_1v8_3v3_to_0_1v0", "1.8-3.3V → 0-1.0V (Disjoint Down)", "1.8–3.3 → 0–1.0 V"),
]
KIND = {"shared": "Shared GND", "subvt": "Sub-Vt input", "split": "Split rail", "disjoint": "Disjoint rails",
        "hvt": "HV (oxide < 1.8 V)"}


def fv(v):
    return f"{v:g}"


def hv_id(dl):
    return "hv_" + dl.replace(".", "v").replace("V_to_", "_to_").rstrip("V")


class Ctx:
    """Shared state: datasets, lookup tables, prose from index.html and the hosted data files."""

    def __init__(self, docs: Path, out: Path):
        self.docs, self.o = docs, Out(out)
        self.data = json.loads((docs / "report_data.json").read_text())
        self.S = {"pre": self.data["pre"], "full": self.data["pex"]}
        self.PRE = self.S["pre"]
        self.topos = self.PRE["topologies"]
        self.T = {t["id"]: t for t in self.topos}
        src = (docs / "index.html").read_text(errors="replace")
        cut = src.find("<script>")
        self.dom = parse_html(src[:cut if cut > 0 else len(src)])
        self.ix = {}
        for st, S in self.S.items():
            ix = self.ix[st] = {}
            for k in ("pilot", "pvt_summary", "mc_summary", "split_matrix"):
                ix[k] = {(r["topology"], r["domain_label"]): r for r in S.get(k) or []}
            ix["hvt_pvt"] = {(r["topology"], r["domain_label"]): r for r in S.get("hvt_pvt_summary") or []}
        self.memo = {}
        self.design_ids = set()

    # ---------------------------------------------------------------- prose from index.html
    def sec(self, sid):
        return self.dom.find(id=sid)

    def sec_desc(self, sid):
        s = self.sec(sid)
        p = s.find("p", cls="sec-desc") if s else None
        return to_md(p) if p else ""

    def sec_desc_by_id(self, eid):
        n = self.dom.find(id=eid)
        return to_md(n) if n else ""

    def h2(self, sid):
        s = self.sec(sid)
        h = s.find("h2") if s else None
        if not h:
            return ""
        for c in list(h.children):
            if not isinstance(c, str) and "badge" in c.cls():
                h.children.remove(c)
        return to_md(h)

    def h3(self, prefix):
        for h in self.dom.find_all("h3"):
            if h.text().strip().startswith(prefix):
                return to_md(h)
        return prefix

    def card_p(self, prefix):
        """First <p> after the h3 starting with prefix, inside the same container."""
        for h in self.dom.find_all("h3"):
            if h.text().strip().startswith(prefix):
                par = h.parent
                seen = False
                for c in par.iter():
                    if c is h:
                        seen = True
                    elif seen and c.tag == "p":
                        return to_md(c)
        return ""

    def cards(self, sid):
        """insight-card blocks (h4 + p) of a section."""
        s = self.sec(sid)
        out = []
        for c in s.find_all("div", cls="insight-card") if s else []:
            h, p = c.find("h4"), c.find("p")
            out.append((to_md(h) if h else "", to_md(p) if p else ""))
        return out

    # ---------------------------------------------------------------- shared hosted figures
    def wave(self, st, tid, did):
        """Section-8 waveform figure (+ metrics line) for one topology/crossing at one stage."""
        key = ("wave", st, tid, did)
        if key in self.memo:
            return self.memo[key]
        pv = self.ix[st]["pvt_summary"].get((tid, did))
        pl = self.ix[st]["pilot"].get((tid, did))
        waves = pv["waves"] if pv and pv.get("waves") else ({"pilot": pl["waveform"]} if pl and pl.get("waveform") else {})
        ref = pv or pl
        res = (None, None)
        if ref:
            fig = wave_fig(waves, ref["vssl"], ref["vddl"], ref["vssh"], ref["vddh"],
                           f"{tid} — {did} Transient Response ({dict(STAGES)[st]})")
            src = self.o.put(f"data/wave/{st}/{tid}__{did}.json", fig, 4) if fig else None
            if pv:
                note = (f"PVT Corner Yield: **{pv['n_pass']}/{pv['n_total']} ({fv(pv['yield_pct'])}%)** | "
                        f"Nominal (tt 27°C): tpLH={fx(pv.get('nom_tplh_ps'))}ps, tpHL={fx(pv.get('nom_tphl_ps'))}ps, "
                        f"Pstat={fx(pv.get('nom_pstat_nw'))}nW | Worst-Case Delay ({pv.get('wc_corner') or '—'}): "
                        f"tpLH={fx(pv.get('wc_tplh_ps'))}ps, tpHL={fx(pv.get('wc_tphl_ps'))}ps, "
                        f"tr={fx(pv.get('wc_trise_ps'))}ps, tf={fx(pv.get('wc_tfall_ps'))}ps")
            else:
                note = (f"Nominal (tt 27°C): Pass={str(pl['pass']).lower()} | tpLH={fx(pl.get('tplh_ps'))}ps | "
                        f"tpHL={fx(pl.get('tphl_ps'))}ps | Pstat={fx(pl.get('p_stat_nw'))}nW | Edyn={fx(pl.get('e_dyn_fj'))}fJ")
            res = (src, note)
        self.memo[key] = res
        return res

    def wave_blocks(self, tid, did, title="Transient waveforms (VIN / VOUT)"):
        blocks = []
        for st, lab in STAGES:
            src, note = self.wave(st, tid, did)
            if src:
                blocks.append({"type": "chart", "stage": st, "alt": f"w-{tid}-{did}", "title": title, "src": src,
                               "height": 440,
                               "caption": "Dashed grey: VIN · solid: VOUT per PVT corner (blue = tt 27 °C, red = ss −40 °C, "
                                          "amber = ff 125 °C, thinner lines = the other six corners) · dotted: output rails."})
                blocks.append({"type": "note", "stage": st, "alt": f"wn-{tid}-{did}", "tone": "muted", "text": note})
        return blocks

    OPR_METRICS = [("swing_ratio", "Output Swing Ratio (%) & Pass Boundary"),
                   ("tpd_ps", "Mean Propagation Delay tpd (ps)"), ("tplh_ps", "Turn-On Delay tpLH (ps)"),
                   ("tphl_ps", "Turn-Off Delay tpHL (ps)"), ("p_stat_nw", "Static Power Consumption Pstat (nW)"),
                   ("e_dyn_fj", "Dynamic Energy per Transition Edyn (fJ)")]

    def opregion(self, st, tid, metric):
        """Section-6 VDDL x VDDH heatmap (shared ground) for one topology / metric / stage."""
        key = ("opr", st, tid, metric)
        if key in self.memo:
            return self.memo[key]
        vddls = [0.55, 0.65, 0.75, 0.85, 1.0, 1.2, 1.5, 1.8, 2.5, 3.3]
        vddhs = [0.8, 1.0, 1.2, 1.5, 1.8, 2.5, 3.3]
        sub = [r for r in self.S[st].get("shared_grid") or [] if r["topology"] == tid]
        if not sub:
            self.memo[key] = None
            return None
        cell = {}
        for r in sub:
            cell[(round(r["vddl"], 2), round(r["vddh"], 2))] = r
        vals = [r[metric] for r in sub if r["pass"] and r.get(metric) is not None and metric != "swing_ratio"]
        lo, hi = (min(vals), max(vals)) if vals else (1, 1)
        logm = metric != "swing_ratio" and lo > 0 and hi / max(lo, 1e-30) > 20
        z, txt, hov = [], [], []
        for vh in vddhs:
            zr, tr, hr = [], [], []
            for vl in vddls:
                r = cell.get((vl, vh))
                if not r:
                    zr.append(None), tr.append("—"), hr.append(f"VDDL={vl}V, VDDH={vh}V: not simulated")
                    continue
                ok = r["pass"]
                if metric == "swing_ratio":
                    sw = (r.get("swing_ratio") or 0) * 100
                    zr.append(1 if ok else -2)
                    tr.append(f"{'✓' if ok else '✗'} {fx(sw, 0)}%")
                else:
                    v = r.get(metric)
                    if not ok or v is None:
                        zr.append(-2), tr.append("FAIL")
                    else:
                        zr.append(norm(v, lo, hi, logm))
                        tr.append((f"{fx(v / 1000, 1)}µW" if v > 9999 else fx(v, 1)) if metric == "p_stat_nw" else fx(v, 0))
                hr.append(f"VDDL={fv(vl)}V, VDDH={fv(vh)}V | Pass={str(ok).lower()} | tpd={fx(r.get('tpd_ps'))}ps | "
                          f"tpLH={fx(r.get('tplh_ps'))}ps | tpHL={fx(r.get('tphl_ps'))}ps | Pstat={fx(r.get('p_stat_nw'))}nW | "
                          f"Edyn={fx(r.get('e_dyn_fj'))}fJ | swing={fx((r.get('swing_ratio') or 0) * 100, 1)}%")
            z.append(zr), txt.append(tr), hov.append(hr)
        scale = band_scale("#ffd7d4", "#fff3c4", "#dcf3e2", "#dcf3e2") if metric == "swing_ratio" else \
            band_scale("#ffd7d4", "#fff3c4", "#e3eefb", "#7fb0ea", "#b3cff2")
        tr = heat_trace([f"{v:.2f}V" for v in vddls], [f"{v:.2f}V" for v in vddhs], z, txt, hov, scale)
        name = dict(self.OPR_METRICS)[metric]
        fig = {"data": [tr], "layout": {
            "title": {"text": f"{tid} — {name} ({dict(STAGES)[st]})", "font": {"size": 13}, "x": 0.01},
            "xaxis": {"title": {"text": "Input rail VDDL (V) [VSSL = VSSH = 0]"}, "type": "category"},
            "yaxis": {"title": {"text": "Output rail VDDH (V)"}, "type": "category"},
            "margin": {"t": 40}}}
        cap = ("Green ✓ = valid output (swing ≥ 85 %), red ✗ = fail." if metric == "swing_ratio" else
               f"Passing cells shaded light → dark blue with increasing value ({'log' if logm else 'linear'} scale); "
               "red = output does not switch (FAIL).")
        res = (self.o.put(f"data/opr/{st}/{tid}__{metric}.json", fig, 4), cap)
        self.memo[key] = res
        return res

    def opregion_tabs(self, tid):
        tabs = []
        for m, lab in self.OPR_METRICS:
            blocks = []
            for st, _ in STAGES:
                r = self.opregion(st, tid, m)
                if r:
                    blocks.append({"type": "chart", "stage": st, "alt": f"opr-{tid}-{m}",
                                   "src": r[0], "height": 430, "caption": r[1]})
            tabs.append({"label": lab, "key": m, "blocks": blocks})
        return {"type": "tabs", "style": "select", "label": "Metric", "id": "opr_metric", "tabs": tabs}

    VSS_X = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.5]
    VSS_SPAN = [0.55, 0.65, 0.80, 1.00, 1.20, 1.50, 1.80, 2.50, 3.30]
    VSS_MODES = [("vss2d_shifted_0v8", "Shifted 0.8V Domains (ΔV1 = ΔV2 = 0.8V, Arbitrary VSS1 × VSS2 ∈ [0.0V, 2.5V] → "
                                       "[VSS1, VSS1+0.8V] × [VSS2, VSS2+0.8V])"),
                 ("vss2d_span_0v8", "Fixed Top Rail VDD1 = VDD2 = 0.8V, Arbitrary VSS1 × VSS2 → 2D Span Space "
                                    "(VDD1−VSS1) × (VDD2−VSS2) ∈ [0.55V, 3.30V]²")]

    def vss2d(self, st, tid, mode):
        """Section-9: four VSS1 x VSS2 maps (tpLH, tpHL, Psw/Edyn, Ptot/Pstat) as 2x2 subplots."""
        key = ("vss", st, tid, mode)
        if key in self.memo:
            return self.memo[key]
        shifted = mode == "vss2d_shifted_0v8"
        items = [r for r in self.S[st].get("vss2d") or [] if r["topology"] == tid and r["sweep_type"] == mode]
        xs = self.VSS_X if shifted else self.VSS_SPAN
        if shifted:
            xl = [f"{v:.1f}-{v + 0.8:.1f}V" for v in xs]
            yl = [f"{v:.1f}..{v + 0.8:.1f}V" for v in xs]
        else:
            xl = [f"{v:.2f}V" for v in xs]
            yl = [f"{v:.2f}V ({0.8 - v:.2f}V)" for v in xs]
        find = {}
        for r in items:
            find[(round(r["vss1"], 2), round(r["vss2"], 2)) if shifted else (round(r["dv1"], 2), round(r["dv2"], 2))] = r

        def getv(r, k):
            if k == "p_sw_nw":
                return None if r.get("e_dyn_fj") is None else r["e_dyn_fj"] * 20.0
            if k == "p_tot_nw":
                return None if r.get("p_tot_uw") is None else r["p_tot_uw"] * 1000.0
            return r.get(k)

        plots = [("tplh_ps", "delay", f"Plot 1: Rising-Edge Logical Delay tpLH (50% Cross Point) — {tid}"),
                 ("tphl_ps", "delay", f"Plot 2: Falling-Edge Logical Delay tpHL (50% Cross Point) — {tid}"),
                 ("p_sw_nw", "psw", f"Plot 3: Dynamic Switching Power Psw & Energy Edyn (@10MHz) — {tid}"),
                 ("p_tot_nw", "ptot", f"Plot 4: Total Active Power Ptot & Static Leakage Pstat (@10MHz) — {tid}")]
        scale = [[0, "#ffd7d4"], [0.3, "#ffd7d4"], [0.3, "#f0efec"], [0.64, "#f0efec"]] + \
            [[0.665 + 0.335 * p, c] for p, c in custom_scale(delay_color, 9)]
        traces, ann = [], []
        for i, (k, unit, title) in enumerate(plots):
            ok = [getv(r, k) for r in items if r["pass"] and getv(r, k) is not None]
            lo, hi = (min(ok), max(ok)) if ok else (1, 1000)
            z, txt, hov = [], [], []
            for yv in xs:
                zr, tr, hr = [], [], []
                for xv in xs:
                    r = find.get((round(xv, 2), round(yv, 2)))
                    if not r:
                        zr.append(-1), tr.append("—"), hr.append("not simulated")
                        continue
                    v = getv(r, k)
                    if r["pass"] and v is not None:
                        zr.append(max(0.0, min(1.0, (v - lo) / max(1, hi - lo))))
                        if unit == "delay":
                            a = f"{fx(v / 1000, 2)}ns" if v >= 1000 else f"{fx(v, 0)}ps"
                            b = f"{fx((r.get('swing_ratio') or 0) * 100, 0)}%"
                        else:
                            a = f"{fx(v / 1000, 2)}µW" if v >= 1000 else f"{fx(v, 0)}nW"
                            ps_ = r.get("p_stat_nw")
                            b = f"{fx(r.get('e_dyn_fj'))}fJ" if unit == "psw" else \
                                ("st:" + (f"{fx(ps_ / 1000, 1)}µW" if ps_ is not None and ps_ >= 1000 else f"{fx(ps_)}nW"))
                        tr.append(f"{a}<br>{b}")
                    else:
                        zr.append(-2)
                        tr.append("FAIL" + (f"<br>{fx(r['swing_ratio'] * 100, 0)}%" if r.get("swing_ratio") is not None else ""))
                    psw = None if r.get("e_dyn_fj") is None else r["e_dyn_fj"] * 20
                    hr.append(f"In=[{fx(r['vssl'], 2)}, {fx(r['vddl'], 2)}V] → Out=[{fx(r['vssh'], 2)}, {fx(r['vddh'], 2)}V] | "
                              f"Pass={str(r['pass']).lower()} | tpLH={fx(r.get('tplh_ps'))}ps | tpHL={fx(r.get('tphl_ps'))}ps | "
                              f"Psw={fx(psw)}nW ({fx(r.get('e_dyn_fj'), 2)}fJ/tr) | Pstat={fx(r.get('p_stat_nw'), 2)}nW | "
                              f"Ptot={fx((r.get('p_tot_uw') or 0) * 1000)}nW")
                z.append(zr), txt.append(tr), hov.append(hr)
            t = heat_trace(xl, yl, z, txt, hov, scale, axis="" if i == 0 else str(i + 1))
            t["textfont"] = {"size": 8, "color": "#111111"}
            traces.append(t)
        xd = [[0, 0.46], [0.54, 1]]
        yd = [[0.555, 0.95], [0, 0.395]]
        lay = {"margin": {"t": 30, "l": 100, "b": 90}, "height": 1150, "showlegend": False}
        xt = "Input Domain [VSS1, VDD1] where VDD1 − VSS1 = 0.8V" if shifted else "Input Domain Span VDD1 − VSS1 (with VDD1 = 0.8V)"
        yt = "Output Domain [VSS2, VDD2] (VDD2 − VSS2 = 0.8V)" if shifted else "Output Span VDD2 − VSS2 (VDD2 = 0.8V)"
        sub = ["Both domains have local VDD=0.8V; axes sweep VSS1 & VSS2 ∈ [0.0V, 2.5V]" if shifted else
               "Fixed VDD1=VDD2=0.8V; axes sweep (VDD1−VSS1) × (VDD2−VSS2)"] * 2 + \
              ["Psw = 2·f·Edyn (top label) & per-transition Edyn in fJ (bottom label)",
               "Ptot = Psw + Pstat (top label) & static power Pstat (bottom label)"]
        for i in range(4):
            sfx = "" if i == 0 else str(i + 1)
            lay[f"xaxis{sfx}"] = {"domain": xd[i % 2], "anchor": f"y{sfx}", "type": "category", "tickangle": -22,
                                  "tickfont": {"size": 9}, "title": {"text": xt, "font": {"size": 11}}}
            lay[f"yaxis{sfx}"] = {"domain": yd[i // 2], "anchor": f"x{sfx}", "type": "category",
                                  "tickfont": {"size": 9}, "title": {"text": yt, "font": {"size": 11}}}
            ann.append({"xref": "paper", "yref": "paper", "x": xd[i % 2][0], "y": yd[i // 2][1] + 0.008, "xanchor": "left",
                        "yanchor": "bottom", "showarrow": False, "align": "left",
                        "text": f"<b>{plots[i][2]}</b><br><span style='font-size:10px'>{sub[i]}</span>", "font": {"size": 12}})
        lay["annotations"] = ann
        src = self.o.put(f"data/vss2d/{st}/{tid}__{mode}.json", {"data": traces, "layout": lay}, 4) if items else None
        # metrics bar
        passes = [r for r in items if r["pass"]]
        rises = [r["tplh_ps"] for r in passes if r.get("tplh_ps") is not None]
        falls = [r["tphl_ps"] for r in passes if r.get("tphl_ps") is not None]
        psws = [r["e_dyn_fj"] * 20 for r in passes if r.get("e_dyn_fj") is not None]
        eds = [r["e_dyn_fj"] for r in passes if r.get("e_dyn_fj") is not None]
        mm = lambda a: (min(a), max(a)) if a else (None, None)  # noqa: E731
        (r0, r1), (f0, f1), (p0, p1), (e0, e1) = mm(rises), mm(falls), mm(psws), mm(eds)
        cov = f"{passes.__len__()} / {len(items)} ({fx(100 * len(passes) / len(items), 1) if items else 0}%)"
        note = (f"2D Grid Pass Coverage: **{cov}** | 50% Rising Delay tpLH: **{fx(r0)} – {fx(r1)} ps** | "
                f"50% Falling Delay tpHL: **{fx(f0)} – {fx(f1)} ps** | Switching Power Psw (@10MHz): "
                f"**{fx(p0)} – {fx(p1)} nW** ({fx(e0)} – {fx(e1)} fJ/transition)") if items else None
        res = (src, note)
        self.memo[key] = res
        return res

    def vss2d_analysis(self, tid):
        return (f"**2D Switching Power & Delay Scaling Analysis ({tid}):**\n"
                "• **Capacitive Charging vs. Crowbar Contention Component:** Total dynamic switching power at `f = 10 MHz` is governed by "
                "`Psw = 2·f·Edyn = f·(C_L·ΔV2² + C_in·ΔV1² + E_crowbar)`. For a `20 fF` load with `ΔV2 = 0.8V`, the fundamental "
                "load-charging floor is `f·C_L·(0.8V)² = 128 nW` (`6.4 fJ/transition`).\n"
                "• **Impact of Offset Voltage `|VSS2 − VSS1|` in Shifted 0.8V Space:** In pure AC-coupled topologies "
                "(`TOP7_AC_DIFF_KEEPER`, `TOP8_AC_HYST_TRIP`), series MIM coupling capacitors block DC rail offsets completely, so "
                "switching power remains nearly invariant across the entire 2D `VSS1 × VSS2` plane (including wide-gap non-overlapping "
                "corners like `0.0–0.8V ↔ 2.5–3.3V`). In DC-coupled envelope/cascode architectures (`TOP6_ENVELOPE_UNIVERSAL`, "
                "`TOP3_NVT_CASC`, `TOP4_CAP_BOOST`), internal swing spans the envelope `VTOP − VBOT = max(VDD1,VDD2) − min(VSS1,VSS2)`, "
                "causing `Psw` and `Edyn` to scale quadratically with the total rail separation `|VSS2 − VSS1| + 0.8V`.\n"
                "• **Impact of Span Scaling `(VDD1−VSS1) × (VDD2−VSS2)`:** As input span `VDD1−VSS1` drops toward `0.55V–0.65V` "
                "(near-threshold regime), conventional latches suffer prolonged crowbar current during slow transitions, whereas "
                "split-node isolation (`TOP3/TOP4/TOP5`), feedback mirror cut-off (`TOP6`), and unloaded Schmitt sense-amp tripping "
                "(`TOP8`) suppress short-circuit crowbar energy and maintain sub-nanosecond 50% logical delays.")

    def vss2d_tabs(self, tid, with_analysis=False):
        tabs = []
        for mode, lab in self.VSS_MODES:
            blocks = []
            for st, _ in STAGES:
                src, note = self.vss2d(st, tid, mode)
                if src:
                    blocks.append({"type": "chart", "stage": st, "alt": f"v2-{tid}-{mode}", "src": src, "height": 1150,
                                   "caption": "Cell colour: emerald (lowest) → violet → rose (highest) among passing cells of the "
                                              "plot; red = FAIL; hover a cell for rails and all metrics."})
                    blocks.append({"type": "note", "stage": st, "alt": f"v2n-{tid}-{mode}", "tone": "muted", "text": note})
            if with_analysis:
                blocks.append({"type": "note", "tone": "warn", "text": self.vss2d_analysis(tid)})
            tabs.append({"label": lab, "key": mode.replace("vss2d_", ""), "blocks": blocks})
        return {"type": "tabs", "style": "select", "label": "2D Space Mode", "id": "v2_mode", "tabs": tabs}

    def mc(self, st, tid, did):
        """Section-11: tpd histogram with µ / µ+3σ markers and the 6-seed waveform overlay."""
        key = ("mc", st, tid, did)
        if key in self.memo:
            return self.memo[key]
        m = self.ix[st]["mc_summary"].get((tid, did))
        if not m:
            self.memo[key] = None
            return None
        hist = None
        s = m.get("tpd_samples") or []
        if len(s) >= 2:
            lo, mx = min(s), max(s)
            t3 = m["tpd_3sigma_ps"] if m.get("tpd_3sigma_ps") is not None else mx
            hi = max(mx, t3 * 1.02)
            nb, span = 12, max(1.0, hi - lo)
            bins = [0] * nb
            for v in s:
                bins[min(nb - 1, int(((v - lo) / span) * nb))] += 1
            w = span / nb
            xs = [lo + (i + 0.5) * w for i in range(nb)]
            shapes, ann = [], []
            if m.get("tpd_mean_ps") is not None:
                shapes.append({"type": "line", "x0": m["tpd_mean_ps"], "x1": m["tpd_mean_ps"], "yref": "paper", "y0": 0, "y1": 1,
                               "line": {"color": "theme:good", "dash": "dash", "width": 1.8}})
                ann.append({"x": m["tpd_mean_ps"], "yref": "paper", "y": 0.99, "yanchor": "top", "xanchor": "left", "showarrow": False,
                            "text": f"µ={fx(m['tpd_mean_ps'], 0)}ps", "font": {"color": "theme:good", "size": 11}})
            if m.get("tpd_3sigma_ps") is not None:
                shapes.append({"type": "line", "x0": m["tpd_3sigma_ps"], "x1": m["tpd_3sigma_ps"], "yref": "paper", "y0": 0,
                               "y1": 1, "line": {"color": "theme:warn", "dash": "dash", "width": 1.8}})
                ann.append({"x": m["tpd_3sigma_ps"], "yref": "paper", "y": 0.9, "xanchor": "right", "showarrow": False,
                            "text": f"µ+3σ = {fx(m['tpd_3sigma_ps'])} ps", "font": {"color": "theme:warn", "size": 11}})
            hist = {"data": [{"type": "bar", "x": xs, "y": bins, "width": w * 0.85, "text": [str(b) if b else "" for b in bins],
                              "textposition": "outside", "marker": {"color": "#e3eefb", "line": {"color": "#2a78d6", "width": 1}},
                              "name": "MC runs",
                              "hovertemplate": "tpd ≈ %{x:.0f} ps: %{y} runs<extra></extra>"}],
                    "layout": {"title": {"text": f"Propagation Delay Distribution & 3σ Acceptance Bound (N={len(s)})",
                                         "font": {"size": 13}, "x": 0.01},
                               "xaxis": {"title": {"text": f"tpd (ps) — µ={fx(m.get('tpd_mean_ps'))}ps · σ={fx(m.get('tpd_std_ps'))}ps · "
                                                           f"µ+3σ={fx(m.get('tpd_3sigma_ps'))}ps "
                                                           f"({'3σ PASS' if m.get('pass_3sigma') else '3σ FAIL'})"},
                                         "range": [lo - w * 0.5, hi + w * 0.5]},
                               "yaxis": {"title": {"text": "MC runs"}, "range": [0, max(bins) * 1.22 + 0.5]}, "shapes": shapes, "annotations": ann,
                               "showlegend": False, "margin": {"t": 44}}}
            hist = self.o.put(f"data/mc/{st}/{tid}__{did}_hist.json", hist, 5)
        wobj = {f"seed_{sw['seed']}": sw["wave"] for sw in m.get("sample_waves") or []}
        wf = wave_fig(wobj, m["vssl"], m["vddl"], m["vssh"], m["vddh"], f"{tid} ({did}) — 6 MC Seeds Overlay")
        waves = self.o.put(f"data/mc/{st}/{tid}__{did}_seeds.json", wf, 4) if wf else None
        res = {"hist": hist, "seeds": waves, "m": m}
        self.memo[key] = res
        return res

    def mc_blocks(self, tid, did):
        blocks = []
        for st, _ in STAGES:
            r = self.mc(st, tid, did)
            if not r:
                continue
            hb = {"type": "chart", "stage": st, "alt": f"mch-{tid}-{did}", "title": "Propagation delay distribution & 3σ acceptance bound",
                  "src": r["hist"], "height": 360} if r["hist"] else \
                {"type": "note", "stage": st, "alt": f"mch-{tid}-{did}", "tone": "muted", "text": "Insufficient passing samples for histogram."}
            blocks.append(hb)
            if r["seeds"]:
                blocks.append({"type": "chart", "stage": st, "alt": f"mcw-{tid}-{did}", "title": "Monte Carlo transient waveform dispersion (seeds 1..6)",
                               "src": r["seeds"], "height": 400})
        return blocks

    HVT_TOPOS = [
        ("TOP11_HVT_TRIPLE_STACK", "3-Stack Dynamic-Mid-Gate Cascode", "TOP11 — 3-Stack Dynamic-Mid-Gate Cascode (Up to 4.80V!)"),
        ("TOP10_HVT_BOOTSTRAP_DYNAMIC", "2-Stack Cap-Boost Upper-Deck Sense-Latch", "TOP10 — 2-Stack Cap-Boost Sense-Latch (Up to 3.50V, 500MHz!)"),
        ("TOP9_HVT_CASC_DCVS", "2-Stack Cascode-Shielded DCVS + VCL Clamp", "TOP9 — 2-Stack Cascode DCVS + VCL Clamp (Up to 3.30V)"),
        ("TOP4_CAP_BOOST", "1-Stack Flying-Cap Gate-Boost", "TOP4 — 1-Stack Cap-Boost Baseline (Oxide-Safe <= 1.60V)"),
        ("TOP3_NVT_CASC", "1-Stack Native-NMOS Cascode", "TOP3 — 1-Stack Native-NMOS Cascode Baseline (Oxide-Safe <= 1.60V)"),
        ("TOP1_DCVS", "1-Stack Conventional DCVS", "TOP1 — 1-Stack Conventional DCVS Baseline (Oxide-Safe <= 1.60V)"),
    ]
    HV_VDDL = [0.80, 1.00, 1.20, 1.40, 1.60, 1.75]
    HV_VDDH = [1.60, 1.80, 2.00, 2.40, 2.70, 3.00, 3.30, 3.50, 3.80, 4.20, 4.50, 4.80]
    HV_MODES = [("vox", "Plot 1: Peak Gate-Oxide Stress max(|VGS|,|VGD|)",
                 "Green = Logic PASS & |Vox| < 1.80V | Yellow = Overvoltage (>=1.80V) | Red = Logic Fail"),
                ("psw", "Plot 2: Dynamic Switching Power Psw (µW @ 10MHz) & Energy Edyn",
                 "Psw = 2·f·Edyn across the |VGS|,|VGD| < 1.80V safe operating region"),
                ("tplh", "Plot 3: Rising-Edge Logical Delay tpLH (50% Cross Point, ps)",
                 "Measured in the |VGS|,|VGD| < 1.80V safe operating region"),
                ("tphl", "Plot 4: Falling-Edge Logical Delay tpHL (50% Cross Point, ps)",
                 "Measured in the |VGS|,|VGD| < 1.80V safe operating region")]

    def hvgrid(self, st, tid, mode):
        key = ("hvg", st, tid, mode)
        if key in self.memo:
            return self.memo[key]
        items = [r for r in self.S[st].get("hvt_grid") or [] if r["topology"] == tid]
        if not items:
            self.memo[key] = None
            return None
        cell = {(round(r["vddl"], 2), round(r["vddh"], 2)): r for r in items}
        safe = [r for r in items if r["pass"] and r["logic_pass"] and r["oxide_safe_1v8"]]

        def valof(r):
            if mode == "vox":
                return r.get("max_vox_v")
            if mode == "psw":
                return None if r.get("e_dyn_fj") is None else r["e_dyn_fj"] * 0.02
            return r.get("tplh_ps" if mode == "tplh" else "tphl_ps")

        vals = [valof(r) for r in safe if valof(r) is not None]
        lo, hi = (min(vals), max(vals)) if vals else (0, 1)
        z, txt, hov = [], [], []
        for vl in self.HV_VDDL:
            zr, tr, hr = [], [], []
            for vh in self.HV_VDDH:
                r = cell.get((round(vl, 2), round(vh, 2)))
                if not r:
                    zr.append(None), tr.append("—"), hr.append("not simulated")
                    continue
                vox, lp, ox = r.get("max_vox_v"), r.get("logic_pass"), r.get("oxide_safe_1v8")
                if mode == "vox":
                    a = f"{fx(vox, 2)}V" if vox is not None else "—"
                    b = (r.get("worst_mos") or "").split(":")[0][:9]
                    if lp and ox:
                        zr.append(1)
                    elif lp:
                        zr.append(-1)
                        b = "OV >1.8V"
                    else:
                        zr.append(-2)
                        b = "NO SWG"
                else:
                    v = valof(r)
                    if lp and ox and v is not None:
                        zr.append(norm(v, lo, hi))
                        if mode == "psw":
                            a = f"{fx(v, 2)}µW" if v >= 1.0 else f"{fx(v * 1000, 0)}nW"
                            b = f"{fx(r.get('e_dyn_fj'), 0)}fJ"
                        else:
                            a = f"{fx(v / 1000, 2)}ns" if v >= 1000 else f"{fx(v, 0)}ps"
                            b = f"{fx(vox, 2)}V"
                    elif lp and not ox:
                        zr.append(-1)
                        a, b = ">1.8V", (f"{fx(vox, 2)}V" if vox is not None else "")
                    else:
                        zr.append(-2)
                        a, b = "FAIL", (f"{fx(r['swing_ratio'] * 100, 0)}%" if r.get("swing_ratio") is not None else "")
                tr.append(f"{a}<br>{b}" if b else a)
                hr.append(f"VDDL={fx(vl, 2)}V → VDDH={fx(vh, 2)}V | Safe(<1.8V)={str(r['pass']).lower()} | "
                          f"LogicPass={str(lp).lower()} | max(|VGS|,|VGD|)={fx(vox, 3)}V ({r.get('worst_mos') or '?'}) | "
                          f"tpLH={fx(r.get('tplh_ps'))}ps | tpHL={fx(r.get('tphl_ps'))}ps | tpd={fx(r.get('tpd_ps'))}ps | "
                          f"Edyn={fx(r.get('e_dyn_fj'))}fJ")
            z.append(zr), txt.append(tr), hov.append(hr)
        scale = band_scale("#ffd7d4", "#fff3c4", "#dcf3e2", "#dcf3e2") if mode == "vox" else \
            band_scale("#ffd7d4", "#fff3c4", blue_color(0), blue_color(1))
        t = heat_trace([f"{v:.2f}V" for v in self.HV_VDDH], [f"{v:.2f}V" for v in self.HV_VDDL], z, txt, hov, scale)
        t["textfont"] = {"size": 8, "color": "#111111"}
        m = dict((k, (a, b)) for k, a, b in self.HV_MODES)[mode]
        fig = {"data": [t], "layout": {
            "title": {"text": f"{m[0]} — {tid}<br><span style='font-size:10px'>{m[1]}</span>", "font": {"size": 12}, "x": 0.01},
            "xaxis": {"title": {"text": "Output High-Voltage Rail VDDH (V) [VSSH = 0V]"}, "type": "category", "tickangle": -25},
            "yaxis": {"title": {"text": "Input LV Rail VDDL (V)"}, "type": "category"}, "margin": {"t": 56}}}
        src = self.o.put(f"data/hvgrid/{st}/{tid}__{mode}.json", fig, 4)
        maxvh = max((r["vddh"] for r in safe), default=None)
        mint = min(((r.get("tpd_ps") or 99999) for r in safe), default=None)
        maxv = max(((r.get("max_vox_v") or 0) for r in safe), default=None)
        note = (f"Selected Architecture: **{tid}** | Oxide-Safe (<1.80V) Operating Points: **{len(safe)} / {len(items)}** | "
                f"Highest Safe Output Voltage: **{fx(maxvh, 2) + ' V' if maxvh else '—'}** | Fastest Safe Propagation Delay tpd: "
                f"**{fx(mint, 1) + ' ps' if mint and mint < 99999 else '—'}** | Peak Gate-Oxide Stress across Safe Region: "
                f"**{fx(maxv, 3) + ' V (< 1.800 V)' if maxv else '—'}**")
        res = (src, note)
        self.memo[key] = res
        return res

    def hvgrid_blocks(self, tid):
        blocks, notes = [], []
        for mode, *_ in self.HV_MODES:
            for st, _ in STAGES:
                r = self.hvgrid(st, tid, mode)
                if r:
                    blocks.append({"type": "chart", "stage": st, "alt": f"hvg-{tid}-{mode}", "src": r[0], "height": 470})
        for st, _ in STAGES:
            r = self.hvgrid(st, tid, "vox")
            if r:
                notes.append({"type": "note", "stage": st, "alt": f"hvgn-{tid}", "tone": "muted", "text": r[1]})
        return [{"type": "section", "cols": 2, "blocks": blocks}] + notes

    def hvwave(self, st, w):
        key = ("hvw", st, w["topology"], w["vddl"], w["vddh"], w["freq_mhz"])
        if key in self.memo:
            return self.memo[key]
        fig = wave_fig({"pilot": w["waveform"]}, w["vssl"], w["vddl"], w["vssh"], w["vddh"],
                       f"{w['topology']}: {fx(w['vddl'], 1)}V → {fx(w['vddh'], 1)}V @ {w['freq_mhz']}MHz")
        src = self.o.put(f"data/hvwave/{st}/{w['topology']}__{fv(w['vddl'])}_{fv(w['vddh'])}_{w['freq_mhz']}.json", fig, 4) if fig else None
        note = (f"Pass={str(w['pass']).lower()} | max(|VGS|,|VGD|) = **{fx(w.get('max_vox_v'), 3)}V "
                f"{'<' if (w.get('max_vox_v') or 9) < 1.8 else '≥'} 1.80V** ({w.get('worst_mos')}) | tpLH={fx(w.get('tplh_ps'))}ps | "
                f"tpHL={fx(w.get('tphl_ps'))}ps | tpd={fx(w.get('tpd_ps'))}ps | Swing={fx((w.get('swing_ratio') or 0) * 100, 1)}%")
        self.memo[key] = (src, note)
        return src, note

    def hvwave_tabs(self, tid=None):
        tabs = []
        for bw in self.PRE.get("hvt_waves") or []:
            if tid and bw["topology"] != tid:
                continue
            blocks, labels = [], {}
            base = f"{bw['topology']} — {fx(bw['vddl'], 1)}V → {fx(bw['vddh'], 1)}V @ {bw['freq_mhz']}MHz"
            for st, _ in STAGES:
                w = next((x for x in self.S[st].get("hvt_waves") or [] if x["topology"] == bw["topology"] and
                          abs(x["vddl"] - bw["vddl"]) < 0.01 and abs(x["vddh"] - bw["vddh"]) < 0.01 and
                          x["freq_mhz"] == bw["freq_mhz"]), None)
                labels[st] = f"{base} (|Vox|={fx(w.get('max_vox_v'), 3)}V)" if w else f"{base} ([N/A] in {dict(STAGES)[st]})"
                if w and w.get("waveform"):
                    src, note = self.hvwave(st, w)
                    blocks.append({"type": "chart", "stage": st, "alt": "hvw", "src": src, "height": 380})
                    blocks.append({"type": "note", "stage": st, "alt": "hvwn", "tone": "muted", "text": note})
            tabs.append({"label": labels.get("pre", base), "labels": labels, "vdd": bw["vddh"],
                         "key": f"{bw['topology']}_{fv(bw['vddl'])}_{fv(bw['vddh'])}_{bw['freq_mhz']}", "blocks": blocks})
        return {"type": "tabs", "style": "select", "label": "Select Operating Point", "id": "hv_wave", "tabs": tabs} if tabs else None


# ===================================================================================== designs
METRICS = [
    # key, label, unit, si, better, digits
    ("tpd", "Delay tpd (avg)", "s", True, "low", 4),
    ("tplh", "Delay tpLH (rising)", "s", True, "low", 4),
    ("tphl", "Delay tpHL (falling)", "s", True, "low", 4),
    ("trise", "Output rise time", "s", True, "low", 3),
    ("tfall", "Output fall time", "s", True, "low", 3),
    ("pstat", "Static power Pstat", "W", True, "low", 3),
    ("ptot", "Total power Ptot", "W", True, "low", 3),
    ("edyn", "Switching energy Edyn", "J", True, "low", 3),
    ("swing", "Output swing", "%", False, "high", 3),
    ("vol", "Output low VOL", "V", True, None, 3),
    ("voh", "Output high VOH", "V", True, None, 4),
    ("vox", "Peak oxide stress |Vox|", "V", True, "low", 4),
    ("pvt_yield", "PVT yield", "%", False, "high", 3),
    ("wc_tpd", "Worst-PVT tpd", "s", True, "low", 4),
    ("wc_tplh", "Worst-PVT tpLH", "s", True, "low", 4),
    ("wc_tphl", "Worst-PVT tpHL", "s", True, "low", 4),
    ("wc_pstat", "Worst-PVT Pstat", "W", True, "low", 3),
    ("wc_vox", "Worst-PVT |Vox|", "V", True, "low", 4),
    ("mc_yield", "MC seed yield", "%", False, "high", 3),
    ("mc_tpd_mean", "MC tpd mean µ", "s", True, "low", 4),
    ("mc_tpd_sd", "MC tpd σ", "s", True, "low", 3),
    ("mc_tpd3s", "MC tpd µ+3σ", "s", True, "low", 4),
    ("mc_swing3s", "MC swing µ−3σ", "%", False, "high", 3),
    ("mc_pstat3s", "MC Pstat µ+3σ", "W", True, "low", 3),
    ("area", "Layout area (gLayout bbox)", "µm²", False, "low", 6),
]
METRIC_DESC = {
    "tpd": "Mean of tpLH and tpHL (50 % crossings) of the nominal tt / 27 °C transient, CL = 20 fF, 10 MHz (HV points: 25 MHz). Empty when the output does not switch.",
    "tplh": "Rising-edge (turn-on) logical delay at tt / 27 °C.", "tphl": "Falling-edge (turn-off) logical delay at tt / 27 °C.",
    "pstat": "Static power from the nominal transient (all rails).", "ptot": "Total average power of the nominal transient.",
    "edyn": "Dynamic energy per output transition reported by the repo (Psw = 2·f·Edyn).",
    "swing": "Output swing as % of the output-domain span; the repo's pass criterion is ≥ 85 %.",
    "vox": "Peak max(|VGS|,|VGD|) over all MOSFETs during the nominal transient (HV oxide check; limit 1.8 V).",
    "pvt_yield": "Share of PVT corners that pass (20 corners tt/ss/ff/fs/sf × −40/27/85/125 °C; HV points: 15 corners incl. the 1.8 V oxide assertion).",
    "wc_tpd": "Slowest tpd over the PVT corners.", "wc_pstat": "Highest static power over the PVT corners.",
    "wc_vox": "Highest peak oxide stress over the 15 HV PVT corners.",
    "mc_yield": "Passing seeds of the 80-run Monte Carlo (global process + local mismatch).",
    "mc_tpd3s": "Monte Carlo µ+3σ of tpd; the 3σ acceptance requires < 25 ns.",
    "mc_swing3s": "Monte Carlo µ−3σ of the output swing; the 3σ acceptance requires ≥ 85 %.",
    "area": "gLayout bounding-box area of the extracted cell (a layout measurement, identical at every stage).",
}


def nominal_metrics(r):
    """Nominal tt/27 °C record (pilot or hvt_speed row) -> metrics.  Timing only when the output
    really toggles (repo's logic_pass: swing >= 85 % and valid edges)."""
    if not r:
        return {}
    ok = r.get("logic_pass", r.get("pass"))
    t = PS if ok else None
    return {"tpd": t and mul(r.get("tpd_ps"), t), "tplh": t and mul(r.get("tplh_ps"), t),
            "tphl": t and mul(r.get("tphl_ps"), t), "trise": t and mul(r.get("trise_ps"), t),
            "tfall": t and mul(r.get("tfall_ps"), t), "pstat": mul(r.get("p_stat_nw"), NW),
            "ptot": mul(r.get("p_tot_uw"), UW), "edyn": mul(r.get("e_dyn_fj"), FJ),
            "swing": mul(r.get("swing_ratio"), 100), "vol": r.get("vol"), "voh": r.get("voh"), "vox": r.get("max_vox_v")}


def hv_nominal(S, topo, summ):
    return next((r for r in (S.get("hvt_speed") or []) + (S.get("hvt_grid") or []) if r["topology"] == topo and
                 abs(r["vddl"] - summ["vddl"]) < 1e-6 and abs(r["vddh"] - summ["vddh"]) < 1e-6 and r["freq_mhz"] == 25), None)


def stage_result(c: Ctx, st, tid, dom, area):
    S, ix = c.S[st], c.ix[st]
    notes = []
    if dom["hv"]:
        summ = ix["hvt_pvt"].get((tid, dom["src"]))
        if not summ:
            return None
        nom = hv_nominal(S, tid, summ)
        m = nominal_metrics(nom)
        m.update(pvt_yield=summ["yield_pct"], wc_tpd=mul(summ.get("wc_tpd_ps"), PS), wc_vox=summ.get("wc_vox_v"))
        mc = None
        notes.append(f"15-corner PVT (tt/ss/ff/fs/sf × −40/27/125 °C) with the |VGS|,|VGD| < 1.8 V oxide assertion: "
                     f"{summ['n_logic_pass']}/{summ['n_total']} logic pass, {summ['n_oxide_safe']}/{summ['n_total']} oxide-safe; "
                     f"worst delay {summ.get('wc_dly_corner')}, worst oxide {summ.get('wc_vox_corner')}")
        if nom and nom.get("logic_pass") and not nom.get("oxide_safe_1v8"):
            notes.insert(0, f"nominal 25 MHz point exceeds the 1.8 V oxide limit (|Vox| = {fx(nom.get('max_vox_v'), 3)} V)")
    else:
        nom, summ = ix["pilot"].get((tid, dom["id"])), ix["pvt_summary"].get((tid, dom["id"]))
        if not nom and not summ:
            return None
        m = nominal_metrics(nom)
        if summ:
            m.update(pvt_yield=summ["yield_pct"], wc_tpd=mul(summ.get("wc_tpd_ps"), PS), wc_tplh=mul(summ.get("wc_tplh_ps"), PS),
                     wc_tphl=mul(summ.get("wc_tphl_ps"), PS), wc_pstat=mul(summ.get("wc_pstat_nw"), NW))
        mc = ix["mc_summary"].get((tid, dom["id"]))
        if summ and nom and (summ.get("nom_tpd_ps") != nom.get("tpd_ps") or summ.get("nom_pstat_nw") != nom.get("p_stat_nw")):
            mc_txt = f"; MC mean tpd {fx(mc.get('tpd_mean_ps'))} ps" if mc else ""
            notes.append(f"the PVT sweep{' and the Monte Carlo ensemble' if mc else ''} ran on an earlier netlist revision than "
                         f"the nominal pilot (PVT-run tt/27 °C point: tpd {fx(summ.get('nom_tpd_ps'))} ps, Pstat "
                         f"{fx(summ.get('nom_pstat_nw'))} nW vs pilot {fx(nom.get('tpd_ps'))} ps, {fx(nom.get('p_stat_nw'))} nW{mc_txt}), "
                         f"so the worst-case, Monte Carlo and robust figures describe that revision")
        if mc:
            m.update(mc_yield=mc["yield_pct"], mc_tpd_mean=mul(mc.get("tpd_mean_ps"), PS), mc_tpd_sd=mul(mc.get("tpd_std_ps"), PS),
                     mc_tpd3s=mul(mc.get("tpd_3sigma_ps"), PS), mc_swing3s=mc.get("swing_3sigma_low_pct"),
                     mc_pstat3s=mul(mc.get("pstat_3sigma_nw"), NW))
        if nom and nom.get("pass") and (nom.get("e_dyn_fj") == 0):
            notes.append("Edyn reported as 0 fJ by the repo's energy extraction (static current dominates the supply integral)")
    m["area"] = area
    if m.get("swing") is not None and m["swing"] < 0:
        notes.append(f"output never toggles (raw swing {fx(m['swing'], 2)} %, not reported)")
        m["swing"] = None
    if m.get("mc_swing3s") is not None and m["mc_swing3s"] < 0:
        notes.append(f"Monte Carlo µ−3σ swing is negative ({fx(m['mc_swing3s'], 1)} %, far below the 85 % limit; not reported)")
        m["mc_swing3s"] = None
    res = {"metrics": {k: m.get(k) for k, *_ in METRICS if m.get(k) is not None}}
    if summ:
        res["pvt"] = {"pass": summ["n_pass"], "total": summ["n_total"]}
        res["robust"] = bool(summ["n_total"] and summ["n_pass"] == summ["n_total"] and (mc is None or mc.get("pass_3sigma")))
    if mc:
        res["mc"] = {"pass": mc["n_pass"], "total": mc["n_runs"]}
    if nom is not None and not nom.get("pass"):
        res["status"] = "fail"
        notes.insert(0, "fails at the nominal tt/27 °C point" + (f" (swing {fx((nom.get('swing_ratio') or 0) * 100, 0)} %)"
                                                                  if not nom.get("logic_pass", True) or not dom["hv"] else ""))
    if st == "full":
        notes.insert(0, "Magic RC extraction (devices + routing parasitics) of the complete gLayout cell")
    if notes:
        res["note"] = "; ".join(notes)
    return res


def domains(c: Ctx):
    doms = {}
    for r in c.PRE["pvt_summary"]:
        dl = r["domain_label"]
        if dl in doms:
            continue
        doms[dl] = dict(id=dl, src=dl, label=dict((a, b) for a, _, b in FLAG).get(dl, dl),
                        title=(r.get("domain_title") or dl).replace("->", "→"), vssl=r["vssl"], vddl=r["vddl"],
                        vssh=r["vssh"], vddh=r["vddh"], kind=dl.split("_")[0], hv=False)
    hv = {}
    for st in ("pre", "full"):
        for r in c.S[st].get("hvt_pvt_summary") or []:
            did = hv_id(r["domain_label"])
            hv.setdefault(did, dict(id=did, src=r["domain_label"], label=f"{r['vddl']:.1f} → {r['vddh']:.1f} V (HV)",
                                    title=f"0-{r['vddl']:.1f}V → 0-{r['vddh']:.1f}V (HV-tolerant, 25 MHz)", vssl=0.0,
                                    vddl=r["vddl"], vssh=0.0, vddh=r["vddh"], kind="hvt", hv=True))
    order = [d for d, *_ in FLAG if d in doms] + [d for d in doms if d not in [x for x, *_ in FLAG]]
    order += sorted(hv, key=lambda k: (hv[k]["vddh"], hv[k]["vddl"]))
    doms.update(hv)
    return doms, order


def kv_nominal(r, hv=False, freq="10 MHz"):
    if not r:
        return []
    it = [{"label": "Status", "value": "PASS" if r["pass"] else "FAIL", "s": "good" if r["pass"] else "bad"},
          {"label": "Logic pass (swing ≥ 85 %)", "value": bool(r.get("logic_pass", r["pass"]))},
          {"label": "Corner / temperature", "value": f"{r.get('corner', 'tt')} / {fv(r.get('temp', 27))} °C"},
          {"label": "Frequency · C<sub>L</sub>", "value": f"{fv((r.get('freq_hz') or 1e7) / 1e6)} MHz · {fv(r.get('cload_ff') or 20)} fF"},
          {"label": "VOL", "value": r.get("vol"), "unit": "V", "si": True, "digits": 4},
          {"label": "VOH", "value": r.get("voh"), "unit": "V", "si": True, "digits": 4},
          {"label": "Swing", "value": mul(r.get("swing_ratio"), 100), "unit": "%", "digits": 4},
          {"label": "tpLH", "value": mul(r.get("tplh_ps"), PS), "unit": "s", "si": True, "digits": 4},
          {"label": "tpHL", "value": mul(r.get("tphl_ps"), PS), "unit": "s", "si": True, "digits": 4},
          {"label": "tpd", "value": mul(r.get("tpd_ps"), PS), "unit": "s", "si": True, "digits": 4},
          {"label": "t<sub>rise</sub>", "value": mul(r.get("trise_ps"), PS), "unit": "s", "si": True, "digits": 4},
          {"label": "t<sub>fall</sub>", "value": mul(r.get("tfall_ps"), PS), "unit": "s", "si": True, "digits": 4},
          {"label": "P<sub>stat</sub>", "value": mul(r.get("p_stat_nw"), NW), "unit": "W", "si": True, "digits": 4},
          {"label": "P<sub>tot</sub>", "value": mul(r.get("p_tot_uw"), UW), "unit": "W", "si": True, "digits": 4},
          {"label": "E<sub>cycle</sub>", "value": mul(r.get("e_cycle_fj"), FJ), "unit": "J", "si": True, "digits": 4},
          {"label": "E<sub>dyn</sub> (per transition)", "value": mul(r.get("e_dyn_fj"), FJ), "unit": "J", "si": True, "digits": 4}]
    if hv or r.get("max_vox_v") is not None:
        it += [{"label": "max |VGS|", "value": r.get("max_vgs_v"), "unit": "V", "si": True, "digits": 4},
               {"label": "max |VGD|", "value": r.get("max_vgd_v"), "unit": "V", "si": True, "digits": 4},
               {"label": "max |Vox|", "value": r.get("max_vox_v"), "unit": "V", "si": True, "digits": 4,
                "s": "good" if r.get("oxide_safe_1v8") else "bad"},
               {"label": "Worst MOSFET", "value": f"`{r.get('worst_mos')}`" if r.get("worst_mos") else "—"},
               {"label": "Oxide safe (< 1.8 V)", "value": bool(r.get("oxide_safe_1v8"))}]
    return it


CORNER_COLS = [
    {"key": "corner", "label": "Process", "type": "text"}, {"key": "temp", "label": "Temp", "unit": "°C", "digits": 3},
    {"key": "pass", "label": "Pass", "type": "status"},
    {"key": "vol", "label": "VOL", "unit": "V", "si": True, "digits": 4}, {"key": "voh", "label": "VOH", "unit": "V", "si": True, "digits": 4},
    {"key": "swing", "label": "Swing", "unit": "%", "digits": 4},
    {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4}, {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4},
    {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4}, {"key": "trise", "label": "t<sub>rise</sub>", "unit": "s", "si": True},
    {"key": "tfall", "label": "t<sub>fall</sub>", "unit": "s", "si": True}, {"key": "pstat", "label": "P<sub>stat</sub>", "unit": "W", "si": True},
    {"key": "ptot", "label": "P<sub>tot</sub>", "unit": "W", "si": True}, {"key": "edyn", "label": "E<sub>dyn</sub>", "unit": "J", "si": True}]


def corner_row(r):
    return {"corner": r["corner"], "temp": r["temp"], "pass": bool(r["pass"]), "vol": r.get("vol"), "voh": r.get("voh"),
            "swing": mul(r.get("swing_ratio"), 100), "tplh": mul(r.get("tplh_ps"), PS), "tphl": mul(r.get("tphl_ps"), PS),
            "tpd": mul(r.get("tpd_ps"), PS), "trise": mul(r.get("trise_ps"), PS), "tfall": mul(r.get("tfall_ps"), PS),
            "pstat": mul(r.get("p_stat_nw"), NW), "ptot": mul(r.get("p_tot_uw"), UW), "edyn": mul(r.get("e_dyn_fj"), FJ)}


def pvt_kv(p):
    return [{"label": "20-corner yield", "value": f"{p['n_pass']}/{p['n_total']} ({fv(p['yield_pct'])} %)",
             "s": "good" if p["n_pass"] == p["n_total"] else "warn" if p["n_pass"] else "bad"},
            {"label": "Nominal tpLH / tpHL (PVT run)", "value": f"{fx(p.get('nom_tplh_ps'))} / {fx(p.get('nom_tphl_ps'))} ps"},
            {"label": "Nominal t<sub>rise</sub> / t<sub>fall</sub>", "value": f"{fx(p.get('nom_trise_ps'))} / {fx(p.get('nom_tfall_ps'))} ps"},
            {"label": "Nominal Pstat · Edyn", "value": f"{fx(p.get('nom_pstat_nw'))} nW · {fx(p.get('nom_edyn_fj'))} fJ"},
            {"label": "Worst-case delay corner", "value": p.get("wc_corner") or "—"},
            {"label": "WC tpLH / tpHL / tpd", "value": f"{fx(p.get('wc_tplh_ps'))} / {fx(p.get('wc_tphl_ps'))} / {fx(p.get('wc_tpd_ps'))} ps"},
            {"label": "WC t<sub>rise</sub> / t<sub>fall</sub>", "value": f"{fx(p.get('wc_trise_ps'), 0)} / {fx(p.get('wc_tfall_ps'), 0)} ps"},
            {"label": "Worst-case leakage corner · WC Pstat", "value": f"{p.get('wc_pstat_corner') or '—'} · {fx(p.get('wc_pstat_nw'))} nW"}]


def pvt_chart(rows, title):
    lab = [f"{r['corner']} {fv(r['temp'])}°C" for r in rows]
    return {"data": [
        {"type": "bar", "name": "tpd (ps)", "x": lab, "y": [r.get("tpd_ps") for r in rows],
         "marker": {"color": ["#2a78d6" if r["pass"] else "#cf222e" for r in rows]},
         "customdata": [["PASS" if r["pass"] else "FAIL", fx((r.get("swing_ratio") or 0) * 100, 0)] for r in rows],
         "hovertemplate": "%{x}: tpd %{y:.1f} ps · %{customdata[0]} (swing %{customdata[1]}%)<extra></extra>"},
        {"type": "scatter", "mode": "lines+markers", "name": "Pstat (nW, right axis)", "x": lab,
         "y": [r.get("p_stat_nw") if (r.get("p_stat_nw") or 0) > 0 else None for r in rows], "yaxis": "y2",
         "line": {"color": "#9a6700", "width": 1.5}, "marker": {"size": 6},
         "hovertemplate": "%{x}: Pstat %{y:.3g} nW<extra></extra>"}],
        "layout": {"title": {"text": title, "font": {"size": 13}, "x": 0.01}, "xaxis": {"tickangle": -40},
                   "yaxis": {"title": {"text": "tpd (ps) — red = failing corner"}},
                   "yaxis2": {"title": {"text": "Pstat (nW)"}, "overlaying": "y", "side": "right", "type": "log", "showgrid": False},
                   "margin": {"t": 40, "r": 60}, "legend": {"orientation": "h", "y": -0.35}}}


def mc_kv(m):
    return [{"label": "3σ acceptance", "value": "3σ PASS" if m.get("pass_3sigma") else "3σ FAIL", "s": "good" if m.get("pass_3sigma") else "bad"},
            {"label": "MC seed yield", "value": f"{m['n_pass']}/{m['n_runs']} ({fv(m['yield_pct'])} %)"},
            {"label": "Swing µ / σ", "value": f"{fx(m.get('swing_mean_pct'))} % / {fx(m.get('swing_std_pct'), 2)} %"},
            {"label": "3σ min swing (µ−3σ) · min", "value": f"{fx(m.get('swing_3sigma_low_pct'))} % · {fx(m.get('swing_min_pct'))} %",
             "s": "good" if (m.get("swing_3sigma_low_pct") or 0) >= 85 else "bad"},
            {"label": "tpd µ / σ", "value": f"{fx(m.get('tpd_mean_ps'))} / {fx(m.get('tpd_std_ps'))} ps"},
            {"label": "3σ WC tpd (µ+3σ)", "value": f"{fx(m.get('tpd_3sigma_ps'))} ps"},
            {"label": "tpd min / p95 / max", "value": f"{fx(m.get('tpd_min_ps'))} / {fx(m.get('tpd_p95_ps'))} / {fx(m.get('tpd_max_ps'))} ps"},
            {"label": "tpLH µ / µ+3σ", "value": f"{fx(m.get('tplh_mean_ps'))} / {fx(m.get('tplh_3sigma_ps'))} ps"},
            {"label": "tpHL µ / µ+3σ", "value": f"{fx(m.get('tphl_mean_ps'))} / {fx(m.get('tphl_3sigma_ps'))} ps"},
            {"label": "Pstat µ / σ / µ+3σ / p95", "value": f"{fx(m.get('pstat_mean_nw'))} / {fx(m.get('pstat_std_nw'), 2)} / "
                                                           f"{fx(m.get('pstat_3sigma_nw'))} / {fx(m.get('pstat_p95_nw'))} nW"},
            {"label": "Edyn µ", "value": f"{fx(m.get('edyn_mean_fj'))} fJ"}]


def topo_md(t):
    a = t.get("area") or {}
    cites = "\n".join(f"- [{x['short']}]({x['url']}) — {x['full']}" for x in t.get("citations") or [])
    return (f"**{t['id']} — {t['name']}** · {t.get('short_name')} · {t.get('category')} · coupling **{t.get('coupled_type')}**\n\n"
            f"{t.get('description', '')}\n\n**Topology origin:** {t.get('origin_note') or t.get('ref') or ''}\n\n"
            f"**Area:** {fx(a.get('total_area_um2'))} µm² (MOS: {fx(a.get('mos_area_um2'))} µm² [{a.get('n_mos')} FETs] + Passive: "
            f"{fx(a.get('passive_area_um2'))} µm² [R={fx(a.get('res_area_um2'))}, C={fx(a.get('cap_area_um2'))}])\n\n"
            f"**Literature references**\n{cites}")


def pex_kv(t):
    pm, a = t.get("pex_meta") or {}, t.get("area") or {}
    return [{"label": "gLayout BBox W × H", "value": f"{fx(pm.get('width_um'))} × {fx(pm.get('height_um'))} µm"},
            {"label": "gLayout bbox area", "value": f"{fx(pm['layout_area_um2'], 2)} µm²" if pm.get("layout_area_um2") is not None else None},
            {"label": "Extracted devices", "value": pm.get("n_extracted_devs"), "digits": 0},
            {"label": "Parasitic caps (count · total)", "value": f"{pm.get('n_parasitic_caps')} · {fx(pm.get('total_cap_ff'), 2)} fF"},
            {"label": "Parasitic resistors (count · total)", "value": f"{pm.get('n_parasitic_res')} · {fx(pm.get('total_res_ohm'))} Ω"},
            {"label": "Post-PEX status", "value": "PEX EXTRACTED" if pm.get("has_pex") else "—", "s": "good" if pm.get("has_pex") else None},
            {"label": "Schematic device area (MOS + passive)", "value": f"{fx(a.get('total_area_um2'), 2)} µm² "
                                                                         f"({fx(a.get('mos_area_um2'), 2)} + {fx(a.get('passive_area_um2'), 2)})"},
            {"label": "Device count MOS / R / C", "value": f"{a.get('n_mos')} / {a.get('n_res')} / {a.get('n_cap')}"},
            {"label": "DRC / LVS", "value": "not reported by the repo (null in report_data.json)"}]


def netlist_blocks(t, alt):
    pm = t.get("pex_meta") or {}
    b = [{"type": "code", "stage": "pre", "alt": alt, "title": f"Executable GF180MCU SPICE subcircuit netlist (Pre-PEX schematic — {t['id']})",
          "text": t.get("spice") or "", "max_height": 480}]
    if pm.get("pex_spice"):
        b.append({"type": "code", "stage": "full", "alt": alt, "title": f"Magic RC-extracted post-PEX SPICE subcircuit netlist ({t['id']}.pex.spice)",
                  "text": pm["pex_spice"], "max_height": 480})
    return b


def build_designs(c: Ctx, pages_mod):
    doms, order = domains(c)
    c.doms, c.dom_order = doms, order
    hv_pairs = {(r["topology"], hv_id(r["domain_label"])) for st in ("pre", "full") for r in c.S[st].get("hvt_pvt_summary") or []}
    designs = []
    by_topo = {}
    for t in c.topos:
        tid = t["id"]
        pm, ar = t.get("pex_meta") or {}, t.get("area") or {}
        area = Keep(pm["layout_area_um2"]) if pm.get("layout_area_um2") is not None else None
        for did in order:
            d = doms[did]
            if d["hv"] and (tid, did) not in hv_pairs:
                continue
            results = {}
            for st, _ in STAGES:
                if st == "full" and not pm.get("has_pex"):
                    continue
                r = stage_result(c, st, tid, d, area)
                if r:
                    results[st] = r
            if not results:
                continue
            up = d["vddh"] > d["vddl"]
            des_id = f"{tid}.{did}"
            files = {k: v for k, v in (("schematic", f"assets/schem_{tid}.svg"), ("thumbnail", pm.get("layout_png") or f"assets/layout_{tid}.png"),
                                       ("data", "report_data.json")) if (c.docs / v).is_file()}
            lay = pm.get("layout_png") or f"assets/layout_{tid}.png"
            rec = {
                "id": des_id, "title": f"{t['short_name']} · {d['title']}",
                "summary": f"{t['name']} ({t.get('category')}, {t.get('coupled_type')}-coupled) translating "
                           f"{fv(d['vssl'])}–{fv(d['vddl'])} V → {fv(d['vssh'])}–{fv(d['vddh'])} V"
                           f"{' at 25 MHz under the 1.8 V gate-oxide limit' if d['hv'] else ' (tt, 27 °C, C<sub>L</sub> = 20 fF, 10 MHz)'}.",
                "vdd": d["vddh"],
                "axes": {"topology": tid, "domain": did, "kind": d["kind"], "direction": "up" if up else "down",
                         "coupling": t.get("coupled_type")},
                "tags": [x for x in (t.get("category"), f"{t.get('coupled_type')} coupled", "step-up" if up else "step-down",
                                     t.get("ref")) if x],
                "physical": {"drc": pm.get("drc_clean"), "lvs": pm.get("lvs_clean"), "pex": True if pm.get("has_pex") else None,
                             "area_um2": area, "width_um": pm.get("width_um"), "height_um": pm.get("height_um")},
                "results": results,
                "params": {
                    "Input rails (VSSL / VDDL)": f"{fv(d['vssl'])} / {fv(d['vddl'])} V",
                    "Output rails (VSSH / VDDH)": f"{fv(d['vssh'])} / {fv(d['vddh'])} V",
                    "Test frequency": "25 MHz" if d["hv"] else "10 MHz", "C<sub>L</sub>": "20 fF", "Nominal corner": "tt, 27 °C",
                    "MOS / R / C devices": f"{ar.get('n_mos')} / {ar.get('n_res')} / {ar.get('n_cap')}",
                    "Schematic device area (MOS + passive)": f"{fx(ar.get('total_area_um2'), 2)} µm² ({fx(ar.get('mos_area_um2'), 2)} + "
                                                             f"{fx(ar.get('passive_area_um2'), 2)})",
                    "Extracted devices": pm.get("n_extracted_devs"),
                    "Parasitic C (total)": f"{fx(pm.get('total_cap_ff'), 2)} fF ({pm.get('n_parasitic_caps')} caps)",
                    "Parasitic R (total)": f"{fx(pm.get('total_res_ohm'))} Ω ({pm.get('n_parasitic_res')} resistors)",
                },
                "files": files,
                "images": [{"label": "gLayout physical layout (PNG render)", "src": lay}] if (c.docs / lay).is_file() else [],
                "detail": f"hub/designs/{des_id}.json",
            }
            designs.append(rec)
            by_topo.setdefault(tid, []).append(rec)
            c.design_ids.add(des_id)
    c.by_topo = by_topo
    for rec in designs:
        tid, did = rec["axes"]["topology"], rec["axes"]["domain"]
        c.o.put(f"designs/{rec['id']}.json", {"blocks": detail_blocks(c, c.T[tid], doms[did], rec, pages_mod)})
    return designs


def sibling_table(c: Ctx, tid, cur):
    rows = []
    for rec in c.by_topo.get(tid, []):
        for st, r in rec["results"].items():
            m = r["metrics"]
            rows.append({"design": {"v": rec["id"], "t": c.doms[rec["axes"]["domain"]]["title"]}, "stage": st,
                         "cur": "◀ this" if rec["id"] == cur else "",
                         "tpd": m.get("tpd"), "pstat": m.get("pstat"), "edyn": m.get("edyn"),
                         "pvt": f"{r['pvt']['pass']}/{r['pvt']['total']}" if r.get("pvt") else "—",
                         "mc": f"{r['mc']['pass']}/{r['mc']['total']}" if r.get("mc") else "—",
                         "robust": r.get("robust")})
    return {"type": "table", "title": "All crossings of this topology", "stage_column": "stage", "search": False, "csv": False,
            "columns": [{"key": "design", "label": "Crossing", "type": "design"}, {"key": "cur", "label": "", "type": "text"},
                        {"key": "stage", "label": "Stage", "type": "text"},
                        {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4},
                        {"key": "pstat", "label": "P<sub>stat</sub>", "unit": "W", "si": True},
                        {"key": "edyn", "label": "E<sub>dyn</sub>", "unit": "J", "si": True},
                        {"key": "pvt", "label": "PVT", "type": "text"}, {"key": "mc", "label": "MC", "type": "text"},
                        {"key": "robust", "label": "Robust", "type": "status"}],
            "rows": rows}


def detail_blocks(c: Ctx, t, d, rec, P):
    tid, did = t["id"], d["id"]
    B = [{"type": "section", "title": "Topology, origin & references", "collapsed": True, "open": True,
          "blocks": [{"type": "markdown", "text": topo_md(t)}]}]
    if d["hv"]:
        nb = []
        for st, lab in STAGES:
            summ = c.ix[st]["hvt_pvt"].get((tid, d["src"]))
            if not summ:
                continue
            nom = hv_nominal(c.S[st], tid, summ)
            if nom:
                nb.append({"type": "kv", "stage": st, "alt": "nom", "cols": 4, "title": "Nominal transient (tt, 27 °C, 25 MHz, 20 fF) with oxide-stress check",
                           "items": kv_nominal(nom, hv=True)})
            nb.append({"type": "kv", "stage": st, "alt": "hvpvt", "cols": 3, "title": "15-corner PVT verification with gate-oxide stress assertion",
                       "items": [{"label": "Combined yield", "value": f"{summ['n_pass']}/{summ['n_total']} ({fv(summ['yield_pct'])} %)",
                                  "s": "good" if summ["n_pass"] >= 12 else "bad"},
                                 {"label": "15-corner logic pass", "value": f"{summ['n_logic_pass']} / {summ['n_total']}"},
                                 {"label": "15-corner oxide safe (< 1.80 V)", "value": f"{summ['n_oxide_safe']} / {summ['n_total']}"},
                                 {"label": "Nominal tpd (PVT run)", "value": mul(summ.get("nom_tpd_ps"), PS), "unit": "s", "si": True, "digits": 4},
                                 {"label": "Nominal peak |Vox|", "value": summ.get("nom_vox_v"), "unit": "V", "si": True, "digits": 4},
                                 {"label": "Nominal worst MOSFET", "value": f"`{summ.get('nom_worst_mos')}`"},
                                 {"label": "Worst-case delay corner · WC tpd", "value": f"{summ.get('wc_dly_corner')} · {fx(summ.get('wc_tpd_ps'))} ps"},
                                 {"label": "Worst-case oxide corner · WC peak |Vox|", "value": f"{summ.get('wc_vox_corner')} · {fx(summ.get('wc_vox_v'), 3)} V"},
                                 {"label": "WC worst MOSFET", "value": f"`{summ.get('wc_worst_mos')}`"}]})
            sp = sorted([r for r in c.S[st].get("hvt_speed") or [] if r["topology"] == tid and abs(r["vddl"] - d["vddl"]) < 1e-6
                         and abs(r["vddh"] - d["vddh"]) < 1e-6], key=lambda r: r["freq_mhz"])
            if sp:
                nb.append({"type": "table", "stage": st, "alt": "hvspeed", "title": "Frequency sweep at this operating point (25 → 500 MHz)",
                           "search": False, "columns": [
                               {"key": "f", "label": "f", "unit": "Hz", "si": True}, {"key": "safe", "label": "Pass (logic & oxide)", "type": "status"},
                               {"key": "lp", "label": "Logic pass", "type": "status"}, {"key": "ox", "label": "Oxide safe", "type": "status"},
                               {"key": "vox", "label": "max |Vox|", "unit": "V", "si": True, "digits": 4},
                               {"key": "mos", "label": "Worst MOSFET", "type": "text"},
                               {"key": "tpd", "label": "tpd", "unit": "s", "si": True, "digits": 4},
                               {"key": "tplh", "label": "tpLH", "unit": "s", "si": True, "digits": 4},
                               {"key": "tphl", "label": "tpHL", "unit": "s", "si": True, "digits": 4},
                               {"key": "swing", "label": "Swing", "unit": "%", "digits": 4},
                               {"key": "edyn", "label": "E<sub>dyn</sub>", "unit": "J", "si": True}],
                           "rows": [{"f": r["freq_mhz"] * 1e6, "safe": bool(r["pass"]), "lp": bool(r["logic_pass"]), "ox": bool(r["oxide_safe_1v8"]),
                                     "vox": r.get("max_vox_v"), "mos": r.get("worst_mos"), "tpd": mul(r.get("tpd_ps"), PS),
                                     "tplh": mul(r.get("tplh_ps"), PS), "tphl": mul(r.get("tphl_ps"), PS),
                                     "swing": mul(r.get("swing_ratio"), 100), "edyn": mul(r.get("e_dyn_fj"), FJ)} for r in sp]})
        B.append({"type": "section", "title": f"Operating point {d['title']}", "blocks": nb})
        hw = [w for w in c.PRE.get("hvt_waves") or [] if w["topology"] == tid and abs(w["vddl"] - d["vddl"]) < 0.01 and abs(w["vddh"] - d["vddh"]) < 0.01]
        if hw:
            wb = []
            for st, _ in STAGES:
                w = next((x for x in c.S[st].get("hvt_waves") or [] if x["topology"] == tid and abs(x["vddl"] - d["vddl"]) < 0.01
                          and abs(x["vddh"] - d["vddh"]) < 0.01), None)
                if w and w.get("waveform"):
                    src, note = c.hvwave(st, w)
                    wb += [{"type": "chart", "stage": st, "alt": "hvw", "src": src, "height": 360},
                           {"type": "note", "stage": st, "alt": "hvwn", "tone": "muted", "text": note}]
            B.append({"type": "section", "title": "HV-tolerant transient waveform", "blocks": wb})
    else:
        nb = []
        for st, lab in STAGES:
            r = c.ix[st]["pilot"].get((tid, did))
            if r:
                nb.append({"type": "kv", "stage": st, "alt": "nom", "cols": 4, "items": kv_nominal(r),
                           "title": "Flagship pilot benchmark (tt, 27 °C, C<sub>L</sub> = 20 fF, f = 10 MHz)"})
        B.append({"type": "section", "title": f"Nominal benchmark · {d['title']}",
                  "intro": f"Input domain [{fv(d['vssl'])}, {fv(d['vddl'])} V] → output domain [{fv(d['vssh'])}, {fv(d['vddh'])} V].",
                  "blocks": nb})
        B.append({"type": "section", "title": "Transient waveforms (nominal and worst-case PVT corners)",
                  "blocks": c.wave_blocks(tid, did) + [{"type": "markdown", "text": f"[Open in the waveform viewer (other domains of {tid}) →]"
                                                                                  f"(#/ls?page=waveforms&t.wave_topo={tid}&t.wave_dom={did})"}]})
        pb = []
        for st, lab in STAGES:
            p = c.ix[st]["pvt_summary"].get((tid, did))
            if not p:
                continue
            rows = [r for r in c.S[st].get("pvt_corners") or [] if r["topology"] == tid and r["domain_label"] == did]
            pb.append({"type": "kv", "stage": st, "alt": "pvtkv", "cols": 4, "items": pvt_kv(p), "title": "20-corner PVT summary"})
            if rows:
                pb.append({"type": "chart", "stage": st, "alt": "pvtchart", "height": 340, **pvt_chart(rows, f"{tid} · {did}: tpd and Pstat per PVT corner ({lab})")})
                pb.append({"type": "table", "stage": st, "alt": "pvttab", "title": "All 20 PVT corners (5 process × 4 temperatures)",
                           "columns": CORNER_COLS, "rows": [corner_row(r) for r in rows], "search": False})
        B.append({"type": "section", "title": "All-PVT-corner verification (tt/ss/ff/fs/sf × −40/27/85/125 °C)", "blocks": pb})
        if any(c.ix[st]["mc_summary"].get((tid, did)) for st, _ in STAGES):
            mb = []
            for st, _ in STAGES:
                m = c.ix[st]["mc_summary"].get((tid, did))
                if m:
                    mb.append({"type": "kv", "stage": st, "alt": "mckv", "cols": 4, "items": mc_kv(m), "title": "Monte Carlo summary (3σ acceptance)"})
            B.append({"type": "section", "title": "Monte Carlo statistical + local mismatch (80 runs, µ ± 3σ)",
                      "intro": "Acceptance: 100 % seed pass, µ_swing − 3σ_swing ≥ 85 % and µ_tpd + 3σ_tpd < 25 ns.",
                      "blocks": mb + [{"type": "section", "cols": 2, "blocks": c.mc_blocks(tid, did)}]})
    B.append({"type": "section", "title": "gLayout physical layout & post-PEX parasitic extraction", "cols": 2,
              "blocks": [{"type": "kv", "cols": 1, "items": pex_kv(t)},
                         {"type": "image", "title": "gLayout render", "src": (t.get("pex_meta") or {}).get("layout_png") or f"assets/layout_{tid}.png",
                          "bg": "white", "max_height": 520}]})
    B.append({"type": "section", "title": "SPICE netlist (schematic / Magic RC-extracted)", "collapsed": True,
              "blocks": netlist_blocks(t, "net")})
    B.append({"type": "section", "title": "Other crossings of this topology", "blocks": [sibling_table(c, tid, rec["id"])]})
    B.append({"type": "section", "title": f"{tid} across the rest of the report", "collapsed": True,
              "intro": "Topology-level sweeps of the same cell (shared with the report pages).",
              "blocks": [P.topology_tabs(c, tid)]})
    return B


# ===================================================================================== main
def main():
    docs, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    c = Ctx(docs, out)
    c.L = sys.modules[__name__]
    import ls_pages as P
    designs = build_designs(c, P)
    pages = P.build_pages(c)
    pre_sims, pex_sims = c.PRE.get("total_sims", 0), c.S["full"].get("total_sims", 0)
    dse = c.PRE.get("dse") or {}
    coupling = []
    for t in c.topos:
        if t.get("coupled_type") not in coupling:
            coupling.append(t.get("coupled_type"))
    mtime = datetime.fromtimestamp((docs / "report_data.json").stat().st_mtime, timezone.utc)
    comp = {
        "schema": "aicdb-hub/2",
        "id": "ls",
        "name": "Level shifters",
        "title": to_md(c.dom.find("h1")) if c.dom.find("h1") else "GF180 Level-Shifter Topology Benchmark",
        "summary": f"{len(c.topos)} level-shifter topologies (DCVS, Wilson current-mirror, near-Vt, cap-boost, split-rail, "
                   "envelope-universal, pure AC-coupled and HV-tolerant stacked) benchmarked across six voltage-domain crossings "
                   "(core→IO, sub-Vt, split-rail and disjoint, up and down) plus HV-tolerant operating points up to 4.8 V. "
                   "The supply shown is the output-domain rail VDDH; the input rails are in the domain axis. Nominal tt/27 °C "
                   "transients, 20-corner PVT, Monte Carlo and Magic full-cell PEX of each gLayout cell.",
        "technology": "gf180mcuD",
        "generated": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats": [{"label": "simulations (pre-PEX)", "value": f"{pre_sims:,}"},
                  {"label": "simulations (post-PEX)", "value": f"{pex_sims:,}"},
                  {"label": "DSE sizing candidates", "value": f"{dse.get('n_total', 0):,}"}],
        "metrics": [{k: v for k, v in dict(key=k, label=lab, unit=u, si=si or None, better=b, digits=dg, desc=METRIC_DESC.get(k)).items()
                     if v is not None} for k, lab, u, si, b, dg in METRICS],
        "axes": {
            "topology": {"label": "Topology", "values": [{"id": t["id"], "label": f"{t['id'].split('_')[0]} · {t['short_name']}"} for t in c.topos]},
            "domain": {"label": "Domain crossing", "values": [{"id": k, "label": c.doms[k]["label"]} for k in c.dom_order]},
            "kind": {"label": "Crossing type", "values": [{"id": k, "label": v} for k, v in KIND.items()
                                                          if any(d["kind"] == k for d in c.doms.values())]},
            "direction": {"label": "Direction", "values": [{"id": "up", "label": "Step-up"}, {"id": "down", "label": "Step-down"}]},
            "coupling": {"label": "Coupling", "values": [{"id": x, "label": x} for x in coupling]},
        },
        "matrix": {"rows": ["topology"], "cols": ["domain"], "metrics": ["tpd", "pvt_yield", "swing"],
                   "presets": [{"label": "Delay, PVT yield & swing", "metrics": ["tpd", "pvt_yield", "swing"]},
                               {"label": "Static power & switching energy", "metrics": ["pstat", "edyn"]},
                               {"label": "Rise / fall delay", "metrics": ["tplh", "tphl"]},
                               {"label": "Worst-case PVT delay", "metrics": ["wc_tpd", "pvt_yield"]},
                               {"label": "Monte Carlo µ+3σ", "metrics": ["mc_tpd3s", "mc_yield"]},
                               {"label": "Oxide stress (HV points)", "metrics": ["wc_vox", "vox"]},
                               {"label": "Layout area", "metrics": ["area", "tpd"]}]},
        "card_metrics": ["tpd", "pvt_yield", "edyn", "pstat", "swing", "area"],
        "cards_group_by": "topology",
        "pages": pages,
        "designs": designs,
    }
    c.o.put("component.json", comp)


if __name__ == "__main__":
    main()
