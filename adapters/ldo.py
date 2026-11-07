#!/usr/bin/env python3
"""Bootstrap hub adapter for ldo-gen-gemini4 (schema aicdb-hub/2).

usage: ldo.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus the
generated pages, design-detail documents and data files under OUT_DIR (referenced as "hub/...").
Copy to scripts/export_hub.py in the repo (with OUT_DIR = docs/hub) and run it as the last step
of the docs build.

What it ports (see adapters/ldo.inventory.md for the item-by-item checklist):
  * Designs view: metrics / axes (topology, polarity, Vreg, load class) / matrix + presets that
    replace the old "Cell Metric" selector / card metrics.  The old Schematic / Post-layout switch
    is the hub's global simulation stage (pre = schematic, full = Magic-extracted whole cell).
  * One detail document per design with the old Overview / Schematic / Simulation / Robustness /
    Layout tabs (stage alternatives where the old page switched with the level).
  * Pages: Database explorer (db.json + the post-layout database), Methodology (verbatim prose +
    gm/Id charts from gmid.json), About & data notes (old hero text, stats, caveats).

Honesty rules applied (from the repo's own site builder, ldogen/site.py):
  * `results` only carry simulated quantities.  Fields the builder computes from other fields
    (dropout @ Imin = 0.35 x dropout @ Imax, line reg @ Imin = 0.75 x, current capability =
    1.25 x Imax, 10 pF / 100 pF load-step numbers = scaled nominal step, start-up overshoot =
    0.4 x step overshoot, Iq @ Imin/10 = 0.95 x Iq, output range = V_REF sweep limits) and the
    noise placeholder (35 uVrms / 180 nV/rtHz on every card, the noise bench returned no data)
    are shown in the detail pages marked with a dagger / double dagger, never in `results`.
  * PVT records carry GM = 12 dB, zeta = 0.68, ring_ok = true as constants of the builder; they are
    not displayed as results.  Nominal all_sat / ring_ok of the schematic view are constants too;
    the computed char.metrics.ring_ok is used instead.
  * Explored-point columns of db.json that the builder copies from the delivered card (zeta, Rout,
    dropout, line reg, PSRR, current capability, area, GM) are not attributed to the candidate
    points; delivered cards carry their own values.
  * PM values below -180 deg (phase-unwrap artefacts such as -360 / -612 deg) are excluded from
    worst-case statistics and reported as invalid samples.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DOCS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
IDX = json.loads((DOCS / "data" / "index.json").read_text())
META, CARDS = IDX["meta"], IDX["cards"]
DB = json.loads((DOCS / "data" / "db.json").read_text()) if (DOCS / "data" / "db.json").is_file() else None
GMID = json.loads((DOCS / "data" / "gmid.json").read_text()) if (DOCS / "data" / "gmid.json").is_file() else None

ARCH_ORDER = list(META["arch_order"])
ARCH_SHORT = dict(META["arch_short"])
ICLS = list(META["iclasses"].keys())
PM_ROBUST_MC = 30.0          # repo: mc_pass = worst MC PM >= 30 deg (ldogen/site.py)
PM_INVALID = -180.0          # PM below this is a phase-unwrap artefact, not a margin
DAG, DDAG = "†", "‡"
PAL = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d",
       "#ea580c", "#4f46e5", "#0d9488", "#9333ea"]
TECH = "gf180mcuD"


# ----------------------------------------------------------------------------- formatting (ports of the old app.js helpers)
def r5(v):
    """round floats to 5 significant digits, recursively"""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return 0.0 if v == 0 else float(f"{v:.5g}")
    if isinstance(v, list):
        return [r5(x) for x in v]
    if isinstance(v, dict):
        return {k: r5(x) for k, x in v.items()}
    return v


def jsn(x: float) -> str:
    """String(Number) of a JS number (shortest repr, no trailing .0)"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    s = repr(float(x))
    return s


def prec(v: float, d: int) -> float:
    return float(f"{v:.{d}g}")


PFX = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")]


def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def si(v, unit="", d=3):
    if not isnum(v):
        return "—"
    if v == 0:
        return f"0 {unit}"
    r = prec(v, d)
    a = abs(r)
    for m, p in PFX:
        if a >= m * 0.9995:
            return f"{jsn(prec(r / m, d))} {p}{unit}"
    return f"{jsn(prec(v / 1e-15, d))} f{unit}"


def num(v, d=1):
    if not isnum(v) or v <= -998:
        return "—"
    return f"{v:.{d}f}"


def ppm(v):
    return "—" if v is None else f"{num(v * 1e3, 2)} mV/V"


ICLS_LABEL = {"lt10n": "<10 nA (1–10 nA)", "lt100n": "10–100 nA", "lt1u": "100 nA–1 µA", "1u_10u": "1–10 µA",
              "10u_100u": "10–100 µA", "100u_1m": "100–1000 µA", "1m_10m": "1–10 mA", "10m_100m": "10–100 mA"}
ICLS_SHORT = {"lt10n": "<10 nA", "lt100n": "10–100 nA", "lt1u": "0.1–1 µA", "1u_10u": "1–10 µA", "10u_100u": "10–100 µA",
              "100u_1m": "0.1–1 mA", "1m_10m": "1–10 mA", "10m_100m": "10–100 mA"}


def icls_label(k):
    if k in ICLS_LABEL:
        return ICLS_LABEL[k]
    lo, hi = META["iclasses"].get(k, [None, None])
    return f"{si(lo, 'A')}–{si(hi, 'A')}" if lo is not None else k


def icls_short(k):
    return ICLS_SHORT.get(k) or icls_label(k)


TIER = {"pos": "Positive (VSS-Ref)", "neg": "Negative (VDD-Ref)", "all": "All (Pos + Neg)"}
POL_LABEL = {"pos": "Positive (VSS-ref)", "neg": "Negative (VDD-ref)"}


def opa_link(cid):
    """reused opa-gen cells: link to the hub's op-amp tab, filtered by the cell id (both load sets)"""
    return f"[`{cid}`](#/opa?q={cid})"


def sa_link(cid):
    return f"[`{cid}`](#/sa?q={cid})"


def cell_link(c):
    if c.get("ea"):
        return opa_link(c["ea"]["id"])
    if c.get("comp"):
        return sa_link(c["comp"]["id"])
    return ""


# ----------------------------------------------------------------------------- block helpers
def S(b, st, alt):
    b = dict(b)
    b["stage"], b["alt"] = st, alt
    return b


def sec(title, blocks, **kw):
    return {"type": "section", "title": title, "blocks": [b for b in blocks if b], **kw}


def mdb(text, **kw):
    return {"type": "markdown", "text": text, **kw}


def note(text, tone="info", **kw):
    return {"type": "note", "text": text, "tone": tone, **kw}


def chart(title, data, layout=None, caption=None, height=None, **kw):
    b = {"type": "chart", "title": title, "data": r5(data), "layout": r5(layout or {})}
    if caption:
        b["caption"] = caption
    if height:
        b["height"] = height
    b.update(kw)
    return b


def table(title, columns, rows, caption=None, **kw):
    b = {"type": "table", "title": title, "columns": columns, "rows": r5(rows)}
    if caption:
        b["caption"] = caption
    b.update(kw)
    return b


def status(ok, yes="pass", no="fail"):
    return {"v": yes if ok else no, "s": "good" if ok else "bad"}


XLOG = {"type": "log", "title": {"text": "Frequency (Hz)"}, "exponentformat": "SI"}
TIME = {"title": {"text": "time (s)"}, "exponentformat": "SI"}
LEG = {"orientation": "h", "y": 1.14, "x": 0}


def line(x, y, name, **kw):
    t = {"type": "scatter", "mode": "lines", "x": x, "y": y, "name": name}
    t.update(kw)
    return t


# ----------------------------------------------------------------------------- per-stage view of a design (port of dview())
def view(d, st):
    c, opt = d["card"], d.get("opt") or {}
    if st == "pre":
        ch = d.get("char")
        if not ch:
            return None
        nom = dict(opt.get("nominal") or {})
        m = ch.get("metrics") or {}
        # builder constants in opt.nominal (ring_ok / all_sat): use the computed char value for ring_ok
        nom["ring_ok"] = m.get("ring_ok", nom.get("ring_ok"))
        return dict(st="pre", pex=False, char=ch, nom=nom, pvt=opt.get("pvt") or [], mc=opt.get("mc") or [],
                    pvt_pass=opt.get("pvt_pass"), mc_pass=opt.get("mc_pass"), robust=c.get("robust"))
    p = d.get("post") or {}
    ch = p.get("char")
    if not ch:
        return None
    m = ch.get("metrics") or {}
    nom = {k: m.get(k) for k in ("pm_min", "gm_min", "pm_light", "ugb_min", "ugb_max", "a0_min", "verr_max",
                                 "iq_min_load", "iq_max_load", "iq_zero", "ring_ok", "zeta_min")}
    nom["os_max"] = m.get("step_overshoot_pct")
    return dict(st="full", pex=True, char=ch, nom=nom, pvt=p.get("pvt") or [], mc=p.get("mc") or [],
                pvt_pass=p.get("pvt_pass"), mc_pass=p.get("mc_pass"), robust=(c.get("post") or {}).get("robust"))


def pvt_worst(pvt):
    v = [p["r"]["pm_min"] for p in pvt if p.get("r", {}).get("ok") and isnum(p["r"].get("pm_min")) and p["r"]["pm_min"] > PM_INVALID]
    return min(v) if v else None


def mc_valid(mc):
    return [s for s in mc if s.get("ok") and isnum(s.get("pm_min")) and s["pm_min"] > PM_INVALID]


def mc_invalid(mc):
    return [s for s in mc if s.get("ok") and isnum(s.get("pm_min")) and s["pm_min"] <= PM_INVALID]


def mc_worst(mc):
    v = [s["pm_min"] for s in mc_valid(mc)]
    return min(v) if v else None


def noise_placeholder(ch):
    n = ((ch or {}).get("curves") or {}).get("noise") or {}
    return not (n.get("f") and n.get("vn"))


# ----------------------------------------------------------------------------- metrics (simulated quantities only)
METRICS = [
    # key, label, unit, si, better, digits, extractor(m) -> value
    ("ugb", "UGB", "Hz", True, "high", 3, lambda m: m.get("ugb_min")),
    ("ugb_max", "UGB max", "Hz", True, "high", 3, lambda m: m.get("ugb_max")),
    ("pm", "PM (nominal)", "°", False, "high", 3, lambda m: m.get("pm_min")),
    ("pm_light", "PM light load", "°", False, "high", 3, lambda m: m.get("pm_light")),
    ("gm", "GM", "dB", False, "high", 3, lambda m: m.get("gm_min")),
    ("a0", "DC loop gain", "dB", False, "high", 3, lambda m: m.get("a0_min")),
    ("pm_pvt", "PM worst PVT", "°", False, "high", 3, None),
    ("pm_mc", "PM worst MC", "°", False, "high", 3, None),
    ("iq", "Iq", "A", True, "low", 3, lambda m: m.get("iq") or None),
    ("iq_max", "Iq @ Imax", "A", True, "low", 3, lambda m: m.get("iq_max_load") or None),
    ("eff", "Efficiency @ Imax", "%", False, "high", 4, lambda m: None if m.get("current_eff") is None else m["current_eff"] * 100),
    ("zeta", "Damping ζ", "", False, "high", 3, lambda m: m.get("zeta_min")),
    ("step_os", "Small-step overshoot", "%", False, "low", 3, lambda m: m.get("step_overshoot_pct")),
    ("verr", "VOUT error", "V", True, "low", 3, lambda m: None if m.get("verr_max") is None else abs(m["verr_max"])),
    ("dropout", "Dropout", "V", True, "low", 3, lambda m: m.get("dropout_imax")),
    ("line_reg", "Line reg", "mV/V", False, "low", 3, lambda m: None if m.get("line_reg_imax") is None else abs(m["line_reg_imax"]) * 1e3),
    ("load_reg", "Load reg", "V", True, "low", 3, lambda m: None if m.get("load_reg_mv") is None else abs(m["load_reg_mv"]) * 1e-3),
    ("rout", "Rout", "Ω", True, "low", 3, lambda m: None if m.get("load_reg") is None else abs(m["load_reg"])),
    ("psrr_1k", "PSRR 1 kHz", "dB", False, "high", 3, lambda m: m.get("psrr_1k_imax")),
    ("psrr_100k", "PSRR 100 kHz", "dB", False, "high", 3, lambda m: m.get("psrr_100k_imax")),
    ("psrr_dc", "PSRR DC", "dB", False, "high", 3, lambda m: m.get("psrr_dc_imax")),
    ("psrr_worst", "PSRR worst", "dB", False, "high", 3, lambda m: m.get("psrr_worst_imax")),
    ("droop", "Step droop", "V", True, "low", 3, lambda m: None if m.get("undershoot_mv_nom") is None else m["undershoot_mv_nom"] * 1e-3),
    ("overshoot", "Release overshoot", "V", True, "low", 3, lambda m: None if m.get("overshoot_mv_nom") is None else m["overshoot_mv_nom"] * 1e-3),
    ("settle", "Settling", "s", True, "low", 3, lambda m: None if m.get("settle_up_us_nom") is None else m["settle_up_us_nom"] * 1e-6),
    ("fom", "FoM", "s", True, "low", 3, lambda m: None if m.get("fom_ps") is None else m["fom_ps"] * 1e-12),
    ("line_tran", "Line-step peak", "V", True, "low", 3, lambda m: None if m.get("line_tran_pk_mv") is None else m["line_tran_pk_mv"] * 1e-3),
    ("startup", "Start-up", "s", True, "low", 3, lambda m: None if m.get("startup_us") is None else m["startup_us"] * 1e-6),
    ("area", "Area", "µm²", False, "low", 4, None),
]
MKEYS = [x[0] for x in METRICS]


def stage_result(V, d, area, key):
    m = V["char"].get("metrics") or {}
    out = {}
    for k, *_rest, fn in METRICS:
        if fn is None:
            continue
        v = fn(m)
        out[k] = r5(float(v)) if isnum(v) else None
    out["pm_pvt"] = r5(pvt_worst(V["pvt"]))
    out["pm_mc"] = r5(mc_worst(V["mc"]))
    out["area"] = area
    res = {"metrics": out, "robust": bool(V["robust"])}
    if V["pvt"]:
        res["pvt"] = {"pass": sum(1 for p in V["pvt"] if p.get("pass")), "total": len(V["pvt"])}
    if V["mc"]:
        res["mc"] = {"pass": sum(1 for s in mc_valid(V["mc"]) if s["pm_min"] >= PM_ROBUST_MC), "total": len(V["mc"])}
    notes = []
    if V["st"] == "pre":
        notes.append("Schematic netlist, ngspice")
    else:
        pc = (d["card"].get("post") or {})
        notes.append("Magic flat extraction of the complete LDO cell (devices as drawn, one per finger; MIM caps, poly "
                     "segments and all parasitic capacitances ≥ 0.01 fF; no wire resistance), same benches, PVT and MC re-run"
                     + (f" — {pc['n_mos']:,} extracted transistors, {pc['n_parasitic_c']:,} parasitic capacitors" if pc.get("n_mos") else ""))
    notes.append(f"robust = repo flag (PVT sweep all-stable, worst MC PM ≥ {PM_ROBUST_MC:g}°); PVT count = corners meeting the "
                 f"per-point PM ≥ {META.get('pm_target', 35)}° flag; MC count = samples with PM ≥ {PM_ROBUST_MC:g}°")
    if V["pvt"] and res["pvt"]["pass"] < res["pvt"]["total"] and V["robust"]:
        notes.append(f"the repo marks this design PVT-robust although only {res['pvt']['pass']}/{res['pvt']['total']} corners meet PM ≥ {META.get('pm_target', 35)}° (worst {num(out['pm_pvt'], 1)}°)")
    inv = mc_invalid(V["mc"])
    if inv:
        notes.append(f"{len(inv)} Monte-Carlo sample(s) report an invalid PM ({', '.join(num(s['pm_min'], 1) + '°' for s in inv[:3])}; phase-unwrap artefact) and are excluded from the worst-case PM")
    if not m.get("iq"):
        notes.append("Iq is published as 0 and is omitted")
    res["note"] = "; ".join(notes)
    return res


# ----------------------------------------------------------------------------- detail document builders
def knob_name(k):
    return {"ota": "error amplifier (opa-gen card)", "comp": "comparator (sa-gen cell)", "pin": "error-amp input pair",
            "inv": "inversion target set", "iq": "quiescent-current budget (EA + bias)", "U": "current units",
            "nref": "bias branch units", "nt": "EA tail units", "nc": "cascode branch units", "nab": "adaptive tail-boost units",
            "kab": "pass : sense ratio", "nsf": "buffer bias (× OTA bias current)", "nx": "FVF branch units", "Lin": "L input (µm)",
            "Lcs": "L current sources (µm)", "Lload": "L loads (µm)", "Lcas": "L cascodes (µm)", "Lsf": "L buffer (µm)",
            "gp": "pass-device gm/Id at I_max", "Lp": "pass-device L (µm)", "cc": "compensation capacitor", "rz": "nulling resistor",
            "ccn": "C_C return node"}.get(k, k)


def knob_val(k, v, c):
    if k == "iq":
        return si(v, "A")
    if k == "cc":
        return si(v, "F")
    if k == "rz":
        return si(v, "Ω") if v else "none"
    if k == "pin":
        return "NMOS" if v == "n" else "PMOS"
    if k == "ota":
        return sa_link(v) if c.get("comp") and not c.get("ea") else opa_link(v)
    return jsn(v) if isinstance(v, float) else str(v)


def stat(label, value, sub=""):
    x = {"label": label, "value": value}
    if sub:
        x["sub"] = sub
    return x


def key_results(d, V):
    c, ch, nom = d["card"], V["char"], V["nom"]
    m = ch.get("metrics") or {}
    lay = d.get("layout") or {}
    lt = ((ch.get("curves") or {}).get("load_tran") or {}).get("nom") or {}
    pm_pvt, pm_mc, inv = pvt_worst(V["pvt"]), mc_worst(V["mc"]), mc_invalid(V["mc"])
    mc_txt = f"MC {num(pm_mc, 1)}°" + (f" ({len(inv)} invalid sample{'s' if len(inv) > 1 else ''} {num(inv[0]['pm_min'], 1)}°)" if inv else "")
    items = [
        stat("Quiescent current", si(m.get("iq"), "A") if m.get("iq") else "—",
             f"{si(nom.get('iq_min_load'), 'A')} @ I<sub>min</sub> · {si(nom.get('iq_max_load'), 'A')} @ I<sub>max</sub> · "
             f"{si(nom.get('iq_zero'), 'A')} @ I<sub>min</sub>/10 {DAG}"),
        stat("Current efficiency", f"{num(m['current_eff'] * 100, 2)} %" if m.get("current_eff") else "—", "at I<sub>max</sub>"),
        stat("Worst-case loop bandwidth", si(nom.get("ugb_min"), "Hz"), f"max {si(nom.get('ugb_max'), 'Hz')}"),
        stat("Phase / gain margin", f"{num(nom.get('pm_min'), 1)}° / {num(nom.get('gm_min'), 1)} dB",
             f"PVT {num(pm_pvt, 1)}° · {mc_txt} · light load {num(nom.get('pm_light'), 1)}°"),
        stat("DC loop gain (min)", f"{num(nom.get('a0_min'), 1)} dB"),
        stat("Closed-loop damping", f"ζ {num(nom.get('zeta_min'), 2)}", f"small-step overshoot {num(nom.get('os_max'), 1)} % (worst class corner)"),
        stat("Dropout @ I<sub>max</sub>", f"{num(m['dropout_imax'] * 1e3, 0)} mV" if m.get("dropout_imax") is not None else "—",
             f"@ I<sub>min</sub>: {num(m['dropout_imin'] * 1e3, 0) + ' mV' if m.get('dropout_imin') is not None else '—'} {DAG} (1 % output drop)"),
        stat("Line regulation", ppm(m.get("line_reg_imax")), f"@ I<sub>min</sub>: {ppm(m.get('line_reg_imin'))} {DAG}"),
        stat("Load regulation", f"{num(m.get('load_reg_mv'), 3)} mV", f"{si(abs(m['load_reg']), 'Ω') if isnum(m.get('load_reg')) else '—'} over the class"),
        stat("PSRR @ 1 kHz", f"{num(m.get('psrr_1k_imax'), 1)} dB", f"DC {num(m.get('psrr_dc_imax'), 0)} dB · worst {num(m.get('psrr_worst_imax'), 0)} dB"),
    ]
    if noise_placeholder(ch):
        items.append(stat("Output noise 10 Hz–100 kHz", f"{DDAG} placeholder",
                          f"old site showed {num(m.get('noise_int_10_100k_uv'), 1)} µVrms · {si(m.get('noise_1k'), 'V/√Hz')} @ 1 kHz — "
                          "repo default, the noise bench returned no spectrum"))
    else:
        items.append(stat("Output noise 10 Hz–100 kHz", f"{num(m.get('noise_int_10_100k_uv'), 1)} µVrms", f"{si(m.get('noise_1k'), 'V/√Hz')} @ 1 kHz"))
    items += [
        stat("Load step droop / overshoot", f"{num(m.get('undershoot_mv_nom'), 0)} / {num(m.get('overshoot_mv_nom'), 0)} mV",
             f"I<sub>min</sub>↔I<sub>max</sub>, 1 µs edge, C<sub>L</sub> {si(lt.get('cl', META.get('cl_nom')), 'F')} · settle {num(m.get('settle_up_us_nom'), 1)} µs"),
        stat("FoM (T<sub>R</sub>·I<sub>q</sub>/ΔI)", si(m["fom_ps"] * 1e-12, "s") if isnum(m.get("fom_ps")) else "—", "C<sub>L</sub>·ΔV/ΔI · I<sub>q</sub>/ΔI"),
        stat("Start-up (98 %)", f"{num(m['startup_us'], 1)} µs" if m.get("startup_us") is not None else "—",
             f"overshoot {num(m.get('startup_overshoot_mv'), 0)} mV {DAG} · 10 µs V<sub>IN</sub> ramp"),
        stat("Usable V<sub>OUT</sub> range", f"{num(m['vout_range_lo_imax'], 2)}–{num(m['vout_range_hi_imax'], 2)} V {DAG}" if m.get("vout_range_lo_imax") is not None else "—",
             f"same sizing, V<sub>REF</sub> swept, I<sub>max</sub>, 1 % tracking — {DAG} published as the V<sub>REF</sub> sweep's start/stop, not a measured limit"),
    ]
    if lay.get("area_um2"):
        items.append(stat("Layout area", f"{round(lay['area_um2']):,} µm²", f"{num(lay.get('width_um'), 1)} × {num(lay.get('height_um'), 1)} µm"))
    return S(sec(f"Key results <small>(tt, 27 °C, V<sub>IN</sub> = {jsn(c['vin'])} V)</small>", [{"type": "stats", "items": items}]), V["st"], "keyres")


def spec_checks(d, V):
    c, nom = d["card"], V["nom"]
    m = V["char"].get("metrics") or {}
    o_pvt, o_mc = V["pvt"], V["mc"]
    pm_pvt, pm_mc = pvt_worst(o_pvt), mc_worst(o_mc)
    n_pt = sum(1 for p in o_pvt if p.get("pass"))
    iq = m.get("iq")
    rows = [
        [f"I<sub>q</sub> ≤ budget ({TIER[c['tier']]} class budget, of I<sub>max</sub>)", f"{si(iq, 'A')} ≤ {si(c.get('iq_budget'), 'A')}",
         status(isnum(iq) and isnum(c.get("iq_budget")) and iq <= c["iq_budget"] * 1.0001)],
        [f"PM ≥ {META['pm_nom']}° / GM ≥ {META['gm_nom']} dB at the class corners (tt, 27 °C)", f"{num(nom.get('pm_min'), 1)}° / {num(nom.get('gm_min'), 1)} dB",
         status(isnum(nom.get("pm_min")) and isnum(nom.get("gm_min")) and nom["pm_min"] >= META["pm_nom"] and nom["gm_min"] >= META["gm_nom"])],
        [f"PM ≥ {META['pm_target']}° / GM ≥ {META['gm_robust']} dB at all PVT points ({len(o_pvt)})",
         f"worst {num(pm_pvt, 1)}°" + (f" · {n_pt}/{len(o_pvt)} points meet PM ≥ {META['pm_target']}° (repo flag shown)" if n_pt < len(o_pvt) else ""),
         status(bool(V["pvt_pass"]))],
        [f"PM ≥ {META['pm_target']}° / GM ≥ {META['gm_robust']} dB in all Monte-Carlo samples ({len(o_mc)})",
         f"worst {num(pm_mc, 1)}°" + (f" · {len(mc_invalid(o_mc))} invalid sample(s)" if mc_invalid(o_mc) else ""), status(bool(V["mc_pass"]))],
        ["Closed-loop step rings down, overshoot ≤ 25 % (ζ ≥ 0.4) at all class corners",
         f"max overshoot {num(nom.get('os_max'), 1)} % · ζ<sub>min</sub> {num(nom.get('zeta_min'), 2)}", status(nom.get("ring_ok") is True)],
    ]
    if not V["pex"]:
        rows.append(["All amplifying devices saturated",
                     f"not evaluated — the repo's builder publishes all_sat = {str(nom.get('all_sat')).lower()} on every card",
                     {"v": "n/a", "s": "muted"}])
    verr = nom.get("verr_max")
    rows.append(["|V<sub>OUT</sub> − V<sub>REF</sub>| ≤ 0.5 % over the class", f"{num(verr * 1e3, 2) if isnum(verr) else '—'} mV",
                 status(isnum(verr) and verr <= max(0.005 * c["vout"], 0.005))])
    ver = d.get("verify")
    if ver:
        drc, lvs = (ver.get("drc") or {}), (ver.get("lvs") or {})
        rows.append(["DRC clean (PDK KLayout deck)", "0 violations" if drc.get("clean") else json.dumps(drc.get("violations")), status(bool(drc.get("clean")))])
        rows.append(["LVS match (PDK KLayout deck)", "netlists match" if lvs.get("match") else "mismatch", status(bool(lvs.get("match")))])
    cols = [{"key": "k", "label": "Check", "type": "text", "md": True}, {"key": "v", "label": "Value", "type": "text", "md": True},
            {"key": "s", "label": "Result", "type": "text"}]
    return S(table("Specification checks", cols, rows, csv=False, search=False), V["st"], "specs")


def design_point(d, dbn):
    c, o, D = d["card"], d.get("opt") or {}, d.get("design") or {}
    kn = o.get("knobs") or {}
    rows = [[knob_name("comp" if (k == "ota" and c.get("comp") and not c.get("ea")) else k), knob_val(k, v, c)] for k, v in kn.items()]
    if D:
        rows.append(["reference current I<sub>ref</sub>", si(D.get("iref"), "A")])
    txt = (f"Chosen from {o.get('n_points', 0):,} simulated candidates of this V<sub>IN</sub>/V<sub>OUT</sub>/class target "
           f"({o.get('n_feasible')} nominally feasible within the {TIER[c['tier']]} budget); {o.get('n_pvt_screened')} candidates were PVT-screened.")
    foot = (f"{DAG} The candidate counts are fixed at {o.get('n_points')} / {o.get('n_feasible')} / {o.get('n_pvt_screened')} in the repo's site builder; "
            f"the published database holds **{dbn}** nominally feasible explored point{'s' if dbn != 1 else ''} for this target.") if DB is not None else ""
    blocks = [mdb(txt + (" " + DAG if foot else "")),
              table("", [{"key": "k", "label": "Knob", "type": "text", "md": True}, {"key": "v", "label": "Value", "type": "text", "md": True, "align": "r"}],
                    rows, csv=False, search=False)]
    if D:
        blocks.append({"type": "downloads", "items": [{"label": "netlist.spice", "file": f"designs/{c['key']}/netlist.spice",
                                                         "note": "subckt pins: vin vss vref vout ib"}]})
        if D.get("notes"):
            blocks.append(mdb("<small>" + "<br>".join(D["notes"]) + "</small>"))
    if foot:
        blocks.append(mdb(f"<small>{foot}</small>"))
    return sec("Design point", blocks)


def ea_panel(c):
    ea = c.get("ea")
    if not ea:
        return None
    return sec("Error amplifier — opa-gen cell", [mdb(
        f"The OTA is the opa-gen design card {opa_link(ea['id'])} ({ea.get('name')}, {ea.get('inv')}), used unchanged: its netlist in every "
        f"simulation here, its GDS as a sub-cell of the layout and its own LVS reference. Card figures: I<sub>DD</sub> {si(ea.get('idd'), 'A')}, "
        f"A<sub>0</sub> {num(ea.get('a0_db'), 1)} dB, UGB {si(ea.get('ugb'), 'Hz')} (at the opa-gen design load). "
        f"<small>(The link opens the hub's op-amp tab filtered by this cell id.)</small>")])


def device_rows(d, V):
    D = d.get("design") or {}
    devs = D.get("devs") or []
    if (d["card"].get("family") == "digital"):            # group identical array devices
        g = {}
        for v in devs:
            base = re.sub(r"\d+$", "", v["name"])
            k = (v.get("role"), v.get("model"), v.get("W"), v.get("L"), v.get("nf"), base)
            if k not in g:
                g[k] = dict(v, count=0, name=base)
            g[k]["count"] += 1
        devs = []
        for v in g.values():
            if v["count"] > 1:
                v = dict(v, name=f"{v['name']}* ×{v['count']}", d=re.sub(r"\d+$", "*", v["d"]), g=re.sub(r"\d+$", "*", v["g"]), s=re.sub(r"\d+$", "*", v["s"]))
            devs.append(v)
    ops = (V["char"] or {}).get("op") or {}
    op = ops[max(ops, key=lambda k: float(k))] if ops else {}
    rows = []
    for v in devs:
        nodes = f"{v.get('d')}/{v.get('g')}/{v.get('s')}/{v.get('b')}"
        base = [v["name"], v.get("model"), v.get("role"), v.get("W"), v.get("L"), v.get("nf"), v.get("gmid")]
        if V["pex"]:
            rows.append(base + [nodes])
            continue
        s = op.get(v["name"]) or {}
        idv = abs(s.get("id") or 0)
        if not idv:
            rows.append(base + [None, None, None, None, None, None, {"v": "no op", "s": "muted", "title": "no operating point published for this device"}, nodes])
            continue
        gmid = s["gm"] / idv if isnum(s.get("gm")) else None
        vds, vdsat = abs(s.get("vds") or 0), abs(s.get("vdsat") or 0)
        reg = "triode" if (vds < vdsat * 0.9 and vds < 0.1) else ("WI" if (gmid or 0) > 18 else "MI" if (gmid or 0) > 9 else "SI")
        tone = {"WI": "good", "MI": None, "SI": "warn", "triode": "bad"}[reg]
        rcell = {"v": reg, "s": tone} if tone else reg
        rows.append(base + [gmid, idv, s.get("gm"), (s["gm"] / s["gds"]) if s.get("gds") else None, vds, vdsat, rcell, nodes])
    cols = [{"key": "n", "label": "Dev", "type": "text"}, {"key": "m", "label": "Model", "type": "text"}, {"key": "r", "label": "Role", "type": "text"},
            {"key": "w", "label": "W µm", "digits": 5}, {"key": "l", "label": "L µm", "digits": 3},
            {"key": "nf", "label": "nf", "digits": 4}, {"key": "gt", "label": "gm/Id target", "digits": 3}]
    if not V["pex"]:
        cols += [{"key": "gs", "label": "<b>gm/Id sim</b>", "digits": 3}, {"key": "id", "label": "Id", "unit": "A", "si": True},
                 {"key": "gm", "label": "gm", "unit": "S", "si": True}, {"key": "av", "label": "gm/gds", "digits": 3},
                 {"key": "vds", "label": "|VDS| V", "digits": 3}, {"key": "vdsat", "label": "VDSsat V", "digits": 3},
                 {"key": "reg", "label": "Region", "type": "text"}]
    cols.append({"key": "nodes", "label": "D/G/S/B", "type": "text"})
    return cols, rows


def schematic_tab(d, V_pre, V_full):
    c = d["card"]
    key, base = c["key"], f"designs/{c['key']}"
    dig = c.get("family") == "digital"
    has = lambda f: (DOCS / base / f).is_file()
    tl = has("schematic_tl.svg")
    blocks = []
    pc = c.get("post") or {}
    pex_note = (f"Extracted layout netlist (`pex.spice`, see Files): {pc['n_mos']:,} transistors (one per finger) and "
                f"{pc['n_parasitic_c']:,} parasitic capacitors. Extracted devices carry no schematic names, so there is no "
                "per-device operating point after layout; the table lists the drawn sizes.") if pc.get("n_mos") else ""
    if dig:
        cap = (f"Comparator(s): the sa-gen cell {sa_link(c['comp']['id']) if c.get('comp') else ''} (used unchanged: netlist, GDS sub-cell, LVS "
               "reference); controller macro (NOR SR latch + registers in standard cells), unit current-source cells with power switches and "
               "proportional cells. The controller netlist is in `netlist.spice`; identical array devices are grouped in the table.")
        if has("schematic.svg"):
            blocks.append({"type": "image", "title": "Block schematic", "src": f"{base}/schematic.svg", "caption": cap})
        for st, V in (("pre", V_pre), ("full", V_full)):
            if V:
                cols, rows = device_rows(d, V)
                blocks.append(S(table("Analog devices", cols, rows), st, "devs"))
        return blocks
    if V_pre and has("schematic.svg"):
        cap = (("" if V_pre["char"] else "**Sizing view** — the simulated operating point is added when the characterisation finishes. ")
               + ("Top level: the error amplifier (a sub-cell) is drawn as an op-amp triangle; its transistor-level schematic follows below. " if tl else "")
               + "Each transistor shows W/L (×fingers) and **gm/Id target → simulated** (1/V) at I<sub>load</sub> = I<sub>max</sub>, coloured by operating "
               "region (green weak, blue moderate, orange strong inversion, red triode). Bias nets are connected by name tags; C<sub>L</sub> and I<sub>L</sub> "
               "(dashed) are the external test load. (The old site's hover tool-tips per device are in the device table below.)")
        blocks.append(S({"type": "image", "title": "Schematic with gm/Id annotation", "src": f"{base}/schematic.svg", "caption": cap, "max_height": 900}, "pre", "schem"))
    if V_full and has("schematic_sizing.svg"):
        cap = ("Sizing view: each transistor shows W/L (×fingers) and its gm/Id design target."
               + (" The error amplifier (a sub-cell) is drawn as an op-amp triangle; its transistor-level schematic follows below." if tl else "")
               + (f"\n\n{pex_note}" if pex_note else ""))
        blocks.append(S({"type": "image", "title": "Schematic with gm/Id annotation", "src": f"{base}/schematic_sizing.svg", "caption": cap, "max_height": 900}, "full", "schem"))
    if tl:
        who = (f"the schematic of the opa-gen OTA cell {opa_link(c['ea']['id'])}" if c.get("ea") else
               f"the schematic of the sa-gen comparator cell {sa_link(c['comp']['id'])}" if c.get("comp") else "the schematic of the reused sub-cell")
        blocks.append({"type": "image", "title": "Error-amplifier sub-cell — transistor level", "src": f"{base}/schematic_tl.svg", "max_height": 900,
                       "caption": f"The triangle above expanded: {who} as published on its design card (the cell is used unchanged). "
                                  "<small>The old site's post-layout file `schematic_tl_sizing.svg` is byte-identical to this one.</small>"})
    for st, V, title in (("pre", V_pre, "Device table (operating point at I<sub>max</sub>, tt 27 °C)"), ("full", V_full, "Device table (drawn sizes)")):
        if V:
            cols, rows = device_rows(d, V)
            cap = ("Region: WI gm/Id > 18, MI 9–18, SI < 9, triode |VDS| < 0.9·VDSsat and < 0.1 V (green / plain / orange / red). "
                   "Rows marked *no op* have no published operating point.") if st == "pre" else ""
            blocks.append(S(table(title, cols, rows, caption=cap or None), st, "devs"))
    D = d.get("design") or {}
    pas = [[x["name"], "MIM cap_mim_2f0_m4m5", f"{num(x.get('w'), 1)} × {num(x.get('l'), 1)} µm", si(x.get("Cact"), "F"), f"{x.get('p')} – {x.get('n')}"]
           for x in D.get("caps") or []]
    pas += [[x["name"], "ppolyf_u_1k (high-Rs poly)", f"{x.get('nseg')} × {num(x.get('w'), 1)}/{num(x.get('lseg'), 1)} µm", si(x.get("Ract"), "Ω"), f"{x.get('p')} – {x.get('n')}"]
            for x in D.get("ress") or []]
    if pas:
        blocks.append(table("Passives", [{"key": "n", "label": "Name", "type": "text"}, {"key": "d", "label": "Device", "type": "text"},
                                         {"key": "s", "label": "Size", "type": "text", "align": "r"}, {"key": "v", "label": "Value", "type": "text", "align": "r"},
                                         {"key": "nodes", "label": "Nodes", "type": "text"}], pas, csv=False, search=False))
    return blocks


def sim_section(d, V):
    c, ch = d["card"], V["char"]
    m, C = ch.get("metrics") or {}, ch.get("curves") or {}
    imin, imax = META["iclasses"][c["iclass"]]
    blocks = []
    # loop gain
    tr = []
    for i, x in enumerate(C.get("loop") or []):
        col, nm = PAL[i % len(PAL)], f"{si(x['iload'], 'A', 2)}, {si(x['cl'], 'F', 2)}"
        tr.append(line(x["f"], x["db"], nm, legendgroup=f"g{i}", line={"color": col, "width": 2}, hovertemplate="%{y:.1f} dB"))
        tr.append(line(x["f"], x["ph"], nm, showlegend=False, legendgroup=f"g{i}", xaxis="x2", yaxis="y2",
                       line={"color": col, "width": 2, "dash": "dot"}, hovertemplate="%{y:.0f}°"))
    if tr:
        blocks.append(chart("Loop gain T(f) at the class corners (Tian probe)", tr, {
            "xaxis": {"type": "log", "anchor": "y", "showticklabels": False, "exponentformat": "SI"},
            "xaxis2": {"type": "log", "anchor": "y2", "matches": "x", "title": {"text": "Frequency (Hz)"}, "exponentformat": "SI"},
            "yaxis": {"title": {"text": "|T| (dB)"}, "domain": [0.53, 1], "anchor": "x"},
            "yaxis2": {"title": {"text": "∠T (°)"}, "domain": [0, 0.47], "anchor": "x2"}, "hovermode": "closest", "legend": LEG},
            caption=f"worst PM {num(m.get('pm_min'), 1)}° · GM {num(m.get('gm_min'), 1)} dB · UGB {si(m.get('ugb_min'), 'Hz')}–{si(m.get('ugb_max'), 'Hz')}",
            height=460))
    # loop-gain summary
    rows = []
    rings = ch.get("ring") or []
    for i, x in enumerate(ch.get("stab") or []):
        rg = rings[i] if i < len(rings) else None
        cond = f"I {si(x.get('iload'), 'A', 2)}, C<sub>L</sub> {si(x.get('cl'), 'F', 2)}" + (" <small>(light load)</small>" if isnum(x.get("iload")) and x["iload"] < imin * 0.999 else "")
        derived = i > 0
        os_cell = (f"{num(rg['overshoot_pct'], 1)} %" if rg else "—")
        z_cell = (num(rg["zeta"], 2) if rg else "—")
        if derived and rg:
            os_cell = {"v": os_cell + " " + DAG, "s": "muted", "title": "derived in the repo's builder: 0.85 × the first corner's overshoot"}
            z_cell = {"v": z_cell + " " + DAG, "s": "muted", "title": "builder default / derived, not measured per corner"}
        gm_cell = {"v": num(x.get("gm_db"), 1) + (" " + DAG if len(ch.get("stab")) > 1 else ""), "title": "worst-case GM repeated on every corner by the repo's builder"}
        rows.append([cond, x.get("a0_db"), x.get("ugb"), x.get("pm"), gm_cell, os_cell, z_cell, None if x.get("verr") is None else x["verr"], x.get("iq")])
    brk = (d.get("design") or {}).get("brk")
    blocks.append(table("Loop-gain summary", [
        {"key": "c", "label": "Condition", "type": "text", "md": True}, {"key": "t0", "label": "T₀", "unit": "dB", "digits": 3},
        {"key": "ugb", "label": "UGB", "unit": "Hz", "si": True}, {"key": "pm", "label": "PM", "unit": "°", "digits": 3},
        {"key": "gm", "label": "GM dB", "type": "text", "align": "r"}, {"key": "os", "label": "step OS", "type": "text", "align": "r"},
        {"key": "z", "label": "ζ", "type": "text", "align": "r"}, {"key": "ve", "label": "V<sub>OUT</sub> err", "unit": "V", "si": True},
        {"key": "iq", "label": "I<sub>q</sub>", "unit": "A", "si": True}], rows, csv=False, search=False,
        caption=(f"Loop broken at `{brk[0]}` → `{brk[1]}`" if brk else "Loop broken at the feedback input")
        + "; PM = minimum over all 0 dB crossings. The probe keeps the local compensation loops closed, so every corner is also checked closed-loop: "
          f"a 5 % I<sub>min</sub> load step must ring down with ≤ 25 % overshoot (ζ = second-order equivalent damping). {DAG} = not measured per corner (see tool-tips)."))
    # line regulation / dropout
    L = C.get("line") or {}
    if (L.get("line_imax") or {}).get("vin"):
        blocks.append(chart("Line regulation / dropout", [line(L["line_imax"]["vin"], L["line_imax"]["vout"], "I_max"),
                                                          line(L["line_imin"]["vin"], L["line_imin"]["vout"], "I_min")],
                            {"xaxis": {"title": {"text": "V_IN (V)"}}, "yaxis": {"title": {"text": "V_OUT (V)"}}, "hovermode": "x unified", "legend": LEG},
                            caption=f"dropout {num((m.get('dropout_imax') or 0) * 1e3, 0)} mV @ I<sub>max</sub>, {num((m.get('dropout_imin') or 0) * 1e3, 0)} mV @ I<sub>min</sub> {DAG} · "
                                    f"line reg {ppm(m.get('line_reg_imax'))}. <small>{DAG} dropout @ I<sub>min</sub> = 0.35 × dropout @ I<sub>max</sub> in the repo's builder; "
                                    "the bench floors dropout at 15 mV.</small>"))
    # load regulation
    Ld = C.get("load") or {}
    if Ld.get("il"):
        sel = [i for i, v in enumerate(Ld["il"]) if isnum(v) and v >= imin / 100]
        x = [Ld["il"][i] for i in sel]
        iq_const = len(set(Ld.get("iq") or [])) <= 1
        tr = [line(x, [Ld["vout"][i] for i in sel], "V_OUT")]
        if Ld.get("iq"):
            tr.append(line(x, [Ld["iq"][i] for i in sel], "I_q" + (f" {DAG} (constant: I_q@I_min repeated, not swept)" if iq_const else ""), yaxis="y2",
                           line={"dash": "dot"} if iq_const else {}))
        lo, hi = max(imin / 100, 1e-15), imax * 1.5
        y2 = {"title": {"text": "I_q (A)"}, "overlaying": "y", "side": "right", "exponentformat": "SI"}
        iqv = [v for v in (Ld.get("iq") or []) if isnum(v)]
        if iq_const and iqv and iqv[0] > 0:
            y2["range"] = [0, iqv[0] * 2]      # a constant trace would otherwise autorange to ±1 A (as on the old site)
        blocks.append(chart("Load regulation and I<sub>q</sub> vs load", tr, {
            "xaxis": {"type": "log", "title": {"text": "I_load (A)"}, "exponentformat": "SI", "range": [math.log10(lo), math.log10(hi)]},
            "yaxis": {"title": {"text": "V_OUT (V)"}}, "yaxis2": y2,
            "margin": {"r": 58}, "hovermode": "x unified", "legend": LEG,
            "shapes": [{"type": "rect", "xref": "x", "yref": "paper", "x0": max(imin, lo), "x1": imax, "y0": 0, "y1": 1,
                        "fillcolor": "rgba(37,99,235,0.08)", "line": {"width": 0}, "layer": "below"}]},
            caption=f"ΔV<sub>OUT</sub> {num(m.get('load_reg_mv'), 3)} mV over the class (shaded) · 3 % drop at {si(m.get('imax_cap'), 'A')} {DAG} "
                    "<small>(= 1.25 × I<sub>max</sub> in the repo's builder, not found by simulation)</small>"))
    # PSRR
    P = C.get("psrr") or {}
    if (P.get("psrr_imax") or {}).get("f"):
        blocks.append(chart("PSRR", [line(P["psrr_imax"]["f"], P["psrr_imax"]["db"], "I_max"), line(P["psrr_imin"]["f"], P["psrr_imin"]["db"], "I_min")],
                            {"xaxis": XLOG, "yaxis": {"title": {"text": "PSRR (dB)"}}, "hovermode": "x unified", "legend": LEG},
                            caption=f"@1 kHz {num(m.get('psrr_1k_imax'), 1)} dB · @100 kHz {num(m.get('psrr_100k_imax'), 1)} dB (I<sub>max</sub>)"))
    # noise
    N = C.get("noise") or {}
    if N.get("f") and N.get("vn"):
        blocks.append(chart("Output noise density", [line(N["f"], N["vn"], "output noise")],
                            {"xaxis": XLOG, "yaxis": {"type": "log", "title": {"text": "V/√Hz"}, "exponentformat": "SI"}, "showlegend": False},
                            caption=f"{si(m.get('noise_1k'), 'V/√Hz')} @1 kHz · {num(m.get('noise_int_10_100k_uv'), 1)} µVrms (10 Hz–100 kHz), I<sub>max</sub>"))
    else:
        blocks.append({"type": "note", "tone": "warn", "title": "Output noise density",
                       "text": f"{DDAG} No noise spectrum in the published results (the noise bench returned no data). The old site showed an empty chart and "
                               f"the repo's placeholder defaults {num(m.get('noise_int_10_100k_uv'), 1)} µVrms (10 Hz–100 kHz) / {si(m.get('noise_1k'), 'V/√Hz')} @ 1 kHz, "
                               "which are not simulation results."})
    # load transient
    lt = C.get("load_tran") or {}
    ltr = [line(lt[k]["t"], lt[k]["vout"], f"C_L {si(lt[k].get('cl'), 'F')}", line={"width": 1.6}) for k in ("nom", "min", "max") if (lt.get(k) or {}).get("t")]
    if ltr:
        nomlt = lt.get("nom") or {}
        shapes = [{"type": "line", "x0": x, "x1": x, "yref": "paper", "y0": 0, "y1": 1, "line": {"color": "#94a3b8", "width": 1, "dash": "dot"}}
                  for x in (nomlt.get("t1"), nomlt.get("t2")) if isnum(x)]
        blocks.append(chart("Load transient I<sub>min</sub> ↔ I<sub>max</sub>", ltr, {"xaxis": TIME, "yaxis": {"title": {"text": "V_OUT (V)"}}, "shapes": shapes,
                                                                                        "hovermode": "x unified", "legend": LEG},
                            caption=f"droop / overshoot: C<sub>L</sub> {si(nomlt.get('cl'), 'F')} {num(m.get('undershoot_mv_nom'), 0)}/{num(m.get('overshoot_mv_nom'), 0)} mV · "
                                    f"10 pF {num(m.get('undershoot_mv_min'), 0)}/{num(m.get('overshoot_mv_min'), 0)} mV {DAG} · 100 pF {num(m.get('undershoot_mv_max'), 0)}/{num(m.get('overshoot_mv_max'), 0)} mV {DAG}. "
                                    f"<small>{DAG} only one C<sub>L</sub> was simulated; the repo's builder scales the nominal step (×1.25 / ×0.65) for the other two. "
                                    "Dotted lines: step instants.</small>"))
    # line transient
    LT = C.get("line_tran") or {}
    if LT.get("t"):
        blocks.append(chart("Line transient (V<sub>IN</sub> +10 %, 1 µs edges, I<sub>max</sub>)",
                            [line(LT["t"], LT["vout"], "V_OUT"), line(LT["t"], LT["vin"], "V_IN", yaxis="y2", line={"width": 1.2})],
                            {"xaxis": TIME, "yaxis": {"title": {"text": "V_OUT (V)"}}, "yaxis2": {"title": {"text": "V_IN (V)"}, "overlaying": "y", "side": "right"},
                             "margin": {"r": 50}, "hovermode": "x unified", "legend": LEG},
                            caption=f"peak deviation {num(m.get('line_tran_pk_mv'), 1)} mV"))
    # start-up
    SU = C.get("startup") or {}
    if SU.get("t"):
        blocks.append(chart("Start-up (V<sub>IN</sub>, V<sub>REF</sub>, I<sub>ref</sub> ramp in 10 µs, I<sub>max</sub>)",
                            [line(SU["t"], SU["vin"], "V_IN", line={"width": 1.2}), line(SU["t"], SU["vout"], "V_OUT")],
                            {"xaxis": TIME, "yaxis": {"title": {"text": "V"}}, "hovermode": "x unified", "legend": LEG},
                            caption=f"98 % in {num(m.get('startup_us'), 1)} µs · overshoot {num(m.get('startup_overshoot_mv'), 0)} mV {DAG} "
                                    "<small>(= 0.4 × load-step overshoot in the repo's builder)</small>"))
    # output range
    VR = C.get("vref") or {}
    if VR.get("vref"):
        same = VR.get("vout_imin") == VR.get("vout_imax")
        tr = [line(VR["vref"], VR["vout_imax"], "I_max")]
        if VR.get("vout_imin") and not same:
            tr.append(line(VR["vref"], VR["vout_imin"], "I_min"))
        tr.append(line([0, c["vin"]], [0, c["vin"]], "ideal", line={"color": "#94a3b8", "width": 1, "dash": "dot"}))
        blocks.append(chart("Output range: V<sub>OUT</sub> vs V<sub>REF</sub>", tr, {"xaxis": {"title": {"text": "V_REF (V)"}}, "yaxis": {"title": {"text": "V_OUT (V)"}},
                                                                                    "hovermode": "x unified", "legend": LEG},
                            caption=f"tracking within 1 %: {num(m.get('vout_range_lo_imax'), 2)}–{num(m.get('vout_range_hi_imax'), 2)} V @ I<sub>max</sub>, "
                                    f"{num(m.get('vout_range_lo_imin'), 2)}–{num(m.get('vout_range_hi_imin'), 2)} V @ I<sub>min</sub> {DAG} "
                                    "<small>(the published limits are the V<sub>REF</sub> sweep's start/stop"
                                    + ("; the I<sub>min</sub> curve is a copy of the I<sub>max</sub> sweep and is not drawn separately" if same else "") + ")</small>"))
    if ch.get("errors"):
        blocks.append(sec("Bench warnings", [mdb("<br>".join(f"**{k}**: {v}" for k, v in ch["errors"].items()))]))
    return S(sec("Simulation" + (" — post-layout (extracted netlist)" if V["pex"] else " — schematic"), blocks, cols=2), V["st"], "sim")


def pvt_cell(p, o_vout):
    if not p:
        return "—"
    r = p.get("r") or {}
    if p.get("vin", 99) < o_vout + 0.1:
        return {"v": f"in dropout (n/a)<br><small>PM {num(r.get('pm_min'), 1)}° · err {num((r.get('verr_max') or 0) * 1e3, 1)} mV</small>", "s": "muted",
                "title": "V_IN below V_OUT + 100 mV: the regulator is in dropout"}
    if not r.get("ok"):
        return {"v": "sim failed", "s": "bad", "title": str(r.get("err") or "")}
    ok = isnum(r.get("pm_min")) and r["pm_min"] >= META["pm_target"] and (r.get("gm_min") or 0) >= META["gm_robust"] and r.get("ring_ok") is not False
    return {"v": f"<b>{num(r.get('pm_min'), 1)}°</b><br><small>UGB {si(r.get('ugb_min'), 'Hz')} · I<sub>q</sub> {si(r.get('iq_min_load'), 'A')} · err {num((r.get('verr_max') or 0) * 1e3, 1)} mV</small>",
            "s": "good" if ok else "bad", "title": f"repo per-point pass flag: {str(p.get('pass')).lower()}"}


def robust_section(d, V):
    o = d.get("opt") or {}
    pvt, mc = V["pvt"], V["mc"]
    vin0, vout0 = o.get("vin", d["card"]["vin"]), o.get("vout", d["card"]["vout"])
    nomV = [p for p in pvt if abs(p["vin"] - vin0) < 1e-6]
    ext = [p for p in pvt if abs(p["vin"] - vin0) >= 1e-6]
    corners = list(dict.fromkeys(p["corner"] for p in nomV))
    temps = list(dict.fromkeys(p["temp"] for p in nomV))
    cols = [{"key": "c", "label": "Corner", "type": "text"}] + [{"key": f"t{i}", "label": f"{t} °C", "type": "text", "md": True, "align": "r"} for i, t in enumerate(temps)]
    rows = [[cn] + [pvt_cell(next((p for p in nomV if p["corner"] == cn and p["temp"] == t), None), vout0) for t in temps] for cn in corners]
    blocks = [table(f"PVT corners (V<sub>IN</sub> = {jsn(vin0)} V) — worst PM over the 4 class corners", cols, rows, csv=False, search=False)]
    if ext:
        blocks.append(table("Supply extremes", [{"key": "c", "label": "Corner", "type": "text"}, {"key": "t", "label": "Temp", "type": "text"},
                                                {"key": "v", "label": "V<sub>IN</sub>", "unit": "V", "digits": 3},
                                                {"key": "p", "label": "PM", "type": "text", "md": True, "align": "r"}],
                            [[p["corner"], f"{p['temp']} °C", p["vin"], pvt_cell(p, vout0)] for p in ext], csv=False, search=False))
    n_pass = sum(1 for p in pvt if p.get("pass"))
    blocks.append(mdb(
        f"<small>Pass criterion: PM ≥ {META['pm_target']}°, GM ≥ {META['gm_robust']} dB and a closed-loop small step ringing down with ≤ 25 % overshoot (ζ ≥ 0.4) "
        f"everywhere, and |V<sub>OUT</sub> − V<sub>REF</sub>| ≤ 3 % at nominal V<sub>IN</sub> (the hot fast corners are limited by pass-device leakage at the "
        f"lowest load). **{n_pass}/{len(pvt)}** points carry the repo's per-point pass flag; the repo's overall PVT flag is "
        f"**{'pass' if V['pvt_pass'] else 'fail'}**. Not shown: the published PVT records carry GM = 12 dB, ζ = 0.68 and ring_ok = true as fixed "
        "constants of the repo's site builder (identical for every corner and design), so the old site's “PM / 12 dB · ζ 0.68” badges are reduced to "
        "the simulated PM, UGB, I<sub>q</sub> and output error.</small>"))
    ok = mc_valid(mc)
    inv = mc_invalid(mc)
    pm = [s["pm_min"] for s in ok]
    ve = [s["verr"] * 1e3 for s in mc if s.get("ok") and isnum(s.get("verr"))]

    def st(a):
        n = len(a) or 1
        mu = sum(a) / n
        return mu, math.sqrt(sum((v - mu) ** 2 for v in a) / n)
    mcb = []
    if pm:
        mu, sd = st(pm)
        mcb.append(chart(f"Monte-Carlo: worst-case phase margin ({len(mc)} samples, global + mismatch)",
                         [{"type": "histogram", "x": pm, "marker": {"line": {"color": "#ffffff", "width": 1.5}}, "hovertemplate": "%{x}: %{y}<extra></extra>"}],
                         {"xaxis": {"title": {"text": "PM (°)"}}, "yaxis": {"title": {"text": "samples"}}, "showlegend": False, "hovermode": "closest"},
                         caption=f"min {num(min(pm), 1)}° · mean {num(mu, 1)}° · σ {num(sd, 2)}°"
                                 + (f" · {len(inv)} sample(s) with an invalid PM ({', '.join(num(s['pm_min'], 1) + '°' for s in inv[:3])}) excluded" if inv else "")
                                 + f" · {sum(1 for v in pm if v >= PM_ROBUST_MC)}/{len(mc)} samples ≥ {PM_ROBUST_MC:g}° (repo MC criterion)"))
    if ve:
        mv, sv = st(ve)
        mcb.append(chart("Monte-Carlo: output error",
                         [{"type": "histogram", "x": ve, "marker": {"line": {"color": "#ffffff", "width": 1.5}}, "hovertemplate": "%{x}: %{y}<extra></extra>"}],
                         {"xaxis": {"title": {"text": "V_OUT − V_REF (mV)"}}, "yaxis": {"title": {"text": "samples"}}, "showlegend": False, "hovermode": "closest"},
                         caption=f"mean {num(mv, 2)} mV · σ {num(sv, 2)} mV. <small>The old site titled this “output error at I<sub>min</sub>”; the repo's builder "
                                 "fills it from the I<sub>max</sub> output-error samples.</small>"))
    if not mcb:
        mcb.append(note("Monte-Carlo not ready yet — the flow is still running for this design.", "muted"))
    blocks.append(sec("", mcb, cols=2))
    return S(sec("Robustness" + (" — post-layout (extracted netlist)" if V["pex"] else " — schematic"), blocks), V["st"], "rob")


def layout_section(d):
    c, L, Vf = d["card"], d.get("layout"), d.get("verify")
    key, base = c["key"], f"designs/{c['key']}"
    if not L:
        return [note("Layout not ready yet — the flow is still running for this design.", "muted")]
    gds = f"{base}/{key}.gds.gz"
    items = []
    if Vf:
        items.append({"label": "DRC", "value": "clean" if Vf["drc"].get("clean") else f"violations: {json.dumps(Vf['drc'].get('violations'))}", "s": "good" if Vf["drc"].get("clean") else "bad"})
        items.append({"label": "LVS", "value": "match" if Vf["lvs"].get("match") else "mismatch", "s": "good" if Vf["lvs"].get("match") else "bad"})
    else:
        items += [{"label": "DRC", "value": "pending"}, {"label": "LVS", "value": "pending"}]
    items += [{"label": "Size", "value": f"{num(L.get('width_um'), 1)} × {num(L.get('height_um'), 1)} µm = {round(L.get('area_um2') or 0):,} µm²"},
              {"label": "Nets", "value": f"{len(L.get('nets') or [])} (schematic nets: {', '.join(sorted(L.get('nets') or []))})"},
              {"label": f"Routed terminals {DAG}", "value": str(L.get("n_stubs"))}]
    dls = []
    for lbl, f in (("GDS (.gz)", f"{key}.gds.gz"), ("LVS netlist", "lvs_reference.spice"), ("Extracted (LVS)", "extracted.cir"), ("Post-layout netlist (PEX)", "pex.spice")):
        if (DOCS / base / f).is_file() and (lbl != "Extracted (LVS)" or Vf) and (lbl != "Post-layout netlist (PEX)" or d.get("post")):
            dls.append({"label": lbl, "file": f"{base}/{f}"})
    tiers = L.get("tiers") or 1
    blocks = []
    if (DOCS / gds).is_file():
        blocks.append({"type": "layout", "gds": gds, "max_height": 640,
                       "caption": "Rendered from the GDS by the hub (the old site's pan/zoom layout SVG is not republished); click to open the GDS in the repository."})
    blocks += [{"type": "kv", "items": items, "cols": 2},
               {"type": "downloads", "items": dls},
               mdb("<small>Pins (METAL2 labels): vdd, vss, vref, vout, vfb, ib. Note: C<sub>L</sub> is off-chip testbench load and is not part of the physical "
                   "layout; on-chip MIM capacitors implement only internal loop compensation (C<sub>C</sub>).</small>"),
               {"type": "kv", "cols": 3, "items": [
                   [f"Floorplan {DAG}", f"{tiers} tier{'s' if tiers > 1 else ''} · aspect {num(L['aspect'], 2) if L.get('aspect') else '—'} <small>(each tier: NMOS row · met4 channel · PMOS row)</small>"],
                   [f"Interdigitated pairs {DAG}", (", ".join(L.get("interdigitated") or []) or "—") + " <small>(ABAB fingers in a shared tap ring)</small>"],
                   [f"Mirror-symmetric pairs {DAG}", (", ".join(L.get("mirrored_pairs") or []) or "—") + " <small>(placed and routed as mirror images)</small>"]],
                "caption": f"{DAG} The tier count, the pair descriptions and the routed-terminal count (4 × devices) are fixed by the repo's site builder for every card; "
                           "the aspect ratio comes from the layout."}]
    return [sec("Layout (gLayout, GF180MCU-D)", blocks)]


def verif_label(c, V):
    if c["status"].get("sim") == "no solution":
        return "no solution", "bad"
    if V is None:
        return "post-layout pending", "muted"
    if V["robust"]:
        return "PVT + MC robust", "good"
    if V["pvt_pass"]:
        return "PVT only", "warn"
    return "nominal only", "warn"


def status_kv(d, V, st):
    c = d["card"]
    s = c.get("status") or {}
    lbl, tone = verif_label(c, V)
    items = [{"label": "Verification", "value": lbl, "s": tone}]
    if st == "pre":
        items.append({"label": "Simulation", "value": {"done": "Sim ✓", "failed": "Sim ✗"}.get(s.get("sim"), "Sim …"),
                      "s": {"done": "good", "failed": "bad"}.get(s.get("sim"), "muted")})
    else:
        items.append({"label": "Simulation", "value": "Post-layout sim ✓" if V else "Post-layout sim …", "s": "good" if V else "muted"})
    items.append({"label": "Layout", "value": {"done": "Layout ✓", "failed": "Layout ✗"}.get(s.get("layout"), "Layout …"),
                  "s": {"done": "good", "failed": "bad"}.get(s.get("layout"), "muted")})
    if s.get("drc") is not None:
        items.append({"label": "DRC", "value": "✓" if s["drc"] else "✗", "s": "good" if s["drc"] else "bad"})
    if s.get("lvs") is not None:
        items.append({"label": "LVS", "value": "✓" if s["lvs"] else "✗", "s": "good" if s["lvs"] else "bad"})
    return S({"type": "kv", "title": "Status", "items": items, "cols": 5}, st, "status")


# --- digital LDO family (app.js tabOverviewD / tabSimD / tabRobustD); no published card uses it today
def digital_tabs(d, V):
    c, o, ch = d["card"], d.get("opt") or {}, V["char"] or {}
    n, k, mo, D = ch.get("nom") or {}, o.get("knobs") or {}, o.get("model") or {}, d.get("design") or {}
    st = V["st"]
    ov = [stat("Quiescent current", si(n.get("iq"), "A"), "comparator + controller + bias" if V["pex"] else f"model estimate {si(mo.get('iq'), 'A')} · comparator + controller + bias"),
          stat("Clock", si(k.get("fclk"), "Hz"), "highest f<sub>clk</sub> the I<sub>q</sub> budget allows (≤ f<sub>max</sub>/2 of the comparator)"),
          stat("Steady-state ripple", f"{num(n.get('ripple_imax_mv'), 1)} mV", f"@ I<sub>max</sub> · {num(n.get('ripple_imin_mv'), 1)} mV @ I<sub>min</sub> · LCO period {num(n.get('lco_period_cycles'), 1)} cycles"),
          stat("DC error", f"{num(n.get('verr_imax_mv'), 1)} mV", f"@ I<sub>max</sub> · {num(n.get('verr_imin_mv'), 1)} mV @ I<sub>min</sub>"),
          stat("Load step droop / overshoot", f"{num(n.get('undershoot_mv'), 0)} / {num(n.get('overshoot_mv'), 0)} mV", f"I<sub>min</sub>↔I<sub>max</sub>, 1 µs edge · settle {num(n.get('settle_up_cycles'), 0)} cycles"),
          stat("Array", f"{D.get('nunits') or '—'} × {si(D.get('iu'), 'A')}", f"{k.get('n')}{'-bit binary' if c['arch'] == 'dbin' else ' thermometer cells'} + {k.get('kp')} P cells · margin {k.get('margin')}")]
    specs = [[f"I<sub>q</sub> ≤ {si(c.get('iq_budget'), 'A')} ({TIER[c['tier']]} of I<sub>max</sub>)", si(n.get("iq"), "A"), status(isnum(n.get("iq")) and n["iq"] <= (c.get("iq_budget") or 0) * 1.05)],
             ["Regulates at I<sub>min</sub> and I<sub>max</sub> (|error| ≤ 3 %, tt 27 °C)", f"{num(n.get('verr_imin_mv'), 1)} / {num(n.get('verr_imax_mv'), 1)} mV", status(bool(ch.get("nom_pass")))],
             ["Bounded limit cycle (ripple < 20 % V<sub>OUT</sub>) at C<sub>L</sub> = 10 / 100 pF", ", ".join(f"{si(x.get('cl'), 'F')}: {num(x.get('ripple_imax_mv'), 0)} mV" for x in ch.get("cl") or []), status(bool(ch.get("cl_pass")))],
             [f"Regulates with bounded ripple at all PVT points ({len(ch.get('pvt') or [])})", "", status(bool(ch.get("pvt_pass")))],
             [f"Regulates with bounded ripple in all Monte-Carlo samples ({len(ch.get('mc') or [])})", "", status(bool(ch.get("mc_pass")))]]
    spec_cols = [{"key": "k", "label": "Check", "type": "text", "md": True}, {"key": "v", "label": "Value", "type": "text", "md": True}, {"key": "s", "label": "Result", "type": "text"}]
    over = [S(sec("Key results <small>(transistor-level transient, tt 27 °C)</small>", [{"type": "stats", "items": ov}]), st, "keyres"),
            S(table("Specification checks", spec_cols, specs, csv=False, search=False,
                    caption="A clocked bang-bang loop has no small-signal phase margin; its stability criterion is a bounded limit cycle (no growing oscillation, "
                            "ripple well below V<sub>OUT</sub>) that regulates the DC level, checked over C<sub>L</sub>, PVT and Monte-Carlo."), st, "specs")]
    cv = n.get("curve") or {}
    sim = []
    if cv.get("t"):
        sim.append(chart("Transient: start-up, I<sub>min</sub> → I<sub>max</sub> → I<sub>min</sub> (tt 27 °C)",
                         [line(cv["t"], cv["vout"], "V_OUT", line={"width": 1.2}), line(cv["t"], cv["il"], "I_load", yaxis="y2", line={"width": 1.2})],
                         {"xaxis": TIME, "yaxis": {"title": {"text": "V_OUT (V)"}}, "yaxis2": {"title": {"text": "I_load (A)"}, "overlaying": "y", "side": "right", "exponentformat": "SI"}, "margin": {"r": 58}},
                         caption=f"ripple {num(n.get('ripple_imin_mv'), 1)} / {num(n.get('ripple_imax_mv'), 1)} mV · droop {num(n.get('undershoot_mv'), 0)} mV · I<sub>q</sub> {si(n.get('iq'), 'A')}", height=440))
    sim.append(table("Load capacitance", [{"key": "cl", "label": "C<sub>L</sub>", "unit": "F", "si": True}, {"key": "a", "label": "ripple @I<sub>max</sub>", "unit": "mV"},
                                          {"key": "b", "label": "ripple @I<sub>min</sub>", "unit": "mV"}, {"key": "e", "label": "error", "unit": "mV"},
                                          {"key": "dr", "label": "droop", "unit": "mV"}, {"key": "iq", "label": "I<sub>q</sub>", "unit": "A", "si": True}],
                     [[x.get("cl"), x.get("ripple_imax_mv"), x.get("ripple_imin_mv"), x.get("verr_imax_mv"), x.get("undershoot_mv"), x.get("iq")] for x in [n] + list(ch.get("cl") or [])], csv=False))

    def row(x):
        s = ({"v": "timed out", "s": "warn"} if x.get("timed_out") else {"v": "sim failed", "s": "bad"} if x.get("failed")
             else {"v": "pending" if V["pex"] else "lost", "s": "muted"} if x.get("lost") else status(bool(x.get("regulates")), "regulates", "fails"))
        return [x.get("corner"), x.get("temp"), x.get("vin"), x.get("seed"), s, x.get("ripple_imax_mv"), f"{num(x.get('verr_imin_mv'), 1)} / {num(x.get('verr_imax_mv'), 1)} mV", x.get("undershoot_mv"), x.get("iq")]
    rcols = [{"key": "c", "label": "corner", "type": "text"}, {"key": "t", "label": "T", "unit": "°C"}, {"key": "v", "label": "V<sub>IN</sub>", "unit": "V"},
             {"key": "s", "label": "seed"}, {"key": "st", "label": "status", "type": "text"}, {"key": "r", "label": "ripple", "unit": "mV"},
             {"key": "e", "label": "error I<sub>min</sub>/I<sub>max</sub>", "type": "text"}, {"key": "d", "label": "droop", "unit": "mV"}, {"key": "iq", "label": "I<sub>q</sub>", "unit": "A", "si": True}]
    rob = [table("PVT corners", rcols, [row(x) for x in ch.get("pvt") or []]), table("Monte-Carlo (global + mismatch, transistor level)", rcols, [row(x) for x in ch.get("mc") or []])]
    return over, [S(sec("Simulation", sim), st, "sim")], [S(sec("Robustness", rob), st, "rob")]


def detail_doc(d, dbn):
    c = d["card"]
    Vp, Vf = view(d, "pre"), view(d, "full")
    pc = c.get("post") or {}
    blocks = [note(f"{DAG} = value computed by the repo's site builder from other quantities or fixed by it (not simulated for this design); "
                   f"{DDAG} = placeholder default (the bench produced no data). Such values are shown as on the old site for completeness but "
                   "are never part of the results table above. Switch **Simulation stage** in the top bar between *Pre-PEX* (old “Schematic”) "
                   "and *Full post-PEX* (old “Post-layout”).", "muted")]
    if Vf:
        blocks.append(dict(stage="full", **note("**Post-layout view** — every result on this page is simulated on the Magic-extracted netlist of the layout (devices as drawn, "
                             "parasitic capacitances ≥ 0.01 fF)" + ("; the controller macro keeps its event-driven model" if c.get("family") == "digital" else "") + "."
                             + (f" {pc['n_mos']:,} extracted transistors (fingers), {pc['n_parasitic_c']:,} parasitic capacitors." if pc.get("n_mos") else ""), "good")))   # no alt: shown only at full post-PEX
    for st, V in (("pre", Vp), ("full", Vf)):
        blocks.append(status_kv(d, V, st))
    if c.get("family") == "digital":
        ov, sim, rob = [], [], []
        for V in (Vp, Vf):
            if V:
                a, b, x = digital_tabs(d, V)
                ov += a
                sim += b
                rob += x
        ov.append(design_point(d, dbn))
    else:
        ov = [key_results(d, V) for V in (Vp, Vf) if V]
        if ea_panel(c):
            ov.append(ea_panel(c))
        ov.append(sec("", [spec_checks(d, V) for V in (Vp, Vf) if V]))
        ov.append(design_point(d, dbn))
        sim = [sim_section(d, V) for V in (Vp, Vf) if V]
        rob = [robust_section(d, V) for V in (Vp, Vf) if V]
    tabs = [{"label": "Overview", "blocks": ov}, {"label": "Schematic", "blocks": schematic_tab(d, Vp, Vf)},
            {"label": "Simulation", "blocks": sim}, {"label": "Robustness", "blocks": rob}, {"label": "Layout", "blocks": layout_section(d)}]
    blocks.append({"type": "tabs", "tabs": tabs})
    return {"blocks": blocks}


# ----------------------------------------------------------------------------- designs
order = {a: i for i, a in enumerate(ARCH_ORDER)}
cards = sorted(CARDS, key=lambda c: (order.get(c["arch"], 99), c["vin"], ICLS.index(c["iclass"]) if c["iclass"] in ICLS else 99))
db_count = Counter(DB["cols"]["key"]) if DB else Counter()

designs, skipped, details = [], [], {}
vouts = []
tot_parc = tot_mos = 0
for c in cards:
    key = c["key"]
    base = f"designs/{key}"
    if not (DOCS / base / "data.json").is_file():
        skipped.append((c, None))
        continue
    d = json.loads((DOCS / base / "data.json").read_text())
    Vp, Vf = view(d, "pre"), view(d, "full")
    if c["status"].get("sim") == "no solution" or not (Vp or Vf):
        skipped.append((c, d))
        continue
    lay = d.get("layout") or {}
    area = r5(float(lay["area_um2"])) if lay.get("area_um2") else None
    results = {}
    if Vp:
        results["pre"] = stage_result(Vp, d, area, key)
    if Vf:
        results["full"] = stage_result(Vf, d, area, key)
    pc = c.get("post") or {}
    tot_parc += pc.get("n_parasitic_c") or 0
    tot_mos += pc.get("n_mos") or 0
    if c["vout"] not in vouts:
        vouts.append(c["vout"])
    files = {k: f"{base}/{v}" for k, v in (("schematic", "schematic.svg"), ("gds", f"{key}.gds.gz"), ("netlist", "netlist.spice"),
                                            ("pex_netlist", "pex.spice"), ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json"))
             if (DOCS / base / v).is_file()}
    sub = "error-amplifier (opa-gen OTA)" if c.get("ea") else "comparator (sa-gen)" if c.get("comp") else "sub-cell"
    images = [{"label": lbl, "src": f"{base}/{fn}"} for lbl, fn in (("Sizing view (post-layout)", "schematic_sizing.svg"),
                                                                    (f"Reused {sub} — transistor level", "schematic_tl.svg"))
              if (DOCS / base / fn).is_file()]
    downloads = [{"label": "KLayout LVS-extracted netlist", "file": f"{base}/extracted.cir"}] if (DOCS / base / "extracted.cir").is_file() else []
    kn = (d.get("opt") or {}).get("knobs") or {}
    D = d.get("design") or {}
    reuse = c.get("ea") or c.get("comp") or {}
    params = {"Reused cell": f"{reuse.get('id')} ({'opa-gen' if c.get('ea') else 'sa-gen'})" if reuse.get("id") else None,
              "Error-amp input pair": {"n": "NMOS", "p": "PMOS"}.get(c.get("pin")),
              "Iq budget": si(c.get("iq_budget"), "A") if c.get("iq_budget") else None,
              "Inversion target": kn.get("inv"),
              "Pass gm/Id at Imax": f"{jsn(kn['gp'])} V⁻¹" if isnum(kn.get("gp")) else None,
              "Pass L": f"{jsn(kn['Lp'])} µm" if isnum(kn.get("Lp")) else None,
              "Cc": si(kn.get("cc"), "F") if isnum(kn.get("cc")) else None,
              "Rz": (si(kn["rz"], "Ω") if kn["rz"] else "none") if isnum(kn.get("rz")) else None,
              "Iref": si(D.get("iref"), "A") if isnum(D.get("iref")) else None,
              "Loop break": f"{D['brk'][0]} → {D['brk'][1]}" if D.get("brk") else None,
              "Testbench CL (class)": si(((((d.get("char") or {}).get("curves") or {}).get("load_tran") or {}).get("nom") or {}).get("cl"), "F") or None,
              "Extracted transistors": pc.get("n_mos"), "Parasitic capacitors (PEX)": pc.get("n_parasitic_c")}
    params = {k: v for k, v in params.items() if v not in (None, "", "—")}
    s = c.get("status") or {}
    ver = d.get("verify") or {}
    drc = (ver.get("drc") or {}).get("clean", s.get("drc"))
    lvs = (ver.get("lvs") or {}).get("match", s.get("lvs"))
    lo_hi = META["iclasses"][c["iclass"]]
    summary = (f"**{c['arch_name']}** · V<sub>IN</sub> {jsn(c['vin'])} V · V<sub>OUT</sub> {jsn(c['vout'])} V · I<sub>load</sub> {icls_label(c['iclass'])} · "
               f"{TIER[c['tier']]} (I<sub>q</sub> ≤ {si(c.get('iq_budget'), 'A')}) · C<sub>L</sub> {si(META['cl_range'][0], 'F')}–{si(META['cl_range'][1], 'F')} "
               f"(testbench range)" + (f" · reuses {cell_link(c)}" if cell_link(c) else ""))
    details[key] = detail_doc(d, db_count.get(key, 0))
    designs.append({
        "id": key,
        "title": f"{c['arch_short']} · {jsn(c['vin'])} → {jsn(c['vout'])} V · {icls_label(c['iclass'])}",
        "summary": summary,
        "technology": TECH,
        "vdd": c["vin"],
        "axes": {"topology": c["arch"], "polarity": c["tier"], "vout": jsn(c["vout"]), "class": c["iclass"]},
        "tags": [t for t in [c.get("arch_name"), *(c.get("tags") or [])] if t],
        "physical": {"drc": drc, "lvs": lvs, "pex": bool(Vf and (DOCS / base / "pex.spice").is_file()) or None,
                     "area_um2": area, "width_um": lay.get("width_um"), "height_um": lay.get("height_um")},
        "results": results,
        "params": params,
        "files": files,
        "images": images,
        "downloads": downloads,
        "detail": f"hub/designs/{key}.json",
    })


# ----------------------------------------------------------------------------- pages
def wjson(rel, obj):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


n_cards = len(CARDS)
n_sol = sum(1 for c in CARDS if c["status"].get("sim") != "no solution")
n_rob = sum(1 for c in CARDS if c.get("robust"))
n_rob_post = sum(1 for c in CARDS if (c.get("post") or {}).get("robust"))
n_sim = sum(1 for c in CARDS if c["status"].get("sim") == "done")
n_sim_post = sum(1 for c in CARDS if (c.get("post") or {}).get("char"))
n_lay = sum(1 for c in CARDS if c["status"].get("drc") and c["status"].get("lvs"))
n_cand = sum(c.get("n_points") or 0 for c in CARDS) // 2
n_targets = sum(len(v) for v in META["vouts"].values()) * len(ICLS)

# --- Database explorer
DBM = [  # key, label, unit, si, log, better
    ("iq", "Quiescent current I_q", "A", True, True, "low"),
    ("ugb", "Loop bandwidth UGB", "Hz", True, True, "high"),
    ("pm", "Worst-case phase margin", "°", False, False, "high"),
    ("zeta", "Closed-loop damping ζ", "", False, False, "high"),
    ("a0", "Minimum DC loop gain T0", "dB", False, False, "high"),
    ("lreg", "Load regulation |ΔV_OUT| over the class", "V", True, True, "low"),
    ("lreg_r", "Output resistance |ΔV_OUT/ΔI|", "Ω", True, True, "low"),
    ("do_max", "Minimum dropout @ I_max", "V", True, True, "low"),
    ("do_min", "Dropout @ I_min † (0.35 × @ I_max)", "V", True, True, "low"),
    ("linreg", "Line regulation |ΔV_OUT/ΔV_IN|", "mV/V", False, True, "low"),
    ("psrr1k", "PSRR @ 1 kHz (I_max)", "dB", False, False, "high"),
    ("psrr100k", "PSRR @ 100 kHz (I_max)", "dB", False, False, "high"),
    ("icap", "Current capability † (1.25 × I_max)", "A", True, True, "high"),
    ("area", "Area", "µm²", False, True, "low"),
    ("vout", "Output voltage V_OUT", "V", False, False, None),
    ("verr", "Output error |V_OUT − V_REF|", "V", True, True, "low"),
]
BEST_MAX = {"pm", "zeta", "a0", "psrr1k", "psrr100k", "ugb", "icap"}
PER_POINT = {"iq", "ugb", "pm", "a0", "lreg", "verr", "vout"}     # db.json columns that really vary per explored point
cols = defaultdict(list)


def add_row(**kw):
    kw["arch_i"] = ARCH_ORDER.index(kw["arch"]) + 1 if kw.get("arch") in ARCH_ORDER else None
    for k in ("stage", "src", "arch", "arch_i", "pol", "vin_c", "vdd", "cls", "pin", "design", "delivered", "label", "target", *[x[0] for x in DBM]):
        cols[k].append(kw.get(k))


def pos(v):
    return v if isnum(v) and v > 0 else None


def absn(v):
    return abs(v) if isnum(v) else None


def card_row(c, m, st, extra):
    add_row(stage=st, src="delivered", arch=c["arch"], pol=c["tier"], vin_c=jsn(c["vin"]), vdd=c["vin"], cls=c["iclass"], pin=c.get("pin"),
            design=c["key"], delivered=(st == "pre"), target=c["key"],
            label=f"{c['arch_short']} {jsn(c['vin'])}→{jsn(c['vout'])} V, {icls_label(c['iclass'])} — {c['key']}",
            iq=pos(m.get("iq")), ugb=m.get("ugb_min"), pm=m.get("pm_min"), zeta=m.get("zeta_min"), a0=m.get("a0_min"),
            lreg=None if m.get("load_reg_mv") is None else abs(m["load_reg_mv"]) * 1e-3, lreg_r=absn(m.get("load_reg")),
            do_max=pos(m.get("dropout_imax")), do_min=pos(m.get("dropout_imin")),
            linreg=None if m.get("line_reg_imax") is None else abs(m["line_reg_imax"]) * 1e3,
            psrr1k=m.get("psrr_1k_imax"), psrr100k=m.get("psrr_100k_imax"), icap=pos(m.get("imax_cap")), area=extra.get("area"),
            vout=c["vout"], verr=absn(m.get("verr_max")))


card_by_key = {c["key"]: c for c in CARDS}
dmap = {x["id"]: x for x in designs}
if DB:
    C = DB["cols"]
    archs, icl = DB["archs"], DB["iclasses"]
    for i in range(len(C["key"])):
        a = archs[C["arch"][i]]
        k = C["key"][i]
        cc = card_by_key.get(k, {})
        add_row(stage="pre", src="explored", arch=a, pol=a.split("_")[0], vin_c=jsn(C["vin"][i]), vdd=C["vin"][i], cls=icl[C["icls"][i]],
                pin=C["pin"][i], design=None, delivered=False, target=k if k in dmap else None,
                label=f"{ARCH_SHORT.get(a, a)} {jsn(C['vin'][i])}→{jsn(C['vout'][i])} V, {icls_label(icl[C['icls'][i]])} — candidate of {k}",
                iq=pos(C["iq"][i]), ugb=C["ugb"][i], pm=C["pm"][i], a0=C["a0"][i],
                lreg=None if C["lreg"][i] is None else abs(C["lreg"][i]) * 1e-3, vout=C["vout"][i],
                verr=None if C["verr"][i] is None else abs(C["verr"][i]) * 1e-3)
for x in designs:
    c = card_by_key[x["id"]]
    d = json.loads((DOCS / "designs" / x["id"] / "data.json").read_text())
    if d.get("char"):
        card_row(c, d["char"]["metrics"], "pre", {"area": x["physical"]["area_um2"]})
    if (d.get("post") or {}).get("char"):
        card_row(c, d["post"]["char"]["metrics"], "full", {"area": x["physical"]["area_um2"]})
explore = {"columns": {k: r5(v) for k, v in cols.items()}}
wjson("data/explore.json", explore)
n_explored_rows = sum(1 for s in cols["src"] if s == "explored")

dims = []
for k, lbl, unit, sio, lg, better in DBM:
    dd = {"key": k, "label": lbl, "unit": unit or None, "si": sio or None, "log": lg or None, "better": better}
    dims.append({a: b for a, b in dd.items() if b is not None})
dims += [{"key": "arch_i", "label": "Architecture # (1–12 in legend order)"},
         {"key": "arch", "label": "Architecture", "type": "cat", "labels": ARCH_SHORT, "order": ARCH_ORDER},
         {"key": "pol", "label": "Polarity", "type": "cat", "labels": POL_LABEL, "order": ["pos", "neg"]},
         {"key": "vin_c", "label": "V_IN", "type": "cat", "labels": {jsn(v): f"{jsn(v)} V" for v in META["vins"]}, "order": [jsn(v) for v in META["vins"]]},
         {"key": "cls", "label": "Load class", "type": "cat", "labels": {k: icls_label(k) for k in ICLS}, "order": ICLS},
         {"key": "pin", "label": "EA input pair", "type": "cat", "labels": {"n": "NMOS", "p": "PMOS"}, "order": ["n", "p"]},
         {"key": "src", "label": "Point", "type": "cat", "labels": {"explored": "explored candidate", "delivered": "delivered card"}, "order": ["explored", "delivered"]}]

db_lede_pre = ("Every nominally feasible point found during design-space exploration (gm/Id sizing + ngspice operating point + Tian loop gain at the four "
               "I<sub>load</sub> × C<sub>L</sub> corners of its class): PM ≥ 55°, GM ≥ 10 dB, all amplifying devices saturated, |V<sub>OUT</sub> − V<sub>REF</sub>| ≤ 0.5 %, "
               "I<sub>q</sub> ≤ 10 % of I<sub>max</sub>. Filter by V<sub>IN</sub>/V<sub>OUT</sub>/load class to see the trade-off between quiescent current and worst-case "
               "loop bandwidth for every architecture; delivered design cards are marked. Every point also carries closed-loop DC and PSRR metrics: load regulation "
               "(|ΔV<sub>OUT</sub>| from I<sub>min</sub> to I<sub>max</sub> and the equivalent DC output resistance), minimum operable dropout (V<sub>IN</sub> − V<sub>OUT</sub> where "
               "V<sub>OUT</sub> is 1 % low, at I<sub>max</sub> and I<sub>min</sub>), line regulation (0.9–1.1 V<sub>IN</sub>), PSRR at 1 kHz / 100 kHz, current capability and "
               "closed-loop damping. Choose any two as axes.")
db_lede_full = ("The delivered analog design cards after layout: every point is one laid-out, DRC/LVS-clean design simulated on its Magic-extracted netlist "
                "(devices as drawn plus parasitic capacitances) — loop gain at the class corners, closed-loop damping, dropout, line and load regulation, PSRR and "
                "current capability, as on the schematic database. Choose any two metrics as axes; click a point to open its card.")
db_honest = (f"**Hub note on the candidate points.** In the published `db.json` only I<sub>q</sub>, UGB (at I<sub>max</sub>), PM, T0, load regulation, V<sub>OUT</sub> and the "
             "output error vary per explored point. The other columns (ζ, R<sub>out</sub>, dropout, line regulation, PSRR, current capability, area, GM) are copies of the "
             "delivered card's values written onto every candidate of the target, so the hub attributes them only to the delivered cards (the old explorer plotted the "
             f"copies). {DAG} marks quantities the repo's builder derives by formula. UGB of delivered cards is the worst case over the class corners.")
db_blocks = [
    S(mdb(db_lede_pre, title="Design database explorer"), "pre", "lede"),
    S(mdb(db_lede_full, title="Post-layout design database"), "full", "lede"),
    S({"type": "stats", "items": [stat("explored design points", f"{(DB or {}).get('n_total', 0):,}"),
                                  stat("nominally feasible (in the database)", f"{(DB or {}).get('n', 0):,}"),
                                  stat("V_IN/V_OUT/load targets", f"{n_targets}"),
                                  stat("analog architectures", f"{len((DB or {}).get('archs') or ARCH_ORDER)}"),
                                  stat("“simulated candidates” (old Designs tile)", f"{n_cand:,}", f"Σ n_points / 2 over the cards; n_points is fixed at 8 by the builder {DAG}")]}, "pre", "dbstats"),
    S({"type": "stats", "items": [stat("laid-out designs simulated post-layout", f"{n_sim_post:,}"),
                                  stat("robust post-layout (PVT + MC)", f"{n_rob_post}"),
                                  stat("analog architectures", f"{len(ARCH_ORDER)}")]}, "full", "dbstats"),
    note(db_honest, "info"),
    {"type": "explorer", "title": "Design-space explorer", "src": "hub/data/explore.json", "dims": dims,
     "x": "iq", "y": "lreg", "color": "arch", "filters": ["vin_c", "cls", "pol", "arch", "src", "pin"],
     "highlight": "delivered", "highlight_label": "Delivered cards", "design_key": "design", "label_key": "label",
     "hover": ["iq", "ugb", "pm", "zeta", "lreg", "do_max", "linreg", "psrr1k"], "height": 560,
     "presets": [{"label": "Load regulation vs I_q (old default)", "x": "iq", "y": "lreg"},
                 {"label": "I_q vs worst-case loop bandwidth", "x": "ugb", "y": "iq"},
                 {"label": "PM vs UGB", "x": "ugb", "y": "pm"},
                 {"label": "Distribution per architecture (y = load reg)", "x": "arch_i", "y": "lreg", "logx": False},
                 {"label": "Distribution per architecture (y = I_q)", "x": "arch_i", "y": "iq", "logx": False},
                 {"label": "Distribution per architecture (y = UGB)", "x": "arch_i", "y": "ugb", "logx": False},
                 {"label": "Per load class", "x": "iq", "y": "ugb", "facet": "cls"},
                 {"label": "Dropout vs I_q", "x": "iq", "y": "do_max"},
                 {"label": "PSRR 1 kHz vs I_q", "x": "iq", "y": "psrr1k"}],
     "caption": "Pre-PEX stage: explored candidates (dots) + delivered cards (rings, click to open). Full post-PEX stage: the delivered designs simulated on their "
                "extracted netlists. Old controls: V<sub>IN</sub> / V<sub>OUT</sub> / I<sub>load</sub> filters → chips (V<sub>OUT</sub> is fixed per V<sub>IN</sub>; the global "
                "V<sub>DD</sub> option also applies); x / y axis selectors → X / Y (all 16 old metrics); “distribution per architecture” box plots → the "
                "*Distribution per architecture* presets (strip plot over the architecture number 1–12, colours = architectures; pick any Y)."},
]
# best value per architecture (old "Best <y> vs V_OUT": V_OUT is fixed per V_IN, so the hub shows the best value per load class, one panel per V_IN)
best_tabs = []
vins = list(META["vins"])
for k, lbl, unit, sio, lg, better in DBM:
    if k == "vout":
        continue
    tab_blocks = []
    for st in ("pre", "full"):
        tr = []
        for vi, v in enumerate(vins):
            for ai, a in enumerate(ARCH_ORDER):
                ys = []
                for cl in ICLS:
                    vals = [cols[k][i] for i in range(len(cols[k])) if cols["stage"][i] == st and cols["arch"][i] == a and cols["vdd"][i] == v and cols["cls"][i] == cl
                            and isnum(cols[k][i]) and (st == "full" or (k in PER_POINT and cols["src"][i] == "explored") or (k not in PER_POINT and cols["src"][i] == "delivered"))]
                    ys.append((max(vals) if k in BEST_MAX else min(vals)) if vals else None)
                if any(y is not None for y in ys):
                    tr.append({"type": "scatter", "mode": "lines+markers", "name": ARCH_SHORT.get(a, a), "legendgroup": a, "showlegend": vi == 0,
                               "x": [icls_short(cl) for cl in ICLS], "y": ys, "xaxis": "x" if vi == 0 else "x2", "yaxis": "y" if vi == 0 else "y2",
                               "line": {"color": PAL[ai % len(PAL)]}, "marker": {"color": PAL[ai % len(PAL)]}, "meta": {"vdd": v},
                               "hovertemplate": f"{ARCH_SHORT.get(a, a)} · V_IN {jsn(v)} V<br>%{{x}}: %{{y}}<extra></extra>"})
        if not tr:
            continue
        ytitle = f"best {lbl}" + (f" ({unit})" if unit else "")
        lay = {"xaxis": {"domain": [0, 0.47], "title": {"text": f"load class (V_IN = {jsn(vins[0])} V → V_OUT = {'/'.join(jsn(o) for o in META['vouts'][jsn(vins[0])])} V)"}, "type": "category"},
               "xaxis2": {"domain": [0.53, 1], "anchor": "y2", "title": {"text": f"load class (V_IN = {jsn(vins[-1])} V → V_OUT = {'/'.join(jsn(o) for o in META['vouts'][jsn(vins[-1])])} V)"}, "type": "category"},
               "yaxis": {"title": {"text": ytitle}, "type": "log" if lg else "linear", "exponentformat": "SI"},
               "yaxis2": {"anchor": "x2", "type": "log" if lg else "linear", "exponentformat": "SI", "matches": "y"},
               "hovermode": "closest", "legend": {"orientation": "h", "y": -0.32}}
        cap = ("best over all feasible explored points of each architecture" + ("" if k in PER_POINT else " — for this quantity only the delivered card carries a value, so it is the card's value")) if st == "pre" \
            else "the delivered design of each architecture, simulated post-layout"
        tab_blocks.append(S(chart(f"Best {lbl} per architecture and load class", tr, lay, caption=cap + (" (max)" if k in BEST_MAX else " (min)"), height=480), st, f"best_{k}"))
    if tab_blocks:
        best_tabs.append({"label": lbl, "blocks": tab_blocks})
db_blocks.append(sec("Best value per architecture", [{"type": "tabs", "style": "select", "label": "Metric", "tabs": best_tabs}],
                     intro="Old chart “Best <y> vs V<sub>OUT</sub>” (best over all feasible points of each architecture at the selected V<sub>IN</sub> and class). "
                           "Each V<sub>IN</sub> has a single V<sub>OUT</sub>, so the hub plots the best value against the load class for both supplies at once "
                           "(every old selection is one point here); pick the metric below."))
# database table
tcols = [{"key": "arch", "label": "Architecture", "type": "text"}, {"key": "vv", "label": "V_IN→V_OUT", "type": "text"},
         {"key": "load", "label": "Load", "type": "text"}, {"key": "iq", "label": "I_q", "unit": "A", "si": True, "better": "low"},
         {"key": "ugb", "label": "UGB", "unit": "Hz", "si": True, "better": "high"}, {"key": "pm", "label": "PM", "unit": "°", "digits": 3, "better": "high"},
         {"key": "zeta", "label": "ζ", "digits": 2}, {"key": "lreg", "label": "Load reg", "unit": "V", "si": True, "better": "low"},
         {"key": "lreg_r", "label": "R_out", "unit": "Ω", "si": True, "better": "low"}, {"key": "do_max", "label": "Dropout", "unit": "V", "si": True, "better": "low"},
         {"key": "linreg", "label": "Line", "unit": "mV/V", "digits": 3, "better": "low"}, {"key": "psrr1k", "label": "PSRR 1k", "unit": "dB", "digits": 3, "better": "high"},
         {"key": "area", "label": "Area", "unit": "µm²", "digits": 4, "better": "low"}, {"key": "target", "label": "Target card", "type": "design"},
         {"key": "vdd", "label": "V_DD", "unit": "V"}, {"key": "stage", "label": "Stage", "type": "text"}]
trows = []
for i in range(len(cols["stage"])):
    if cols["src"][i] == "delivered" and cols["stage"][i] == "pre":
        continue     # the old table lists database points (schematic) or the post-layout designs only
    trows.append([ARCH_SHORT.get(cols["arch"][i], cols["arch"][i]), f"{cols['vin_c'][i]}→{jsn(cols['vout'][i])} V", icls_label(cols["cls"][i]),
                  cols["iq"][i], cols["ugb"][i], cols["pm"][i], cols["zeta"][i], cols["lreg"][i], cols["lreg_r"][i], cols["do_max"][i], cols["linreg"][i],
                  cols["psrr1k"][i], cols["area"][i], cols["target"][i], cols["vdd"][i], cols["stage"][i]])
wjson("data/db_table.json", {"columns": tcols, "rows": r5(trows)})
db_blocks.append({"type": "table", "title": "Database table", "src": "hub/data/db_table.json", "stage_column": "stage", "sort": {"key": "iq", "dir": "asc"},
                  "page_size": 300, "caption": "Pre-PEX stage: every nominally feasible explored point (columns copied from the delivered card are left empty, see the note above); "
                                               "Full post-PEX stage: the delivered designs on their extracted netlists. Follows the global V<sub>DD</sub> option; "
                                               "click a header to sort; CSV export of the filtered rows."})
wjson("pages/db.json", {"blocks": db_blocks})

# --- Methodology (verbatim from index.html)
FLOW = [
    "**Error amplifier = an opa-gen cell.** The OTA is taken unchanged from the opa-gen design database (PVT-robust, DRC/LVS-clean cards only, both of its load sets): netlist for simulation, GDS for layout, its own LVS reference. A card qualifies when its supply is V<sub>IN</sub>, its input common-mode range holds V<sub>OUT</sub> and its supply current fits the I<sub>q</sub> budget; where no card fits (the smallest draws ≈ 0.5 µA) the target is reported infeasible.",
    "**Sizing around the cell.** Only the pass device (gm/Id + L at I<sub>max</sub>, from ngspice gm/Id lookup tables), the optional source-follower buffer (biased by an exact mirror of the OTA's own bias diode) and the compensation (C<sub>C</sub>, R<sub>Z</sub>) are generated here.",
    "**Unity feedback.** The error amplifier compares V<sub>OUT</sub> directly with V<sub>REF</sub> (= the set-point), so no resistive divider burns quiescent current; V<sub>OUT</sub> is swept by sweeping V<sub>REF</sub>. The input-pair polarity is chosen from the headroom of each V<sub>IN</sub>/V<sub>OUT</sub> pair.",
    "**Exploration.** Random sampling of each architecture's knobs (OTA card, pass-device gm/Id and L, buffer bias, C<sub>C</sub>, R<sub>Z</sub>) plus evolutionary refinement — op + Tian loop gain at (I<sub>min</sub>, I<sub>max</sub>) × (10 pF, 100 pF) per point.",
    "**Selection.** Within each quiescent-current budget (q1: I<sub>q</sub> ≤ 1 % of I<sub>max</sub>; q10: ≤ 10 %), maximise the worst-case loop bandwidth (→ fastest load-step recovery) subject to PM ≥ 55° / GM ≥ 10 dB nominal.",
    f"**Robustness.** Candidates are re-simulated at 5 corners × 3 temperatures and V<sub>IN</sub> ± 10 %, then with {META.get('n_mc', 50)} Monte-Carlo samples (global + mismatch); the first one with PM ≥ 45° and GM ≥ 6 dB everywhere is delivered.",
    "**Characterisation.** Dropout, line and load regulation, PSRR, output noise, load transients at three C<sub>L</sub>, line transient, start-up, output-range (V<sub>REF</sub>) sweep.",
    "**Layout.** The opa-gen / sa-gen cell GDS is placed unchanged as a sub-cell: its labelled pins and rails are escaped sideways on their own layer to columns outside the cell outline and taken up beside it, so nothing is drawn over the cell. Pass devices, buffers and the current-source array are gLayout `nmos`/`pmos`, compensation MIM caps and high-R poly; a symmetric, tiered floorplan with a met3/met4/met5 channel router; verified with the PDK KLayout DRC and LVS decks (the sub-cell checked against its own LVS reference).",
    "**Digital LDOs.** Comparator(s) from the sa-gen database (all architectures: StrongARM, double-tail, dynamic-bias, floating-inverter preamp …; functional, DRC/LVS clean, input range holding V<sub>OUT</sub>; Pareto-pruned on probed energy, offset σ and f<sub>max</sub>) → controller (NOR SR latch + thermometer shift register, dead-zone register or binary up/down counter, synthesised with Yosys to `gf180mcu_fd_sc_mcu7t5v0`) → PMOS current-source unit cells with switches plus proportional (P) cells that damp the bang-bang loop. Designs are selected with a cycle-accurate behavioural model (clock = highest f<sub>clk</sub> the I<sub>q</sub> budget allows, ≤ f<sub>max</sub>/2 of the comparator; Monte-Carlo comparator offset with the database σ and unit mismatch), then verified with transistor-level transients (C<sub>L</sub> extremes, PVT, Monte-Carlo). In those transients the comparator, clock inverter, bias, array and switches are transistor level and the synthesised controller is an event-driven XSPICE model generated cell by cell from the Liberty functions, with its supply current taken from a transistor-level power probe (13–24× faster at matching waveforms). The controller is hardened with LibreLane/OpenROAD and placed as a macro next to the sa-gen comparator cell; the whole regulator is DRC- and LVS-checked with the PDK decks.",
    "**Post-layout verification.** Every DRC/LVS-clean layout is extracted with Magic (flat; devices as drawn, one per finger, with diffusion areas/perimeters; MIM caps, poly segments and all parasitic capacitances ≥ 0.01 fF to substrate and between nets) and checked against the KLayout LVS extraction (total W per model and L, MIM area, resistor length). The same benches then run on the extracted netlist: full characterisation, the PVT screen and the Monte-Carlo screen. For the loop gain, the gates on the break node that lie beyond the cut (the OTA input devices, or the FVF pass device) are moved to a new node, so the Tian probe sits at the same cut as in the schematic. Digital LDOs: the controller macro is reduced to its labelled pins before extraction and keeps its event-driven model. Extracted devices carry no schematic names, so no per-device operating point is reported after layout. The header switch selects schematic or post-layout results for every view.",
    "**Monte-Carlo.** Mismatch is drawn per finger: multi-finger devices are split into single-finger instances in every Monte-Carlo deck (the PDK draws once per instance, so an m = N device would move all fingers together and overstate mismatch).",
    "**Compute.** Every simulation runs on a compute farm; every run is capped at 30 minutes as a whole (each ngspice call ≤ 28 min, and each farm launch including its re-sent batches); long stages continue in a new launch from their cached results.",
]
STAB = [
    "Loop gain by Tian's method (exact two-injection probe, no loading error), broken at the error-amplifier feedback input (FVF: at the pass-device gate). PM is the minimum over all 0 dB crossings.",
    "No single break point cuts every loop of a Miller-compensated LDO (the compensation capacitor closes a local loop around the pass device; the OTA cell has its own internal compensation), so every corner is also checked **closed-loop**: a small load-current step must ring down with ≤ 25 % overshoot (ζ ≥ 0.4).",
    "Load class corners: I<sub>load</sub> ∈ {I<sub>min</sub>, I<sub>max</sub>}, C<sub>L</sub> ∈ {10 pF, 100 pF}; a near-zero-load point (I<sub>min</sub>/10) is reported separately.",
    "Ideal reference current into `ib` and ideal V<sub>REF</sub> (both counted/available); I<sub>q</sub> = all current drawn from V<sub>IN</sub> and V<sub>REF</sub> minus the load.",
    "Corners tt/ss/ff/sf/fs × −40/27/125 °C; Monte-Carlo with the PDK statistical models (`sw_stat_global` + `sw_stat_mismatch`), mismatch drawn per finger.",
    "Operating point: these LDOs can have a second, non-regulating DC solution that the DC solver can land on (extracted netlists more often than schematics). The physical one is reached at power-up, so when a condition's operating point is more than max(3 %, 30 mV) off its set-point, it is solved again from the node voltages at the end of a closed-loop sweep of V<sub>IN</sub> from 0, and the solution closer to regulation is kept (loop gain and closed-loop step alike).",
]
roles = {"inp": "error-amplifier input pair", "cas": "cascodes", "load": "active loads / mirrors / buffers", "cs": "bias current sources"}
gt = META.get("gm_targets") or {}
gm_rows = [[roles[r], (gt.get("WI") or {}).get(r), (gt.get("MI") or {}).get(r)] for r in roles] + [["pass device (at I<sub>max</sub>)", "8–24, explored", "8–24, explored"]]
method_blocks = [
    sec("Methodology", [
        sec("Flow", [mdb("\n".join(f"{i + 1}. {t}" for i, t in enumerate(FLOW)))]),
        sec("", [sec("Stability test conditions", [mdb("\n".join(f"- {t}" for t in STAB))]),
                 table("gm/Id targets (1/V)", [{"key": "r", "label": "Role", "type": "text", "md": True}, {"key": "wi", "label": "WI", "type": "text", "align": "r"},
                                               {"key": "mi", "label": "MI", "type": "text", "align": "r"}], gm_rows, csv=False, search=False,
                       caption="Pass device: one value, 8–24 explored (spans both columns on the old site).")]),
    ], cols=2),
]
if GMID:
    ramp = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
    gtabs = []
    for dev in ("nfet_03v3", "pfet_03v3"):
        Dd = GMID.get(dev)
        if not Dd:
            continue
        Ls = list(Dd.keys())

        def tr(yk):
            return [line(Dd[L]["gm_id"], Dd[L][yk], f"L={L} µm", line={"color": ramp[i % len(ramp)], "width": 2},
                         hovertemplate=f"L={L} µm<br>gm/Id %{{x:.1f}}<br>%{{y:.3s}}<extra></extra>") for i, L in enumerate(Ls)]
        ax = {"title": {"text": "gm/Id (1/V)"}, "autorange": "reversed"}
        gtabs.append({"label": dev, "blocks": [sec("", [
            chart("", tr("id_w"), {"xaxis": ax, "yaxis": {"type": "log", "title": {"text": "Id/W (A/µm)"}, "exponentformat": "SI"}, "hovermode": "closest", "legend": LEG}, height=340),
            chart("", tr("gm_gds"), {"xaxis": ax, "yaxis": {"type": "log", "title": {"text": "intrinsic gain gm/gds"}}, "hovermode": "closest", "legend": LEG}, height=340),
            chart("", tr("ft"), {"xaxis": ax, "yaxis": {"type": "log", "title": {"text": "fT (Hz)"}, "exponentformat": "SI"}, "hovermode": "closest", "legend": LEG}, height=340)], cols=3)]})
    method_blocks.append(sec("gm/Id design charts", [{"type": "tabs", "tabs": gtabs}]))
wjson("pages/method.json", {"blocks": method_blocks})

# --- About & data notes (old hero, stats, coverage-matrix legend, class breakdown, footer, caveats)
lede = ("Low-quiescent-current LDO regulators for GF180MCU-D, composed from the verified cells of two sibling generators: every analog LDO's error amplifier is an "
        "OTA card of the [opa-gen](#/opa) database and every digital LDO's comparator a cell of the [sa-gen](#/sa) database, used unchanged (netlist, layout and LVS "
        "reference). Twelve positive (VSS-referenced) and negative (entirely VDD-referenced) LDO topologies — spanning Miller Two-Stage, Source-Follower Buffered, "
        "Adaptive-Biased, Ahuja Cascode-Multiplying, Flipped Voltage Follower (FVF), and Hybrid PI Digital-Assisted (DLDO) structures — across VDD = 1.8 V and 3.3 V and "
        "eight load/quiescent-current classes (<10 nA, 10–100 nA, 100 nA–1 µA, 1–10 µA, 10–100 µA, 100–1000 µA, 1–10 mA, and 10–100 mA; with quiescent current "
        "I<sub>q</sub> spanning ~1.2 nA to ~55 µA) = **192 deliverable design cards**. Analog cards are chosen from explored candidates (OTA card × pass device × "
        "compensation) and verified for phase margin and closed-loop damping over 5 corners × 3 temperatures and Monte-Carlo; digital cards are verified with "
        "transistor-level transients. Every card is laid out with the sub-cell GDS placed as is (DRC/LVS with the PDK decks), extracted, and verified again on its "
        "post-layout netlist — the **Schematic / Post-layout** switch at the top selects which results every view shows.")
iq_vals = [c["m"].get("iq") for c in CARDS if isnum(c["m"].get("iq")) and c["m"]["iq"] > 0]
lede_check = (f"Hub check against the published data: {n_cards} cards, {len(ICLS)} load classes, {len(META['vins'])} supplies, {len(ARCH_ORDER)} topologies; "
              f"I<sub>q</sub> spans {si(min(iq_vals), 'A')} – {si(max(iq_vals), 'A')}." if iq_vals else "")
by_cls = Counter((c["vin"], c["vout"], c["iclass"]) for c in CARDS)
cls_rows = []
for v in META["vins"]:
    for o in META["vouts"][jsn(v)]:
        for k in ICLS:
            n = by_cls.get((v, o, k), 0)
            if n:
                cls_rows.append([f"V<sub>DD</sub> = {jsn(v)} V → V<sub>reg</sub> = {jsn(o)} V", f"I<sub>load</sub> {icls_label(k)}", n,
                                 sum(1 for c in CARDS if c["vin"] == v and c["vout"] == o and c["iclass"] == k and c["tier"] == "pos"),
                                 sum(1 for c in CARDS if c["vin"] == v and c["vout"] == o and c["iclass"] == k and c["tier"] == "neg"), v])
skip_rows = [[c["key"], (d or {}).get("diag", {}).get("explanation", "") if d else "no data.json", "; ".join(f"{a}: {b}" for a, b in ((d or {}).get("diag") or {}).get("reasons", []))]
             for c, d in skipped]
flag_mismatch, bad_pm = [], []
for x in designs:
    for st, r in x["results"].items():
        if r.get("robust") and r.get("pvt") and r["pvt"]["pass"] < r["pvt"]["total"]:
            flag_mismatch.append(f"{x['id']} {st} {r['pvt']['pass']}/{r['pvt']['total']}")
        if "invalid PM" in (r.get("note") or ""):
            bad_pm.append(f"{x['id']} {st}")
about_blocks = [
    sec("Deliverable LDO design cards", [mdb(lede), note(lede_check, "muted") if lede_check else None,
                                         S({"type": "stats", "items": [stat("design targets", f"{n_cards}"), stat("with a feasible design", f"{n_sol}"),
                                                                       stat("robust over PVT + Monte-Carlo", f"{n_rob}"), stat("fully characterised", f"{n_sim}"),
                                                                       stat("layouts DRC + LVS clean", f"{n_lay}"),
                                                                       stat("simulated candidates", f"{n_cand:,}", f"Σ n_points / 2; n_points fixed at 8 per card by the builder {DAG}")]}, "pre", "herostats"),
                                         S({"type": "stats", "items": [stat("design targets", f"{n_cards}"), stat("with a feasible design", f"{n_sol}"),
                                                                       stat("robust post-layout (PVT + Monte-Carlo)", f"{n_rob_post}"), stat("characterised post-layout", f"{n_sim_post}"),
                                                                       stat("layouts DRC + LVS clean", f"{n_lay}"), stat("extracted parasitic capacitors", f"{tot_parc:,}")]}, "full", "herostats")]),
    sec("Coverage matrix legend (old site)", [mdb(
        "One cell per design card: **robust** PM ≥ 45° and GM ≥ 6 dB at all PVT points and all Monte-Carlo samples · **PVT only** / **nominal** weaker verification · "
        "**none** no feasible design. The value is the quiescent current. Click a cell to open the design."),
        note("On the hub the matrix (Designs view) colours cells green when the design meets the generator's robustness flag at the selected stage and amber when it "
             "does not; the old **Polarity** selector is the *Polarity* filter chip row (or the *Architecture* chips, whose ids carry the pos_/neg_ prefix); the old "
             "**Cell Metric** modes are the *Cell metric* presets: Overview (UGB · PM) / Overview (I<sub>q</sub> · area) / Bandwidth / PSRR / Layout area / "
             "I<sub>q</sub> & dropout / Robustness. The old *Noise & PSRR* mode shows only PSRR because the published noise is a placeholder "
             f"({DDAG}); a hub cell holds two values, so the old 5-value Overview line is split into two presets.", "info")]),
    sec("Design cards per voltage and load class", [table("", [
        {"key": "v", "label": "Voltage class", "type": "text", "md": True}, {"key": "l", "label": "Load class", "type": "text", "md": True},
        {"key": "n", "label": "design cards", "digits": 3}, {"key": "p", "label": "positive (VSS-ref)", "digits": 3}, {"key": "q", "label": "negative (VDD-ref)", "digits": 3},
        {"key": "vdd", "label": "V_DD", "unit": "V"}], cls_rows, csv=False, search=False,
        caption=f"External testbench C<sub>L</sub> ({si(META['cl_range'][0], 'F')}–{si(META['cl_range'][1], 'F')}). The old Designs view grouped its cards by these classes; "
                "on the hub use the matrix or the axis filters.")]),
    sec("Data notes (hub port)", [mdb("\n".join([
        f"- **Placeholder {DDAG}:** output noise. Every card publishes 35 µVrms (10 Hz–100 kHz) and 180 nV/√Hz @ 1 kHz, the repo bench's defaults when the noise "
        "analysis returns no spectrum (no card has a spectrum). Not exported as a metric; shown labelled on the design pages.",
        f"- **Derived by the repo's site builder {DAG}** (shown labelled, never in results): dropout @ I<sub>min</sub> = 0.35 × dropout @ I<sub>max</sub>; line regulation @ "
        "I<sub>min</sub> = 0.75 × @ I<sub>max</sub>; current capability (3 % drop) = 1.25 × I<sub>max</sub>; 10 pF / 100 pF load-step droop and overshoot = ×1.25 / ×0.65 "
        "of the nominal-C<sub>L</sub> step; start-up overshoot = 0.4 × load-step overshoot; I<sub>q</sub> @ I<sub>min</sub>/10 = 0.95 × I<sub>q</sub>; usable V<sub>OUT</sub> "
        "range = start/stop of the V<sub>REF</sub> sweep; the second loop-gain corner's step overshoot = 0.85 × the first; the I<sub>q</sub> curve vs load is I<sub>q</sub>@I<sub>min</sub> "
        "repeated; the V<sub>OUT</sub>-vs-V<sub>REF</sub> curve at I<sub>min</sub> is a copy of the I<sub>max</sub> sweep.",
        "- **Builder constants:** PVT records carry GM = 12 dB, ζ = 0.68, ring_ok = true for every corner; the schematic view's nominal all_sat = true / ring_ok = true; "
        "candidate counts 8 / 8 / 2; floorplan tiers = 2, the interdigitated / mirrored pair texts and routed terminals = 4 × devices. The hub omits them from results "
        "and labels them where the old page showed them.",
        "- **Dropout floor:** the dropout bench reports max(15 mV, measured), so many cards show exactly 15 mV.",
        f"- **Robustness:** `robust` is the repo's flag (PVT sweep all-stable and worst Monte-Carlo PM ≥ {PM_ROBUST_MC:g}°). The PVT count on the hub is the number of "
        f"corners with the repo's per-point pass flag (PM ≥ {META.get('pm_target')}°), the MC count the samples with PM ≥ {PM_ROBUST_MC:g}°."
        + (f" {len(flag_mismatch)} design/stage combination(s) are flagged robust with fewer passing corners ({', '.join(flag_mismatch[:6])}{' …' if len(flag_mismatch) > 6 else ''}); "
           "the note on their pages says so." if flag_mismatch else "")
        + (f" {len(bad_pm)} design/stage combination(s) contain Monte-Carlo PM values below −180° ({', '.join(bad_pm[:6])}) — phase-unwrap artefacts, excluded from worst cases."
           if bad_pm else f" PM values below −180° would be treated as phase-unwrap artefacts (none in the current data)."),
        "- **Database explorer:** candidate-point columns copied from the delivered card are attributed to the card only (see the note on that page).",
        "- **Post-layout values** are read from each design's `data.json` (`post.char`), not from `index.json` `post.m`, which the builder back-fills with schematic "
        "values when a post-layout field is missing.",
        "- **Load transient C<sub>L</sub>:** the old Key-results tile and caption printed the global nominal 100 pF; the hub prints the class's testbench C<sub>L</sub> used in the "
        "simulation (from the transient record).",
        "- **Reused-cell links** point to the hub's op-amp / sense-amp tabs (filtered by the cell id) instead of the retired per-repo sites.",
    ]))]),
]
if skip_rows:
    about_blocks.append(sec("Targets without a feasible design", [table("No feasible design point", [
        {"key": "k", "label": "Target", "type": "text"}, {"key": "e", "label": "Explanation", "type": "text"}, {"key": "r", "label": "Failure reasons over the explored points", "type": "text"}],
        skip_rows, csv=False)]))
about_blocks.append(sec("Old site header / footer", [mdb(
    f"**GF180 Low-Power LDO Generator** — opa-gen / sa-gen cells · Tian loop gain over PVT + Monte-Carlo · gLayout layouts · GF180MCU-D\n\n"
    f"generated {META.get('generated')} · GF180MCU-D (5LM, MIM M4/M5) · ngspice + KLayout + gLayout in hpretl/iic-osic-tools · source on "
    "[GitHub](https://github.com/aicdb/ldo-gen-gemini4)")], collapsed=True))
wjson("pages/about.json", {"blocks": about_blocks})

for key, doc in details.items():
    wjson(f"designs/{key}.json", doc)

# ----------------------------------------------------------------------------- component
gen = META.get("generated", "")
m_ = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", gen)
generated = f"{m_.group(1)}T{m_.group(2)}:00Z" if m_ else gen
arch_base = sorted({re.sub(r"^(pos|neg)_", "", a) for a in ARCH_ORDER})
comp = {
    "schema": "aicdb-hub/2",
    "id": "ldo",
    "name": "LDOs",
    "title": "GF180 Low-Power LDO Generator",
    "summary": (f"{len(designs)} low-quiescent-current LDO design cards: {len(arch_base)} topologies (Miller OTA, source-follower buffered, adaptive-bias, "
                "Ahuja cascode-compensated, folded FVF, hybrid PI digital-assisted) in positive VSS-referenced and negative VDD-referenced flavours, "
                f"{' and '.join(f'{jsn(v)} V → {jsn(META['vouts'][jsn(v)][0])} V' for v in META['vins'])}, across {len(ICLS)} load classes from "
                f"{icls_short(ICLS[0])} to {icls_short(ICLS[-1])}. Error amps / comparators are reused unchanged from the op-amp and sense-amp libraries; "
                f"17-point PVT, {META.get('n_mc', 50)}-run Monte Carlo, gLayout DRC/LVS and whole-cell Magic PEX."),
    "technology": TECH,
    "generated": generated,
    "stats": [{"label": "with a feasible design", "value": f"{n_sol}"},
              {"label": "characterised post-layout", "value": f"{n_sim_post}"},
              {"label": "explored design points", "value": f"{(DB or {}).get('n_total', 0):,}"},
              {"label": "extracted parasitic capacitors", "value": f"{tot_parc:,}"}],
    "metrics": [{k2: v2 for k2, v2 in dict(key=k, label=l, unit=u or None, si=s_ or None, better=b, digits=dg if dg != 3 else None).items() if v2 is not None}
                for k, l, u, s_, b, dg, _ in METRICS],
    "axes": {
        "topology": {"label": "Architecture", "values": [{"id": a, "label": ARCH_SHORT.get(a, a)} for a in ARCH_ORDER]},
        "polarity": {"label": "Polarity", "values": [{"id": t, "label": POL_LABEL.get(t, t)} for t in META["tiers"]]},
        "vout": {"label": "Vreg (output)", "values": [{"id": jsn(v), "label": f"{jsn(v)} V"} for v in sorted(vouts)]},
        "class": {"label": "Load current", "values": [{"id": k, "label": icls_short(k)} for k in ICLS]},
    },
    "matrix": {"rows": ["topology"], "cols": ["class"], "metrics": ["ugb", "pm"],
               "presets": [{"label": "Overview (UGB · PM)", "metrics": ["ugb", "pm"]},
                           {"label": "Overview (Iq · area)", "metrics": ["iq", "area"]},
                           {"label": "Bandwidth (UGB & DC loop gain)", "metrics": ["ugb", "a0"]},
                           {"label": "PSRR 1 kHz & 100 kHz (noise: placeholder, not exported)", "metrics": ["psrr_1k", "psrr_100k"]},
                           {"label": "Layout area", "metrics": ["area"]},
                           {"label": "Quiescent Iq & dropout", "metrics": ["iq", "dropout"]},
                           {"label": "Robustness (worst PVT / MC PM)", "metrics": ["pm_pvt", "pm_mc"]}]},
    "card_metrics": ["ugb", "area", "iq", "a0", "pm", "pm_pvt", "pm_mc", "psrr_1k", "dropout", "load_reg", "droop"],
    "pages": [{"id": "db", "title": "Database explorer", "src": "hub/pages/db.json"},
              {"id": "method", "title": "Methodology", "src": "hub/pages/method.json"},
              {"id": "about", "title": "About & data notes", "src": "hub/pages/about.json"}],
    "designs": designs,
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "component.json").write_text(json.dumps(comp, separators=(",", ":"), ensure_ascii=False))
if skipped:
    print(f"ldo adapter: {len(skipped)} target(s) without results listed on the About page", file=sys.stderr)
