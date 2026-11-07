#!/usr/bin/env python3
"""Bootstrap hub adapter for switch-gen-gemini4 (schema aicdb-hub/2).

usage: switch.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus
  hub/pages/*.json      overview, topology comparison, design-space explorer, methodology
  hub/designs/<id>.json one detail document per design card (Overview / Schematic / Simulation / Layout)
  hub/data/**           explorer data, Pareto-front charts and tables
Starting point for the repo builder: copy to scripts/export_hub.py in the repo (OUT_DIR = docs/hub).

Data (the same files the old site's assets/app.js used):
  data/index.json        meta + one card per topology x VDD x current class
                         card.m  = schematic characterisation (15 PVT points)          -> results.pre
                         card.mp = same benches on the Magic-extracted full cell netlist -> results.full
  designs/<key>/data.json  per-card evidence: char (schematic) / post (extracted) curves, circuit, layout, verify
  data/sweep.json        design-space sweep (schematic simulations, area estimated) + precomputed Pareto fronts
  data/gmid.json         gm/ID lookup curves of the five devices
Cards with status.sim == "n/a" (3.3 V-oxide bootstrap at 3.3 V) have no results: they are not design
records, but are listed on the Overview page (coverage matrix + "Not applicable" table) and in the stats.
Stdlib only.
"""
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
import sys
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
HUB = out  # "hub/<x>" paths resolve to OUT_DIR/<x>


def load(rel):
    return json.loads((docs / rel).read_text())


IDX = load("data/index.json")
META, CARDS = IDX["meta"], IDX["cards"]
SHORT, ORDER, DESC = META["short"], META["order"], META["desc"]
ICLS = META["iclasses"]
GRADES = META["ron_grades"]          # [["A", 0.02], ...]
DROP, LEAKF = META["drop_frac"], META["leak_frac"]
DESIGN_KEYS = ["rt", "ws", "naux", "area_um2", "layout_w", "layout_h", "aspect", "banks", "em_ok", "act_um2", "mim_um2",
               "vtest", "imax", "rl", "ch", "T", "thd_amp", "thd_vc", "cg_sw"]
ICL = {"10u-100u": "10–100 µA", "100u-1m": "0.1–1 mA", "1m-10m": "1–10 mA", "10m-100m": "10–100 mA", "100m-1": "0.1–1 A"}
TCOL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#8c3bd1", "#11a3a3", "#7a5c00", "#d43d3d",
        "#0284c7", "#c026d3", "#4f46e5"]
S1, S2, S3, BAD, GOOD, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#cf222e", "#1a7f37", "rgba(140,140,140,0.55)"
DIAMOND = {"symbol": "diamond", "size": 9, "color": "#71717a", "line": {"width": 1.2, "color": "#ffffff"}}   # mid grey: visible in light and dark themes
STAGE_OF = {"pre": "pre", "post": "full"}   # "post" is set per design (full / partial) and to "partial" for the mixed page views
VIEW_NAME = {"pre": "schematic (pre-PEX)", "post": "extracted (post-PEX)"}
written = []


# ----------------------------------------------------------------------------- formatting (ports of app.js)
def r5(o):
    """round floats to 5 significant digits (recursively) for compact hosted JSON"""
    if isinstance(o, float):
        if not math.isfinite(o):
            return None
        return float(f"{o:.5g}")
    if isinstance(o, dict):
        return {k: r5(v) for k, v in o.items()}
    if isinstance(o, list):
        return [r5(v) for v in o]
    return o


def write(rel, obj):
    """write hub/<rel> (rel without the hub/ prefix) and return the "hub/..." reference"""
    p = HUB / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(r5(obj), separators=(",", ":"), ensure_ascii=False))
    written.append(rel)
    return f"hub/{rel}"


def jsnum(x, d):
    """+(x).toPrecision(d) printed like a JS number"""
    v = float(f"{x:.{d}g}")
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


PFX = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f"), (1e-18, "a")]


def si(v, unit="", d=3):
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "—"
    if v == 0:
        return "0 " + unit
    a = abs(v)
    for m, p in PFX:
        if a >= m * 0.9995:
            return f"{jsnum(v / m, d)} {p}{unit}"
    return f"{jsnum(v / 1e-18, d)} a{unit}"


def jsround(x):
    """Math.round"""
    return int(math.floor(x + 0.5))


def fx(v, d=1):
    """(+v).toFixed(d)"""
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "—"
    q = Decimal(v).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)  # exact binary value, ties away from zero (JS)
    return f"{q:.{d}f}"


def area(a):
    if a is None:
        return "—"
    return f"{a / 1e6:.2f} mm²" if a >= 1e6 else f"{int(math.floor(a + 0.5)):,} µm²"


def range_txt(iv):
    return "none" if not iv else " ∪ ".join(f"{fx(a, 2)}–{fx(b, 2)} V" for a, b in iv)


def grade_txt(m):
    if m.get("drop") is None:
        return "—"
    return f"{m.get('grade') or 'below D'} · {fx(100 * m['drop'], 1 if m['drop'] < 0.1 else 0)} % VDD"


def grade_s(g):
    return "good" if g in ("A", "B") else "warn" if g in ("C", "D") else "bad"


def pick(o, ks):
    return {k: o[k] for k in ks if o and k in o}


def knobs_txt(k):
    return " ".join(f"{a}={jsnum(b, 6) if isinstance(b, float) else b}" for a, b in k.items())


def icl_of(key):
    return ICL.get(key, key)


def gds_bbox(path):
    """(width, height) in µm of the drawn geometry of a flat GDS(.gz) — stdlib GDSII record reader"""
    import gzip
    import struct
    raw = gzip.open(path).read() if str(path).endswith(".gz") else Path(path).read_bytes()

    def real8(b):
        if not any(b):
            return 0.0
        sign = -1 if b[0] & 0x80 else 1
        exp = (b[0] & 0x7F) - 64
        mant = int.from_bytes(b[1:8], "big") / 2 ** 56
        return sign * mant * 16 ** exp
    i, n, unit_m = 0, len(raw), 1e-9
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    elem = None
    while i + 4 <= n:
        ln, rt = struct.unpack(">HB", raw[i:i + 3])
        if ln < 4:
            break
        body = raw[i + 4:i + ln]
        if rt == 0x03:                       # UNITS: user/db, db in metres
            unit_m = real8(body[8:16])
        elif rt in (0x08, 0x09, 0x2D, 0x0C, 0x0A, 0x0B):  # BOUNDARY PATH BOX TEXT SREF AREF
            elem = rt
        elif rt == 0x11:                     # ENDEL
            elem = None
        elif rt == 0x10 and elem in (0x08, 0x09, 0x2D):
            v = struct.unpack(f">{len(body) // 4}i", body)
            xs, ys = v[0::2], v[1::2]
            x0, x1, y0, y1 = min(x0, *xs), max(x1, *xs), min(y0, *ys), max(y1, *ys)
        i += ln
    if x0 == math.inf:
        return None
    s = unit_m * 1e6
    return (x1 - x0) * s, (y1 - y0) * s


def mv(c, view):
    """metrics of a card in a view: post-PEX = design data + extracted results only (app.js MV)"""
    if view == "post":
        return {**pick(c["m"], DESIGN_KEYS), **(c.get("mp") or {})}
    return c["m"]


def cval(c, k, view):
    m = mv(c, view)
    if k == "area":
        return m.get("area_um2")
    if k == "fom_ra":
        return m["area_um2"] * m["ron_wc"] if m.get("area_um2") and m.get("ron_wc") else None
    return m.get(k)


def status_txt(c, view):
    st, b = c["status"], []
    if st["sim"] == "n/a":
        return "not applicable"
    b.append("Sim ✓" if st["sim"] == "done" else "Sim …")
    b.append({"done": "Layout ✓", "failed": "Layout ✗", "timeout": "Layout > 30 min"}.get(st["layout"], "Layout …"))
    if st.get("drc") is not None:
        b.append("DRC ✓" if st["drc"] else "DRC ✗")
    if st.get("lvs") is not None:
        b.append("LVS ✓" if st["lvs"] else "LVS ✗")
    m = mv(c, view)
    if m.get("coverage") is not None:
        b.append("rail-to-rail" if m["coverage"] > 0.97 else f"{jsround(100 * m['coverage'])} % of VDD" if m["coverage"] > 0 else "no valid range")
    if m.get("stress_ok") is False:
        b.append("overstress")
    if m.get("drop") is not None:
        b.append(f"R_on grade {grade_txt(m)}")
    if view == "post" and not c.get("mp"):
        b.append("no post-PEX")
    if m.get("em_ok") is False:
        b.append("EM-limited")
    return " · ".join(b)


def robust(m, imax):
    """the repo's own specification checks (app.js tabOverview), all at worst PVT"""
    return bool(m.get("ron_wc") is not None and m["ron_wc"] <= m["rt"] * 1.001
                and m.get("grade") is not None and (m.get("coverage") or 0) > 0
                and m.get("leak_wc") is not None and m["leak_wc"] <= LEAKF * imax * 1.001
                and m.get("stress_ok"))


# ----------------------------------------------------------------------------- metrics
METRICS = [
    # key, label, unit, si, digits, better, source field, scale
    ("coverage", "Valid range", "% VDD", False, 3, "high", "coverage", 100),
    ("on_coverage", "On-range", "% VDD", False, 3, "high", "on_coverage", 100),
    ("off_coverage", "Off-range", "% VDD", False, 3, "high", "off_coverage", 100),
    ("ron_vtest", "R_on @ test level", "Ω", True, 3, "low", "ron_vtest", 1),
    ("ron_min", "R_on min (tt, range)", "Ω", True, 3, "low", "ron_min", 1),
    ("ron_max", "R_on max (tt, range)", "Ω", True, 3, "low", "ron_max", 1),
    ("ron_wc", "R_on worst PVT", "Ω", True, 3, "low", "ron_wc", 1),
    ("drop", "I_max·R_on drop (worst PVT)", "% VDD", False, 3, "low", "drop", 100),
    ("ron_flat", "R_on flatness (max/min)", "", False, 3, "low", "ron_flat", 1),
    ("roff_wc", "R_off worst PVT", "Ω", True, 3, "high", "roff_wc", 1),
    ("leak_wc", "Off leakage worst PVT", "A", True, 3, "low", "leak_wc", 1),
    ("leak_tt", "Off leakage tt", "A", True, 3, "low", "leak_tt", 1),
    ("t_on", "Turn-on time", "s", True, 3, "low", "t_on", 1),
    ("t_off", "Turn-off time", "s", True, 3, "low", "t_off", 1),
    ("t_gate", "Gate delay", "s", True, 3, "low", "t_gate", 1),
    ("e_vdd", "Switching energy / cycle", "J", True, 3, "low", "e_vdd", 1),
    ("e_in", "Energy from input / cycle", "J", True, 3, "low", "e_in", 1),
    ("q_vtest", "Q_inj @ test level", "C", True, 3, None, "q_vtest", 1),
    ("q_absmax", "Max |charge injection|", "C", True, 3, "low", "q_absmax", 1),
    ("ped_absmax", "Max hold pedestal", "V", True, 3, "low", "ped_absmax", 1),
    ("iso_1m", "Off-isolation @1 MHz", "dB", False, 3, "low", "iso_1m", 1),
    ("iso_10m", "Off-isolation @10 MHz", "dB", False, 3, "low", "iso_10m", 1),
    ("iso_100m", "Off-isolation @100 MHz", "dB", False, 3, "low", "iso_100m", 1),
    ("coff", "C_off", "F", True, 3, "low", "coff", 1),
    ("ron_coff", "R_on·C_off", "s", True, 3, "low", "ron_coff_fs", 1e-15),
    ("thd", "Tracking THD (1 MHz, 90 %)", "dB", False, 3, "low", "thd_db", 1),
    ("thd_small", "Tracking THD (1 MHz, 40 %)", "dB", False, 3, "low", "thd_small_db", 1),
    ("vgs_on", "On-state gate drive", "V", False, 3, "high", "vgs_on", 1),
    ("v_gate_on", "On-state gate voltage", "V", False, 3, None, "v_gate_on", 1),
    ("stress", "Device stress / rating (sustained)", "%", False, 3, "low", "stress_ratio", 100),
    ("stress_peak", "Device stress / rating (peak)", "%", False, 3, "low", "stress_peak_ratio", 100),
    ("area", "Layout area", "µm²", False, 4, "low", "area_um2", 1),
]


METRIC_DESC = {
    "coverage": "Valid signal range (on-range ∩ off-range) as a fraction of VDD, worst PVT; matrix colour: green > 97 % (rail-to-rail), amber partial, red none",
    "on_coverage": "Input range where the worst-PVT R_on stays within 3× its minimum",
    "off_coverage": "Largest window in which every (in, out) pair leaks < 0.1 % of I_max (worst PVT)",
    "ron_vtest": "On-resistance at the test level (centre of the valid range), tt 27 °C",
    "ron_wc": "Worst on-resistance over the valid range and all 15 PVT points",
    "drop": "I_max·R_on (worst PVT, over the valid range) as a fraction of VDD; grades A ≤ 2 %, B ≤ 5 % (target), C ≤ 10 %, D ≤ 20 %",
    "leak_wc": "Worst off-leakage over every (in, out) pair in the valid range, 15 PVT points",
    "t_on": "ck 50 % → 90 % of the load current, tt 27 °C, input at the test level, resistive load at I_max",
    "t_off": "ck 50 % → 10 % of the load current, tt 27 °C",
    "e_vdd": "Charge from VDD over one full on/off cycle × VDD (drivers, bootstrap / pump)",
    "q_vtest": "Injected charge (pedestal × C_H) at the test level, tt 27 °C (signed)",
    "q_absmax": "Largest |injected charge| over 7 levels across the valid range",
    "thd": "Tracking THD for a 1 MHz sine over 90 % of the valid range into the I_max load",
    "stress": "Largest sustained (≥ 1 ns) gate-to-channel / drain-source voltage of any device as a fraction of its oxide rating",
    "area": "Layout property of the drawn cell (identical at every stage); only for the cards whose complete cell is drawn — "
            "multi-bank cells are drawn as one unit bank and their full-cell area is only estimated",
}


def stage_result(m, c, note):
    mm = {}
    for key, _l, _u, _s, _d, _b, field, scale in METRICS:
        v = m.get(field)
        mm[key] = None if v is None else v * scale
    if not LAY[c["key"]]["complete"]:
        mm.pop("area")  # full-cell area of a multi-bank cell is a formula estimate (only one unit bank is drawn): not a result
    ok = robust(m, c["imax"])
    r = {"metrics": mm, "robust": ok, "note": f"{note}; valid {range_txt(m.get('valid'))}; R_on grade {m.get('grade') or 'below D'}"}
    # 15 PVT points: R_on (sizing target) and leakage are checked at the worst of the 15 points, so all pass iff the worst does
    if m.get("ron_wc") is not None and m["ron_wc"] <= m["rt"] * 1.001 and m.get("leak_wc") is not None and m["leak_wc"] <= LEAKF * c["imax"] * 1.001:
        r["pvt"] = {"pass": 15, "total": 15}
    return r


# ============================================================================= drawn layout vs reported cell
# The generator draws, verifies (DRC/LVS) and extracts one *unit bank* when the switch is wider than its physical bank
# limit; the reported layout width/height/area of such a cell are a formula estimate for the full multi-bank cell, and
# its post-PEX netlist is the unit-bank extraction with devices multiplied to the full width and parasitic C scaled.
# Detect it from docs/ alone: the published GDS's drawn bounding box differs from the reported cell size.
LAY = {}
for _c in CARDS:
    if _c["status"]["sim"] != "done":
        continue
    _k, _m = _c["key"], _c["m"]
    _g = docs / "designs" / _k / f"{_k}.gds.gz"
    _bb = gds_bbox(_g) if _g.is_file() else None
    _ok = bool(_bb and _m.get("layout_w") and abs(_bb[0] - _m["layout_w"]) < 0.5 and abs(_bb[1] - _m["layout_h"]) < 0.5)
    LAY[_k] = {"drawn": _bb, "complete": _ok}
POST_STAGE = {k: "full" if v["complete"] else "partial" for k, v in LAY.items()}
N_COMPLETE = sum(1 for v in LAY.values() if v["complete"])
N_UNIT = len(LAY) - N_COMPLETE


def est(c):
    """True when the card's reported layout area is the generator's multi-bank estimate"""
    return not LAY.get(c["key"], {}).get("complete", True)


def area_lbl(c, a):
    return f"≈ {area(a)}" if est(c) and a else area(a)


def drawn_txt(c):
    bb = LAY[c["key"]]["drawn"]
    return f"{fx(bb[0], 1)} × {fx(bb[1], 1)} µm = {area(bb[0] * bb[1])}" if bb else "—"


SCALE = ("devices multiplied by m-factors to the full width, extracted parasitic C × (1 + 0.22·(W/W<sub>drawn</sub> − 1)) (generator heuristic), MIM capacitors set to the full-cell area")
MIXED_NOTE = (f"Post-PEX values: {N_COMPLETE} cards are extractions of the complete drawn cell (full post-PEX), the other {N_UNIT} are "
              "extractions of the drawn unit bank scaled to the full switch width (partial post-PEX); layout areas marked ≈ are the "
              "generator's estimate for the full multi-bank cell, which is not drawn.")


# ============================================================================= design detail documents
def stats_keyres(d, view):
    c = d["card"]
    if view == "post":
        m = {**pick(c["m"], DESIGN_KEYS), **pick(d["char"]["metrics"], DESIGN_KEYS), **d["post"]["metrics"], **pick(c["mp"], ["drop", "grade"])}
        ch = m
    else:
        m, ch = mv(c, "pre"), d["char"]["metrics"]
    L = d.get("layout")
    tr, tf = m.get("t_on_range") or [None, None], m.get("t_off_range") or [None, None]
    items = [
        ("On-resistance @ test level", si(m.get("ron_vtest"), "Ω"),
         f"min {si(m.get('ron_min'), 'Ω')} · max {si(m.get('ron_max'), 'Ω')} over the range · worst PVT {si(m.get('ron_wc'), 'Ω')}"),
        ("R<sub>on</sub> grade", grade_txt(m),
         "I<sub>max</sub>·R<sub>on</sub> worst PVT over the valid range; points " + " · ".join(f"{g} {si(f * c['vdd'] / c['imax'], 'Ω')}" for g, f in GRADES)),
        ("Valid signal range", range_txt(m.get("valid")), f"{fx(100 * m['coverage'], 0)} % of VDD · test level {fx(m.get('vtest'), 2)} V"),
        ("Off-resistance (worst PVT)", si(m.get("roff_wc"), "Ω"), f"leakage {si(m.get('leak_wc'), 'A')} worst · {si(m.get('leak_tt'), 'A')} tt"),
        ("Turn-on / turn-off time", f"{si(m.get('t_on'), 's')} / {si(m.get('t_off'), 's')}",
         f"PVT {si(tr[0], 's')}…{si(tr[1], 's')} / {si(tf[0], 's')}…{si(tf[1], 's')}"),
        ("Switching energy per cycle", si(m.get("e_vdd"), "J"), f"from VDD; {si(m.get('e_in'), 'J')} from the input source"),
        ("Charge injection @ test level", si(m.get("q_vtest"), "C"), f"max |Q| {si(m.get('q_absmax'), 'C')} over the range · C<sub>H</sub> {si(ch.get('ch'), 'F')}"),
        ("Off-isolation", f"{fx(m.get('iso_10m'), 0)} dB @ 10 MHz", f"{fx(m.get('iso_1m'), 0)} dB @ 1 MHz · C<sub>off</sub> {si(m.get('coff'), 'F')}"),
        ("Tracking THD (1 MHz)", f"{fx(m.get('thd_db'), 1)} dB", f"40 % amplitude: {fx(m.get('thd_small_db'), 1)} dB · R<sub>on</sub> flatness {fx(m.get('ron_flat'), 2)}"),
        ("Figure of merit R<sub>on</sub>·C<sub>off</sub>", si(m["ron_coff_fs"] * 1e-15 if m.get("ron_coff_fs") is not None else None, "s"), ""),
    ]
    if m.get("vgs_on") is not None:
        items.append(("On-state gate drive", f"{fx(m['vgs_on'], 2)} V", "V<sub>gate</sub> − V<sub>in</sub> at the test level"))
    if est(c):
        items.append(("Area (estimated)", area_lbl(c, m.get("area_um2")),
                      f"multi-bank estimate {fx(L['width_um'], 1)} × {fx(L['height_um'], 1)} µm · {L['naux']} auxiliary slice{'s' if L['naux'] > 1 else ''}; "
                      f"drawn unit bank {drawn_txt(c)}"))
    else:
        items.append(("Area", area(m["area_um2"]) if m.get("area_um2") else "layout pending",
                      f"{fx(L['width_um'], 1)} × {fx(L['height_um'], 1)} µm · {L['naux']} auxiliary slice{'s' if L['naux'] > 1 else ''}" if L
                      else f"devices {area(m.get('act_um2'))} + MIM {area(m.get('mim_um2'))}"))
    return m, {"type": "stats", "stage": STAGE_OF[view], "alt": "keyres",
               "items": [{"label": l, "value": v, **({"sub": s} if s else {})} for l, v, s in items]}


def spec_table(d, m, view):
    c, rows = d["card"], []
    rows.append(["R_on ≤ target over the valid range (worst PVT)", f"{si(m.get('ron_wc'), 'Ω')} ≤ {si(m['rt'], 'Ω')}",
                 m.get("ron_wc") is not None and m["ron_wc"] <= m["rt"] * 1.001])
    if m.get("drop") is not None:
        rows.append(["R_on point reached (A ≤ 2 %, B ≤ 5 %, C ≤ 10 %, D ≤ 20 % VDD)", grade_txt(m), m.get("grade") is not None])
    rows.append(["Valid signal range (on-range ∩ off-range)", range_txt(m.get("valid")), (m.get("coverage") or 0) > 0])
    rows.append([f"Off leakage ≤ {jsnum(100 * LEAKF, 6)} % of I_max (worst PVT, any in/out pair in range)", si(m.get("leak_wc"), "A"),
                 m.get("leak_wc") is not None and m["leak_wc"] <= LEAKF * c["imax"] * 1.001])
    rows.append(["Device stress ≤ oxide rating (sustained ≥ 1 ns)",
                 f"{fx(100 * m['stress_ratio'], 0)} % of rating (peak {fx(100 * m['stress_peak_ratio'], 0)} %)", bool(m.get("stress_ok"))])
    V, L = d.get("verify"), d.get("layout")
    if V:
        unit = " — drawn unit bank" if est(c) else ""
        rows.append([f"DRC clean (PDK KLayout deck){unit}", "0 violations" if V["drc"]["clean"] else json.dumps(V["drc"]["violations"]), bool(V["drc"]["clean"])])
        rows.append([f"LVS match (PDK KLayout deck){unit}", "netlists match" if V["lvs"]["match"] else "mismatch", bool(V["lvs"]["match"])])
    if L and L.get("em"):
        rows.append(["EM: DC current density in the met3 S/D stripes ≤ 1 mA/µm",
                     ", ".join(f"{e['dev']} {fx(e['j_stripe_ma_per_um'], 2)} mA/µm" for e in L["em"]), all(e["ok"] for e in L["em"])])
    return {"type": "table", "title": "Specification checks", "stage": STAGE_OF[view], "alt": "spec", "csv": False, "search": False,
            "columns": [{"key": "r", "label": "Result", "type": "text"}, {"key": "k", "label": "Check", "type": "text", "wrap": True},
                        {"key": "v", "label": "Value", "type": "text", "wrap": True}],
            "rows": [{"k": k, "v": v, "r": {"v": "pass" if ok else "fail", "s": "good" if ok else "bad"}} for k, v, ok in rows]}


KNOB_NAME = {"rp": "P/N width ratio W_p/W_n", "kcb": "C_B (pump) / switch gate capacitance",
             "f_dum": "Dummy size / switch size (f_dum)", "f_shunt": "Shunt size / switch size (f_shunt)"}


def overview_blocks(d, key):
    c = d["card"]
    unit = (f" **Partial extraction:** only one unit bank of this cell is drawn ({drawn_txt(c)}); its Magic extraction was scaled by the "
            f"generator to the full switch width ({SCALE}), so these post-PEX results are *partial post-PEX*.") if est(c) else ""
    blocks = [{"type": "note", "stage": STAGE_OF["post"], "tone": "info",
               "text": "**Post-PEX view:** every result below is from the extracted layout netlist (R<sub>on</sub>, range, leakage, timing and "
                       "energy over PVT, charge injection, isolation, THD, device stress); only the design data (sizing, test conditions) "
                       "and the layout area are shared with the schematic view." + unit}]
    notes = "\n\n".join(f"<small>{n}</small>" for n in d["circuit"].get("notes") or [])
    blocks.append({"type": "section", "title": "Topology", "blocks": [{"type": "markdown", "text": f"{DESC[c['topo']]}\n\n{notes}"}]})
    keyres, specs = [], []
    for view in ("pre", "post"):
        m, st = stats_keyres(d, view)
        keyres.append(st)
        specs.append(spec_table(d, m, view))
    blocks.append({"type": "section", "title": "Key results (tt, 27 °C unless noted)", "blocks": keyres})
    m = c["m"]
    dp = [["Main switch width W<sub>s</sub>", f"{fx(m['ws'] / 1000, 3)} mm" if m["ws"] >= 1000 else f"{fx(m['ws'], 2)} µm"]]
    dp += [[KNOB_NAME.get(k, k), jsnum(v, 6)] for k, v in (c.get("knobs") or {}).items()]
    dp += [["Auxiliary slices (parallel copies)", str(m.get("naux") or 1)], ["R<sub>on</sub> target (5 % VDD / I<sub>max</sub>)", si(m["rt"], "Ω")]]
    right = [{"type": "kv", "title": "Design point", "cols": 1, "items": dp}]
    alts = d["design"].get("alternatives") or []
    if len(alts) > 1:
        right.append({
            "type": "table", "title": "Knob exploration", "csv": False, "search": False,
            "caption": "Sized from the reference characterisation (W<sub>s</sub> = 100 µm, 15 PVT points). Chosen (highlighted): smallest "
                       "estimated area among the knobs reaching ≥ 97 % of the best range. *Area est.* is the generator's pre-layout estimate, "
                       "not a layout result.",
            "columns": [{"key": "k", "label": "Knob", "type": "text"}, {"key": "ws", "label": "W<sub>s</sub>", "type": "text", "align": "r"},
                        {"key": "cov", "label": "Range", "unit": "%", "digits": 3}, {"key": "a", "label": "Area est.", "unit": "µm²", "digits": 4},
                        {"key": "ch", "label": "Chosen", "type": "text"}],
            "rows": [dict(k=", ".join(f"{a}={jsnum(b, 6)}" for a, b in x["knobs"].items()) or "—", ws=f"{fx(x['ws'] / 1000, 2)} mm" if x["ws"] >= 1000 else f"{fx(x['ws'], 1)} µm", cov=100 * x["coverage"],
                          a=x["area_est"], ch="✓" if x["knobs"] == c["knobs"] else "",
                          **({"_s": "good"} if x["knobs"] == c["knobs"] else {})) for x in alts]})
    right.append({"type": "downloads", "items": [{"label": "netlist.spice", "file": f"designs/{key}/netlist.spice", "note": "simulation netlist"}]})
    blocks.append({"type": "section", "cols": 2, "blocks": [{"type": "section", "blocks": specs}, {"type": "section", "blocks": right}]})
    return blocks


def schematic_blocks(d, key):
    circ = d["circuit"]
    naux = circ.get("naux") or 1
    base = ("Each transistor shows its model, W · L · fingers and **gm/I<sub>D</sub> target → simulated** (1/V): the target is the LUT "
            "inversion level at the device's intended on-state bias (e.g. V<sub>GS</sub> = VDD for an ideal bootstrap), the simulated value "
            "is the LUT evaluated at the V<sub>GS</sub>/V<sub>SB</sub> the timing bench actually produced in the device's conducting phase — "
            "a bootstrap that loses gate drive to charge sharing shows up as a higher gm/I<sub>D</sub>. Colour: green weak, blue moderate, "
            "orange strong inversion. Click the figure to open it full size; the device table below lists every operating point.")
    post = (" **Post-PEX view:** simulated values are from the extracted netlist — each schematic device is matched to its extracted "
            "device(s) (switch arrays by cell, auxiliary devices by size and connectivity); a device whose match is ambiguous shows “—”.")
    tail = f" Auxiliary devices are drawn once; the cell contains {naux} parallel slices." if naux > 1 else ""
    blocks = [
        {"type": "image", "stage": "pre", "alt": "schem", "title": "Schematic with gm/I<sub>D</sub> annotation", "src": f"designs/{key}/schematic.svg",
         "bg": "dark", "max_height": 900, "caption": base + tail},
        {"type": "image", "stage": STAGE_OF["post"], "alt": "schem", "title": "Schematic with gm/I<sub>D</sub> annotation", "src": f"designs/{key}/schematic_post.svg",
         "bg": "dark", "max_height": 900, "caption": base + post + tail},
    ]
    reg = lambda g: "" if g is None else "WI" if g >= 18 else "MI" if g >= 8 else "SI"  # noqa: E731
    rs = {"WI": "good", "MI": "muted", "SI": "warn"}
    cols = [{"key": "dev", "label": "Dev", "type": "text"}, {"key": "model", "label": "Model", "type": "text"},
            {"key": "role", "label": "Role", "type": "text"}, {"key": "W", "label": "W (µm)", "digits": 5},
            {"key": "L", "label": "L (µm)", "digits": 3}, {"key": "nf", "label": "nf", "digits": 5},
            {"key": "gt", "label": "gm/Id target (1/V)", "digits": 3}, {"key": "gs", "label": "gm/Id sim (1/V)", "digits": 3},
            {"key": "vgs", "label": "V<sub>GS</sub> (V)", "digits": 4}, {"key": "vsb", "label": "V<sub>SB</sub> (V)", "digits": 4},
            {"key": "inv", "label": "Inv.", "type": "text", "title": "inversion level of gm/Id sim: WI ≥ 18, MI ≥ 8, SI < 8 (1/V)"},
            {"key": "st", "label": "stress ox / ds (V)", "type": "text"}, {"key": "rating", "label": "rating (V)", "digits": 3},
            {"key": "nodes", "label": "D/G/S/B", "type": "text"}]
    for view, src in (("pre", d["char"]), ("post", d["post"])):
        op, stv = (src or {}).get("op") or {}, (src or {}).get("stress") or {}
        rows = []
        for v in circ["devs"]:
            s, x = op.get(v["name"]) or {}, stv.get(v["name"]) or {}
            r = reg(s.get("gm_id"))
            rows.append({"dev": v["name"] + (f" ×{naux}" if v.get("aux") and naux > 1 else ""), "model": v["model"], "role": v["role"],
                         "W": v["W"], "L": v["L"], "nf": v["nf"], "gt": v.get("gmid"), "gs": s.get("gm_id"), "vgs": s.get("vgs"), "vsb": s.get("vsb"),
                         "inv": {"v": r, "s": rs[r]} if r else None,
                         "st": f"{fx(x['vox_sus'], 2)} / {fx(x['vds_sus'], 2)}" if x.get("vox_sus") is not None else None,
                         "rating": x.get("rating"), "nodes": f"{v['d']}/{v['g']}/{v['s']}/{v['b']}"})
        blocks.append({"type": "table", "stage": STAGE_OF[view], "alt": "devs",
                       "title": f"Devices (on-state operating point, tt 27 °C{', extracted netlist' if view == 'post' else ''})",
                       "columns": cols, "rows": rows, "search": False,
                       "caption": "×N: auxiliary device replicated in N parallel slices. stress ox / ds: largest sustained (≥ 1 ns) gate-to-channel / "
                                  "drain-source voltage in the timing bench."})
    caps = circ.get("caps") or []
    if caps:
        blocks.append({"type": "table", "title": "Capacitors", "search": False, "csv": False,
                       "columns": [{"key": "n", "label": "Name", "type": "text"}, {"key": "dev", "label": "Device", "type": "text"},
                                   {"key": "size", "label": "Size", "type": "text"}, {"key": "c", "label": "Value", "unit": "F", "si": True},
                                   {"key": "nodes", "label": "Nodes", "type": "text"}],
                       "rows": [{"n": cp["name"] + (f" ×{naux}" if naux > 1 else ""), "dev": "MIM cap_mim_2f0_m4m5_noshield",
                                 "size": f"{cp.get('blocks') or 1} × {cp['units']} × {fx(cp['side'], 1)}² µm", "c": cp["Cact"],
                                 "nodes": f"{cp['p']} – {cp['n']}"} for cp in caps]})
    return blocks


def clip(a):
    return [None if v is None or v > 1e9 else v for v in a]


def sim_charts(d, view):
    """port of app.js tabSim for one netlist; returns chart blocks (stage-tagged)"""
    post = view == "post"
    c = d["card"]
    src = d["post"] if post else d["char"]
    ch = dict(src, metrics={**pick(d["char"]["metrics"], DESIGN_KEYS), **d["post"]["metrics"]}) if post else d["char"]
    alt = d["char"] if post else d["post"]
    m, vdd, st = ch["metrics"], c["vdd"], STAGE_OF[view]
    out = []
    R, vin = ch["ron"], ch["ron"]["vin"]
    tr = [{"x": vin, "y": clip(p["r"]), "name": f"{p['c']} {p['t']}°C", "mode": "lines", "line": {"width": 1, "color": GREY}, "showlegend": False,
           "hovertemplate": f"{p['c']} {p['t']}°C: %{{y:.3s}}Ω<extra></extra>"} for p in R["pvt"]]
    tr.append({"x": vin, "y": clip(R["tt"]), "name": "tt 27 °C", "mode": "lines", "line": {"width": 2, "color": S1}, "hovertemplate": "tt: %{y:.3s}Ω<extra></extra>"})
    tr.append({"x": vin, "y": clip(R["env"]), "name": "worst PVT", "mode": "lines", "line": {"width": 2, "color": S2, "dash": "dash"},
               "hovertemplate": "worst: %{y:.3s}Ω<extra></extra>"})
    if alt and alt.get("ron"):
        tr.append({"x": alt["ron"]["vin"], "y": clip(alt["ron"]["tt"]), "name": "tt (schematic)" if post else "tt (post-PEX)", "mode": "lines",
                   "line": {"dash": "dot", "width": 1.5, "color": S3}, "hovertemplate": "%{y:.3s}Ω<extra></extra>"})
    finite = [v for v in R["tt"] if v is not None and v < 1e9]
    ymin, ymax = min(finite) * 0.7, max(m["rt"] * 6, min(finite) * 20)
    shapes = [{"type": "line", "x0": 0, "x1": vdd, "y0": m["rt"], "y1": m["rt"], "line": {"color": BAD, "width": 1.5, "dash": "dot"}}]
    shapes += [{"type": "line", "x0": 0, "x1": vdd, "y0": m["rt"] * f / DROP, "y1": m["rt"] * f / DROP, "line": {"color": GREY, "width": 1, "dash": "dot"}}
               for _g, f in GRADES if f != DROP]
    shapes += [{"type": "rect", "xref": "x", "yref": "paper", "x0": a, "x1": b, "y0": 0, "y1": 1, "fillcolor": GOOD, "opacity": 0.08, "line": {"width": 0}}
               for a, b in (m.get("valid") or [])]
    out.append({"type": "chart", "stage": st, "alt": "ron", "title": "On-resistance vs input level (15 PVT points)", "height": 420,
                "caption": f"target {si(m['rt'], 'Ω')} (red; grey: R<sub>on</sub> points A, C, D) · valid {range_txt(m.get('valid'))} · "
                           f"tt {si(m.get('ron_min'), 'Ω')}…{si(m.get('ron_max'), 'Ω')} · grey curves: the 15 PVT points · green band: valid range",
                "data": tr, "layout": {"xaxis": {"title": {"text": "input level (V)"}, "range": [0, vdd]},
                                       "yaxis": {"type": "log", "title": {"text": "R_on (Ω)"}, "range": [math.log10(ymin), math.log10(ymax)]},
                                       "hovermode": "closest", "shapes": shapes}})
    L = ch["leak"]
    lt = [{"x": L["vin"], "y": [max(v, 1e-18) for v in p["i"]], "name": f"{p['c']} {p['t']}°C", "mode": "lines",
           "line": {"width": 1.6 if p["t"] == 125 else 1, "color": S2 if p["t"] == 125 else S1 if p["t"] == 27 else GREY}, "showlegend": False,
           "hovertemplate": f"{p['c']} {p['t']}°C: %{{y:.3s}}A<extra></extra>"} for p in L["pvt"]]
    lim = LEAKF * c["imax"]
    out.append({"type": "chart", "stage": st, "alt": "leak", "title": "Off leakage vs input level (worst output level)", "height": 420,
                "caption": f"limit {si(lim, 'A')} · worst in range {si(m.get('leak_wc'), 'A')} · orange: 125 °C, blue: 27 °C, grey: −40 °C (5 corners each)",
                "data": lt, "layout": {"xaxis": {"title": {"text": "input level (V)"}}, "yaxis": {"type": "log", "title": {"text": "leakage (A)"}, "exponentformat": "SI"},
                                       "hovermode": "closest", "shapes": [{"type": "line", "x0": 0, "x1": vdd, "y0": lim, "y1": lim, "line": {"color": BAD, "width": 1.5, "dash": "dot"}}]}})
    waves = {
        "won": ("wave_on", "Turn-on edge (tt, resistive load at I<sub>max</sub>)",
                f"t<sub>on</sub> {si(m.get('t_on'), 's')} (ck 50 % → 90 % load current) · gate delay {si(m.get('t_gate'), 's')} · input {fx(m.get('vtest'), 2)} V"),
        "woff": ("wave_off", "Turn-off edge", f"t<sub>off</sub> {si(m.get('t_off'), 's')} (ck 50 % → 10 % load current)"),
        "wave": ("wave", "Full on/off cycle", f"phase length {si(m.get('T'), 's')} · on-state gate {fx(m.get('v_gate_on'), 2)} V"),
    }
    for alt_key, (wk, title, cap) in waves.items():
        W = ch.get(wk)
        if not W or not W.get("t"):
            continue
        tt = [x * 1e9 for x in W["t"]]
        trs = [{"x": tt, "y": W["ck"], "name": "ck", "mode": "lines", "line": {"width": 1.5, "color": S3}}]
        if W.get("gate"):
            trs.append({"x": tt, "y": W["gate"], "name": "switch gate", "mode": "lines", "line": {"width": 2, "color": S2}})
        trs.append({"x": tt, "y": W["vout"], "name": "output", "mode": "lines", "line": {"width": 2, "color": S1}})
        out.append({"type": "chart", "stage": st, "alt": alt_key, "title": title, "caption": cap, "data": trs,
                    "layout": {"xaxis": {"title": {"text": "time (ns)"}}, "yaxis": {"title": {"text": "V"}}, "hovermode": "x unified"}})
    if ch.get("qinj"):
        Q = ch["qinj"]
        out.append({"type": "chart", "stage": st, "alt": "q", "title": "Charge injection vs input level",
                    "caption": f"C<sub>H</sub> = {si(Q.get('ch'), 'F')} · pedestal max {si(m.get('ped_absmax'), 'V')}",
                    "data": [{"x": Q["vin"], "y": [v * 1e15 for v in Q["q"]], "name": "Q_inj", "mode": "lines+markers", "line": {"width": 2, "color": S1},
                              "marker": {"color": S1}, "hovertemplate": "%{y:.3g} fC<extra></extra>"}],
                    "layout": {"xaxis": {"title": {"text": "input level (V)"}, "range": [0, vdd]}, "yaxis": {"title": {"text": "injected charge (fC)"}},
                               "showlegend": False, "hovermode": "closest"}})
    if ch.get("ac"):
        out.append({"type": "chart", "stage": st, "alt": "iso", "title": "Off-isolation (resistive load)",
                    "caption": f"{fx(m.get('iso_1m'), 0)} dB @ 1 MHz · {fx(m.get('iso_10m'), 0)} dB @ 10 MHz · {fx(m.get('iso_100m'), 0)} dB @ 100 MHz",
                    "data": [{"x": ch["ac"]["f"], "y": ch["ac"]["iso_db"], "name": "isolation", "mode": "lines", "line": {"width": 2, "color": S1},
                              "hovertemplate": "%{y:.1f} dB<extra></extra>"}],
                    "layout": {"xaxis": {"type": "log", "title": {"text": "frequency (Hz)"}, "exponentformat": "SI"},
                               "yaxis": {"title": {"text": "|V_out/V_in| (dB)"}}, "showlegend": False}})
    if ch.get("thd"):
        t = ch["thd"][0]
        out.append({"type": "chart", "stage": st, "alt": "thd", "title": "Tracking distortion (1 MHz)",
                    "caption": " · ".join(f"{fx(x['amp'], 2)} V pk: THD {fx(x['thd_db'], 1)} dB" for x in ch["thd"]) + f" · bars: harmonics of the {fx(t['amp'], 2)} V pk tone",
                    "data": [{"type": "bar", "x": [f"H{k + 1}" for k in range(1, len(t["spec_db"]))], "y": [v + 160 for v in t["spec_db"][1:]], "base": -160,
                              "customdata": t["spec_db"][1:], "marker": {"color": S1}, "hovertemplate": "%{x}: %{customdata:.1f} dBc<extra></extra>"}],
                    "layout": {"yaxis": {"title": {"text": "dBc"}, "range": [-160, 0]}, "showlegend": False, "hovermode": "closest"}})
    # PVT tables (corner rows x temperature columns), app.js pvtTable
    corners = list(dict.fromkeys(p["corner"] for p in ch["timing"]))
    temps = list(dict.fromkeys(p["temp"] for p in ch["timing"]))
    tcols = [{"key": "corner", "label": "Corner", "type": "text"}]
    for T in temps:
        for k, lab, u in (("t_on", "t<sub>on</sub>", "s"), ("t_off", "t<sub>off</sub>", "s"), ("e_vdd", "E", "J")):
            tcols.append({"key": f"{k}_{T}", "label": lab, "unit": u, "si": True, "group": f"{T} °C"})
    trows = []
    for co in corners:
        r = {"corner": co}
        for p in ch["timing"]:
            if p["corner"] == co:
                for k in ("t_on", "t_off", "e_vdd"):
                    r[f"{k}_{p['temp']}"] = p[k]
        trows.append(r)
    qcorners = list(dict.fromkeys(p["corner"] for p in ch["qinj_pvt"]))
    qtemps = list(dict.fromkeys(p["temp"] for p in ch["qinj_pvt"]))
    qrows = [{"corner": co, **{f"q_{p['temp']}": p["q"] for p in ch["qinj_pvt"] if p["corner"] == co}} for co in qcorners]
    tabs = [
        {"type": "table", "stage": st, "alt": "tpvt", "title": "Timing and energy over PVT", "columns": tcols, "rows": trows, "search": False,
         "caption": "Per cell: t<sub>on</sub>, t<sub>off</sub>, E (switching energy per cycle from VDD); input at the test level, I<sub>max</sub> load."},
        {"type": "table", "stage": st, "alt": "qpvt", "title": "Charge injection over PVT (test level)", "search": False,
         "columns": [{"key": "corner", "label": "Corner", "type": "text"}] + [{"key": f"q_{T}", "label": f"Q<sub>inj</sub> {T} °C", "unit": "C", "si": True} for T in qtemps],
         "rows": qrows},
    ]
    return out, tabs


def simulation_blocks(d):
    V = d.get("verify") or {}
    px = V.get("pex") or {}
    rp = px.get("r_path") or {}
    c = d["card"]
    what = (f"of the drawn unit bank ({drawn_txt(c)}), scaled by the generator to the full switch width ({SCALE}) — **partial post-PEX**"
            if est(c) else "of the complete verified cell — **full post-PEX**")
    note = (f"Post-PEX: Magic extraction {what} (hierarchical, {px.get('n_c', 0):,} parasitic capacitances ≥ 0.01 fF, MIM and junction "
            f"geometry) plus an estimated series resistance of the met3 source/drain stripes (formula on the stripe geometry; in "
            f"{si(rp.get('in') or 0, 'Ω')}, out {si(rp.get('out') or 0, 'Ω')}) added at the IN/OUT pins; "
            "same benches and test conditions as the schematic results. Dotted R<sub>on</sub> curve: the schematic.")
    if px.get("coupling") is False:
        note += (" **Reduced extraction:** the full extraction of this cell exceeds the 30-min run limit, so coupling capacitance between nets is omitted "
                 "(devices and capacitance to substrate only).")
    charts, tables = [], []
    for view in ("pre", "post"):
        c_, t_ = sim_charts(d, view)
        charts += c_
        tables += t_
    # interleave so both stage variants sit next to each other (renderer picks one per alt)
    order = ["ron", "leak", "won", "woff", "wave", "q", "iso", "thd"]
    charts.sort(key=lambda b: order.index(b["alt"]))
    tables.sort(key=lambda b: b["alt"])
    return [{"type": "note", "stage": STAGE_OF["post"], "alt": "simnote", "tone": "info", "text": note},
            {"type": "note", "stage": "pre", "alt": "simnote", "tone": "muted", "text": "Schematic (pre-PEX) netlist, Cadence Spectre. Dotted R<sub>on</sub> curve: the extracted (post-PEX) netlist for comparison."},
            {"type": "section", "cols": 2, "blocks": charts},
            {"type": "section", "cols": 2, "blocks": [b for b in tables if b["alt"] == "tpvt"] + [b for b in tables if b["alt"] == "qpvt"]}]


def layout_blocks(d, key):
    c, L, V = d["card"], d.get("layout"), d.get("verify")
    if not L:
        if c["status"]["layout"] == "timeout":
            return [{"type": "note", "tone": "warn", "text": (
                f"Layout not delivered: generating and verifying this cell exceeded the 30-minute limit per run. It needs {si(c['m']['ws'] * 1e-6, 'm')} of switch "
                f"width ({c['short']} at {c['vdd']} V for {si(c['imax'], 'A')}); the cell would be several mm². Its area estimate (device + MIM) is "
                f"{area(c['m'].get('act_um2'))} + {area(c['m'].get('mim_um2'))}.")}]
        return [{"type": "note", "tone": "muted", "text": "Layout not ready yet."}]
    to = c["status"]["layout"] == "timeout"
    kv = []
    if V:
        kv.append({"label": "DRC (PDK KLayout deck, variant D)", "value": "clean" if V["drc"]["clean"] else json.dumps(V["drc"]["violations"]), "s": "good" if V["drc"]["clean"] else "bad"})
        kv.append({"label": "LVS (PDK KLayout deck)", "value": "match" if V["lvs"]["match"] else "mismatch", "s": "good" if V["lvs"]["match"] else "bad"})
    else:
        kv.append({"label": "DRC / LVS", "value": "not completed within the 30-min limit" if to else "pending", "s": "warn"})
    asp = L.get("aspect") or min(L["width_um"], L["height_um"]) / max(L["width_um"], L["height_um"])
    grid = L.get("aux_grid")
    grid_txt = f", {grid[0]} × {grid[1]} grid" if grid and L["naux"] > 1 else ""
    if est(c):
        kv.append({"label": "Drawn GDS (unit bank)", "value": drawn_txt(c), "s": "warn"})
    kv += [{"label": "Cell size (estimated, multi-bank)" if est(c) else "Cell size",
            "value": f"{fx(L['width_um'], 1)} × {fx(L['height_um'], 1)} µm = {area(L['area_um2'])}"},
           {"label": "Aspect ratio", "value": fx(asp, 2)},
           {"label": "Switch banks", "value": f"switch folded into {L['banks']} banks" if L.get("banks", 1) > 1 else "1"},
           {"label": "Auxiliary slices", "value": f"{L['naux']} ({fx(L['aux']['width_um'], 0)} × {fx(L['aux']['height_um'], 0)} µm each{grid_txt})"}]
    px = (V or {}).get("pex") or {}
    if px:
        rp = px.get("r_path") or {}
        kv += [{"label": "PEX (Magic)", "value": "ok" if px.get("ok") else "failed", "s": "good" if px.get("ok") else "bad"},
               {"label": "Extracted parasitic capacitances (≥ 0.01 fF)", "value": f"{px.get('n_c', 0):,}"},
               {"label": "Coupling capacitance", "value": "extracted" if px.get("coupling") is not False else "omitted (reduced extraction)"},
               {"label": "Series stripe R added at IN / OUT (estimated, formula)", "value": f"{si(rp.get('in') or 0, 'Ω')} / {si(rp.get('out') or 0, 'Ω')}"},
               {"label": "Missing ports", "value": ", ".join(px.get("missing_ports") or []) or "none"}]
    blocks = []
    if est(c):
        blocks.append({"type": "note", "tone": "warn", "title": "Unit-bank layout.",
                       "text": f"The published GDS contains one unit bank of this switch ({drawn_txt(c)}). The cell size, bank count and auxiliary-slice "
                               f"grid below ({fx(L['width_um'], 1)} × {fx(L['height_um'], 1)} µm, {L.get('banks', 1)} banks, {L['naux']} slices) are the "
                               "generator's estimate for the full multi-bank cell, which is not drawn; DRC, LVS and the Magic extraction were run on the "
                               "unit bank (the post-PEX netlist is scaled to the full width, see the Simulation tab)."})
    blocks += [{"type": "layout", "title": "Layout (gLayout primitives, GF180MCU-D)" + (" — drawn unit bank" if est(c) else ""),
                "gds": f"designs/{key}/{key}.gds.gz", "max_height": 720,
                "caption": "Rendered from the GDS by the hub (click to open the raw GDS in the repository)."},
               {"type": "kv", "cols": 2, "items": kv}]
    rt = c["m"]["rt"]
    rows = []
    for a in L.get("arrays") or []:
        rm = 2 * 0.09 * a["h"] / (3 * a["stripe_w"]) / max(1, a["stripes"] / 2)
        rows.append({"dev": a["dev"], "rows": a["rows"], "fpr": a["fingers_per_row"], "stripes": a["stripes"], "sw": a["stripe_w"],
                     "size": f"{fx(a['w'], 1)} × {fx(a['h'], 1)} µm", "rm": rm, "pct": 100 * rm / rt})
    blocks.append({"type": "table", "title": "Switch arrays", "search": False,
                   "columns": [{"key": "dev", "label": "Switch array", "type": "text"}, {"key": "rows", "label": "rows"},
                               {"key": "fpr", "label": "fingers / row"}, {"key": "stripes", "label": "S/D stripes"},
                               {"key": "sw", "label": "stripe width", "unit": "µm", "digits": 3}, {"key": "size", "label": "size", "type": "text"},
                               {"key": "rm", "label": "stripe R (est.)", "unit": "Ω", "si": True}, {"key": "pct", "label": "% of R<sub>on</sub> target", "unit": "%", "digits": 3}],
                   "rows": rows,
                   "caption": "Stripe R: estimated series resistance of the met3 source + drain stripes (0.09 Ω/□, current collected uniformly along each "
                              "stripe → R/3 per stripe, stripes in parallel), per bank; not part of the schematic R<sub>on</sub>, added to the extracted "
                              "netlist at its IN/OUT pins for the post-PEX benches. *Estimate from the array geometry, not a simulation result.*"
                              + (" For this cell the array rows / stripes are the generator's plan for the full multi-bank cell (only one unit bank is drawn)."
                                 if est(c) else "")})
    em = L.get("em") or []
    txt = []
    if em:
        txt.append(f"EM (DC, I<sub>max</sub> = {si(c['imax'], 'A')} through one device): " + " · ".join(
            f"{e['dev']}: {e['stripes']} source stripes × {fx(e['stripe_w'], 2)} µm → {fx(e['j_stripe_ma_per_um'], 2)} mA/µm "
            f"{'✓' if e['ok'] else '✗ (above the 1 mA/µm met3 limit; stripe width is capped at 4 µm)'}" for e in em))
    txt.append("Floorplan: the switch devices are folded into K banks of finger rows stacked vertically (odd banks mirrored so neighbours share their "
               "VSS rail and spines), K chosen for a near-square cell. Inside a bank: the input spine, the switch array(s) — finger rows of gLayout "
               "`multiplier` cells inside a tap ring, interleaved met3 source/drain stripes sized for the DC current, gate stripes and body straps "
               "beside the ring — and the output spine (met4 + met5). The IN spines of all banks join a bar on the left, the OUT spines a bar on the "
               "right (the high-current pins); gate stripes and body straps run continuously through the stack. Above it: a jog band, a met4 track "
               "channel and the auxiliary slices (drivers, bootstrap / pump circuitry and MIM capacitors, placed by a row floorplanner and wired by a "
               "negotiated-congestion router on a 0.8 µm met3/met4 grid), arranged as a grid of mirrored row pairs around shared channels that are "
               "tied together outside the block. Side straps tie the bottom rails to the rails of the auxiliary rows. Verified with the PDK's KLayout "
               f"DRC (variant D) and LVS decks{' (DRC in deep mode)' if V and V['drc'].get('mode') == 'deep' else ''}.")
    blocks.append({"type": "markdown", "text": "\n\n".join(txt)})
    blocks.append({"type": "downloads", "items": [{"label": "GDS (.gz)", "file": f"designs/{key}/{key}.gds.gz"},
                                                  {"label": "LVS netlist", "file": f"designs/{key}/lvs_reference.spice"},
                                                  {"label": "Extracted (PEX) netlist", "file": f"designs/{key}/{key}.pex.spice"}]})
    return blocks


def detail_doc(d, key):
    return {"blocks": [{"type": "tabs", "id": "tab", "tabs": [
        {"label": "Overview", "blocks": overview_blocks(d, key)},
        {"label": "Schematic", "blocks": schematic_blocks(d, key)},
        {"label": "Simulation", "blocks": simulation_blocks(d)},
        {"label": "Layout", "blocks": layout_blocks(d, key)},
    ]}]}


# ============================================================================= design records
designs, na_cards = [], []
order = {t: i for i, t in enumerate(ORDER)}
icl_order = {k: i for i, k in enumerate(ICLS)}
CARDS_SORTED = sorted(CARDS, key=lambda c: (order.get(c["topo"], 99), c["vdd"], icl_order.get(c["iclass"], 99)))
for c in CARDS_SORTED:
    key, m, mp, st = c["key"], c.get("m") or {}, c.get("mp") or {}, c.get("status") or {}
    if st.get("sim") == "n/a" or not m:
        na_cards.append(c)
        nd = load(f"designs/{key}/data.json") if (docs / "designs" / key / "data.json").is_file() else {}
        designs.append({
            "id": key, "title": c["name"], "vdd": c["vdd"], "axes": {"topology": c["topo"], "class": c["iclass"]},
            "tags": list(c.get("tags") or []) + ["not applicable"], "na": c.get("reason") or "not applicable", "results": {},
            **({"files": {"data": f"designs/{key}/data.json"}} if nd else {}),
            "detail": write(f"designs/{key}.json", {"blocks": [
                {"type": "section", "title": "Topology", "blocks": [{"type": "markdown", "text": DESC[c["topo"]] + "".join(
                    f"\n\n<small>{n}</small>" for n in (nd.get("circuit") or {}).get("notes") or [] if n != c.get("reason"))}]}]}),
        })
        continue
    base = f"designs/{key}"
    d = load(f"{base}/data.json")
    verify, L = d.get("verify") or {}, d.get("layout") or {}
    STAGE_OF["post"] = POST_STAGE[key]
    unit = est(c)
    pex_txt = (docs / base / f"{key}.pex.spice").read_text() if (docs / base / f"{key}.pex.spice").is_file() else ""
    capfix = any(re.match(r"^C\S*\s+(ntop\s+vss|vss\s+ntop|vb\s+vss|vss\s+vb)\s", ln) for ln in pex_txt.splitlines())
    results = {"pre": stage_result(m, c, "Schematic netlist (Cadence Spectre), 15 PVT points (5 corners × 3 temperatures)")}
    if mp:
        if unit:
            note = (f"Magic extraction of the drawn unit bank only ({drawn_txt(c)}; the full multi-bank cell is not drawn), scaled by the generator "
                    "to the full switch width (devices multiplied by m-factors, extracted parasitic C × (1 + 0.22·(W/W_drawn − 1)) as a generator "
                    "heuristic, MIM caps set to the full-cell area), plus an estimated met3 stripe series R (formula) at IN/OUT; same benches, 15 PVT points")
        else:
            note = ("Magic extraction of the complete drawn cell (device geometry, parasitic C ≥ 0.01 fF incl. coupling) plus an estimated met3 "
                    "stripe series R (formula) at IN/OUT; same benches, 15 PVT points")
        if capfix:
            note += "; the generator scales the extracted ntop–vss / vb–vss capacitances by 0.25"
        results[POST_STAGE[key]] = stage_result(mp, c, note)
    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("gds", f"{key}.gds.gz"), ("netlist", "netlist.spice"), ("pex_netlist", f"{key}.pex.spice"),
        ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json")) if (docs / base / v).is_file()}
    images = [{"label": "Schematic (post-PEX operating points)", "src": f"{base}/schematic_post.svg"}] if (docs / base / "schematic_post.svg").is_file() else []
    pex = verify.get("pex") or {}
    tags = list(c.get("tags") or []) + [f"R_on grade {m.get('grade') or 'below D'}"]
    r2r_pre, r2r_post = (m.get("coverage") or 0) > 0.97, (mp.get("coverage") or 0) > 0.97
    tags += (["r2r-pre"] if r2r_pre else []) + (["r2r-post"] if r2r_post else [])   # rail-to-rail (> 97 % VDD) per netlist; not substrings
    if m.get("stress_ok") is False:
        tags.append("overstress")
    if m.get("em_ok") is False:
        tags.append("EM-limited")
    tags.append("unit-bank layout (physical area = drawn unit bank)" if unit else "complete layout")
    params = {"R_on target (5 % VDD / I_max)": si(m["rt"], "Ω"), "I_max (class maximum)": si(c["imax"], "A"),
              "Main switch width W_s": f"{fx(m['ws'] / 1000, 3)} mm" if m["ws"] >= 1000 else f"{fx(m['ws'], 2)} µm",
              "Test level (input)": f"{fx(m['vtest'], 3)} V", "Load R_L": si(m["rl"], "Ω"), "Hold cap C_H": si(m["ch"], "F"),
              "Switch gate capacitance": si(m.get("cg_sw"), "F"), "Phase length T": si(m.get("T"), "s"),
              "THD tone (amplitude @ centre)": f"{fx(m.get('thd_amp'), 3)} V @ {fx(m.get('thd_vc'), 3)} V",
              "Auxiliary slices": m.get("naux"), "Switch banks": m.get("banks"),
              "Device / MIM area": f"{area(m.get('act_um2'))} / {area(m.get('mim_um2'))}"}
    params["Valid range (pre-PEX)"] = range_txt(m.get("valid"))
    if mp:
        params[f"Valid range ({POST_STAGE[key]} post-PEX)"] = range_txt(mp.get("valid"))
    if unit:
        params["Estimated full-cell size (multi-bank, not drawn)"] = f"{fx(m['layout_w'], 1)} × {fx(m['layout_h'], 1)} µm = {area(m['area_um2'])}"
    params.update({KNOB_NAME.get(k, k): v for k, v in (c.get("knobs") or {}).items()})
    designs.append({
        "id": key, "title": c["name"],
        "summary": (f"**Unit-bank layout:** the GDS and the *Physical* area are one drawn unit bank ({drawn_txt(c)}); the full multi-bank "
                    f"cell (≈ {fx(m['layout_w'], 1)} × {fx(m['layout_h'], 1)} µm = {area(m['area_um2'])}) is the generator's estimate and is not drawn. "
                    if unit else "") + f"Sized for I<sub>max</sub>·R<sub>on</sub> ≤ 5 % VDD at I<sub>max</sub> = {si(c['imax'], 'A')} (R<sub>on</sub> target {si(m['rt'], 'Ω')}) "
                   f"over the valid signal range at all 15 PVT points. Results: Overview · Schematic · Simulation · Layout tabs below; "
                   f"the global *Simulation stage* switches between the schematic (pre-PEX) and the extracted-layout results"
                   + (f" (*partial post-PEX*: only one unit bank of this cell is drawn and extracted, {drawn_txt(c)}; the reported cell size is an estimate)."
                      if unit else " (*full post-PEX*: complete drawn cell extracted)."),
        "vdd": c["vdd"], "axes": {"topology": c["topo"], "class": c["iclass"]}, "tags": tags,
        "physical": {"drc": st.get("drc"), "lvs": st.get("lvs"), "pex": pex.get("ok") if pex else (True if mp else None),
                     **({"area_um2": LAY[key]["drawn"][0] * LAY[key]["drawn"][1], "width_um": LAY[key]["drawn"][0], "height_um": LAY[key]["drawn"][1]}
                        if unit and LAY[key]["drawn"] else {"area_um2": m.get("area_um2"), "width_um": m.get("layout_w"), "height_um": m.get("layout_h")})},
        "results": results, "params": params, "files": files, "images": images,
        "detail": write(f"designs/{key}.json", detail_doc(d, key)),
    })
STAGE_OF["post"] = "partial"
DESIGN_IDS = {x["id"] for x in designs}
done = [c for c in CARDS_SORTED if c["status"]["sim"] == "done"]
# page-level views of the old site's pre/post switch. The post-PEX cards have two extraction levels (35 complete cells = full,
# 90 unit banks = partial); fixed page views are emitted per stage: partial = all extracted cards together, full = complete cells only.
PARTIAL_NOTE = (f"Partial post-PEX view: all {N_COMPLETE + N_UNIT} extracted cards together — the {N_UNIT} unit-bank extractions (partial "
                f"post-PEX) and, alongside, the {N_COMPLETE} complete-cell extractions (full post-PEX); select Full post-PEX for the complete cells "
                "only. Areas marked ≈ are the generator's estimates for multi-bank cells.")
FULL_NOTE = (f"Full post-PEX view: only the {N_COMPLETE} cards whose complete cell is drawn and extracted; the other {N_UNIT} cards have a "
             "partial (unit-bank) extraction — select Partial post-PEX to include them.")
PAGE_VIEWS = [
    {"stage": "pre", "mv": "pre", "cards": lambda c: True, "note": ""},
    {"stage": "partial", "mv": "post", "cards": lambda c: bool(c.get("mp")), "note": PARTIAL_NOTE},
    {"stage": "full", "mv": "post", "cards": lambda c: bool(c.get("mp")) and not est(c), "note": FULL_NOTE},
]


# ============================================================================= page: overview (old list view)
def page_overview():
    blocks = []
    vdds = META["vdds"]
    for V in PAGE_VIEWS:
        for v in vdds:
            cs = [c for c in CARDS if c["vdd"] == v]
            dv = [c for c in done if c["vdd"] == v]
            sub = [c for c in dv if V["cards"](c)]
            items = [{"label": "design cards", "value": str(sum(1 for c in cs if c["status"]["sim"] != "n/a"))},
                     {"label": "fully characterised", "value": str(sum(1 for c in cs if c["status"]["sim"] == "done"))}]
            if V["stage"] != "pre":
                items.append({"label": "cards in this view", "value": str(len(sub))})
            items += [{"label": "rail-to-rail valid range", "value": str(sum(1 for c in sub if (mv(c, V["mv"]).get("coverage") or 0) > 0.97))},
                      {"label": "layouts DRC + LVS clean (drawn GDS)", "value": str(sum(1 for c in cs if c["status"].get("drc") and c["status"].get("lvs")))},
                      {"label": "meet the R<sub>on</sub> target (grade A/B)", "value": str(sum(1 for c in sub if mv(c, V["mv"]).get("grade") in ("A", "B")))},
                      {"label": "post-PEX simulated (complete / unit bank)",
                       "value": f"{sum(1 for c in dv if c.get('mp') and not est(c))} / {sum(1 for c in dv if c.get('mp') and est(c))}"},
                      {"label": "not applicable (n/a)", "value": str(sum(1 for c in cs if c["status"]["sim"] == "n/a"))}]
            blk = {"type": "stats", "title": f"Design cards at {v} V", "stage": V["stage"], "alt": f"ovst{v}", "vdd": v, "items": items}
            if v == vdds[-1]:
                blk["caption"] = V["note"] or (f"DRC/LVS were run on the drawn GDS: the complete cell for {N_COMPLETE} cards, one unit bank for the "
                                               f"other {N_UNIT}.")
            blocks.append(blk)
    # coverage matrix (heatmap with the old colour code and n/a cells), one trace per supply (follows the global V_DD filter)
    cs_ = [[0, "#e5e7eb"], [0.1667, "#e5e7eb"], [0.1667, "#ffd8d6"], [0.5, "#ffd8d6"], [0.5, "#fdeeb8"], [0.8333, "#fdeeb8"], [0.8333, "#cdeed6"], [1, "#cdeed6"]]
    heat = []
    for V in PAGE_VIEWS:
        for v in vdds:
            z, text, cd = [], [], []
            for t in ORDER:
                zr, tr, cr = [], [], []
                for k in ICLS:
                    c = next((x for x in CARDS if x["topo"] == t and x["vdd"] == v and x["iclass"] == k), None)
                    if not c:
                        zr.append(None); tr.append(""); cr.append(["", ""])
                        continue
                    if c["status"]["sim"] == "n/a":
                        zr.append(-1); tr.append("n/a"); cr.append([c["key"], f"{c['key']}: {c['reason']}"])
                        continue
                    if not V["cards"](c):
                        zr.append(-1); tr.append("partial<br>only")
                        cr.append([c["key"], f"{c['name']}: only a unit-bank (partial) extraction — select Partial post-PEX"])
                        continue
                    m = mv(c, V["mv"])
                    cov = m.get("coverage")
                    zr.append(None if cov is None else 2 if cov > 0.97 else 1 if cov > 0 else 0)
                    tr.append("…" if cov is None else f"{jsround(100 * cov)} %<br>{area_lbl(c, m['area_um2']) if m.get('area_um2') else '…'}")
                    cr.append([c["key"], f"{c['name']}<br>valid {range_txt(m.get('valid'))} · area {area_lbl(c, m.get('area_um2'))}"
                                         f"{' (estimated, unit bank drawn)' if est(c) else ''}<br>R_on wc {si(m.get('ron_wc'), 'Ω')} · {grade_txt(m)}"
                                         + ("" if V["stage"] == "pre" else f" · {POST_STAGE[c['key']]} post-PEX")])
                z.append(zr); text.append(tr); cd.append(cr)
            heat.append({"type": "chart", "stage": V["stage"], "alt": f"covmx{v}", "vdd": v, "title": f"Coverage matrix · V<sub>DD</sub> = {v} V",
                         "height": 680, "link_designs": True,
                         **({"caption": V["note"]} if V["note"] and v == vdds[-1] else {}),
                         "data": [{"type": "heatmap", "z": z, "text": text, "texttemplate": "%{text}", "textfont": {"size": 11, "color": "#1f2937"},
                                   "x": [icl_of(k) for k in ICLS], "y": [SHORT[t] for t in ORDER], "customdata": cd,
                                   "hovertemplate": "%{customdata[1]}<extra></extra>", "zmin": -1, "zmax": 2, "colorscale": cs_, "showscale": False,
                                   "xgap": 3, "ygap": 3}],
                         "layout": {"yaxis": {"autorange": "reversed", "automargin": True, "showgrid": False},
                                    "xaxis": {"side": "top", "showgrid": False, "type": "category"}, "margin": {"l": 200, "t": 40, "b": 10, "r": 10}}})
    blocks.append({"type": "section", "title": "Coverage matrix", "cols": 2, "blocks": heat,
                   "intro": "One cell per design card. The value is the valid signal range as a fraction of the supply (green: rail-to-rail, amber: "
                            "partial, red: none) and the cell's area (**≈** = the generator's estimate for a multi-bank cell of which only one unit bank "
                            "is drawn); grey **n/a**: not applicable. Click a cell to open the design. The built-in *Designs → Matrix* view shows the "
                            "same grid with any metric."})
    # R_on point ladder per supply x current class (group headers of the old card list)
    rows = []
    for v in vdds:
        for k, (lo, hi) in ICLS.items():
            rows.append({"vdd": v, "cls": icl_of(k), "imax": hi, **{g: f * v / hi for g, f in GRADES},
                         "n": sum(1 for c in CARDS if c["vdd"] == v and c["iclass"] == k)})
    blocks.append({"type": "table", "title": "R<sub>on</sub> points per supply and current class", "search": False,
                   "caption": f"The card list grouped by V<sub>DD</sub> × current class: R<sub>on</sub> points at the class's maximum current, "
                              f"R = f·VDD / I<sub>max</sub> with A ≤ 2 %, B ≤ 5 % (the design target = {jsround(100 * DROP)} % VDD), C ≤ 10 %, D ≤ 20 % — "
                              "specification thresholds, not simulation results.",
                   "columns": [{"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"}, {"key": "cls", "label": "Current class", "type": "text"},
                               {"key": "imax", "label": "I<sub>max</sub>", "unit": "A", "si": True}]
                              + [{"key": g, "label": f"{g} ({jsround(100 * f)} %)" + (" target" if f == DROP else ""), "unit": "Ω", "si": True} for g, f in GRADES]
                              + [{"key": "n", "label": "cards"}], "rows": rows})
    # comparison table (old list "Comparison table"): one row per design and stage; best stage per design
    rows = []
    for c in done:
        for view in ("pre", "post"):
            if view == "post" and not c.get("mp"):
                continue
            m = mv(c, view)
            rows.append({"design": {"v": c["key"], "t": f"{c['short']} · {c['vdd']} V · {icl_of(c['iclass'])}"}, "vdd": c["vdd"],
                         "valid": range_txt(m.get("valid")), "cov": 100 * m["coverage"], "ron": m.get("ron_vtest"), "ronwc": m.get("ron_wc"),
                         "grade": {"v": grade_txt(m), "s": grade_s(m.get("grade"))}, "flat": m.get("ron_flat"), "roff": m.get("roff_wc"),
                         "ton": m.get("t_on"), "toff": m.get("t_off"), "e": m.get("e_vdd"), "q": m.get("q_vtest"), "qmax": m.get("q_absmax"),
                         "iso": m.get("iso_10m"), "thd": m.get("thd_db"), "rc": m["ron_coff_fs"] * 1e-15 if m.get("ron_coff_fs") is not None else None,
                         "area": {"v": m.get("area_um2"), "s": "muted", "title": "estimated full-cell area (only one unit bank is drawn)"} if est(c) else m.get("area_um2"),
                         "lay": "unit bank (area ≈)" if est(c) else "complete", "status": status_txt(c, view),
                         "stage": "pre" if view == "pre" else POST_STAGE[c["key"]], "_design": c["key"]})
    tcols = [{"key": "design", "label": "Design", "type": "design"}, {"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"},
             {"key": "valid", "label": "Valid range", "type": "text"}, {"key": "cov", "label": "Range", "unit": "% VDD", "better": "high"},
             {"key": "ron", "label": "Ron", "unit": "Ω", "si": True, "better": "low"}, {"key": "ronwc", "label": "Ron wc", "unit": "Ω", "si": True, "better": "low"},
             {"key": "grade", "label": "Grade", "type": "text"}, {"key": "flat", "label": "flat", "digits": 3, "better": "low"},
             {"key": "roff", "label": "Roff wc", "unit": "Ω", "si": True, "better": "high"}, {"key": "ton", "label": "ton", "unit": "s", "si": True, "better": "low"},
             {"key": "toff", "label": "toff", "unit": "s", "si": True, "better": "low"}, {"key": "e", "label": "E/cycle", "unit": "J", "si": True, "better": "low"},
             {"key": "q", "label": "Qinj", "unit": "C", "si": True}, {"key": "qmax", "label": "|Q| max", "unit": "C", "si": True, "better": "low"},
             {"key": "iso", "label": "Iso 10M", "unit": "dB", "better": "low"}, {"key": "thd", "label": "THD", "unit": "dB", "better": "low"},
             {"key": "rc", "label": "Ron·Coff", "unit": "s", "si": True, "better": "low"}, {"key": "area", "label": "Area", "unit": "µm²", "digits": 4, "better": "low"},
             {"key": "lay", "label": "Layout", "type": "text"}, {"key": "status", "label": "Status", "type": "text"}, {"key": "stage", "label": "Stage", "type": "text"}]
    blocks.append({"type": "table", "title": "Comparison table", "src": write("data/compare_table.json", {"columns": tcols, "rows": rows}),
                   "columns": tcols, "stage_column": "stage", "stage_group": "design", "page_size": 400, "csv_name": "switch_comparison",
                   "caption": "Every characterised design in one sortable table (click a header; default: generator order). Rows open the design. "
                              "Follows the global *Simulation stage*: each design shows its best available stage ≤ the selected one (with *fill from "
                              f"earlier stage*), so at Full post-PEX the {N_COMPLETE} complete-cell extractions (full) appear together with the {N_UNIT} "
                              "unit-bank extractions (partial); the *Stage* column tells which is which. Areas in grey are the generator's estimates for "
                              "multi-bank cells. Follows the V<sub>DD</sub> filter."})
    blocks.append({"type": "table", "title": "Not applicable cards", "search": False, "csv": False,
                   "caption": "These matrix positions are part of the generator's grid but are not built: no simulation, layout or results exist. They "
                              "appear as n/a placeholders in the Designs view.",
                   "columns": [{"key": "key", "label": "Card", "type": "design"}, {"key": "topo", "label": "Topology", "type": "text"},
                               {"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"}, {"key": "cls", "label": "Current class", "type": "text"},
                               {"key": "tags", "label": "Tags", "type": "text", "wrap": True}, {"key": "reason", "label": "Reason", "type": "text", "wrap": True}],
                   "rows": [{"key": c["key"], "topo": c["short"], "vdd": c["vdd"], "cls": icl_of(c["iclass"]), "tags": ", ".join(c.get("tags") or []),
                             "reason": c.get("reason") or "", "_design": c["key"]} for c in na_cards]})
    tags_of = {t: [] for t in ORDER}
    for c in CARDS:
        for g in c.get("tags") or []:
            if g not in tags_of[c["topo"]]:
                tags_of[c["topo"]].append(g)
    blocks.append({"type": "table", "title": "Topologies", "search": False, "csv": False,
                   "columns": [{"key": "t", "label": "Topology", "type": "text"}, {"key": "id", "label": "id", "type": "text"},
                               {"key": "tags", "label": "Devices / tags", "type": "text", "wrap": True},
                               {"key": "desc", "label": "Description", "type": "text", "wrap": True}, {"key": "n", "label": "cards"}],
                   "rows": [{"t": SHORT[t], "id": t, "tags": ", ".join(tags_of[t]), "desc": DESC[t],
                             "n": sum(1 for c in done if c["topo"] == t)} for t in ORDER]})
    intro = ("## Deliverable design cards\n\nThirteen analog-switch topologies (including precision ADC sampling switches) × two supplies (1.8 V, 3.3 V) × "
             "five load-current classes (10 µA … 1 A). Every switch is sized so that its on-resistance keeps the drop at the class's maximum current "
             "below 5 % of VDD over its whole valid signal range at all 15 PVT corners, characterised with a testbench suite (on-resistance, leakage, "
             "timing, switching energy, charge injection, off-isolation, distortion, device stress) and laid out with gLayout primitives (DRC/LVS with "
             "the PDK KLayout decks), then re-simulated from the extracted layout (post-PEX; the hub's global *Simulation stage* option). Select a "
             "card for its schematic with gm/I<sub>D</sub> annotation, simulation results and layout.\n\n"
             "<small>pass-gate · T-switch · clock-boosted · bootstrapped (3 V<sub>T</sub> options) · Spectre PVT · gLayout · GF180MCU-D. "
             "Filters of the old card list map to the hub as follows: V<sub>DD</sub> → global supply filter; current class and topology → chips "
             "in the Designs view; DRC+LVS clean → global verification filter; Status *Rail-to-rail* → search tag `r2r-pre` (schematic) or "
             "`r2r-post` (extracted), or the matrix colours; R<sub>on</sub> grade → search tag `R_on grade B` or sort the comparison table.</small>")
    return {"intro": intro, "blocks": blocks}


# ============================================================================= page: topology comparison
CMP = [("area_um2", "Layout area", "µm²", "log", 1), ("e_vdd", "Switching energy per cycle", "pJ", "log", 1e12),
       ("q_absmax", "Max |charge injection| over the range", "pC", "log", 1e12), ("t_on", "Turn-on time", "ns", "log", 1e9),
       ("coverage", "Valid signal range", "% of VDD", "linear", 100), ("thd_db", "Tracking THD, 1 MHz into I_max load", "dB", "linear", 1),
       ("ron_coff_fs", "R_on · C_off", "fs", "log", 1), ("ron_flat", "R_on flatness max/min over range", "", "log", 1)]


def page_compare():
    cls = list(ICLS)
    tabs = []
    for v in META["vdds"]:
        cs = [c for c in CARDS if c["vdd"] == v and c["status"]["sim"] == "done"]
        blocks = []
        for V in PAGE_VIEWS:
            sub = [c for c in cs if V["cards"](c)]
            blocks.append({"type": "stats", "title": f"Cards at {v} V", "stage": V["stage"], "alt": "cst",
                           "items": [{"label": f"characterised cards at {v} V", "value": str(len(cs))}]
                                    + ([{"label": "cards in this view", "value": str(len(sub))}] if V["stage"] != "pre" else [])
                                    + [{"label": "rail-to-rail", "value": str(sum(1 for c in sub if (mv(c, V["mv"]).get("coverage") or 0) > 0.97))}],
                           **({"caption": V["note"]} if V["note"] else {})})
        present = [t for t in ORDER if any(c["topo"] == t for c in cs)]
        blocks.append({"type": "chart", "height": 150, "title": "Topologies",
                       "data": [{"x": [None], "y": [None], "name": SHORT[t], "mode": "lines+markers", "line": {"color": TCOL[ORDER.index(t)], "width": 2},
                                 "marker": {"size": 6}} for t in present],
                       "layout": {"xaxis": {"visible": False}, "yaxis": {"visible": False}, "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
                                  "legend": {"orientation": "h", "y": 1, "x": 0, "yanchor": "top"}, "showlegend": True},
                       "config": {"displayModeBar": False, "staticPlot": False}})
        charts = []
        for i, (k, title, unit, ty, f) in enumerate(CMP):
            for V in PAGE_VIEWS:
                trs = []
                for j, topo in enumerate(ORDER):
                    pts = [next((x for x in cs if x["topo"] == topo and x["iclass"] == cl and V["cards"](x)), None) for cl in cls]
                    ys = [mv(p, V["mv"])[k] * f if p and mv(p, V["mv"]).get(k) is not None else None for p in pts]
                    if not any(y is not None for y in ys):
                        continue
                    isarea = k == "area_um2"
                    trs.append({"x": [icl_of(cl) for cl in cls], "y": ys, "name": SHORT[topo], "mode": "lines+markers",
                                "line": {"color": TCOL[j], "width": 2},
                                "marker": {"size": 6, "color": TCOL[j], **({"symbol": ["circle-open" if p and est(p) else "circle" for p in pts]} if isarea else {})},
                                "customdata": [p["key"] if p else "" for p in pts],
                                "text": [(("≈ estimated (multi-bank)" if est(p) else "drawn layout") if isarea else "")
                                         + ("" if V["stage"] == "pre" else f" · {POST_STAGE[p['key']]} post-PEX") if p else "" for p in pts],
                                "hovertemplate": f"{SHORT[topo]}: %{{y:.3g}} %{{text}}<extra></extra>"})
                cap = ("Filled markers: drawn layout area (complete cell); open markers: the generator's estimate for a multi-bank cell of which "
                       "only one unit bank is drawn.") if k == "area_um2" else ""
                if i == 0 and V["note"]:
                    cap = (cap + " " + V["note"]).strip()
                yax = {"type": ty, "title": {"text": f"{title.split(',')[0]}{f' ({unit})' if unit else ''}"}}
                if ty == "log":
                    yax["dtick"] = 1
                charts.append({"type": "chart", "stage": V["stage"], "alt": f"c{i}", "title": f"{title}{f' ({unit})' if unit else ''}",
                               "link_designs": True, "height": 340, **({"caption": cap} if cap else {}),
                               "data": trs, "layout": {"showlegend": False, "yaxis": yax, "hovermode": "closest",
                                                       "xaxis": {"type": "category", "title": {"text": "load-current class"}}}})
        blocks.append({"type": "section", "cols": 2, "blocks": charts})
        tabs.append({"label": f"{v} V", "vdd": v, "blocks": blocks})
    intro = ("## Topology comparison\n\nKey metrics of all characterised cards against the load-current class, one line per topology. Every card meets "
             "the same on-resistance target (R<sub>on</sub>·I<sub>max</sub> ≤ 5 % VDD over its valid range, worst PVT), so the curves show what each "
             "topology pays for it: area, switching energy, charge injection and speed, and how much of the supply it can actually pass. "
             "Click a point to open the card. The global *Simulation stage* selects the netlist: Pre-PEX = schematic; Partial post-PEX = all "
             f"125 extracted cards ({N_UNIT} unit-bank + {N_COMPLETE} complete-cell extractions); Full post-PEX = only the {N_COMPLETE} complete cells.")
    return {"intro": intro, "blocks": [{"type": "tabs", "id": "vdd", "label": "V<sub>DD</sub>", "tabs": tabs}]}


# ============================================================================= page: design-space explorer
SW = load("data/sweep.json")
C = SW["cols"]
NS = len(C["vdd"])
XM = {"ron_wc": ("R_on, worst PVT (Ω)", "log"), "area": ("layout area (µm²)", "log"), "q_absmax": ("max |charge injection| (C)", "log"),
      "e_vdd": ("switching energy / cycle (J)", "log"), "t_on": ("turn-on time (s)", "log"), "coverage": ("valid range (fraction of VDD)", "linear"),
      "fom_ra": ("R_on · area (Ω·µm²)", "log"), "thd_db": ("tracking THD (dB)", "linear")}
EXP = {"ron_area": ("R_on vs area", "Minimise both: what a given on-resistance costs in silicon."),
       "ron_q": ("R_on vs charge injection", "Minimise both: a lower R_on needs a wider switch, which injects more charge."),
       "ron_e": ("R_on vs energy", "Minimise both: switching energy per on/off cycle (drivers, bootstrap / pump) vs on-resistance."),
       "ron_ton": ("R_on vs speed", "Minimise both: turn-on time (ck to 90 % of the load current) vs on-resistance."),
       "cov_fom": ("Range vs R_on·area", "Maximise the valid signal range, minimise the R_on·area product (width-independent figure of merit)."),
       "thd_cov": ("Linearity vs range", "Maximise the valid range, minimise tracking THD at 1 MHz into the I_max load.")}
EXKEYS = {"ron_area": ("ron_wc", "area"), "ron_q": ("ron_wc", "q_absmax"), "ron_e": ("ron_wc", "e_vdd"), "ron_ton": ("ron_wc", "t_on"),
          "cov_fom": ("fom_ra", "coverage"), "thd_cov": ("coverage", "thd_db")}
EX_PRE = {"ov": "Pareto fronts by topology", "fac_h": "Per-topology design clouds",
          "fac_p": "Grey: sampled designs · coloured line: the topology's Pareto front for this trade-off (filled = R<sub>on</sub> re-simulated at all 5 corners "
                   "× 3 temperatures stays within 5 % of the sweep's worst-case estimate, open = it does not) · grey diamonds: the delivered design cards. "
                   "Hover any point for its parameters; click a diamond to open the card.",
          "tab_h": "Front designs (all topologies)", "tab_p": "The designs on the combined Pareto front of the selected trade-off and supply, with their knobs."}
EX_POST = {"ov": "Post-PEX Pareto fronts of the design cards", "fac_h": "Per-topology design cards (post-PEX)",
           "fac_p": "Diamonds: the delivered design cards with their extracted-layout (post-PEX) results · coloured line: the topology's Pareto front among its "
                    "cards for this trade-off. The sweep samples are schematic simulations without a layout and are hidden in this view. Hover a diamond for "
                    "its values; click it to open the card.",
           "tab_h": "Front design cards (all topologies, post-PEX)", "tab_p": "The design cards on the combined post-PEX Pareto front of the selected trade-off and supply."}


def ax(k):
    return {"type": XM[k][1], "title": {"text": XM[k][0]}, "exponentformat": "SI"}


def hov_sample(i):
    t = SW["topos"][C["topo"][i]]
    pr = f" · 15-PVT R_on ×{fx(C['pvt_ratio'][i], 2)}" if C.get("pvt_ratio") and C["pvt_ratio"][i] is not None else ""
    return (f"{SHORT[t]} · W {si(C['ws'][i] * 1e-6, 'm')}<br>R_on wc {si(C['ron_wc'][i], 'Ω')} · I_max {si(C['imax'][i], 'A')}{pr}<br>"
            f"range {fx(100 * C['coverage'][i], 0)} % · area {area(C['area'][i])}<br>t_on {si(C['t_on'][i], 's')} · E {si(C['e_vdd'][i], 'J')} · "
            f"|Q| {si(C['q_absmax'][i], 'C')}<br>THD {fx(C['thd_db'][i], 1)} dB<br>{knobs_txt(C['knobs'][i])}")


def card_trace(cs, kx, ky, view):
    return {"x": [cval(c, kx, view) for c in cs], "y": [cval(c, ky, view) for c in cs], "mode": "markers", "type": "scatter", "name": "design cards",
            "marker": DIAMOND, "customdata": [c["key"] for c in cs],
            "text": [f"area {area_lbl(c, mv(c, view).get('area_um2'))}" for c in cs], "hovertemplate": "%{customdata}<br>%{text}<extra></extra>"}


def pareto(pts, kx, ky):
    sx, sy = (-1 if kx == "coverage" else 1), (-1 if ky == "coverage" else 1)
    outp, best = [], math.inf
    for p in sorted(pts, key=lambda p: (sx * p["x"], sy * p["y"])):
        if sy * p["y"] < best:
            best = sy * p["y"]
            outp.append(p)
    return sorted(outp, key=lambda p: p["x"])


def combo_pre(preset, vdd):
    kx, ky = EXKEYS[preset]
    sel = [i for i in range(NS) if C["vdd"][i] == vdd and C[kx][i] is not None and C[ky][i] is not None]
    fr = lambda t: sorted(SW["fronts"].get(f"{preset}|{vdd}|{t}") or [], key=lambda i: C[kx][i])  # noqa: E731
    sym = lambda f: ["circle-open" if C["robust"][i] is False else "circle" for i in f]  # noqa: E731
    cards = [c for c in done if c["vdd"] == vdd]
    trs = []
    for j, t in enumerate(ORDER):
        f = fr(t)
        if f:
            trs.append({"x": [C[kx][i] for i in f], "y": [C[ky][i] for i in f], "mode": "lines+markers", "type": "scatter", "name": SHORT[t],
                        "line": {"color": TCOL[j], "width": 2, "shape": "hv"}, "marker": {"size": 6, "color": TCOL[j], "symbol": sym(f)},
                        "text": [hov_sample(i) for i in f], "hovertemplate": "%{text}<extra></extra>"})
    trs.append(card_trace(cards, kx, ky, "pre"))
    tag = f"pre_{preset}_{str(vdd).replace('.', 'p')}"
    blocks = [{"type": "stats", "title": "Sweep fronts (this trade-off and supply)", "stage": "pre", "alt": "cst",
               "items": [{"label": "samples shown", "value": f"{len(sel):,}"},
                         {"label": "per-topology front points", "value": str(sum(len(fr(t)) for t in ORDER))},
                         {"label": "on the combined front", "value": str(len(fr("all")))},
                         {"label": "design cards (diamonds)", "value": str(len(cards))}]},
              {"type": "chart", "stage": "pre", "alt": "ov", "title": EX_PRE["ov"], "link_designs": True, "height": 560,
               "caption": f"{EXP[preset][1]} VDD = {vdd} V; {len(sel):,} samples shown." + (
                   " Area of the sweep samples is *estimated* (device + MIM area with a per-topology fit to the delivered cards' layouts); the "
                   f"diamonds use the cards' reported areas — drawn layouts for {N_COMPLETE} cards, generator estimates for the {N_UNIT} multi-bank "
                   "cards of which only one unit bank is drawn." if "area" in (kx, ky) or "fom_ra" in (kx, ky) else ""),
               "src": write(f"data/dse/{tag}_ov.json", {"data": trs, "layout": {"xaxis": ax(kx), "yaxis": ax(ky), "hovermode": "closest"}})}]
    facets = []
    for j, t in enumerate(ORDER):
        ti = SW["topos"].index(t)
        pts, f = [i for i in sel if C["topo"][i] == ti], fr(t)
        if not pts:
            facets.append({"type": "note", "tone": "muted", "title": SHORT[t], "text": "not applicable at this supply" if META["na"].get(t) else "no samples"})
            continue
        fig = {"data": [
            {"x": [C[kx][i] for i in pts], "y": [C[ky][i] for i in pts], "mode": "markers", "type": "scatter", "name": "samples",
             "marker": {"size": 4, "color": "#9ca3af", "opacity": 0.7}, "text": [hov_sample(i) for i in pts], "hovertemplate": "%{text}<extra></extra>"},
            {"x": [C[kx][i] for i in f], "y": [C[ky][i] for i in f], "mode": "lines+markers", "type": "scatter", "name": "front",
             "line": {"color": TCOL[j], "width": 2, "shape": "hv"}, "marker": {"size": 6, "color": TCOL[j], "symbol": sym(f)},
             "text": [hov_sample(i) for i in f], "hovertemplate": "%{text}<extra></extra>"},
            card_trace([c for c in cards if c["topo"] == t], kx, ky, "pre")],
            "layout": {"xaxis": ax(kx), "yaxis": ax(ky), "showlegend": False, "hovermode": "closest", "margin": {"l": 56, "r": 8, "t": 6, "b": 40}}}
        facets.append({"type": "chart", "title": SHORT[t], "height": 300, "link_designs": True, "src": write(f"data/dse/{tag}_{t}.json", fig)})
    blocks.append({"type": "section", "stage": "pre", "alt": "fac", "title": EX_PRE["fac_h"], "intro": EX_PRE["fac_p"], "cols": 3, "blocks": facets})
    fa = fr("all")
    rows = [{"topo": SHORT[SW["topos"][C["topo"][i]]], "w": C["ws"][i] * 1e-6, "ron": C["ron_wc"][i], "imax": C["imax"][i], "cov": 100 * C["coverage"][i],
             "area": C["area"][i], "ton": C["t_on"][i], "e": C["e_vdd"][i], "q": C["q_absmax"][i], "thd": C["thd_db"][i],
             "pvt": "—" if C["robust"][i] is None else "✓" if C["robust"][i] else "✗", "knobs": knobs_txt(C["knobs"][i])} for i in fa]
    cols = [{"key": "topo", "label": "Topology", "type": "text"}, {"key": "w", "label": "W", "unit": "m", "si": True},
            {"key": "ron", "label": "R_on wc", "unit": "Ω", "si": True}, {"key": "imax", "label": "I_max", "unit": "A", "si": True},
            {"key": "cov", "label": "range", "unit": "%", "digits": 3}, {"key": "area", "label": "area (est.)", "unit": "µm²", "digits": 4},
            {"key": "ton", "label": "t_on", "unit": "s", "si": True}, {"key": "e", "label": "E/cycle", "unit": "J", "si": True},
            {"key": "q", "label": "|Q| max", "unit": "C", "si": True}, {"key": "thd", "label": "THD", "unit": "dB", "digits": 3},
            {"key": "pvt", "label": "15-PVT", "type": "text", "title": "R_on re-simulated at all 15 PVT points within 5 % of the sweep estimate"},
            {"key": "knobs", "label": "knobs", "type": "text"}]
    blocks.append({"type": "table", "stage": "pre", "alt": "tab", "title": EX_PRE["tab_h"], "caption": EX_PRE["tab_p"],
                   "src": write(f"data/dse/{tag}_tab.json", {"columns": cols, "rows": rows}), "columns": cols, "max_height": 520})
    return blocks


def combo_post(preset, vdd, V):
    """post-PEX trade-off view over the cards of page view V (partial = all extracted cards, full = complete cells only)"""
    kx, ky = EXKEYS[preset]
    st = V["stage"]
    allc = [c for c in done if V["cards"](c)]
    cards = [{"c": c, "x": cval(c, kx, "post"), "y": cval(c, ky, "post")} for c in allc if c["vdd"] == vdd]
    cards = [p for p in cards if p["x"] is not None and p["y"] is not None and math.isfinite(p["x"]) and math.isfinite(p["y"])]
    fronts = {t: pareto([p for p in cards if p["c"]["topo"] == t], kx, ky) for t in ORDER}
    fall = pareto(cards, kx, ky)
    nfr = sum(len(fronts[t]) for t in ORDER)

    def hov(p):
        v = mv(p["c"], "post")
        return (f"{p['c']['key']} · {grade_txt(v)} · {POST_STAGE[p['c']['key']]} post-PEX<br>R_on wc {si(v.get('ron_wc'), 'Ω')} · I_max {si(v.get('imax'), 'A')} · "
                f"range {fx(100 * v['coverage'], 0)} %<br>area {area_lbl(p['c'], v.get('area_um2'))} · t_on {si(v.get('t_on'), 's')} · E {si(v.get('e_vdd'), 'J')}<br>"
                f"|Q| {si(v.get('q_absmax'), 'C')} · THD {fx(v.get('thd_db'), 1)} dB")

    def tr(ps, j, name, line):
        return {"x": [p["x"] for p in ps], "y": [p["y"] for p in ps], "type": "scatter", "name": name, "mode": "lines+markers" if line else "markers",
                "line": {"color": TCOL[j], "width": 2, "shape": "hv"},
                "marker": {"symbol": "diamond", "size": 9 if line else 8, "color": TCOL[j], "opacity": 1 if line else 0.45, "line": {"width": 1, "color": "#ffffff"}},
                "customdata": [p["c"]["key"] for p in ps], "text": [hov(p) for p in ps], "hovertemplate": "%{text}<extra></extra>", "showlegend": line}
    trs = []
    for j, t in enumerate(ORDER):
        ps = [p for p in cards if p["c"]["topo"] == t]
        if ps:
            trs += [tr(ps, j, SHORT[t], False), tr(fronts[t], j, SHORT[t], True)]
    tag = f"{st}_{preset}_{str(vdd).replace('.', 'p')}"
    blocks = [{"type": "stats", "title": "Post-PEX fronts (this trade-off and supply)", "stage": st, "alt": "cst",
               "items": [{"label": "design cards in this view", "value": str(len(cards))},
                         {"label": "per-topology post-PEX front cards (this view)", "value": str(nfr)},
                         {"label": "on the combined front (this view)", "value": str(len(fall))}]},
              {"type": "chart", "stage": st, "alt": "ov", "title": EX_POST["ov"], "link_designs": True, "height": 560,
               "caption": f"{EXP[preset][1]} VDD = {vdd} V; {len(cards)} design cards, all values from the extracted-layout (post-PEX) simulations. The sweep "
                          "samples have no layout and are hidden in this view; switch the global *Simulation stage* to Pre-PEX to see them. " + V["note"],
               "src": write(f"data/dse/{tag}_ov.json", {"data": trs, "layout": {"xaxis": ax(kx), "yaxis": ax(ky), "hovermode": "closest"}})}]
    facets = []
    for j, t in enumerate(ORDER):
        ps = [p for p in cards if p["c"]["topo"] == t]
        if not ps:
            facets.append({"type": "note", "tone": "muted", "title": SHORT[t],
                           "text": "not applicable at this supply" if META["na"].get(t) and vdd > 2 else
                                   ("no complete-cell card at this supply (select Partial post-PEX)" if st == "full" else "no design card with post-PEX results")})
            continue
        facets.append({"type": "chart", "title": SHORT[t], "height": 300, "link_designs": True,
                       "src": write(f"data/dse/{tag}_{t}.json", {"data": [tr(ps, j, "cards", False), tr(fronts[t], j, "front", True)],
                                                                 "layout": {"xaxis": ax(kx), "yaxis": ax(ky), "showlegend": False, "hovermode": "closest",
                                                                            "margin": {"l": 56, "r": 8, "t": 6, "b": 40}}})})
    blocks.append({"type": "section", "stage": st, "alt": "fac", "title": EX_POST["fac_h"], "intro": EX_POST["fac_p"], "cols": 3, "blocks": facets})
    rows = []
    for p in fall:
        v = mv(p["c"], "post")
        rows.append({"card": p["c"]["key"], "topo": SHORT[p["c"]["topo"]], "w": v["ws"] * 1e-6, "ron": v.get("ron_wc"),
                     "pt": {"v": grade_txt(v), "s": grade_s(v.get("grade"))}, "imax": v.get("imax"), "cov": 100 * v["coverage"],
                     "area": {"v": v.get("area_um2"), "s": "muted", "title": "estimated full-cell area (only one unit bank is drawn)"} if est(p["c"]) else v.get("area_um2"),
                     "ton": v.get("t_on"), "e": v.get("e_vdd"), "q": v.get("q_absmax"), "thd": v.get("thd_db"),
                     "stage": f"{POST_STAGE[p['c']['key']]} post-PEX", "_design": p["c"]["key"]})
    cols = [{"key": "card", "label": "Card", "type": "design"}, {"key": "topo", "label": "Topology", "type": "text"},
            {"key": "w", "label": "W", "unit": "m", "si": True}, {"key": "ron", "label": "R_on wc", "unit": "Ω", "si": True},
            {"key": "pt", "label": "R_on point", "type": "text"}, {"key": "imax", "label": "I_max", "unit": "A", "si": True},
            {"key": "cov", "label": "range", "unit": "%", "digits": 3}, {"key": "area", "label": "area", "unit": "µm²", "digits": 4},
            {"key": "ton", "label": "t_on", "unit": "s", "si": True}, {"key": "e", "label": "E/cycle", "unit": "J", "si": True},
            {"key": "q", "label": "|Q| max", "unit": "C", "si": True}, {"key": "thd", "label": "THD", "unit": "dB", "digits": 3},
            {"key": "stage", "label": "extraction", "type": "text"}]
    blocks.append({"type": "table", "stage": st, "alt": "tab", "title": EX_POST["tab_h"],
                   "caption": EX_POST["tab_p"] + " Areas in grey are the generator's estimates for multi-bank cells.",
                   "src": write(f"data/dse/{tag}_tab.json", {"columns": cols, "rows": rows}), "columns": cols})
    return blocks


def class_of(imax):
    for k, (lo, hi) in ICLS.items():
        if lo <= imax <= hi:
            return k
    first = next(iter(ICLS.values()))
    return "below" if imax < first[0] else "above"


def explorer_data():
    knob_keys = ["kcb", "rp", "fo", "f_aux", "f_dum", "f_shunt", "l_scale"]
    front_set = {i for k, v in SW["fronts"].items() if not k.endswith("|all") for i in v}
    col = {k: [] for k in ["topo", "vdd", "supply", "stage", "source", "lay", "pvt", "front", "cls", "design", "delivered", "label", "ws", "ron_wc", "imax",
                           "imax_cls", "coverage", "area", "fom_ra", "t_on", "e_vdd", "q_absmax", "thd_db", "pvt_ratio", "knobs", "ron_vtest", "t_off",
                           "iso_10m", "ron_flat", "leak_wc"] + knob_keys}

    def add(**kw):
        for k in col:
            col[k].append(kw.get(k))
    for i in range(NS):
        t = SW["topos"][C["topo"][i]]
        rb = C["robust"][i]
        add(topo=t, vdd=C["vdd"][i], supply=f"{C['vdd'][i]} V", stage="pre", source="sweep sample", lay="sweep (area estimated)",
            pvt="not re-simulated" if rb is None else "within 5 % over 15 PVT" if rb else "not within 5 % over 15 PVT",
            front="Pareto-front point" if i in front_set else "off-front sample", cls=class_of(C["imax"][i]), delivered=False,
            label=f"{SHORT[t]} · sweep #{i}", ws=C["ws"][i] * 1e-6, ron_wc=C["ron_wc"][i], imax=C["imax"][i], coverage=100 * C["coverage"][i],
            area=C["area"][i], fom_ra=C["fom_ra"][i], t_on=C["t_on"][i], e_vdd=C["e_vdd"][i], q_absmax=C["q_absmax"][i], thd_db=C["thd_db"][i],
            pvt_ratio=C["pvt_ratio"][i], knobs=knobs_txt(C["knobs"][i]), **{k: C["knobs"][i].get(k) for k in knob_keys})
    for c in done:
        for view in ("pre", "post"):
            if view == "post" and not c.get("mp"):
                continue
            m = mv(c, view)
            rating = DROP * c["vdd"] / m["ron_wc"] if m.get("ron_wc") else None   # same rule as the sweep: 5 % VDD / R_on,wc
            add(topo=c["topo"], vdd=c["vdd"], supply=f"{c['vdd']} V", stage="pre" if view == "pre" else POST_STAGE[c["key"]],
                source="design card", pvt="design card (15 PVT)", lay="unit bank (area estimated)" if est(c) else "complete layout",
                front="design card", cls=c["iclass"], design=c["key"], delivered=True,
                label=c["name"] + ("" if view == "pre" else " · " + POST_STAGE[c["key"]] + " post-PEX"),
                ws=m["ws"] * 1e-6, ron_wc=m.get("ron_wc"), imax=rating, imax_cls=c["imax"], coverage=100 * m["coverage"], area=m.get("area_um2"),
                fom_ra=cval(c, "fom_ra", view), t_on=m.get("t_on"), e_vdd=m.get("e_vdd"), q_absmax=m.get("q_absmax"), thd_db=m.get("thd_db"),
                knobs=knobs_txt(c["knobs"]), ron_vtest=m.get("ron_vtest"), t_off=m.get("t_off"), iso_10m=m.get("iso_10m"),
                ron_flat=m.get("ron_flat"), leak_wc=m.get("leak_wc"), **{k: (c.get("knobs") or {}).get(k) for k in knob_keys})
    return col


def page_explore():
    col = explorer_data()
    dims = [
        {"key": "ron_wc", "label": "R_on, worst PVT", "unit": "Ω", "si": True, "log": True, "better": "low"},
        {"key": "area", "label": "Layout area (sweep & multi-bank cards: estimated)", "unit": "µm²", "log": True, "better": "low", "digits": 4},
        {"key": "q_absmax", "label": "Max |charge injection|", "unit": "C", "si": True, "log": True, "better": "low"},
        {"key": "e_vdd", "label": "Switching energy / cycle", "unit": "J", "si": True, "log": True, "better": "low"},
        {"key": "t_on", "label": "Turn-on time", "unit": "s", "si": True, "log": True, "better": "low"},
        {"key": "coverage", "label": "Valid range", "unit": "% VDD", "better": "high"},
        {"key": "fom_ra", "label": "R_on · area", "unit": "Ω·µm²", "log": True, "better": "low"},
        {"key": "thd_db", "label": "Tracking THD (1 MHz)", "unit": "dB", "better": "low"},
        {"key": "imax", "label": "I_max rating (5 % VDD / R_on,wc)", "unit": "A", "si": True, "log": True, "better": "high"},
        {"key": "imax_cls", "label": "I_max class target (cards)", "unit": "A", "si": True, "log": True},
        {"key": "ws", "label": "Switch width W_s", "unit": "m", "si": True, "log": True},
        {"key": "pvt_ratio", "label": "15-PVT R_on / sweep estimate", "digits": 4, "better": "low"},
        {"key": "ron_vtest", "label": "R_on @ test level (cards)", "unit": "Ω", "si": True, "log": True, "better": "low"},
        {"key": "t_off", "label": "Turn-off time (cards)", "unit": "s", "si": True, "log": True, "better": "low"},
        {"key": "iso_10m", "label": "Off-isolation @10 MHz (cards)", "unit": "dB", "better": "low"},
        {"key": "ron_flat", "label": "R_on flatness (cards)", "log": True, "better": "low"},
        {"key": "leak_wc", "label": "Off leakage worst PVT (cards)", "unit": "A", "si": True, "log": True, "better": "low"},
        {"key": "kcb", "label": "knob kcb (C_B / C_gate)"}, {"key": "rp", "label": "knob rp (W_p/W_n)"}, {"key": "fo", "label": "knob fo (driver fan-out)"},
        {"key": "f_aux", "label": "knob f_aux (aux scale)"}, {"key": "f_dum", "label": "knob f_dum (dummy size)"},
        {"key": "f_shunt", "label": "knob f_shunt (shunt size)"}, {"key": "l_scale", "label": "knob l_scale (channel length)"},
        {"key": "topo", "label": "Topology", "type": "cat", "labels": {t: SHORT[t] for t in ORDER}, "order": ORDER,
         "colors": {t: TCOL[j] for j, t in enumerate(ORDER)}},
        {"key": "supply", "label": "Supply", "type": "cat", "order": ["1.8 V", "3.3 V"]},
        {"key": "cls", "label": "Current class", "type": "cat", "labels": {**ICL, "below": "< 10 µA", "above": "> 1 A"}, "order": ["below", *ICLS, "above"]},
        {"key": "source", "label": "Source", "type": "cat", "order": ["sweep sample", "design card"]},
        {"key": "lay", "label": "Layout", "type": "cat", "order": ["complete layout", "unit bank (area estimated)", "sweep (area estimated)"]},
        {"key": "pvt", "label": "15-PVT re-simulation", "type": "cat",
         "order": ["within 5 % over 15 PVT", "not within 5 % over 15 PVT", "not re-simulated", "design card (15 PVT)"]},
        {"key": "front", "label": "Pareto front (any trade-off)", "type": "cat", "order": ["Pareto-front point", "off-front sample", "design card"]},
    ]
    presets = [{"label": EXP[p][0], "x": EXKEYS[p][0], "y": EXKEYS[p][1], "color": "topo", "facet": "", "pareto": False} for p in EXP]
    presets += [{"label": "Per-topology clouds (R_on vs area)", "x": "ron_wc", "y": "area", "color": "source", "facet": "topo", "pareto": True},
                {"label": "PVT robustness of the fronts", "x": "ron_wc", "y": "pvt_ratio", "color": "pvt", "logy": False, "facet": "", "pareto": False},
                {"label": "Bootstrap C_B knob vs R_on·area", "x": "kcb", "y": "fom_ra", "color": "topo", "logx": False, "facet": "", "pareto": False},
                {"label": "Supply comparison", "x": "ron_wc", "y": "area", "color": "supply", "facet": "topo", "pareto": False}]
    explorer = {"type": "explorer", "title": "Interactive design-space explorer", "src": write("data/dse_explorer.json", {"columns": col}),
                "dims": dims, "x": "ron_wc", "y": "area", "color": "topo", "filters": ["topo", "supply", "cls", "source", "lay", "pvt", "front", "coverage", "ron_wc"],
                "highlight": "delivered", "highlight_label": "Delivered design cards", "design_key": "design", "label_key": "label", "stage_group": "design",
                "hover": ["topo", "ron_wc", "ws", "imax", "coverage", "area", "fom_ra", "t_on", "e_vdd", "q_absmax", "thd_db", "pvt_ratio", "knobs"],
                "presets": presets, "height": 560,
                "intro": "All 2,025 sweep samples (schematic simulations) plus the 125 delivered design cards. The explorer follows the global options: at "
                         "**Pre-PEX** it shows the sweep and the cards' schematic results; at a post-PEX stage it shows each card's best available "
                         f"extraction ≤ the selected stage (at Full post-PEX with *fill from earlier stage*: the {N_COMPLETE} complete-cell extractions plus "
                         f"the {N_UNIT} unit-bank extractions; without it only the {N_COMPLETE}). The sweep has no layout and is hidden at post-PEX stages. "
                         "Pick any axes, colour, symbol and facet, filter by chips / ranges and toggle the Pareto front; click a highlighted point to "
                         "open its card.",
                "caption": "Area of the sweep samples is **estimated** from the sample's device and MIM area with a per-topology fit to the delivered cards' "
                           f"layouts; the cards' areas are drawn layout areas for {N_COMPLETE} cards and the generator's multi-bank estimates for the other "
                           f"{N_UNIT} (see *Layout* in the filters). I_max rating = 5 % VDD / R_on,wc for samples and cards alike; *I_max class target* is "
                           "the card's sizing current. Metrics marked *(cards)* exist only for the design cards. Knobs that a topology does not have are empty."}
    blocks = [{"type": "note", "tone": "info",
               "text": "The design-space **sweep** (2,025 schematic samples, sweep fronts, design clouds, front-design tables) is shown at the *Pre-PEX* "
                       "stage: [show the schematic sweep](#/switch?page=explore&stage=pre). Post-PEX stages show only the design cards (the sweep has no "
                       "layout)."}]
    nfr = len({i for k, v in SW["fronts"].items() if not k.endswith("|all") for i in v})
    blocks.append({"type": "stats", "title": "Design-space sweep", "stage": "pre", "alt": "exst", "items": [
        {"label": "designs simulated", "value": f"{SW['n_total']:,}"}, {"label": "with a valid signal range", "value": f"{SW['n_feasible']:,}"},
        {"label": "Pareto-front points", "value": f"{nfr:,}"},
        {"label": "front points within 5 % of R_on over all 15 PVT corners", "value": f"{SW['n_robust']}/{SW['n_front']}" if SW.get("n_front") else "—"}]})
    for V in PAGE_VIEWS[1:]:
        sub = [c for c in done if V["cards"](c)]
        blocks.append({"type": "stats", "title": "Post-PEX design cards", "stage": V["stage"], "alt": "exst", "items": [
            {"label": "design cards with post-PEX results (this view)", "value": str(len(sub))},
            {"label": "meet the R_on target post-PEX (grade A/B)", "value": str(sum(1 for c in sub if c["mp"].get("grade") in ("A", "B")))}],
            "caption": "Front counts for the selected trade-off and supply are shown with each view below. " + V["note"]})
    blocks.append(explorer)
    tabs = []
    for p in EXP:
        inner = []
        for v in META["vdds"]:
            inner.append({"label": f"{v} V", "vdd": v, "blocks": combo_pre(p, v) + combo_post(p, v, PAGE_VIEWS[1]) + combo_post(p, v, PAGE_VIEWS[2])})
        tabs.append({"label": EXP[p][0], "blocks": [{"type": "note", "tone": "muted", "text": EXP[p][1]},
                                                     {"type": "tabs", "id": "exvdd", "label": "V<sub>DD</sub>", "default": 1, "tabs": inner}]})
    blocks.append({"type": "section", "title": "Trade-off views", "intro": "The fixed views of the original explorer page: pick the trade-off, then the "
                   "supply (default 3.3 V). The global *Simulation stage* selects the data: Pre-PEX = the sweep fronts with the cards' schematic results; "
                   f"Partial post-PEX = the post-PEX fronts of all 125 extracted cards ({N_UNIT} unit-bank + {N_COMPLETE} complete-cell extractions); "
                   f"Full post-PEX = the {N_COMPLETE} complete cells only.", "blocks": [{"type": "tabs", "id": "tradeoff", "tabs": tabs}]})
    intro = ("## Design-space explorer\n\nA random and structured known-design-point sweep of all thirteen topologies over both supplies: log-uniform switch "
             "width (1 µm – 100 mm, so every load-current class from 10 µA to 1 A is covered) and continuous knobs — P/N ratio, bootstrap / pump capacitor "
             "ratio, auxiliary-device scale, driver fan-out, switch channel length, dummy and shunt size. Every sample is simulated on the compute farm with "
             "the card testbenches: R<sub>on</sub>(V<sub>in</sub>) at tt 27 °C and ss 125 °C, the 2-D off-leakage map at ff 125 °C, timing and switching "
             "energy, charge injection, off-isolation and tracking THD. Its current rating follows from its worst R<sub>on</sub> over its on-range "
             "(I<sub>max</sub> = 5 % VDD / R<sub>on,wc</sub>), exactly as the design cards are sized. Layout area is estimated from the sample's device and "
             "MIM area with a per-topology fit to the delivered cards' real layouts. Every Pareto-front design was re-simulated at all 5 corners × 3 "
             "temperatures (filled vs open markers).")
    return {"intro": intro, "blocks": blocks}


# ============================================================================= page: methodology
FLOW = [
    "**Device characterisation.** gm/I<sub>D</sub> lookup tables of the five GF180 devices used here (`nfet_03v3`, `pfet_03v3`, 6 V thick-oxide "
    "`nfet_06v0`/`pfet_06v0` and the 6 V native `nfet_06v0_nvt`) from Cadence Spectre sweeps (commercial `YI-141-SM064 Rev 9` models) over L, "
    "V<sub>SB</sub>, V<sub>DS</sub>, V<sub>GS</sub>; on-state gate capacitance per µm from AC simulation.",
    "**Topology generators.** Every device of a cell scales with the main switch width W<sub>s</sub>: bootstrap / pump capacitors as a multiple "
    "k<sub>CB</sub> of the switch gate capacitance, auxiliary devices as fractions of it, and a tapered inverter chain (fan-out ≈ 4 from a minimum "
    "inverter on `ck`) for every gate load. Each device carries a gm/I<sub>D</sub> target, the inversion level at its intended on-state bias.",
    "**Reference characterisation and sizing.** Each topology, supply and knob value (P/N ratio, k<sub>CB</sub>) is simulated once at W<sub>s</sub> = "
    "100 µm over 5 corners × 3 temperatures (R<sub>on</sub> vs input, 2-D off-leakage map). For a current class, the on-range is where the worst-PVT "
    "R<sub>on</sub> stays within 3× its minimum, W<sub>s</sub> is the smallest width with R<sub>on</sub> ≤ 5 % VDD / I<sub>max</sub> over that range, "
    "and the off-range is the largest window in which every (in, out) pair leaks less than 0.1 % of I<sub>max</sub>. The knob with the smallest "
    "estimated area among those reaching ≥ 97 % of the best range is kept.",
    "**Verification loop.** The chosen cell is rebuilt at its width and re-simulated over PVT; minimum-size parts that do not scale are compensated by "
    "re-scaling until the target holds.",
    "**Characterisation.** Full testbench suite (below) at tt 27 °C and the timing / charge-injection benches at all 15 PVT points; device stress "
    "against the oxide rating.",
    "**Schematics.** SVG with W/L, model and gm/I<sub>D</sub> target → simulated (the LUT evaluated at the V<sub>GS</sub>/V<sub>SB</sub> the "
    "transient bench produced).",
    "**Layout.** Switch devices as EM-sized power arrays: gLayout `multiplier` finger rows in a tap ring, interleaved met3 source/drain stripes (width "
    "set by the DC current per stripe), met4+met5 spines as the high-current pins, gate stripes and body straps beside the ring. Native devices get "
    "per-row NAT strips with the gate poly bar outside NAT; the bulk-bootstrapped switch sits in an isolated p-well (deep n-well + n-tap ring + "
    "substrate guard ring). Drivers and bootstrap / pump circuitry form an auxiliary slice built by a row floorplanner and negotiated-congestion "
    "router (gLayout `nmos`/`pmos`/`mimcap_array`), replicated N× for the large classes and joined to the arrays through a met4 track channel. Large "
    "switches are folded into mirrored banks stacked vertically (IN / OUT bars on the sides, sized from the load current) and the auxiliary slices "
    "into a grid. Floorplan: one cell width is shared by the banks and the slice grid; for every candidate width the banks are folded to it and the "
    "slice is re-planned to fill its share of it (block sizes from formulas fitted to the gLayout cells), and the smallest cell with an aspect ratio "
    "near 1 wins. Inside a slice the blocks are packed tallest first, side by side in rows, with large drivers folded to the row width; only the "
    "risers that must step aside get a row of the jog band under the first track channel. Verified with the PDK KLayout DRC (variant D) and LVS decks.",
    "**Post-layout (post-PEX) simulation.** Every verified cell is extracted with Magic (device geometry and parasitic capacitances ≥ 0.01 fF to "
    "substrate and coupling; hierarchical, with the finger-row cells flattened); the series resistance of the met3 source/drain stripes is added at "
    "the IN/OUT pins. The extracted netlist runs the same testbench suite on the compute farm — R<sub>on</sub>, the leakage map, timing / energy with "
    "device stress and charge injection at the test level at all 15 PVT points; the charge-injection sweep, isolation and THD at tt 27 °C. Each "
    "extracted device is mapped back to its schematic device (switch arrays by cell name, auxiliary devices by size and connectivity), so the "
    "schematic tab shows the gm/I<sub>D</sub> the extracted circuit actually reaches. The header switch selects schematic or extracted results; the "
    "post-PEX view shows nothing simulated on the schematic, only design data (sizing, test conditions, layout area) is shared. *(On the hub the "
    "header switch is the global Simulation stage option: Pre-PEX = schematic; post-PEX = extracted — Full post-PEX for the cards whose "
    "complete cell is drawn and extracted, Partial post-PEX for the multi-bank cards whose unit bank is extracted and scaled to full width.)*",
    "**R<sub>on</sub> points (grades).** Each card is a sample of the design space at one R<sub>on</sub> point, and its result is reported on a fixed "
    "ladder of points rather than as pass / fail: the worst-PVT drop I<sub>max</sub>·R<sub>on</sub> over the valid range, as a fraction of VDD, graded "
    "A ≤ 2 % (precision), B ≤ 5 % (the design target), C ≤ 10 % (relaxed), D ≤ 20 % (loose), or below D. The grade is computed from the schematic and "
    "from the extracted netlist alike, so the post-PEX view shows which R<sub>on</sub> point a laid-out switch actually reaches; the list filters by grade.",
]
TBS = [
    "**R<sub>on</sub>(V<sub>in</sub>)**: after three warm-up clock cycles the switch is held on while the input ramps 0 → VDD in 4 µs; two copies carry "
    "±0.2·I<sub>max</sub>, R<sub>on</sub> = ΔV / 2I.",
    "**Off leakage**: DC, ck = 0, every (V<sub>in</sub>, V<sub>out</sub>) pair on a 23 × 23 grid; R<sub>off</sub> = VDD / worst leakage.",
    "**t<sub>on</sub> / t<sub>off</sub>**: ck step to 90 % / 10 % of the load current, input at the centre of the valid range, resistive load drawing I<sub>max</sub>.",
    "**Switching energy**: charge from VDD over one full on/off cycle (drivers, bootstrap / pump), and separately the charge drawn from the input source.",
    "**Charge injection**: hold capacitor C<sub>H</sub> = 20 × switch gate capacitance (≥ 1 pF); pedestal × C<sub>H</sub> at 7 levels over the valid "
    "range and over PVT at the centre level.",
    "**Off-isolation** into the resistive load and **C<sub>off</sub>** at the output (AC, off state).",
    "**Tracking distortion**: 1 MHz sine over 90 % (and 40 %) of the valid range into the resistive load.",
    "**Stress**: largest gate-to-channel and drain-source voltage of every device held for ≥ 1 ns, against the oxide rating (3.63 V for 3.3 V devices, "
    "6.6 V for 6 V devices).",
]


def page_method():
    G = load("data/gmid.json")
    devs = list(G)
    tabs = []
    for vsb in ("0.0", "0.9", "1.8"):
        tr = lambda key, f=1: [{"x": G[d]["curves"][vsb]["vgs"], "y": [v * f for v in G[d]["curves"][vsb][key]], "name": d, "mode": "lines",  # noqa: E731
                                "line": {"color": TCOL[i], "width": 2}} for i, d in enumerate(devs)]
        tabs.append({"label": f"V<sub>SB</sub> = {vsb} V", "blocks": [{"type": "section", "cols": 2, "blocks": [
            {"type": "chart", "data": tr("gm_id"), "layout": {"xaxis": {"title": {"text": "|V_GS| (V)"}}, "yaxis": {"title": {"text": "gm/Id (1/V)"}}, "hovermode": "closest"}},
            {"type": "chart", "data": tr("id_w", 1e6), "layout": {"xaxis": {"title": {"text": "|V_GS| (V)"}},
                                                               "yaxis": {"type": "log", "title": {"text": "Id/W (µA/µm), |V_DS| = max(V_GS, 1 V)"}}, "hovermode": "closest"}}]}]})
    D = META["devices"]
    blocks = [
        {"type": "section", "cols": 2, "blocks": [
            {"type": "markdown", "title": "Flow", "text": "\n".join(f"{i + 1}. {s}" for i, s in enumerate(FLOW))},
            {"type": "markdown", "title": "Testbenches", "text": "\n".join(f"- {s}" for s in TBS)}]},
        {"type": "table", "title": "Devices", "search": False, "csv": False,
         "columns": [{"key": "m", "label": "Model", "type": "text"}, {"key": "d", "label": "Description", "type": "text", "wrap": True},
                     {"key": "l", "label": "L<sub>min</sub>", "unit": "µm"}, {"key": "w", "label": "W<sub>min</sub>", "unit": "µm"},
                     {"key": "r", "label": "Rating", "unit": "V"}],
         "rows": [{"m": k, "d": v["desc"], "l": v["lmin"], "w": v.get("wmin"), "r": v["rating"]} for k, v in D.items()]},
        {"type": "section", "title": "gm/I<sub>D</sub> of the GF180 devices (saturation, L<sub>min</sub>)",
         "intro": f"From `data/gmid.json` (W = {G[devs[0]]['w_um']} µm, L = L<sub>min</sub> per device).",
         "blocks": [{"type": "tabs", "id": "vsb", "label": "V<sub>SB</sub>", "tabs": tabs}]},
        {"type": "downloads", "title": "Data files",
         "items": [{"label": "Card index (meta + all cards, pre/post metrics)", "file": "data/index.json"},
                   {"label": "Design-space sweep (2,025 samples + Pareto fronts)", "file": "data/sweep.json"},
                   {"label": "gm/I<sub>D</sub> lookup curves", "file": "data/gmid.json"},
                   {"label": "Explorer data as shown on the hub (sweep + cards, columnar)", "src": "hub/data/dse_explorer.json"}]},
        {"type": "note", "tone": "muted",
         "text": f"generated {META['generated']} · GF180MCU-D (5LM, MIM M4/M5) · Cadence Spectre (YI-141-SM064 Rev 9) · KLayout DRC/LVS · source on "
                 "[GitHub](https://github.com/aicdb/switch-gen-gemini4) (private)"},
    ]
    return {"intro": "## Methodology\n\nHow the cards are sized, characterised, laid out and re-simulated, the testbenches, and the device data behind them.", "blocks": blocks}


# ============================================================================= component
pages = [("overview", "Overview", page_overview()), ("compare", "Topology comparison", page_compare()),
         ("explore", "Design-space explorer", page_explore()), ("method", "Methodology", page_method())]
gen = META.get("generated", "")
try:
    ymd, hm = gen.split()[0], gen.split()[1]
    generated = f"{ymd}T{hm}:00Z"
except (IndexError, ValueError):
    generated = gen
r2r = lambda view: sum(1 for c in done if (mv(c, view).get("coverage") or 0) > 0.97)  # noqa: E731
shrink = sum(1 for c in done if c.get("mp") and c["mp"]["coverage"] < c["m"]["coverage"] - 1e-9)
comp = {
    "schema": "aicdb-hub/2",
    "id": "switch",
    "name": "Switches",
    "title": "GF180 Analog Switch Generator",
    "summary": "Thirteen analog / sampling-switch topologies (pass-gates, transmission gates, T-switches, clock-boosted and bootstrapped NMOS incl. "
               "DNW bulk-bootstrapped and charge-cancelled ADC S/H switches) at 1.8 V and 3.3 V for five load-current classes (10 µA … 1 A). Each is "
               "sized for an I_max·R_on drop ≤ 5 % of VDD over its valid signal range at all 15 PVT corners, laid out with gLayout (KLayout DRC/LVS) and "
               f"re-simulated from Magic PEX ({N_COMPLETE} complete cells = full post-PEX; {N_UNIT} wide switches drawn and extracted as one unit bank "
               f"scaled to full width = partial post-PEX, with estimated cell areas). {len(na_cards)} grid positions (3.3 V-oxide bootstrap at 3.3 V) "
               "are not applicable (oxide overstress).",
    "technology": "gf180mcuD",
    "generated": generated,
    "stats": [{"label": "design-space sweep points", "value": f"{SW['n_total']:,}"},
              {"label": "not applicable (n/a)", "value": str(len(na_cards))},
              {"label": "rail-to-rail pre / post-PEX", "value": f"{r2r('pre')} / {r2r('post')}"},
              {"label": "valid range shrinks post-PEX", "value": str(shrink)},
              {"label": "complete-cell / unit-bank layouts", "value": f"{N_COMPLETE} / {N_UNIT}"},
              {"label": "R_on grade A/B pre / post", "value": f"{sum(1 for c in done if c['m'].get('grade') in ('A', 'B'))} / "
                                                         f"{sum(1 for c in done if (c.get('mp') or {}).get('grade') in ('A', 'B'))}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=s or None, digits=dg if dg != 3 else None, better=b,
                                       desc=METRIC_DESC.get(k)).items() if v is not None}
                for k, l, u, s, dg, b, _f, _sc in METRICS],
    "axes": {
        "topology": {"label": "Topology", "values": [{"id": t, "label": SHORT.get(t, t)} for t in ORDER]},
        "class": {"label": "Current class", "values": [{"id": k, "label": icl_of(k)} for k in ICLS]},
    },
    "matrix": {"rows": ["topology"], "cols": ["class"], "metrics": ["coverage", "ron_wc"],
               "status": {"metric": "coverage", "good": 97, "warn": 0.01},
               "presets": [{"label": "Valid range & area", "metrics": ["coverage", "area"]},
                           {"label": "R_on worst PVT & drop", "metrics": ["ron_wc", "drop"]},
                           {"label": "R_on @ test level & flatness", "metrics": ["ron_vtest", "ron_flat"]},
                           {"label": "Charge injection & pedestal", "metrics": ["q_absmax", "ped_absmax"]},
                           {"label": "Turn-on time & energy", "metrics": ["t_on", "e_vdd"]},
                           {"label": "Isolation & THD", "metrics": ["iso_10m", "thd"]},
                           {"label": "R_on·C_off & C_off", "metrics": ["ron_coff", "coff"]},
                           {"label": "Leakage & R_off", "metrics": ["leak_wc", "roff_wc"]},
                           {"label": "Device stress & gate drive", "metrics": ["stress", "vgs_on"]}]},
    "card_metrics": ["coverage", "ron_vtest", "ron_wc", "t_on", "t_off", "e_vdd", "q_vtest", "q_absmax", "area"],
    "cards_group_by": "class",
    "pages": [{"id": pid, "title": title, "src": write(f"pages/{pid}.json", doc)} for pid, title, doc in pages],
    "designs": designs,
}
(out / "component.json").write_text(json.dumps(r5(comp), separators=(",", ":"), ensure_ascii=False))
print(f"switch adapter: {len(designs)} designs, {len(pages)} pages, {len(written)} generated files; "
      f"{len(na_cards)} n/a cards listed on the overview page: {', '.join(c['key'] for c in na_cards)}", file=sys.stderr)
