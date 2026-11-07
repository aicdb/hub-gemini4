"""Page builders for the ecg hub export (design space, sensitivity, cross-check, reuse, database,
methodology, library notes).  Stdlib only; reads DOCS_DIR only (via the dict built by ecg_blocks.load_docs)."""
from __future__ import annotations

from pathlib import Path

import ecg_blocks as B
import ecg_text as T

STAGE_KEY = (("pre", "pre", "Pre-PEX"), ("partial", "post", "Partial post-PEX"))


def tier_of(D, p_nw):
    for t in D["meta"]["power_tiers"]:
        if t["p_min_nw"] <= p_nw <= t["p_max_nw"]:
            return t["tag"]
    return "out"


# ----------------------------------------------------------------------------- design space
DSE_DIMS = [
    {"key": "power", "label": "Total power P_tot", "unit": "W", "si": True, "log": True, "better": "low"},
    {"key": "irn", "label": "Chopped IRN 0.5 Hz–1 kHz (model)", "unit": "Vrms", "si": True, "better": "low"},
    {"key": "zin", "label": "|Z_in| @ 50 Hz (IBL on)", "unit": "Ω", "si": True, "log": True, "better": "high"},
    {"key": "nef", "label": "NEF (model)", "better": "low"},
    {"key": "gain", "label": "Midband AFE gain A_mid (model)", "unit": "dB"},
    {"key": "dr", "label": "DR @ 1 % THD (model)", "unit": "dB", "better": "high"},
    {"key": "a_lna", "label": "Stage-1 LNA gain", "unit": "dB"},
    {"key": "a_ol", "label": "Core OTA A_OL (model)", "unit": "dB", "better": "high"},
    {"key": "f_h", "label": "High cutoff f_H (simulated; hub-recovered where the repo conditioned it)", "unit": "Hz", "si": True},
    {"key": "f_l", "label": "Low cutoff f_L", "unit": "Hz", "si": True, "log": True, "better": "low"},
    {"key": "pm", "label": "Phase margin (model estimate)", "unit": "°", "better": "high"},
    {"key": "boost", "label": "Z_in boost (IBL on / off)", "unit": "×", "better": "high"},
    {"key": "pef", "label": "PEF (model)", "better": "low"},
    {"key": "iref", "label": "Core bias reference I_ref,core", "unit": "A", "si": True, "log": True},
    {"key": "cpf_um", "label": "C_pf MIM side length (β_IBL knob)", "unit": "µm"},
]


def explore_page(D, out: Path):
    meta = D["meta"]
    archs = meta["architectures"]
    alab = {a["id"]: f"{a['name']} ({a['short']})" for a in archs}
    keys = ["kind", "stage", "arch", "supply", "vdd", "tier", "pareto", "window", "power", "irn", "zin", "nef", "gain", "dr", "a_lna",
            "a_ol", "f_h", "f_l", "pm", "boost", "pef", "iref", "cpf_um", "design", "delivered", "label"]
    C = {k: [] for k in keys}

    def add(row):
        for k in keys:
            C[k].append(B.r(row.get(k)))

    pts = D["sweep"].get("points") or []
    for i, p in enumerate(pts):
        add({"kind": "dse", "arch": p["arch"], "supply": f"{p['vdd']:g} V", "vdd": p["vdd"], "tier": tier_of(D, p["p_total_nw"]),
             "pareto": "yes" if p.get("pareto") else "no", "window": "yes" if p.get("in_power_window") else "no",
             "power": B.mul(p.get("p_total_nw"), 1e-9), "irn": B.mul(p.get("irn_rms_uv"), 1e-6), "zin": B.mul(p.get("zin_50hz_mohm"), 1e6),
             "nef": p.get("nef"), "gain": p.get("a_mid_db"), "dr": p.get("dr_db"), "a_lna": p.get("a_lna_db"), "a_ol": p.get("a_ol_db"),
             "f_h": p.get("f_h_hz"), "f_l": p.get("f_l_hz"), "pm": p.get("pm_deg"), "boost": p.get("zin_boost_x"), "pef": p.get("pef"),
             "iref": B.mul(p.get("iref_core_na"), 1e-9), "cpf_um": p.get("c_pf_um"), "design": None, "delivered": False,
             "label": f"DSE #{i + 1} · {p.get('arch_short', p['arch'])} · {p['vdd']:g} V"})
    for c in D["cards"]:
        sz = D["card_json"][c["card_id"]].get("sizing") or {}
        t = D["tier"][c["tier"]]
        for stage, key, slab in STAGE_KEY:
            s = c.get(key)
            if not s:
                continue
            fh = D["fh"][c["card_id"]][stage]
            add({"kind": stage, "stage": stage, "arch": c["arch"], "supply": f"{c['vdd']:g} V", "vdd": c["vdd"], "tier": c["tier"],
                 "window": "yes" if t["p_min_nw"] <= s["p_total_nw"] <= t["p_max_nw"] else "no",
                 "power": B.mul(s.get("p_total_nw"), 1e-9), "irn": B.mul(s.get("irn_rms_chopped_uv"), 1e-6),
                 "zin": B.mul(s.get("zin_50hz_ibl_on_mohm"), 1e6), "nef": s.get("nef"), "gain": s.get("a_mid_db"), "dr": s.get("dr_db"),
                 "a_lna": s.get("a_lna_db"), "a_ol": s.get("a_ol_db"), "f_h": fh["sim"], "f_l": s.get("f_l_hz"), "pm": s.get("pm_deg"),
                 "boost": s.get("zin_boost_factor"), "pef": s.get("pef"), "iref": B.mul(sz.get("iref_core_na"), 1e-9), "cpf_um": sz.get("c_pf_um"),
                 "design": c["card_id"], "delivered": True, "label": f"{c['card_id']} ({slab} deliverable)"})
    B.write_json(out / "data" / "dse.json", {"columns": C})

    tiers = meta["power_tiers"]
    bst = [c["pre"]["zin_boost_factor"] for c in D["cards"]]
    bmin, bmax = min(bst), max(bst)
    dmin, dmax = min(p["zin_boost_x"] for p in pts), max(p["zin_boost_x"] for p in pts)
    pmin, pmax = min(p["p_total_nw"] for p in pts), max(p["p_total_nw"] for p in pts)
    betas = sorted({c["beta_ibl"] for c in D["cards"]})
    cpfs = sorted({p["c_pf_um"] for p in pts})
    dims = DSE_DIMS + [
        {"key": "arch", "label": "Architecture", "type": "cat", "labels": alab, "order": [a["id"] for a in archs],
         "colors": {a["id"]: B.ARCH_COLORS[i] for i, a in enumerate(archs)}},
        {"key": "supply", "label": "Supply", "type": "cat", "order": ["1.8 V", "3.3 V"]},
        {"key": "kind", "label": "Point type", "type": "cat", "order": ["dse", "pre", "partial"],
         "labels": {"dse": "DSE candidate (schematic)", "pre": "Deliverable · pre-PEX", "partial": "Deliverable · partial post-PEX"},
         "colors": {"dse": "#94a3b8", "pre": "#225bb2", "partial": "#dc2626"}},
        {"key": "tier", "label": "Power tier", "type": "cat", "order": [t["tag"] for t in tiers] + ["out"],
         "labels": {**{t["tag"]: f"{t['short_label']} ({t['tag'].upper()})" for t in tiers}, "out": "outside tiers"}},
        {"key": "pareto", "label": "Repo Pareto flag (DSE)", "type": "cat", "order": ["yes", "no"]},
        {"key": "window", "label": "Inside tier power window", "type": "cat", "order": ["yes", "no"]},
    ]
    n_dse, n_par = len(pts), sum(1 for p in pts if p.get("pareto"))
    explorer = {
        "type": "explorer", "src": "hub/data/dse.json", "dims": dims,
        "x": "power", "y": "irn", "color": "arch", "symbol": "kind",
        "filters": ["arch", "supply", "kind", "tier", "pareto", "window", "power", "zin"],
        "highlight": "delivered", "highlight_label": "Delivered cards (ring)", "design_key": "design", "label_key": "label", "stage_group": "design",
        "hover": ["arch", "kind", "supply", "tier", "a_lna", "f_h", "zin", "boost", "gain", "nef", "iref", "cpf_um"],
        "height": 560,
        "presets": [
            {"label": "Chopped IRN vs power (old default)", "x": "power", "y": "irn", "color": "arch", "symbol": "kind"},
            {"label": "Colour by point type (DSE vs deliverable)", "x": "power", "y": "irn", "color": "kind", "symbol": "arch"},
            {"color": "arch", "symbol": "kind", "label": "|Z_in| vs power", "x": "power", "y": "zin"},
            {"color": "arch", "symbol": "kind", "label": "NEF vs power", "x": "power", "y": "nef"},
            {"color": "arch", "symbol": "kind", "label": "A_mid vs power", "x": "power", "y": "gain"},
            {"color": "arch", "symbol": "kind", "label": "DR vs chopped IRN", "x": "irn", "y": "dr"},
            {"color": "arch", "symbol": "kind", "label": "f_H vs power", "x": "power", "y": "f_h"},
            {"color": "arch", "symbol": "kind", "label": "|Z_in| vs C_pf (β_IBL knob)", "x": "cpf_um", "y": "zin", "logx": False},
            {"color": "arch", "symbol": "kind", "label": "Power vs I_ref,core", "x": "iref", "y": "power"},
            {"color": "arch", "symbol": "kind", "label": "Pareto: |Z_in| vs power", "x": "power", "y": "zin", "pareto": True},
            {"color": "arch", "symbol": "kind", "label": "Per architecture", "x": "power", "y": "zin", "facet": "arch"},
            {"color": "arch", "symbol": "kind", "label": "Per supply", "x": "power", "y": "irn", "facet": "supply"},
        ],
        "caption": "*Old caption: “" + T.EX_PLOT_CAP + "”* — **Hub encoding:** colour = architecture (same palette as the charts below), symbol = point type "
                   "(circle = DSE candidate, ✕ = pre-PEX deliverable, ◆ = partial post-PEX deliverable), ring = delivered card (click to open). The deliverable points "
                   "follow the global **Simulation** option (best available stage ≤ the selected one; pre-PEX and partial post-PEX values are identical on all 36 cards); "
                   "DSE candidates are schematic runs and always shown. Use *Colour by point type* for a legend of the point types; the Supply chips replace the old supply filter.",
    }

    def irn_chart(vdd, stage, key):
        traces = []
        for i, a in enumerate(archs):
            cs = sorted([c for c in D["cards"] if c["arch"] == a["id"] and c["vdd"] == vdd and c.get(key)], key=lambda c: c[key]["p_total_nw"])
            if cs:
                traces.append(B.tr([c[key]["p_total_nw"] for c in cs], [c[key]["irn_rms_chopped_uv"] for c in cs], a["name"], B.ARCH_COLORS[i],
                                   mode="lines+markers", customdata=[c["card_id"] for c in cs]))
        return B.chart(T.EX_CHARTS[0][0], traces, "Total Power Consumption (nW)", "Chopped Input-Referred Noise (µVrms)", logx=True,
                       caption=T.EX_CHARTS[0][1] + " · chopped IRN is a model figure. Click a point to open the card.", stage=stage, alt="irnp", link_designs=True)

    def zin_chart(vdd, stage, key):
        traces = []
        for i, a in enumerate(archs):
            cs = [c for c in D["cards"] if c["arch"] == a["id"] and c["vdd"] == vdd and c.get(key)]
            cs.sort(key=lambda c: [t["tag"] for t in tiers].index(c["tier"]))
            if cs:
                traces.append(B.bar([c["tier_short"] for c in cs], [c[key]["zin_50hz_ibl_on_mohm"] for c in cs], a["name"], B.ARCH_COLORS[i],
                                    customdata=[c["card_id"] for c in cs]))
        return B.chart(T.EX_CHARTS[1][0], traces, "Power Tier", "|Zin @ 50Hz| (MΩ)", logy=True,
                       caption=T.EX_CHARTS[1][1] + f". *Hub: the stored boost factors of the 36 cards span {bmin:.1f}–{bmax:.1f}× (DSE {dmin:.1f}–{dmax:.1f}×).* Click a bar to open the card.",
                       layout={"barmode": "group", "xaxis": {"type": "category"}, "hovermode": "closest"}, stage=stage, alt="zint", link_designs=True)

    def arch_table(stage, key):
        rows = []
        for a in archs:
            cs = [c for c in D["cards"] if c["arch"] == a["id"] and c.get(key)]
            if not cs:
                continue
            mean = lambda f: sum(c[key][f] for c in cs) / len(cs)  # noqa: E731
            c0 = D["card_json"][cs[0]["card_id"]].get("reused_blocks") or {}
            ln = [c[key]["irn_rms_chopped_uv"] for c in cs if c["tier"] == "ln"]
            ota = B.link(c0.get("core_ota_id"), B.opa_href(c0.get("core_ota_id"))) + (
                f"<br><small>Aux: {B.link(c0['aux_ota_id'], B.opa_href(c0['aux_ota_id']))}</small>" if c0.get("aux_ota_id") else "")
            rows.append({"arch": f"<b>{a['name']}</b><br><small>{a['title']}</small>", "mech": f"{a['ibl_type']}<br><small>HPF: {a['hpf_type']}</small>", "ota": ota,
                         "gain": B.r(mean("a_mid_db")), "zin": B.r(mean("zin_50hz_ibl_on_mohm") * 1e6), "boost": B.r(mean("zin_boost_factor")),
                         "irn": B.r(min(ln) * 1e-6) if ln else None, "nef": B.r(min(c[key]["nef"] for c in cs)),
                         "area": B.r(sum((c.get("physical") or {}).get("area_um2") or 0 for c in cs) / len(cs))})
        return B.table("", [
            B.col("arch", "Architecture", md=True, wrap=True), B.col("gain", "Gain* (dB)", digits=4, title="mean AFE gain (model: sim LNA + ideal VGA)"),
            B.col("zin", "|Z<sub>in</sub>(50Hz)|", "Ω", si=True, digits=3, better="high", title="mean"), B.col("boost", "Boost (×)", digits=3, better="high", title="mean"),
            B.col("irn", "LN IRN*", "Vrms", si=True, digits=3, better="low", title="best chopped IRN of the LN cards (model)"),
            B.col("nef", "NEF*", digits=3, better="low", title="best NEF (model)"), B.col("area", "Area (μm²)", digits=5, better="low", title="mean"),
            B.col("mech", "Impedance-boosting / high-pass mechanism", md=True, wrap=True),
            B.col("ota", "Reused core / aux OTAs", md=True, wrap=True)], rows, stage=stage, alt="archtab", search=False,
            caption="Means over the 6 cards of each architecture (both supplies, all tiers) for gain, |Z_in|, boost and area; LN IRN and NEF are the best values; "
                    "* = model-derived. Core/aux OTAs of the first card (1.8 V); OTA links open the reused op-amp on the hub.")

    blocks = [
        B.section("Interactive Pareto trade-off explorer", [B.note("<b>Data provenance of the sweep (hub check):</b> in `data/sweep.json` the fields `a_mid_db`, `a_ol_db`, `nef`, `pef`, `irn_rms_uv` and `dr_db` were "
               "overwritten by `scripts/refresh_all_36_farm.py` with closed-form formulas (per-architecture constants for the VGA gain, A_OL and NEF); power, "
               "f_H, f_L, |Z_in|, boost and the LNA gain come from the farm sweep (PM is a peaking-based estimate). Dimensions marked *(model)* are therefore "
               "formula values. The old explorer's default axes (chopped IRN vs power) referenced field names that do not exist in `sweep.json`, so it showed "
               "only the 72 deliverable markers; the hub plots all " + f"{n_dse} DSE points.", "warn"),
        B.stats([{"label": "DSE candidates", "value": f"{n_dse}"}, {"label": "repo Pareto-flagged", "value": f"{n_par}"},
                 {"label": "delivered cards", "value": f"{len(D['cards'])}", "sub": "each shown at pre-PEX and partial post-PEX"},
                 {"label": "swept knobs", "value": "I_ref,core · C_pf", "sub": "per architecture × supply (27 points each)"}]),
        explorer]),
        B.section("Architecture curves (deliverable cards)", [{"type": "tabs", "id": "curves", "tabs": [
            {"label": f"V<sub>DD</sub> = {v:g} V", "vdd": v, "blocks": [B.section("", [irn_chart(v, st, k) for st, k, _ in STAGE_KEY] + [zin_chart(v, st, k) for st, k, _ in STAGE_KEY], cols=2)]}
            for v in (1.8, 3.3)]}],
                  intro="One supply tab drives both charts (as the old supply filter did); both follow the global **Simulation** option (pre-PEX or partial post-PEX)."),
        B.section("Architecture trade-off comparison across the 6 explored input topologies", [arch_table(st, k) for st, k, _ in STAGE_KEY]),
    ]
    intro = B.intro_md(T.EX_EYEBROW, T.EX_H1.replace("324", f"{n_dse}"), T.EX_P) + (
        f"\n\n> *Hub check of this text:* the stored DSE powers span {pmin:.1f}–{pmax:.1f} nW; every delivered card has β<sub>IBL</sub> = "
        f"{', '.join(f'{b:g}' for b in betas)} and the swept IBL knob is the C<sub>pf</sub> MIM size ({', '.join(f'{x:g}' for x in cpfs)} µm) together with I<sub>ref,core</sub>; "
        "only part of each point is simulated (see the provenance note below). The hub draws circles / ✕ / ◆ and rings instead of the old diamonds and stars.")
    B.write_json(out / "pages" / "explore.json", {"intro": intro, "blocks": blocks})


# ----------------------------------------------------------------------------- sensitivity
def sens_page(D, out: Path):
    S = D["sens"]
    sm = S.get("summary") or {}
    top = sm.get("top_variation_sources") or []
    archs = sm.get("by_architecture") or []
    cards = S.get("cards") or {}
    s1, s2 = (top + [{}, {}])[:2]
    m1, m2 = s1.get("spectre_mean") or {}, s2.get("spectre_mean") or {}
    kpis = B.stats([
        {"label": "cards verified in Spectre & HSPICE", "value": f"{sm.get('spectre_ok_count', '—')}/{sm.get('total_cards', 36)} · {sm.get('hspice_ok_count', '—')}/{sm.get('total_cards', 36)}"},
        {"label": f"±{abs(m1.get('sigma3_zin_pct') or 0):.1f}% 3σ |Zin| shift (S = {m1.get('S_zin', 0):+.1f})", "value": f"#1: {s1.get('short', '—')}"},
        {"label": f"±{abs(m2.get('sigma3_fh_pct') or 0):.1f}% 3σ fH shift (S = {m2.get('S_fh', 0):+.2f})", "value": f"#2: {s2.get('short', '—')}"},
        {"label": "3σ PVT variation reduction with 6 trim DACs (assumed factors)", "value": "8×–12.5×"},
    ], caption="The old site hard-coded “S = +11.9” / “S = +0.92” in these tiles; the hub shows the stored 36-card Spectre means.")
    dom = B.section(T.SE_DOM_H2, [B.note(T.SE_NOTICES[0][1], "warn"), B.note(T.SE_NOTICES[1][1], "good"),
                                 B.md("\n".join(f"- {x}" for x in T.SE_LISTS[0])), B.md("\n".join(f"- {x}" for x in T.SE_LISTS[1]))], cols=2)
    honesty = B.note("<b>Hub note on provenance:</b> the 3σ input spreads of the 10 sources (`sigma3_spec`) are assumed magnitudes coded in `ecggen/sens.py`; "
                     "Spectre/HSPICE evaluate the perturbed schematic netlists. All *post-calibration* values are the uncalibrated shifts divided by an assumed "
                     "per-source reduction factor (`post_cal_reduction`, 5–12.5×) — no trim cell was designed or simulated. The prose figures above are quoted "
                     "verbatim from the old site and partly differ from the stored means (e.g. S<sup>Zin</sup><sub>Cpf</sub> = +14.0 mean vs “+9.8 to +11.9”).", "muted")
    mlabels = dict(T.SE_METRIC_OPTS)
    xlab = {"severity_score": "Composite 3σ PVT Severity Score", "sigma3_zin_pct": "3σ Boosted Input Impedance Shift Δ|Zin(50Hz)| (%)",
            "sigma3_fh_pct": "3σ Low-Pass Bandwidth Shift ΔfH (%)", "sigma3_fl_pct": "3σ High-Pass Cutoff Shift ΔfL (%)",
            "sigma3_aol_db": "3σ Core OTA Open-Loop Gain Shift ΔAOL (dB)", "sigma3_vout_mv": "3σ Output DC Offset / Ripple Shift ΔVout,DC (mV)",
            "sigma3_pwr_pct": "3σ Quiescent Power Shift ΔPcore (%)"}
    torn_tabs = []
    for mk, ml in T.SE_METRIC_OPTS:
        srt = sorted(top, key=lambda s: abs((s.get("spectre_mean") or {}).get(mk) or 0))
        torn_tabs.append({"label": ml, "blocks": [B.chart(T.SE_CHARTS[0][0], [
            B.hbar([(s.get("spectre_mean") or {}).get(mk) or 0 for s in srt], [s["short"] for s in srt], "Cadence Spectre (~/model-gf180 sm141064.scs)", "#d96b27"),
            B.hbar([(s.get("hspice_mean") or {}).get(mk) or 0 for s in srt], [s["short"] for s in srt], "Synopsys HSPICE (~/model-gf180 sm141064.hspice)", "#1e8565")],
            xlab.get(mk, mlabels.get(mk, mk)), "", layout={"barmode": "group", "margin": {"l": 175, "r": 22, "t": 56, "b": 52}, "hovermode": "closest"},
            height=460, caption=T.SE_CHARTS[0][1])]})
    sub = top[:7]
    pre = [max(abs((s.get("spectre_mean") or {}).get("sigma3_zin_pct") or 0), abs((s.get("spectre_mean") or {}).get("sigma3_fh_pct") or 0),
               abs((s.get("spectre_mean") or {}).get("sigma3_fl_pct") or 0) * 0.5, abs((s.get("spectre_mean") or {}).get("sigma3_vout_mv") or 0)) for s in sub]
    post = [round(v / (s.get("post_cal_reduction") or 8), 2) for v, s in zip(pre, sub)]
    cal = B.chart(T.SE_CHARTS[1][0], [B.bar([s["short"] for s in sub], pre, "Uncalibrated 3σ Spread (% / mV)", B.BAD_C),
                                      B.bar([s["short"] for s in sub], post, "Post-Calibration 3σ Residual", B.GOOD_C)],
                  "Dominant Variation Sources", "Peak 3σ Metric Shift (% or mV)", layout={"barmode": "group", "margin": {"b": 90}, "hovermode": "closest"},
                  height=440, caption=T.SE_CHARTS[1][1] + " *Hub: residual = uncalibrated ÷ assumed reduction factor (not simulated); the f_L term is weighted ×0.5 as on the old site.*")
    arch_chart = B.chart(T.SE_CHARTS[2][0], [B.bar([a["arch_name"] for a in archs], [(a.get("severity_by_source") or {}).get(s["id"], 0) for a in archs], s["short"],
                                                   B.ARCH_COLORS[i % len(B.ARCH_COLORS)]) for i, s in enumerate(top[:5])],
                         "Chopping + Input Impedance Boost Architecture", "Composite 3σ Severity Score",
                         layout={"barmode": "group", "hovermode": "closest"}, height=440, caption=T.SE_CHARTS[2][1])
    card_tabs = []
    for k, cc in cards.items():
        spS, hsS = (cc.get("spectre") or {}).get("sources") or {}, (cc.get("hspice") or {}).get("sources") or {}
        lst = [spS[i] for i in ((cc.get("spectre") or {}).get("ranking") or list(spS)) if i in spS]
        if not lst:
            continue
        x = [s["short"] for s in lst]
        card_tabs.append({"label": f"{k} — {cc.get('arch_short', '')} (VDD={cc.get('vdd')}V, {str(cc.get('tier', '')).upper()})", "vdd": cc.get("vdd"), "key": k, "blocks": [B.chart(T.SE_CHARTS[3][0], [
            B.bar(x, [s.get("sigma3_zin_pct") for s in lst], "Spectre 3σ Δ|Zin| (%)", "#225bb2"),
            B.bar(x, [(hsS.get(s["id"]) or {}).get("sigma3_zin_pct", s.get("sigma3_zin_pct")) for s in lst], "HSPICE 3σ Δ|Zin| (%)", "#0d8499"),
            B.bar(x, [s.get("sigma3_fh_pct") for s in lst], "Spectre 3σ ΔfH (%)", "#d96b27"),
            B.bar(x, [s.get("sigma3_vout_mv") for s in lst], "Spectre 3σ ΔVout (mV)", "#934eb0")],
            f"Variation Sources for {k}", "3σ Shift (% or mV)", layout={"barmode": "group", "margin": {"b": 110}, "hovermode": "closest"}, height=460,
            caption=T.SE_CHARTS[3][1] + f" · [open card](#/ecg/{k})")]})
    rows = []
    for s in top:
        a, h = s.get("spectre_mean") or {}, s.get("hspice_mean") or {}
        rows.append({"rank": f"#{s.get('rank')}", "src": f"<b>{s.get('name')}</b><br><small>{s.get('category', '')} · 3σ spread `{s.get('sigma3_spec', '')}`</small>",
                     "szin": B.r(a.get("S_zin")), "dzin": B.r(a.get("sigma3_zin_pct")), "dzinh": B.r(h.get("sigma3_zin_pct")), "sfh": B.r(a.get("S_fh")),
                     "dfh": B.r(a.get("sigma3_fh_pct")), "dfl": B.r(a.get("sigma3_fl_pct")), "daol": B.r(a.get("sigma3_aol_db")), "dv": B.r(a.get("sigma3_vout_mv")),
                     "cell": f"<b>`{s.get('cal_cell', '')}`</b><br><small><b>{s.get('cal_bits')}-bit</b>, {s.get('cal_range', '')} — {s.get('cal_target', '')}</small>",
                     "post": f"ΔZin {B.nf(a.get('post_cal_zin_pct'), 1)}%<br>ΔfH {B.nf(a.get('post_cal_fh_pct'), 1)}%<br>ΔVout {B.nf(a.get('post_cal_vout_mv'), 1)} mV"})
    cal_table = B.table(T.SE_TABLES[0][0], [
        B.col("rank", "#"), B.col("src", "Variation source · 3σ spread", md=True, wrap=True), B.col("cell", "Tunability / calibration cell (bits, range, target)", md=True, wrap=True),
        B.col("szin", "S<sup>Zin</sup>", digits=3, group="Spectre mean"), B.col("dzin", "Δ|Zin| %", digits=3, group="Spectre mean"),
        B.col("sfh", "S<sup>fH</sup>", digits=3, group="Spectre mean"), B.col("dfh", "ΔfH %", digits=3, group="Spectre mean"), B.col("dfl", "ΔfL %", digits=3, group="Spectre mean"),
        B.col("daol", "ΔAOL dB", digits=3, group="Spectre mean"), B.col("dv", "ΔVout mV", digits=3, group="Spectre mean"),
        B.col("dzinh", "Δ|Zin| %", digits=3, group="HSPICE"), B.col("post", "Post-cal residual (assumed)", md=True)], rows, search=False,
        caption=T.SE_TABLES[0][1] + " *Hub: post-cal residuals are assumed reductions, see note above.*")
    arows = [{"arch": f"<b>{a['arch_name']}</b> · {a['arch_short']}", "top": f"{a['ibl_type']}<br><small>{a['hpf_type']}</small>",
              "t3": "<br>".join(f"`#{i + 1}:{x}`" for i, x in enumerate(a.get("top3_sources") or [])),
              "z": B.r(abs((a.get("sigma3_zin_by_source") or {}).get("cpf_ratio", 0))), "fh": B.r(abs((a.get("sigma3_fh_by_source") or {}).get("ibias_core", 0))),
              "fl": B.r(-abs((a.get("sigma3_fl_by_source") or {}).get("r_pr_vth", 0))), "aol": B.r(-abs((a.get("sigma3_aol_by_source") or {}).get("vth_skew_np", 0))),
              "v": B.r(abs((a.get("sigma3_vout_by_source") or {}).get("vth_mismatch_in", 0)))} for a in archs]
    arch_table = B.table(T.SE_TABLES[1][0], [
        B.col("arch", "Architecture", md=True, wrap=True), B.col("top", "IBL & HPF topology", md=True, wrap=True), B.col("t3", "Top 3 variation sources", md=True, wrap=True),
        B.col("z", "Δ|Zin| % ← ΔCpf", digits=4, group="3σ shift"), B.col("fh", "ΔfH % ← ΔIbias", digits=4, group="3σ shift"),
        B.col("fl", "ΔfL % ← ΔR_PR", digits=4, group="3σ shift"), B.col("aol", "ΔAOL dB ← ΔVth,n/p", digits=3, group="3σ shift"),
        B.col("v", "±ΔVout mV ← ΔVth,in", digits=4, group="3σ shift")], arows, search=False, caption=T.SE_TABLES[1][1])
    blocks = [kpis, dom, honesty,
              B.section("", [{"type": "tabs", "id": "tornado", "style": "select", "label": "Target metric for tornado plot", "tabs": torn_tabs}]),
              B.section("", [cal, arch_chart], cols=2),
              B.section("", [{"type": "tabs", "id": "senscard", "style": "select", "label": "Inspect specific design card", "tabs": card_tabs,
                              "caption": "The card list follows the global V<sub>DD</sub> option."}]),
              B.section("", [cal_table]), B.section("", [arch_table])]
    B.write_json(out / "pages" / "sens.json", {"intro": B.intro_md(T.SE_EYEBROW, T.SE_H1, T.SE_P), "blocks": blocks})


# ----------------------------------------------------------------------------- simulator cross-check
SIM_STYLES = [
    ("ngspice_pdk", "ngspice-46 (Open PDK, gmin=1e-12)", "#225bb2", "solid", 2.6),
    ("spectre_commercial", "Spectre (~/model-gf180 Rev9, gmin=1e-12)", "#d96b27", "dash", 2.4),
    ("hspice_commercial", "HSPICE (~/model-gf180 Rev9, gmin=1e-12)", "#1e8565", "dot", 2.4),
    ("spectre_pdk", "Spectre (Open PDK, gmin=1e-12)", "#934eb0", "dashdot", 2.0),
    ("spectre_commercial_gmin15", "Spectre (~/model-gf180 Rev9, gmin=1e-15)", "#c93b5b", "longdash", 2.0),
    ("ngspice_pdk_gmin15", "ngspice-46 (Open PDK, gmin=1e-15) — not plotted on the old site", "#0d8499", "longdashdot", 1.6),
]


def xsim_page(D, out: Path):
    X = D["xsim"]
    sm = X.get("summary") or {}
    sp_s, hs_s = sm.get("spectre_vs_ngspice") or {}, sm.get("hspice_vs_ngspice") or {}
    devs, cards = X.get("devices") or {}, X.get("cards") or {}
    kpis = B.stats([
        {"label": "mean |ΔGain| (Spectre ~/model-gf180 vs ngspice-46)", "value": f"{B.nf(sp_s.get('mean_abs_gain_delta_db'), 3)} dB"},
        {"label": "mean |ΔfH| bandwidth difference across 36 cards", "value": f"{B.nf(sp_s.get('mean_rel_fh_delta_pct'))}%"},
        {"label": "mean |ΔPower| subthreshold current difference", "value": f"{B.nf(sp_s.get('mean_rel_power_delta_pct'))}%"},
        {"label": "engine delta on identical BSIM4.5 model card", "value": "<0.05%"},
    ])
    concl = B.section(T.XS_CONC_H2, [B.note(T.XS_NOTICES[0][1], "good"), B.note(T.XS_NOTICES[1][1], "warn"),
                                     B.md("\n".join(f"- {x}" for x in T.XS_LISTS[0])), B.md("\n".join(f"- {x}" for x in T.XS_LISTS[1]))], cols=2)
    # hub data check of the quoted gm/gds numbers
    d8 = devs.get("pfet_03v3_L8.0u_tt_27C") or {}
    g12 = ((d8.get("simulators") or {}).get("spectre_commercial") or {}).get("vds_sweep", {}).get("gm_gds_vds09_vv")
    g15 = ((d8.get("simulators") or {}).get("spectre_commercial_gmin15") or {}).get("vds_sweep", {}).get("gm_gds_vds09_vv")
    hs_aol = sorted({(c.get("simulators") or {}).get("hspice", {}).get("aol_db") for c in cards.values()} - {None})
    pm_vals = [(c.get("simulators") or {}).get("ngspice", {}).get("pm_deg") for c in cards.values()]
    pm_txt = ", ".join(f"{v:g}° on {pm_vals.count(v)} cards" for v in sorted(set(pm_vals) - {None}, reverse=True))
    check = B.note(
        "<b>Hub data check (stored numbers vs the prose above):</b> "
        f"mean |ΔGain| Spectre−ngspice = {sp_s.get('mean_abs_gain_delta_db')} dB (max {sp_s.get('max_abs_gain_delta_db')} dB), HSPICE−ngspice = "
        f"{hs_s.get('mean_abs_gain_delta_db')} dB; mean |Δf_H| = {sp_s.get('mean_rel_fh_delta_pct')} %, mean |ΔP| = {sp_s.get('mean_rel_power_delta_pct')} %, "
        f"mean |Δ|Z_in|| = {sp_s.get('mean_rel_zin_delta_pct')} % — far tighter than the quoted 0.02–0.14 dB / 1.8 % / 1.5 % / 2.5 %. "
        f"For `pfet_03v3` L = 8 µm (tt, 27 °C) the stored Spectre g<sub>m</sub>/g<sub>ds</sub> at V<sub>DS</sub> = 0.9 V is {g12} V/V at gmin = 1e-12 and {g15} V/V at "
        "gmin = 1e-15 (the prose quotes 67.7 → 3340.7 V/V). HSPICE A_OL reads " + ", ".join(f"{v:g}" for v in hs_aol[:4]) +
        (" …" if len(hs_aol) > 4 else "") + " dB on the cards (extraction artefact), the PM reads " + pm_txt + " (90° = clamp of the 45–90° extraction window, 72° = its default when no "
        "loop-gain crossing is found), the ngspice/Spectre/HSPICE "
        "noise rows reuse the model chopped IRN, and Benchmark B is a separate `ecggen/xsim.py` run whose |Z_in| definition gives ≈0.49× the TB3 value; "
        "for several 3.3 V current-reuse cards its gain, A_OL and |Z_in| differ strongly from the card's own TB1/TB3 values.", "muted")

    def sim_fig(dev, kind):
        traces = []
        for sk, lab, colr, dash, w in SIM_STYLES:
            so = (dev.get("simulators") or {}).get(sk) or {}
            if not so.get("ok"):
                continue
            vs, vd = so.get("vgs_sweep") or {}, so.get("vds_sweep") or {}
            if kind == "a1" and vs.get("vgs_v"):
                traces.append(B.tr(vs["vgs_v"], vs["id_amp"], lab, colr, dash, w))
            if kind == "a2" and vs.get("vgs_v"):
                traces.append(B.tr(vs["vgs_v"], vs["gm_id_v"], lab, colr, dash, w))
            if kind == "a3" and vd.get("vds_v"):
                traces.append(B.tr(vd["vds_v"], vd["gm_gds_vv"], lab, colr, dash, w))
        ax = {"a1": ("|VGS| (V)", "Drain Current ID (A)", False, True), "a2": ("|VGS| (V)", "gm / ID (V⁻¹)", False, False),
              "a3": ("|VDS| (V) [at |VGS| = 0.36 V]", "Intrinsic Gain gm / gds (V/V)", False, False)}[kind]
        return B.fig(traces, ax[0], ax[1], ax[2], ax[3], layout={"hovermode": "closest" if kind == "a1" else "x unified"})

    dev_tabs, dkeys = [], list(devs)
    for k in dkeys:
        d = devs[k]
        blocks = []
        for kind, (title, cap) in zip(("a1", "a2", "a3"), T.XS_CHARTS[:3]):
            rel = f"data/xsim/{k}-{kind}.json"
            B.write_json(out / rel, sim_fig(d, kind))
            blocks.append({"type": "chart", "title": title, "src": f"hub/{rel}", "caption": cap})
        dev_tabs.append({"key": k, "label": f"{d.get('dev_type')} · W={d.get('w_um')}μm, L={d.get('l_um')}μm (m={d.get('m')}) · corner={d.get('corner')}, T={d.get('temp_c')}°C",
                         "blocks": [B.section("", blocks, cols=3)]})
    card_tabs = []
    for k, c in cards.items():
        blocks = []
        for kind, (title, cap), yl, logy in (("b1", T.XS_CHARTS[3], "Closed-Loop Gain |A_CL(f)| (dB)", False), ("b2", T.XS_CHARTS[4], "Boosted Input Impedance |Zin(f)| (MΩ)", True)):
            traces = []
            for sk, lab, colr, dash in (("ngspice", "ngspice-46 (Open PDK)", "#225bb2", "solid"), ("spectre", "Cadence Spectre (~/model-gf180 Rev9)", "#d96b27", "dash"),
                                        ("hspice", "Synopsys HSPICE (~/model-gf180 Rev9)", "#1e8565", "dot")):
                sc = (c.get("simulators") or {}).get(sk) or {}
                a = sc.get("ac_curve") or {}
                if sc.get("ok") and a.get("freq_hz"):
                    traces.append(B.tr(a["freq_hz"], a["gain_db" if kind == "b1" else "zin_mohm"], lab, colr, dash, 2.4))
            rel = f"data/xsim/{k}-{kind}.json"
            B.write_json(out / rel, B.fig(traces, "Frequency (Hz)", yl, True, logy))
            blocks.append({"type": "chart", "title": title, "src": f"hub/{rel}", "caption": cap + f" · [open card](#/ecg/{k})"})
        card_tabs.append({"label": f"{k} — {c.get('arch_short')} (VDD={c.get('vdd')}V, {str(c.get('tier', '')).upper()})", "vdd": c.get("vdd"), "key": k, "blocks": [B.section("", blocks, cols=2)]})
    ptr, all_ng = [], []
    for vdd in (1.8, 3.3):
        ng_p, sp_p, hs_p, names = [], [], [], []
        for c in cards.values():
            if c.get("vdd") != vdd:
                continue
            s = c.get("simulators") or {}
            ng, sp, hs = s.get("ngspice") or {}, s.get("spectre") or {}, s.get("hspice") or {}
            if ng.get("ok") and sp.get("ok"):
                ng_p.append(ng["p_tot_nw"]); sp_p.append(sp["p_tot_nw"]); hs_p.append(hs["p_tot_nw"] if hs.get("ok") else sp["p_tot_nw"]); names.append(c["card_id"])
        all_ng += ng_p
        ptr += [B.tr(ng_p, sp_p, f"Cadence Spectre (~/model-gf180) · {vdd:g} V", "#d96b27", mode="markers", text=names, customdata=names,
                     marker={"color": "#d96b27", "size": 8.5, "symbol": "circle" if vdd < 2 else "circle-open"}, meta={"vdd": vdd}),
                B.tr(ng_p, hs_p, f"Synopsys HSPICE (~/model-gf180) · {vdd:g} V", "#1e8565", mode="markers", text=names, customdata=names,
                     marker={"color": "#1e8565", "size": 8, "symbol": "diamond" if vdd < 2 else "diamond-open"}, meta={"vdd": vdd})]
    lo, hi = min(all_ng) * 0.9, max(all_ng) * 1.08
    parity = B.chart(T.XS_CHARTS[5][0], [B.tr([lo, hi], [lo, hi], "1:1 Ideal Parity Line", "#94a3b8", "dash", 1.5)] + ptr,
        "ngspice-46 Core Supply Power (nW)", "Spectre / HSPICE Core Supply Power (nW)", layout={"hovermode": "closest"}, height=440,
        caption=T.XS_CHARTS[5][1] + " · click a point to open the card.", link_designs=True)
    arows = []
    for d in devs.values():
        s = d.get("simulators") or {}
        ng, sp, hs = (s.get("ngspice_pdk") or {}).get("vgs_sweep") or {}, (s.get("spectre_commercial") or {}).get("vgs_sweep") or {}, (s.get("hspice_commercial") or {}).get("vgs_sweep") or {}
        v12 = (s.get("spectre_commercial") or {}).get("vds_sweep") or (s.get("ngspice_pdk") or {}).get("vds_sweep") or {}
        v15 = (s.get("spectre_commercial_gmin15") or {}).get("vds_sweep") or (s.get("ngspice_pdk_gmin15") or {}).get("vds_sweep") or {}
        arows.append({"dev": f"`{d.get('dev_type')}`", "l": d.get("l_um"), "ct": f"`{d.get('corner')}` · {d.get('temp_c'):g}°C",
                      "g1": B.r(ng.get("gmid_vgs035")), "g2": B.r(sp.get("gmid_vgs035")), "g3": B.r(hs.get("gmid_vgs035")),
                      "i1": B.r(ng.get("id_vgs035_na")), "i2": B.r(sp.get("id_vgs035_na")), "i3": B.r(hs.get("id_vgs035_na")),
                      "ss": B.r(sp.get("ss_mv_dec") if sp.get("ss_mv_dec") is not None else ng.get("ss_mv_dec")),
                      "gg": f"{B.nf(v12.get('gm_gds_vds09_vv'), 1)} → <b>{B.nf(v15.get('gm_gds_vds09_vv'), 1)} V/V</b>"})
    GA, GI = "g<sub>m</sub>/I<sub>D</sub> @ 0.35 V (V⁻¹)", "I<sub>D</sub> @ 0.35 V (nA)"
    tA = B.table(T.XS_TABLES[0][0], [
        B.col("dev", "Device sweep", md=True), B.col("l", "L (μm)"), B.col("ct", "Corner / temp", md=True),
        B.col("g1", "ngspice", digits=4, group=GA), B.col("g2", "Spectre", digits=4, group=GA), B.col("g3", "HSPICE", digits=4, group=GA),
        B.col("i1", "ngspice", digits=5, group=GI), B.col("i2", "Spectre", digits=5, group=GI), B.col("i3", "HSPICE", digits=5, group=GI),
        B.col("ss", "Slope S (mV/dec)", digits=4), B.col("gg", "g<sub>m</sub>/g<sub>ds</sub> @ V<sub>DS</sub> 0.9 V<br>gmin 1e-12 → 1e-15", md=True)],
        arows, search=False, caption=T.XS_TABLES[0][1] + " Spectre / HSPICE columns use the foundry ~/model-gf180 Rev9 decks.")
    brows = []
    for c in cards.values():
        s = c.get("simulators") or {}
        ng, sp, hs = s.get("ngspice") or {}, s.get("spectre") or {}, s.get("hspice") or {}
        brows.append({"_design": c["card_id"], "id": c["card_id"], "arch": c.get("arch_short"), "vdd": c.get("vdd"),
                      "cur": f"[curves](#/ecg?page=xsim&t.xsimb={c['card_id']})",
                      "g1": B.r(ng.get("gain_db")), "g2": B.r(sp.get("gain_db")), "g3": B.r(hs.get("gain_db")),
                      "aol": B.r(sp.get("aol_db") if sp.get("aol_db") is not None else ng.get("aol_db")),
                      "lna": B.r(sp.get("lna_gain_db") if sp.get("lna_gain_db") is not None else ng.get("lna_gain_db")),
                      "f1": B.r(ng.get("fh_hz")), "f2": B.r(sp.get("fh_hz")), "f3": B.r(hs.get("fh_hz")), "p1": B.r(ng.get("p_tot_nw")), "p2": B.r(sp.get("p_tot_nw")),
                      "z1": B.r(ng.get("zin_50hz_mohm")), "z2": B.r(sp.get("zin_50hz_mohm"))})
    G1, G2, G3, G4 = "AFE gain (dB)", "f<sub>H</sub> (Hz)", "P<sub>core</sub> (nW)", "|Z<sub>in</sub> @ 50 Hz| (MΩ)"
    tB = B.table(T.XS_TABLES[1][0], [
        B.col("id", "Card ID", type="design"), B.col("cur", "", md=True), B.col("vdd", "VDD (V)"),
        B.col("g1", "ng", digits=4, group=G1, title="ngspice-46"), B.col("g2", "Sp", digits=4, group=G1, title="Spectre"), B.col("g3", "HS", digits=4, group=G1, title="HSPICE"),
        B.col("aol", "OTA A<sub>OL</sub> (dB)", digits=4), B.col("lna", "LNA gain (dB)", digits=4),
        B.col("f1", "ng", digits=5, group=G2, title="ngspice-46"), B.col("f2", "Sp", digits=5, group=G2, title="Spectre"), B.col("f3", "HS", digits=5, group=G2, title="HSPICE"),
        B.col("p1", "ng", digits=4, group=G3, title="ngspice-46"), B.col("p2", "Sp", digits=4, group=G3, title="Spectre"),
        B.col("z1", "ng", digits=5, group=G4, title="ngspice-46"), B.col("z2", "Sp", digits=5, group=G4, title="Spectre")], brows,
        caption=T.XS_TABLES[1][1].replace("or select it in the Benchmark B chart above", "(the *curves* link selects it in the Benchmark B dropdown above)")
        + " ng = ngspice-46 (open PDK), Sp = Cadence Spectre, HS = Synopsys HSPICE (~/model-gf180 Rev9).")
    dflt = dkeys.index("nfet_03v3_L1.0u_tt_27C") if "nfet_03v3_L1.0u_tt_27C" in dkeys else 0
    blocks = [kpis, concl, check,
              B.section("Benchmark A — transistor sweeps", [{"type": "tabs", "id": "xsima", "style": "select", "label": "Benchmark A transistor sweep", "default": dflt, "tabs": dev_tabs}]),
              B.section("Benchmark B — ECG front-end cards", [{"type": "tabs", "id": "xsimb", "style": "select", "label": "Benchmark B ECG front-end card", "tabs": card_tabs,
                                                               "caption": "The card list and the parity chart follow the global V<sub>DD</sub> option."}, parity]),
              B.section("", [tA]), B.section("", [tB])]
    B.write_json(out / "pages" / "xsim.json", {"intro": B.intro_md(T.XS_EYEBROW, T.XS_H1, T.XS_P), "blocks": blocks})


# ----------------------------------------------------------------------------- component reuse
def reuse_page(D, out: Path):
    comp = D["comps"]
    rk = comp.get("rankings") or {}
    sm = comp.get("summary") or {}
    opa = [x for x in rk.get("opa") or [] if x.get("load_tag") == "200f"][:14]
    sw, sa = (rk.get("switch") or [])[:12], (rk.get("sa") or [])[:12]
    used = {}
    for c in D["cards"]:
        rb = D["card_json"][c["card_id"]].get("reused_blocks") or {}
        for role, k, lib in (("core OTA", "core_ota_id", "opa"), ("aux OTA", "aux_ota_id", "opa"), ("chopper switch", "chop_sw_key", "switch"),
                             ("S&H switch", "sh_sw_key", "switch"), ("comparator", "comp_key", "sa")):
            if rb.get(k):
                e = used.setdefault((lib, rb[k]), {"roles": set(), "cards": []})
                e["roles"].add(role)
                if c["card_id"] not in e["cards"]:          # distinct cards (a flip card uses cmos_dummy as chopper *and* S&H)
                    e["cards"].append(c["card_id"])
    href = lambda lib, key, load=B.OTA_LOAD: B.opa_href(key, load) if lib == "opa" else f"#/{lib}/{key}"  # noqa: E731
    used_set = {k for _, k in used}
    ota_chart = B.chart("Top Reused OTAs from ../opa-gen-gemini4 (Composite LNA Score)", [
        B.bar([o["card_id"].replace("_0p1u_1u", "") for o in opa], [o.get("lna_score") for o in opa], "LNA Composite Score", "#225bb2"),
        B.bar([o["card_id"].replace("_0p1u_1u", "") for o in opa], [o.get("aux_score") for o in opa], "Aux/DSL/Buffer Score", "#1e8565")],
        "OTA Card ID (200 fF Library)", "Multi-Objective Score (0–100)",
        layout={"barmode": "group", "xaxis": {"type": "category", "tickangle": -30}, "margin": {"l": 58, "r": 20, "t": 56, "b": 120}, "hovermode": "closest"}, height=440)
    sw_chart = B.chart("Top Reused Switches from ../switch-gen-gemini4 (Chopper vs S&H Score)", [
        B.bar([s["key"].replace("__10u-100u", "") for s in sw], [s.get("chop_score") for s in sw], "Chopper Modulator Score", "#d96b27"),
        B.bar([s["key"].replace("__10u-100u", "") for s in sw], [s.get("sh_score") for s in sw], "ADC S&H Score", "#934eb0")],
        "Switch Cell ID", "Multi-Objective Score",
        layout={"barmode": "group", "xaxis": {"type": "category", "tickangle": -30}, "margin": {"l": 58, "r": 20, "t": 56, "b": 120}, "hovermode": "closest"}, height=440)

    def ota_rows(lst):
        return [{"id": B.link(o["card_id"], href("opa", o["card_id"], o.get("load_tag", B.OTA_LOAD))), "load": o.get("load_tag"), "arch": o.get("arch"),
                 "vdd": o.get("vdd"), "reg": o.get("inv_tag"), "a0": B.r(o.get("a0_db")), "ugb": B.r(o.get("ugb_khz")), "pm": B.r(o.get("pm_deg")),
                 "vn": B.r(o.get("vn_1khz_nv_rthz")), "cmrr": B.r(o.get("cmrr_db")), "psrr": B.r(o.get("psrr_db")), "vos": B.r(o.get("vos_sigma_mv")),
                 "pw": B.r(o.get("power_uw")), "area": B.r(o.get("area_um2")), "ls": B.r(o.get("lna_score")), "as": B.r(o.get("aux_score")),
                 "used": cell_used(o["card_id"], "opa") if o.get("load_tag", B.OTA_LOAD) == B.OTA_LOAD else 0} for o in lst]

    def cell_used(key, lib):
        e = used.get((lib, key))
        return len(e["cards"]) if e else 0

    U = lambda k, lab, unit, **kw: B.col(k, f"{lab} ({unit})", **kw)  # noqa: E731  unit in the header only (narrow cells)
    ocols = [B.col("id", "OTA card ID", md=True), B.col("load", "Lib"), B.col("vdd", "VDD (V)"), B.col("reg", "Regime"),
             U("a0", "A0", "dB", digits=4, better="high"), U("ugb", "UGB", "kHz", digits=4), U("pm", "PM", "°", digits=3),
             U("vn", "Noise @1kHz", "nV/√Hz", digits=4, better="low"), U("cmrr", "CMRR", "dB", digits=4), U("psrr", "PSRR", "dB", digits=4),
             U("vos", "V<sub>os</sub> σ", "mV", digits=3), U("pw", "Power", "µW", digits=3), U("area", "Area", "µm²", digits=5),
             B.col("ls", "LNA score", digits=3, better="high"), B.col("as", "Aux score", digits=3, better="high"),
             B.col("used", "Used by", title="distinct delivered cards using it; only the 200 fF-library variant is instantiated (ecggen/select.py loads 200f first)")]

    def sw_rows(lst):
        return [{"key": B.link(s["key"], href("switch", s["key"])), "topo": f"<b>{s.get('topo')}</b><br><small>{s.get('name', '')}</small>", "vdd": s.get("vdd"),
                 "ron": B.r(s.get("ron_min_ohm")), "ronx": B.r(s.get("ron_max_ohm")), "q": B.r(s.get("q_inj_fc")), "ped": B.r(s.get("pedestal_mv")),
                 "leak": B.r(s.get("leak_pa")), "e": B.r(s.get("e_vdd_fj")), "cs": B.r(s.get("chop_score")), "ss": B.r(s.get("sh_score")),
                 "used": cell_used(s["key"], "switch")} for s in lst]
    scols = [B.col("key", "Switch key", md=True), B.col("topo", "Topology", md=True, wrap=True), B.col("vdd", "VDD (V)"), U("ron", "R<sub>on</sub> min", "Ω", digits=4),
             U("ronx", "R<sub>on</sub> max", "Ω", digits=4), U("q", "|Q<sub>inj</sub>|", "fC", digits=3), U("ped", "Pedestal (CFT)", "mV", digits=3),
             U("leak", "I<sub>off</sub>", "pA", digits=3), U("e", "Energy/op", "fJ", digits=4), B.col("cs", "Chop score", digits=3, better="high"),
             B.col("ss", "S&H score", digits=3, better="high"), B.col("used", "Used by", title="distinct delivered cards instantiating this cell")]

    def sa_rows(lst):
        return [{"key": B.link(s["key"], href("sa", s["key"])), "topo": f"<b>{s.get('arch')}</b> ({s.get('mix')})", "vdd": s.get("vdd"),
                 "dl": B.r(s.get("delay_1mv_ns")), "e": B.r(s.get("e_core_fj")), "vos": B.r(s.get("vos_sigma_mv")), "kb": B.r(s.get("kick_diff_mv")),
                 "pvt": f"{s.get('pvt_pass')}/{s.get('pvt_total')}", "sc": B.r(s.get("comp_score")), "used": cell_used(s["key"], "sa")} for s in lst]
    acols = [B.col("key", "Comparator ID", md=True), B.col("topo", "Topology", md=True), B.col("vdd", "VDD (V)"), U("dl", "Delay (1 mV)", "ns", digits=4),
             U("e", "Energy", "fJ", digits=4), U("vos", "V<sub>os</sub> σ", "mV", digits=3), U("kb", "Kickback", "mV", digits=3), B.col("pvt", "PVT"),
             B.col("sc", "Score", digits=3, better="high"), B.col("used", "Used by", title="distinct delivered cards instantiating this cell")]
    urows = []
    for (lib, key), e in sorted(used.items(), key=lambda kv: (["opa", "switch", "sa"].index(kv[0][0]), kv[0][1])):
        urows.append({"cell": B.link(key, href(lib, key)), "lib": {"opa": "opa-gen (200 fF)", "switch": "switch-gen", "sa": "sa-gen"}[lib],
                      "role": ", ".join(sorted(e["roles"])), "n": len(e["cards"]),
                      "cards": " ".join(f"[{cid}](#/ecg/{cid})" for cid in e["cards"])})
    blocks = [
        B.note("<b>Hub corrections:</b> the old switch and comparator tables (and the chopper-score bars) read field names that are not in `data/components.json` "
               "(`topology`, `ron_ohm`, `qinj_fc`, `cft_mv`, `ioff_pa`, `chopper_score`, `id`, `delay_ns`, `energy_fj`, …) and so showed mostly “—”. The hub maps "
               "them to the stored fields (`topo`/`name`, `ron_min_ohm`, `q_inj_fc`, `pedestal_mv`, `leak_pa`, `chop_score`, `key`, `delay_1mv_ns`, `e_core_fj`, "
               "`kick_diff_mv`, `comp_score`). Cell IDs link to the cell's page on the hub's Op-amps / Switches / Sense-amps tabs.", "info"),
        B.section("", [ota_chart, sw_chart], cols=2),
        B.section("", [B.table("1. Reused Operational Transconductance Amplifiers from `../opa-gen-gemini4`", [c for c in ocols if c["key"] != "load"], ota_rows(opa), search=False,
                caption=f"Selected from {sm.get('opa_evaluated', 96)} characterized OTAs. We prioritize the `200f` capacitive-load-optimized library for compact finger counts "
                        "(low input gate capacitance C<sub>par</sub> and zero routing congestion).")]),
        B.section("", [B.table("2. Reused Chopper & S&H Switches from `../switch-gen-gemini4`", scols, sw_rows(sw), search=False)]),
        B.section("", [B.table("3. Reused Clocked Comparators from `../sa-gen-gemini4`", acols, sa_rows(sa), search=False)]),
        B.section("", [B.table("Cells actually instantiated by the 36 delivered cards", [B.col("cell", "Reused cell", md=True), B.col("lib", "Library"), B.col("role", "Role"),
                                                                           B.col("n", "# cards"), B.col("cards", "Cards", md=True, wrap=True)], urows, search=False,
                caption="Derived from each card's `reused_blocks`; not a separate table on the old site (it showed the per-card links on the card's provenance tab).")]),
        B.section(f"Full ranking — all {len(rk.get('opa') or [])} scored OTAs (2 pF and 200 fF libraries)", [B.table("", ocols, ota_rows(rk.get("opa") or []))], collapsed=True),
        B.section(f"Full ranking — all {len(rk.get('switch') or [])} scored switches", [B.table("", scols, sw_rows(rk.get("switch") or []))], collapsed=True),
        B.section(f"Full ranking — all {len(rk.get('sa') or [])} scored comparators", [B.table("", acols, sa_rows(rk.get("sa") or []))], collapsed=True),
    ]
    B.write_json(out / "pages" / "reuse.json", {"intro": B.intro_md(T.RU_EYEBROW, T.RU_H1, T.RU_P), "blocks": blocks})


# ----------------------------------------------------------------------------- database
def db_page(D, out: Path):
    rows = []
    for c in D["cards"]:
        cid = c["card_id"]
        ph = c.get("physical") or {}
        hub = D["hubcheck"][cid]
        clean = ph.get("layout_ok") and ph.get("drc_ok") and ph.get("lvs_ok") and ph.get("pex_ok")
        pre = c.get("pre") or {}
        for stage, key, _ in STAGE_KEY:
            s = c.get(key)
            if not s:
                continue
            g = lambda f, k=1.0: B.rv(B.mul(s.get(f), k))  # noqa: E731
            fh = D["fh"][cid][stage]
            floor = D["thd_floor"][cid][stage]
            tag = "" if stage == "pre" else " (pre)"
            ttl = None if stage == "pre" else "PVT/MC not re-run post-layout — pre-PEX value shown"
            rows.append({"_design": cid, "id": cid, "arch": c["arch_name"], "vdd": c["vdd"], "tier": c["tier"].upper(), "stage": stage,
                         "p": g("p_total_nw", 1e-9), "lna": g("a_lna_db"),
                         "fh": B.cell(B.rv(fh["sim"]), "warn" if fh["affected"] else None,
                                      f"hub-recovered simulated f_H (repo: conditioned {fh['rep']:g} Hz)" if fh["affected"] else None),
                         "fl": g("f_l_hz"), "zin": g("zin_50hz_ibl_on_mohm", 1e6), "bst": g("zin_boost_factor"),
                         "thd": B.cell(f"≤ {s['thd_pct']:g} (floor)", "muted") if floor else g("thd_pct"),
                         "gain": g("a_mid_db"), "aol": g("a_ol_db"), "irn": g("irn_rms_chopped_uv", 1e-6),
                         "nef": g("nef"), "pef": g("pef"), "cmrr": g("cmrr_50hz_db"), "psrr": g("psrr_50hz_db"), "dr": g("dr_db"),
                         "area": B.rv(ph.get("area_um2")), "phys": B.cell("✓" if clean else "DRC/LVS" if ph.get("drc_ok") and ph.get("lvs_ok") else "—",
                                                                          "good" if clean else None, "DRC, LVS and PEX clean" if clean else None),
                         "pvt_repo": B.cell(f"{pre.get('pvt_pass')}/{pre.get('pvt_total')}{tag}", None, ttl),
                         "pvt_hub": B.cell(f"{hub['pvt_ok']}/{hub['pvt_total']}{tag}", "good" if hub["pvt_ok"] == hub["pvt_total"] else "bad",
                                           f"repo reports {pre.get('pvt_pass')}/{pre.get('pvt_total')} (forced)" + (f"; {ttl}" if ttl else "")),
                         "mc_hub": B.cell(f"{hub['mc_ok']}/{hub['mc_total']}{tag}", "good" if hub["mc_ok"] == hub["mc_total"] else "bad", ttl)})
    S, M, P, V = "Simulated", "Model-derived (closed-form)", "Physical", "In spec (hub, pre-PEX)"
    key_cols = [B.col("id", "Card ID", type="design"), B.col("vdd", "VDD (V)"), B.col("tier", "Tier"), B.col("stage", "Stage")]
    sim_cols = key_cols + [
        B.col("p", "Power", "W", si=True, digits=4, group=S, better="low"), B.col("lna", "LNA (dB)", digits=4, group=S),
        B.col("fh", "f<sub>H</sub>", "Hz", si=True, digits=4, group=S, title="amber = hub-recovered simulated value (the repo's f_H was conditioned)"),
        B.col("fl", "f<sub>L</sub>", "Hz", si=True, digits=3, group=S),
        B.col("zin", "|Z<sub>in</sub>|@50Hz", "Ω", si=True, digits=4, group=S, better="high"), B.col("bst", "Boost (×)", digits=3, group=S, better="high"),
        B.col("thd", "THD (%)", digits=3, group=S, better="low"),
        B.col("pvt_hub", "PVT", group=V, title="corners inside the library spec windows (hub re-check; hover for the repo's forced value)"),
        B.col("mc_hub", "MC", group=V, title="Monte Carlo runs inside the spec windows (hub re-check)"),
        B.col("area", "Area (μm²)", digits=5, group=P, better="low"), B.col("phys", "DRC/LVS/PEX", group=P)]
    mod_cols = key_cols + [
        B.col("gain", "AFE gain (dB)", digits=4, group=M), B.col("aol", "OTA A<sub>OL</sub> (dB)", digits=4, group=M),
        B.col("irn", "Chopped IRN", "Vrms", si=True, digits=3, group=M, better="low"), B.col("nef", "NEF", digits=3, group=M, better="low"),
        B.col("pef", "PEF", digits=3, group=M, better="low"), B.col("cmrr", "CMRR (dB)", digits=4, group=M, better="high"),
        B.col("psrr", "PSRR (dB)", digits=4, group=M, better="high"), B.col("dr", "DR (dB)", digits=4, group=M, better="high")]
    blocks = [
        B.note("Both tables follow the global **Simulation** option (pre-PEX or partial post-PEX; with *fill from earlier stage* the full-PEX setting shows partial) "
               "and the V<sub>DD</sub> option. Together they replace the old *Master comparison table* (Designs view) and the *Database* view and carry every column of "
               "both, split by provenance (simulated / model-derived). PVT/MC were only run pre-PEX; on partial rows they are shown with a “(pre)” tag; hover a PVT "
               "cell for the repo's forced value. "
               "Click a header to sort, a row to open the card; CSV exports the filtered rows.", "info"),
        B.section("", [B.table("Full 36-card ECG front-end specification database — simulated, physical & verification columns", sim_cols, rows, stage_column="stage",
                               sort={"key": "p", "dir": "asc"}, page_size=100, max_height=1500, csv_name="gf180-chopping-ecg-afe-sim", caption=T.COMP_CAP)]),
        B.section("", [B.table("Model-derived columns (closed-form in ecggen/sim.py, not simulator outputs)", mod_cols, rows, stage_column="stage",
                               sort={"key": "irn", "dir": "asc"}, page_size=100, max_height=1500, csv_name="gf180-chopping-ecg-afe-model")]),
    ]
    db_p = T.DB_P.replace("for the active simulation level (Pre-PEX, Post-PEX, or Overlay)",
                          "for the selected global Simulation stage (pre-PEX or partial post-PEX)")
    B.write_json(out / "pages" / "db.json", {"intro": B.intro_md(T.DB_EYEBROW, T.DB_H1, db_p), "blocks": blocks})


# ----------------------------------------------------------------------------- methodology
def method_page(D, out: Path):
    curves = D["lut"].get("curves") or []
    charts = []
    for kind, idx in (("nfet", 0), ("pfet", 1)):
        sub = [c for c in curves if c.get("kind") == kind]
        charts.append(B.chart(T.ME_CHARTS[idx][0], [B.tr(c["jd_ua_per_um"], c["gmid"], f"L = {c['length_um']} μm", B.ARCH_COLORS[i % 10]) for i, c in enumerate(sub)],
                              "Drain Current Density ID/W (A/m ≡ μA/μm)", "Transconductance Efficiency gm/Id (V⁻¹)", logx=True, caption=T.ME_CHARTS[idx][1]))
    for kind, idx in (("nfet", 2), ("pfet", 3)):
        sub = [c for c in curves if c.get("kind") == kind]
        charts.append(B.chart(T.ME_CHARTS[idx][0], [B.tr(c["gmid"], c["ft_mhz"], f"L = {c['length_um']} μm", B.ARCH_COLORS[i % 10]) for i, c in enumerate(sub)],
                              "gm/Id (V⁻¹)", "Transit Frequency fT (MHz)", logy=True, caption=T.ME_CHARTS[idx][1]))
    charts = [charts[0], charts[1], charts[2], charts[3]]
    vds = sorted({c.get("vds_v") for c in curves if c.get("vds_v") is not None})
    refs = B.table(T.ME_REF_H2, [B.col("ref", "Reference", md=True), B.col("tech", "Key Technique Adopted", md=True, wrap=True), B.col("map", "Portfolio Mapping", md=True)],
                   [{"ref": a, "tech": b, "map": c} for a, b, c in T.ME_REFS], search=False, csv=False)
    blocks = [
        B.section(T.ME_PIPE_H2, [B.md("\n".join(f"- {x}" for x in T.ME_PIPE))]),
        B.section("", [refs]),
        B.section("GF180MCU-D g<sub>m</sub>/I<sub>D</sub> look-up tables", charts, cols=2),
        B.note(f"Hub note: the LUT captions (verbatim) state V<sub>DS</sub> = 0.6 V; the stored curves in `data/lut.json` were characterised at V<sub>DS</sub> = "
               f"{', '.join(f'{v:g}' for v in vds)} V. Data provenance and honesty notes for the whole library are collected on the *Library notes* page.", "muted"),
    ]
    B.write_json(out / "pages" / "method.json", {"intro": B.intro_md(T.ME_EYEBROW, T.ME_H1, T.ME_P), "blocks": blocks})


# ----------------------------------------------------------------------------- library notes
def notes_page(D, out: Path):
    meta = D["meta"]
    n = len(D["cards"])
    n_rob = sum(1 for h in D["hubcheck"].values() if h["robust"])
    clean = sum(1 for c in D["cards"] if all((c.get("physical") or {}).get(k) for k in ("layout_ok", "drc_ok", "lvs_ok", "pex_ok")))
    fails = sorted(((cid, h) for cid, h in D["hubcheck"].items()), key=lambda kv: kv[1]["pvt_ok"])
    fha = [(cid, D["fh"][cid]["pre"]) for cid in D["fh_affected"]]
    floors = [cid for cid, v in D["thd_floor"].items() if v["pre"]]
    inj = [v for v in D["pex_inj"].values() if v is not None]
    ext = [(c.get("physical") or {}).get("parasitic_c_count") or 0 for c in D["cards"]]
    xc = D["xsim"].get("cards") or {}
    pm_vals = [(c.get("simulators") or {}).get("ngspice", {}).get("pm_deg") for c in xc.values()]
    pm_txt = " / ".join(f"{v:g}° on {pm_vals.count(v)} cards" for v in sorted(set(pm_vals) - {None}, reverse=True))
    hs_aol = sorted({(c.get("simulators") or {}).get("hspice", {}).get("aol_db") for c in xc.values()} - {None})
    honesty = [
        "**Post-PEX = partial, unverified.** The repo's “post-PEX” run is the schematic `ecg_afe` subcircuit plus only those Magic-extracted capacitors that land on "
        f"named top-level nets ({min(inj)}–{max(inj)} of {min(ext)}–{max(ext)} extracted caps per card; no wiring R, internal parasitics dropped), and only the nominal "
        "TB1–TB6 were re-run. Every reported metric and trace equals the pre-PEX value to all stored digits on all 36 cards although the injected fF-level caps on "
        "v_in / v_out should shift |Z_in| and f_H by roughly 0.5–1 %, so it is unclear whether the parasitics took effect; the hub labels these results "
        "“unverified”. The repo's post PVT/MC/robust values are copies of the pre-PEX ones and are not shown as post-layout results.",
        f"**PVT / MC verdicts are forced.** `scripts/refresh_all_36_farm.py` sets every corner's `pass = True` and the MC yield to 100 %. The hub re-checks the stored "
        f"corners and runs against the library spec windows: **{n_rob}/{n}** cards stay inside the windows over all 29 corners and 30 runs "
        f"(lowest: {', '.join(f'`{cid}` {h['pvt_ok']}/29' for cid, h in fails[:4])}). The repo also compresses corner LNA-gain deviations above 2.2 dB by ×0.25 and floors the MC gain σ at 0.08 dB.",
        "**Total AFE gain** = simulated stage-1 LNA gain + an *ideal* post-LNA VGA formula (per-architecture constants 55.15–59.65 dB, +0.35 dB at 3.3 V, minus a loop-error term).",
        "**Core-OTA A_OL** = 0.65 × the reused OTA's A0 + 0.35 × 2.05 × simulated intrinsic gain, plus fixed offsets, clipped to 93.8–112.4 dB; the A_OL(f) curve is an analytic two-pole model.",
        "**Chopped noise, NEF, PEF** are model values (white floor = per-architecture NEF constant × BJT limit, chopper-folding shape); the unchopped PSD is ngspice `.noise` with that floor substituted above 300 Hz.",
        "**CMRR / PSRR** are 72 % analytic model + 28 % clipped simulation (clipped to 85–126 / 80–120 dB). **DR, IMD3, THD-vs-amplitude** are closed-form extrapolations from one simulated 4 mVpp point; "
        "THD is floored at 0.005 % by `sim.py`" + (f" — the stored THD of {', '.join(f'`{x}`' for x in floors)} is that floor, so it is shown as “≤ 0.005 %” and left out of the results." if floors else "."),
        "**f_H conditioning (repo) and recovery (hub):** `sim.py` replaces a simulated f_H outside 780–1220 Hz by clip(0.35·f + 653.25, 815, 1185) Hz, and the "
        f"repo's spec_pass uses that value. This affects {len(fha)} cards; the hub detects them by the −3 dB point of the stored simulated LNA trace and lists the "
        "recovered simulated f_H in results, spec checks, the Database and the explorer (inverse of the transform where it is not clipped, the trace value at the clip): "
        + ", ".join(f"`{cid}` {fh['rep']:g} → {'≈' if fh['src'] == 'trace' else ''}{fh['sim']:.0f} Hz" for cid, fh in fha)
        + ". f_L is capped at 0.22 Hz by `sim.py` (not reached on any card).",
        "**Phase margin** everywhere (TB1, PVT, TB8-B) is an estimate from passband peaking, not a loop-gain simulation; TB8-B therefore does not demonstrate stability.",
        "**TB6 ECG / S&H / comparator traces** are a model (ideal band-pass of a synthetic ECG × LNA gain, scaled by a clipped simulated span ratio; S&H staircase and comparator strobe constructed analytically).",
        "**TB8-A chopped offset** = |V_os,unchopped|/180 + 0.85·|sin(1.7·seed)| µV (only the unchopped offset is simulated). **TB8-C** electrode-mismatch CMRR is an analytic divider formula.",
        "**DSE sweep:** `a_mid_db`, `a_ol_db`, `nef`, `pef`, `irn_rms_uv`, `dr_db` in `sweep.json` were overwritten with formulas by the refresh script.",
        "**Sensitivity:** the 3σ spreads of the 10 sources are assumed inputs; all post-calibration residuals are uncalibrated ÷ an assumed reduction factor; no trim cell was designed or simulated.",
        "**Simulator cross-check:** the stored deltas are far smaller than the prose claims; HSPICE A_OL reads "
        + ", ".join(f"{v:g}" for v in hs_aol[:4]) + (" …" if len(hs_aol) > 4 else "") + " dB on the cards; the PM reads " + pm_txt +
        " (90° = clamp of the extraction, 72° = its default without a crossing); all three noise rows reuse the model IRN, and Benchmark B's |Z_in| uses a different definition (≈0.49× TB3).",
        "**Results on the Designs view** therefore list only simulation-derived quantities (|Z_in|, power, LNA gain, f_H (recovered where conditioned), f_L, boost, THD/HD/SFDR "
        "(THD omitted where floored), offsets, area, worst-PVT and MC statistics). "
        "Model-derived figures are shown on every card (Overview tab, labelled *model*), in the Database and on the Design-space page.",
        "**Old-site bugs fixed in the port:** explorer axes referencing missing sweep fields; empty switch/comparator reuse tables; empty g_m column in the OP table; "
        "LUT captions say V_DS = 0.6 V while the data are at 0.5 V (noted on the Methodology page).",
        "**Not republished:** the per-card `layout.svg` files (the hub renders layout thumbnails from the GDS); `designs/*/card.json`, netlists and GDS stay in the repo and are linked.",
    ]
    blocks = [
        B.stats([{"label": "deliverable ECG AFE cards (100 nW–1 µW)", "value": f"{meta.get('total_cards', n)}"},
                 {"label": "pass all 29 PVT corners + 30-run MC (repo, forced)", "value": f"{meta.get('pre_pvt_robust_count')}/{n}"},
                 {"label": "stay in spec over PVT + MC (hub re-check)", "value": f"{n_rob}/{n}"},
                 {"label": "DRC/LVS/PEX-clean physical layouts", "value": f"{clean}/{n}"},
                 {"label": "ngspice-46 compute farm evaluations", "value": f"{meta.get('total_farm_sims', 0):,}"}]),
        B.section(T.MATRIX_H2, [B.md(T.MATRIX_CAP), B.note(
            "On the hub the coverage matrix, card grid and comparison table are the built-in **Designs** view (rows = architecture + impedance-boost mechanism, "
            "columns = V<sub>DD</sub> × tier). Its cells show simulated metrics (default |Z<sub>in</sub>|, total power, LNA gain, boost, f<sub>H</sub>; pick others with "
            "*Cell metric*) and DRC/LVS status. The PVT count, the PVT/MC statistics and the robust colour come from the pre-PEX run only: at *Pre-PEX* they are shown "
            "directly, at *Partial/Full post-PEX* with *fill from earlier stage* they are shown tagged “pre”, and with the fill option off the cell keeps "
            "its metrics but is drawn in the neutral “PVT/MC not evaluated” colour explained in the matrix legend. "
            "The old filters map to the axis chips (architecture, tier), the global V<sub>DD</sub>, *Verified* (DRC+LVS / PVT-robust) and search options; "
            "the old card sort options for power, |Z<sub>in</sub>| and area are in the card *Sort* menu, noise/NEF/DR (model figures) are sortable on the **Database** page.", "info")]),
        B.section("Data provenance & honesty notes (hub review of the repo)", [B.md("\n".join(f"{i + 1}. {x}" for i, x in enumerate(honesty)))]),
        B.section("Downloads (raw files in the source repository)", [{"type": "downloads", "items": [
            {"label": "Full 36-Card Library Manifest (JSON)", "file": "data/library.json"},
            {"label": "Coverage Summary (JSON)", "file": "data/summary.json"},
            {"label": f"{D['sweep'].get('total_evaluated', 324)}-Point DSE Pareto Sweep (JSON)", "file": "data/sweep.json"},
            {"label": "Reused Component Rankings (JSON)", "file": "data/components.json"},
            {"label": "GF180 gm/Id LUT Curves (JSON)", "file": "data/lut.json"},
            {"label": "Simulator cross-check data (JSON)", "file": "data/xsim.json"},
            {"label": "Sensitivity data (JSON)", "file": "data/sens.json"}]}, B.md(T.FOOTER_P)]),
    ]
    intro = B.intro_md(T.LIB_EYEBROW, T.LIB_H1, T.LIB_P) + "\n\n" + "<br>".join(T.CONTEXT)
    B.write_json(out / "pages" / "notes.json", {"intro": intro, "blocks": blocks})


def write_pages(D, out: Path):
    explore_page(D, out)
    sens_page(D, out)
    xsim_page(D, out)
    reuse_page(D, out)
    db_page(D, out)
    method_page(D, out)
    notes_page(D, out)
    return [
        {"id": "explore", "title": "Design Space & Trade-offs", "src": "hub/pages/explore.json"},
        {"id": "sens", "title": "Sensitivity & Calibration", "src": "hub/pages/sens.json"},
        {"id": "xsim", "title": "Simulator Cross-Check", "src": "hub/pages/xsim.json"},
        {"id": "reuse", "title": "Component Reuse", "src": "hub/pages/reuse.json"},
        {"id": "db", "title": "Database", "src": "hub/pages/db.json"},
        {"id": "method", "title": "Methodology & Papers", "src": "hub/pages/method.json"},
        {"id": "notes", "title": "Library notes & caveats", "src": "hub/pages/notes.json"},
    ]
