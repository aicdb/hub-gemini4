#!/usr/bin/env python3
"""Bootstrap hub adapter for opa-gen-gemini4 (schema aicdb-hub/2).

usage: opa.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus
hosted files under OUT_DIR (referenced as "hub/<path>"):

  pages/overview.json  explore.json  db.json  method.json      component pages
  designs/<id>.json                                           one detail doc per design
  data/dse_<load>.json  dse_all.json  ulp_points.json  db_<load>.json  db_all.json

It reproduces everything the retired GitHub Pages site (docs/index.html + assets/app.js)
showed; see adapters/opa.inventory.md for the item-by-item mapping.
Stage mapping: pre_pex -> "pre"; post_pex (whole-cell Magic C-only extraction) -> "full".
Python >= 3.8 stdlib only. Copy to scripts/export_hub.py in the repo when going native.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opa_fmt import MU, cmp_sub, fin, fmt_idd, fmt_pwr, fmt_range, jsn, num, r5, rl, scale, si, unit_label  # noqa: E402

ARCH_COLORS = ['#225bb2', '#d96b27', '#1e8565', '#934eb0', '#b08218', '#c93b5b',
               '#0d8499', '#5c6bc0', '#2e7d32', '#ad1457', '#6d4c41', '#0284c7']
PRE_C, POST_C, GRAY, GREEN, ORANGE = '#225bb2', '#dc2626', '#64748b', '#1e8565', '#d96b27'
POST_NOTE = ("Whole-cell Magic `ext2spice` extraction of the complete op-amp layout (coupling + ground "
             "capacitances, C-only); nominal benches, 17-corner PVT and 50-run Monte Carlo re-run on the "
             "extracted netlist.")

# key, label, unit, si, better, summary field, scale, digits
METRICS = [
    ("ugb", "UGB", "Hz", True, "high", "ugb_hz", 1, 3),
    ("a0", "DC gain", "dB", False, "high", "a0_db", 1, 4),
    ("cl_bw", "CL −3 dB BW (ULP only)", "Hz", True, None, "cl_bw_hz", 1, 3),
    ("pm", "Phase margin", "°", False, "high", "pm_deg", 1, 4),
    ("gm", "Gain margin", "dB", False, "high", "gm_db", 1, 3),
    ("idd", "Supply current", "A", True, "low", "idd_ua", 1e-6, 3),
    ("power", "Power", "W", True, "low", "power_uw", 1e-6, 3),
    ("vos", "Offset (nominal)", "V", True, None, "vos_mv", 1e-3, 3),
    ("overshoot", "Step overshoot", "%", False, "low", "overshoot_pct", 1, 3),
    ("ts", "Settling time (1 %)", "s", True, "low", "ts_1pct_us", 1e-6, 3),
    ("sr_pos", "Slew rate +", "V/s", True, "high", "sr_pos_vus", 1e6, 3),
    ("sr_neg", "Slew rate −", "V/s", True, "high", "sr_neg_vus", 1e6, 3),
    ("vn_1k", "Input noise @ 1 kHz", "V/√Hz", True, "low", "vn_1khz_nv_rthz", 1e-9, 3),
    ("vn_rms", "Integrated noise (1 Hz–1 MHz)", "V", True, "low", "vn_rms_uv", 1e-6, 3),
    ("cmrr", "CMRR (DC)", "dB", False, "high", "cmrr_dc_db", 1, 4),
    ("psrr_p", "PSRR+ (DC)", "dB", False, "high", "psrr_p_dc_db", 1, 4),
    ("psrr_n", "PSRR− (DC)", "dB", False, "high", "psrr_n_dc_db", 1, 4),
    ("icmr", "ICMR span", "V", True, "high", "icmr_span_v", 1, 3),
    ("swing", "Output swing", "V", True, "high", "vout_swing_v", 1, 3),
    ("thd", "THD", "%", False, "low", "thd_pct", 1, 3),
    ("hd2", "HD2", "dBc", False, "low", "hd2_dbc", 1, 3),
    ("hd3", "HD3", "dBc", False, "low", "hd3_dbc", 1, 3),
    ("im3", "Two-tone IM3", "dBc", False, "low", "im3_dbc", 1, 3),
    ("zin", "Z_in @ 1 kHz (1×)", "Ω", True, "high", "zin_1khz_mohm", 1e6, 3),
    ("pm_min", "Worst-case PVT PM", "°", False, "high", "pm_min_deg", 1, 4),
    ("a0_min", "Worst-case PVT gain", "dB", False, "high", "a0_min_db", 1, 4),
    ("mc_yield", "MC yield", "%", False, "high", "mc_yield_pct", 1, 3),
    ("vos_sigma", "Offset σ (MC)", "V", True, "low", "vos_sigma_mv", 1e-3, 3),
    ("pm_p5", "MC PM 5th pct.", "°", False, "high", "pm_p5_deg", 1, 3),
    ("area", "Layout area", "µm²", False, "low", None, 1, 5),
]
MDEF = {m[0]: m for m in METRICS}
METRIC_DESC = {
    "ugb": "Open-loop unity-gain bandwidth, nominal TT 27 °C, at the card's load C_L",
    "a0": "Open-loop DC gain, nominal TT 27 °C",
    "cl_bw": "Closed-loop −3 dB bandwidth of the unity-gain follower; reported for the ultra-low-power (<0.1 µW, <10 kHz) designs only",
    "pm": "Open-loop phase margin, nominal TT 27 °C (multi-crossing aware)",
    "idd": "Quiescent supply current of the op-amp (excluding the reference branch)",
    "power": "Quiescent power I_DD × V_DD",
    "vn_1k": "Input-referred noise density at 1 kHz",
    "vn_rms": "Integrated input-referred noise, 1 Hz–1 MHz",
    "pm_min": "Minimum phase margin over the 17 recorded PVT corners",
    "a0_min": "Minimum DC gain over the 17 recorded PVT corners",
    "mc_yield": "Yield of the 50-run per-finger mismatch Monte Carlo (PM ≥ 45°, step-stable; pre-PEX also all devices saturated)",
    "vos_sigma": "Standard deviation of the input offset over the 50 Monte Carlo runs",
    "pm_p5": "5th percentile of the phase margin over the 50 Monte Carlo runs",
    "zin": "Closed-loop input impedance at 1 kHz in the 1 V/V follower",
    "area": "Layout bounding-box area from the GDS — a layout property, the same at every simulation stage",
}

KNOBS = {  # card.knobs key -> (label, unit, scale)
    "l_in": ("L<sub>in</sub>", "µm", 1), "l_load": ("L<sub>load</sub>", "µm", 1), "l_tail": ("L<sub>tail</sub>", "µm", 1),
    "l_casc": ("L<sub>casc</sub>", "µm", 1), "l_out": ("L<sub>out</sub>", "µm", 1),
    "gmid_in": ("gm/Id<sub>in</sub>", "V⁻¹", 1), "gmid_load": ("gm/Id<sub>load</sub>", "V⁻¹", 1),
    "gmid_tail": ("gm/Id<sub>tail</sub>", "V⁻¹", 1), "gmid_cascode": ("gm/Id<sub>cascode</sub>", "V⁻¹", 1),
    "gmid_stage2": ("gm/Id<sub>stage2</sub>", "V⁻¹", 1), "scale_i": ("Current scale", "×", 1),
    "cc_scale": ("C<sub>c</sub> scale", "×", 1), "rz_scale": ("R<sub>z</sub> scale", "×", 1),
    "c_out_extra_f": ("Extra C<sub>out</sub>", "F", 1), "vdd_v": ("V<sub>DD</sub>", "V", 1),
    "itotal_ua": ("I<sub>total</sub> target", "µA", 1), "vcm_ratio": ("V<sub>CM</sub>/V<sub>DD</sub>", "", 1),
    "cl_pf": ("C<sub>L</sub>", "pF", 1), "w_unit_um": ("W<sub>unit</sub>", "µm", 1),
    "r_width_um": ("Resistor width", "µm", 1),
}

COMPACT = dict(separators=(",", ":"), ensure_ascii=False)


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, **COMPACT))


def jload(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


# ============================================================================ helpers
def chart(title, data, layout=None, **kw):
    layout = dict(layout or {})
    layout.setdefault("showlegend", True)
    b = {"type": "chart", "title": title, "data": data, "layout": layout}
    b.update({k: v for k, v in kw.items() if v is not None})
    return b


def lay(xt, yt, logx=False, logy=False, **extra):
    L = {"xaxis": {"title": {"text": xt}, "type": "log" if logx else "linear", "exponentformat": "SI"},
         "yaxis": {"title": {"text": yt}, "type": "log" if logy else "linear", "exponentformat": "SI"},
         "hovermode": "x unified"}
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(L.get(k), dict):
            L[k] = {**L[k], **v}
        else:
            L[k] = v
    return L


def line(x, y, name, color, dash="solid", mode="lines", **kw):
    t = {"type": "scatter", "mode": mode, "name": name, "x": rl(x), "y": rl(y),
         "line": {"color": color, "width": 2.1, "dash": dash}}
    t.update(kw)
    return t


def stage_alts(alt, make, title, **kw):
    """[pre block, full block] for a stage-alternative pair; make(stage) -> block body or None."""
    out = []
    for st in ("pre", "full"):
        b = make(st)
        if b is None:
            continue
        b = dict(b)
        b.setdefault("title", title)
        b.update({"alt": alt, "stage": st})
        b.update(kw)
        out.append(b)
    return out


def status_tuple(s):
    """app.js statusTuple(): label + tone of the PVT status badge."""
    if s.get("pvt_robust"):
        return "17/17 PVT pass", "good"
    if s.get("pm_pass"):
        return f"{s.get('pvt_pass') if s.get('pvt_pass') is not None else 16}/17 PVT", "warn"
    return "Screen warn", "bad"


def phys_badge(p):
    if p.get("layout_ok") and p.get("drc_ok") and p.get("lvs_ok") and p.get("pex_ok"):
        return "DRC/LVS/PEX pass", "good"
    if p.get("layout_ok") and p.get("drc_ok") and p.get("lvs_ok"):
        return "DRC/LVS pass", "good"
    if p.get("layout_ok"):
        return "Layout routed", "warn"
    return "Layout pending", "muted"


def stage_result(s, area, mc):
    """area: the exact layout bounding-box area (a stage-independent layout property, identical in every stage)."""
    if not s:
        return None
    m = {}
    for key, _l, _u, _si, _b, field, k, _d in METRICS:
        if field and fin(s.get(field)):
            m[key] = r5(s[field] * k) if k != 1 else r5(float(s[field]))
    if fin(area):
        m["area"] = area
    out = {"metrics": m, "robust": bool(s.get("pvt_robust"))}
    if s.get("pm_pass") is False:
        out["status"] = "fail"  # nominal PM screen failed at this stage (old site: 'Screen warn', red)
    if s.get("pvt_total"):
        out["pvt"] = {"pass": s["pvt_pass"], "total": s["pvt_total"]}
    if mc and mc.get("n_completed") and fin(mc.get("yield_pct")):
        out["mc"] = {"pass": int(round(mc["yield_pct"] * mc["n_completed"] / 100)), "total": mc["n_completed"]}
    return out


# ============================================================================ design detail
def nom_of(card, st):
    return ((card.get("pre_pex") if st == "pre" else card.get("post_pex")) or {}).get("nominal") or {}


def part_of(card, st, k):
    return ((card.get("pre_pex") if st == "pre" else card.get("post_pex")) or {}).get(k) or {}


def views(card, mode):
    pre, post = nom_of(card, "pre"), nom_of(card, "full")
    if mode == "pre":
        return [("Pre-PEX", pre, PRE_C, "solid")]
    if mode == "full":
        return [("Post-PEX", post, POST_C, "solid")] if post else []
    return [("Pre-PEX", pre, PRE_C, "solid")] + ([("Post-PEX", post, POST_C, "dash")] if post else [])


def curve(nom, k):
    return (nom.get("curves") or {}).get(k) or {}


def waveform_charts(card, mode):
    """The eight 'Simulation Waveforms' plots of app.js for one view mode (pre / full / overlay)."""
    V = views(card, mode)
    charts = []
    # 1. open-loop gain
    tr = [line(curve(n, "bode").get("f_hz"), curve(n, "bode").get("mag_db"),
               f"{lab} Gain (A0={num(n.get('a0_db'), 1)}dB, UGB={si(n.get('ugb_hz'), 'Hz')})", c, d)
          for lab, n, c, d in V if curve(n, "bode").get("f_hz")]
    charts.append(("gain", "Open-Loop Gain Response A<sub>OL</sub>(f)", tr, lay("Frequency (Hz)", "Magnitude (dB)", logx=True)))
    # 2. phase
    tr = [line(curve(n, "bode").get("f_hz"), curve(n, "bode").get("phase_deg"), f"{lab} Phase (PM={num(n.get('pm_deg'), 1)}°)", c, d)
          for lab, n, c, d in V if curve(n, "bode").get("f_hz")]
    charts.append(("phase", "Open-Loop Phase Response ∠T(f)", tr, lay("Frequency (Hz)", "Phase (°)", logx=True)))
    # 3. rejection
    tr = []
    for lab, n, _c, d in V:
        r = curve(n, "rejection")
        if r.get("f_hz"):
            tr += [line(r["f_hz"], r.get("cmrr_db"), f"{lab} CMRR", PRE_C, d),
                   line(r["f_hz"], r.get("psrr_p_db"), f"{lab} PSRR+", GREEN, d),
                   line(r["f_hz"], r.get("psrr_n_db"), f"{lab} PSRR−", ORANGE, d)]
    charts.append(("rej", "Rejection Ratios: CMRR, PSRR+, PSRR−", tr, lay("Frequency (Hz)", "Rejection (dB)", logx=True)))
    # 4. noise
    tr = [line(curve(n, "noise").get("f_hz"), curve(n, "noise").get("vn_nv_rthz"),
               f"{lab} en(f) (@1kHz: {num(n.get('vn_1khz_nv_rthz'), 1)} nV/√Hz)", c, d)
          for lab, n, c, d in V if curve(n, "noise").get("f_hz")]
    charts.append(("noise", "Input-Referred Noise Density e<sub>n</sub>(f)", tr, lay("Frequency (Hz)", "Noise (nV/√Hz)", logx=True, logy=True)))
    # 5. step / slew
    tr = []
    ref = curve(V[-1][1], "slew") if V else {}
    if not ref.get("t_us") and V:
        ref = curve(V[0][1], "slew")
    if ref.get("t_us"):
        tr.append(line(ref["t_us"], ref.get("vin_v"), "Input Step Vin", GRAY, "dot"))
    tr += [line(curve(n, "slew")["t_us"], curve(n, "slew").get("vout_v"), f"{lab} Vout (SR+ {num(n.get('sr_pos_vus'), 3)} V/μs)", c, d)
           for lab, n, c, d in V if curve(n, "slew").get("t_us")]
    charts.append(("slew", "Unity-Follower Step & Slew Response", tr, lay("Time (μs)", "Voltage (V)")))
    # 6. DC transfer
    tr = []
    dref = curve(nom_of(card, "pre"), "dc") if mode != "full" else curve(nom_of(card, "full"), "dc")
    if dref.get("vin_v"):
        tr.append(line(dref["vin_v"], dref["vin_v"], "Ideal 1:1 Tracking", GRAY, "dot"))
    tr += [line(curve(n, "dc")["vin_v"], curve(n, "dc").get("vout_v"), f"{lab} Vout (ICMR {num(n.get('icmr_span_v'), 2)} V)", c, d)
           for lab, n, c, d in V if curve(n, "dc").get("vin_v")]
    charts.append(("dc", "Unity-Follower DC Transfer & ICMR", tr, lay("Input Voltage Vin (V)", "Output Voltage Vout (V)")))
    # 7. Zin
    tr = []
    for lab, n, _c, d in V:
        z = curve(n, "zin")
        if z.get("f_hz"):
            tr += [line(z["f_hz"], z.get("zin_1x_ohm"), f"{lab} |Zin| (1 V/V)", PRE_C, d),
                   line(z["f_hz"], z.get("zin_6x_ohm"), f"{lab} |Zin| (6 V/V)", GREEN, d)]
    charts.append(("zin", "Closed-Loop Input Impedance |Z<sub>in</sub>(f)| (1× & 6×)", tr, lay("Frequency (Hz)", "|Zin| (Ω)", logx=True, logy=True)))
    # 8. distortion bars
    cats = ["HD2 (dBc)", "HD3 (dBc)", "THD (dB)", "Two-Tone IM3 (dBc)"]
    tr = [{"type": "bar", "x": cats, "y": rl([n.get("hd2_dbc"), n.get("hd3_dbc"), n.get("thd_db"), n.get("im3_dbc")]),
           "name": f"{lab} (THD={num(n.get('thd_pct'), 4)}%)", "marker": {"color": c}} for lab, n, c, _d in V]
    charts.append(("dist", "Coherent-FFT Harmonic Distortion & Two-Tone IM3", tr,
                   lay("Distortion Component", "Relative Level (dBc / dB)", barmode="group", xaxis={"type": "category"}, hovermode="closest")))
    return charts


PVT_LAYOUT = dict(barmode="group", xaxis={"type": "category", "tickangle": -35}, margin={"l": 58, "r": 20, "t": 40, "b": 110}, hovermode="closest",
                  legend={"orientation": "h", "x": 0, "y": 1.12})


def pvt_labels(pts):
    return [f"{p.get('corner')} {jsn(p.get('temp_c'))}°C {num(p.get('vdd'), 2)}V" for p in pts]


def pvt_mc_charts(card, mode):
    pre_p = part_of(card, "pre", "pvt").get("points") or []
    post_p = part_of(card, "full", "pvt").get("points") or []
    labels = pvt_labels(pre_p or post_p)
    use = {"pre": [("Pre-PEX", pre_p, PRE_C, GREEN)], "full": [("Post-PEX", post_p, POST_C, ORANGE)],
           "overlay": [("Pre-PEX", pre_p, PRE_C, GREEN), ("Post-PEX", post_p, POST_C, ORANGE)]}[mode]
    out = []
    tr = [{"type": "bar", "x": labels, "y": rl([p.get("pm_deg") for p in pts]), "name": f"{lab} PM (°)", "marker": {"color": c1}}
          for lab, pts, c1, _c2 in use if pts]
    out.append(("pvt_pm", "Phase Margin Across All 17 PVT Corners", tr, lay("PVT Corner (Process / Temp / Supply)", "Phase Margin (°)", **PVT_LAYOUT)))
    gcol = {"Pre-PEX": GREEN, "Post-PEX": ORANGE}
    tr = [{"type": "bar", "x": labels, "y": rl([p.get("a0_db") for p in pts]), "name": f"{lab} Gain (dB)", "marker": {"color": gcol[lab]}}
          for lab, pts, _c1, _c2 in use if pts]
    out.append(("pvt_a0", "Open-Loop DC Gain Across All 17 PVT Corners", tr, lay("PVT Corner (Process / Temp / Supply)", "DC Gain (dB)", **PVT_LAYOUT)))
    mcs = {"pre": [("Pre-PEX", part_of(card, "pre", "mc"), PRE_C)], "full": [("Post-PEX", part_of(card, "full", "mc"), POST_C)],
           "overlay": [("Pre-PEX", part_of(card, "pre", "mc"), PRE_C), ("Post-PEX", part_of(card, "full", "mc"), POST_C)]}[mode]
    mcs = [x for x in mcs if x[1].get("vos_samples_mv")]
    if mcs:
        pre_lab = len(mcs) > 1
        tr = [{"type": "histogram", "x": rl(mc["vos_samples_mv"]), "nbinsx": 14, "opacity": 0.65 if pre_lab else 1,
               "name": f"{lab + ' ' if pre_lab else ''}Vos (σ={num(mc.get('vos_sigma_mv'), 3)} mV)", "marker": {"color": c}} for lab, mc, c in mcs]
        out.append(("mc_hist", "50-Run Mismatch Monte Carlo: Input Offset V<sub>os</sub>", tr,
                    lay("Input-Referred Offset Vos (mV)", "Sample Count", hovermode="closest", barmode="overlay")))
        tr = [{"type": "scatter", "mode": "markers", "x": rl(mc["vos_samples_mv"]), "y": rl(mc.get("pm_samples_deg")),
               "name": f"{lab + ' ' if pre_lab else ''}MC Samples (n={len(mc['vos_samples_mv'])})",
               "marker": {"color": c if pre_lab else GREEN, "size": 8}} for lab, mc, c in mcs]
        out.append(("mc_scatter", "50-Run Mismatch Monte Carlo: Phase Margin vs Offset", tr,
                    lay("Input Offset Vos (mV)", "Phase Margin (°)", hovermode="closest")))
    return out


def kpi_items(card, st, phys, cl_pf):
    """Overview KPI tiles (app.js showTab('overview')), values from the given stage."""
    pre, post = nom_of(card, "pre"), nom_of(card, "full")
    nom = pre if st == "pre" else post
    pvt, mc = part_of(card, st, "pvt"), part_of(card, st, "mc")
    is_ulp = card.get("iclass_tag") == "ulp_lt0p1uw"
    cl_bw = nom.get("cl_bw_hz") or nom.get("ugb_hz")
    if is_ulp:
        idd_sub = cmp_sub((pre.get("idd_ua") or 0) * 1000, post["idd_ua"] * 1000 if fin(post.get("idd_ua")) else float("nan"), " nA", 1)
    else:
        idd_sub = cmp_sub(pre.get("idd_ua"), post.get("idd_ua"), f" {MU}A", 2)
    if is_ulp:
        bw = ("Closed-Loop -3 dB BW", si(cl_bw, "Hz"), f"UGB = {si(nom.get('ugb_hz'), 'Hz')} · CL = {jsn(cl_pf)} pF")
    else:
        bw = ("Unity-Gain Bandwidth", si(nom.get("ugb_hz"), "Hz"),
              f"Pre {si(pre.get('ugb_hz'), 'Hz')} → Post {si(post.get('ugb_hz'), 'Hz')}" if post else f"CL = {jsn(cl_pf)} pF")
    n_pass = pvt.get("n_pass") if pvt.get("n_pass") is not None else 17
    n_pts = pvt.get("n_points") if pvt.get("n_points") is not None else 17
    items = [
        ("Quiescent IDD", fmt_idd(nom.get("idd_ua")), idd_sub or f"Envelope {card.get('iclass_label')}"),
        ("Total Power", fmt_pwr(nom.get("power_uw")), f"At VDD = {num(card.get('vdd'), 1)} V"),
        ("Open-Loop DC Gain", f"{num(nom.get('a0_db'), 2)} dB", cmp_sub(pre.get("a0_db"), post.get("a0_db"), " dB", 2)),
        bw,
        ("Phase Margin (Nominal)", f"{num(nom.get('pm_deg'), 2)}°", cmp_sub(pre.get("pm_deg"), post.get("pm_deg"), "°", 2)),
        ("Worst-Case PVT PM", f"{num(pvt.get('pm_min_deg'), 2)}°", f"{n_pass}/{n_pts} PVT corners pass >45°"),
        ("Input Noise @ 1 kHz", (f"{num(nom.get('vn_1khz_nv_rthz'), 1)} nV/√Hz" if not fin(nom.get('vn_1khz_nv_rthz')) or nom['vn_1khz_nv_rthz'] < 1000
                                 else si(nom["vn_1khz_nv_rthz"] * 1e-9, "V/√Hz", 3)), f"Integrated (1Hz–1MHz): {num(nom.get('vn_rms_1hz_1mhz_uv'), 2)} μVrms"),
        ("Mismatch Offset σ", f"{num(mc.get('vos_sigma_mv'), 3)} mV", f"50-run MC yield: {num(mc.get('yield_pct'), 1)}% (P5 PM {num(mc.get('pm_p5_deg'), 1)}°)"),
        ("CMRR (DC)", f"{num(nom.get('cmrr_dc_db'), 1)} dB", "DC rejection ratio (original tile: CMRR / PSRR+ / PSRR−)"),
        ("PSRR+ (DC)", f"{num(nom.get('psrr_p_dc_db'), 1)} dB", "DC rejection ratio"),
        ("PSRR− (DC)", f"{num(nom.get('psrr_n_dc_db'), 1)} dB", "DC rejection ratio"),
        ("Slew Rate +", f"{num(nom.get('sr_pos_vus'), 3)} V/μs", f"1% settling: {num(nom.get('ts_1pct_us'), 3)} μs"),
        ("Slew Rate −", f"{num(nom.get('sr_neg_vus'), 3)} V/μs", "unity-follower step"),
        ("THD", f"{num(nom.get('thd_pct'), 4)}%", f"HD2 {num(nom.get('hd2_dbc'), 1)} dBc, HD3 {num(nom.get('hd3_dbc'), 1)} dBc"),
        ("Two-Tone IM3", f"{num(nom.get('im3_dbc'), 1)} dBc", "coherent FFT"),
        ("Physical Footprint", f"{phys['area_um2']:,.0f} μm²" if phys.get("area_um2") else "Pending",
         f"{num(phys.get('area_um2'), 1)} μm² · {num(phys.get('width_um'), 1)} × {num(phys.get('height_um'), 1)} μm ({phys.get('parasitic_c_count') or 0} par C)" if phys.get("width_um") else ""),
    ]
    return [{"label": a, "value": b, "sub": c} for a, b, c in items]


def checklist_rows(card, st, phys):
    pre = nom_of(card, "pre")
    nom = pre if st == "pre" else nom_of(card, "full")
    sat = pre.get("all_saturated")
    if sat is None:
        sat = nom.get("all_saturated")
    if sat is None:
        sat = True
    pre_pvt, post_pvt = part_of(card, "pre", "pvt"), part_of(card, "full", "pvt")
    mc = part_of(card, st, "mc")
    checks = [
        ("Nominal Stability & Bias Screen", bool(nom.get("pm_pass") and sat),
         f"PM = {num(nom.get('pm_deg'), 2)}° (>45°), Gain = {num(nom.get('a0_db'), 2)} dB, all devices in saturation"
         + (" (saturation map from the pre-PEX operating point)" if st == "full" else "")),
        ("17-Corner PVT Verification (Pre-PEX)", pre_pvt.get("pvt_robust"),
         f"{pre_pvt.get('n_pass') or 0}/{pre_pvt.get('n_points') or 17} corners pass, min PM = {num(pre_pvt.get('pm_min_deg'), 2)}°"),
        ("17-Corner PVT Verification (Post-PEX)", post_pvt.get("pvt_robust") if post_pvt else None,
         f"{post_pvt.get('n_pass')}/{post_pvt.get('n_points')} corners pass, min PM = {num(post_pvt.get('pm_min_deg'), 2)}°" if post_pvt else "Pending post-PEX farm run"),
        ("50-Run Per-Finger Mismatch Monte Carlo", (mc.get("yield_pct") or 0) >= 90,
         f"Yield {num(mc.get('yield_pct'), 1)}%, Vos σ = {num(mc.get('vos_sigma_mv'), 3)} mV"
         + (f" — criterion: {mc['yield_check']}" if mc.get("yield_check") else "")),
        ("KLayout GF180 DRC Signoff", phys.get("drc_ok"), "0 effective DRC violations" if phys.get("drc_ok") else "Pending"),
        ("KLayout GF180 LVS Signoff", phys.get("lvs_ok"), phys.get("lvs_conclusion") or "Pending"),
        ("Magic Parasitic Extraction (PEX)", phys.get("pex_ok"),
         f"{phys.get('nfet_fingers')} NFET + {phys.get('pfet_fingers')} PFET fingers, {phys.get('mim_caps')} MIM caps, "
         f"{phys.get('poly_resistors')} poly res, {phys.get('parasitic_c_count')} parasitic caps" if phys.get("pex_ok") else "Pending"),
    ]
    st_cell = lambda ok: {"v": "PASS", "s": "good"} if ok is True else {"v": "WARN", "s": "warn"} if ok is False else {"v": "PENDING", "s": "muted"}  # noqa: E731
    return [[a, c, st_cell(b)] for a, b, c in checks]


def design_target_items(card, st):
    nom = nom_of(card, st)
    caps = "; ".join(f"{x['name']}: {num(x.get('c_pf'), 3)} pF ({jsn(x.get('n_units'))}× {jsn(x.get('c_width'))}×{jsn(x.get('c_length'))} μm)"
                     for x in card.get("caps") or []) or "None"
    res = "; ".join(f"{x['name']}: {num(x.get('r_kohm'), 2)} kΩ ({jsn(x.get('n_segs'))}× {jsn(x.get('r_width'))}×{jsn(x.get('r_length'))} μm)"
                    for x in card.get("resistors") or []) or "None"
    return [
        ["Architecture", f"{card.get('arch_title')} ({card.get('stages')}-stage, {card.get('input_type')} input)"],
        ["Supply & Common Mode", f"VDD = {num(card.get('vdd'), 1)} V, VCM = {num(card.get('vcm'), 2)} V"],
        ["Current Envelope & Reference", f"{card.get('iclass_label')} (Iref = {fmt_idd(card.get('iref_ua'))})"],
        ["Inversion Target", f"{card.get('inv_label')} (input gm/Id = {jsn(card.get('gmid_target'))} V⁻¹)"],
        ["Input ICMR / Output Swing", f"ICMR {num(nom.get('icmr_min_v'), 2)}–{num(nom.get('icmr_max_v'), 2)} V ({num(nom.get('icmr_span_v'), 2)} V) · Swing {num(nom.get('vout_swing_v'), 2)} V"],
        ["Input Impedance @ 1 kHz", f"1×: {num(nom.get('zin_1khz_mohm'), 1)} MΩ · 6×: {num(nom.get('zin_6x_1khz_mohm'), 1)} MΩ"],
        ["MIM Capacitors (`cap_mim_2f0fF`)", caps],
        ["Poly Resistors (`ppolyf_u_1k`)", res],
    ]


def extra_nominal_items(nom):
    return [
        ["DC output (V<sub>out,DC</sub>)", f"{num(nom.get('vout_dc'), 3)} V"],
        ["Total supply current incl. reference", fmt_idd(nom.get("idd_total_ua"))],
        ["Output range V<sub>out,min</sub> – V<sub>out,max</sub>", f"{num(nom.get('vout_min_v'), 3)} – {num(nom.get('vout_max_v'), 3)} V"],
        ["Noise @ 100 Hz / 1 kHz / 100 kHz", f"{num(nom.get('vn_100hz_nv_rthz'), 1)} / {num(nom.get('vn_1khz_nv_rthz'), 1)} / {num(nom.get('vn_100khz_nv_rthz'), 1)} nV/√Hz"],
        ["Z<sub>in</sub> @ 100 kHz (1× / 6×)", f"{num(nom.get('zin_100khz_mohm'), 2)} / {num(nom.get('zin_6x_100khz_mohm'), 2)} MΩ"],
        ["Gain margin", f"{num(nom.get('gm_db'), 2)} dB"],
        ["Nominal offset V<sub>os</sub>", f"{num(nom.get('vos_mv'), 3)} mV"],
        ["Step overshoot / BW·settling ratio", f"{num(nom.get('overshoot_pct'), 2)}% / {num(nom.get('bw_settle_ratio'), 3)}"],
        ["Distortion test tone", f"{si(nom.get('f_in_hz'), 'Hz')}, {num(nom.get('v_amp_v'), 3)} V amplitude"],
        {"label": "PM check / step-stable / valid PM", "value": " / ".join("✓" if nom.get(k) else "✗" for k in ("pm_pass", "step_stable", "valid_pm")),
         "s": "good" if nom.get("pm_pass") and nom.get("step_stable") else "warn"},
    ]


OP_COLS = [
    {"key": "dev", "label": "Device", "type": "text"}, {"key": "role", "label": "Role", "type": "text"},
    {"key": "model", "label": "Model", "type": "text"}, {"key": "nets", "label": "Nets (D, G, S, B)", "type": "text"},
    {"key": "wf", "label": "W<sub>f</sub> (µm)", "digits": 4}, {"key": "l", "label": "L (µm)", "digits": 4},
    {"key": "m", "label": "m", "digits": 4}, {"key": "wt", "label": "W<sub>tot</sub> (µm)", "digits": 5},
    {"key": "gt", "label": "gm/Id Tgt", "digits": 3}, {"key": "gs", "label": "gm/Id Sim", "digits": 4},
    {"key": "it", "label": "I<sub>D</sub> Tgt", "unit": "A", "si": True}, {"key": "is", "label": "I<sub>D</sub> Sim", "unit": "A", "si": True},
    {"key": "vgs", "label": "V<sub>GS</sub> (V)", "digits": 4}, {"key": "vds", "label": "V<sub>DS</sub> (V)", "digits": 4},
    {"key": "vdsat", "label": "V<sub>DSAT</sub> (V)", "digits": 4},
    {"key": "hr", "label": "|V<sub>DS</sub>|−V<sub>DSAT</sub> (V)", "digits": 4, "title": "Saturation headroom computed from the simulated V_DS and V_DSAT (red when negative)"},
    {"key": "gm", "label": "g<sub>m</sub>", "unit": "S", "si": True, "group": "Additional OP data"}, {"key": "gds", "label": "g<sub>ds</sub>", "unit": "S", "si": True, "group": "Additional OP data"},
    {"key": "vth", "label": "V<sub>th</sub> (V)", "digits": 4, "group": "Additional OP data"}, {"key": "sat", "label": "Sat.", "type": "status", "group": "Additional OP data"},
]


def op_rows(card):
    ops = nom_of(card, "pre").get("dev_ops") or {}
    rows = []
    for d in card.get("devices") or []:
        op = ops.get(d.get("name")) or {}
        hr = abs(op["vds"]) - abs(op["vdsat"]) if fin(op.get("vds")) and fin(op.get("vdsat")) else None
        rows.append([f"M{d.get('name')}", d.get("role"), d.get("model"), f"{d.get('d')}, {d.get('g')}, {d.get('s')}, {d.get('b')}",
                     r5(d.get("w_finger")), r5(d.get("l")), d.get("m"), r5(d.get("w_total")), r5(d.get("target_gmid")),
                     r5(op.get("gmid_sim")), scale(d.get("target_id_ua"), 1e-6), scale(op.get("id_ua"), 1e-6),
                     r5(op.get("vgs")), r5(op.get("vds")), r5(op.get("vdsat")),
                     {"v": r5(hr), "s": "bad"} if hr is not None and hr < 0 else r5(hr),
                     scale(op.get("gm_us"), 1e-6), scale(op.get("gds_ns"), 1e-9), r5(op.get("vth")), op.get("saturated")])
    return rows


PVT_COLS = [
    {"key": "corner", "label": "Corner", "type": "text"}, {"key": "temp", "label": "Temp (°C)", "digits": 3},
    {"key": "vcorner", "label": "V<sub>DD</sub> (V)", "digits": 3}, {"key": "idd", "label": "I<sub>DD</sub>", "unit": "A", "si": True},
    {"key": "a0", "label": "DC Gain (dB)", "digits": 5}, {"key": "ugb", "label": "UGB", "unit": "Hz", "si": True},
    {"key": "pm", "label": "PM (°)", "digits": 5}, {"key": "gm", "label": "GM (dB)", "digits": 4},
    {"key": "vos", "label": "V<sub>os</sub> (mV)", "digits": 5}, {"key": "os", "label": "Overshoot (%)", "digits": 4},
    {"key": "ts", "label": "1% Settling (μs)", "digits": 6}, {"key": "sat", "label": "All sat.", "type": "status"},
    {"key": "pass", "label": "Pass", "type": "text"},
]


def pvt_rows(pts):
    out = []
    for p in pts:
        ok = bool(p.get("pm_pass") and p.get("step_stable"))
        # vdd column renamed so the table does not follow the global VDD filter
        out.append([p.get("corner"), p.get("temp_c"), r5(p.get("vdd")), scale(p.get("idd_ua"), 1e-6), r5(p.get("a0_db")),
                    r5(p.get("ugb_hz")), r5(p.get("pm_deg")), r5(p.get("gm_db")), r5(p.get("vos_mv")), r5(p.get("overshoot_pct")),
                    r5(p.get("ts_1pct_us"), 7), p.get("all_saturated"), {"v": "PASS" if ok else "WARN", "s": "good" if ok else "warn"}])
    return out


def pvt_summary_items(pvt):
    if not pvt:
        return None
    ok = pvt.get("pvt_robust")
    return [
        {"label": "Corners passing", "value": f"{pvt.get('n_pass')}/{pvt.get('n_points')}", "s": "good" if ok else "warn"},
        {"label": "PVT-robust (17/17, PM > 45°)", "value": bool(ok), "s": "good" if ok else "warn"},
        ["PM min / max", f"{num(pvt.get('pm_min_deg'), 2)}° / {num(pvt.get('pm_max_deg'), 2)}°"],
        ["Worst-case DC gain", f"{num(pvt.get('a0_min_db'), 2)} dB"],
        ["Worst-case UGB", si(pvt.get("ugb_min_hz"), "Hz")],
        ["I<sub>DD</sub> min / max", f"{fmt_idd(pvt.get('idd_min_ua'))} / {fmt_idd(pvt.get('idd_max_ua'))}"],
    ]


def mc_summary_items(mc):
    if not mc:
        return None
    y = mc.get("yield_pct")
    return [
        ["Runs completed", f"{mc.get('n_completed')}/{mc.get('n_planned')}"],
        {"label": "Yield", "value": f"{num(y, 1)}%", "s": "good" if (y or 0) >= 90 else "warn"},
        ["Yield criterion", mc.get("yield_check") or "—"],
        ["V<sub>os</sub> mean / σ", f"{num(mc.get('vos_mean_mv'), 3)} / {num(mc.get('vos_sigma_mv'), 3)} mV"],
        ["PM mean / σ / P5", f"{num(mc.get('pm_mean_deg'), 2)}° / {num(mc.get('pm_sigma_deg'), 2)}° / {num(mc.get('pm_p5_deg'), 2)}°"],
        ["Mean UGB / DC gain", f"{si(mc.get('ugb_mean_hz'), 'Hz')} / {num(mc.get('a0_mean_db'), 2)} dB"],
        ["Mean I<sub>DD</sub>", fmt_idd(mc.get("idd_mean_ua"))],
    ]


def phys_items(p):
    items = [
        ["Bounding Box (W × H)", f"{num(p.get('width_um'), 2)} μm × {num(p.get('height_um'), 2)} μm ({num(p.get('area_um2'), 2)} μm²)"],
        ["Aspect Ratio & Blocks", f"{num(p.get('aspect_ratio'), 3)} ({p.get('n_blocks') if p.get('n_blocks') is not None else '—'} placeable blocks)"],
        ["Routed Wirelength & Vias", f"{num(p.get('wirelength_um'), 1)} μm wirelength · {p.get('vias') if p.get('vias') is not None else '—'} vias"],
        {"label": "KLayout DRC (`gf180mcu.drc`)", "value": "0 effective violations (PASS)" if p.get("drc_ok") else "Pending", "s": "good" if p.get("drc_ok") else "warn"},
        {"label": "KLayout LVS (`gf180mcu.lvs`)", "value": p.get("lvs_conclusion") or "Pending", "s": "good" if p.get("lvs_ok") else "warn"},
        ["Extracted MOSFET Fingers", f"{p.get('nfet_fingers', '—')} nfet_03v3 + {p.get('pfet_fingers', '—')} pfet_03v3 fingers"],
        ["Extracted Passives", f"{p.get('mim_caps') or 0} Option-B MIM caps · {p.get('poly_resistors') or 0} ppolyf_u_1k segments"],
        ["Extracted Parasitic Caps", f"{p.get('parasitic_c_count') or 0} coupling/ground capacitances"],
        {"label": "Magic PEX", "value": "Extracted" if p.get("pex_ok") else "Pending", "s": "good" if p.get("pex_ok") else "warn"},
        ["DRC effective / ignored violations", f"{p.get('drc_effective', '—')} / {p.get('drc_ignored', '—')}"],
    ]
    if p.get("drc_by_rule"):
        items.append(["DRC violations by rule", ", ".join(f"{k}: {v}" for k, v in sorted(p["drc_by_rule"].items()))])
    return items


def detail_doc(lt, ld, card, base, twin):
    phys = card.get("physical") or {}
    cl_pf = card.get("cl_pf", ld.get("cl_f", 0) * 1e12)
    blocks = []

    # ---- Overview
    ov = []
    ov += stage_alts("kpi", lambda st: {"type": "stats", "items": kpi_items(card, st, phys, cl_pf), "span": 2},
                     "Key nominal results (TT, 27 °C)")
    ov += stage_alts("checklist", lambda st: {"type": "table", "columns": [
        {"key": "check", "label": "Check", "type": "text", "wrap": True}, {"key": "ev", "label": "Evidence Summary", "type": "text", "wrap": True},
        {"key": "st", "label": "Status", "type": "text"}], "rows": checklist_rows(card, st, phys), "csv": False, "search": False},
        "Verification Signoff Checklist")
    ov += stage_alts("target", lambda st: {"type": "kv", "cols": 1, "items": design_target_items(card, st)},
                     "Design Target & Passive Compensation")
    ov += stage_alts("extra_nom", lambda st: {"type": "kv", "cols": 2, "span": 2, "items": extra_nominal_items(nom_of(card, st))}
                     if nom_of(card, st) else None, "Additional nominal measurements")
    blocks.append({"type": "section", "title": "Overview", "cols": 2, "blocks": ov,
                   "intro": "Values follow the **Simulation** stage selector (Pre-PEX schematic or Full post-PEX = Magic-extracted netlist). "
                            "Sub-texts compare pre-PEX → post-PEX nominal values as on the original card."})

    # ---- Schematic & OP
    files = card.get("files") or {}
    sch = files.get("schematic_svg")
    sblocks = [{"type": "downloads", "items": [x for x in [
        {"label": "Pre-PEX SPICE Subcircuit", "file": files.get("netlist_spice")} if files.get("netlist_spice") else None,
        {"label": "Post-PEX Extracted SPICE", "file": files.get("pex_spice")} if files.get("pex_spice") else None,
        {"label": "Full-Resolution Schematic SVG", "src": sch} if sch else None] if x]}]
    if sch:
        sblocks.append({"type": "markdown", "text": "Transistor-level schematic annotated with per-finger W/L, finger multiplier m, target gm/Id, and simulated operating-point gm/Id & drain current: "
                                                    "see **Figures → Schematic** at the top of this page (click it to open the full-resolution SVG and zoom in the browser)."})
    sblocks.append({"type": "table", "title": "Transistor Sizing & Simulated Operating Point (Nominal TT, 27 °C)",
                    "columns": OP_COLS, "rows": op_rows(card), "search": False,
                    "caption": "Operating point (g<sub>m</sub>/I<sub>D</sub>, I<sub>D</sub>, V<sub>GS</sub>, V<sub>DS</sub>, V<sub>DSAT</sub> …) from the **pre-PEX** schematic simulation — the post-PEX netlist carries no per-device operating-point map. The headroom column |V<sub>DS</sub>|−V<sub>DSAT</sub> is computed from the simulated values (red = negative)."})
    blocks.append({"type": "section", "title": "Schematic & gm/Id operating point", "blocks": sblocks})

    # ---- Simulation waveforms (stage alternatives) + overlay
    sim = []
    pre_c = {k: (t, d, L) for k, t, d, L in waveform_charts(card, "pre")}
    post_c = {k: (t, d, L) for k, t, d, L in waveform_charts(card, "full")}
    for k, t, d, L in waveform_charts(card, "pre"):
        for st, src in (("pre", pre_c), ("full", post_c)):
            tt, dd, LL = src[k]
            if dd:
                sim.append(chart(tt, dd, LL, alt=f"w_{k}", stage=st))
    blocks.append({"type": "section", "title": "Simulation waveforms", "cols": 2, "blocks": sim,
                   "intro": "Interactive ngspice-46 waveforms from the compute farm (nominal TT, 27 °C) at the selected simulation stage. "
                            "The section below overlays both stages (solid: pre-PEX schematic; dashed: post-PEX Magic-extracted netlist), as the original site did by default."})
    ovl = [chart(t, d, L) for k, t, d, L in waveform_charts(card, "overlay") if d]
    blocks.append({"type": "section", "title": "Simulation waveforms — pre-PEX vs post-PEX overlay", "cols": 2, "collapsed": True,
                   "blocks": ovl, "intro": "Solid curves: Pre-PEX schematic; dashed curves: Post-PEX Magic extracted netlist."})

    # ---- PVT & MC
    rob = []
    rob += stage_alts("pvt_sum", lambda st: {"type": "kv", "cols": 1, "items": pvt_summary_items(part_of(card, st, "pvt"))}
                      if part_of(card, st, "pvt") else None, "17-corner PVT summary")
    rob += stage_alts("mc_sum", lambda st: {"type": "kv", "cols": 1, "items": mc_summary_items(part_of(card, st, "mc"))}
                      if part_of(card, st, "mc") else None, "50-run mismatch Monte Carlo summary")
    pm_pre = {k: (t, d, L) for k, t, d, L in pvt_mc_charts(card, "pre")}
    pm_post = {k: (t, d, L) for k, t, d, L in pvt_mc_charts(card, "full")}
    for k in ("pvt_pm", "pvt_a0", "mc_hist", "mc_scatter"):
        for st, src in (("pre", pm_pre), ("full", pm_post)):
            if k in src and src[k][1]:
                t, d, L = src[k]
                rob.append(chart(t, d, L, alt=k, stage=st, height=400 if k.startswith("pvt") else None))
    rob += stage_alts("pvt_tab", lambda st: {"type": "table", "columns": PVT_COLS, "span": 2, "search": False,
                                             "rows": pvt_rows(part_of(card, st, "pvt").get("points") or []),
                                             "title": f"All {len(part_of(card, st, 'pvt').get('points') or [])} Recorded PVT Corner Evaluations ({'Pre-PEX' if st == 'pre' else 'Post-PEX'})"}
                      if part_of(card, st, "pvt").get("points") else None, "All 17 Recorded PVT Corner Evaluations")
    blocks.append({"type": "section", "title": "PVT corners & mismatch Monte Carlo", "cols": 2, "blocks": rob,
                   "intro": "17-point PVT matrix (tt/ff/ss/sf/fs × −40/27/125 °C plus tt 27 °C at ±10 % V<sub>DD</sub>) and 50-run per-finger mismatch Monte Carlo at the selected simulation stage. "
                            "PASS = PM > 45° and closed-loop step stable."})
    cmp_blocks = [chart(t, d, L, height=400 if k.startswith("pvt") else None) for k, t, d, L in pvt_mc_charts(card, "overlay") if d]
    blocks.append({"type": "section", "title": "PVT & Monte Carlo — pre-PEX vs post-PEX comparison", "cols": 2, "collapsed": True,
                   "blocks": cmp_blocks, "intro": "Grouped pre-PEX and post-PEX bars per corner (as on the original card) and both Monte Carlo populations overlaid."})

    # ---- Physical layout & PEX
    gds = phys.get("gds_gz") or files.get("gds_gz")
    lay_blocks = [{"type": "note", "tone": "info", "span": 2,
                   "text": f"Full-custom passive-inclusive physical layout generated with experimental gLayout (PR #128) · DRC: **{'0 effective violations (PASS)' if phys.get('drc_ok') else 'Pending'}** · "
                           f"LVS: **{phys.get('lvs_conclusion') or 'Pending'}** · Magic PEX: **{'Extracted (%s parasitic caps)' % phys.get('parasitic_c_count') if phys.get('pex_ok') else 'Pending'}**"}]
    if gds:
        lay_blocks.append({"type": "markdown", "span": 2,
                           "text": f"Footprint: {num(phys.get('width_um'), 2)} μm × {num(phys.get('height_um'), 2)} μm = {num(phys.get('area_um2'), 1)} μm². "
                                   "The layout view is **Figures → Layout** at the top of this page (rendered by the hub from the GDS; the thumbnail size line is the GDS bounding box). "
                                   "The full-resolution layout is the GDS file below."})
    lay_blocks.append({"type": "downloads", "span": 2, "items": [x for x in [
        {"label": "Compressed GDSII (.gds.gz)", "file": gds} if gds else None,
        {"label": "KLayout LVS Reference Netlist", "file": phys.get("lvs_ref_spice") or files.get("lvs_ref_spice")} if (phys.get("lvs_ref_spice") or files.get("lvs_ref_spice")) else None,
        {"label": "Magic Post-PEX Extracted Netlist", "file": phys.get("pex_spice") or files.get("pex_spice")} if (phys.get("pex_spice") or files.get("pex_spice")) else None] if x]})
    lay_blocks.append({"type": "kv", "cols": 1, "title": "Physical Verification & Extraction Summary", "items": phys_items(phys)})
    lay_blocks.append({"type": "table", "title": "Top-Level Pin Coordinates (METAL2 36/10)", "search": False, "csv": False,
                       "columns": [{"key": "n", "label": "Port Name", "type": "text"}, {"key": "l", "label": "Layer", "type": "text"},
                                   {"key": "g", "label": "GDS (Layer/DT)", "type": "text"}, {"key": "x", "label": "X (μm)", "digits": 7},
                                   {"key": "y", "label": "Y (μm)", "digits": 7}],
                       "rows": [[p.get("name"), p.get("layer"), "/".join(str(v) for v in (p.get("gds_layer") or [])), p.get("x_um"), p.get("y_um")]
                                for p in phys.get("pin_coords") or []]})
    blocks.append({"type": "section", "title": "Physical layout & PEX", "cols": 2, "blocks": lay_blocks})

    # ---- Files & provenance
    h = card.get("hashes") or {}
    prov = [{"type": "downloads", "items": [x for x in [
        {"label": "Complete Card Evidence JSON", "file": files.get("card_json")} if files.get("card_json") else None,
        {"label": "Pre-PEX SPICE Subcircuit", "file": files.get("netlist_spice")} if files.get("netlist_spice") else None,
        {"label": "Post-PEX SPICE Subcircuit", "file": files.get("pex_spice")} if files.get("pex_spice") else None,
        {"label": "Load Library Manifest JSON", "file": f"data/{lt}/library.json"}] if x]},
        {"type": "table", "title": "Integration & Artifact Provenance", "search": False, "csv": False,
         "columns": [{"key": "k", "label": "Item", "type": "text"}, {"key": "v", "label": "Value", "type": "text", "md": True}],
         "rows": [["Subcircuit Signature", f"`.subckt opamp_dut {' '.join(card.get('ports') or ['vdd', 'vss', 'inp', 'inn', 'out', 'ib'])}`"],
                  ["PDK & Models Required", "GF180MCU-D (`sm141064.ngspice`): `nfet_03v3`, `pfet_03v3`, `cap_mim_2f0fF`, `ppolyf_u_1k`"],
                  ["Pre-PEX Netlist SHA-256", f"`{h.get('netlist_spice_sha256') or '—'}`"],
                  ["Post-PEX Netlist SHA-256", f"`{h.get('pex_spice_sha256') or '—'}`"],
                  ["GDSII Archive SHA-256", f"`{h.get('gds_gz_sha256') or '—'}`"],
                  ["Card / load", f"`{card.get('card_id')}` · load tag `{lt}` (C<sub>L</sub> = {jsn(cl_pf)} pF)"]]}]
    blocks.append({"type": "section", "title": "Files & provenance", "blocks": prov})
    return {"blocks": blocks}


# ============================================================================ pages
def overview_page(loads, summ, ulp, ids):
    meta = summ[loads[0]["id"]]["meta"]
    archs, classes, regimes = meta["architectures"], meta["current_classes"], meta["inversion_regimes"]
    total_sims = max(summ[ld["id"]]["meta"].get("total_farm_sims", 0) for ld in loads)
    intro = (
        "**GM/ID SIZING · COMPUTE FARM NGSPICE-46 · EXPERIMENTAL GLAYOUT PR #128 · MAGIC PEX**\n\n"
        "## Deliverable operational amplifier library\n\n"
        "Twelve architectures (including NMOS/PMOS 5-T, Miller, Telescopic & Folded Cascode, Symmetrical, Rail-to-Rail, Cherry-Hooper, "
        "and Current-Reuse Complementary Input LNA) spanning Ultra-Low-Power (<0.1 μW, <10 kHz High-Gain) plus six standard supply/current "
        "classes (1.8 V & 3.3 V; 0.1–1 μA, 1–10 μA, 10–100 μA) across two gm/Id inversion regimes (sub-threshold 23.5 V⁻¹ and weak-inversion "
        "16.5 V⁻¹). Select any cell or card to inspect its gm/Id-annotated schematic, multi-bench Pre-PEX & Post-PEX waveforms, 17-corner PVT & "
        "50-run mismatch Monte Carlo distributions, and DRC/LVS-clean physical layout.\n\n"
        "GF180MCU-D (3.3 V FETs at 1.8 V & 3.3 V · Option-B MIM Cap · High-Rs Poly Res) · Nominal C<sub>L</sub> = "
        + " or ".join(f"**{ld['label']}**" for ld in loads) + "  \n"
        "12 Architectures × 2 Inversion Regimes × (ULP <0.1 μW + 6 V<sub>DD</sub>/I<sub>DD</sub> Classes) = **168 Deliverable Designs / Load**\n\n"
        "The **Designs** tab holds the coverage matrix (pick the load with the *Load* filter, the stage with the *Simulation* selector), the design "
        "cards and the sortable comparison table with CSV export. This page reproduces the original library view: per-load statistics, the classic "
        "coverage matrix with its ultra-low-power frontier column, and the dataset downloads.")
    blocks = []
    tabs = []
    for ld in loads:
        m = summ[ld["id"]]["meta"]
        sblocks = [{"type": "stats", "title": "All supplies", "items": [
            {"label": f"deliverable cards · CL = {m['cl_label']}", "value": str(m["total_cards"])},
            {"label": "pass all 17 PVT corners (>45° PM) — pre-PEX", "value": f"{m['pre_pvt_robust_count']}/{m['total_cards']}"},
            {"label": "pass all 17 PVT corners (>45° PM) — post-PEX", "value": f"{m.get('post_pvt_robust_count', '—')}/{m['total_cards']}"},
            {"label": "post-PEX results available", "value": f"{m.get('post_ready_count', '—')}/{m['total_cards']}"},
            {"label": "DRC/LVS/PEX-clean physical layouts", "value": f"{m['phys_clean_count']}/{m['total_cards']}"},
            {"label": "ngspice-46 compute farm evaluations", "value": f"{m['total_farm_sims']:,}"},
        ]}]
        for vdd in sorted({c["vdd"] for c in summ[ld["id"]]["cards"]}):
            cs = [c for c in summ[ld["id"]]["cards"] if c["vdd"] == vdd]
            n = len(cs)
            sblocks.append({"type": "stats", "vdd": vdd, "title": f"V<sub>DD</sub> = {jsn(vdd)} V", "items": [
                {"label": f"deliverable cards · CL = {m['cl_label']}", "value": str(n)},
                {"label": "pass all 17 PVT corners — pre-PEX", "value": f"{sum(1 for c in cs if (c.get('pre') or {}).get('pvt_robust'))}/{n}"},
                {"label": "pass all 17 PVT corners — post-PEX", "value": f"{sum(1 for c in cs if (c.get('post') or {}).get('pvt_robust'))}/{n}"},
                {"label": "DRC/LVS/PEX-clean physical layouts", "value": f"{sum(1 for c in cs if all((c.get('physical') or {}).get(k) for k in ('drc_ok', 'lvs_ok', 'pex_ok')))}/{n}"},
            ]})
        tabs.append({"label": f"C<sub>L</sub> = {ld['label']}", "key": ld["id"], "blocks": sblocks})
    blocks.append({"type": "section", "title": "Library statistics", "intro": "Totals over both supplies, then per supply (the per-supply tiles follow the global V<sub>DD</sub> option).",
                   "blocks": [{"type": "tabs", "id": "stats", "tabs": tabs}]})

    # classic coverage matrix (port of renderMatrix) per load and stage
    ulp_t = (ulp or {}).get("topologies") or {}
    vcols = {}
    for vt, vl in (("1v8", "1.8"), ("3v3", "3.3")):
        cols = [{"key": "row", "label": "Architecture · Regime (gm/Id)", "type": "text", "wrap": True}]
        if vt == "1v8":
            cols.append({"key": "ulp", "label": "Low Power (<0.1 μW)", "md": True, "group": "ULP High-Gain (<10 kHz)", "type": "text", "wrap": True})
        for c in classes:
            cols.append({"key": f"{vt}_{c['tag']}", "label": c["label"], "md": True, "type": "text", "wrap": True, "group": f"V<sub>DD</sub> = {vl} V"})
        vcols[vt] = cols
    mtabs = []
    for ld in loads:
        lt = ld["id"]
        cards = {c["card_id"]: c for c in summ[lt]["cards"]}
        alts = []
        for st in ("pre", "full"):
            rows = []
            for a in archs:
                top = ulp_t.get(a["id"]) or {}
                mp, mg = top.get("min_power_design"), top.get("max_gain_design")
                min_pwr = (f"{num(mp['power_nw'] * 1000, 1)} pW" if mp["power_nw"] < 1 else f"{num(mp['power_nw'], 1)} nW") if mp else ""
                max_gain = f"{num(mg['a0_db'], 1)} dB" if mg else ""
                for r in regimes:
                    reg_short = "Sub-th" if r["tag"] == "subth" else "Weak-inv"
                    row = {"row": f"{a['short']} · {reg_short} ({jsn(r['gmid_target_in'])} V⁻¹)"}
                    ucid = f"{a['id']}_1v8_ulp_lt0p1uw_{r['tag']}"
                    uc = cards.get(ucid)
                    if uc:
                        s = (uc.get("post") if st == "full" else uc.get("pre")) or {}
                        _, kind = status_tuple(s)
                        st_short = "17/17 PVT" if s.get("pvt_robust") else f"{s.get('pvt_pass') if s.get('pvt_pass') is not None else 16}/17 PVT"
                        p = uc.get("physical") or {}
                        ptag = "DRC/LVS✓" if p.get("drc_ok") and p.get("lvs_ok") else "GDS✓" if p.get("layout_ok") else ""
                        bw = s.get("cl_bw_hz") or s.get("ugb_hz") or 0
                        ftag = f"<br><small>**Min {min_pwr} · Max {max_gain}**</small>" if min_pwr and max_gain else ""
                        row["ulp"] = {"v": f"[**{num(s.get('a0_db'), 1)} dB**](#/opa/{lt}-{ucid}) · BW {si(bw, 'Hz')}<br><small>{fmt_pwr(s.get('power_uw'))} · PM {num(s.get('pm_deg'), 1)}° · {st_short} {ptag}</small>{ftag}",
                                      "s": kind, "title": f"{lt}-{ucid}"}
                    elif top:
                        row["ulp"] = {"v": f"**{max_gain}** · min {min_pwr}<br><small>{top.get('valid_ulp_count')} valid <10 kHz</small>", "s": "good"}
                    else:
                        row["ulp"] = "—"
                    for vt in ("1v8", "3v3"):
                        for ic in classes:
                            cid = f"{a['id']}_{vt}_{ic['tag']}_{r['tag']}"
                            c = cards.get(cid)
                            if not c:
                                row[f"{vt}_{ic['tag']}"] = "—"
                                continue
                            s = (c.get("post") if st == "full" else c.get("pre")) or {}
                            _, kind = status_tuple(s)
                            st_short = "17/17 PVT" if s.get("pvt_robust") else f"{s.get('pvt_pass') if s.get('pvt_pass') is not None else 16}/17 PVT"
                            p = c.get("physical") or {}
                            ptag = "DRC/LVS✓" if p.get("drc_ok") and p.get("lvs_ok") else "GDS✓" if p.get("layout_ok") else ""
                            row[f"{vt}_{ic['tag']}"] = {"v": f"[**{si(s.get('ugb_hz') or 0, 'Hz')}**](#/opa/{lt}-{cid}) · {num(s.get('a0_db'), 1)} dB<br><small>PM {num(s.get('pm_deg'), 1)}° · {st_short} {ptag}</small>",
                                                        "s": kind, "title": f"{lt}-{cid}"}
                    rows.append(row)
            for vt, vnum in (("1v8", 1.8), ("3v3", 3.3)):
                keys = [c["key"] for c in vcols[vt]]
                alts.append({"type": "table", "alt": f"mx_{lt}_{vt}", "stage": st, "vdd": vnum, "columns": vcols[vt],
                             "rows": [{k: r.get(k) for k in keys} for r in rows], "csv": False, "search": False, "max_height": 2400,
                             "title": f"C<sub>L</sub> = {ld['label']} · V<sub>DD</sub> = {jsn(vnum)} V{' (+ ULP column)' if vt == '1v8' else ''} — {'Pre-PEX schematic' if st == 'pre' else 'Post-PEX extracted'} results"})
        mtabs.append({"label": f"C<sub>L</sub> = {ld['label']}", "key": lt, "blocks": alts})
    blocks.append({"type": "section", "title": "Coverage matrix (12 architectures × 2 regimes × [Low Power <0.1 μW + 6 V<sub>DD</sub>/I<sub>DD</sub> classes] = 168 cells)",
                   "intro": "The **Low Power (<0.1 μW)** column highlights low-speed (<10 kHz closed-loop BW), high-gain nW/pW designs alongside the standard 1.8 V and 3.3 V current envelopes. "
                            "ULP cells show A<sub>0</sub> · closed-loop BW, power, PM, PVT and the per-topology ULP frontier (minimum power · maximum gain, from the ULP exploration); standard cells show UGB · A<sub>0</sub>, PM and PVT. "
                            "Green = 17/17 PVT pass, amber = nominal PM pass but < 17/17 PVT, red = screen warning. Click a value to open the design card. "
                            "The values follow the **Simulation** stage selector (Pre-PEX / Full post-PEX); the interactive matrix with a metric selector is on the **Designs** tab.",
                   "blocks": [{"type": "tabs", "id": "mx", "tabs": mtabs}]})

    dls = [{"label": f"{ld['label']} Library Manifest (JSON)", "file": f"data/{ld['id']}/library.json"} for ld in loads]
    dls += [{"label": f"{ld['label']} Coverage Summary (JSON)", "file": f"data/{ld['id']}/summary.json"} for ld in loads]
    dls += [{"label": "Topology Parameter Boundaries (JSON)", "file": "data/param_boundaries.json"},
            {"label": "GF180 gm/Id LUT Curves (JSON)", "file": "data/lut.json"},
            {"label": "Ultra-Low-Power Frontier (JSON)", "file": "data/ulp_exploration.json"}]
    dls += [{"label": f"{ld['label']} Design-Space Candidates (JSON)", "file": f"data/{ld['id']}/dse.json"} for ld in loads]
    dls += [{"label": "Load definitions (JSON)", "file": "loads.json"}]
    blocks.append({"type": "section", "title": "Downloads", "blocks": [
        {"type": "downloads", "items": dls},
        {"type": "markdown", "text": "All SPICE simulations executed on the remote compute farm using ngspice-46 and GF180MCU-D models. Physical layouts generated with experimental gLayout (PR #128) and verified with KLayout DRC/LVS and Magic PEX."}]})
    return {"intro": intro, "blocks": blocks}, total_sims


def dse_data(loads, summ, dse, out, ids):
    """Columnar explorer data: candidates + delivered pre/post points (per load and combined)."""
    keys = ["idd", "ugb", "a0", "pm", "fom", "vos", "arch", "archs", "kind", "cls", "regime", "supply", "pmpass", "load", "vdd", "stage", "design", "delivered", "label"]
    allc = {k: [] for k in keys}
    for ld in loads:
        lt = ld["id"]
        cl_pf = ld.get("cl_f", 0) * 1e12 or summ[lt]["meta"].get("cl_pf")
        C = {k: [] for k in keys}

        def add(**kw):
            for k in keys:
                C[k].append(kw.get(k))
        for p in (dse.get(lt) or {}).get("points") or []:
            did = f"{lt}-{p['card_id']}"
            add(idd=scale(p.get("idd_ua"), 1e-6), ugb=r5(p.get("ugb_hz")), a0=r5(p.get("a0_db")), pm=r5(p.get("pm_deg")),
                fom=r5(p.get("fom_s")), vos=scale(p.get("vos_mv"), 1e-3), arch=p.get("arch"),
                archs=p.get("arch") if p.get("feasible") else "screened",
                kind="feasible" if p.get("feasible") else "screened", cls=p.get("iclass_tag"), regime=p.get("inv_tag"),
                supply=p.get("vdd_tag"), pmpass="pass" if p.get("pm_pass") else "fail", load=lt, vdd=p.get("vdd"),
                design=did if did in ids else None, delivered=False, label=f"{p['card_id']} · candidate #{p.get('cand_idx')}")
        for c in summ[lt]["cards"]:
            did = f"{lt}-{c['card_id']}"
            for st, kind in (("pre", "del_pre"), ("post", "del_post")):
                s = c.get(st)
                if not s:
                    continue
                fom = s["ugb_hz"] / 1e6 * cl_pf / (s["idd_ua"] / 1e3) if fin(s.get("ugb_hz")) and fin(s.get("idd_ua")) and s["idd_ua"] > 0 else None
                add(idd=scale(s.get("idd_ua"), 1e-6), ugb=r5(s.get("ugb_hz")), a0=r5(s.get("a0_db")), pm=r5(s.get("pm_deg")),
                    fom=r5(fom), vos=scale(s.get("vos_mv"), 1e-3), arch=c["arch"], archs=c["arch"], kind=kind, cls=c["iclass_tag"], regime=c["inv_tag"],
                    supply=c["vdd_tag"], pmpass="pass" if s.get("pm_pass") else "fail", load=lt, vdd=c["vdd"],
                    stage="pre" if st == "pre" else "full", design=did, delivered=True,
                    label=f"{c['card_id']} · delivered ({'pre-PEX' if st == 'pre' else 'post-PEX'})")
        dump(out / "data" / f"dse_{lt}.json", {"columns": {k: v for k, v in C.items() if k != "load"}})
        for k in keys:
            allc[k] += C[k]
    dump(out / "data" / "dse_all.json", {"columns": allc})


def explore_page(loads, summ, ulp, bnd, out):
    meta = summ[loads[0]["id"]]["meta"]
    archs, classes = meta["architectures"], meta["current_classes"]
    arch_labels = {a["id"]: a["short"] for a in archs}
    order = [a["id"] for a in archs]
    arch_colors = {a["id"]: ARCH_COLORS[i % len(ARCH_COLORS)] for i, a in enumerate(archs)}
    cls_labels = {meta["ulp_class"]["tag"]: "<0.1 µW (ULP)", **{c["tag"]: c["label"] for c in classes}}
    reg_labels = {r["tag"]: f"{r['label']} ({jsn(r['gmid_target_in'])} V⁻¹)" for r in meta["inversion_regimes"]}
    dims = [
        {"key": "idd", "label": "Quiescent supply current IDD", "unit": "A", "si": True, "log": True, "better": "low"},
        {"key": "ugb", "label": "Unity-gain bandwidth UGB", "unit": "Hz", "si": True, "log": True, "better": "high"},
        {"key": "a0", "label": "Open-loop DC gain A0", "unit": "dB", "better": "high", "digits": 4},
        {"key": "pm", "label": "Phase margin PM", "unit": "°", "better": "high", "digits": 4},
        {"key": "fom", "label": "Small-signal FoM UGB·CL/IDD", "unit": "MHz·pF/mA", "log": True, "better": "high", "digits": 4},
        {"key": "vos", "label": "Nominal offset Vos", "unit": "V", "si": True},
        {"key": "archs", "label": "Architecture (screened grey)", "type": "cat", "labels": {**arch_labels, "screened": "Screened candidates"},
         "order": ["screened"] + order, "colors": {**arch_colors, "screened": "#94a3b8"}},
        {"key": "arch", "label": "Architecture", "type": "cat", "labels": arch_labels, "order": order, "colors": arch_colors},
        {"key": "kind", "label": "Point type", "type": "cat", "order": ["feasible", "screened", "del_pre", "del_post"],
         "labels": {"feasible": "Feasible candidate", "screened": "Screened candidate", "del_pre": "Delivered · pre-PEX", "del_post": "Delivered · post-PEX"},
         "colors": {"feasible": "#225bb2", "screened": "#94a3b8", "del_pre": "theme:ink", "del_post": "#dc2626"},
         "symbols": {"feasible": "circle", "screened": "x", "del_pre": "diamond", "del_post": "star"}},
        {"key": "cls", "label": "Current class", "type": "cat", "labels": cls_labels, "order": list(cls_labels)},
        {"key": "regime", "label": "Inversion regime", "type": "cat", "labels": reg_labels, "order": list(reg_labels)},
        {"key": "supply", "label": "Supply", "type": "cat", "labels": {"1v8": "1.8 V", "3v3": "3.3 V"}, "order": ["1v8", "3v3"]},
        {"key": "pmpass", "label": "Nominal PM check", "type": "cat", "labels": {"pass": "PM pass", "fail": "PM fail"}, "order": ["pass", "fail"]},
    ]
    presets = [
        {"label": "UGB vs I<sub>DD</sub> (original default)", "x": "idd", "y": "ugb", "color": "archs", "symbol": "kind"},
        {"label": "A<sub>0</sub> vs I<sub>DD</sub>", "x": "idd", "y": "a0", "color": "archs", "symbol": "kind"},
        {"label": "PM vs UGB", "x": "ugb", "y": "pm", "color": "archs", "symbol": "kind"},
        {"label": "A<sub>0</sub> vs UGB", "x": "ugb", "y": "a0", "color": "archs", "symbol": "kind"},
        {"label": "FoM vs I<sub>DD</sub>", "x": "idd", "y": "fom", "color": "archs", "symbol": "kind"},
        {"label": "PM vs A<sub>0</sub>", "x": "a0", "y": "pm", "color": "archs", "symbol": "kind"},
        {"label": "Feasible vs screened", "x": "idd", "y": "ugb", "color": "kind", "symbol": "",
         "desc": "Colour = point type: feasible candidates blue, screened (PM / I<sub>DD</sub> / saturation screen failed) grey, delivered cards dark / red."},
        {"label": "Feasible only + Pareto", "x": "idd", "y": "ugb", "color": "archs", "symbol": "kind", "pareto": "all",
         "show": {"kind": ["feasible", "del_pre", "del_post"]}, "desc": "Screened candidates hidden; the front is computed over feasible, PM-passing candidates only."},
        {"label": "Per architecture", "x": "idd", "y": "ugb", "color": "kind", "symbol": "", "facet": "arch"},
        {"label": "Per current class", "x": "idd", "y": "ugb", "color": "arch", "symbol": "kind", "facet": "cls"},
        {"label": "Per supply", "x": "idd", "y": "ugb", "color": "arch", "symbol": "kind", "facet": "supply"},
        {"label": "Per regime", "x": "idd", "y": "ugb", "color": "arch", "symbol": "kind", "facet": "regime"},
    ]
    ex_common = {"type": "explorer", "dims": dims, "x": "idd", "y": "ugb", "color": "archs", "symbol": "kind",
                 "filters": ["kind", "arch", "supply", "cls", "regime", "pmpass", "a0", "pm", "ugb", "idd"],
                 "highlight": "delivered", "highlight_label": "Delivered cards", "design_key": "design", "label_key": "label",
                 "stage_group": "design", "pareto_on": {"kind": ["feasible"], "pmpass": ["pass"]},
                 "hover": ["a0", "pm", "fom", "cls", "regime", "supply", "kind"], "height": 600}
    tabs = []
    for ld in loads:
        m = summ[ld["id"]]["meta"]
        tabs.append({"label": f"C<sub>L</sub> = {ld['label']}", "key": ld["id"], "blocks": [dict(ex_common, src=f"hub/data/dse_{ld['id']}.json", presets=presets,
                     caption=f"{m['dse_points_count']:,} candidates + {m['total_cards']} delivered cards at C<sub>L</sub> = {ld['label']}. Delivered cards are ringed and drawn at the selected "
                             "**Simulation** stage (◆ pre-PEX, ■ post-PEX); candidates are pre-PEX schematic evaluations and always shown. "
                             "The Pareto front (Pareto menu) is computed over feasible, PM-passing candidates only (screened points and the delivered overlay are excluded). "
                             "FoM of delivered cards is computed with the same formula as for the candidates (UGB[MHz]·C<sub>L</sub>[pF]/I<sub>DD</sub>[mA]) from their measured UGB and I<sub>DD</sub>.")]})
    dims_all = dims + [{"key": "load", "label": "Load", "type": "cat", "labels": {ld["id"]: ld["label"] for ld in loads}, "order": [ld["id"] for ld in loads],
                        "colors": {ld["id"]: c for ld, c in zip(loads, ["#225bb2", "#d96b27", "#1e8565"])}}]
    tabs.append({"label": "Both loads (compare)", "key": "all", "blocks": [dict(ex_common, src="hub/data/dse_all.json", dims=dims_all, color="load", symbol="kind",
                 filters=["load"] + ex_common["filters"], hover=ex_common["hover"] + ["load"],
                 presets=[{"label": "UGB vs I<sub>DD</sub> by load", "x": "idd", "y": "ugb", "color": "load", "symbol": "kind"},
                          {"label": "PM vs UGB by load", "x": "ugb", "y": "pm", "color": "load", "symbol": "kind"},
                          {"label": "Per architecture (by load)", "x": "idd", "y": "ugb", "color": "load", "symbol": "kind", "facet": "arch"}]
                 + [p for p in presets if p.get("facet") != "arch"],
                 caption="Both loads in one cloud; colour = load. Use the Load chips to compare.")]})
    counts = " / ".join(f"{summ[ld['id']]['meta']['dse_points_count']:,} ({ld['label']})" for ld in loads)
    intro = (f"**PARETO DESIGN-SPACE EXPLORATION & VALID PARAMETER BOUNDARIES**\n\n"
             f"## Measured design space ({counts} candidates / load + {meta.get('bounds_jobs_count', 0):,} boundary sweeps)\n\n"
             "Every candidate point is a recorded compute-farm ngspice-46 evaluation. Circles pass all nominal constraints (PM > 45°, I<sub>DD</sub> in decade, all devices saturated); "
             f"crosses (grey) were screened out; the {meta['total_cards']} selected deliverable designs per load are ringed — ◆ pre-PEX or ■ post-PEX values, following the **Simulation** stage option "
             "(click any point to inspect the card it was generated for).")
    shift_tabs = []
    for ld in loads:
        lt = ld["id"]
        cards = [c for c in summ[lt]["cards"] if c.get("pre") and c.get("post")]
        charts = []
        for (xk, yk, xl, yl, lx, ly) in (("idd_ua", "ugb_hz", "Quiescent supply current IDD (A)", "Unity-gain bandwidth UGB (Hz)", True, True),
                                          ("ugb_hz", "pm_deg", "Unity-gain bandwidth UGB (Hz)", "Phase margin PM (°)", True, False)):
            kx = 1e-6 if xk == "idd_ua" else 1
            seg_x, seg_y = [], []
            for c in cards:
                seg_x += [r5(c["pre"][xk] * kx), r5(c["post"][xk] * kx), None]
                seg_y += [r5(c["pre"][yk]), r5(c["post"][yk]), None]
            ids = [f"{lt}-{c['card_id']}" for c in cards]
            hov = "<b>%{customdata}</b><br>%{x:.4s} · %{y:.4s}<extra>%{fullData.name}</extra>"
            data = [{"type": "scatter", "mode": "lines", "name": "pre → post shift", "x": seg_x, "y": seg_y, "hoverinfo": "skip",
                     "line": {"color": "theme:muted", "width": 1}},
                    {"type": "scatter", "mode": "markers", "name": "Deliverable (Pre-PEX)", "x": [r5(c["pre"][xk] * kx) for c in cards],
                     "y": [r5(c["pre"][yk]) for c in cards], "customdata": ids, "hovertemplate": hov,
                     "marker": {"symbol": "diamond-open", "size": 10, "color": "theme:ink", "line": {"width": 2}}},
                    {"type": "scatter", "mode": "markers", "name": "Post-PEX Extracted", "x": [r5(c["post"][xk] * kx) for c in cards],
                     "y": [r5(c["post"][yk]) for c in cards], "customdata": ids, "hovertemplate": hov,
                     "marker": {"symbol": "star-open", "size": 10, "color": "#dc2626", "line": {"width": 2}}}]
            charts.append(chart(f"{yl.split(' (')[0]} vs {xl.split(' (')[0]} — pre-PEX ◆ → post-PEX ★", data,
                                lay(xl, yl, logx=lx, logy=ly, hovermode="closest"), height=480, link_designs=True))
        shift_tabs.append({"label": f"C<sub>L</sub> = {ld['label']}", "key": lt, "blocks": [{"type": "section", "cols": 2, "blocks": charts}]})
    blocks = [{"type": "section", "title": "Interactive Pareto trade-off plot",
               "intro": "Choose X / Y / colour / symbol / facet, toggle log axes and the Pareto front, and filter by point type, architecture, supply, class, regime and numeric ranges. "
                        "The global V<sub>DD</sub> option filters the supply. Click any delivered (ringed) point — or any candidate — to open its design card.",
               "blocks": [{"type": "tabs", "id": "dse", "tabs": tabs}]},
              {"type": "section", "title": "Delivered cards: pre-PEX vs post-PEX side by side",
               "intro": "The original plot's overlay of the deliverable designs at both levels: each card's pre-PEX value (open diamond) is joined to its post-PEX value "
                        "(red open star), so the extraction shift is visible directly. These charts show both stages regardless of the Simulation option; click a marker to open the card.",
               "blocks": [{"type": "tabs", "id": "shift", "tabs": shift_tabs}]}]

    # ---------------- ULP frontier
    if ulp and ulp.get("topologies"):
        tops = list(ulp["topologies"].values())
        crit = ulp.get("criteria") or {}
        g_tr, b_tr = [], []
        for i, t in enumerate(tops):
            col = ARCH_COLORS[i % len(ARCH_COLORS)]
            lbl = t["title"].replace(" Op-Amp", "").replace(" OTA", "").replace("Current-Reuse Complementary Input LNA /", "Current-Reuse LNA")
            cv = t.get("power_scaling_curve") or []
            if cv:
                g_tr.append(line([p["power_nw"] for p in cv], [p["a0_db"] for p in cv], lbl, col, mode="lines+markers", marker={"color": col, "size": 7}))
                b_tr.append(line([p["power_nw"] for p in cv], [p["cl_bw_hz"] for p in cv], lbl, col, mode="lines+markers", marker={"color": col, "size": 7}))
        fp = lambda p: "—" if p is None else (f"{num(p * 1000, 1)} pW" if p < 1.0 else f"{num(p, 2)} nW")  # noqa: E731
        fi = lambda i: "—" if i is None else (f"{num(i * 1000, 1)} pA" if i < 1.0 else f"{num(i, 2)} nA")  # noqa: E731

        def dcell(d):
            if not d:
                return "—"
            return f"**{fp(d.get('power_nw'))}** ({fi(d.get('idd_na'))} @ {num(d.get('vdd'), 2)} V)<br><small>A<sub>0</sub> {num(d.get('a0_db'), 1)} dB · BW {num(d.get('cl_bw_hz'), 2)} Hz · PM {num(d.get('pm_deg'), 1)}°</small>"
        rows = []
        for t in tops:
            mg, env = t.get("max_gain_design"), t.get("envelopes") or {}
            rows.append({
                "top": f"**{t['title']}**<br><small>`{t['arch']}` ({t.get('stage_count')}-stage)</small>",
                "valid": {"v": f"{t.get('valid_ulp_count')}/{t.get('total_evaluated')}<br><small>≥60dB: {t.get('valid_60db_count')} · ≥80dB: {t.get('valid_80db_count')}</small>",
                          "s": "good" if (t.get("valid_ulp_count") or 0) > 100 else "warn"},
                "mp": dcell(t.get("min_power_design")), "mp60": dcell(t.get("min_power_60db_design")), "mp80": dcell(t.get("min_power_80db_design")),
                "mg": f"**{num(mg.get('a0_db'), 2)} dB** @ {fp(mg.get('power_nw'))}<br><small>{fi(mg.get('idd_na'))} @ {num(mg.get('vdd'), 2)} V · BW {num(mg.get('cl_bw_hz'), 1)} Hz · PM {num(mg.get('pm_deg'), 1)}°</small>" if mg else "—",
                "env": f"[{num(env.get('cl_bw_hz_min'), 2)}, {num(env.get('cl_bw_hz_max'), 0)}]" if env.get("cl_bw_hz_min") is not None else "—",
                "fom": f"**{num(env.get('fom_p_max'), 0)}**" if env.get("fom_p_max") is not None else "—"})
        tcols = [{"key": "top", "label": "Topology", "md": True, "type": "text", "wrap": True},
                 {"key": "valid", "label": "Valid ULP Designs<br>(<10 kHz)", "md": True, "type": "text"},
                 {"key": "mp", "label": "Min Power Frontier<br>(A<sub>0</sub> ≥ 35 dB)", "md": True, "type": "text", "wrap": True},
                 {"key": "mp60", "label": "Min Power<br>w/ A<sub>0</sub> ≥ 60 dB", "md": True, "type": "text", "wrap": True},
                 {"key": "mp80", "label": "Min Power<br>w/ A<sub>0</sub> ≥ 80 dB", "md": True, "type": "text", "wrap": True},
                 {"key": "mg", "label": "Max DC Gain A<sub>0,max</sub><br>(<10 kHz, nW)", "md": True, "type": "text", "wrap": True},
                 {"key": "env", "label": "Valid CL BW<br>Envelope (Hz)", "type": "text"},
                 {"key": "fom", "label": "Peak FoM<sub>P</sub><br>(MHz·pF/mW)", "md": True, "type": "text"}]
        ecols = [{"key": "arch", "label": "Topology", "type": "text", "wrap": True}, {"key": "n", "label": "Evaluated", "digits": 0},
                 {"key": "v", "label": "Valid", "digits": 0}, {"key": "v60", "label": "≥60 dB", "digits": 0},
                 {"key": "v80", "label": "≥80 dB", "digits": 0}, {"key": "v90", "label": "≥90 dB", "digits": 0},
                 {"key": "pmin", "label": "P min", "unit": "W", "si": True, "group": "Power"}, {"key": "pmax", "label": "P max", "unit": "W", "si": True, "group": "Power"},
                 {"key": "imin", "label": "I min", "unit": "A", "si": True, "group": "I<sub>DD</sub>"}, {"key": "imax", "label": "I max", "unit": "A", "si": True, "group": "I<sub>DD</sub>"},
                 {"key": "amin", "label": "min (dB)", "digits": 4, "group": "A<sub>0</sub>"}, {"key": "amax", "label": "max (dB)", "digits": 4, "group": "A<sub>0</sub>"},
                 {"key": "bmin", "label": "min", "unit": "Hz", "si": True, "group": "CL −3 dB BW"}, {"key": "bmax", "label": "max", "unit": "Hz", "si": True, "group": "CL −3 dB BW"},
                 {"key": "umin", "label": "min", "unit": "Hz", "si": True, "group": "UGB"}, {"key": "umax", "label": "max", "unit": "Hz", "si": True, "group": "UGB"},
                 {"key": "pmn", "label": "min (°)", "digits": 4, "group": "PM"}, {"key": "pmx", "label": "max (°)", "digits": 4, "group": "PM"},
                 {"key": "vmn", "label": "min (V)", "digits": 3, "group": "V<sub>DD</sub>"}, {"key": "vmx", "label": "max (V)", "digits": 3, "group": "V<sub>DD</sub>"},
                 {"key": "fomp", "label": "FoM<sub>P</sub> max", "digits": 4},
                 {"key": "mf", "label": "Max-FoM design", "md": True, "type": "text", "wrap": True}]
        erows = []
        for t in tops:
            e, mf = t.get("envelopes") or {}, t.get("max_fom_design")
            erows.append([t["title"], t.get("total_evaluated"), t.get("valid_ulp_count"), t.get("valid_60db_count"), t.get("valid_80db_count"), t.get("valid_90db_count"),
                          scale(e.get("power_nw_min"), 1e-9), scale(e.get("power_nw_max"), 1e-9), scale(e.get("idd_na_min"), 1e-9), scale(e.get("idd_na_max"), 1e-9),
                          r5(e.get("a0_db_min")), r5(e.get("a0_db_max")), r5(e.get("cl_bw_hz_min")), r5(e.get("cl_bw_hz_max")), r5(e.get("ugb_hz_min")), r5(e.get("ugb_hz_max")),
                          r5(e.get("pm_deg_min")), r5(e.get("pm_deg_max")), r5(e.get("vdd_min")), r5(e.get("vdd_max")), r5(e.get("fom_p_max")),
                          (f"FoM<sub>P</sub> {num(mf.get('fom_p_mhz_pf_mw'), 0)} · {fp(mf.get('power_nw'))} · A<sub>0</sub> {num(mf.get('a0_db'), 1)} dB · BW {num(mf.get('cl_bw_hz'), 2)} Hz · {num(mf.get('vdd'), 2)} V") if mf else "—"])
        ulp_points(ulp, out)
        knob_dims = [{"key": f"k_{k}", "label": f"knob {k}", "unit": "µm" if k.startswith("l_") else ""} for k in ULP_KNOBS]
        u_dims = [
            {"key": "power", "label": "Quiescent power P", "unit": "W", "si": True, "log": True, "better": "low"},
            {"key": "power_total", "label": "Total power incl. reference", "unit": "W", "si": True, "log": True, "better": "low"},
            {"key": "a0", "label": "Open-loop DC gain A0", "unit": "dB", "better": "high", "digits": 4},
            {"key": "cl_bw", "label": "Closed-loop −3 dB BW", "unit": "Hz", "si": True, "log": True},
            {"key": "ugb", "label": "UGB", "unit": "Hz", "si": True, "log": True, "better": "high"},
            {"key": "pm", "label": "Phase margin", "unit": "°", "better": "high", "digits": 4},
            {"key": "gm", "label": "Gain margin", "unit": "dB", "digits": 3},
            {"key": "idd", "label": "Supply current IDD", "unit": "A", "si": True, "log": True, "better": "low"},
            {"key": "idd_total", "label": "Total current incl. reference", "unit": "A", "si": True, "log": True},
            {"key": "itarget", "label": "Target total current", "unit": "A", "si": True, "log": True},
            {"key": "vdd_v", "label": "Supply voltage", "unit": "V", "digits": 3},
            {"key": "cl", "label": "Load capacitance CL", "unit": "F", "si": True, "log": True},
            {"key": "vos", "label": "Offset Vos", "unit": "V", "si": True},
            {"key": "overshoot", "label": "Step overshoot", "unit": "%"},
            {"key": "fom_s", "label": "FoM_S (MHz·pF/mA)", "unit": "", "log": True, "better": "high", "digits": 4},
            {"key": "fom_p", "label": "FoM_P (MHz·pF/mW)", "unit": "", "log": True, "better": "high", "digits": 4},
        ] + knob_dims + [
            {"key": "arch", "label": "Architecture", "type": "cat", "labels": arch_labels, "order": order, "colors": arch_colors},
            {"key": "set", "label": "Data set", "type": "cat", "order": ["sample", "curve", "frontier"],
             "labels": {"sample": "Exploration sample", "curve": "Power-scaling curve", "frontier": "Frontier design"}},
            {"key": "stype", "label": "Sample type", "type": "cat"},
            {"key": "profile", "label": "Bias profile", "type": "cat"},
            {"key": "sat", "label": "All saturated", "type": "cat", "labels": {"yes": "all saturated", "no": "not all saturated"}},
        ]
        ublocks = [
            {"type": "downloads", "items": [{"label": "Download ULP Frontier JSON", "file": "data/ulp_exploration.json"}]},
            {"type": "section", "cols": 2, "blocks": [
                chart("Open-Loop DC Gain A<sub>0</sub> (dB) vs Quiescent Power P (nW)", g_tr,
                      lay("Quiescent Power P (nW)", "Open-Loop DC Gain A0 (dB)", logx=True, hovermode="closest", legend={"font": {"size": 10}}),
                      height=520, caption="Valid low-speed (<10 kHz CL BW, PM ≥ 45°, step-stable) designs across all 12 topologies (power-scaling curves). Click legend entries to hide / isolate topologies."),
                chart("Closed-Loop −3 dB Bandwidth f<sub>−3dB,CL</sub> (Hz) vs Quiescent Power P (nW)", b_tr,
                      lay("Quiescent Power P (nW)", "Closed-Loop -3 dB Bandwidth (Hz)", logx=True, logy=True, hovermode="closest", legend={"font": {"size": 10}}),
                      height=520, caption="Power scaling law from sub-nW / pW up to hundreds of nW (<10 kHz closed-loop bandwidth ceiling)")]},
            {"type": "table", "title": "ULP frontier by topology", "columns": tcols, "rows": rows, "search": False, "csv": False},
            {"type": "table", "title": "ULP envelopes and counts by topology (all numeric)", "columns": ecols, "rows": erows, "search": False,
             "caption": "Envelope (min/max over valid designs) of every metric recorded in the ULP exploration, the ≥ 90 dB count and the maximum-FoM<sub>P</sub> design per topology."},
            {"type": "explorer", "title": "ULP exploration samples (explorer)", "src": "hub/data/ulp_points.json", "dims": u_dims,
             "x": "power", "y": "a0", "color": "arch", "symbol": "set", "highlight": "frontier", "highlight_label": "Frontier designs",
             "label_key": "label", "hover": ["cl_bw", "pm", "vdd_v", "idd", "fom_p", "stype", "profile"],
             "filters": ["set", "arch", "stype", "profile", "sat", "a0", "cl_bw", "vdd_v"],
             "presets": [{"label": "A<sub>0</sub> vs power", "x": "power", "y": "a0"}, {"label": "CL BW vs power", "x": "power", "y": "cl_bw"},
                         {"label": "PM vs power", "x": "power", "y": "pm"}, {"label": "FoM<sub>P</sub> vs power", "x": "power", "y": "fom_p"},
                         {"label": "A<sub>0</sub> vs L<sub>in</sub>", "x": "k_l_in", "y": "a0", "logx": False},
                         {"label": "A<sub>0</sub> vs gm/Id<sub>in</sub>", "x": "k_gmid_in", "y": "a0", "logx": False},
                         {"label": "Power vs V<sub>DD</sub>", "x": "vdd_v", "y": "power", "logx": False, "logy": True},
                         {"label": "Per architecture", "x": "power", "y": "a0", "facet": "arch"}],
             "caption": f"All {len(ulp.get('scatter_points') or [])} recorded exploration samples (Halton multi-parameter + scaling grid, with the generator knobs), the power-scaling curve points and the per-topology frontier designs (ringed). "
                        "These sample-level data were in the ULP JSON but not plotted on the original site."},
        ]
        blocks.append({"type": "section", "title": f"Ultra-Low-Power (nW / pW), Low-Speed (<10 kHz CL BW), High-Gain Frontier ({ulp.get('total_jobs', 0):,} Farm Runs)",
                       "intro": "5-decade sub-threshold scaling (5 pA to 200 nA across 0.9 V–3.3 V and L = 2.5–20 μm) + Halton multi-parameter sweeps pushing each topology to its minimum power (nW / pW) "
                                f"and maximum DC gain A<sub>0</sub> under closed-loop bandwidth f<sub>−3dB,CL</sub> < {jsn(crit.get('cl_bw_hz_max', 10000) / 1000)} kHz and PM ≥ {jsn(crit.get('pm_deg_min', 45))}°. "
                                f"Validity: A<sub>0</sub> ≥ {jsn(crit.get('a0_db_min', 35))} dB, |V<sub>os</sub>| ≤ {jsn(crit.get('vos_mv_max', 35))} mV, step stable · {ulp.get('total_valid_ulp', 0):,} valid designs. "
                                "The original site's architecture filter maps to the plot legends (click to hide / double-click to isolate) and the explorer chips.",
                       "blocks": ublocks})

    # ---------------- parameter boundaries
    if bnd and bnd.get("topologies"):
        blocks.append(boundary_section(bnd, arch_labels))
    return {"intro": intro, "blocks": blocks}


ULP_KNOBS = ["gmid_in", "gmid_load", "gmid_tail", "gmid_cascode", "gmid_stage2", "l_in", "l_load", "l_tail", "l_casc", "l_out", "cc_scale", "rz_scale"]


def ulp_points(ulp, out):
    keys = ["power", "power_total", "a0", "cl_bw", "ugb", "pm", "gm", "idd", "idd_total", "itarget", "vdd_v", "cl", "vos", "overshoot",
            "fom_s", "fom_p"] + [f"k_{k}" for k in ULP_KNOBS] + ["arch", "set", "stype", "profile", "sat", "frontier", "label"]
    C = {k: [] for k in keys}

    def add(p, set_, label, frontier=False):
        kn = p.get("knobs") or {}
        row = {"power": scale(p.get("power_nw"), 1e-9), "power_total": scale(p.get("power_total_nw"), 1e-9), "a0": r5(p.get("a0_db")),
               "cl_bw": r5(p.get("cl_bw_hz")), "ugb": r5(p.get("ugb_hz")), "pm": r5(p.get("pm_deg")), "gm": r5(p.get("gm_db")),
               "idd": scale(p.get("idd_na"), 1e-9), "idd_total": scale(p.get("idd_total_na"), 1e-9), "itarget": scale(p.get("target_itotal_na"), 1e-9),
               "vdd_v": r5(p.get("vdd")), "cl": scale(p.get("cl_pf"), 1e-12), "vos": scale(p.get("vos_mv"), 1e-3), "overshoot": r5(p.get("overshoot_pct")),
               "fom_s": r5(p.get("fom_s_mhz_pf_ma")), "fom_p": r5(p.get("fom_p_mhz_pf_mw")),
               "arch": p.get("arch"), "set": set_, "stype": p.get("sample_type"), "profile": p.get("profile"),
               "sat": "yes" if p.get("all_saturated") else "no", "frontier": frontier, "label": label}
        for k in ULP_KNOBS:
            row[f"k_{k}"] = r5(kn.get(k))
        for k in keys:
            C[k].append(row.get(k))
    for p in ulp.get("scatter_points") or []:
        add(p, "sample", f"{p.get('arch')} · {p.get('sample_type')} / {p.get('profile')}")
    for t in ulp["topologies"].values():
        for p in t.get("power_scaling_curve") or []:
            add(p, "curve", f"{t['arch']} · power-scaling curve")
        for k, lab in (("min_power_design", "minimum power (A0 ≥ 35 dB)"), ("min_power_60db_design", "minimum power with A0 ≥ 60 dB"),
                       ("min_power_80db_design", "minimum power with A0 ≥ 80 dB"), ("max_gain_design", "maximum DC gain"), ("max_fom_design", "maximum FoM_P")):
            if t.get(k):
                add(t[k], "frontier", f"{t['arch']} · {lab}", True)
    dump(out / "data" / "ulp_points.json", {"columns": C})


def boundary_section(bnd, short=None):
    short = short or {}
    tops = bnd["topologies"]
    vc, cc = bnd.get("validity_criteria") or {}, bnd.get("core_criteria") or {}
    ocols = [{"key": "t", "label": "Topology", "md": True, "type": "text", "wrap": True}, {"key": "io", "label": "Input / Stages", "type": "text", "wrap": True},
             {"key": "fr", "label": "Feasible Rate", "type": "text"}, {"key": "cr", "label": "Strict Core<br>Rate", "md": True, "type": "text"},
             {"key": "vddr", "label": "Valid V<sub>DD</sub> Range (Core)", "md": True, "type": "text"},
             {"key": "vcm", "label": "Valid V<sub>CM</sub>/V<sub>DD</sub> ICMR (Core)", "md": True, "type": "text"},
             {"key": "gm", "label": "Valid g<sub>m</sub>/I<sub>D,in</sub> (V⁻¹)", "md": True, "type": "text"},
             {"key": "li", "label": "Valid L<sub>in</sub> (μm)", "md": True, "type": "text"},
             {"key": "idd", "label": "Achieved I<sub>DD</sub><br>Range (µA)", "type": "text"}, {"key": "a0", "label": "Achieved A<sub>0</sub><br>Range (dB)", "type": "text"}]
    orows = []
    for t in tops.values():
        p, env = t.get("parameters") or {}, t.get("achieved_envelopes") or {}
        g = lambda k, f: (p.get(k) or {}).get(f)  # noqa: E731
        orows.append({
            "t": f"**{t['title']}**<br><small>`{t['arch']}`</small>", "io": f"{t.get('input_type')} · {t.get('stage_count')}-st",
            "fr": {"v": f"{num(t.get('valid_rate_pct'), 1)}% ({t.get('valid_count')}/{t.get('total_evaluated')})", "s": "good" if (t.get("valid_rate_pct") or 0) >= 75 else "warn"},
            "cr": f"**{num(t.get('core_rate_pct'), 1)}%**",
            "vddr": f"{fmt_range(g('vdd_v', 'valid_min'), g('vdd_v', 'valid_max'), 2, 'V')}<br><small>Core: {fmt_range(g('vdd_v', 'core_min'), g('vdd_v', 'core_max'), 2, 'V')}</small>",
            "vcm": f"{fmt_range(g('vcm_ratio', 'valid_min'), g('vcm_ratio', 'valid_max'), 2)}<br><small>Core: {fmt_range(g('vcm_ratio', 'core_min'), g('vcm_ratio', 'core_max'), 2)}</small>",
            "gm": f"{fmt_range(g('gmid_in', 'valid_min'), g('gmid_in', 'valid_max'), 1)}<br><small>1D ray: {fmt_range(g('gmid_in', 'ray_valid_min'), g('gmid_in', 'ray_valid_max'), 1)}</small>",
            "li": f"{fmt_range(g('l_in', 'valid_min'), g('l_in', 'valid_max'), 2)}<br><small>1D ray: {fmt_range(g('l_in', 'ray_valid_min'), g('l_in', 'ray_valid_max'), 2)}</small>",
            "idd": fmt_range((env.get("idd_ua") or {}).get("min"), (env.get("idd_ua") or {}).get("max"), 2),
            "a0": fmt_range((env.get("a0_db") or {}).get("min"), (env.get("a0_db") or {}).get("max"), 1),
            "_href": f"#/opa?page=explore&t.topo={t['arch']}"})
    pcols = [{"key": "p", "label": "Parameter", "md": True, "type": "text", "wrap": True}, {"key": "d", "label": "Description", "type": "text", "wrap": True},
             {"key": "ex", "label": "Explored Range", "type": "text"}, {"key": "ray", "label": "1-D Orthogonal Ray Valid", "md": True, "type": "text"},
             {"key": "nd", "label": "N-D Feasible Boundary", "md": True, "type": "text"}, {"key": "core", "label": "Strict Saturation Core", "type": "text"},
             {"key": "v18", "label": "1.8 V Valid Range", "type": "text"}, {"key": "v33", "label": "3.3 V Valid Range", "type": "text"},
             {"key": "cov", "label": "Coverage", "type": "text"}, {"key": "p595", "label": "Valid P5–P95", "type": "text"},
             {"key": "c18", "label": "1.8 V Core", "type": "text"}, {"key": "c33", "label": "3.3 V Core", "type": "text"},
             {"key": "r18", "label": "1.8 V 1-D Ray", "type": "text"}, {"key": "r33", "label": "3.3 V 1-D Ray", "type": "text"}]
    ecols = [{"key": "m", "label": "Metric", "type": "text"}] + [{"key": k, "label": k, "digits": 4} for k in ("min", "p5", "median", "p95", "max")]
    ENV_LABEL = {"idd_ua": "I<sub>DD</sub> (µA)", "a0_db": "A<sub>0</sub> (dB)", "ugb_mhz": "UGB (MHz)", "pm_deg": "PM (°)",
                 "vos_mv": "|V<sub>os</sub>| (mV)", "vdd_v": "V<sub>DD</sub> (V)", "vcm_ratio": "V<sub>CM</sub>/V<sub>DD</sub>", "cl_pf": "C<sub>L</sub> (pF)"}
    ecols[0]["md"] = True
    atabs = []
    keys = list(tops)
    for an in keys:
        t = tops[an]
        order = t.get("parameter_order") or list(t.get("parameters") or {})
        prow, rtabs = [], []
        for k in order:
            p = (t.get("parameters") or {}).get(k)
            if not p:
                continue
            d = 0 if p.get("scale") == "int" else 2
            u = unit_label(p.get("unit") or "")
            bv = p.get("by_vdd") or {}
            v18, v33 = bv.get("1v8") or {}, bv.get("3v3") or {}
            prow.append({
                "p": f"**{p.get('label')}**<br><small>`{p.get('name')}` ({u})</small>", "d": p.get("description"),
                "ex": fmt_range(p.get("sweep_min"), p.get("sweep_max"), d, u), "ray": f"**{fmt_range(p.get('ray_valid_min'), p.get('ray_valid_max'), d, u)}**",
                "nd": f"**{fmt_range(p.get('valid_min'), p.get('valid_max'), d, u)}**", "core": fmt_range(p.get("core_min"), p.get("core_max"), d, u),
                "v18": fmt_range(v18.get("valid_min"), v18.get("valid_max"), d), "v33": fmt_range(v33.get("valid_min"), v33.get("valid_max"), d),
                "cov": {"v": f"{num(p.get('valid_span_pct'), 0)}%", "s": "good" if (p.get("valid_span_pct") or 0) >= 70 else "warn"},
                "p595": fmt_range(p.get("valid_p5"), p.get("valid_p95"), d), "c18": fmt_range(v18.get("core_min"), v18.get("core_max"), d),
                "c33": fmt_range(v33.get("core_min"), v33.get("core_max"), d), "r18": fmt_range(v18.get("ray_valid_min"), v18.get("ray_valid_max"), d),
                "r33": fmt_range(v33.get("ray_valid_min"), v33.get("ray_valid_max"), d)})
            rtabs.append({"label": p.get("label") or p.get("name"), "key": p.get("name"), "blocks": [ray_chart(p, u)]})
        env = t.get("achieved_envelopes") or {}
        erows = [[ENV_LABEL.get(m, m)] + [r5(env[m].get(q)) for q in ("min", "p5", "median", "p95", "max")] for m in env]
        atabs.append({"label": short.get(an, t["title"]), "key": an, "blocks": [
            {"type": "table", "title": f"Per-Parameter Valid Design Boundary: {t['title']} (`{an}`)", "columns": pcols, "rows": prow, "search": False,
             "caption": f"{t.get('summary', '')} — {t.get('valid_count')}/{t.get('total_evaluated')} feasible ({num(t.get('valid_rate_pct'), 1)}%), "
                        f"{t.get('core_count')} strict core ({num(t.get('core_rate_pct'), 1)}%). Pick another topology with the selector above."},
            {"type": "table", "title": "Achieved performance envelope over feasible points", "columns": ecols, "rows": erows, "search": False, "csv": False},
            {"type": "tabs", "style": "select", "label": "1-D parameter ray", "id": f"ray_{an}", "title": "1-D orthogonal parameter rays (A<sub>0</sub> and PM vs parameter, 1.8 V and 3.3 V centres)",
             "tabs": rtabs,
             "caption": "Filled circles: feasible and in the strict saturation core; open circles: feasible only; crosses: infeasible. Shaded band: N-D feasible boundary. "
                        "These ray samples are in the boundary JSON but were not plotted on the original site."}]})
    default = keys.index("nmos_miller") if "nmos_miller" in keys else 0
    crit = (f"Feasible boundary requires PM ≥ {jsn(vc.get('pm_deg_min', 45))}°, closed-loop step stability, A<sub>0</sub> ≥ {jsn(vc.get('a0_db_min', 25))} dB, "
            f"|V<sub>OS</sub>| ≤ {jsn(vc.get('vos_mv_max', 35))} mV" + (f" and UGB ≥ {si(vc['ugb_hz_min'], 'Hz')}" if vc.get("ugb_hz_min") else "")
            + f"; strict core boundary additionally requires PM ≥ {jsn(cc.get('pm_deg_min', 50))}°, A<sub>0</sub> ≥ {jsn(cc.get('a0_db_min', 35))} dB, "
              f"|V<sub>OS</sub>| ≤ {jsn(cc.get('vos_mv_max', 15))} mV, and all transistors in saturation.")
    return {"type": "section", "title": "Valid Design Boundary by Topology (Parameterized Device & Circuit Generator Sweep)",
            "intro": "Systematic 1-D orthogonal parameter rays + multi-dimensional Halton sweeps across all 12 topologies on the compute farm. " + crit
                     + f" {bnd.get('total_jobs', 0):,} sweep jobs, {bnd.get('total_valid', 0):,} feasible, {bnd.get('total_core', 0):,} strict core (load tag `{bnd.get('load_tag', '2p')}`).",
            "blocks": [{"type": "downloads", "items": [{"label": "Download Boundary JSON", "file": "data/param_boundaries.json"}]},
                       {"type": "table", "title": "Boundary overview", "columns": ocols, "rows": orows, "search": False, "csv": False,
                        "caption": "Click a row to show that topology's per-parameter boundary below (the original *Inspect / Parameters →* buttons)."},
                       {"type": "tabs", "style": "select", "label": "Topology", "id": "topo", "default": default, "tabs": atabs}]}


def ray_chart(p, u):
    tr = []
    for vt, col, vl, vnum in (("1v8", PRE_C, "1.8 V", 1.8), ("3v3", ORANGE, "3.3 V", 3.3)):
        ray = ((p.get("by_vdd") or {}).get(vt) or {}).get("ray") or []
        if not ray:
            continue
        sym = ["circle" if r.get("valid") and r.get("core") else "circle-open" if r.get("valid") else "x" for r in ray]
        cd = [[r5(r.get("ugb_mhz")), r5(r.get("idd_ua")), r5(r.get("vos_mv")), "feasible" if r.get("valid") else "infeasible",
               "core" if r.get("core") else "not core", "sat" if r.get("all_saturated") else "not all sat"] for r in ray]
        ht = "%{x}: %{y}<br>UGB %{customdata[0]} MHz · IDD %{customdata[1]} µA · Vos %{customdata[2]} mV<br>%{customdata[3]}, %{customdata[4]}, %{customdata[5]}<extra>"
        x = rl([r.get("val") for r in ray])
        tr.append({"type": "scatter", "mode": "lines+markers", "name": f"A0 @ {vl}", "x": x, "y": rl([r.get("a0_db") for r in ray]),
                   "line": {"color": col, "width": 2}, "marker": {"symbol": sym, "size": 9, "color": col}, "customdata": cd,
                   "hovertemplate": ht + f"A0 {vl}</extra>", "meta": {"vdd": vnum}})
        tr.append({"type": "scatter", "mode": "lines+markers", "name": f"PM @ {vl}", "x": x, "y": rl([r.get("pm_deg") for r in ray]), "yaxis": "y2",
                   "line": {"color": col, "width": 1.5, "dash": "dash"}, "marker": {"symbol": sym, "size": 7, "color": col}, "customdata": cd,
                   "hovertemplate": ht + f"PM {vl}</extra>", "meta": {"vdd": vnum}})
    shapes = []
    if p.get("valid_min") is not None and p.get("valid_max") is not None:
        shapes.append({"type": "rect", "xref": "x", "yref": "paper", "x0": r5(p["valid_min"]), "x1": r5(p["valid_max"]), "y0": 0, "y1": 1,
                       "fillcolor": "rgba(30,133,101,0.10)", "line": {"width": 0}, "layer": "below"})
    L = lay(f"{p.get('label')} ({u})", "DC gain A0 (dB)", logx=p.get("scale") == "log", hovermode="closest",
            yaxis2={"title": {"text": "Phase margin (°)"}, "overlaying": "y", "side": "right", "showgrid": False}, shapes=shapes,
            margin={"l": 60, "r": 60, "t": 30, "b": 50})
    return chart(f"{p.get('label')} — {p.get('description', '')}", tr, L, height=420)


DB_COLS = [  # key, label, group, spec
    ("load", "Load", "Design", {"type": "text"}), ("design", "Card ID", "Design", {"type": "design"}),
    ("arch", "Arch", "Design", {"type": "text"}), ("vdd", "V<sub>DD</sub> (V)", "Design", {"digits": 2}),
    ("cls", "I<sub>DD</sub> Class", "Design", {"type": "text"}), ("regime", "Regime", "Design", {"type": "text"}),
    ("gmid", "gm/Id (V⁻¹)", "Design", {"digits": 3}), ("stage", "Stage", "Design", {"type": "text"}),
    ("idd", "I<sub>DD</sub>", "DC & AC", {"unit": "A", "si": True}), ("power", "Power", "DC & AC", {"unit": "W", "si": True}),
    ("a0", "Gain (dB)", "DC & AC", {"digits": 5, "better": "high"}), ("ugb", "UGB", "DC & AC", {"unit": "Hz", "si": True, "better": "high"}),
    ("cl_bw", "CL −3 dB BW", "DC & AC", {"unit": "Hz", "si": True}), ("pm", "PM (°)", "DC & AC", {"digits": 4, "better": "high"}),
    ("gm", "GM (dB)", "DC & AC", {"digits": 4}),
    ("status", "Status", "Robustness", {"type": "text"}), ("pm_min", "PVT Min PM (°)", "Robustness", {"digits": 4, "better": "high"}),
    ("a0_min", "PVT Min Gain (dB)", "Robustness", {"digits": 5}), ("mc_yield", "MC Yield (%)", "Robustness", {"digits": 4, "better": "high"}),
    ("vos_sigma", "V<sub>os</sub> σ (mV)", "Robustness", {"digits": 4, "better": "low"}), ("pm_p5", "MC P5 PM (°)", "Robustness", {"digits": 4}),
    ("vos", "V<sub>os</sub> nom (mV)", "Robustness", {"digits": 3}),
    ("vn_1k", "Noise @1k (nV/√Hz)", "Noise", {"digits": 5, "better": "low"}), ("vn_rms", "Integrated (μV<sub>rms</sub>)", "Noise", {"digits": 5}),
    ("cmrr", "CMRR (dB)", "Rejection", {"digits": 5}), ("psrr_p", "PSRR+ (dB)", "Rejection", {"digits": 5}), ("psrr_n", "PSRR− (dB)", "Rejection", {"digits": 5}),
    ("sr_pos", "SR+ (V/μs)", "Transient", {"digits": 4}), ("sr_neg", "SR− (V/μs)", "Transient", {"digits": 4}),
    ("ts", "1% Settling (μs)", "Transient", {"digits": 5}), ("overshoot", "Overshoot (%)", "Transient", {"digits": 3}),
    ("icmr", "ICMR span (V)", "Range", {"digits": 3}), ("swing", "Swing (V)", "Range", {"digits": 4}),
    ("thd", "THD (%)", "Linearity", {"digits": 3}), ("hd2", "HD2 (dBc)", "Linearity", {"digits": 4}), ("hd3", "HD3 (dBc)", "Linearity", {"digits": 4}),
    ("im3", "IM3 (dBc)", "Linearity", {"digits": 4}), ("zin", "Z<sub>in</sub> @1k (MΩ)", "Linearity", {"digits": 5}),
    ("pm_pass", "PM pass", "Checks", {"type": "status"}),
    ("sat", "All sat.", "Checks", {"type": "status", "title": "All devices saturated at the nominal operating point (pre-PEX only: the extracted netlist has no device operating-point map)"}),
    ("area", "Area (μm²)", "Physical", {"digits": 6, "better": "low"}), ("w", "W (μm)", "Physical", {"digits": 4}), ("h", "H (μm)", "Physical", {"digits": 4}),
    ("wl", "Wirelength (μm)", "Physical", {"digits": 5}), ("vias", "Vias", "Physical", {"digits": 4}), ("parc", "Parasitic C", "Physical", {"digits": 4}),
    ("phys", "Physical", "Physical", {"type": "text"}),
]


def db_data(loads, summ, out):
    files = {}
    allrows = []
    for ld in loads:
        lt = ld["id"]
        rows = []
        for c in summ[lt]["cards"]:
            did = f"{lt}-{c['card_id']}"
            p = c.get("physical") or {}
            pl, pk = phys_badge(p)
            for st, key in (("pre", "pre"), ("full", "post")):
                s = c.get(key)
                if not s:
                    continue
                sl, sk = status_tuple(s)
                v = {"load": ld["label"], "design": {"v": did, "t": c["card_id"]}, "arch": c.get("arch_short"), "vdd": c.get("vdd"),
                     "cls": c.get("iclass_label"), "regime": c.get("inv_tag"), "gmid": c.get("gmid_target"), "stage": st,
                     "idd": scale(s.get("idd_ua"), 1e-6), "power": scale(s.get("power_uw"), 1e-6), "a0": r5(s.get("a0_db")), "ugb": r5(s.get("ugb_hz")),
                     "cl_bw": r5(s.get("cl_bw_hz")), "pm": r5(s.get("pm_deg")), "gm": r5(s.get("gm_db")), "status": {"v": sl, "s": sk},
                     "pm_min": r5(s.get("pm_min_deg")), "a0_min": r5(s.get("a0_min_db")), "mc_yield": r5(s.get("mc_yield_pct")),
                     "vos_sigma": r5(s.get("vos_sigma_mv")), "pm_p5": r5(s.get("pm_p5_deg")), "vos": r5(s.get("vos_mv")),
                     "vn_1k": r5(s.get("vn_1khz_nv_rthz")), "vn_rms": r5(s.get("vn_rms_uv")), "cmrr": r5(s.get("cmrr_dc_db")),
                     "psrr_p": r5(s.get("psrr_p_dc_db")), "psrr_n": r5(s.get("psrr_n_dc_db")), "sr_pos": r5(s.get("sr_pos_vus")),
                     "sr_neg": r5(s.get("sr_neg_vus")), "ts": r5(s.get("ts_1pct_us")), "overshoot": r5(s.get("overshoot_pct")),
                     "icmr": r5(s.get("icmr_span_v")), "swing": r5(s.get("vout_swing_v")), "thd": r5(s.get("thd_pct")), "hd2": r5(s.get("hd2_dbc")),
                     "hd3": r5(s.get("hd3_dbc")), "im3": r5(s.get("im3_dbc")), "zin": r5(s.get("zin_1khz_mohm")), "pm_pass": s.get("pm_pass"),
                     "sat": s.get("all_saturated") if st == "pre" else None, "area": r5(p.get("area_um2")), "w": r5(p.get("width_um")), "h": r5(p.get("height_um")),
                     "wl": r5(p.get("wirelength_um")), "vias": p.get("vias"), "parc": p.get("parasitic_c_count"), "phys": {"v": pl, "s": pk}}
                row = [v.get(k) for k, _l, _g, _s in DB_COLS]
                rows.append(row)
        dump(out / "data" / f"db_{lt}.json", {"rows": rows})
        files[lt] = f"hub/data/db_{lt}.json"
        allrows += rows
    dump(out / "data" / "db_all.json", {"rows": allrows})
    files["all"] = "hub/data/db_all.json"
    return files


def db_page(loads, summ, files):
    cols = [dict({"key": k, "label": l, "group": g}, **s) for k, l, g, s in DB_COLS]
    total = summ[loads[0]["id"]]["meta"]["total_cards"]
    n_ulp = sum(1 for c in summ[loads[0]["id"]]["cards"] if c.get("iclass_tag") == "ulp_lt0p1uw")
    tabs = [{"label": f"C<sub>L</sub> = {ld['label']}", "key": ld["id"], "blocks": [{"type": "table", "src": files[ld["id"]], "columns": cols, "stage_column": "stage", "stage_group": "design",
             "sort": {"key": "ugb", "dir": "desc"}, "max_height": 760, "page_size": 400, "csv_name": f"gf180-opamp-{ld['id']}",
             "title": f"Specification database — C<sub>L</sub> = {ld['label']}"}]} for ld in loads]
    tabs.append({"label": "Both loads", "key": "all", "blocks": [{"type": "table", "src": files["all"], "columns": cols, "stage_column": "stage", "stage_group": "design",
                 "sort": {"key": "ugb", "dir": "desc"}, "max_height": 760, "page_size": 400, "csv_name": "gf180-opamp-all",
                 "title": "Specification database — both loads"}]})
    intro = ("**COMPLETE ENGINEERING DATABASE**\n\n"
             f"## Full {total}-card specification database\n\n"
             f"Sortable master table across all {total} deliverable cards (including the {n_ulp} Low Power <0.1 μW ULP high-gain designs) for the active load capacitance "
             "(tabs) and simulation level (the **Simulation** stage selector: Pre-PEX or Full post-PEX). Click any column header to sort or any Card ID to open the card. "
             "The table carries every scalar of the coverage summaries (a superset of the original database and comparison-table columns), follows the global V<sub>DD</sub> filter and exports CSV.")
    return {"intro": intro, "blocks": [{"type": "tabs", "id": "db", "tabs": tabs}]}


def method_page(meta, lut):
    pipeline = (
        "1. **Compute-Farm LUT Characterization:** 1,008 ngspice-46 sweeps across `nfet_03v3` and `pfet_03v3` (18 channel lengths 0.28–20.0 μm, V<sub>GS</sub>/V<sub>DS</sub>/V<sub>SB</sub> grids) extracting g<sub>m</sub>/I<sub>D</sub>, I<sub>D</sub>/W, f<sub>T</sub>, g<sub>m</sub>/g<sub>ds</sub>, and V<sub>DSAT</sub>.\n"
        "2. **Fully Parameterized gm/Id Topology & Device Generator:** 12 architectures parameterized across continuous supply V<sub>DD</sub>, unclamped quiescent current I<sub>DD</sub>, common-mode ratio V<sub>CM</sub>/V<sub>DD</sub>, load capacitance C<sub>L</sub>, per-stage g<sub>m</sub>/I<sub>D</sub> targets, continuous gate lengths (L<sub>in</sub>, L<sub>load</sub>, L<sub>tail</sub>, L<sub>casc</sub>, L<sub>out</sub>), unit finger width W<sub>unit</sub>, branch mirror ratios (m<sub>tail</sub>, m<sub>st2</sub>, m<sub>fold</sub>, m<sub>out_br</sub>), and passive compensation scales (c<sub>c,scale</sub>, r<sub>z,scale</sub>).\n"
        "3. **Multi-Crossing & Doublet-Aware Stability Verification:** Open-loop AC analysis checks every 0 dB crossing up to 5×UGB alongside closed-loop unity-gain step response (overshoot < 55%, monotonic settling) so pole-zero doublets cannot masquerade as stable.\n"
        "4. **Comprehensive Nominal Testbench Suite:** Evaluates DC operating point, Bode gain/phase, CMRR/PSRR+/PSRR− vs frequency, input-referred noise (1 Hz–1 GHz), rising/falling slew rate, DC ICMR & output swing, coherent-FFT HD2/HD3/THD & two-tone IM3, and closed-loop |Z<sub>in</sub>(f)| at 1× and 6×.\n"
        "5. **17-Corner PVT & 50-Run Mismatch Monte Carlo:** Full 17-point PVT matrix (`tt`, `ff`, `ss`, `sf`, `fs` × −40/27/125 °C, plus `tt` 27 °C at ±10% V<sub>DD</sub>) plus 50-run Monte Carlo with per-finger uncorrelated mismatch expansion (`m=M → M × m=1`).\n"
        "6. **Experimental gLayout (PR #128) + KLayout DRC/LVS:** Generates common-centroid diffusion-shared MOSFET rows with well-tie taprings, custom DRC/LVS-clean `ppolyf_u_1k` serpentine poly resistors and Option-B `cap_mim_2f0fF` MIM capacitors, simulated-annealing floorplanning, and two-layer rip-up-and-reroute A* routing. Verified with `gf180mcu.drc` (0 effective violations) and `gf180mcu.lvs` (`Netlists match`).\n"
        "7. **Magic Parasitic Extraction & Post-PEX Farm Closure:** Extracts distributed coupling and ground capacitances via Magic `ext2spice`, validates device/port counts, and re-runs the full testbench suite, 17-corner PVT, and 50-run Monte Carlo on the compute farm.")
    portfolio = [  # verbatim from the original methodology table
        ("nmos_5t", "5-T NMOS-Input OTA", "NMOS", 1), ("pmos_5t", "5-T PMOS-Input OTA", "PMOS", 1),
        ("nmos_miller", "2-Stage NMOS Miller Op-Amp (Rz + Cc)", "NMOS", 2), ("pmos_miller", "2-Stage PMOS Miller Op-Amp (Rz + Cc)", "PMOS", 2),
        ("telescopic_nmos", "Telescopic Cascode NMOS OTA", "NMOS", 1), ("telescopic_pmos", "Telescopic Cascode PMOS OTA", "PMOS", 1),
        ("folded_cascode_pmos", "Folded-Cascode PMOS-Input OTA", "PMOS", 1), ("folded_cascode_nmos", "Folded-Cascode NMOS-Input OTA", "NMOS", 1),
        ("symmetrical_ota", "Symmetrical Current-Mirror OTA", "NMOS", 1), ("rail_to_rail", "Complementary NMOS+PMOS Rail-to-Rail 2-Stage", "Rail-to-Rail", 2),
        ("cherry_hooper", "Cherry-Hooper Gm-TIS 2-Stage Op-Amp", "NMOS", 2), ("current_reuse", "Current-Reuse Complementary Input LNA / Op-Amp", "NMOS+PMOS (Current-Reuse)", 2),
    ]
    amap = {a["id"]: a for a in meta.get("architectures") or []}
    desc = {i: a.get("desc", "") for i, a in amap.items()}
    blocks = [{"type": "section", "blocks": [
        {"type": "markdown", "title": "Seven-stage automated pipeline", "text": pipeline},
        {"type": "table", "title": "Architecture portfolio (12 topologies)", "search": False, "csv": False,
         "columns": [{"key": "id", "label": "ID", "type": "text", "md": True}, {"key": "a", "label": "Architecture", "type": "text"},
                     {"key": "i", "label": "Input", "type": "text"}, {"key": "s", "label": "Stages", "digits": 1}],
         "rows": [[f"`{i}`", {"v": a, "title": desc.get(i, "")}, amap.get(i, {}).get("input_type", inp), amap.get(i, {}).get("stages", s)]
                  for i, a, inp, s in portfolio],
         "caption": "Hover an architecture name for the generator's topology description. Input and stage count come from the generator metadata "
                    "(the original static table listed `symmetrical_ota` as 1 stage; the generator and every card record 2 stages). "
                    "Step 5 lists the 17 corners as recorded in the card data (the original text named the skew corners `fnsp`/`snfp`)."}]}]
    if lut and lut.get("curves"):
        charts = []
        for kind, dev in (("nfet", "NMOS"), ("pfet", "PMOS")):
            sub = [c for c in lut["curves"] if c.get("kind") == kind]
            vds = "VDS" if kind == "nfet" else "|VDS|"
            vv = sorted({c.get("vds_v") for c in sub if c.get("vds_v") is not None})
            vtxt = " / ".join(jsn(v) for v in vv) if vv else "0.6"
            charts.append(chart(f"{dev} ({kind}_03v3) gm/Id vs Drain Current Density ID/W",
                                [line(c["jd_ua_per_um"], c["gmid"], f"L = {jsn(c['length_um'])} μm", ARCH_COLORS[i % 12]) for i, c in enumerate(sub)],
                                lay("Drain Current Density ID/W (μA/μm)", "Transconductance Efficiency gm/Id (V⁻¹)", logx=True),
                                caption=f"Farm LUT characterization at {vds} = {vtxt} V, VSB = 0 V (bias from the LUT data; the original page said 0.6 V)", key=kind))
            charts.append(chart(f"{dev} ({kind}_03v3) Transit Frequency fT vs gm/Id",
                                [line(c["gmid"], c["ft_mhz"], f"L = {jsn(c['length_um'])} μm", ARCH_COLORS[i % 12]) for i, c in enumerate(sub)],
                                lay("gm/Id (V⁻¹)", "Transit Frequency fT (MHz)", logy=True),
                                caption=f"Farm LUT characterization at {vds} = {vtxt} V (bias from the LUT data; the original page said 0.6 V)", key=kind + "_ft"))
        # original order: gm/Id NMOS, gm/Id PMOS, fT NMOS, fT PMOS
        order = [charts[0], charts[2], charts[1], charts[3]]
        for c in order:
            c.pop("key", None)
        blocks.append({"type": "section", "title": "GF180MCU-D gm/Id look-up-table characterization", "cols": 2, "blocks": order})
    intro = ("**METHODOLOGY & CHARACTERIZATION**\n\n## Automated gm/Id design & physical verification flow\n\n"
             "End-to-end synthesis from GF180MCU-D transistor characterization to DRC/LVS-clean GDSII and post-PEX farm verification.")
    return {"intro": intro, "blocks": blocks}


# ============================================================================ main
def main():
    docs, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    loads = (jload(docs / "loads.json") or {}).get("loads") or [{"id": "2p", "label": "2 pF", "cl_f": 2e-12}, {"id": "200f", "label": "200 fF", "cl_f": 2e-13}]
    loads = [ld for ld in loads if (docs / "data" / ld["id"] / "summary.json").is_file()]
    summ = {ld["id"]: jload(docs / "data" / ld["id"] / "summary.json") for ld in loads}
    dse = {ld["id"]: jload(docs / "data" / ld["id"] / "dse.json", {}) for ld in loads}
    ulp = jload(docs / "data" / "ulp_exploration.json")
    bnd = jload(docs / "data" / "param_boundaries.json")
    lut = jload(docs / "data" / "lut.json")
    meta = summ[loads[0]["id"]]["meta"]
    archs = meta["architectures"]
    arch_idx = {a["id"]: i for i, a in enumerate(archs)}
    cls_order = [meta["ulp_class"]["tag"]] + [c["tag"] for c in meta["current_classes"]]
    reg_order = [r["tag"] for r in meta["inversion_regimes"]]

    designs = []
    for ld in loads:
        lt = ld["id"]
        other = [x for x in loads if x["id"] != lt]
        cards = sorted(summ[lt]["cards"], key=lambda c: (arch_idx.get(c["arch"], 99), c["vdd"], cls_order.index(c["iclass_tag"]) if c["iclass_tag"] in cls_order else 9,
                                                         reg_order.index(c["inv_tag"]) if c["inv_tag"] in reg_order else 9))
        for c in cards:
            cid = c["card_id"]
            did = f"{lt}-{cid}"
            base = f"designs/{lt}/{cid}"
            card = jload(docs / base / "card.json", {}) or {}
            ph = c.get("physical") or {}
            area = ph.get("area_um2")
            results = {}
            if (s := stage_result(c.get("pre"), area, part_of(card, "pre", "mc"))):
                results["pre"] = s
            if c.get("post") and (s := stage_result(c.get("post"), area, part_of(card, "full", "mc"))):
                s["note"] = POST_NOTE
                results["full"] = s
            files = {k: f"{base}/{v}" for k, v in (
                ("schematic", "schematic.svg"), ("gds", f"{cid}.gds.gz"), ("netlist", "netlist.spice"),
                ("pex_netlist", "pex.spice"), ("lvs_netlist", "lvs_ref.spice"), ("data", "card.json")) if (docs / base / v).is_file()}
            twin = [f"[C<sub>L</sub> = {x['label']}](#/opa/{x['id']}-{cid})" for x in other if any(k["card_id"] == cid for k in summ[x["id"]]["cards"])]
            fails = [(lab, c[st_]) for st_, lab in (("pre", "Pre-PEX"), ("post", "Post-PEX")) if (c.get(st_) or {}).get("pm_pass") is False]
            summary = (f"{num(c['vdd'], 1)} V supply · {c['iclass_label']} envelope · {c['inv_label']} (target gm/Id = {jsn(c['gmid_target'])} V⁻¹) · "
                       f"{card.get('topology_desc') or next((a.get('desc') for a in archs if a['id'] == c['arch']), '')}\n\n"
                       f"Card `{cid}` · C<sub>L</sub> = {ld['label']} · {'Pre-PEX + Post-PEX Extracted Available' if c.get('post') else 'Pre-PEX Farm Verified'}"
                       + (f" · same design at {', '.join(twin)}" if twin else "")
                       + "".join(f"\n\n**{lab}: nominal phase-margin screen FAILED** (PM = {num(x.get('pm_deg'), 2)}° < 45°; {x.get('pvt_pass')}/{x.get('pvt_total')} PVT corners, "
                                 f"MC yield {num(x.get('mc_yield_pct'), 1)}%) — shown as *Screen warn* (red) on the original site." for lab, x in fails))
            params = {"C<sub>L</sub>": ld["label"], "Input gm/Id target": f"{jsn(c['gmid_target'])} V⁻¹",
                      "I<sub>ref</sub>": fmt_idd(card.get("iref_ua")) if card else None,
                      "V<sub>CM</sub>": f"{num(card.get('vcm'), 2)} V" if card.get("vcm") is not None else None,
                      "Current envelope": f"{c['iclass_label']}"}
            for k, v in (card.get("knobs") or {}).items():
                lab, unit, _ = KNOBS.get(k, (k, "", 1))
                params[f"{lab} (knob)"] = si(v, "F") if unit == "F" else fmt_idd(v) if unit == "µA" else f"{jsn(r5(float(v)) if isinstance(v, float) else v)}{(' ' + unit) if unit and unit != '×' else ('×' if unit == '×' else '')}"
            params = {k: v for k, v in params.items() if v not in (None, "")}
            detail = detail_doc(lt, ld, card, base, twin) if card else None
            if detail:
                dump(out / "designs" / f"{did}.json", detail)
            d = {
                "id": did,
                "title": f"{c['arch_title']} · {c['vdd']} V · {c['iclass_label']} · {c['inv_label']} · CL {ld['label']}",
                "summary": summary,
                "vdd": c["vdd"],
                "axes": {"topology": c["arch"], "regime": c["inv_tag"], "class": c["iclass_tag"], "load": lt},
                "tags": [f"{c.get('input_type')} input", f"{c.get('stages')}-stage", f"gm/Id {jsn(c.get('gmid_target'))} V⁻¹", f"CL {ld['label']}"]
                        + [f"✗ nominal PM screen failed ({lab})" for st_, lab in (("pre", "pre-PEX"), ("post", "post-PEX")) if (c.get(st_) or {}).get("pm_pass") is False],
                "physical": {"drc": ph.get("drc_ok"), "lvs": ph.get("lvs_ok"), "pex": ph.get("pex_ok"), "area_um2": area,
                             "width_um": ph.get("width_um"), "height_um": ph.get("height_um")},
                "results": results,
                "params": params,
                "files": files,
                "downloads": [{"label": "Load library manifest (JSON)", "file": f"data/{lt}/library.json"}],
            }
            if detail:
                d["detail"] = f"hub/designs/{did}.json"
            designs.append(d)
    ids = {d["id"] for d in designs}

    # pages + data
    ov, total_sims = overview_page(loads, summ, ulp, ids)
    dump(out / "pages" / "overview.json", ov)
    dse_data(loads, summ, dse, out, ids)
    dump(out / "pages" / "explore.json", explore_page(loads, summ, ulp, bnd, out))
    dump(out / "pages" / "db.json", db_page(loads, summ, db_data(loads, summ, out)))
    dump(out / "pages" / "method.json", method_page(meta, lut))

    updated = max((summ[ld["id"]]["meta"].get("updated") or "") for ld in loads)
    try:
        generated = datetime.fromisoformat(updated).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        generated = updated or None
    regs = {r["tag"]: f"{r['label']} ({jsn(r['gmid_target_in'])} V⁻¹)" for r in meta["inversion_regimes"]}
    comp = {
        "schema": "aicdb-hub/2",
        "id": "opa",
        "name": "Op-amps",
        "title": "GF180 Op-Amp Design Library",
        "summary": ("Twelve op-amp architectures (NMOS/PMOS 5-T, Miller, telescopic & folded cascode, symmetrical, rail-to-rail, Cherry-Hooper, "
                    "current-reuse LNA) × two gm/Id inversion regimes × (ultra-low-power <0.1 µW + six 1.8 V / 3.3 V current classes) = 168 "
                    "deliverable designs per load, for CL = 2 pF and 200 fF. gm/Id sizing, ngspice-46 farm verification (17-corner PVT, 50-run "
                    "mismatch MC), gLayout DRC/LVS-clean layouts and Magic PEX."),
        "technology": "gf180mcuD",
        "generated": generated,
        "stats": [{"label": f"farm evaluations · {loads[0]['label']}" + "".join(f" ({ld['label']}: {summ[ld['id']]['meta'].get('total_farm_sims', 0):,})" for ld in loads[1:]),
                   "value": f"{summ[loads[0]['id']]['meta'].get('total_farm_sims', 0):,}"},
                  {"label": f"DSE candidates · {loads[0]['label']}" + "".join(f" ({ld['label']}: {summ[ld['id']]['meta'].get('dse_points_count', 0):,})" for ld in loads[1:]),
                   "value": f"{summ[loads[0]['id']]['meta'].get('dse_points_count', 0):,}"},
                  {"label": "boundary sweeps", "value": f"{meta.get('bounds_jobs_count', 0):,}"},
                  {"label": "ULP frontier runs", "value": f"{meta.get('ulp_jobs_count', 0):,}"}],
        "metrics": [{k: v for k, v in dict(key=k, label=lab, unit=u, si=s or None, better=b, digits=dg, desc=METRIC_DESC.get(k)).items() if v is not None}
                    for k, lab, u, s, b, _f, _k, dg in METRICS],
        "axes": {
            "topology": {"label": "Architecture", "values": [{"id": a["id"], "label": a["short"]} for a in archs]},
            "regime": {"label": "Inversion regime", "values": [{"id": t, "label": regs[t]} for t in reg_order]},
            "class": {"label": "Current class", "values": [{"id": meta["ulp_class"]["tag"], "label": "<0.1 µW (ULP, <10 kHz)"}]
                      + [{"id": c["tag"], "label": c["label"]} for c in meta["current_classes"]]},
            "load": {"label": "Load CL", "values": [{"id": ld["id"], "label": ld["label"]} for ld in loads]},
        },
        "matrix": {"rows": ["topology", "regime", "load"], "cols": ["class"], "metrics": ["ugb", "a0", "pm"],
                   "presets": [{"label": "ULP view: DC gain / CL BW / power / PM", "metrics": ["a0", "cl_bw", "power", "pm"]},
                               {"label": "Power / DC gain", "metrics": ["power", "a0"]},
                               {"label": "Stability: PM / worst-case PVT PM / MC P5 PM", "metrics": ["pm", "pm_min", "pm_p5"]},
                               {"label": "Noise @ 1 kHz / offset σ", "metrics": ["vn_1k", "vos_sigma"]},
                               {"label": "Rejection: CMRR / PSRR+", "metrics": ["cmrr", "psrr_p"]},
                               {"label": "Linearity: THD / IM3", "metrics": ["thd", "im3"]},
                               {"label": "Speed: slew rate / settling", "metrics": ["sr_pos", "ts"]},
                               {"label": "Monte Carlo: yield / offset σ", "metrics": ["mc_yield", "vos_sigma"]},
                               {"label": "Layout area / power", "metrics": ["area", "power"]}]},
        "card_metrics": ["ugb", "a0", "pm", "pm_min", "idd", "power", "vn_1k", "area", "mc_yield", "cl_bw"],
        "table_metrics": ["idd", "a0", "ugb", "pm", "pm_min", "vn_1k", "vos_sigma", "thd", "area", "power", "mc_yield", "cl_bw"],
        "pages": [{"id": "overview", "title": "Library overview", "src": "hub/pages/overview.json"},
                  {"id": "explore", "title": "Design space", "src": "hub/pages/explore.json"},
                  {"id": "db", "title": "Database", "src": "hub/pages/db.json"},
                  {"id": "method", "title": "Methodology", "src": "hub/pages/method.json"}],
        "designs": designs,
    }
    dump(out / "component.json", comp)


if __name__ == "__main__":
    main()
