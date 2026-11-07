#!/usr/bin/env python3
"""Bootstrap hub adapter for ldo-gen-gemini4.

usage: ldo.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
Copy to scripts/export_hub.py in the repo and run it as the last step of the docs build.

Data sources: docs/data/index.json (meta + 144 card summaries) and, per design,
docs/designs/<key>/data.json. Metrics are taken from data.json `char.metrics`
(schematic) and `post.char.metrics` (post-PEX) rather than index.json `post.m`, because
the repo's site builder fills missing post-PEX fields in index.json with schematic values.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
idx = json.loads((docs / "data" / "index.json").read_text())
meta, cards = idx["meta"], idx["cards"]

# The repo's own robustness threshold (ldogen/site.py: MC pass = worst PM >= 30°).
PM_ROBUST = 30.0

METRICS = [
    # key, label, unit, si, better, source field in char.metrics, scale
    ("ugb", "UGB (min)", "Hz", True, "high", "ugb_min", 1),
    ("pm", "Phase margin", "°", False, "high", "pm_min", 1),
    ("gm", "Gain margin", "dB", False, "high", "gm_min", 1),
    ("a0", "DC loop gain", "dB", False, "high", "a0_min", 1),
    ("iq", "Quiescent current", "A", True, "low", "iq", 1),
    ("dropout", "Dropout @ Imax", "V", True, "low", "dropout_imax", 1),
    ("line_reg", "Line regulation", "mV/V", False, "low", "line_reg_imax", 1e3),
    ("load_reg", "Load regulation", "V", True, "low", "load_reg_mv", 1e-3),
    ("rout", "Output resistance", "Ω", True, "low", "load_reg", 1),
    ("psrr_1k", "PSRR @ 1 kHz", "dB", False, "high", "psrr_1k_imax", 1),
    ("psrr_100k", "PSRR @ 100 kHz", "dB", False, "high", "psrr_100k_imax", 1),
    ("psrr_dc", "PSRR (DC)", "dB", False, "high", "psrr_dc_imax", 1),
    ("droop", "Load-step droop", "V", True, "low", "undershoot_mv_nom", 1e-3),
    ("overshoot", "Load-step overshoot", "V", True, "low", "overshoot_mv_nom", 1e-3),
    ("settle", "Settling (up step)", "s", True, "low", "settle_up_us_nom", 1e-6),
    ("fom", "FoM (TR·Iq/ΔI)", "s", True, "low", "fom_ps", 1e-12),
    ("verr", "Output error (max)", "V", True, "low", "verr_max", 1),
    ("zeta", "Damping ζ (min)", "", False, "high", "zeta_min", 1),
    ("step_os", "Small-step overshoot", "%", False, "low", "step_overshoot_pct", 1),
    ("startup", "Start-up time", "s", True, "low", "startup_us", 1e-6),
    ("pm_pvt", "Worst PVT PM", "°", False, "high", None, 1),
    ("pm_mc", "Worst MC PM", "°", False, "high", None, 1),
    ("area", "Layout area", "µm²", False, "low", None, 1),
]
# Not exported: noise_int_10_100k_uv / noise_1k (the published value is the builder's
# placeholder default 35 µV / 0 for every card), dropout_imin / line_reg_imin / imax_cap
# (derived by formula from other fields, not measured).

ICLASS_LABEL = {"lt1u": "<1 µA", "1u_10u": "1–10 µA", "10u_100u": "10–100 µA",
                "100u_1m": "0.1–1 mA", "1m_10m": "1–10 mA", "10m_100m": "10–100 mA"}
POL_LABEL = {"pos": "Positive (VSS-ref)", "neg": "Negative (VDD-ref)"}


def stage(char, opt, area, robust):
    """One results.<stage> block from a char payload plus its PVT/MC lists."""
    if not char or not char.get("metrics"):
        return None
    cm = char["metrics"]
    m = {}
    for key, _, _, _, _, field, scale in METRICS:
        if field is None:
            continue
        v = cm.get(field)
        if v is not None and key in ("load_reg", "rout"):
            v = abs(v)
        if v is not None and key in ("iq", "line_reg") and v == 0:
            v = None  # source rounds to 5 decimals: Iq < 5 µA / line reg < 5 µV/V publish as 0.0
        m[key] = None if v is None else float(f"{v * scale:.6g}")
    pvt, mc = opt.get("pvt") or [], opt.get("mc") or []
    pvt_pm = [p["r"]["pm_min"] for p in pvt if p["r"].get("ok") and p["r"].get("pm_min") is not None]
    mc_pm = [s["pm_min"] for s in mc if s.get("ok") and s.get("pm_min") is not None]
    m["pm_pvt"] = min(pvt_pm) if pvt_pm else None
    m["pm_mc"] = min(mc_pm) if mc_pm else None
    m["area"] = area
    res = {"metrics": m, "robust": bool(robust)}
    if pvt:
        res["pvt"] = {"pass": sum(1 for p in pvt if p.get("pass")), "total": len(pvt)}
    if mc:
        res["mc"] = {"pass": sum(1 for s in mc if s.get("ok") and (s.get("pm_min") or 0) >= PM_ROBUST),
                     "total": len(mc)}
    return res


def fmt(v, unit=""):
    return None if v is None else f"{v:g}{(' ' + unit) if unit else ''}"


order = {a: i for i, a in enumerate(meta["arch_order"])}
icls = list(meta["iclasses"])
cards.sort(key=lambda c: (order.get(c["arch"], 99), c["vin"], icls.index(c["iclass"])))

designs, n_post_sims, n_par_c = [], 0, 0
vouts = []
for c in cards:
    key = c["key"]
    base = f"designs/{key}"
    dj = json.loads((docs / base / "data.json").read_text())
    lay = dj.get("layout") or {}
    ver = dj.get("verify") or {}
    post = dj.get("post") or {}
    area = lay.get("area_um2") or c["m"].get("area_um2")
    pidx = c.get("post") or {}
    n_post_sims += pidx.get("n_done") or 0
    n_par_c += pidx.get("n_parasitic_c") or 0
    if c["vout"] not in vouts:
        vouts.append(c["vout"])

    results = {}
    if (s := stage(dj.get("char"), dj.get("opt") or {}, area, c["robust"])):
        results["pre"] = s
    if post.get("char") and (s := stage(post["char"], post, area, pidx.get("robust"))):
        s["note"] = ("Magic ext2spice extraction of the complete LDO cell (error amp, pass device, "
                     "compensation): device geometry + coupling/ground capacitance, no wire resistance")
        results["full"] = s

    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.svg"), ("gds", f"{key}.gds.gz"),
        ("netlist", "netlist.spice"), ("pex_netlist", "pex.spice"),
        ("lvs_netlist", "lvs_reference.spice"), ("data", "data.json"))
        if (docs / base / v).is_file()}
    images = [{"label": lbl, "path": f"{base}/{fn}"} for lbl, fn in (
        ("Schematic with sizing", "schematic_sizing.svg"),
        ("Top-level schematic", "schematic_tl.svg")) if (docs / base / fn).is_file()]
    downloads = [{"label": "KLayout LVS-extracted netlist", "path": f"{base}/extracted.cir"}] \
        if (docs / base / "extracted.cir").is_file() else []

    reuse = c.get("ea") or c.get("comp") or {}
    kn = (dj.get("opt") or {}).get("knobs") or {}
    params = {"Reused cell": reuse.get("id"),
              "Iq budget": fmt(c.get("iq_budget") or None, "A"),
              "Inversion": kn.get("inv"),
              "Pass gm/Id": fmt(kn.get("gp"), "V⁻¹"),
              "Pass L": fmt(kn.get("Lp"), "µm"),
              "Rz": fmt(kn.get("rz"), "Ω"),
              "Parasitic C (PEX)": pidx.get("n_parasitic_c")}
    params = {k: v for k, v in params.items() if v is not None}

    drc = (ver.get("drc") or {}).get("clean")
    lvs = (ver.get("lvs") or {}).get("match")
    designs.append({
        "id": key,
        "title": f"{c['arch_short']} · {c['vin']} V → {c['vout']} V · {ICLASS_LABEL.get(c['iclass'], c['iclass'])}",
        "vdd": c["vin"],
        "axes": {"topology": c["arch"], "polarity": c["polarity"], "vout": str(c["vout"]),
                 "class": c["iclass"]},
        "tags": [t for t in [c.get("arch_name"), POL_LABEL.get(c["polarity"]),
                             (c.get("tags") or [None, None])[1],
                             f"reuses {reuse['id']}" if reuse.get("id") else None] if t],
        "physical": {"drc": drc if drc is not None else c["status"].get("drc"),
                     "lvs": lvs if lvs is not None else c["status"].get("lvs"),
                     "pex": True if (docs / base / "pex.spice").is_file() else None,
                     "area_um2": area, "width_um": lay.get("width_um"), "height_um": lay.get("height_um")},
        "results": results,
        "params": params,
        "files": files,
        "images": images,
        "downloads": downloads,
        "links": {"classic": f"index.html#d/{key}"},
    })

n = len(designs)
comp = {
    "schema": "aicdb-hub/1",
    "id": "ldo",
    "name": "LDOs",
    "title": "GF180 LDO Regulator Library",
    "summary": f"{n} LDO designs: six topologies (Miller OTA, source-follower buffered, adaptive-bias, "
               "Ahuja cascode-compensated, folded FVF, hybrid PI digital-assisted) in positive VSS-referenced "
               "and negative VDD-referenced flavours, 1.8 V → 1.2 V and 3.3 V → 1.8 V, across six load-current "
               "classes from <1 µA to 100 mA. Error amps and comparators are reused from the op-amp and "
               "sense-amp libraries; 17-corner PVT, 50-run Monte Carlo, gLayout DRC/LVS and Magic PEX.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "post-layout simulations", "value": f"{n_post_sims:,}"},
              {"label": "extracted parasitic capacitors", "value": f"{n_par_c:,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b).items()
                 if v is not None} for k, l, u, si, b, _, _ in METRICS],
    "axes": {
        "topology": {"label": "Architecture",
                     "values": [{"id": a, "label": meta["arch_short"].get(a, a)} for a in meta["arch_order"]]},
        "polarity": {"label": "Polarity",
                     "values": [{"id": t, "label": POL_LABEL.get(t, lbl)} for t, lbl in meta["tiers"].items()]},
        "vout": {"label": "Output voltage",
                 "values": [{"id": str(v), "label": f"{v} V"} for v in sorted(vouts)]},
        "class": {"label": "Load current",
                  "values": [{"id": k, "label": ICLASS_LABEL.get(k, k)} for k in icls]},
    },
    "matrix": {"rows": ["topology"], "cols": ["class"], "metrics": ["ugb", "pm"]},
    "card_metrics": ["ugb", "pm", "iq", "dropout", "psrr_1k", "area"],
    "designs": designs,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
