#!/usr/bin/env python3
"""Bootstrap hub adapter for sa-gen-gemini4.

usage: sa.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
Starting point for the repo builder: copy to scripts/export_hub.py in your repo.

Stage mapping: `m` (schematic netlist) -> pre; `m_pex` -> partial. The repo's post-layout
netlist (netlist_pex.spice) is the schematic devices plus Magic C-only node capacitances,
scaled and clamped into lumped caps on internal nets (no wiring R, inputs/clock/supplies
ideal), so it is a partial extraction, not a full one.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
idx = json.loads((docs / "data" / "index.json").read_text())
meta, cards = idx["meta"], idx["cards"]

ARCH_ORDER = ["san", "sap", "dt", "dtx", "db", "dbx", "fia", "miy", "scsa"]  # app.js ARCH_ORDER
MIX_ORDER = ["lv", "hvl", "nat"]
TGT_ORDER = ["sub", "wi", "mi"]

METRICS = [
    # key, label, unit, si, better, source field in m / m_pex
    ("delay", "Delay @1 mV", "s", True, "low", "delay_1mv"),
    ("delay10", "Delay @10 mV", "s", True, "low", "delay_10mv"),
    ("delay_worst", "Worst PVT delay @1 mV", "s", True, "low", "delay_1mv_worst"),
    ("e_comp", "Energy / decision", "J", True, "low", "e_comp"),
    ("e_total", "Energy incl. buffer", "J", True, "low", "e_total"),
    ("idd", "Core IDD @2.5 MHz", "A", True, "low", "idd_avg"),
    ("p_comp", "Power (core+clk)", "W", True, "low", "p_comp"),
    ("dv_min", "Min. detectable ΔV", "V", True, "low", "min_detectable_dv_v"),
    ("vos_sigma", "Offset σ (model)", "V", True, "low", "vos_sigma"),
    ("noise", "Input noise σ", "V", True, "low", "sigma_noise"),
    ("hyst", "Hysteresis", "V", True, "low", "hysteresis"),
    ("tau", "Regeneration τ", "s", True, "low", "tau_regen"),
    ("kick", "Kickback (diff)", "V", True, "low", "kick_diff"),
    ("fmax", "Max clock", "Hz", True, "high", "fmax"),
    ("cm_min", "Input CM min", "V", True, "low", "cm_min"),
    ("cm_max", "Input CM max", "V", True, "high", "cm_max"),
    ("leak", "Leakage @125 °C", "A", True, "low", "i_leak_125c_max"),
    ("fom", "FoM E·σn²", "J·V²", False, "low", "fom_e_sigma2"),
    ("area", "Layout area", "µm²", False, "low", None),
]

PARTIAL_NOTE = ("Schematic devices + Magic C-only extraction, back-annotated as scaled/clamped lumped "
                "caps on internal nets (no wiring R; inputs, clock and supplies ideal)")


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def stage(m, area):
    if not m or m.get("functional") is None:
        return None
    vals = {k: num(m.get(f)) for k, _, _, _, _, f in METRICS if f}
    if vals.get("hyst") is not None:
        vals["hyst"] = abs(vals["hyst"])
    vals["area"] = area
    r = {"metrics": vals, "robust": bool(m.get("functional") and m.get("pvt_robust"))}
    if m.get("pvt_total"):
        r["pvt"] = {"pass": m["pvt_pass"], "total": m["pvt_total"]}
    return r


def gmid_txt(g):
    g = g or {}
    return " / ".join(f"{k} {v:.1f}" for k, v in g.items() if num(v) is not None) or None


order = {(a, mx, v, t): i for i, (a, mx, v, t) in enumerate(
    (a, mx, v, t) for a in ARCH_ORDER for mx in MIX_ORDER for v in meta["vdds"] for t in TGT_ORDER)}
designs = []
for c in sorted(cards, key=lambda c: order.get((c["arch"], c["mix"], c["vdd"], c["target"]), 1e9)):
    key = c["key"]
    base = f"designs/{key}"
    data = json.loads((docs / base / "data.json").read_text())
    L = data.get("layout") or {}
    params = (data.get("design") or {}).get("params") or {}
    st = c.get("status") or {}
    area = num(L.get("area_um2")) or num(c.get("area"))
    m, mp = c.get("m") or {}, c.get("m_pex") or {}

    results = {}
    if (s := stage(m, area)):
        results["pre"] = s
    if st.get("pex") == "done" and (s := stage(mp, area)):
        s["note"] = PARTIAL_NOTE
        results["partial"] = s

    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.png"), ("gds", "comp.gds.gz"),
        ("netlist", "netlist.spice"), ("pex_netlist", "netlist_pex.spice"),
        ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json"))
        if (docs / base / v).is_file()}
    images = [{"label": "Schematic (post-PEX gm/Id annotation)", "path": f"{base}/schematic_pex.svg"}] \
        if (docs / base / "schematic_pex.svg").is_file() else []
    downloads = [{"label": "Magic raw extraction (extracted.cir)", "path": f"{base}/extracted.cir"}] \
        if (docs / base / "extracted.cir").is_file() else []

    tgt = meta["targets"][c["target"]]
    selfcal = bool(m.get("self_calibrated"))
    tags = [meta["archs"].get(c["arch"], c["arch"]), meta["mixes"].get(c["mix"], c["mix"]),
            f"IDD {tgt['short']}", "f_read 2.5 MHz", "C_L 200 fF"]
    if selfcal:
        tags.append("Self-calibrated")

    p = {"gm/Id target (V⁻¹)": c.get("gmid_target"), "gm/Id sim (V⁻¹)": gmid_txt(c.get("gmid_sim")),
         "gm/Id sim post-PEX (V⁻¹)": gmid_txt(c.get("gmid_sim_pex")), "V_CM (V)": c.get("vcm"),
         "W_in (µm)": params.get("w_in"), "L_in (µm)": params.get("l_in"), "nf_in": params.get("nf_in"),
         "W_tail (µm)": params.get("w_tail")}
    if selfcal:
        p["Cal range (mV)"] = m.get("cal_range_mv")
        p["Cal step (µV)"] = m.get("cal_step_uv")
        p["Offset σ uncal. (mV)"] = round(m["vos_sigma_uncal"] * 1e3, 3) if num(m.get("vos_sigma_uncal")) else None
    p["Routed nets"] = len(L.get("nets") or []) or None

    designs.append({
        "id": key,
        "title": f"{meta['arch_short'][c['arch']]} · {meta['mix_short'][c['mix']]} · {c['vdd']} V · "
                 f"{tgt['short']}",
        "vdd": c["vdd"],
        "axes": {"topology": c["arch"], "mix": c["mix"], "target": c["target"]},
        "tags": tags,
        "physical": {"drc": st.get("drc"), "lvs": st.get("lvs"),
                     "pex": True if st.get("pex") == "done" else None,
                     "area_um2": area, "width_um": num(L.get("width_um")), "height_um": num(L.get("height_um"))},
        "results": results,
        "params": {k: v for k, v in p.items() if v is not None},
        "files": files,
        "images": images,
        "downloads": downloads,
        "links": {"classic": f"index.html#d/{key}"},
    })

n_rob = sum(1 for d in designs if (d["results"].get("pre") or {}).get("robust"))
comp = {
    "schema": "aicdb-hub/1",
    "id": "sa",
    "name": "Sense amps",
    "title": "GF180 Clocked Sense-Amplifier / Comparator Library",
    "summary": "Nine clocked comparator topologies (StrongARM N/P, double-tail and its cross-coupled and "
               "dynamic-bias variants, FIA preamp, two self-calibrating designs) in three threshold-voltage "
               "device mixes, gm/Id-sized into three supply-current bands at a 2.5 MHz read rate for 1.8 V "
               "and 3.3 V, 200 fF load. 29-point PVT, KLayout DRC/LVS and Magic capacitance extraction.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "PVT-robust (schematic)", "value": f"{n_rob}/{len(designs)}"},
              {"label": "PVT points per design", "value": "29"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=si or None, better=b).items() if v is not None}
                for k, l, u, si, b, _ in METRICS],
    "axes": {
        "topology": {"label": "Architecture",
                     "values": [{"id": a, "label": meta["arch_short"][a]} for a in ARCH_ORDER if a in meta["archs"]]},
        "mix": {"label": "Threshold mix",
                "values": [{"id": x, "label": meta["mix_short"][x]} for x in MIX_ORDER if x in meta["mixes"]]},
        "target": {"label": "IDD band @2.5 MHz",
                   "values": [{"id": t, "label": meta["targets"][t]["short"]} for t in TGT_ORDER if t in meta["targets"]]},
    },
    "matrix": {"rows": ["topology", "mix"], "cols": ["target"], "metrics": ["delay", "idd"]},
    "card_metrics": ["delay", "e_comp", "idd", "dv_min", "vos_sigma", "area"],
    "designs": designs,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
