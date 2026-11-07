#!/usr/bin/env python3
"""Bootstrap hub adapter for sa-gen-gemini4 (schema aicdb-hub/2).

usage: sa.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus the
generated pages, per-design detail documents and chart/table/explorer data under OUT_DIR
(referenced as "hub/<path>"). It reproduces everything the retired per-repo site showed
(list view, comparison view, design-space explorer, methodology, the four detail tabs); see
adapters/sa.inventory.md for the item-by-item checklist. Starting point for the repo builder:
copy to scripts/export_hub.py in the repo and write to docs/hub/.

Stage mapping: `m` / `results` (schematic netlist) -> pre; `m_pex` / `results_pex` -> partial.
The repo's post-layout netlist (netlist_pex.spice) is the schematic devices plus Magic C-only
node capacitances, scaled (x0.085) and clamped (0.12-0.65 fF) into lumped caps on internal
nets only (no wiring R; inputs, clock and supplies ideal) -> partial coverage, not "full".

Provenance (checked against sa-gen-gemini4/flow): input noise (constant 381.9 uV analytical
fallback), the offset "Monte Carlo" (Pelgrom formula + Python random samples), the global+
mismatch MC (synthetic log-normal samples), the CM trip-point curve (linear formula), and the
whole 11,520-point DSE (analytical scaling of 12 SPICE anchors per group; post-PEX DSE = fixed
factors) are model-based. They are ported, clearly labelled, but never put into `results`.
Post-PEX gm/Id and active-tail current were not re-simulated (copied / zero) and are omitted
from the partial stage.
"""
import json
import math
import sys
from pathlib import Path

DOCS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

IDX = json.loads((DOCS / "data" / "index.json").read_text())
META, CARDS = IDX["meta"], IDX["cards"]
DSE = json.loads((DOCS / "data" / "dse.json").read_text())
CMP = json.loads((DOCS / "data" / "compare.json").read_text())
GMID = json.loads((DOCS / "data" / "gmid.json").read_text())

ARCH_ORDER = ["san", "sap", "dt", "dtx", "db", "dbx", "fia", "miy", "scsa"]   # app.js ARCH_ORDER
MIX_ORDER = ["lv", "hvl", "nat"]
TGT_ORDER = ["sub", "wi", "mi"]
VDDS = META["vdds"]
STG = ("pre", "partial")
STG_LBL = {"pre": "schematic (pre-PEX)", "partial": "partial post-PEX"}
TGT_LBL = {"sub": "0.1–1 µA (sub-Vt)", "wi": "1–10 µA (weak inv.)", "mi": "10–100 µA (mod. inv.)"}
TGT_BAND = {"sub": "0.1–1 µA", "wi": "1–10 µA", "mi": "10–100 µA"}
# old style.css light-theme palette (--c1..--c9, --s1, --s2, --good, --bad, --muted)
C = {"c1": "#2a78d6", "c2": "#eb6834", "c3": "#1baf7a", "c4": "#eda100", "c5": "#e87ba4", "c6": "#008300",
     "c7": "#7d5bd6", "c8": "#a0522d", "c9": "#0891b2", "s1": "#2a78d6", "s2": "#eb6834", "good": "#1a7f37",
     "bad": "#cf222e", "muted": "theme:muted", "ink": "theme:ink"}
ARCH_COL = {"san": C["c1"], "sap": C["c2"], "dt": C["c3"], "db": C["c4"], "fia": C["c5"], "dtx": C["c6"],
            "dbx": C["c7"], "miy": C["c8"], "scsa": C["c9"]}
MIX_SYM = {"lv": "circle", "hvl": "square", "nat": "diamond"}
MIX_DASH = {"lv": "solid", "hvl": "dash", "nat": "dot"}
TGT_SYM = {"sub": "", "wi": "-open", "mi": "-open-dot"}
VIR = ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"]
DM_TICKS = {"tickvals": [-5, -4, -3, -2, -1], "ticktext": ["10µ", "100µ", "1m", "10m", "100m"]}
KNOB = {"vcm": "input common mode V<sub>CM</sub>", "w_ct": "tail capacitor width W<sub>CT</sub>",
        "w_cr": "reservoir capacitor width W<sub>CR</sub>"}
PIN_NOTE = "subcircuit `comp`: INP INN CLK CLKB OUTP OUTN VDD VDDB VSS"
PARTIAL_NOTE = ("Schematic devices + Magic C-only extraction back-annotated as scaled (×0.085) and "
                "clamped (0.12–0.65 fF) lumped caps on internal nets; no wiring R, inputs/clock/supplies ideal. "
                "Input gm/Id and active-tail current were not re-simulated post-PEX and are omitted. Energy per read "
                "comes out lower than pre-PEX in 61 of 96 designs (mostly the clock-driver term).")
MODEL_NOTE = ("model-based — not a SPICE result (see Methodology → Data provenance)")


# ----------------------------------------------------------------------------- helpers
def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def rs(v, n=5):
    """round to n significant digits (recursively)"""
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return v if v == 0 else float(f"{v:.{n - 1}e}")
    if isinstance(v, list):
        return [rs(x, n) for x in v]
    if isinstance(v, dict):
        return {k: rs(x, n) for k, x in v.items()}
    return v


def rd(arr, nd):
    return [None if x is None else round(x, nd) for x in arr]


def write(rel, obj, n=5):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rs(obj, n), separators=(",", ":"), ensure_ascii=False))
    return f"hub/{rel}"


def jsnum(x):
    """JS Number -> string for values produced by toPrecision"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def prec(x, d):
    return jsnum(float(f"{x:.{d}g}"))


PFX = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f"),
       (1e-18, "a")]


def si(v, unit="", d=3):
    """port of app.js si()"""
    if not isnum(v):
        return "—"
    if v == 0:
        return "0 " + unit
    a = abs(v)
    for m, p in PFX:
        if a >= m * 0.9995:
            return f"{prec(v / m, d)} {p}{unit}"
    return f"{prec(v / 1e-18, d)} a{unit}"


def fx(v, d=1):
    """port of app.js num() (toFixed)"""
    return "—" if not isnum(v) else f"{v:.{d}f}"


def ar(v):
    if not isnum(v) or not v:
        return "—"
    return f"{round(v):,}" if v >= 100 else prec(v, 3)


def jround(x):
    return math.floor(x + 0.5)


def shared_range(vals, log, pad=0.04):
    v = [x for x in vals if isnum(x) and (not log or x > 0)]
    if not v:
        return None
    lo, hi = min(v), max(v)
    if log:
        lo, hi = math.log10(lo), math.log10(hi)
    span = (hi - lo) or (1 if log else abs(hi) or 1)
    return [lo - pad * span, hi + pad * span]


def nice_step(raw):
    p = 10 ** math.floor(math.log10(raw))
    m = raw / p
    return (1 if m < 1.5 else 2 if m < 3.5 else 5 if m < 7.5 else 10) * p


def tick(log, r):
    if log:
        return {"dtick": "D2" if r and r[1] - r[0] < 1.6 else 1}
    return {"tick0": 0, "dtick": nice_step((r[1] - r[0]) / 6)} if r else {}


def vir_r(f):
    return VIR[jround((1 - f) * (len(VIR) - 1))]


def vtag(v):
    return "1v8" if abs(v - 1.8) < 0.05 else "3v3"


arch_s = META["arch_short"]
mix_s = META["mix_short"]


def gmid_text(card, g):
    g = g or {}
    if g.get("n") is not None and g.get("p") is not None and card["arch"] == "fia":
        s = f"{fx(g['n'], 1)}/{fx(g['p'], 1)}"
    else:
        s = fx(g.get("n") if g.get("n") is not None else g.get("p"), 1)
    return f"{fx(card['gmid_target'], 1)} → {s}"


def gmid_val(g):
    """simulated gm/Id of the single input pair (None for two-pair FIA designs, reported per pair instead)"""
    g = g or {}
    if g.get("n") is not None and g.get("p") is not None:
        return None
    return g.get("n") if g.get("n") is not None else g.get("p")


TRIP_EDGE = 7.9e-3   # find_trip_after_overdrive bisects 9x over +-8 mV -> 31.25 uV bins; |trip| >= ~8 mV = window edge


def in_dev_text(D):
    """input-device description; FIA has an NMOS and a PMOS input pair (in_model names only the P pair)"""
    P = D["params"]
    if D.get("arch") == "fia":
        pd = next((v for v in D["devices"] if v["name"] == "M1P"), None)
        n = next((v for v in D["devices"] if v["name"] == "M1"), None)
        return (f"{n['model'] if n else 'nfet_03v3'} (N pair) W {fx(P['w_in'], 2)} µm / L {fx(P['l_in'], 2)} µm (nf={P['nf_in']}) + "
                f"{pd['model'] if pd else D['in_model']} (P pair) W {fx(P.get('w_in_p'), 2)} µm / L {fx(pd['l'] if pd else P['l_in'], 2)} µm "
                f"(nf={P.get('nf_in_p')})")
    return f"{D['in_model']} W {fx(P['w_in'], 2)} µm / L {fx(P['l_in'], 2)} µm (nf={P['nf_in']})"


def trip_censored(m):
    """True when a deterministic trip search hit the +-8 mV window edge (value is only a lower bound)"""
    return isnum(m.get("min_detectable_dv_det_v")) and m["min_detectable_dv_det_v"] >= TRIP_EDGE


def ax_log(title, r=None, **kw):
    a = {"type": "log", "title": {"text": title}, "exponentformat": "SI"}
    if r:
        a.update({"range": r, "autorange": False}, **tick(True, r))
    a.update(kw)
    return a


def log_ticks(vals):
    """explicit ticks for log axes: linear steps when the data span < ~1 decade (the hub's default decade ticks would
    leave such an axis without labels), decades otherwise"""
    v = [x for x in vals if isnum(x) and x > 0]
    if not v:
        return {}
    lo, hi = min(v), max(v)
    if hi / lo < 12:
        return {"dtick": f"L{nice_step((hi - lo) / 5 or lo / 5):.3g}", "tick0": 0}
    return {"dtick": 1}


def legend_dummy(name, **kw):
    t = {"type": "scatter", "x": [None], "y": [None], "name": name, "showlegend": True, "hoverinfo": "skip"}
    t.update(kw)
    return t


# ----------------------------------------------------------------------------- metrics (simulated only)
METRICS = [
    # key, label, unit, si, better, digits
    ("delay", "Sensing delay @1 mV", "s", True, "low", 3),
    ("delay10", "Sensing delay @10 mV", "s", True, "low", 3),
    ("delay100", "Sensing delay @100 mV", "s", True, "low", 3),
    ("delay_ul", "Unloaded delay @1 mV", "s", True, "low", 3),
    ("delay_worst", "Worst PVT delay @1 mV", "s", True, "low", 3),
    ("tau", "Regeneration τ", "s", True, "low", 3),
    ("t_int", "Integration phase", "s", True, None, 3),
    ("idd", "I_DD avg @2.5 MHz", "A", True, "low", 3),
    ("idd_tail", "Active tail current", "A", True, None, 3),
    ("e_comp", "Energy / read (core+clk)", "J", True, "low", 3),
    ("e_core", "Core energy / read", "J", True, "low", 3),
    ("e_clk", "Clock-driver energy / read", "J", True, "low", 3),
    ("e_buf", "Buffers + 200 fF loads / read", "J", True, "low", 3),
    ("e_total", "Total energy / read", "J", True, "low", 3),
    ("p_comp", "Power (core+clock)", "W", True, "low", 3),
    ("gmid", "Input gm/Id (simulated)", "1/V", False, None, 4),
    ("gmid_n", "FIA N-pair gm/Id (simulated)", "1/V", False, None, 4),
    ("gmid_p", "FIA P-pair gm/Id (simulated)", "1/V", False, None, 4),
    ("hyst", "Hysteresis |Δtrip|", "V", True, "low", 3),
    ("vos_sys", "Systematic offset (trip midpoint)", "V", True, None, 3),
    ("dv_det", "ΔV_BL,min (deterministic)", "V", True, "low", 3),
    ("kick", "Kickback (diff)", "V", True, "low", 3),
    ("kick_cm", "Kickback (CM)", "V", True, "low", 3),
    ("fmax", "f_max (1 mV)", "Hz", True, "high", 3),
    ("cm_min", "Input CM min", "V", True, "low", 3),
    ("cm_max", "Input CM max", "V", True, "high", 3),
    ("i_rst", "Static current (reset, 27 °C)", "A", True, "low", 3),
    ("leak", "Leakage @125 °C (max)", "A", True, "low", 3),
    ("area", "Layout area", "µm²", False, "low", 4),
]
DESC = {
    "delay": "Clock edge to output crossing VDD/2 through the 3-stage buffer into 200 fF; |ΔV_BL| = 1 mV, nominal V_CM, tt 27 °C, 2.5 MHz.",
    "delay_worst": "Slowest correct 1 mV decision over the 29 PVT points.",
    "tau": "Slope of delay vs −ln|ΔV_BL| fitted over 30 µV…35 mV of the delay sweep.",
    "idd": "Cycle-averaged core supply current E_core·f_read/V_DD at 2.5 MHz (excl. clock drivers and output buffers).",
    "e_comp": "Energy per read of core + clock drivers, excluding output buffers and 200 fF loads.",
    "gmid": "Charge-weighted input-pair gm/Id during integration (∫gm dt / ∫Id dt); pre-PEX only (post-PEX value was copied in the source flow).",
    "gmid_n": "FIA only: charge-weighted gm/Id of the NMOS input pair (pre-PEX).",
    "gmid_p": "FIA only: charge-weighted gm/Id of the PMOS input pair (pre-PEX).",
    "hyst": "|trip after −overdrive − trip after +overdrive| (±0.2·V_DD preconditioning). 9-step bisection over ±8 mV: 31.25 µV resolution; 0 means < 31 µV. Omitted where the search hit the ±8 mV window.",
    "vos_sys": "Mean of the two preconditioned trip points (systematic offset); 15.6 µV resolution (bisection over ±8 mV). Omitted where the search hit the window edge.",
    "dv_det": "Larger |trip point| after opposite-polarity overdrive; 9-step bisection over ±8 mV → 15.6 µV means ≤ 31 µV (search resolution). Omitted where the search hit the ±8 mV window (value would only be a lower bound).",
    "kick": "Peak differential input disturbance through a 10 kΩ source (+25 fF) during a decision.",
    "fmax": "Highest clock of the scan 1…250 MHz with a correct 1 mV decision and t_d < 0.45·T.",
    "cm_min": "Lowest of the 14 V_CM grid points (0.05…0.95·V_DD) where the ±1 mV decision resolves.",
    "cm_max": "Highest of the 14 V_CM grid points (0.05…0.95·V_DD) where the ±1 mV decision resolves.",
    "leak": "Largest reset-phase supply current over the 125 °C PVT points.",
    "area": "Layout bounding-box area (stage-independent).",
}
SRC = {"delay": "delay_1mv", "delay10": "delay_10mv", "delay100": "delay_100mv", "delay_ul": "delay_unloaded",
       "delay_worst": "delay_1mv_worst", "tau": "tau_regen", "t_int": "t_int", "idd": "idd_avg",
       "idd_tail": "idd_active_tail", "e_comp": "e_comp", "e_core": "e_core", "e_clk": "e_clk", "e_buf": "e_buf",
       "e_total": "e_total", "p_comp": "p_comp", "vos_sys": "vos_sys", "dv_det": "min_detectable_dv_det_v",
       "kick": "kick_diff", "kick_cm": "kick_cm", "fmax": "fmax", "cm_min": "cm_min", "cm_max": "cm_max",
       "i_rst": "i_static_reset", "leak": "i_leak_125c_max"}


def stage_result(m, area, partial):
    if not m or m.get("functional") is None:
        return None
    vals = {k: (m.get(f) if isnum(m.get(f)) else None) for k, f in SRC.items()}
    vals["hyst"] = abs(m["hysteresis"]) if isnum(m.get("hysteresis")) else None
    vals["area"] = area
    if partial:   # not re-simulated post-PEX in the source flow (copied gm/Id, zero tail current)
        vals.pop("idd_tail")
    else:
        vals["gmid"] = gmid_val(m.get("gmid_sim"))
        g = m.get("gmid_sim") or {}
        if g.get("n") is not None and g.get("p") is not None:   # FIA: two input pairs, report both (no average)
            vals["gmid_n"], vals["gmid_p"] = g["n"], g["p"]
    if trip_censored(m):   # trip search hit the +-8 mV window: dv_det / hyst / vos_sys are only bounds
        vals["dv_det"] = vals["hyst"] = vals["vos_sys"] = None
    r = {"metrics": {k: v for k, v in vals.items() if v is not None},
         "robust": bool(m.get("functional") and m.get("pvt_robust"))}
    if m.get("pvt_total"):
        r["pvt"] = {"pass": m["pvt_pass"], "total": m["pvt_total"]}
    if partial:
        r["note"] = PARTIAL_NOTE
    return r


# ----------------------------------------------------------------------------- per-design data
ORDER = {(a, mx, v, t): i for i, (a, mx, v, t) in enumerate(
    (a, mx, v, t) for a in ARCH_ORDER for mx in MIX_ORDER for v in VDDS for t in TGT_ORDER)}
CARDS = sorted(CARDS, key=lambda c: ORDER.get((c["arch"], c["mix"], c["vdd"], c["target"]), 1e9))
DATA = {c["key"]: json.loads((DOCS / "designs" / c["key"] / "data.json").read_text()) for c in CARDS}
KEYS = [c["key"] for c in CARDS]
CARD = {c["key"]: c for c in CARDS}


def sv(d, st):
    """stage view of a design data.json: (results, design, tune, card metrics, card gm/Id, card vcm)"""
    c = d["card"]
    if st == "pre":
        return d["results"], d["design"], d["tune"], c["m"], c.get("gmid_sim"), c.get("vcm")
    return (d["results_pex"], d.get("design_pex") or d["design"], d.get("tune_pex") or d["tune"], c["m_pex"],
            c.get("gmid_sim_pex") or c.get("gmid_sim"), c.get("vcm_pex") if c.get("vcm_pex") is not None else c.get("vcm"))


def card_m(key, st):
    c = CARD[key]
    return c["m"] if st == "pre" else c["m_pex"]


def extrap_counts(R):
    """sub-mV delay points / map cells that equal the tau*ln extrapolation of the 1 mV delay (<0.2 % / <0.1 %)"""
    m = R["metrics"]
    tau, d1 = m.get("tau_regen"), m.get("delay_1mv")
    nd = ndt = 0
    if isnum(tau) and isnum(d1):
        for p in R.get("delay_vs_vin") or []:
            if p["vin"] < 1e-3 and isnum(p.get("delay")):
                ndt += 1
                if abs(p["delay"] - (d1 + tau * math.log(1e-3 / p["vin"]))) / p["delay"] < 2e-3:
                    nd += 1
    nc = nct = 0
    for row in R.get("cmdm") or []:
        p1 = next((p for p in row["pts"] if abs(p["dm"] - 1e-3) < 1e-9), None)
        if not p1 or not isnum(p1.get("delay")) or not isnum(tau):
            continue
        for p in row["pts"]:
            if any(abs(p["dm"] - a) < 1e-12 for a in (1e-4, 1e-3, 1e-2, 1e-1)) or not isnum(p.get("delay")):
                continue
            nct += 1
            ex = max(0.2e-9, p1["delay"] + tau * math.log(1e-3 / p["dm"]))
            if abs(p["delay"] - ex) / p["delay"] < 1e-3:
                nc += 1
    return nd, ndt, nc, nct


# ----------------------------------------------------------------------------- chart builders (ports of app.js)
def cmdm_trace(rows, dm, zr, showscale, key=None):
    z = [[round(math.log10(v * 1e9), 3) if isnum(v) and v > 0 else None for v in r["d"]] for r in rows]
    txt = [[f"V<sub>CM</sub> {fx(r['cm'], 3)} V, ΔV {si(dm[j], 'V')}: {si(v, 's') if isnum(v) else 'not resolved'}"
            for j, v in enumerate(r["d"])] for r in rows]
    t = {"type": "heatmap", "x": [round(math.log10(v), 4) for v in dm], "y": [r["cm"] for r in rows], "z": z,
         "text": txt, "hoverinfo": "text", "zmin": zr[0], "zmax": zr[1], "colorscale": "Viridis",
         "reversescale": True, "showscale": bool(showscale), "xgap": 1, "ygap": 1,
         "colorbar": {"title": {"text": "t<sub>d</sub> (ns)", "side": "right"}, "tickvals": [-1, 0, 1, 2, 3],
                      "ticktext": ["0.1", "1", "10", "100", "1000"], "thickness": 12, "len": 0.9}}
    if key:
        t["customdata"] = [[key] * len(dm) for _ in rows]
    return t


def cmdm_layout(vdd, vcm):
    return {"xaxis": dict({"title": {"text": "differential bitline input |ΔV_BL|"}, "range": [-5.3, -0.7],
                           "autorange": False}, **DM_TICKS),
            "yaxis": {"title": {"text": "input CM (V)"}, "range": [0, vdd], "autorange": False, "tick0": 0,
                      "dtick": 0.5 if vdd > 2 else 0.25},
            "margin": {"l": 52, "r": 10, "t": 8, "b": 42}, "showlegend": False,
            "shapes": [{"type": "line", "xref": "x", "yref": "y", "x0": -5.3, "x1": -5.05, "y0": vcm, "y1": vcm,
                        "line": {"color": C["bad"], "width": 3}}]}


def zrange(vals):
    a = [math.log10(v * 1e9) for v in vals if isnum(v) and v > 0]
    return [math.floor(min(a) * 4) / 4, math.ceil(max(a) * 4) / 4] if a else [0, 3]


def colour_strip(zr):
    """one shared colour-scale strip per set (replaces the old gradient legend; panels carry no colourbar)"""
    n = 64
    zs = [round(zr[0] + (zr[1] - zr[0]) * i / (n - 1), 4) for i in range(n)]
    lab = {-1: "100 ps", 0: "1 ns", 1: "10 ns", 2: "100 ns", 3: "1 µs"}
    tv = [t for t in range(-2, 5) if zr[0] - 1e-9 <= t <= zr[1] + 1e-9]
    return {"type": "chart", "span": 4, "height": 90, "config": {"displayModeBar": False},
            "title": "Shared colour scale: sensing delay (log, viridis reversed); white = wrong / no decision",
            "data": [{"type": "heatmap", "x": zs, "y": [0], "z": [zs], "zmin": zr[0], "zmax": zr[1], "colorscale": "Viridis",
                      "reversescale": True, "showscale": False, "hoverinfo": "skip"}],
            "layout": {"margin": {"l": 20, "r": 20, "t": 4, "b": 30},
                       "xaxis": {"tickvals": tv, "ticktext": [lab.get(t, f"1e{t} ns") for t in tv], "range": [zr[0], zr[1]],
                                 "showgrid": False, "zeroline": False},
                       "yaxis": {"visible": False}, "showlegend": False}}


def cal_wave_fig(CW, vcm, vdd):
    t = [x * 1e9 for x in CW["t"]]
    mv = lambda arr, off=0.0: rd([(v - off) * 1e3 for v in arr], 3)
    tr = [
        {"x": t, "y": mv(CW["vcaln"], vcm), "name": "VCALN − VCM (mV)", "yaxis": "y", "line": {"color": C["c3"], "width": 2.0}},
        {"x": t, "y": mv(CW["vcalp"], vcm), "name": "VCALP − VCM (mV)", "yaxis": "y", "line": {"color": C["c7"], "width": 2.0, "dash": "dash"}},
        {"x": t, "y": mv(CW["vos_res"]), "name": "Residual Vos (mV)", "yaxis": "y", "line": {"color": C["s2"], "width": 2.6}},
        {"x": t, "y": mv(CW.get("bl_diff") or []), "name": "Bitline ΔV_BL (mV)", "yaxis": "y", "line": {"color": C["c1"], "width": 1.6, "dash": "dot"}},
        {"x": t, "y": rd(CW["clk"], 4), "name": "CLK (V)", "yaxis": "y2", "line": {"color": C["muted"], "width": 1.0}},
        {"x": t, "y": rd(CW["cal_en"], 4), "name": "CAL_EN (V)", "yaxis": "y2", "line": {"color": C["c4"], "width": 1.4, "dash": "dot"}},
        {"x": t, "y": rd(CW["outp"], 4), "name": "OUTP (V)", "yaxis": "y2", "line": {"color": C["c1"], "width": 2.1}},
        {"x": t, "y": rd(CW["outn"], 4), "name": "OUTN (V)", "yaxis": "y2", "line": {"color": C["c2"], "width": 2.1}},
    ]
    for x in tr:
        x["x"] = rd(x["x"], 4)
        x["type"] = "scatter"
        x["mode"] = "lines"
    t_cal = (CW.get("t_cal_end") or 0.8 * CW["t"][-1]) * 1e9
    return {"data": tr, "layout": {
        "xaxis": {"title": {"text": "time (ns)"}, "anchor": "y2"},
        "yaxis": {"domain": [0.48, 1.0], "title": {"text": "mV (cal / offset)"}},
        "yaxis2": {"domain": [0.0, 0.40], "title": {"text": "V (CLK / OUT)"}, "range": [-0.15, vdd * 1.1]},
        "hovermode": "x unified",
        "shapes": [{"type": "line", "xref": "paper", "yref": "y", "x0": 0, "x1": 1, "y0": 0, "y1": 0,
                    "line": {"color": C["muted"], "width": 1, "dash": "dot"}},
                   {"type": "line", "xref": "x", "yref": "paper", "x0": t_cal, "x1": t_cal, "y0": 0, "y1": 1,
                    "line": {"color": C["bad"], "width": 1.8, "dash": "dash"}}]}}


def cal_caption(CW, vcm):
    return (f"Closed-loop charge pump on MOS hold capacitors `MCAP1/MCAP2` steps `VCALN` (up) and `VCALP` (down) from "
            f"V<sub>CM</sub> ({fx(vcm, 3)} V) to cancel a +{fx(CW['vos_init_mv'], 1)} mV initial input mismatch down to "
            f"{fx(abs(CW['vos_final_mv']), 2)} mV residual offset (Cycles 1–{CW['n_cal_cycles']}, `CAL_EN=1`), followed by "
            f"frozen-hold normal reads (`CAL_EN=0`) resolving ΔV<sub>BL</sub> = −1.8 mV (Cycle 9 → OUTN=VDD) and +1.8 mV "
            f"(Cycle 10 → OUTP=VDD). *Hub note:* the charge pump and the input offset are behavioural sources in the "
            f"testbench; the residual V<sub>os</sub> trace is computed as V<sub>os,init</sub> − gain·(VCALN − VCALP).")


def cal_title(CW):
    return (f"Self-calibration transient waveform ({CW['n_cal_cycles']} closed-loop calibration cycles + 2 "
            f"post-calibration ±1.8 mV read cycles)")


# ----------------------------------------------------------------------------- detail document
def detail_doc(key):
    d = DATA[key]
    c = d["card"]
    base = f"designs/{key}"
    vdd, arch, mix, tgt = c["vdd"], c["arch"], c["mix"], c["target"]
    L = d.get("layout") or {}
    V = L.get("verify") or {}
    fclk = c["fclk"]
    selfcal = arch in ("miy", "scsa")
    blocks = []

    # ---------------- Overview
    ov = [{"type": "note", "tone": "muted",
           "text": "Ported from the retired sa-gen-gemini4 site (tabs Overview · Schematic · Simulation · Layout). "
                   "Use the **Simulation stage** option above to switch between the schematic netlist (Pre-PEX) and the "
                   "extracted-layout netlist (*Partial post-PEX*), like the old Schematic / Post-PEX toggle. Tiles and charts "
                   f"marked *model* are not SPICE results. Old crumb *comparison* → [this design's comparison set "
                   f"({vdd} V · {TGT_LBL[tgt]})](#/sa?page=compare&t.set={vtag(vdd)}-{tgt}&t.band={tgt})."}]
    for st in STG:
        R, D, T, cm, gs, vcm = sv(d, st)
        m, est, P = R["metrics"], D["est"], D["params"]
        idd_v = m.get("idd_avg") if m.get("idd_avg") is not None else T.get("idd_achieved")
        tail = m.get("idd_active_tail") if m.get("idd_active_tail") is not None else est.get("idd_active_tail")
        tail_txt = f"active tail {si(tail, 'A')}" if st == "pre" else "active tail not re-simulated post-PEX"
        hy = m.get("hysteresis")
        cens = trip_censored(m)
        items = [
            {"label": "Average I<sub>DD</sub> @ 2.5 MHz", "value": idd_v, "unit": "A", "si": True,
             "sub": f"target band {TGT_BAND[tgt]} · {tail_txt}"},
            {"label": "Sensing delay @1 mV", "value": m.get("delay_1mv"), "unit": "s", "si": True,
             "sub": f"@10 mV {si(m.get('delay_10mv'), 's')} · @100 mV {si(m.get('delay_100mv'), 's')}"},
            {"label": "Energy / read", "value": m.get("e_comp"), "unit": "J", "si": True,
             "sub": f"core {si(m.get('e_core'), 'J')} + clock drivers {si(m.get('e_clk'), 'J')}"},
            {"label": "Buffers + 200 fF loads", "value": m.get("e_buf"), "unit": "J", "si": True,
             "sub": f"total {si(m.get('e_total'), 'J')} per read"},
            {"label": "Deterministic ΔV<sub>BL,min</sub>",
             "value": "≥ 8 mV" if cens else "≤ 31 µV" if (m.get("min_detectable_dv_det_v") or 0) <= 15.7e-6
             else m.get("min_detectable_dv_det_v"), "unit": "V", "si": True,
             "sub": "trip-point bisection (9 steps over ±8 mV, 31 µV resolution) after opposite-polarity overdrive (simulated)"
                    + (" — **search limit**: the trip hit the ±8 mV window, the true value is larger" if cens else "")},
            {"label": "Hysteresis (decision memory)",
             "value": "≥ 16 mV" if cens else "< 0.2 mV" if isnum(hy) and abs(hy) < 0.2e-3 else si(hy, "V"),
             "sub": "trip point after 0 minus after 1 (±0.2·V<sub>DD</sub> preceding overdrive; 31 µV search resolution)"
                    + (" — **search limit** (±8 mV window), true value larger" if cens else "")},
            {"label": "Regeneration τ<sub>regen</sub>", "value": m.get("tau_regen"), "unit": "s", "si": True,
             "sub": f"integration phase {si(m.get('t_int'), 's')}"},
            {"label": "f<sub>max</sub>", "value": m.get("fmax"), "unit": "Hz", "si": True,
             "sub": "1 mV decisions, t<sub>d</sub> < 0.45 T"},
            {"label": "CM range (±1 mV resolves)",
             "value": f"{fx(m.get('cm_min'), 2)} – {fx(m.get('cm_max'), 2)} V" if m.get("cm_min") is not None else "—",
             "sub": f"nominal V<sub>CM</sub> {fx(P.get('vcm'), 3)} V"},
            {"label": "Kickback (10 kΩ source)", "value": m.get("kick_diff"), "unit": "V", "si": True,
             "sub": f"differential · CM {si(m.get('kick_cm'), 'V')}"},
            {"label": "Static leakage", "value": m.get("i_static_reset"), "unit": "A", "si": True,
             "sub": f"reset phase, 27 °C · 125 °C max {si(m.get('i_leak_125c_max'), 'A')}"},
        ]
        if L:
            items.append({"label": "Layout", "value": f"{ar(L.get('area_um2'))} µm²",
                          "sub": f"{fx(L.get('width_um'), 1)} × {fx(L.get('height_um'), 1)} µm, aspect {fx(L.get('aspect'), 2)}"})
        ov.append({"type": "stats", "alt": "keyres", "stage": st,
                   "title": f"Key results (tt, 27 °C, nominal V<sub>CM</sub>, uniform f<sub>read</sub> = {si(fclk, 'Hz')})",
                   "items": items})
        if selfcal and m.get("vos_sigma_uncal") is not None:
            os_sub = (f"post-cal · uncal. {si(m.get('vos_sigma_uncal'), 'V')} · range ±{fx(m.get('cal_range_mv'), 1)} mV "
                      f"(formula) · Pelgrom formula + random samples")
        else:
            os_sub = f"mean {si(m.get('vos_mean'), 'V')} · Pelgrom est. {si(est.get('sigma_os'), 'V')} · Pelgrom formula + random samples"
        mitems = [
            {"label": "Min detectable ΔV<sub>BL,min</sub> (incl. 3σ)", "value": m.get("min_detectable_dv_v"), "unit": "V", "si": True,
             "sub": f"= |hyst| + 3·√(σ<sub>n</sub>² + σ<sub>os</sub>²) · deterministic {si(m.get('min_detectable_dv_det_v'), 'V')} · 3σ stat. {si(m.get('min_detectable_dv_3sigma_v'), 'V')}"},
            {"label": "Input noise σ<sub>n</sub>", "value": m.get("sigma_noise"), "unit": "V", "si": True,
             "sub": f"estimate {si(est.get('sigma_n'), 'V')} · analytical-probit fallback, identical for all 96 designs"},
            {"label": "Offset σ<sub>os</sub> (old site: 100-run MC)", "value": m.get("vos_sigma"), "unit": "V", "si": True, "sub": os_sub},
            {"label": "E·σ<sub>n</sub>² (FoM)",
             "value": f"{m['fom_e_sigma2'] * 1e21:.3f} fJ·mV²" if isnum(m.get("fom_e_sigma2")) and m["fom_e_sigma2"] else "—",
             "sub": "lower is better · uses the model σ<sub>n</sub>"},
            {"label": "Global+mismatch MC", "value": m.get("mcg_delay_mean"), "unit": "s", "si": True,
             "sub": f"delay σ {si(m.get('mcg_delay_sigma'), 's')} · E σ {si(m.get('mcg_e_sigma'), 'J')} · synthetic log-normal samples"},
        ]
        ov.append({"type": "stats", "alt": "model", "stage": st, "title": "Model-based estimates (*model*, not SPICE results)",
                   "items": mitems,
                   "caption": "Shown as on the old site's *Key results* panel, but separated: in the source flow the noise "
                              "testbench fell back to an analytical probit (σ<sub>n</sub> = 381.9 µV for every design), the offset "
                              "“Monte Carlo” draws Python random samples around a Pelgrom-formula σ, and the global MC draws "
                              "log-normal samples around the nominal delay/energy. ΔV<sub>BL,min</sub> (3σ) and E·σ<sub>n</sub>² "
                              "inherit these model values."})
    notes = [{"type": "note", "tone": "info", "text": n} for n in (d["design"].get("notes") or [])]
    if mix == "nat":
        notes.append({"type": "note", "tone": "warn",
                      "text": "Native device: the PDK has no mismatch model for `nfet_06v0_nvt`; Monte-Carlo offset uses an "
                              "assumed Pelgrom coefficient equal to the 6 V NMOS (11.6 mV·µm)."})
    if notes:
        ov.append({"type": "section", "title": "Notes", "blocks": notes})

    # specification checks + design point
    for st in STG:
        R, D, T, cm, gs, vcm = sv(d, st)
        m, est, P = R["metrics"], D["est"], D["params"]
        gsd = gs or {}
        gsim = T.get("achieved") if T.get("achieved") is not None else (
            (gsd["n"] + gsd["p"]) / 2 if arch == "fia" and gsd.get("n") is not None and gsd.get("p") is not None
            else (gsd.get("n") if gsd.get("n") is not None else gsd.get("p")))
        tgt_g = est["gmid_target"]
        idd_v = m.get("idd_avg") if m.get("idd_avg") is not None else T.get("idd_achieved")
        lo, hi = D.get("idd_range") or [0, 1]
        func = m.get("functional") if m.get("functional") is not None else T.get("functional")
        dly = m.get("delay_1mv") if m.get("delay_1mv") is not None else c.get("delay_close")
        os_v = (f"{si(m.get('vos_sigma'), 'V')} cal. (uncal. {si(m.get('vos_sigma_uncal'), 'V')})"
                if m.get("self_calibrated") and m.get("vos_sigma_uncal") is not None else si(m.get("vos_sigma"), "V"))
        gm_lbl = "Input gm/Id within 6 % of the target (simulated, charge-weighted)"
        if arch == "fia":
            gm_lbl += " — *FIA: mean of the N and P pairs (per-pair values in the design point)*"
        if st == "partial":
            gm_lbl += " — *post-PEX value copied from the schematic closure*"
        specs = [
            ["Correct decisions at ±1 mV, ±10 mV, ±100 mV, ±0.5 mV after ±100 mV", func, "all correct" if func else "fails"],
            [gm_lbl, gsim is not None and abs(gsim - tgt_g) <= 0.06 * tgt_g, f"{fx(tgt_g, 2)} → {fx(gsim, 2)} /V"],
            [f"Average I<sub>DD</sub> in target band {TGT_BAND[tgt]} @ f<sub>read</sub> = 2.5 MHz",
             idd_v is not None and lo <= idd_v <= hi, f"{si(idd_v, 'A')} (target {TGT_BAND[tgt]})"],
            ["Offset σ ≤ 6.0 mV (Pelgrom-sized for 5 mV, 100-run MC) — *model*",
             (m["vos_sigma"] <= 6.0e-3) if m.get("vos_sigma") is not None else None, os_v],
            ["Sensing delay @1 mV < 48 % of the read period (192 ns)", dly is not None and dly < 0.48 / fclk,
             f"{si(dly, 's')} vs {si(0.48 / fclk, 's')}"],
            ["Correct at every PVT point", m.get("pvt_robust"),
             f"{m['pvt_pass']}/{m['pvt_total']}" if m.get("pvt_total") else "—"],
        ]
        if V:
            specs.append(["DRC clean (PDK KLayout deck)", V["drc"]["clean"],
                          "0 violations" if V["drc"]["clean"] else json.dumps(V["drc"]["violations"])])
            specs.append(["LVS match (PDK KLayout deck)", V["lvs"]["match"], "netlists match" if V["lvs"]["match"] else "mismatch"])
        rows = [{"check": k, "value": v, "res": {"v": "pending" if ok is None else "pass" if ok else "fail",
                                                  "s": "muted" if ok is None else "good" if ok else "bad"}}
                for k, ok, v in specs]
        ov.append({"type": "table", "alt": "spec", "stage": st, "title": "Specification checks", "search": False, "csv": False,
                   "columns": [{"key": "check", "label": "Check", "type": "text", "md": True, "wrap": True},
                               {"key": "value", "label": "Value", "type": "text"},
                               {"key": "res", "label": "Result", "type": "text"}], "rows": rows})
        knob = T.get("knob")
        knob_v = f"V<sub>CM</sub> {fx(P.get('vcm'), 4)} V"
        if arch == "fia":
            knob_v += f" · W<sub>CR</sub> {fx(P.get('w_cr'), 2)} µm"
        elif arch in ("db", "dbx"):
            knob_v += f" · W<sub>CT</sub> {fx(P.get('w_ct'), 2)} µm"
        gsim_txt = " · ".join(f"{k.upper()} {fx(v, 2)}" for k, v in gsd.items())
        if st == "partial":
            gsim_txt += " (copied from the schematic closure, not re-simulated)"
        pct = fx(100 * est["gmid_target"] / est["gmid_peak"], 0) if est.get("gmid_target") else ""
        kv = [
            ["Input devices (N pair + P pair)" if arch == "fia" else "Input device", in_dev_text(D)],
            [f"gm/Id target ({pct} % of peak {fx(est.get('gmid_peak'), 1)})", f"{fx(est['gmid_target'], 2)} /V · IC ≈ {fx(est.get('ic'), 2)}"],
            ["LUT V<sub>GS</sub>, I<sub>D</sub>/W, f<sub>T</sub> at target",
             f"{fx(est.get('vgs'), 3)} V · {si(est.get('idw'), 'A/µm')} · {si(est.get('ft'), 'Hz')}"],
            ["Target I<sub>DD</sub> band @ 2.5 MHz", f"{TGT_BAND[tgt]} → simulated {si(idd_v, 'A')}"],
            [f"Tuned knob: {KNOB.get(knob, knob or '—')}", knob_v],
            ["Simulated gm/Id (∫g<sub>m</sub>dt/∫I<sub>D</sub>dt)", gsim_txt],
        ]
        ov.append({"type": "kv", "alt": "dp", "stage": st, "title": "gm/Id & I<sub>DD</sub> design point", "cols": 2,
                   "items": [{"label": a, "value": b} for a, b in kv]})
        nl = "netlist.spice" if st == "pre" else "netlist_pex.spice"
        ov.append({"type": "downloads", "alt": "nl", "stage": st, "title": "Netlist",
                   "items": [{"label": f"Netlist ({'schematic' if st == 'pre' else 'post-PEX'})", "file": f"{base}/{nl}", "note": PIN_NOTE}]})
    T = d["tune"]
    P = d["design"]["params"]
    if T.get("history"):
        h = [x for x in T["history"] if x.get("gmid") is not None]
        ok, bad = [x for x in h if x.get("ok")], [x for x in h if not x.get("ok")]
        ov.append({"type": "chart", "title": "gm/Id closure in simulation",
                   "caption": "Every simulated value of the inversion knob during closure (filled = sense amplifier functional). Dashed: target.",
                   "data": [
                       {"type": "scatter", "x": [x["v"] for x in ok], "y": [x["gmid"] for x in ok], "mode": "markers",
                        "name": "functional", "marker": {"size": 9, "color": C["s1"]}},
                       {"type": "scatter", "x": [x["v"] for x in bad], "y": [x["gmid"] for x in bad], "mode": "markers",
                        "name": "not functional", "marker": {"size": 9, "symbol": "circle-open", "color": C["bad"], "line": {"width": 2}}},
                       {"type": "scatter", "x": [P["vcm"]], "y": [T.get("achieved")], "mode": "markers", "name": "chosen",
                        "marker": {"size": 14, "symbol": "star", "color": C["s2"]}}],
                   "layout": {"xaxis": {"title": {"text": "Knob value (V_CM in V / W_cap in µm)"}},
                              "yaxis": {"title": {"text": "simulated gm/Id (1/V)"}},
                              "shapes": [{"type": "line", "xref": "paper", "x0": 0, "x1": 1, "y0": T["target"], "y1": T["target"],
                                          "line": {"dash": "dash", "color": C["muted"]}}]}})
    blocks.append({"type": "section", "title": "Overview", "blocks": ov})

    # ---------------- Schematic
    D0 = d["design"]
    ins = set(D0["meta"]["inputs"])
    sch = []
    leg = ("Labels: flavour (n3v3/p3v3 thin oxide, n6v0/p6v0 thick oxide, nnat native), W/L in µm (× fingers); input devices "
           "show **gm/Id target → simulated** (charge-weighted over integration) and the header banner shows **I<sub>DD</sub> "
           "target band → simulated @ 2.5 MHz**.")
    for st, f in (("pre", "schematic.svg"), ("partial", "schematic_pex.svg")):
        if (DOCS / base / f).is_file():
            sch.append({"type": "image", "alt": "sch", "stage": st, "src": f"{base}/{f}", "bg": "white",
                        "title": "Schematic with gm/Id & I<sub>DD</sub> targets annotated",
                        "caption": leg + (" Post-PEX annotation (schematic_pex.svg)." if st == "partial" else "")})
    sch.append({"type": "table", "title": "Devices", "search": False,
                "columns": [{"key": "dev", "label": "Dev", "type": "text"}, {"key": "model", "label": "Model", "type": "text"},
                            {"key": "role", "label": "Role", "type": "text"}, {"key": "w", "label": "W", "unit": "µm", "digits": 4},
                            {"key": "l", "label": "L", "unit": "µm", "digits": 4}, {"key": "nf", "label": "nf"},
                            {"key": "g", "label": "gm/Id target", "digits": 4}, {"key": "dgsb", "label": "D/G/S/B", "type": "text"}],
                "rows": [[v["name"], v["model"], v["role"], v["w"], v["l"], v["nf"],
                          D0["est"]["gmid_target"] if v["name"] in ins else None,
                          f"{v['d']}/{v['g']}/{v['s']}/{v['b']}"] for v in D0["devices"]]})
    blocks.append({"type": "section", "title": "Schematic", "blocks": sch})

    # ---------------- Simulation
    sim = []
    for st in STG:
        R, D, T, cm, gs, vcm = sv(d, st)
        m, P = R["metrics"], D["params"]
        tag = "pre" if st == "pre" else "pex"
        nd, ndt, nc, nct = extrap_counts(R)
        W = R.get("waves")
        if W and W.get("t"):
            t = rd([x * 1e9 for x in W["t"]], 4)
            tr = [{"x": t, "y": rd(W["clk"], 4), "name": "CLK", "line": {"color": C["muted"], "width": 1.2}}]
            pc = [C["c3"], C["c6"], C["c4"], C["c5"]]
            for i, n in enumerate(R.get("pre_nodes") or []):
                if W.get(n):
                    tr.append({"x": t, "y": rd(W[n], 4), "name": n, "line": {"color": pc[i % 4], "width": 1.3, "dash": "dot"}})
            for i, n in enumerate(D["meta"]["latch"]):
                if W.get(n):
                    tr.append({"x": t, "y": rd(W[n], 4), "name": n, "line": {"color": C["c4"] if i else C["c5"], "width": 1.4, "dash": "dash"}})
            tr += [{"x": t, "y": rd(W["outp"], 4), "name": "OUTP", "line": {"color": C["c1"], "width": 2.2}},
                   {"x": t, "y": rd(W["outn"], 4), "name": "OUTN", "line": {"color": C["c2"], "width": 2.2}}]
            for x in tr:
                x.update({"type": "scatter", "mode": "lines"})
            src = write(f"d/{key}/{tag}_wave.json", {"data": tr, "layout": {
                "xaxis": {"title": {"text": "time (ns)"}}, "yaxis": {"title": {"text": "V"}, "range": [-0.1, vdd * 1.08]},
                "hovermode": "x unified"}}, 6)
            sim.append({"type": "chart", "alt": "wave", "stage": st, "span": 2, "height": 440, "src": src,
                        "title": "Transient waveforms (two cycles: −1 mV then +10 mV)",
                        "caption": "Clock, preamp / integration nodes, latch nodes (exponential positive-feedback regeneration), "
                                   "and the buffered outputs into 200 fF."})
        CW = R.get("cal_waves")
        if CW and CW.get("t"):
            src = write(f"d/{key}/{tag}_cal.json", cal_wave_fig(CW, P["vcm"], vdd), 6)
            sim.append({"type": "chart", "alt": "cal", "stage": st, "span": 2, "height": 480, "src": src,
                        "title": cal_title(CW), "caption": cal_caption(CW, P["vcm"])})
        if R.get("cmdm"):
            rows = [{"cm": r["cm"], "d": [p["delay"] if p.get("ok") else None for p in r["pts"]]} for r in R["cmdm"]]
            dm = [p["dm"] for p in R["cmdm"][0]["pts"]]
            zr = zrange([v for r in rows for v in r["d"]])
            lay = cmdm_layout(vdd, P["vcm"])
            lay["margin"]["r"] = 60
            src = write(f"d/{key}/{tag}_cmdm.json", {"data": [cmdm_trace(rows, dm, zr, True)], "layout": lay})
            cap = (f"Colour = clock→output sensing delay; white = wrong/no decision; red tick = nominal V<sub>CM</sub> "
                   f"{fx(P['vcm'], 3)} V.")
            if nc:
                cap += (f" *Hub note:* {nc} of {nct} cells off the 0.1/1/10/100 mV columns equal the τ·ln extrapolation of "
                        f"the 1 mV delay (likely fast-mode interpolation in the generator, not individual simulations).")
            sim.append({"type": "chart", "alt": "cmdm", "stage": st, "height": 420, "src": src,
                        "title": "Resolve-time map (input CM × differential bitline input |ΔV<sub>BL</sub>|)", "caption": cap})
        if R.get("delay_vs_vin"):
            p = R["delay_vs_vin"]
            cap = (f"τ<sub>regen</sub> = {si(m.get('tau_regen'), 's')} · ΔV<sub>BL,min</sub> = {si(m.get('min_detectable_dv_v'), 'V')} "
                   f"(*model*, incl. 3σ)")
            if nd:
                cap += (f". *Hub note:* {nd} of {ndt} points below 1 mV coincide with the τ·ln(1 mV/|ΔV|) extrapolation of "
                        f"the 1 mV delay to < 0.2 %.")
            sim.append({"type": "chart", "alt": "dvin", "stage": st, "height": 420, "title": "Sensing delay vs |ΔV<sub>BL</sub>|",
                        "caption": cap,
                        "data": [{"type": "scatter", "x": [q["vin"] for q in p], "y": [q["delay"] for q in p], "mode": "lines+markers",
                                  "name": "sensing delay", "line": {"color": C["s1"], "width": 2}, "marker": {"color": C["s1"]}}],
                        "layout": {"xaxis": ax_log("|ΔV_BL| (V)", dtick=1), "yaxis": ax_log("s", **log_ticks([q["delay"] for q in p])),
                                   "showlegend": False}})
        N = R.get("noise")
        if N and N.get("v"):
            mu, s = m.get("noise_mu") or 0, m.get("sigma_noise")
            tr = [{"type": "scatter", "x": N["v"], "y": N["p"], "mode": "markers", "name": "P(OUTP=1), binned",
                   "marker": {"color": C["s1"]}}]
            if isnum(s) and s > 0:
                xs = [N["v"][0] + (N["v"][-1] - N["v"][0]) * i / 80 for i in range(81)]
                tr.append({"type": "scatter", "x": xs, "y": [0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2)))) for x in xs],
                           "mode": "lines", "name": f"Φ fit, σ={si(s, 'V')}", "line": {"color": C["s2"], "width": 2}})
            sim.append({"type": "chart", "alt": "noise", "stage": st,
                        "title": "Input-referred noise (transient noise, probit fit) — *model*",
                        "caption": f"σ<sub>n</sub> = {si(s, 'V')} · μ = {si(m.get('noise_mu'), 'V')} · {N.get('n', 0)} decisions. "
                                   f"*Hub note:* every binned probability equals Φ(k·0.65) exactly — the source flow's analytical "
                                   f"fallback (kT/C estimate clamped at 450 µV), not transient-noise statistics.",
                        "data": tr, "layout": {"xaxis": {"title": {"text": "differential bitline input ΔV_BL (V)"}, "exponentformat": "SI"},
                                               "yaxis": {"title": {"text": "P(1)"}, "range": [-0.03, 1.03]}}})
        if R.get("mc_vos"):
            cap = f"σ {si(m.get('vos_sigma'), 'V')}"
            if m.get("self_calibrated") and m.get("vos_sigma_uncal") is not None:
                cap += f" (uncal. {si(m.get('vos_sigma_uncal'), 'V')})"
            cap += (f" · μ {si(m.get('vos_mean'), 'V')}. *Hub note:* samples are Python `random.gauss` draws around a "
                    f"Pelgrom-formula σ, not SPICE mismatch runs; post-PEX the formula σ is scaled ×0.97 and the samples are "
                    f"redrawn, so the shown post/pre σ ratio varies randomly (0.76–1.27 over the 96 designs).")
            sim.append({"type": "chart", "alt": "mc", "stage": st,
                        "title": f"Offset Monte Carlo (mismatch, {len(R['mc_vos'])} runs{' · post-calibration' if m.get('self_calibrated') else ''}) — *model*",
                        "caption": cap,
                        "data": [{"type": "histogram", "x": [round(v * 1e3, 4) for v in R["mc_vos"]], "name": "Vos",
                                  "marker": {"color": C["s1"], "line": {"color": "theme:paper", "width": 1.5}},
                                  "hovertemplate": "%{x} mV: %{y} runs<extra></extra>"}],
                        "layout": {"xaxis": {"title": {"text": "input offset (mV)"}}, "yaxis": {"title": {"text": "runs"}}, "showlegend": False}})
        G = R.get("mcg")
        if G and G.get("e"):
            sim.append({"type": "chart", "alt": "mcg", "stage": st, "title": "Global + mismatch Monte Carlo — *synthetic*",
                        "caption": f"{G['n_ok']}/{G['n']} runs correct at ±10 mV · delay σ {si(m.get('mcg_delay_sigma'), 's')}. "
                                   f"*Hub note:* log-normal Python samples around the nominal 10 mV delay and energy, not SPICE runs.",
                        "data": [{"type": "scatter", "x": G["e"], "y": G["delay"], "mode": "markers", "name": "run",
                                  "marker": {"color": C["s1"]}}],
                        "layout": {"xaxis": {"title": {"text": "energy / read (J)"}, "exponentformat": "SI"},
                                   "yaxis": {"title": {"text": "sensing delay @10 mV (s)"}, "exponentformat": "SI"}, "showlegend": False}})
        if R.get("cmdm"):
            okr = [r for r in R["cmdm"] if r.get("gmid") and (r["gmid"].get("n") is not None or r["gmid"].get("p") is not None)]
            cap = "Energy per read and simulated input gm/Id vs V<sub>CM</sub>"
            if st == "partial":
                cap += ". *Hub note:* post-PEX gm/Id per row is the copied schematic-closure value (flat line), not re-simulated."
            sim.append({"type": "chart", "alt": "cm", "stage": st, "title": "Common-mode sweep", "caption": cap,
                        "data": [{"type": "scatter", "x": [r["cm"] for r in R["cmdm"]], "y": [r["e"] for r in R["cmdm"]],
                                  "name": "energy / read", "mode": "lines+markers", "line": {"color": C["s1"], "width": 2}, "marker": {"color": C["s1"]}},
                                 {"type": "scatter", "x": [r["cm"] for r in okr],
                                  "y": [r["gmid"]["n"] if r["gmid"].get("n") is not None else r["gmid"]["p"] for r in okr],
                                  "name": "gm/Id (input)", "mode": "lines+markers", "yaxis": "y2",
                                  "line": {"color": C["s2"], "width": 2}, "marker": {"color": C["s2"]}}],
                        "layout": {"xaxis": {"title": {"text": "V_CM (V)"}, "range": [0, vdd]},
                                   "yaxis": dict({"title": {"text": "J"}, "exponentformat": "SI", "type": "log"}, **log_ticks([r["e"] for r in R["cmdm"]])),
                                   "yaxis2": {"title": {"text": "gm/Id (1/V)"}, "overlaying": "y", "side": "right", "showgrid": False},
                                   "margin": {"r": 50}}})
        K = (R.get("kick") or {}).get("waves")
        if K and K.get("t"):
            kt = rd([x * 1e9 for x in K["t"]], 4)
            src = write(f"d/{key}/{tag}_kick.json", {"data": [
                {"type": "scatter", "mode": "lines", "x": kt, "y": rd([v * 1e3 for v in K["dp"]], 4), "name": "INP pin − source",
                 "line": {"color": C["s1"], "width": 2}},
                {"type": "scatter", "mode": "lines", "x": kt, "y": rd([v * 1e3 for v in K["dn"]], 4), "name": "INN pin − source",
                 "line": {"color": C["s2"], "width": 2}}],
                "layout": {"xaxis": {"title": {"text": "time in cycle (ns)"}}, "yaxis": {"title": {"text": "mV"}}}}, 6)
            sim.append({"type": "chart", "alt": "kick", "stage": st, "src": src, "title": "Kickback (10 kΩ source)",
                        "caption": f"V(input pin) − V(source): differential {si(m.get('kick_diff'), 'V')} · CM {si(m.get('kick_cm'), 'V')}"})
        Q = R.get("cm_char")
        if Q:
            b0 = lambda r: (r.get("bursts") or [{}])[0]
            sim.append({"type": "chart", "alt": "cmchar", "stage": st, "title": "Trip point and unloaded decision delay vs input CM",
                        "caption": "Absolute trip point (f<sub>read</sub> = 2.5 MHz, 200 fF) and unloaded delay vs V<sub>CM</sub>. "
                                   "*Hub note:* the unloaded delay is simulated; the trip-point curve is a linear formula "
                                   "(V<sub>os,sys</sub> + 0.18 mV/V·(V<sub>CM</sub> − V<sub>CM,nom</sub>)) in the source flow — *model*.",
                        "data": [{"type": "scatter", "x": [r["cm"] for r in Q], "y": [None if r.get("vtrip") is None else r["vtrip"] * 1e3 for r in Q],
                                  "name": "trip point (mV, model)", "mode": "lines+markers", "line": {"color": C["s1"], "width": 2}, "marker": {"color": C["s1"]}},
                                 {"type": "scatter", "x": [r["cm"] for r in Q], "y": [b0(r).get("delay_small") for r in Q],
                                  "name": "unloaded delay", "mode": "lines+markers", "yaxis": "y2", "line": {"color": C["s2"], "width": 2},
                                  "marker": {"color": C["s2"], "size": 8, "symbol": ["circle-open" if b0(r).get("wrong") else "circle" for r in Q]}}],
                        "layout": {"xaxis": {"title": {"text": "V_CM (V)"}, "range": [0, vdd]}, "yaxis": {"title": {"text": "trip point (mV)"}},
                                   "yaxis2": {"title": {"text": "s"}, "overlaying": "y", "side": "right", "showgrid": False, "type": "log", **log_ticks([b0(r).get("delay_small") for r in Q]),
                                              "exponentformat": "SI"}, "margin": {"r": 50}}})
        F = R.get("fmax_scan")
        if F:
            sim.append({"type": "chart", "alt": "fmax", "stage": st, "title": "Clock-frequency scan",
                        "caption": f"f<sub>max</sub> = {si(m.get('fmax'), 'Hz')} · energy per read vs f<sub>clk</sub> (green = correct, red = fails)",
                        "data": [{"type": "scatter", "x": [f["f"] for f in F], "y": [f["e"] for f in F], "mode": "lines+markers", "name": "energy",
                                  "marker": {"size": 10, "color": [C["good"] if f["ok"] else C["bad"] for f in F]}, "line": {"color": C["muted"]}}],
                        "layout": {"xaxis": ax_log("f_clk (Hz)", dtick=1), "yaxis": {"title": {"text": "J / read"}, "exponentformat": "SI"},
                                   "showlegend": False}})
        pv = R.get("pvt") or []
        if pv:
            corners, temps = ["typical", "ff", "ss", "fs", "sf"], [-40, 27, 85, 125]
            vs = sorted({p["vdd"] for p in pv}, key=str)
            rows = []
            for cn in corners:
                for v in vs:
                    row = [next((p for p in pv if p["corner"] == cn and p["temp"] == t and p["vdd"] == v), None) for t in temps]
                    if not any(row):
                        continue
                    r = {"corner": cn, "supply": f"{fx(v, 2)} V"}
                    for t, p in zip(temps, row):
                        r[f"t{t}"] = "—" if not p else {
                            "v": f"{'✓' if p['ok'] else '✗'} {si(p.get('delay_1mv'), 's', 2)}<br><small>{si(p.get('e'), 'J', 2)} · "
                                 f"I<sub>leak</sub> {si(p.get('i_reset'), 'A', 2)}</small>", "s": "good" if p["ok"] else "bad"}
                    rows.append(r)
            sim.append({"type": "table", "alt": "pvt", "stage": st, "span": 2, "title": "PVT corners (±1 mV decisions)",
                        "search": False, "csv": False,
                        "caption": f"{m.get('pvt_pass')}/{m.get('pvt_total')} correct. Cell: decision ✓/✗ and sensing delay @1 mV; "
                                   f"second line energy per read · reset-phase leakage.",
                        "columns": [{"key": "corner", "label": "Corner", "type": "text"}, {"key": "supply", "label": "VDD", "type": "text"}] +
                                   [{"key": f"t{t}", "label": f"{t} °C<br><small>t<sub>d</sub> · E · I<sub>leak</sub></small>", "type": "text",
                                     "md": True, "align": "r"} for t in temps],
                        "rows": rows})
    blocks.append({"type": "section", "title": "Simulation", "cols": 2,
                   "intro": "All charts follow the **Simulation stage** option (schematic netlist vs extracted-layout netlist).",
                   "blocks": sim})

    # ---------------- Layout
    lay = []
    if L:
        drc = "DRC pending" if not V else ("DRC clean" if V["drc"]["clean"] else f"DRC: {json.dumps(V['drc']['violations'])}")
        lvs = "LVS pending" if not V else ("LVS match" if V["lvs"]["match"] else "LVS mismatch")
        lay.append({"type": "layout", "gds": f"{base}/comp.gds.gz", "title": "Layout (GF180MCU-D, met1–met4)", "max_height": 620,
                    "caption": f"**{drc} · {lvs}** · {fx(L.get('width_um'), 1)} × {fx(L.get('height_um'), 1)} µm = {ar(L.get('area_um2'))} µm² · "
                               f"aspect {fx(L.get('aspect'), 2)} · {len(L.get('nets') or [])} nets · {L.get('n_stubs')} routed terminals. "
                               f"Thumbnail rendered by the hub from the GDS (replaces the old zoomable layout.png)."})
        lay.append({"type": "stats", "items": [
            {"label": "Floorplan", "value": "1 NMOS + 1 PMOS row",
             "sub": f"rails on bottom (VSS) and top (VDD, VDDB on met4) edges; {L.get('channel_rows') or '—'} channel rows"},
            {"label": "Shared-diffusion centre pairs", "value": f"{len(L.get('interdigitated') or [])} pair(s)" if L.get("interdigitated") else "—",
             "sub": ", ".join(L.get("interdigitated") or []) + " · A fingers left, B fingers right of common source column"},
            {"label": "Mirror-symmetric pairs", "value": f"{len(L.get('mirrored_pairs') or [])} pairs",
             "sub": ", ".join(L.get("mirrored_pairs") or [])},
            {"label": "Mirror-routed net pairs", "value": str(len(L.get("symmetric_routes") or [])),
             "sub": ", ".join(L.get("symmetric_routes") or [])}]})
        dl = [("GDS (.gz)", "comp.gds.gz"), ("LVS netlist", "lvs_reference.spice")]
        if V:
            dl.append(("Extracted (Magic, extracted.cir)", "extracted.cir"))
        lay.append({"type": "downloads", "items": [{"label": a, "file": f"{base}/{b}"} for a, b in dl if (DOCS / base / b).is_file()]})
    blocks.append({"type": "section", "title": "Layout", "blocks": lay})
    return {"blocks": blocks}


# ----------------------------------------------------------------------------- design records
designs = []
for key in KEYS:
    c, d = CARD[key], DATA[key]
    base = f"designs/{key}"
    L = d.get("layout") or {}
    P = d["design"]["params"]
    est = d["design"]["est"]
    st = c.get("status") or {}
    area = L.get("area_um2") if isnum(L.get("area_um2")) else c.get("area")
    results = {}
    r = stage_result(c.get("m"), area, False)
    if r:
        results["pre"] = r
    if st.get("pex") == "done":
        r = stage_result(c.get("m_pex"), area, True)
        if r:
            results["partial"] = r
    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("gds", "comp.gds.gz"), ("netlist", "netlist.spice"),
        ("pex_netlist", "netlist_pex.spice"), ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json"))
        if (DOCS / base / v).is_file()}
    images = [{"label": "Schematic (post-PEX annotation)", "src": f"{base}/schematic_pex.svg"}] \
        if (DOCS / base / "schematic_pex.svg").is_file() else []
    downloads = [{"label": "Magic raw extraction (extracted.cir)", "file": f"{base}/extracted.cir"}] \
        if (DOCS / base / "extracted.cir").is_file() else []
    tg = META["targets"][c["target"]]
    selfcal = c["arch"] in ("miy", "scsa")
    m = c.get("m") or {}
    tags = [META["mixes"][c["mix"]], f"I_DD {TGT_BAND[c['target']]} ✓" if c.get("idd_met") is not False else "I_DD out of band",
            "f_read 2.5 MHz (uniform)", "C_L = 200 fF / output"]
    if selfcal:
        tags.append("Self-Cal ✓")
    if c.get("tune_met") is False:
        tags.append("gm/Id target not reached")
    pct = round(100 * est["gmid_target"] / est["gmid_peak"]) if est.get("gmid_peak") else None
    fia = c["arch"] == "fia"
    p = {("Input devices" if fia else "Input device"): in_dev_text(d["design"]),
         ("W_in,N / L_in (µm), nf" if fia else "W_in / L_in (µm), nf"): f"{fx(P['w_in'], 2)} / {fx(P['l_in'], 2)}, nf {P['nf_in']}",
         "gm/Id target → sim (V⁻¹)": f"{gmid_text(c, c.get('gmid_sim'))} (pre-PEX simulation)",
         "gm/Id target": f"{fx(est['gmid_target'], 2)} /V = {pct} % of peak {fx(est.get('gmid_peak'), 2)} · IC ≈ {fx(est.get('ic'), 2)}",
         "Nominal V_CM (V)": c.get("vcm"),
         "Tuned knob": {"vcm": "input common mode V_CM", "w_ct": "tail capacitor width W_CT",
                        "w_cr": "reservoir capacitor width W_CR"}.get(d["tune"].get("knob"), d["tune"].get("knob")),
         "W_tail (µm)": P.get("w_tail")}
    if c["arch"] in ("db", "dbx"):
        p["W_CT (µm)"] = P.get("w_ct")
    if c["arch"] == "fia":
        p["W_CR (µm)"] = P.get("w_cr")
        p["W_in,P (µm), nf"] = f"{fx(P.get('w_in_p'), 2)}, nf {P.get('nf_in_p')}"
    p["I_DD target band @2.5 MHz"] = f"{TGT_BAND[c['target']]} (closure target {si(tg['idd_target'], 'A')})"
    p["Read rate / load"] = "2.5 MHz (T_read 400 ns) · 200 fF per output"
    if selfcal:
        p["Cal range (formula, mV)"] = m.get("cal_range_mv")
        p["Cal step (formula, µV)"] = m.get("cal_step_uv")
    p["Routed nets"] = len(L.get("nets") or []) or None
    designs.append({
        "id": key,
        "title": f"{arch_s[c['arch']]} · {mix_s[c['mix']]} · {c['vdd']} V · {TGT_BAND[c['target']]}",
        "summary": f"**{META['archs'][c['arch']]}** — {META['mixes'][c['mix']]}; I<sub>DD</sub> band {TGT_LBL[c['target']]} "
                   f"at f<sub>read</sub> = 2.5 MHz, 200 fF per output.",
        "vdd": c["vdd"],
        "axes": {"topology": c["arch"], "mix": c["mix"], "target": c["target"]},
        "tags": tags,
        "physical": {"drc": st.get("drc"), "lvs": st.get("lvs"), "pex": True if st.get("pex") == "done" else None,
                     "area_um2": area, "width_um": L.get("width_um"), "height_um": L.get("height_um")},
        "results": results,
        "params": {k: v for k, v in p.items() if v is not None},
        "files": files,
        "images": images,
        "downloads": downloads,
        "detail": write(f"designs/{key}.json", detail_doc(key)),
    })


# ----------------------------------------------------------------------------- page: overview & comparison table
def stage_rows():
    rows = []
    for st in STG:
        for key in KEYS:
            c = CARD[key]
            m = card_m(key, st)
            g = c.get("gmid_sim") if st == "pre" else (c.get("gmid_sim_pex") or c.get("gmid_sim"))
            vcm = c.get("vcm") if st == "pre" else (c.get("vcm_pex") if c.get("vcm_pex") is not None else c.get("vcm"))
            s = c.get("status") or {}
            fom = m.get("fom_e_sigma2")
            rows.append({
                "stage": st, "design": key, "arch": arch_s[c["arch"]], "mix": c["mix"], "vdd": c["vdd"],
                "band": TGT_LBL[c["target"]], "idd": m.get("idd_avg"), "gm": gmid_text(c, g) + (" ᶜ" if st == "partial" else ""),
                "vcm": vcm, "dvmin": m.get("min_detectable_dv_v"), "td": m.get("delay_1mv"), "tau": m.get("tau_regen"),
                "e": m.get("e_comp"), "sn": m.get("sigma_noise"), "vos": m.get("vos_sigma"),
                "fom": round(fom * 1e21, 2) if isnum(fom) and fom else None, "fmax": m.get("fmax"),
                "cmr": f"{fx(m['cm_min'], 2)}–{fx(m['cm_max'], 2)}" if m.get("cm_min") is not None else "—",
                "pvt": {"v": f"{m['pvt_pass']}/{m['pvt_total']}" if m.get("pvt_total") else "—",
                        "s": "good" if m.get("pvt_robust") else "warn"},
                "kick": m.get("kick_diff"), "area": c.get("area"),
                "drclvs": "—" if s.get("drc") is None else f"{'✓' if s.get('drc') else '✗'}/{'✓' if s.get('lvs') else '✗'}",
                "selfcal": c["arch"] in ("miy", "scsa"),
                "iddok": c.get("idd_met") is not False, "_design": key})
    return rows


cmp_cols = [
    {"key": "stage", "label": "Stage", "type": "text"},
    {"key": "design", "label": "Design", "type": "design"},
    {"key": "arch", "label": "Arch", "type": "text"}, {"key": "mix", "label": "Mix", "type": "text"},
    {"key": "vdd", "label": "VDD", "unit": "V"}, {"key": "band", "label": "IDD Band", "type": "text"},
    {"key": "idd", "label": "I<sub>DD</sub> @2.5MHz", "unit": "A", "si": True, "better": "low"},
    {"key": "gm", "label": "gm/Id tgt→sim", "type": "text", "title": "ᶜ = post-PEX gm/Id copied from the schematic closure"},
    {"key": "vcm", "label": "V<sub>CM</sub>", "unit": "V", "digits": 4},
    {"key": "dvmin", "label": "ΔV<sub>BL,min</sub> (model)", "unit": "V", "si": True, "better": "low"},
    {"key": "td", "label": "t<sub>d</sub> 1 mV", "unit": "s", "si": True, "better": "low"},
    {"key": "tau", "label": "τ<sub>regen</sub>", "unit": "s", "si": True, "better": "low"},
    {"key": "e", "label": "E / read", "unit": "J", "si": True, "better": "low"},
    {"key": "sn", "label": "σ noise (model)", "unit": "V", "si": True, "better": "low"},
    {"key": "vos", "label": "σ offset (model)", "unit": "V", "si": True, "better": "low"},
    {"key": "fom", "label": "E·σ² (model)", "unit": "fJ·mV²", "digits": 4, "better": "low"},
    {"key": "fmax", "label": "f<sub>max</sub>", "unit": "Hz", "si": True, "better": "high"},
    {"key": "cmr", "label": "CM range", "unit": "V", "type": "text"},
    {"key": "pvt", "label": "PVT", "type": "text"},
    {"key": "kick", "label": "Kickback", "unit": "V", "si": True, "better": "low"},
    {"key": "area", "label": "Area", "unit": "µm²", "digits": 4, "better": "low"},
    {"key": "drclvs", "label": "DRC/LVS", "type": "text"},
    {"key": "selfcal", "label": "Self-Cal", "type": "status"},
    {"key": "iddok", "label": "I<sub>DD</sub> in band", "type": "status"},
]
n_closed = sum(1 for c in CARDS if c.get("tune_met") and c.get("idd_met") is not False)
n_sim = sum(1 for c in CARDS if (c.get("status") or {}).get("sim") == "done")
n_lay = sum(1 for c in CARDS if (c.get("status") or {}).get("drc") and (c.get("status") or {}).get("lvs"))
n_rob = {st: sum(1 for k in KEYS if card_m(k, st).get("functional") and card_m(k, st).get("pvt_robust")) for st in STG}
LEDE = (
    "Nine clocked sense-amplifier architectures — NMOS-input (StrongARM `san`, Schinkel double-tail `dt`, Babayan-Mashhadi "
    "cross-coupled double-tail `dtx`, dynamic-bias tail-capacitor double-tail `db` and `dbx`), PMOS-input (StrongARM `sap`), "
    "complementary latch-based (floating-inverter-amplifier preamp + StrongARM latch `fia`), and **closed-loop "
    "self-calibrating topologies** (Miyahara tail-less-latch self-calibrating dynamic comparator `miy` and self-calibrating "
    "StrongARM sense amplifier `scsa`) — across threshold/oxide mixtures (`lv` all 3.3 V thin-oxide, `hvl` 3.3 V input + 6 V "
    "thick-oxide high-V<sub>t</sub> latch & reset switches, `nat` 6 V native zero-V<sub>t</sub> NMOS input + 3.3 V latch) × "
    "**six (V<sub>DD</sub>, I<sub>DD</sub>) target combinations**: **V<sub>DD</sub> = 1.8 V and 3.3 V**, each with "
    "cycle-averaged **I<sub>DD</sub> ranges of 0.1–1 µA (deep subthreshold), 1–10 µA (weak inversion), and 10–100 µA "
    "(moderate inversion)**, all compared at the **same read rate (f<sub>read</sub> = 2.5 MHz, T<sub>read</sub> = 400 ns)** "
    "driving **200 fF** per output. Every design is sized via gm/Id lookup tables, dual-closed in simulation on the compute "
    "farm for both input-pair gm/Id and cycle-averaged I<sub>DD</sub>, laid out with gLayout + KLayout DRC/LVS verification, "
    "extracted with Magic, and characterised across minimum detectable bitline differential (ΔV<sub>BL,min</sub>), sensing "
    "delay, energy per read, transient shot noise, and Monte Carlo offset (including post-calibration offset "
    "σ<sub>os,cal</sub> < 0.5 mV for `miy` and `scsa`).")
overview = {"intro": "## Deliverable sense-amplifier design cards\n\n" + LEDE, "blocks": [
    {"type": "stats", "items": [
        {"label": "design cards (6 VDD×IDD sets)", "value": len(CARDS)}, {"label": "gm/Id & IDD closed", "value": n_closed},
        {"label": "characterised", "value": n_sim}, {"label": "DRC + LVS clean", "value": n_lay},
        {"label": "PVT-robust, pre-PEX", "value": n_rob["pre"]}, {"label": "PVT-robust, partial post-PEX", "value": n_rob["partial"]}]},
    {"type": "note", "tone": "warn", "title": "Provenance.",
     "text": "The input noise σ<sub>n</sub> (381.9 µV for every design), the offset σ<sub>os</sub> “MC”, the global MC, "
             "ΔV<sub>BL,min</sub> (3σ) and E·σ<sub>n</sub>² of the old site are model-based in the source flow; they are kept in "
             "this table and in the detail pages marked *(model)*, but not used as hub results. Details: Methodology → Data provenance."},
    {"type": "markdown", "title": "Coverage matrix — 6 (V<sub>DD</sub> × I<sub>DD</sub> range) combinations @ f<sub>read</sub> = 2.5 MHz",
     "text": "The coverage matrix lives in the **Designs** tab (rows = architecture · threshold mix, columns = I<sub>DD</sub> band "
             "inside each V<sub>DD</sub> group). As on the old site each cell is one design card showing the sensing delay at 1 mV "
             "and the average supply current I<sub>DD</sub> at the uniform 2.5 MHz read rate (choose other cell metrics, e.g. "
             "energy per read = core + clock, excluding output buffers and 200 fF loads, with *Cell metric*). Cell colours: green "
             "= correct at every PVT point (old badge *robust*), amber = correct at tt 27 °C only (*nominal*), red = fails. Click a "
             "cell to open the design card. The old **Schematic / Post-PEX** header toggle is the hub's **Simulation stage** option "
             "(Pre-PEX / Partial post-PEX; *Full post-PEX* with fill-from-earlier shows the partial results); the old filter rows "
             "(V<sub>DD</sub>, architecture, threshold mix, I<sub>DD</sub> range) are the V<sub>DD</sub> option and the axis chips."},
    {"type": "table", "title": "Comparison table", "stage_column": "stage", "sort": {"key": "design", "dir": "asc"},
     "caption": "All 96 designs compared at uniform f<sub>read</sub> = 2.5 MHz in one sortable table (click a header); rows open the "
                "design card. The table follows the Simulation-stage and V<sub>DD</sub> options. Columns marked *(model)* are "
                "model-based estimates (see note above); ᶜ = post-PEX gm/Id copied from the schematic closure.",
     "columns": cmp_cols, "rows": stage_rows(), "page_size": 200},
    {"type": "markdown", "title": "About the generator",
     "text": f"Generated {META['generated']} · GF180MCU-D (5LM, MIM M4/M5) · ngspice-46 + gLayout + KLayout + Magic · uniform read "
             f"rate f<sub>read</sub> = 2.5 MHz · C<sub>L</sub> = 200 fF per output · source: aicdb/sa-gen-gemini4 (private). "
             f"Old site header: *gm/Id-sized · simulation-closed gm/Id & IDD bands · ngspice-verified · DRC/LVS-clean gLayout · GF180MCU-D*."},
]}


# ----------------------------------------------------------------------------- page: comparison
def cmp_page():
    blocks = [{"type": "note", "tone": "info",
               "text": "Every chart follows the **Simulation stage** option (old Schematic / Post-PEX toggle) and the V<sub>DD</sub> "
                       "option. Click a map, line or point to open the design."}]
    # --- resolve-time maps, one tab per (VDD, IDD band) set
    tabs = []
    for v in VDDS:
        for t in TGT_ORDER:
            sel_all = [k for k in KEYS if CARD[k]["vdd"] == v and CARD[k]["target"] == t]
            if not sel_all:
                continue
            tb = []
            for st in STG:
                C_ = CMP["cmdm"] if st == "pre" else CMP["cmdm_pex"]
                sel = [k for k in sel_all if C_.get(k)]
                zr = zrange([x for k in sel for r in C_[k] for x in r["d"]])
                tb.append({"type": "stats", "alt": "st", "stage": st, "title": "Set statistics", "items": [
                    {"label": "designs in this set", "value": len(sel)},
                    {"label": "shared colour scale", "value": f"{si(10 ** zr[0] * 1e-9, 's', 2)}–{si(10 ** zr[1] * 1e-9, 's', 2)}"}]})
                charts = []
                for i, k in enumerate(sel):
                    c = CARD[k]
                    m = card_m(k, st)
                    vcm = c["vcm"] if st == "pre" else (c.get("vcm_pex") if c.get("vcm_pex") is not None else c["vcm"])
                    tag = "pre" if st == "pre" else "pex"
                    src = write(f"cmp/{tag}/{k}.json", {"data": [cmdm_trace(C_[k], CMP["dm"], zr, False, k)],
                                                        "layout": cmdm_layout(v, vcm)})
                    charts.append({"type": "chart", "src": src, "height": 300, "link_designs": True, "config": {"displayModeBar": "hover"},
                                   "title": f"[{arch_s[c['arch']]} · {c['mix']}](#/sa/{k})",
                                   "caption": f"V<sub>CM,nom</sub> {fx(vcm, 2)} V · I<sub>DD</sub> {si(m.get('idd_avg'), 'A')} · "
                                              f"t<sub>d</sub>(1 mV) {si(m.get('delay_1mv'), 's')}"})
                if charts:
                    charts.insert(0, colour_strip(zr))
                tb.append({"type": "section", "alt": "maps", "stage": st, "cols": 4, "title": "Resolve-time maps (this set)",
                           "blocks": charts or [
                    {"type": "note", "tone": "muted", "text": "Resolve-time maps are being computed on the farm for this set."}]})
            tabs.append({"label": f"{v} V · {TGT_LBL[t]}", "key": f"{vtag(v)}-{t}", "vdd": v, "blocks": tb})
    default = next((i for i, tb in enumerate(tabs) if tb["label"].startswith("1.8 V · 1–10")), 0)
    blocks.append({"type": "section", "title": "Resolve-time maps",
                   "intro": "One tab per (V<sub>DD</sub>, I<sub>DD</sub>) set (old VDD / IDD-range selectors). Every panel: x = "
                            "|ΔV<sub>BL</sub>| 10 µV…100 mV (log), y = V<sub>CM</sub> 0…V<sub>DD</sub>, colour = sensing delay (log, "
                            "viridis reversed, shared scale per set); white = wrong or no decision; red tick = nominal V<sub>CM</sub>.",
                   "blocks": [{"type": "tabs", "id": "set", "label": "Set", "default": default, "tabs": tabs}]})
    # --- sensing delay vs |dV|
    dtabs = []
    for t in TGT_ORDER:
        tb = []
        for st in STG:
            Dv = CMP["dvin"] if st == "pre" else (CMP.get("dvin_pex") or CMP["dvin"])
            dsel = [k for k in KEYS if CARD[k]["target"] == t and Dv.get(k)]
            xr = shared_range([p[0] for k in dsel for p in Dv[k]], True, 0.03)
            yr = shared_range([p[1] for k in dsel for p in Dv[k]], True, 0.05)
            for v in VDDS:
                tr = []
                for k in dsel:
                    c = CARD[k]
                    if c["vdd"] != v:
                        continue
                    tr.append({"type": "scatter", "x": [p[0] for p in Dv[k]], "y": [p[1] for p in Dv[k]], "mode": "lines+markers",
                               "name": k, "showlegend": False, "customdata": [k] * len(Dv[k]),
                               "line": {"color": ARCH_COL[c["arch"]], "dash": MIX_DASH[c["mix"]], "width": 1.8},
                               "marker": {"size": 4, "color": ARCH_COL[c["arch"]]},
                               "hovertemplate": f"{k}<br>|ΔV| %{{x:.3s}}V: %{{y:.3s}}s<extra></extra>"})
                tr += [legend_dummy(arch_s[a], mode="lines", line={"color": ARCH_COL[a], "width": 2}) for a in ARCH_ORDER]
                tr += [legend_dummy(mix_s[x], mode="lines", line={"color": C["ink"], "dash": MIX_DASH[x], "width": 2}) for x in MIX_ORDER]
                tb.append({"type": "chart", "alt": f"dv{vtag(v)}", "stage": st, "vdd": v, "height": 520, "link_designs": True,
                           "title": f"VDD {v} V · {TGT_LBL[t]}", "data": tr,
                           "layout": {"xaxis": ax_log("|ΔV_BL| (V)", xr), "yaxis": ax_log("sensing delay (s)", yr)}})
        dtabs.append({"label": TGT_LBL[t], "key": t, "blocks": [{"type": "section", "cols": 2, "blocks": tb}]})
    blocks.append({"type": "section", "title": "Sensing delay vs differential bitline input |ΔV<sub>BL</sub>|",
                   "intro": "Nominal common mode, tt 27 °C. The slope at small inputs is the regeneration time constant τ "
                            "(delay = t₀ − τ·ln|ΔV<sub>BL</sub>|). Both supplies are drawn on identical axes. Colour = architecture, "
                            "line style = threshold mix (solid 3.3V LV, dashed 6V HVL, dotted 6V Native).",
                   "blocks": [{"type": "tabs", "id": "band", "label": "I<sub>DD</sub> range (@ 2.5 MHz)", "default": 1, "tabs": dtabs}]})
    # --- scatter panels
    pairs = [("idd_avg", "delay_1mv", "average I_DD @ 2.5 MHz (A)", "sensing delay @1 mV (s)"),
             ("e_comp", "sigma_noise", "energy / read (J)", "input noise σ (V)")]
    sc = []
    for j, (xk, yk, xt, yt) in enumerate(pairs):
        for st in STG:
            xr2 = shared_range([card_m(k, st).get(xk) for k in KEYS], True, 0.05)
            yr2 = shared_range([card_m(k, st).get(yk) for k in KEYS], True, 0.05)
            for v in VDDS:
                tr = []
                for a in ARCH_ORDER:
                    for mx in MIX_ORDER:
                        for t in TGT_ORDER:
                            g = [k for k in KEYS if CARD[k]["vdd"] == v and CARD[k]["arch"] == a and CARD[k]["mix"] == mx
                                 and CARD[k]["target"] == t and card_m(k, st).get(xk) and card_m(k, st).get(yk)]
                            if not g:
                                continue
                            tr.append({"type": "scatter", "x": [card_m(k, st)[xk] for k in g], "y": [card_m(k, st)[yk] for k in g],
                                       "mode": "markers", "name": f"{a} {mx} {t}", "customdata": g, "showlegend": False,
                                       "marker": {"symbol": MIX_SYM[mx] + TGT_SYM[t], "size": 10, "color": ARCH_COL[a],
                                                  "line": {"width": 2, "color": ARCH_COL[a]}},
                                       "hovertemplate": f"%{{customdata}}<br>{xt}: %{{x:.3s}}<br>{yt}: %{{y:.3s}}<extra></extra>"})
                tr += [legend_dummy(arch_s[a], mode="markers", marker={"color": ARCH_COL[a], "size": 9}) for a in ARCH_ORDER]
                tr += [legend_dummy(mix_s[x], mode="markers", marker={"color": C["ink"], "symbol": MIX_SYM[x], "size": 9}) for x in MIX_ORDER]
                tr += [legend_dummy(TGT_LBL[t], mode="markers", marker={"color": C["ink"], "symbol": "circle" + TGT_SYM[t], "size": 9,
                                                                         "line": {"width": 2, "color": C["ink"]}}) for t in TGT_ORDER]
                ttl = f"{yt.split(' (')[0]} vs {xt.split(' (')[0]} · VDD {v} V" + (" — *σ is a model constant*" if j else "")
                sc.append({"type": "chart", "alt": f"sc{j}{vtag(v)}", "stage": st, "vdd": v, "height": 440, "link_designs": True,
                           "title": ttl, "data": tr,
                           "layout": {"xaxis": ax_log(xt, xr2), "yaxis": ax_log(yt, yr2) if yr2 and yr2[1] - yr2[0] > 0.2 else
                                      ax_log(yt, [sum(yr2) / 2 - 0.5, sum(yr2) / 2 + 0.5] if yr2 else None)}})
    blocks.append({"type": "section", "title": "Energy per read, average I<sub>DD</sub>, sensing delay, noise and offset", "cols": 2,
                   "intro": "One point per design (colour = architecture, symbol = threshold mix, filled = 0.1–1 µA subthreshold, "
                            "open = 1–10 µA weak inversion, open-dot = 10–100 µA moderate inversion). Panels in a row share their axes. "
                            "Hover for the design, click to open it. *Hub note:* the input noise σ is the same 381.9 µV model value for "
                            "every design in the source data, so the noise-vs-energy panels collapse onto one horizontal line.",
                   "blocks": sc})
    return {"intro": "## Design comparison\n\nKey result: the **resolve-time map** — time from the clock edge to the output crossing "
                     "VDD/2 (through the 3-stage buffer into 200 fF) as a function of the input common mode and the differential "
                     "bitline input |ΔV<sub>BL</sub>|, for every design across the 6 (V<sub>DD</sub>, I<sub>DD</sub>) target "
                     "combinations. White = the sense amplifier does not resolve correctly. All panels of a set share the same axes "
                     "and colour scale.", "blocks": blocks}


# ----------------------------------------------------------------------------- page: design-space explorer
XM = {
    "delay": ("sensing delay @1 mV", "sensing delay @1 mV (s)", True, lambda v: si(v, "s")),
    "e": ("energy / read", "energy / read (J)", True, lambda v: si(v, "J")),
    "sn": ("input-referred noise σ", "input noise σ (V)", True, lambda v: si(v, "V")),
    "vos": ("offset σ (mismatch MC)", "offset σ (V)", True, lambda v: si(v, "V")),
    "fom": ("FoM = E·σ<sub>n</sub>²", "E·σn² (fJ·mV²)", True, lambda v: f"{fx(v, 2)} fJ·mV²"),
    "area": ("active gate area", "gate area ΣW·L (µm²)", True, lambda v: f"{fx(v, 1)} µm²"),
    "tau": ("regeneration τ", "τ (s)", True, lambda v: si(v, "s")),
    "gmid": ("input-pair gm/Id (simulated)", "charge-weighted gm/Id (1/V)", False, lambda v: f"{fx(v, 1)} /V"),
}
PRESETS = [
    ("speed", "Energy vs speed", "delay", "e", True, "Minimise both energy per read and sensing delay."),
    ("noise", "Energy vs noise", "sn", "e", True, "Minimise both energy and input-referred noise: the classic E·σ² trade-off."),
    ("offset", "Energy vs offset", "vos", "e", True, "Minimise both energy and mismatch offset σ."),
    ("fom", "FoM vs speed", "delay", "fom", True, "Minimise the energy-noise figure of merit E·σn² and sensing delay."),
    ("area", "Offset vs area", "area", "vos", True, "Minimise both offset and active gate area."),
    ("gmid", "FoM vs gm/Id", "gmid", "fom", False, "How the input-pair inversion level sets the energy-noise efficiency (lower envelope per architecture)."),
]


def explore_page():
    archs = [a for a in ARCH_ORDER if a in DSE["archs"]]
    spaces = {}
    for st in STG:
        cols = {k: list(v) for k, v in (DSE["cols"] if st == "pre" else DSE.get("cols_pex") or DSE["cols"]).items()}
        cols["fom"] = [None if v is None else v * 1e21 for v in cols["fom"]]
        dl = [dict(x) for x in (DSE["delivered"] if st == "pre" else DSE.get("delivered_pex") or [])]
        for x in dl:
            if x.get("fom") is not None:
                x["fom"] *= 1e21
        spaces[st] = (cols, dl)
    n = DSE["n"]
    c0 = spaces["pre"][0]
    fun_n = sum(1 for x in c0["functional"] if x)
    met_n = sum(1 for i, x in enumerate(c0["functional"]) if x and c0["met"][i])

    def ex_v(cols, i, k):
        return cols[k][i]

    def hover(cols, i):
        return (f"<b>{cols['id'][i]}</b><br>{arch_s[DSE['archs'][cols['arch'][i]]]} · {mix_s[DSE['mixes'][cols['mix'][i]]]} · {cols['vdd'][i]} V"
                f"<br>gm/Id {fx(cols['gmid'][i], 1)} /V (target {fx(cols['gmid_t'][i], 1)}, {jround(cols['frac'][i] * 100)} % of peak)"
                f"<br>σos target {si(cols['sigma_os_t'][i], 'V')} · latch ×{cols['lat'][i]} · W<sub>in</sub> {fx(cols['w_in'][i], 1)} µm · "
                f"f<sub>read</sub> {si(cols['fclk'][i], 'Hz')}<br>t<sub>d</sub> {si(cols['delay'][i], 's')} · E {si(cols['e'][i], 'J')} · "
                f"τ {si(cols['tau'][i], 's')}<br>σn {si(cols['sn'][i], 'V')} · σos {si(cols['vos'][i], 'V')} · area {ar(cols['area'][i])} µm²")

    def front2(cols, ids, xk, yk):
        v = sorted([i for i in ids if (cols[xk][i] or 0) > 0 and (cols[yk][i] or 0) > 0], key=lambda i: (cols[xk][i], cols[yk][i]))
        out, best = [], math.inf
        for i in v:
            if cols[yk][i] < best:
                out.append(i)
                best = cols[yk][i]
        return out

    def envelope(cols, ids, xk, yk):
        best = {}
        for i in ids:
            if not ((cols[yk][i] or 0) > 0):
                continue
            b = jround(cols[xk][i])
            if b not in best or cols[yk][i] < cols[yk][best[b]]:
                best[b] = i
        return [best[b] for b in sorted(best)]

    def nd_set(cols, vdd):
        K = ("delay", "e", "sn", "vos")
        ids = [i for i in range(len(cols["arch"])) if cols["functional"][i] and cols["vdd"][i] == vdd and all((cols[k][i] or 0) > 0 for k in K)]
        ids.sort(key=lambda i: tuple(cols[k][i] for k in K))
        front = []
        for i in ids:
            pi = [cols[k][i] for k in K]
            dom = False
            for j in front:
                pj = [cols[k][j] for k in K]
                if all(a <= b for a, b in zip(pj, pi)) and any(a < b for a, b in zip(pj, pi)):
                    dom = True
                    break
            if not dom:
                front.append(i)
        return front

    nd = {(st, v): nd_set(spaces[st][0], v) for st in STG for v in VDDS}
    blocks = [
        {"type": "note", "tone": "warn", "title": "Model-based design space.",
         "text": "In the source flow (`flow/dse.py`) each (architecture, mix, V<sub>DD</sub>) group runs **12 SPICE anchor "
                 "simulations**; the 11,520 points are analytical scalings of those anchors over inversion level, σ<sub>os</sub> "
                 "target and latch scale (with random gm/Id jitter and a random offset factor), and the *post-PEX* space is the "
                 "pre-PEX space with fixed factors (delay ×1.14, E ×1.11, τ ×1.12, σ<sub>n</sub> ×0.94). The old site's claim that "
                 "each point is sized and closed in simulation is therefore not supported. Only the black diamonds (delivered "
                 "design cards) carry SPICE results (partial post-PEX for the post-PEX space; their σ<sub>n</sub>/σ<sub>os</sub> "
                 "are the model values described on the Methodology page)."},
    ]
    for st in STG:
        items = [{"label": "design points (old site: “simulated”; model-scaled)", "value": n},
                 {"label": "functional", "value": fun_n}, {"label": "gm/Id target reached", "value": met_n}]
        items += [{"label": f"4-objective non-dominated @ {v} V", "value": len(nd[(st, v)])} for v in VDDS]
        blocks.append({"type": "stats", "alt": "exstats", "stage": st, "title": "Design-space statistics", "items": items,
                       "caption": "All functional points reach their gm/Id target, so the old *only points that reach their gm/Id target* "
                                  "checkbox did not change any view."})
    # --- overview fronts (old #ex-overlay), one tab per trade-off preset
    ptabs = []
    for pk, plabel, xk, yk, front, pcap in PRESETS:
        X, Y = XM[xk], XM[yk]
        tb = []
        for st in STG:
            cols, dl = spaces[st]
            N_ = len(cols["arch"])
            all_ok = [i for i in range(N_) if cols["functional"][i]]
            xr = shared_range([cols[xk][i] for i in all_ok] + [x.get(xk) for x in dl], X[2])
            yr = shared_range([cols[yk][i] for i in all_ok] + [x.get(yk) for x in dl], Y[2])
            axes = {"xaxis": {"type": "log" if X[2] else "linear", "title": {"text": X[1]}, "exponentformat": "SI", "range": xr,
                              "autorange": False, **tick(X[2], xr)},
                    "yaxis": {"type": "log" if Y[2] else "linear", "title": {"text": Y[1]}, "exponentformat": "SI", "range": yr,
                              "autorange": False, **tick(Y[2], yr)}}
            for v in VDDS:
                ids = [i for i in all_ok if cols["vdd"][i] == v]
                curve = (lambda sub: front2(cols, sub, xk, yk)) if front else (lambda sub: envelope(cols, sub, xk, yk))
                tr = []
                for a in archs:
                    ai = DSE["archs"].index(a)
                    pts = curve([i for i in ids if cols["arch"][i] == ai])
                    tr.append({"type": "scatter", "x": [cols[xk][i] for i in pts], "y": [cols[yk][i] for i in pts], "name": arch_s[a],
                               "mode": "lines+markers", "marker": {"size": 6, "color": ARCH_COL[a]},
                               "line": {"width": 2, "shape": "hv" if front else "linear", "color": ARCH_COL[a]},
                               "text": [hover(cols, i) for i in pts], "hovertemplate": "%{text}<extra></extra>"})
                if front:
                    g = front2(cols, ids, xk, yk)
                    tr.append({"type": "scatter", "x": [cols[xk][i] for i in g], "y": [cols[yk][i] for i in g], "name": "all architectures",
                               "mode": "lines", "line": {"width": 1.5, "dash": "dash", "color": C["ink"], "shape": "hv"}, "hoverinfo": "skip"})
                dv = [x for x in dl if x["vdd"] == v and x.get("functional")]
                tr.append({"type": "scatter", "x": [x.get(xk) for x in dv], "y": [x.get(yk) for x in dv], "name": "delivered designs",
                           "mode": "markers", "customdata": [x["key"] for x in dv], "text": [x["key"] for x in dv],
                           "marker": {"symbol": "diamond", "size": 9, "color": "theme:ink", "line": {"color": "theme:paper", "width": 1.5}},
                           "hovertemplate": "%{text}<extra></extra>"})
                tag = "pre" if st == "pre" else "pex"
                src = write(f"ex/{pk}_{vtag(v)}_{tag}.json", {"data": tr, "layout": axes})
                tb.append({"type": "chart", "alt": f"ov{vtag(v)}", "stage": st, "vdd": v, "src": src, "height": 520, "link_designs": True,
                           "title": f"{'Pareto fronts' if front else 'Lower envelopes'} by architecture — {Y[0]} vs {X[0]} (VDD {v} V)",
                           "caption": pcap + (" Lines join each architecture's non-dominated points; the dashed line is the front over "
                                              "all architectures." if front else " Lines join each architecture's lowest E·σn² per "
                                              "rounded gm/Id (lower envelope).") + " Black diamonds are the 96 delivered design cards "
                                              "(click to open)."})
        ptabs.append({"label": plabel, "key": pk, "blocks": tb})
    blocks.append({"type": "section", "title": "Pareto fronts by architecture",
                   "intro": "The old explorer's overview chart for each *Trade-off* button; V<sub>DD</sub> follows the global option "
                            "(both supplies when *All*). Axis ranges are shared by both supplies, as on the old site.",
                   "blocks": [{"type": "tabs", "id": "tradeoff", "label": "Trade-off", "tabs": ptabs}]})
    # --- explorer data (functional points of both spaces + delivered cards)
    E = {k: [] for k in ("id", "stage", "kind", "arch", "mix", "vdd", "frac", "gmid_t", "gmid", "met", "sigma_os_t", "lat", "w_in",
                         "fclk", "delay", "e", "tau", "sn", "vos", "fom", "area", "delivered", "design")}
    for st in STG:
        cols, dl = spaces[st]
        for i in range(len(cols["arch"])):
            if not cols["functional"][i]:
                continue
            E["id"].append(cols["id"][i]); E["stage"].append(st); E["kind"].append("sweep")
            E["arch"].append(DSE["archs"][cols["arch"][i]]); E["mix"].append(DSE["mixes"][cols["mix"][i]]); E["vdd"].append(cols["vdd"][i])
            E["frac"].append(jround(cols["frac"][i] * 100)); E["gmid_t"].append(cols["gmid_t"][i]); E["gmid"].append(cols["gmid"][i])
            E["met"].append("yes" if cols["met"][i] else "no"); E["sigma_os_t"].append(cols["sigma_os_t"][i]); E["lat"].append(cols["lat"][i])
            E["w_in"].append(cols["w_in"][i]); E["fclk"].append(cols["fclk"][i])
            for k in ("delay", "e", "tau", "sn", "vos", "fom", "area"):
                E[k].append(cols[k][i])
            E["delivered"].append(False); E["design"].append(None)
        for x in dl:
            if not x.get("functional"):
                continue
            est = DATA[x["key"]]["design"]["est"] if x["key"] in DATA else {}
            tg = META["targets"].get(x.get("target")) or {}
            E["id"].append(x["key"]); E["stage"].append(st); E["kind"].append("card")
            E["arch"].append(x["arch"]); E["mix"].append(x["mix"]); E["vdd"].append(x["vdd"])
            # a card's inversion level = its gm/Id target as % of the flavour's peak (colours it like the sweep)
            E["frac"].append(jround(100 * est["gmid_target"] / est["gmid_peak"]) if est.get("gmid_peak") else None)
            E["gmid_t"].append(CARD[x["key"]]["gmid_target"] if x["key"] in CARD else None)
            E["gmid"].append(x.get("gmid")); E["met"].append("yes" if CARD.get(x["key"], {}).get("tune_met") else "no")
            E["sigma_os_t"].append(tg.get("sigma_os_target")); E["lat"].append(tg.get("lat_scale"))
            E["w_in"].append(DATA[x["key"]]["design"]["params"]["w_in"] if x["key"] in DATA else None)
            E["fclk"].append(CARD[x["key"]]["fclk"] if x["key"] in CARD else None)
            for k in ("delay", "e", "tau", "sn", "vos", "fom", "area"):
                E[k].append(x.get(k))
            E["delivered"].append(True); E["design"].append(x["key"] if x["key"] in CARD else None)
    ex_src = write("data/dse_explorer.json", {"columns": E})
    dims = [
        {"key": "delay", "label": "Sensing delay @1 mV", "unit": "s", "si": True, "log": True, "better": "low"},
        {"key": "e", "label": "Energy / read", "unit": "J", "si": True, "log": True, "better": "low"},
        {"key": "sn", "label": "Input noise σn (model)", "unit": "V", "si": True, "log": True, "better": "low"},
        {"key": "vos", "label": "Offset σos (model)", "unit": "V", "si": True, "log": True, "better": "low"},
        {"key": "fom", "label": "E·σn² (model)", "unit": "fJ·mV²", "log": True, "better": "low"},
        {"key": "area", "label": "Gate area ΣW·L", "unit": "µm²", "log": True, "better": "low"},
        {"key": "tau", "label": "Regeneration τ", "unit": "s", "si": True, "log": True, "better": "low"},
        {"key": "gmid", "label": "Input-pair gm/Id", "unit": "1/V"},
        {"key": "gmid_t", "label": "gm/Id target", "unit": "1/V"},
        {"key": "frac", "label": "gm/Id % of peak", "unit": "%"},
        {"key": "sigma_os_t", "label": "σos target", "unit": "V", "si": True},
        {"key": "lat", "label": "Latch scale", "unit": "×"},
        {"key": "w_in", "label": "W_in", "unit": "µm", "log": True},
        {"key": "fclk", "label": "f_read", "unit": "Hz", "si": True},
        {"key": "arch", "label": "Architecture", "type": "cat", "labels": {a: arch_s[a] for a in archs}, "order": archs,
         "colors": {a: ARCH_COL[a] for a in archs}},
        {"key": "mix", "label": "Threshold mix", "type": "cat", "labels": {x: mix_s[x] for x in MIX_ORDER}, "order": MIX_ORDER},
        {"key": "vdd", "label": "VDD", "unit": "V", "type": "cat", "labels": {str(v): f"{v} V" for v in VDDS}, "order": VDDS},
        {"key": "kind", "label": "Source", "type": "cat", "labels": {"sweep": "DSE sweep (model)", "card": "Delivered card (SPICE)"},
         "order": ["sweep", "card"]},
        {"key": "met", "label": "gm/Id target reached", "type": "cat"},
    ]
    hov = ["kind", "arch", "mix", "vdd", "gmid", "gmid_t", "frac", "sigma_os_t", "lat", "w_in", "fclk", "delay", "e", "tau", "sn", "vos", "area"]
    env_desc = ("The old page drew each architecture's **lower envelope** (best E·σn² per rounded gm/Id) here; the explorer has no "
                "envelope mode, so the envelopes are in the *FoM vs gm/Id* tab of **Pareto fronts by architecture** above.")

    def ex_presets(color, symbol, facet, front):
        return [{"label": pl, "x": xk, "y": yk, "color": color, "symbol": symbol, "facet": facet, "pareto": front if fr else "",
                 "desc": pcap + ("" if fr else " " + env_desc)} for _, pl, xk, yk, fr, pcap in PRESETS]

    ex1, ex2 = [], []
    for v in VDDS:
        ex1.append({"label": f"{v} V", "key": str(v), "vdd": v, "blocks": [
            {"type": "explorer", "src": ex_src, "dims": dims, "x": "delay", "y": "e", "color": "arch",
             "filters": ["vdd", "arch", "mix", "kind", "met"], "filters_default": {"vdd": [v]}, "fixed_axes": True,
             "highlight": "delivered", "highlight_label": "Delivered design cards", "design_key": "design", "label_key": "id",
             "hover": hov, "pareto_default": "color", "height": 560, "preset_default": 0,
             "presets": ex_presets("arch", "", "", "color")}]})
        ex2.append({"label": f"{v} V", "key": str(v), "vdd": v, "blocks": [
            {"type": "explorer", "src": ex_src, "dims": dims, "x": "delay", "y": "e", "color": "frac", "symbol": "mix",
             "facet_default": "arch", "filters": ["vdd", "mix", "kind"], "filters_default": {"vdd": [v]}, "fixed_axes": True,
             "highlight": "delivered", "highlight_label": "Delivered design cards", "design_key": "design", "label_key": "id",
             "hover": hov, "pareto_default": "all", "preset_default": 0,
             "presets": ex_presets("frac", "mix", "arch", "all")}]})
    blocks.append({"type": "section", "title": "Design-space explorer",
                   "intro": "Every functional point of the sweep, for the stage chosen with the Simulation-stage option (pre-PEX space "
                            "or the post-PEX scaled space; the 251 non-functional points are not plotted, as on the old site). One "
                            "supply at a time as on the old page (tabs; add the other supply with the V<sub>DD</sub> chips). Pick a "
                            "trade-off preset or any X/Y/colour/symbol/facet; *front per colour group* draws each architecture's "
                            "non-dominated points (the delivered cards are not front candidates, as on the old site). Ringed points = "
                            "delivered design cards (click to open). Axes stay fixed when filtering. All points are at the uniform "
                            "2.5 MHz read rate into 200 fF; gate area is ΣW·L of the devices (not the layout area).",
                   "blocks": [{"type": "tabs", "id": "exvdd", "label": "V<sub>DD</sub>", "tabs": ex1}]})
    blocks.append({"type": "section", "title": "Per-architecture design clouds",
                   "intro": "One panel per architecture, all on shared axes. Points are coloured by the inversion level (gm/Id as % "
                            "of the flavour's peak, 35…94 %; delivered cards at their target level); symbol = threshold mix; the line "
                            "is each architecture's front over the sweep points for the current axes; ringed points = delivered cards. "
                            "One supply per tab, as on the old page.",
                   "blocks": [{"type": "tabs", "id": "cloudvdd", "label": "V<sub>DD</sub>", "tabs": ex2}]})
    # --- non-dominated table
    nrows = []
    for st in STG:
        cols, _ = spaces[st]
        for v in VDDS:
            for i in nd[(st, v)]:
                nrows.append({"stage": st, "vdd": v, "id": cols["id"][i], "arch": arch_s[DSE["archs"][cols["arch"][i]]],
                              "mix": DSE["mixes"][cols["mix"][i]],
                              "gmid": cols["gmid"][i] if cols["met"][i] else {"v": cols["gmid"][i], "s": "warn", "title": "gm/Id target missed"},
                              "sig": cols["sigma_os_t"][i], "lat": cols["lat"][i], "delay": cols["delay"][i], "e": cols["e"][i], "sn": cols["sn"][i],
                              "vos": cols["vos"][i], "fom": cols["fom"][i], "area": cols["area"][i], "fclk": cols["fclk"][i]})
    nsrc = write("data/dse_nondominated.json", {"rows": nrows})
    blocks.append({"type": "table", "title": "Non-dominated designs", "src": nsrc, "stage_column": "stage", "sort": {"key": "e", "dir": "asc"},
                   "page_size": 400,
                   "caption": "Designs not beaten on all four of sensing delay, energy per read, input noise and offset at the same supply "
                              "(4-objective Pareto set; amber gm/Id = target missed — none in the data). Click a header to sort. Counts: " +
                              "; ".join(f"{len(nd[(st, v)])} at VDD {v} V ({'pre-PEX' if st == 'pre' else 'post-PEX space'})"
                                        for st in STG for v in VDDS) + ". Noise and offset are model values (see note above).",
                   "columns": [{"key": "stage", "label": "Stage", "type": "text"}, {"key": "vdd", "label": "VDD", "unit": "V"},
                               {"key": "id", "label": "Design point", "type": "text"}, {"key": "arch", "label": "Architecture", "type": "text"},
                               {"key": "mix", "label": "Mix", "type": "text"}, {"key": "gmid", "label": "gm/Id", "unit": "1/V", "digits": 3},
                               {"key": "sig", "label": "σos tgt", "unit": "V", "si": True, "digits": 2},
                               {"key": "lat", "label": "latch", "unit": "×", "digits": 3},
                               {"key": "delay", "label": "t<sub>d</sub> 1 mV", "unit": "s", "si": True, "better": "low"},
                               {"key": "e", "label": "E", "unit": "J", "si": True, "better": "low"},
                               {"key": "sn", "label": "σn", "unit": "V", "si": True, "better": "low"},
                               {"key": "vos", "label": "σos MC", "unit": "V", "si": True, "better": "low"},
                               {"key": "fom", "label": "E·σn²", "unit": "fJ·mV²", "digits": 3, "better": "low"},
                               {"key": "area", "label": "area", "unit": "µm²", "digits": 4, "better": "low"},
                               {"key": "fclk", "label": "f<sub>read</sub>", "unit": "Hz", "si": True}]})
    intro = ("## Design-space explorer\n\nEvery architecture and threshold mixture at both supplies (1.8 V, 3.3 V), swept over the "
             "input-pair inversion level (gm/Id = 50…92 % of each flavour's peak across moderate, weak, and deep subthreshold "
             "operation), the Pelgrom offset target that sets input-pair area (σ<sub>os</sub> = 3 / 5 / 8 mV), and latch scaling. "
             "Each point is sized and closed in simulation on the compute farm, then characterised into **200 fF** at uniform 2.5 MHz "
             "read rate. *(Text of the old site; see the provenance note below. The data actually span 35…94 % of peak, "
             "σ<sub>os</sub> targets 2–8.5 mV and latch scales 0.6–2.2.)*")
    return {"intro": intro, "blocks": blocks}


# ----------------------------------------------------------------------------- page: methodology
def method_page():
    pk = lambda dev, L: max(x for x in GMID[dev][L]["gmid"] if x is not None) if GMID.get(dev, {}).get(L) else None
    flow = (
        "1. **gm/Id lookup tables across weak inversion & deep subthreshold.** ngspice DC sweeps on the compute farm of `nfet_03v3`, "
        "`pfet_03v3`, 6 V thick-oxide high-V<sub>t</sub> `nfet_06v0`/`pfet_06v0`, and 6 V native zero-V<sub>t</sub> `nfet_06v0_nvt` "
        "(W = 10 µm, 6 lengths per flavour, V<sub>GS</sub> from −0.6 V/0 V to 3.3 V, V<sub>DS</sub> 0.25…3.3 V) characterize "
        "I<sub>D</sub>/W, gm/Id, gm/gds, f<sub>T</sub>, C<sub>gg</sub>, and C<sub>dd</sub>.\n"
        "2. **Six (V<sub>DD</sub>, I<sub>DD</sub>) target combinations at uniform read rate.** All designs are evaluated at the **same "
        "read rate f<sub>read</sub> = 2.5 MHz (T<sub>read</sub> = 400 ns)** across V<sub>DD</sub> ∈ {1.8 V, 3.3 V} and three "
        "cycle-averaged supply current bands: **0.1–1 µA** (deep subthreshold, gm/Id = 0.87 × peak, IC ≈ 0.15), **1–10 µA** (weak "
        "inversion, gm/Id = 0.72 × peak, IC ≈ 0.55), and **10–100 µA** (upper weak / moderate inversion, gm/Id = 0.56 × peak, IC ≈ 1.4).\n"
        "3. **Sizing & dual simulation closure.** Input-pair gate area W·L<sub>eff</sub> is set from Pelgrom mismatch (σ<sub>os</sub> "
        "= 5 mV target using PDK mismatch coefficients). In simulation on the compute farm, each design undergoes two-step closure: "
        "(1) bisecting its architecture inversion knob (V<sub>CM</sub>, C<sub>T</sub>, or C<sub>R</sub> × V<sub>CM</sub>) until the "
        "charge-weighted input-pair gm/Id during integration (∫g<sub>m</sub>dt / ∫I<sub>D</sub>dt) matches the target, and (2) "
        "closing the cycle-averaged supply current I<sub>DD</sub> = (1/T<sub>read</sub>)∫I<sub>VDD</sub>(t)dt at 2.5 MHz squarely "
        "into the target band (0.1–1 µA, 1–10 µA, or 10–100 µA).\n"
        "4. **Comprehensive testbench suite.** Every design is verified on the compute farm with testbenches covering: (1) minimum "
        "detectable bitline differential ΔV<sub>BL,min</sub> (deterministic hysteresis resolution after opposite-polarity ±100 mV "
        "overdrive + 3σ statistical limit), (2) sensing delay vs |ΔV<sub>BL</sub>| (3 µV…100 mV, regeneration time constant "
        "τ<sub>regen</sub>) and 2D resolve-time map (14 V<sub>CM</sub> × 9 |ΔV<sub>BL</sub>|), (3) energy per read and average "
        "I<sub>DD</sub> split into core, clock drivers, and 200 fF output buffers, (4) input-referred noise σ<sub>n</sub> via "
        "transient shot-noise simulation + probit CDF fit, (5) 100-run Pelgrom mismatch Monte Carlo offset σ<sub>os</sub> + 40-run "
        "global+mismatch MC, 29 PVT corners, kickback into 10 kΩ, and f<sub>max</sub> scan.\n"
        "5. **Layout & Post-PEX verification.** Layouts are generated using the GF180 gLayout flow + KLayout DRC/LVS verification and "
        "Magic parasitic extraction in `hpretl/iic-osic-tools`, then re-simulated post-PEX on the compute farm.")
    tbs = (
        "- **Minimum detectable bitline differential (ΔV<sub>BL,min</sub>):** 3-stage zooming staircase search with opposite-polarity "
        "±20 mV / ±100 mV preconditioning measures deterministic hysteresis (decision memory from incomplete reset) and systematic "
        "offset; combined with 6√(σ<sub>n</sub>² + σ<sub>os</sub>²) for 99.7% statistical yield.\n"
        "- **Sensing delay & resolve-time map:** 14 common modes × 9 differential inputs (10 µV…100 mV) + 17-point log sweep "
        "(3 µV…100 mV) extracting regeneration τ<sub>regen</sub>.\n"
        "- **Energy per read & average I<sub>DD</sub>:** Cycle-averaged I<sub>DD</sub> = E<sub>core</sub> / (V<sub>DD</sub> · "
        "T<sub>read</sub>) at uniform f<sub>read</sub> = 2.5 MHz, plus clock-driver and buffer energy.\n"
        "- **Transient noise:** Shot-noise current sources across every core FET over 11 input overdrive levels, fitted with a normal "
        "CDF (probit) for input-referred σ<sub>n</sub> and FoM = E·σ<sub>n</sub>².\n"
        "- **Monte Carlo offset, self-calibration & PVT:** 100-run Pelgrom mismatch MC (in-simulation 9-step binary-search SAR per "
        "seed), closed-loop charge-pump self-calibration via auxiliary transconductance pairs `MCAL1, MCAL2` and MOS hold capacitors "
        "`MCAP1, MCAP2` for `miy` (Miyahara tail-less-latch comparator) and `scsa` (self-calibrating StrongARM), 40-run "
        "global+mismatch MC, and 29 PVT corners (tt/ff/ss/fs/sf × −40/27/125 °C × VDD ±10%).")
    trows = []
    for dev, L in (("nfet_03v3", "0.5"), ("pfet_03v3", "0.5"), ("nfet_06v0_nvt", "1.8"), ("nfet_06v0", "0.7"), ("pfet_06v0", "0.55")):
        p = pk(dev, L)
        trows.append([f"{dev} (L {L} µm)", fx(p, 2), fx(p * 0.87, 2), fx(p * 0.72, 2), fx(p * 0.56, 2)])
    gm_tabs = []
    cols8 = [C["c1"], C["c2"], C["c3"], C["c4"], C["c5"], C["c6"], C["c7"], C["c8"]]
    for dev in GMID:
        Ls = list(GMID[dev])
        figs = []
        for j, (fxk, fyk, xt, yt, ylog) in enumerate((("vgs", "gmid", "|VGS| (V)", "gm/Id (1/V)", False),
                                                      ("gmid", "idw", "gm/Id (1/V)", "Id/W (A/µm)", True),
                                                      ("gmid", "ft", "gm/Id (1/V)", "fT (Hz)", True))):
            tr = [{"type": "scatter", "x": GMID[dev][L][fxk], "y": GMID[dev][L][fyk], "name": f"L={L}", "mode": "lines",
                   "line": {"color": cols8[i % len(cols8)], "width": 1.8}} for i, L in enumerate(Ls)]
            lay = {"xaxis": {"title": {"text": xt}}, "yaxis": {"title": {"text": yt}}, "showlegend": j == 0}
            if ylog:
                lay["yaxis"].update({"type": "log", "exponentformat": "SI"})
            src = write(f"gmid/{dev}_{fyk}.json", {"data": tr, "layout": lay})
            figs.append({"type": "chart", "src": src, "height": 340})
        gm_tabs.append({"label": dev, "key": dev, "blocks": [{"type": "section", "cols": 3, "blocks": figs}]})
    prov = (
        "Checked against the generator source (`flow/char.py`, `flow/dse.py`, `flow/layout/gen.py`) while porting the site to the hub:\n\n"
        "- **Simulation stages.** *Pre-PEX* = schematic netlist. *Partial post-PEX* = `netlist_pex.spice`: the schematic devices plus "
        "Magic C-only node capacitances scaled ×0.085 and clamped to 0.12–0.65 fF on internal nets (×0.012 / 0.015–0.035 fF for "
        "sub-threshold StrongARM-P), no wiring resistance, inputs/clock/supplies ideal — only part of the layout parasitics.\n"
        "- **Input noise σ<sub>n</sub>.** All 192 noise records (96 designs × 2 stages) hold the analytical-probit fallback "
        "(P = Φ(k·0.65) exactly, kT/C estimate clamped at 450 µV); the reported σ<sub>n</sub> = 381.9 µV is the same for every design "
        "→ *model constant*, not a transient-noise result.\n"
        "- **Offset σ<sub>os</sub> “100-run MC”.** Python `random.gauss` samples around a Pelgrom-formula σ (input pair + latch/gain); "
        "the statistical SPICE deck is run but its output is not used; post-PEX the formula σ is scaled ×0.97 and the samples are "
        "redrawn, so shown post/pre σ ratios scatter between 0.76 and 1.27. Self-calibrated designs use a "
        "quantisation/noise formula for the post-cal σ. → *model*.\n"
        "- **Global + mismatch MC (40 runs).** Log-normal Python samples around the nominal 10 mV delay and energy → *synthetic*.\n"
        "- **ΔV<sub>BL,min</sub> (incl. 3σ) and E·σ<sub>n</sub>².** Derived from the two model values above → *model*. The "
        "deterministic ΔV<sub>BL,min</sub> (trip-point bisection after ±overdrive), hysteresis and systematic offset are simulated.\n"
        "- **Trip point vs V<sub>CM</sub>.** Linear formula; the unloaded delay vs V<sub>CM</sub> is simulated.\n"
        "- **Deterministic trip search.** 9-step bisection over ±8 mV (31.25 µV bins) after a ±0.2·V<sub>DD</sub> preconditioning "
        "overdrive (not the ±20 mV / ±100 mV quoted in the testbench text above). Hysteresis, systematic offset and the deterministic "
        "ΔV<sub>BL,min</sub> are therefore quantised to 31 µV (173 of 192 records sit at the 15.6 µV floor = ‘≤ 31 µV’); in 5 FIA "
        "records the search hit the ±8 mV window, so those values are only lower bounds and are left out of the hub results.\n"
        "- **CM range** (and the hub's Input CM min/max) uses the ±1 mV column of the resolve-time map on the 14-point V<sub>CM</sub> "
        "grid; the old tile label ‘≥100 µV resolves’ did not match the flow.\n"
        "- **FIA gm/Id.** The FIA has an NMOS and a PMOS input pair; the hub reports both (FIA N-/P-pair gm/Id) instead of a "
        "single value; the old spec check used their mean.\n"
        "- **Post-PEX gm/Id** is copied from the schematic closure and the post-PEX active-tail current is 0 in every record → both "
        "omitted from the hub's partial-stage results.\n"
        "- **Delay sweeps.** In some designs the sub-mV points of the delay sweep and the off-grid cells of the resolve-time map equal "
        "the τ·ln extrapolation of the 1 mV delay (fast-mode interpolation); the detail pages count them per design.\n"
        "- **Energy after PEX.** Energy per read is lower post-PEX than pre-PEX in 61 of 96 designs (mainly the clock-driver term), "
        "which added capacitance would not explain — treat with caution.\n"
        "- **Design-space explorer (11,520 points).** 12 SPICE anchors per (architecture, mix, V<sub>DD</sub>) group; all points are "
        "analytical scalings of them; the post-PEX space applies fixed factors (delay ×1.14, E ×1.11, τ ×1.12, σ<sub>n</sub> ×0.94).\n"
        "- **What the hub uses as results.** Only SPICE-derived quantities (delays, energies, I<sub>DD</sub>, τ, hysteresis, "
        "deterministic ΔV<sub>BL,min</sub>, kickback, f<sub>max</sub>, CM range, leakage, PVT pass counts) plus the layout area. "
        "*Robust* = functional and correct at all 29 PVT points (pre-PEX " + f"{n_rob['pre']}/96, partial post-PEX {n_rob['partial']}/96).")
    blocks = [
        {"type": "section", "title": "Flow", "blocks": [{"type": "markdown", "text": flow}]},
        {"type": "section", "title": "Inversion targets & testbenches", "blocks": [
            {"type": "table", "title": "Inversion targets (gm/Id in 1/V) & I<sub>DD</sub> bands (@ 2.5 MHz)", "search": False, "csv": True,
             "columns": [{"key": "d", "label": "Input device", "type": "text"}, {"key": "p", "label": "peak gm/Id", "type": "text", "align": "r"},
                         {"key": "a", "label": "0.1–1 µA (×0.87, sub-Vt)", "type": "text", "align": "r"},
                         {"key": "b", "label": "1–10 µA (×0.72, weak inv.)", "type": "text", "align": "r"},
                         {"key": "c", "label": "10–100 µA (×0.56, mod. inv.)", "type": "text", "align": "r"}],
             "rows": trows, "caption": "Peak gm/Id read from the published gm/Id lookup tables (`data/gmid.json`)."},
            {"type": "markdown", "title": "Testbenches (all driving 200 fF on OUTP and OUTN at f<sub>read</sub> = 2.5 MHz)", "text": tbs}]},
        {"type": "section", "title": "gm/Id design charts",
         "intro": "ngspice LUT sweeps per device flavour (one line per channel length L in µm): gm/Id vs V<sub>GS</sub>, I<sub>D</sub>/W "
                  "vs gm/Id and f<sub>T</sub> vs gm/Id.",
         "blocks": [{"type": "tabs", "id": "dev", "label": "Device", "tabs": gm_tabs}]},
        {"type": "section", "title": "Data provenance (hub notes)", "blocks": [
            {"type": "markdown", "text": prov},
            {"type": "note", "tone": "info",
             "text": f"Tool chain (old site footer): generated {META['generated']} · GF180MCU-D (5LM, MIM M4/M5) · ngspice-46 + gLayout + "
                     f"KLayout + Magic · uniform read rate f<sub>read</sub> = 2.5 MHz · C<sub>L</sub> = 200 fF per output."}]},
    ]
    return {"blocks": blocks}


pages = [
    {"id": "overview", "title": "Overview & table", "src": write("pages/overview.json", overview)},
    {"id": "compare", "title": "Comparison", "src": write("pages/compare.json", cmp_page())},
    {"id": "explore", "title": "Design-space explorer", "src": write("pages/explore.json", explore_page())},
    {"id": "method", "title": "Methodology", "src": write("pages/method.json", method_page())},
]

gen = META.get("generated", "")
try:
    gen_iso = gen.replace(" UTC", "").replace(" ", "T") + ":00Z"
except Exception:  # noqa: BLE001
    gen_iso = None

comp = {
    "schema": "aicdb-hub/2",
    "id": "sa",
    "name": "Sense amps",
    "title": "Low-Power Clocked Sense Amplifier Generator",
    "summary": "Nine clocked sense-amplifier / comparator architectures (StrongARM N/P, double-tail and its cross-coupled and "
               "dynamic-bias variants, FIA preamp, two self-calibrating designs) in three threshold-voltage mixes, gm/Id-sized and "
               "closed in simulation into three I_DD bands at a uniform 2.5 MHz read rate for 1.8 V and 3.3 V, 200 fF per output; "
               "29-point PVT, KLayout DRC/LVS, Magic capacitance extraction (partial post-PEX).",
    "technology": "gf180mcuD",
    "generated": gen_iso,
    "stats": [{"label": "PVT-robust (pre / partial)", "value": f"{n_rob['pre']} / {n_rob['partial']}"},
              {"label": "PVT points per design", "value": "29"},
              {"label": "DSE points (model-scaled)", "value": f"{DSE['n']:,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=s or None, better=b, digits=dg if not s else None,
                                       desc=DESC.get(k)).items() if v is not None} for k, l, u, s, b, dg in METRICS],
    "axes": {
        "topology": {"label": "Architecture",
                     "values": [{"id": a, "label": arch_s[a]} for a in ARCH_ORDER if a in META["archs"]]},
        "mix": {"label": "Threshold mix", "values": [{"id": x, "label": mix_s[x]} for x in MIX_ORDER if x in META["mixes"]]},
        "target": {"label": "I_DD range @2.5 MHz", "values": [{"id": t, "label": TGT_LBL[t]} for t in TGT_ORDER if t in META["targets"]]},
    },
    "matrix": {"rows": ["topology", "mix"], "cols": ["target"], "metrics": ["delay", "idd", "e_comp"],
               "presets": [{"label": "Delay @1 mV · I_DD · energy (old matrix)", "metrics": ["delay", "idd", "e_comp"]},
                           {"label": "Energy / read · delay", "metrics": ["e_comp", "delay"]},
                           {"label": "Worst-PVT delay · leakage @125 °C", "metrics": ["delay_worst", "leak"]},
                           {"label": "Max clock · kickback", "metrics": ["fmax", "kick"]},
                           {"label": "τ_regen · hysteresis", "metrics": ["tau", "hyst"]},
                           {"label": "Area · total energy", "metrics": ["area", "e_total"]}]},
    "card_metrics": ["idd", "gmid", "delay", "e_comp", "dv_det", "tau", "kick", "fmax", "area"],
    "cards_group_by": "topology",
    "table_metrics": ["idd", "gmid", "delay", "tau", "e_comp", "dv_det", "hyst", "fmax", "cm_min", "cm_max", "kick", "leak", "area"],
    "pages": pages,
    "designs": designs,
}
(OUT / "component.json").write_text(json.dumps(rs(comp), separators=(",", ":"), ensure_ascii=False))
