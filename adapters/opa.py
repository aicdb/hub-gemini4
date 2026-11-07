#!/usr/bin/env python3
"""Bootstrap hub adapter for opa-gen-gemini4.

usage: opa.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
Reference implementation for repo builders: copy to scripts/export_hub.py in your repo.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
loads = json.loads((docs / "loads.json").read_text())["loads"]

METRICS = [
    # key, label, unit, si, better, source field, scale
    ("a0", "DC gain", "dB", False, "high", "a0_db", 1),
    ("ugb", "UGB", "Hz", True, "high", "ugb_hz", 1),
    ("pm", "Phase margin", "°", False, "high", "pm_deg", 1),
    ("power", "Power", "W", True, "low", "power_uw", 1e-6),
    ("idd", "Supply current", "A", True, "low", "idd_ua", 1e-6),
    ("gm", "Gain margin", "dB", False, "high", "gm_db", 1),
    ("sr", "Slew rate (+)", "V/s", True, "high", "sr_pos_vus", 1e6),
    ("ts", "Settling 1%", "s", True, "low", "ts_1pct_us", 1e-6),
    ("vn_rms", "Output noise", "V", True, "low", "vn_rms_uv", 1e-6),
    ("vn_1k", "Noise @1 kHz", "V/√Hz", True, "low", "vn_1khz_nv_rthz", 1e-9),
    ("cmrr", "CMRR (DC)", "dB", False, "high", "cmrr_dc_db", 1),
    ("psrr", "PSRR+ (DC)", "dB", False, "high", "psrr_p_dc_db", 1),
    ("swing", "Output swing", "V", True, "high", "vout_swing_v", 1),
    ("thd", "THD", "%", False, "low", "thd_pct", 1),
    ("pm_min", "Worst PVT PM", "°", False, "high", "pm_min_deg", 1),
    ("mc_yield", "MC yield", "%", False, "high", "mc_yield_pct", 1),
    ("vos_sigma", "Offset σ (MC)", "V", True, "low", "vos_sigma_mv", 1e-3),
    ("area", "Layout area", "µm²", False, "low", None, 1),
]


def stage(r, area):
    if not r:
        return None
    m = {}
    for key, _, _, _, _, field, scale in METRICS:
        if field is None:
            continue
        v = r.get(field)
        if key == "power" and v is None and r.get("power_nw") is not None:
            v = r["power_nw"] * 1e-3
        if key == "idd" and v is None and r.get("idd_na") is not None:
            v = r["idd_na"] * 1e-3
        m[key] = None if v is None else v * scale
    m["area"] = area
    out = {"metrics": m, "robust": bool(r.get("pvt_robust"))}
    if r.get("pvt_total"):
        out["pvt"] = {"pass": r["pvt_pass"], "total": r["pvt_total"]}
    return out


archs, supplies, classes, regimes, designs = [], set(), [], [], []
total_sims = 0
for ld in loads:
    lt = ld["id"]
    summ = json.loads((docs / "data" / lt / "summary.json").read_text())
    meta = summ["meta"]
    total_sims = max(total_sims, meta.get("total_farm_sims", 0))
    if not archs:
        archs = [{"id": a["id"], "label": a["short"]} for a in meta["architectures"]]
        classes = [{"id": meta["ulp_class"]["tag"], "label": "<0.1 µW (ULP)"}] + \
                  [{"id": c["tag"], "label": c["label"]} for c in meta["current_classes"]]
        regimes = [{"id": r["tag"], "label": r["label"]} for r in meta["inversion_regimes"]]
    for c in summ["cards"]:
        cid = c["card_id"]
        base = f"designs/{lt}/{cid}"
        ph = c.get("physical") or {}
        area = ph.get("area_um2")
        results = {}
        if (s := stage(c.get("pre"), area)):
            results["pre"] = s
        if c.get("post") and (s := stage(c.get("post"), area)):
            s["note"] = "Magic-extracted parasitics of the full op-amp layout"
            results["full"] = s
        files = {k: f"{base}/{v}" for k, v in (
            ("schematic", "schematic.svg"), ("layout", "layout.svg"), ("gds", f"{cid}.gds.gz"),
            ("netlist", "netlist.spice"), ("pex_netlist", "pex.spice"),
            ("lvs_netlist", "lvs_ref.spice"), ("data", "card.json"))
            if (docs / base / v).is_file()}
        designs.append({
            "id": f"{lt}-{cid}",
            "title": f"{c['arch_short']} · {c['vdd']} V · {c['iclass_label']} · {c['inv_label']} · CL {ld['label']}",
            "vdd": c["vdd"],
            "axes": {"topology": c["arch"], "class": c["iclass_tag"], "regime": c["inv_tag"], "load": lt},
            "tags": [c.get("arch_title", ""), f"{c.get('input_type', '')} input", f"{c.get('stages')}-stage",
                     f"gm/Id {c.get('gmid_target')} V⁻¹"],
            "physical": {"drc": ph.get("drc_ok"), "lvs": ph.get("lvs_ok"), "pex": ph.get("pex_ok"),
                         "area_um2": area, "width_um": ph.get("width_um"), "height_um": ph.get("height_um")},
            "results": results,
            "params": {"C_L": ld["label"], "gm/Id target": c.get("gmid_target"),
                       "Wirelength (µm)": ph.get("wirelength_um"), "Vias": ph.get("vias")},
            "files": files,
            "links": {"classic": f"index.html#/{lt}/{cid}"},
        })

comp = {
    "schema": "aicdb-hub/1",
    "id": "opa",
    "name": "Op-amps",
    "title": "GF180 Op-Amp Design Library",
    "summary": "Twelve op-amp architectures (5-T, Miller, telescopic & folded cascode, symmetrical, "
               "rail-to-rail, Cherry-Hooper, current-reuse LNA) in two inversion regimes, an ultra-low-power "
               "<0.1 µW class plus three current classes at 1.8 V and 3.3 V, for 2 pF and 200 fF loads. "
               "gm/Id sizing, 17-corner PVT, 50-run Monte Carlo, gLayout DRC/LVS and Magic PEX.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "farm simulations", "value": f"{total_sims:,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=si or None, better=b).items() if v is not None}
                for k, l, u, si, b, _, _ in METRICS],
    "axes": {
        "topology": {"label": "Architecture", "values": archs},
        "regime": {"label": "Inversion", "values": regimes},
        "class": {"label": "Current class", "values": classes},
        "load": {"label": "Load", "values": [{"id": l["id"], "label": l["label"]} for l in loads]},
    },
    "matrix": {"rows": ["topology", "regime"], "cols": ["class"], "metrics": ["ugb", "a0"]},
    "card_metrics": ["a0", "ugb", "pm", "power", "area"],
    "designs": designs,
}
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
