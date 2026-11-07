#!/usr/bin/env python3
"""Bootstrap hub adapter for sdm-gen-gemini4.

usage: sdm.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.

Stage mapping (repo "Verification Stage" switch -> hub stage):
  pre  "1. Pre-Layout"      -> pre      schematic netlists, nominal unit caps
  post "2. Post-Cap PEX"    -> partial  trimmed SC cap-array macro Magic PEX (+ op-amp PEX
                                        models); no top-level routing parasitics
  full "3. Full-Chip PEX"   -> full     cap PEX + component PEX subckts + top-level route PEX
                                        + gate-level sdm2bin decimator
9-corner PVT and 100-run MC are evaluated on the full-chip view only, so they are attached
to `full` only.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
idx = json.loads((docs / "data" / "index.json").read_text())
sims = json.loads((docs / "data" / "sim_summary.json").read_text())
lays = json.loads((docs / "data" / "layout_summary.json").read_text())

METRICS = [
    # key, label, unit, si, better, digits, source field (view metrics), scale
    ("enob", "ENOB", "bit", False, "high", 4, "enob", 1),
    ("sndr", "SNDR", "dB", False, "high", 4, "sndr_db", 1),
    ("snr", "SNR", "dB", False, "high", 4, "snr_db", 1),
    ("sfdr", "SFDR", "dB", False, "high", 4, "sfdr_db", 1),
    ("thd", "THD", "dB", False, "low", 4, "thd_db", 1),
    ("dr", "Dynamic range", "dB", False, "high", 4, "dr_db", 1),
    ("msa", "Max stable amplitude", "dBFS", False, "high", 3, "msa_dbfs", 1),
    ("power", "Total power", "W", True, "low", None, "pwr_total_uw", 1e-6),
    ("p_analog", "Analog power", "W", True, "low", None, "pwr_analog_uw", 1e-6),
    ("p_digital", "Digital power", "W", True, "low", None, "pwr_digital_uw", 1e-6),
    ("fom_s", "FoM Schreier", "dB", False, "high", 5, "fom_schreier_db", 1),
    ("fom_w", "FoM Walden", "fJ/step", False, "low", 4, "fom_walden_fj", 1),
    ("bw", "Signal bandwidth", "Hz", True, "high", None, "fb_hz", 1),
    ("fs", "Sampling rate", "Hz", True, None, None, "fs_hz", 1),
    ("tau", "Stage-1 settling τ", "s", True, "low", None, "tau_settle_ns", 1e-9),
    ("settle_err", "Settling error", "V", True, "low", None, "v_settle_err_uv", 1e-6),
    ("noise", "In-band noise", "V", True, "low", None, None, 1e-6),
    ("swing1", "Int-1 swing", "V", True, None, None, "vout1_swing_vpp", 1),
    ("swing2", "Int-2 swing", "V", True, None, None, "vout2_swing_vpp", 1),
    # full-chip-only robustness / linearity (from PVT, MC and full-view linearity)
    ("pvt_min_enob", "Worst PVT ENOB", "bit", False, "high", 4, None, 1),
    ("mc_enob", "MC ENOB mean", "bit", False, "high", 4, None, 1),
    ("mc_enob_std", "MC ENOB σ", "bit", False, "low", 3, None, 1),
    ("mc_yield", "MC yield", "%", False, "high", 4, None, 1),
    ("dnl", "DNL max", "LSB", False, "low", 3, None, 1),
    ("inl", "INL max", "LSB", False, "low", 3, None, 1),
    ("area", "Layout area", "µm²", False, "low", 4, None, 1),
]

NOTES = {
    "pre": "Schematic netlists, nominal unit capacitor and coefficients",
    "partial": "Post-Cap PEX: trimmed SC capacitor-array macro Magic-extracted (and op-amp PEX models); "
               "switches/comparator schematic, no top-level routing parasitics",
    "full": "Full-chip PEX: cap-array PEX + extracted sub-block subcircuits + top-level summing-node "
            "routing PEX + gate-level sdm2bin; 9-corner PVT and 100-run MC at this stage",
}


def stage(m, area):
    if not m:
        return None
    r = {}
    for key, _, _, _, _, _, field, scale in METRICS:
        if field is None:
            continue
        v = m.get(field)
        r[key] = None if v is None else float(f"{v * scale:.6g}")
    nb = (m.get("noise_budget_uv_rms") or {}).get("total_inband_noise_uv")
    r["noise"] = None if nb is None else float(f"{nb * 1e-6:.6g}")
    r["area"] = area
    return {"metrics": r}


def load_sim(cid):
    p = docs / "designs" / cid / "sim.json"
    return json.loads(p.read_text()) if p.is_file() else {}


arch_specs, res_specs, cap_specs = idx["arch_specs"], idx["res_specs"], idx["cap_specs"]
CAP_LABEL = {"mom": "MOM", "mim": "MIM"}
designs = []
for c in idx["cards"]:
    cid = c["card_id"]
    s, lay = sims.get(cid, {}), lays.get(cid, {})
    ls = c.get("layout_summary") or {}
    area = lay.get("area_um2", ls.get("area_um2"))
    rs = res_specs.get(str(c["nbits"]), {})
    a = arch_specs.get(c["arch_id"], {})
    results = {}
    for src, st in (("pre", "pre"), ("post", "partial"), ("full", "full")):
        if (r := stage(s.get(src), area)):
            r["note"] = NOTES[st]
            results[st] = r

    if "full" in results:
        sim = load_sim(cid)
        pvt, mc = sim.get("pvt") or {}, sim.get("monte_carlo") or {}
        fm = results["full"]["metrics"]
        fm["pvt_min_enob"] = s.get("pvt_min_enob", pvt.get("enob_min"))
        fm["mc_enob"] = s.get("mc_enob_mean", mc.get("enob_mean"))
        fm["mc_enob_std"] = s.get("mc_enob_std", mc.get("enob_std"))
        fm["mc_yield"] = s.get("mc_yield_pct", mc.get("yield_pct"))
        fm["dnl"] = s.get("dnl_max_lsb")
        fm["inl"] = s.get("inl_max_lsb")
        if pvt.get("corners"):
            results["full"]["pvt"] = {"pass": sum(1 for k in pvt["corners"] if k.get("pass")),
                                      "total": len(pvt["corners"])}
        if mc.get("n_runs") and mc.get("yield_pct") is not None:
            results["full"]["mc"] = {"pass": round(mc["n_runs"] * mc["yield_pct"] / 100.0),
                                     "total": mc["n_runs"]}
        # repo criterion: every PVT corner and every MC run meets ENOB >= nbits
        pvt_ok = s.get("pvt_pass", pvt.get("all_pass"))
        y = fm["mc_yield"]
        results["full"]["robust"] = bool(pvt_ok) and y is not None and y >= 100.0

    base = f"designs/{cid}"
    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.svg"), ("gds", f"{cid}.gds.gz"),
        ("netlist", "netlist_pre.spice"), ("pex_netlist", "netlist_full.spice"), ("data", "data.json"))
        if (docs / base / v).is_file()}
    images = [{"label": lbl, "path": f"{base}/{f}"} for lbl, f in (
        ("Cap-array layout", "cap_layout.svg"), ("sdm2bin layout", "dig_layout.svg"),
        ("Stage-1 op-amp", "opa1_schematic.svg"), ("Stage-2 op-amp", "opa2_schematic.svg"),
        ("VCM buffer op-amp", "opa_vcm_schematic.svg"), ("Comparator", "comp_schematic.svg"),
        ("Input switch", "sw_in_schematic.svg"), ("sdm2bin decimator", "dig_schematic.svg"))
        if (docs / base / f).is_file()]
    downloads = [{"label": lbl, "path": f"{base}/{f}"} for lbl, f in (
        ("Post-Cap-PEX netlist", "netlist_post.spice"), ("Simulation data", "sim.json"))
        if (docs / base / f).is_file()]

    cs = c.get("components_summary") or {}
    tags = [a.get("name", c.get("arch_name", "")), cap_specs.get(c["cap_type"], {}).get("name", ""),
            f"OSR {c['osr']}", f"L={rs.get('loop_order')} loop", f"sinc{rs.get('sinc_order')}"]
    if rs.get("cds_chopper"):
        tags.append("CDS chopper")
    if rs.get("dwa_order"):
        tags.append(f"DWA order {rs['dwa_order']}")
    if s.get("cosim_bit_exact"):
        tags.append("gate-level bit-exact")

    designs.append({
        "id": cid,
        "title": f"{c['nbits']}-bit · {c['vdd']} V · {CAP_LABEL.get(c['cap_type'], c['cap_type'])} · {c['arch_short']}",
        "vdd": c["vdd"],
        "axes": {"topology": c["arch_id"], "resolution": f"{c['nbits']}b", "cap": c["cap_type"]},
        "tags": [t for t in tags if t],
        "physical": {"drc": lay.get("drc_clean"), "lvs": lay.get("lvs_match"),
                     "pex": True if "full" in results else None,
                     "area_um2": area, "width_um": lay.get("width_um"), "height_um": lay.get("height_um")},
        "results": results,
        "params": {
            "OSR": c["osr"], "f_s": f"{c['fs_mhz']} MHz", "f_B": f"{c['fb_khz']} kHz",
            "Loop order": rs.get("loop_order"), "Decimator": f"sinc{rs.get('sinc_order')} ({c.get('dig_key')})",
            "Cap macro": c.get("cap_key"), "Cap trim error (%)": ls.get("max_ratio_err_pct"),
            "Stage-1 op-amp": cs.get("opa1_key"), "Stage-2 op-amp": cs.get("opa2_key"),
            "VCM op-amp": cs.get("opa_vcm_key"), "Comparator": cs.get("comp_key"),
            "Input switch": cs.get("sw_in_key"), "SC switch": cs.get("sw_sc_key"),
            "Cap area (µm²)": lay.get("cap_area_um2"), "Op-amp area (µm²)": lay.get("opa_area_um2"),
            "Digital area (µm²)": lay.get("dig_area_um2"), "Routing area (µm²)": lay.get("routing_area_um2"),
        },
        "files": files,
        "images": images,
        "downloads": downloads,
        "links": {"classic": f"index.html#card={cid}"},
    })

order = {a: i for i, a in enumerate(idx["arch_order"])}
designs.sort(key=lambda d: (d["vdd"], order.get(d["axes"]["topology"], 99),
                            int(d["axes"]["resolution"][:-1]), idx["cap_types"].index(d["axes"]["cap"])))

comp = {
    "schema": "aicdb-hub/1",
    "id": "sdm",
    "name": "ΣΔ ADCs",
    "title": "GF180 Switched-Capacitor ΣΔ ADC Library",
    "summary": f"{idx['total_cards']} low-power switched-capacitor sigma-delta ADCs: four loop architectures "
               "(shared-Cs and split-DAC CIFB, feedforward CIFF, resonator CRFF) at 8–20 bits, MOM or MIM "
               "capacitor arrays, 1.8 V and 3.3 V, each with an OpenROAD sdm2bin decimator. Reported at "
               "pre-layout, post-cap-PEX and full-chip PEX, with 9-corner PVT and 100-run Monte Carlo on the "
               "full-chip view.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "cap macros", "value": str(idx.get("cap_macros_count", ""))},
              {"label": "decimator macros", "value": str(idx.get("digital_macros_count", ""))}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=si or None, better=b, digits=dg).items()
                 if v is not None}
                for k, l, u, si, b, dg, _, _ in METRICS],
    "axes": {
        "topology": {"label": "Loop architecture",
                     "values": [{"id": a, "label": arch_specs[a]["short"]} for a in idx["arch_order"]]},
        "resolution": {"label": "Resolution",
                       "values": [{"id": f"{n}b", "label": f"{n}-bit (OSR {res_specs[str(n)]['osr']})"}
                                  for n in idx["nbits_list"]]},
        "cap": {"label": "Capacitor", "values": [{"id": t, "label": CAP_LABEL.get(t, t)} for t in idx["cap_types"]]},
    },
    "matrix": {"rows": ["topology"], "cols": ["resolution", "cap"], "metrics": ["enob", "power"]},
    "card_metrics": ["enob", "sndr", "power", "fom_s", "area"],
    "designs": designs,
}
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
