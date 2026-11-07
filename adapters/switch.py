#!/usr/bin/env python3
"""Bootstrap hub adapter for switch-gen-gemini4.

usage: switch.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
Starting point for the repo builder: copy to scripts/export_hub.py in the repo.

Source: docs/data/index.json (meta + one card per topology × VDD × current class).
  card.m  = schematic characterisation (15 PVT points)  -> results.pre
  card.mp = same testbench suite on the Magic-extracted cell netlist -> results.full
Cards with status.sim == "n/a" (e.g. 3.3 V-oxide bootstrap at 3.3 V) have no results and are skipped.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
idx = json.loads((docs / "data" / "index.json").read_text())
meta, cards = idx["meta"], idx["cards"]

METRICS = [
    # key, label, unit, si, better, source field, scale
    ("coverage", "Valid range", "% VDD", False, "high", "coverage", 100),
    ("ron_vtest", "R_on @ test level", "Ω", True, "low", "ron_vtest", 1),
    ("ron_wc", "R_on worst PVT", "Ω", True, "low", "ron_wc", 1),
    ("drop", "I_max·R_on drop", "% VDD", False, "low", "drop", 100),
    ("ron_flat", "R_on flatness (max/min)", "", False, "low", "ron_flat", 1),
    ("roff_wc", "R_off worst PVT", "Ω", True, "high", "roff_wc", 1),
    ("leak_wc", "Off leakage worst PVT", "A", True, "low", "leak_wc", 1),
    ("t_on", "Turn-on time", "s", True, "low", "t_on", 1),
    ("t_off", "Turn-off time", "s", True, "low", "t_off", 1),
    ("e_vdd", "Switching energy / cycle", "J", True, "low", "e_vdd", 1),
    ("q_absmax", "Max |charge injection|", "C", True, "low", "q_absmax", 1),
    ("ped_absmax", "Max hold pedestal", "V", True, "low", "ped_absmax", 1),
    ("iso_10m", "Off-isolation @10 MHz", "dB", False, "low", "iso_10m", 1),
    ("iso_1m", "Off-isolation @1 MHz", "dB", False, "low", "iso_1m", 1),
    ("coff", "C_off", "F", True, "low", "coff", 1),
    ("ron_coff", "R_on·C_off", "s", True, "low", "ron_coff_fs", 1e-15),
    ("thd", "Tracking THD (1 MHz)", "dB", False, "low", "thd_db", 1),
    ("vgs_on", "On-state gate drive", "V", True, "high", "vgs_on", 1),
    ("stress", "Device stress / rating", "%", False, "low", "stress_ratio", 100),
    ("area", "Layout area", "µm²", False, "low", None, 1),
]


def si(x, u):
    for f, p in ((1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")):
        if abs(x) >= f or f == 1e-15:
            return f"{x / f:.3g} {p}{u}"


def rng(valid):
    if not valid:
        return "none"
    return " ∪ ".join(f"{lo:.2f}–{hi:.2f} V" for lo, hi in valid)


def robust(m, c):
    """The repo's own specification checks (app.js tabOverview), all at worst PVT."""
    return bool(m.get("ron_wc") is not None and m["ron_wc"] <= m["rt"] * 1.001
                and m.get("grade") is not None
                and (m.get("coverage") or 0) > 0
                and m.get("leak_wc") is not None and m["leak_wc"] <= meta["leak_frac"] * c["imax"] * 1.001
                and m.get("stress_ok"))


def stage(m, c, area, note):
    if not m:
        return None
    mm = {}
    for key, _, _, _, _, field, scale in METRICS:
        if field is None:
            continue
        v = m.get(field)
        mm[key] = None if v is None else float(f"{v * scale:.6g}")
    mm["area"] = area
    grade = m.get("grade") or "below D"
    return {"metrics": mm, "robust": robust(m, c),
            "note": f"{note}; valid {rng(m.get('valid'))}; R_on grade {grade}"}


def icl_label(lo, hi):
    def f(x):
        for s, u in ((1, "A"), (1e-3, "mA"), (1e-6, "µA")):
            if x >= s:
                v = x / s
                return (f"{v:.0f}" if v >= 1 else f"{v:g}"), u
        return f"{x:g}", "A"
    (a, ua), (b, ub) = f(lo), f(hi)
    if ua == ub:
        return f"{a}–{b} {ub}"
    if ub == "A":  # 0.1–1 A
        return f"{lo:g}–{hi:g} A"
    if ub == "mA" and ua == "µA":
        return f"{lo * 1e3:g}–{hi * 1e3:g} mA"
    return f"{a} {ua}–{b} {ub}"


KNOBS = {"rp": "W_p/W_n", "kcb": "C_B / C_gate", "f_dum": "Dummy size fraction", "f_shunt": "Shunt size fraction"}

designs, skipped = [], []
order = {t: i for i, t in enumerate(meta["order"])}
icl_order = {k: i for i, k in enumerate(meta["iclasses"])}
for c in sorted(cards, key=lambda c: (order.get(c["topo"], 99), c["vdd"], icl_order.get(c["iclass"], 99))):
    key, m, mp = c["key"], c.get("m") or {}, c.get("mp") or {}
    st = c.get("status") or {}
    if st.get("sim") == "n/a" or not m:
        skipped.append(key)
        continue
    base = f"designs/{key}"
    dpath = docs / base / "data.json"
    data = json.loads(dpath.read_text()) if dpath.is_file() else {}
    verify = data.get("verify") or {}
    area = m.get("area_um2")
    results = {}
    if (s := stage(m, c, area, "Schematic netlist, 15 PVT points")):
        results["pre"] = s
    if mp and (s := stage(mp, c, area, "Magic RC extraction of the full switch cell (+ met3 stripe R at IN/OUT), 15 PVT points")):
        results["full"] = s
    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.png"), ("gds", f"{key}.gds.gz"),
        ("netlist", "netlist.spice"), ("pex_netlist", f"{key}.pex.spice"),
        ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json"))
        if (docs / base / v).is_file()}
    images = [{"label": "Schematic (post-PEX operating points)", "path": f"{base}/schematic_post.svg"}] \
        if (docs / base / "schematic_post.svg").is_file() else []
    pex = verify.get("pex") or {}
    params = {"R_on target": f"{m['rt']:g} Ω", "I_max": si(c["imax"], "A"), "Switch width W_s": f"{m['ws']:g} µm",
              "Test level": f"{m['vtest']:g} V", "Load R_L": f"{m['rl']:g} Ω", "Hold cap C_H": si(m["ch"], "F"),
              "Aux slices": m.get("naux"), "Banks": m.get("banks"),
              "Active / MIM area": f"{m.get('act_um2', 0):g} / {m.get('mim_um2', 0):g} µm²"}
    params.update({KNOBS.get(k, k): v for k, v in (c.get("knobs") or {}).items()})
    designs.append({
        "id": key,
        "title": c["name"],
        "vdd": c["vdd"],
        "axes": {"topology": c["topo"], "class": c["iclass"]},
        "tags": list(c.get("tags") or []) + [f"R_on grade {m.get('grade') or 'below D'}"]
                + (["rail-to-rail"] if (m.get("coverage") or 0) > 0.97 else []),
        "physical": {"drc": st.get("drc"), "lvs": st.get("lvs"),
                     "pex": pex.get("ok") if pex else (True if mp else None),
                     "area_um2": area, "width_um": m.get("layout_w"), "height_um": m.get("layout_h")},
        "results": results,
        "params": params,
        "files": files,
        "images": images,
        "links": {"classic": f"index.html#d/{key}"},
    })

stats = [{"label": "post-PEX simulated", "value": str(sum(1 for d in designs if "full" in d["results"]))}]
sw = docs / "data" / "sweep.json"
if sw.is_file():
    stats.insert(0, {"label": "design-space sweep points", "value": f"{json.loads(sw.read_text())['n_total']:,}"})
if skipped:
    stats.append({"label": "not applicable", "value": str(len(skipped))})

comp = {
    "schema": "aicdb-hub/1",
    "id": "switch",
    "name": "Switches",
    "title": "GF180 Analog Switch Generator",
    "summary": "Thirteen analog / sampling-switch topologies (pass-gates, transmission gates, T-switches, clock-boosted and "
               "bootstrapped NMOS incl. DNW bulk-bootstrapped and charge-cancelled ADC S/H switches) at 1.8 V and 3.3 V for "
               "five load-current classes (10 µA … 1 A). Each is sized for an I_max·R_on drop ≤ 5 % of VDD over its valid "
               "signal range at all 15 PVT corners, laid out with gLayout (KLayout DRC/LVS) and re-simulated from Magic PEX.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": stats,
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b).items() if v is not None}
                for k, l, u, si, b, _, _ in METRICS],
    "axes": {
        "topology": {"label": "Topology",
                     "values": [{"id": t, "label": meta["short"].get(t, t)} for t in meta["order"]]},
        "class": {"label": "Current class",
                  "values": [{"id": k, "label": icl_label(*v)} for k, v in meta["iclasses"].items()]},
    },
    "matrix": {"rows": ["topology"], "cols": ["class"], "metrics": ["coverage", "area"]},
    "card_metrics": ["coverage", "ron_wc", "drop", "q_absmax", "t_on", "area"],
    "designs": designs,
}
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
if skipped:
    print(f"switch adapter: skipped {len(skipped)} n/a cards: {', '.join(skipped)}", file=sys.stderr)
