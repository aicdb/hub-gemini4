#!/usr/bin/env python3
"""Bootstrap hub adapter for aux-gen-gemini4.

usage: aux.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
The repo holds ten unrelated block families (ring oscillators, tunable R/C, current mirrors,
references, dividers, ...), so every family becomes a hub sub-tab with its own matrix
(topology x target) and card metrics. Copy to scripts/export_hub.py in the repo to take over.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
idx = json.loads((docs / "data" / "index.json").read_text())
meta, cards = idx["meta"], idx["cards"]

METRICS = [
    # key, label, unit, si, better  (union over all families, display order)
    ("f_osc", "f_osc", "Hz", True, None),
    ("f_center", "Center frequency", "Hz", True, None),
    ("f_min", "Tuning f_min", "Hz", True, "low"),
    ("f_max", "Tuning f_max", "Hz", True, "high"),
    ("f_max_in", "Max input frequency", "Hz", True, "high"),
    ("lock_range", "Locking range", "Hz", True, "high"),
    ("div_ratio", "Measured division ratio", "÷", False, None),
    ("ratio_err", "Division ratio error", "%", False, "low"),
    ("vin_sens", "Min input sensitivity", "V", True, "low"),
    ("f_err", "|Frequency error|", "%", False, "low"),
    ("tuning_range", "Tuning range", "%", False, "high"),
    ("kvco", "K_VCO", "Hz/V", True, None),
    ("kdco", "K_DCO", "Hz/LSB", True, None),
    ("fom_t", "Tuning FoM_T", "dBc/Hz", False, "low"),
    ("c_max", "C_max", "F", True, None),
    ("c_min", "C_min", "F", True, "low"),
    ("c_lsb", "C LSB", "F", True, None),
    ("c_err", "|C_max error|", "%", False, "low"),
    ("q_100m", "Q @ 100 MHz", "", False, "high"),
    ("q_min_100m", "Min Q @ 100 MHz", "", False, "high"),
    ("esr", "ESR", "Ω", True, "low"),
    ("tcap_fom", "FoM (Q × tuning ratio)", "", False, "high"),
    ("r_nom", "R_nom", "Ω", True, None),
    ("r_min", "R_min", "Ω", True, None),
    ("r_max", "R_max", "Ω", True, None),
    ("r_err", "|R_nom error|", "%", False, "low"),
    ("tuning_ratio", "Tuning ratio (max/min)", "×", False, "high"),
    ("lin_err", "I–V linearity error", "%", False, "low"),
    ("thd", "Equivalent THD", "dB", False, "low"),
    ("tc_r", "R temp. coeff.", "ppm/°C", False, "low"),
    ("i_fs", "I_FS / I_out", "A", True, None),
    ("i_lsb", "I LSB", "A", True, None),
    ("copy_err", "Copy error", "%", False, "low"),
    ("v_comp", "Compliance voltage", "V", True, "low"),
    ("rout", "Output resistance", "Ω", True, "high"),
    ("bw", "Bandwidth (−3 dB)", "Hz", True, "high"),
    ("t_settle", "Settling time", "s", True, "low"),
    ("inl", "INL", "LSB", False, "low"),
    ("dnl", "DNL", "LSB", False, "low"),
    ("vref", "V_REF (27 °C)", "V", True, None),
    ("i_ref", "I_REF (TT)", "A", True, None),
    ("i_err", "|I_REF error|", "%", False, "low"),
    ("tc_ref", "Temp. coeff. (−40..125 °C)", "ppm/°C", False, "low"),
    ("line_sens", "Line sensitivity", "%/V", False, "low"),
    ("psrr_100", "PSRR @ 100 Hz", "dB", False, "high"),
    ("min_vdd", "Min supply", "V", True, "low"),
    ("startup", "Start-up time", "s", True, "low"),
    ("trim_range", "Trim range", "%", False, "high"),
    ("vref_fom", "FoM (1e4 / (TC·√P_nW))", "", False, "high"),
    ("bm_fom", "Composite FoM", "", False, "high"),
    ("power", "Power", "W", True, "low"),
    ("energy", "Energy per cycle", "J", True, "low"),
    ("pn_1m", "Phase noise L(1 MHz)", "dBc/Hz", False, "low"),
    ("jitter", "RMS jitter", "s", True, "low"),
    ("fom_osc", "Oscillator FoM", "dBc/Hz", False, "low"),
    ("fom_div", "Divider FoM", "dBc/Hz", False, "low"),
    ("vpp_diff", "Diff. swing V_pp", "V", True, "high"),
    ("vpp_out", "Output swing V_pp", "V", True, "high"),
    ("swing", "Output swing", "V", True, "high"),
    ("duty", "Duty cycle", "%", False, None),
    ("t_start", "Oscillation start-up", "s", True, "low"),
    ("vdd_sens", "f supply sensitivity", "%/V", False, None),
    ("tc_f", "f temp. coeff.", "ppm/°C", False, None),
    ("mc_cv", "MC spread σ/µ (primary)", "%", False, "low"),
    ("area", "Layout area", "µm²", False, "low"),
]

# Per family: (hub key, source field in metrics_pre/post, scale to base unit), matrix metrics,
# card metrics. "mc_cv" and "area" are appended to every family.
OSC = [("pn_1m", "phase_noise_dbc_1m", 1), ("jitter", "jitter_ps", 1e-12), ("fom_osc", "fom_dbc", 1),
       ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6)]
FAM = {
    "ro": ([("f_osc", "f_osc_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1)] + OSC +
           [("duty", "duty_pct", 1), ("swing", "swing_v", 1), ("t_start", "t_start_ns", 1e-9),
            ("vdd_sens", "vdd_sens_pct_per_v", 1), ("tc_f", "temp_coeff_ppm_c", 1)],
           ["f_osc", "power"], ["f_osc", "power", "energy", "pn_1m", "fom_osc", "area"]),
    "tcap": ([("c_max", "c_max_pf", 1e-12), ("c_min", "c_min_pf", 1e-12), ("c_lsb", "c_lsb_ff", 1e-15),
              ("c_err", "c_err_pct", 1), ("tuning_ratio", "tuning_ratio", 1), ("q_100m", "q_factor_100m", 1),
              ("q_min_100m", "q_min_100m", 1), ("esr", "esr_ohm", 1), ("tcap_fom", "fom", 1),
              ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
             ["c_max", "tuning_ratio"], ["c_max", "c_min", "tuning_ratio", "q_100m", "esr", "area"]),
    "tres": ([("r_nom", "r_nom_kohm", 1e3), ("r_min", "r_min_kohm", 1e3), ("r_max", "r_max_kohm", 1e3),
              ("r_err", "r_err_pct", 1), ("tuning_ratio", "tuning_ratio", 1), ("lin_err", "linearity_err_pct", 1),
              ("thd", "thd_db", 1), ("bw", "bw_3db_mhz", 1e6), ("tc_r", "temp_coeff_ppm_c", 1),
              ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
             ["r_nom", "tuning_ratio"], ["r_nom", "tuning_ratio", "lin_err", "bw", "tc_r", "area"]),
    "cm_idac": ([("i_fs", "i_fs_ua", 1e-6), ("i_lsb", "lsb_ua", 1e-6), ("copy_err", "copy_err_pct", 1),
                 ("v_comp", "v_comp_v", 1), ("rout", "rout_mohm", 1e6), ("bw", "bw_mhz", 1e6),
                 ("t_settle", "t_settle_ns", 1e-9), ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1),
                 ("power", "power_uw", 1e-6)],
                ["i_fs", "rout"], ["i_fs", "rout", "v_comp", "copy_err", "power", "area"]),
    "dco_vco": ([("f_center", "f_center_mhz", 1e6), ("f_min", "f_min_mhz", 1e6), ("f_max", "f_max_mhz", 1e6),
                 ("f_err", "abs_freq_err_pct", 1), ("tuning_range", "tuning_range_pct", 1),
                 ("tuning_ratio", "tuning_ratio", 1), ("fom_t", "fom_t_dbc", 1)] + OSC +
                [("swing", "swing_v", 1), ("duty", "duty_pct", 1), ("tc_f", "temp_coeff_ppm_c", 1)],
                ["f_center", "tuning_range"], ["f_center", "tuning_range", "power", "fom_t", "pn_1m", "area"]),
    "cml_ro": ([("f_osc", "f_osc_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1), ("vpp_diff", "vpp_diff_v", 1),
                ("tuning_range", "tuning_range_pct", 1), ("kvco", "kvco_mhz_per_v", 1e6)] + OSC +
               [("duty", "duty_pct", 1), ("t_start", "t_start_ns", 1e-9),
                ("vdd_sens", "vdd_sens_pct_per_v", 1), ("tc_f", "temp_coeff_ppm_c", 1)],
               ["f_osc", "power"], ["f_osc", "vpp_diff", "power", "pn_1m", "fom_osc", "area"]),
    "clk_div": ([("f_max_in", "f_max_ghz", 1e9), ("lock_range", "lock_range_ghz", 1e9),
                 ("div_ratio", "div_ratio_meas", 1), ("ratio_err", "ratio_err_pct", 1),
                 ("vin_sens", "min_vin_sens_v", 1), ("vpp_out", "vpp_out_v", 1), ("duty", "duty_pct", 1),
                 ("pn_1m", "pn_1m_dbc", 1), ("jitter", "jitter_ps", 1e-12), ("fom_div", "fom_dbc", 1),
                 ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6)],
                ["f_max_in", "power"], ["f_max_in", "lock_range", "vin_sens", "vpp_out", "power", "area"]),
    "vref_2t": ([("vref", "vref_mv", 1e-3), ("tc_ref", "tc_ppm_c", 1), ("line_sens", "line_sens_pct_v", 1),
                 ("psrr_100", "psrr_100hz_db", 1), ("power", "power_nw", 1e-9), ("min_vdd", "min_vdd_v", 1),
                 ("rout", "rout_kohm", 1e3), ("vref_fom", "fom", 1)],
                ["tc_ref", "power"], ["tc_ref", "vref", "line_sens", "psrr_100", "power", "area"]),
    "cml_dco_vco": ([("f_center", "f_center_mhz", 1e6), ("f_min", "f_min_mhz", 1e6), ("f_max", "f_max_mhz", 1e6),
                     ("f_err", "abs_freq_err_pct", 1), ("tuning_range", "tuning_range_pct", 1),
                     ("tuning_ratio", "tuning_ratio", 1), ("fom_t", "fom_t_dbc", 1), ("vpp_diff", "vpp_diff_v", 1)]
                    + OSC + [("duty", "duty_pct", 1), ("vdd_sens", "vdd_sens_pct_per_v", 1),
                             ("tc_f", "temp_coeff_ppm_c", 1), ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
                    ["f_center", "tuning_range"], ["f_center", "tuning_range", "power", "fom_t", "pn_1m", "area"]),
    "bm_iref": ([("i_ref", "iref_ua", 1e-6), ("i_err", "curr_err_pct", 1), ("tc_ref", "tc_ppm_c", 1),
                 ("line_sens", "line_sens_pct_v", 1), ("rout", "rout_mohm", 1e6), ("psrr_100", "psrr_100hz_db", 1),
                 ("v_comp", "v_comp_v", 1), ("min_vdd", "min_vdd_v", 1), ("startup", "startup_ns", 1e-9),
                 ("trim_range", "trim_range_pct", 1), ("power", "power_uw", 1e-6), ("bm_fom", "fom", 1)],
                ["i_ref", "tc_ref"], ["i_ref", "tc_ref", "line_sens", "rout", "power", "area"]),
}


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def stage(c, st, fields):
    m = c.get(f"metrics_{st}")
    if not m:
        return None
    vals = {}
    for key, field, scale in fields:
        v = num(m.get(field))
        if key in ("kvco", "kdco") and field == "kvco_mhz_per_unit":
            unit = m.get("kvco_unit") or ""
            if (key == "kvco") != unit.endswith("/V"):
                v = None
        vals[key] = None if v is None else float(f"{v * scale:.6g}")
    cv = num(c.get(f"mc_cv_{st}"))
    vals["mc_cv"] = cv
    vals["area"] = num(m.get("area_um2")) or num(c.get("area_um2"))
    r = {"metrics": vals}
    p, t = num(c.get(f"pvt_pass_{st}")), num(c.get(f"pvt_total_{st}"))
    if t:
        r["pvt"] = {"pass": p, "total": t}
        r["robust"] = p == t           # classic report's green "PVT n/n" badge
    else:
        r["robust"] = False
    return r


# DCO/VCO families report the tuning gain per LSB (DCO) or per V (VCO) in one field.
for f in ("dco_vco", "cml_dco_vco"):
    FAM[f][0].extend([("kvco", "kvco_mhz_per_unit", 1e6), ("kdco", "kvco_mhz_per_unit", 1e6)])

fams = meta["families"]
topo_vals, target_vals, families = [], [], []
for f in fams:
    ft = f["tag"]
    topo_vals += [{"id": t["tag"], "label": t["short_name"]} for t in f["topologies"]]
    target_vals += [{"id": f"{ft}.{t['tag']}", "label": t["label"]} for t in f["targets"]]
    _, mx, cm = FAM[ft]
    families.append({
        "id": ft, "label": f["short_name"], "summary": f.get("summary", ""),
        "matrix": {"rows": ["topology"], "cols": ["target"], "metrics": mx},
        "card_metrics": cm,
    })

fam_order = {f["tag"]: i for i, f in enumerate(fams)}
topo_order = {t["tag"]: i for f in fams for i, t in enumerate(f["topologies"])}
tgt_order = {(f["tag"], t["tag"]): i for f in fams for i, t in enumerate(f["targets"])}
cards.sort(key=lambda c: (fam_order.get(c["family"], 99), topo_order.get(c["topo"], 99), c["vdd"],
                          tgt_order.get((c["family"], c["target_tag"]), 99), c["card_id"]))

PEX_NOTE = "Magic extraction of the full cell (device + parasitic C, cthresh 0.01 fF; no wire R)"
designs = []
for c in cards:
    cid, ft = c["card_id"], c["family"]
    fields = FAM[ft][0] + [("mc_cv", None, 1), ("area", None, 1)]
    results = {}
    if (s := stage(c, "pre", fields)):
        results["pre"] = s
    if c.get("has_post_pex") and (s := stage(c, "post", fields)):
        s["note"] = PEX_NOTE + ("; MOM lateral comb C added from calibrated model" if "_mom_" in c["topo"] else "")
        results["full"] = s
    cf = c.get("files") or {}
    files = {slot: cf[k] for slot, k in (
        ("schematic", "schematic_svg"), ("layout", "layout_svg"), ("gds", "gds_gz"),
        ("netlist", "netlist_spice"), ("pex_netlist", "pex_spice_gz"),
        ("lvs_netlist", "lvs_reference_spice"), ("data", "detail_json"))
        if cf.get(k) and (docs / cf[k]).is_file()}
    images = []
    if cf.get("schematic_design_svg") and (docs / cf["schematic_design_svg"]).is_file():
        images.append({"label": "Schematic (design view)", "path": cf["schematic_design_svg"]})
    params = {k: v for k, v in (c.get("knobs") or {}).items() if v is not None}
    params.update({"MOSFETs": c.get("n_mos"), "Capacitors": c.get("n_caps"), "Resistors": c.get("n_res"),
                   "Parasitic C (PEX)": c.get("parasitic_c_count")})
    designs.append({
        "id": cid,
        "title": f"{c['topo_short']} · {c['vdd']} V · {c['target_label']}",
        "family": ft,
        "vdd": c["vdd"],
        "axes": {"topology": c["topo"], "target": f"{ft}.{c['target_tag']}"},
        "tags": [t for t in (c.get("topo_name"), c.get("device_flavor"), c.get("circuit_style")) if t],
        "physical": {"drc": None if c.get("drc_ok") is None else bool(c["drc_ok"]),
                     "lvs": None if c.get("lvs_ok") is None else bool(c["lvs_ok"]),
                     "pex": None if c.get("pex_ok") is None else bool(c["pex_ok"]),
                     "area_um2": c.get("area_um2"), "width_um": c.get("width_um"), "height_um": c.get("height_um")},
        "results": results,
        "params": {k: v for k, v in params.items() if v is not None},
        "files": files,
        "images": images,
        "links": {"classic": f"index.html#d/{cid}/Overview"},
    })

cnt = meta.get("counts", {})
comp = {
    "schema": "aicdb-hub/1",
    "id": "aux",
    "name": "Aux blocks",
    "title": "GF180 Low-Power Auxiliary Block Library",
    "summary": "Ten auxiliary block families (ring, CML and tunable oscillators, clock dividers, tunable "
               "capacitor and resistor banks, current mirrors & IDACs, 2T voltage references and beta-multiplier "
               "current references) across 70 topologies at 1.8 V and 3.3 V. gm/Id sizing, 15-corner PVT, "
               "Monte Carlo, gLayout DRC/LVS and Magic PEX with post-layout re-simulation of every cell.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "topologies", "value": str(cnt.get("topologies_covered", len(topo_vals)))},
              {"label": "DSE points", "value": f"{cnt.get('total_dse_points', 0):,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b).items()
                 if v is not None} for k, l, u, si, b in METRICS],
    "axes": {
        "topology": {"label": "Topology", "values": topo_vals},
        "target": {"label": "Target", "values": target_vals},
    },
    "matrix": {"rows": ["topology"], "cols": ["target"], "metrics": ["power", "area"]},
    "card_metrics": ["power", "area"],
    "families": families,
    "designs": designs,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
