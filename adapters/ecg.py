#!/usr/bin/env python3
"""Bootstrap hub adapter for ecg-gen-gemini4.

usage: ecg.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.

Stage mapping (see ecggen/pex.py + ecggen/site.py in the repo):
  pre     = schematic netlist, nominal TB1-TB6 + 29-corner PVT + 30-run MC.
  partial = nominal TB1-TB6 re-run on the "post-PEX" netlist. That netlist is the *schematic*
            ecg_afe subcircuit with only the Magic-extracted parasitic capacitors that land on
            top-level named AFE nets injected (no R, internal-net parasitics dropped), so it is a
            C-only, partially back-annotated simulation, not a full extracted-layout run.
            PVT/MC were not re-run post-layout (the repo reuses the pre variation numbers for its
            "post" summary), so this stage carries no pvt/mc counts and no robust flag.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
summ = json.loads((docs / "data" / "summary.json").read_text())
meta = summ["meta"]

METRICS = [
    # key, label, unit, si, better, source field, scale, needs post-layout variation run
    ("irn", "Input noise (0.5 Hz–1 kHz)", "V", True, "low", "irn_rms_chopped_uv", 1e-6, False),
    ("power", "Total power", "W", True, "low", "p_total_nw", 1e-9, False),
    ("gain", "AFE gain", "dB", False, "high", "a_mid_db", 1, False),
    ("zin", "|Z_in| @ 50 Hz", "Ω", True, "high", "zin_50hz_ibl_on_mohm", 1e6, False),
    ("nef", "NEF", "", False, "low", "nef", 1, False),
    ("pef", "PEF", "", False, "low", "pef", 1, False),
    ("a_lna", "LNA gain", "dB", False, "high", "a_lna_db", 1, False),
    ("a_ol", "Core OTA A_OL", "dB", False, "high", "a_ol_db", 1, False),
    ("f_h", "High cutoff f_H", "Hz", True, None, "f_h_hz", 1, False),
    ("f_l", "Low cutoff f_L", "Hz", True, "low", "f_l_hz", 1, False),
    ("zin_boost", "Z_in boost (IBL)", "×", False, "high", "zin_boost_factor", 1, False),
    ("cmrr", "CMRR @ 50 Hz", "dB", False, "high", "cmrr_50hz_db", 1, False),
    ("psrr", "PSRR @ 50 Hz", "dB", False, "high", "psrr_50hz_db", 1, False),
    ("thd", "THD (4 mVpp)", "%", False, "low", "thd_pct", 1, False),
    ("dr", "Dynamic range", "dB", False, "high", "dr_db", 1, False),
    ("pm", "Loop phase margin", "°", False, "high", "pm_deg", 1, False),
    ("edo", "Electrode offset tol.", "V", True, "high", "edo_tolerance_mv", 1e-3, False),
    ("vn_1k", "Noise @1 kHz (chopped)", "V/√Hz", True, "low", "vn_1khz_chopped_nv_rthz", 1e-9, False),
    ("idd", "Supply current", "A", True, "low", "idd_na", 1e-9, False),
    ("zin_min", "Worst PVT |Z_in|", "Ω", True, "high", "zin_min_mohm", 1e6, True),
    ("mc_yield", "MC yield", "%", False, "high", "mc_yield_pct", 1, True),
    ("vos_sigma", "Chopped offset σ (MC)", "V", True, "low", "vos_chop_sigma_uv", 1e-6, True),
    ("area", "Layout area", "µm²", False, "low", None, 1, False),
]


def metrics(r, area, with_variation):
    m = {}
    for key, _, _, _, _, field, scale, var in METRICS:
        if field is None or (var and not with_variation):
            continue
        v = r.get(field)
        m[key] = None if v is None else round(v * scale, 15)
    m["area"] = area
    return m


archs = [{"id": a["id"], "label": a["short"]} for a in meta["architectures"]]
arch_meta = {a["id"]: a for a in meta["architectures"]}
tiers = [{"id": t["tag"], "label": t["short_label"]} for t in meta["power_tiers"]]
arch_order = {a["id"]: i for i, a in enumerate(archs)}
tier_order = {t["id"]: i for i, t in enumerate(tiers)}

designs = []
cards = sorted(summ["cards"], key=lambda c: (arch_order.get(c["arch"], 99), c["vdd"],
                                             tier_order.get(c["tier"], 99)))
for c in cards:
    cid = c["card_id"]
    base = f"designs/{cid}"
    ph = c.get("physical") or {}
    area = ph.get("area_um2")
    detail_path = docs / base / "card.json"
    detail = json.loads(detail_path.read_text()) if detail_path.is_file() else {}
    sizing = detail.get("sizing") or {}
    pre_var = (detail.get("pre_pex") or {}).get("variation") or {}

    results = {}
    pre = c.get("pre")
    if pre:
        s = {"metrics": metrics(pre, area, True), "robust": bool(pre.get("pvt_robust"))}
        if pre.get("pvt_total"):
            s["pvt"] = {"pass": pre["pvt_pass"], "total": pre["pvt_total"]}
        mc = pre_var.get("mc") or {}
        if mc.get("n_runs") and mc.get("yield_pct") is not None:
            s["mc"] = {"pass": round(mc["n_runs"] * mc["yield_pct"] / 100), "total": mc["n_runs"]}
        results["pre"] = s
    post = c.get("post")
    post_nom = (detail.get("post_pex") or {}).get("nominal") or {}
    if post and post_nom.get("ok", True):
        n_c = ph.get("parasitic_c_count")
        results["partial"] = {
            "metrics": metrics(post, area, False),
            "note": "Nominal TB1–TB6 on the schematic AFE netlist with Magic-extracted parasitic "
                    f"capacitors on top-level AFE nets injected (C-only; {n_c} caps extracted, "
                    "internal-net parasitics and wiring R not back-annotated). PVT/MC not re-run "
                    "post-layout.",
        }

    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.svg"), ("gds", f"{cid}.gds.gz"),
        ("netlist", "netlist.spice"), ("pex_netlist", "pex.spice"),
        ("lvs_netlist", "lvs_ref.spice"), ("data", "card.json"))
        if (docs / base / v).is_file()}
    am = arch_meta.get(c["arch"], {})
    params = {
        "Chopper freq.": f"{c.get('f_chop_hz', 0) / 1e3:g} kHz",
        "β_IBL": c.get("beta_ibl"),
        "Core OTA": c.get("core_ota_id"),
        "Aux OTA": c.get("aux_ota_id"),
        "I_core (nA)": sizing.get("i_core_na"),
        "I_aux (nA)": sizing.get("i_aux_na"),
        "C_in (pF)": sizing.get("c_in_pf"),
        "C_fb (fF)": sizing.get("c_fb_ff"),
        "C_pf (fF)": sizing.get("c_pf_ff"),
        "C_LPF (pF)": sizing.get("c_lpf_pf"),
        "Chopper switch": c.get("chop_sw_key"),
        "S&H switch": c.get("sh_sw_key"),
        "Comparator": c.get("comp_key"),
        "Wirelength (µm)": ph.get("wirelength_um"),
        "Vias": ph.get("vias"),
        "Parasitic C (extracted)": ph.get("parasitic_c_count"),
    }
    designs.append({
        "id": cid,
        "title": f"{c['arch_short']} · {c['vdd']} V · {c['tier_short']}",
        "vdd": c["vdd"],
        "axes": {"topology": c["arch"], "tier": c["tier"]},
        "tags": [t for t in (c.get("arch_name"), c.get("ibl_type"), c.get("hpf_type"),
                             c.get("tier_label")) if t],
        "physical": {"drc": ph.get("drc_ok"), "lvs": ph.get("lvs_ok"), "pex": ph.get("pex_ok"),
                     "area_um2": area, "width_um": ph.get("width_um"), "height_um": ph.get("height_um")},
        "results": results,
        "params": {k: v for k, v in params.items() if v is not None},
        "files": files,
        "links": {"classic": f"index.html#/{cid}"},
    })

comp = {
    "schema": "aicdb-hub/1",
    "id": "ecg",
    "name": "ECG AFEs",
    "title": "GF180 Chopper ECG Front-End Library",
    "summary": "Six capacitively-coupled chopper instrumentation amplifier (CCIA) architectures for ECG "
               "(capacitive / buffered positive-feedback IBL, DC-servo loop, capacitor flipping, precharge, "
               "two-stage LNA + PGA) at 1.8 V and 3.3 V in three power tiers from 100 nW to 1 µW. "
               "29-corner PVT, 30-run Monte Carlo, gLayout DRC/LVS and Magic C extraction.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "farm simulations", "value": f"{meta.get('total_farm_sims', 0):,}"},
              {"label": "DSE points", "value": f"{meta.get('dse_points_count', 0):,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b).items()
                 if v is not None}
                for k, l, u, si, b, _, _, _ in METRICS],
    "axes": {
        "topology": {"label": "Architecture", "values": archs},
        "tier": {"label": "Power tier", "values": tiers},
    },
    "matrix": {"rows": ["topology"], "cols": ["tier"], "metrics": ["irn", "zin"]},
    "card_metrics": ["irn", "power", "gain", "zin", "nef", "area"],
    "designs": designs,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
