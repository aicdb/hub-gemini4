#!/usr/bin/env python3
"""Bootstrap hub adapter for aux-gen-gemini4 (schema aicdb-hub/2).

usage: aux.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/: data/index.json, data/dse.json, data/gmid.json,
cards/<id>/detail.json) and writes a collection (BUILDERS.md §4.3) under OUT_DIR (paths "hub/<path>"):

  component.json                 manifest {"id": "aux", "group": "Aux blocks", "components": [...]}
  <fam>/component.json           one component per block family, id "aux-<fam>" (own top-level tab)
  <fam>/pages/overview.json      family intro, retired per-family comparison table, coverage, data slices
  <fam>/pages/explore.json       family design-space explorer + generator Pareto overlay / facet grid
  <fam>/data/...                 explorer columns, static figures, per-family slices of the data files
  designs/<id>.json              one detail document per card (every section of the retired card page)
  pages/method.json              shared: methodology prose, gm/Id LUT charts, topology catalogue
  pages/collection.json          shared: retired hero, all-family master table and coverage, downloads

Each family has its own metrics, matrix (topology x target, supply as outer column group), presets and
card metrics. Stdlib only.

Honesty rules applied (see the inventory / report):
  * pre = metrics_pre, full = metrics_post (whole-cell Magic C-only extraction, noted per design).
  * Phase noise, jitter, oscillator/divider FoM, FoM_T and the tres "equivalent THD" are analytic
    estimates computed by the generator from simulated f/P/swing (or from the linearity error); they are
    NOT published as results, only in clearly labelled detail tables/charts and explorer dimensions.
  * Constant placeholders (tcap power/leakage, dco_vco INL/DNL, clk_div f_min, DSE area = 450 um^2) are
    left out; clip-limit values (cm_idac R_out = 5000 MOhm, cm_idac BW <= 0, bm_iref TC at 8/450 ppm/C)
    are omitted from results and flagged in the detail tables.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aux_detail  # noqa: E402
import aux_pages  # noqa: E402
from aux_fmt import isnum, write_json  # noqa: E402

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
idx = json.loads((docs / "data" / "index.json").read_text())
meta, cards = idx["meta"], idx["cards"]
dse = json.loads((docs / "data" / "dse.json").read_text())
gmid = json.loads((docs / "data" / "gmid.json").read_text())

METRICS = [
    # key, label, unit, si, better, digits   (union over all families, display order)
    ("f_osc", "f_osc", "Hz", True, None, 4),
    ("f_center", "Center frequency", "Hz", True, None, 4),
    ("f_min", "Tuning f_min", "Hz", True, "low", 4),
    ("f_max", "Tuning f_max", "Hz", True, "high", 4),
    ("f_max_in", "Max input frequency", "Hz", True, "high", 4),
    ("lock_range", "Locking range (≥, sweep-bounded)", "Hz", True, "high", 3),
    ("div_ratio", "Measured division ratio", "÷", False, None, 4),
    ("ratio_err", "Division ratio error", "%", False, "low", 3),
    ("vin_sens", "Min input sensitivity", "V", True, "low", 3),
    ("f_err", "|Frequency error| vs target", "%", False, "low", 3),
    ("tuning_range", "Tuning range", "%", False, "high", 3),
    ("kvco", "K_VCO", "Hz/V", True, None, 3),
    ("kdco", "K_DCO", "Hz/LSB", True, None, 3),
    ("c_max", "C_max", "F", True, None, 4),
    ("c_min", "C_min", "F", True, "low", 4),
    ("c_lsb", "C LSB", "F", True, None, 3),
    ("c_err", "|C_max error|", "%", False, "low", 3),
    ("q_100m", "Q @ 100 MHz", "", False, "high", 3),
    ("q_min_100m", "Min Q @ 100 MHz", "", False, "high", 3),
    ("esr", "ESR", "Ω", True, "low", 3),
    ("tcap_fom", "FoM (Q × tuning ratio)", "", False, "high", 3),
    ("r_nom", "R_nom", "Ω", True, None, 4),
    ("r_min", "R_min", "Ω", True, None, 4),
    ("r_max", "R_max", "Ω", True, None, 4),
    ("r_err", "|R_nom error|", "%", False, "low", 3),
    ("tuning_ratio", "Tuning ratio (max/min)", "×", False, "high", 3),
    ("lin_err", "I–V linearity error", "%", False, "low", 3),
    ("tc_r", "R temp. coeff.", "ppm/°C", False, "low", 3),
    ("i_fs", "I_FS / I_out", "A", True, None, 4),
    ("i_lsb", "I LSB", "A", True, None, 3),
    ("copy_err", "Copy error", "%", False, "low", 3),
    ("v_comp", "Compliance voltage", "V", True, "low", 3),
    ("rout", "Output resistance", "Ω", True, "high", 3),
    ("bw", "Bandwidth (−3 dB)", "Hz", True, "high", 3),
    ("t_settle", "Settling time", "s", True, "low", 3),
    ("inl", "INL", "LSB", False, "low", 3),
    ("dnl", "DNL", "LSB", False, "low", 3),
    ("vref", "V_REF (27 °C)", "V", True, None, 4),
    ("i_ref", "I_REF (TT, code 4)", "A", True, None, 4),
    ("i_err", "|I_REF error|", "%", False, "low", 3),
    ("tc_ref", "Temp. coeff. (−40..125 °C)", "ppm/°C", False, "low", 3),
    ("line_sens", "Line sensitivity", "%/V", False, "low", 3),
    ("psrr_100", "PSRR @ 100 Hz", "dB", False, "high", 3),
    ("min_vdd", "Min supply", "V", True, "low", 3),
    ("startup", "Start-up time", "s", True, "low", 3),
    ("trim_range", "Trim range", "%", False, "high", 3),
    ("vref_fom", "FoM (1e4 / (TC·√P_nW))", "", False, "high", 3),
    ("bm_fom", "Composite FoM", "", False, "high", 3),
    ("power", "Power", "W", True, "low", 3),
    ("energy", "Energy per cycle", "J", True, "low", 3),
    ("vpp_diff", "Diff. swing V_pp", "V", True, "high", 3),
    ("vpp_out", "Output swing V_pp", "V", True, "high", 3),
    ("swing", "Output swing", "V", True, "high", 3),
    ("duty", "Duty cycle", "%", False, None, 3),
    ("t_start", "Oscillation start-up", "s", True, "low", 3),
    ("vdd_sens", "f supply sensitivity", "%/V", False, None, 3),
    ("tc_f", "f temp. coeff.", "ppm/°C", False, None, 3),
    ("mc_cv", "MC spread σ/µ (primary metric)", "%", False, "low", 3),
    ("area", "Layout area", "µm²", False, "low", 4),
]
MLABEL = {k: l for k, l, *_ in METRICS}

# Per family: fields (hub key, source field, scale), matrix metrics, presets, card metrics.
# "mc_cv" and "area" are appended to every family.
FAM = {
    "ro": ([("f_osc", "f_osc_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1), ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6),
            ("duty", "duty_pct", 1), ("swing", "swing_v", 1), ("t_start", "t_start_ns", 1e-9), ("vdd_sens", "vdd_sens_pct_per_v", 1),
            ("tc_f", "temp_coeff_ppm_c", 1)],
           ["f_osc", "power", "energy"], [("f_osc / energy per cycle", ["f_osc", "energy"]), ("Frequency error / f_osc", ["f_err", "f_osc"]),
                                ("Duty cycle / swing", ["duty", "swing"]), ("Supply / temperature sensitivity", ["vdd_sens", "tc_f"])],
           ["f_osc", "power", "energy", "f_err", "duty", "swing", "t_start", "vdd_sens", "tc_f", "mc_cv", "area"]),
    "tcap": ([("c_max", "c_max_pf", 1e-12), ("c_min", "c_min_pf", 1e-12), ("c_lsb", "c_lsb_ff", 1e-15), ("c_err", "c_err_pct", 1),
              ("tuning_ratio", "tuning_ratio", 1), ("q_100m", "q_factor_100m", 1), ("q_min_100m", "q_min_100m", 1), ("esr", "esr_ohm", 1),
              ("tcap_fom", "fom", 1), ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
             ["c_max", "tuning_ratio", "q_100m"], [("C_max / Q @ 100 MHz", ["c_max", "q_100m"]), ("C_min / tuning ratio", ["c_min", "tuning_ratio"]),
                                         ("ESR / INL", ["esr", "inl"])],
             ["c_max", "c_min", "tuning_ratio", "q_100m", "esr", "inl", "dnl", "c_lsb", "c_err", "tcap_fom", "mc_cv", "area"]),
    "tres": ([("r_nom", "r_nom_kohm", 1e3), ("r_min", "r_min_kohm", 1e3), ("r_max", "r_max_kohm", 1e3), ("r_err", "r_err_pct", 1),
              ("tuning_ratio", "tuning_ratio", 1), ("lin_err", "linearity_err_pct", 1), ("bw", "bw_3db_mhz", 1e6),
              ("tc_r", "temp_coeff_ppm_c", 1), ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
             ["r_nom", "tuning_ratio", "bw"], [("R_nom / bandwidth", ["r_nom", "bw"]), ("Linearity / TC", ["lin_err", "tc_r"]), ("R error / R_nom", ["r_err", "r_nom"])],
             ["r_nom", "r_min", "r_max", "tuning_ratio", "lin_err", "bw", "tc_r", "inl", "dnl", "r_err", "mc_cv", "area"]),
    "cm_idac": ([("i_fs", "i_fs_ua", 1e-6), ("i_lsb", "lsb_ua", 1e-6), ("copy_err", "copy_err_pct", 1), ("v_comp", "v_comp_v", 1),
                 ("rout", "rout_mohm", 1e6), ("bw", "bw_mhz", 1e6), ("t_settle", "t_settle_ns", 1e-9), ("inl", "inl_lsb", 1),
                 ("dnl", "dnl_lsb", 1), ("power", "power_uw", 1e-6)],
                ["i_fs", "rout", "v_comp"], [("I_FS / compliance", ["i_fs", "v_comp"]), ("Copy error / INL", ["copy_err", "inl"]), ("Bandwidth / settling", ["bw", "t_settle"])],
                ["i_fs", "rout", "v_comp", "copy_err", "inl", "bw", "t_settle", "dnl", "i_lsb", "power", "mc_cv", "area"]),
    "dco_vco": ([("f_center", "f_center_mhz", 1e6), ("f_min", "f_min_mhz", 1e6), ("f_max", "f_max_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1),
                 ("tuning_range", "tuning_range_pct", 1), ("tuning_ratio", "tuning_ratio", 1), ("energy", "energy_fj", 1e-15),
                 ("power", "power_uw", 1e-6), ("swing", "swing_v", 1), ("duty", "duty_pct", 1), ("tc_f", "temp_coeff_ppm_c", 1)],
                ["f_center", "tuning_range", "power"], [("f_center / power", ["f_center", "power"]), ("Tuning span f_min / f_max", ["f_min", "f_max"]),
                                               ("Frequency error / f_center", ["f_err", "f_center"])],
                ["f_center", "f_min", "f_max", "tuning_range", "kdco", "kvco", "power", "energy", "f_err", "tuning_ratio", "mc_cv", "area"]),
    "cml_ro": ([("f_osc", "f_osc_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1), ("vpp_diff", "vpp_diff_v", 1), ("tuning_range", "tuning_range_pct", 1),
                ("kvco", "kvco_mhz_per_v", 1e6), ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6), ("duty", "duty_pct", 1),
                ("t_start", "t_start_ns", 1e-9), ("vdd_sens", "vdd_sens_pct_per_v", 1), ("tc_f", "temp_coeff_ppm_c", 1)],
               ["f_osc", "vpp_diff", "power"], [("f_osc / power", ["f_osc", "power"]), ("Tuning range / K_VCO", ["tuning_range", "kvco"]),
                                       ("Frequency error / f_osc", ["f_err", "f_osc"])],
               ["f_osc", "vpp_diff", "power", "energy", "tuning_range", "kvco", "f_err", "duty", "t_start", "tc_f", "mc_cv", "area"]),
    "clk_div": ([("f_max_in", "f_max_ghz", 1e9), ("lock_range", "lock_range_ghz", 1e9), ("div_ratio", "div_ratio_meas", 1),
                 ("ratio_err", "ratio_err_pct", 1), ("vin_sens", "min_vin_sens_v", 1), ("vpp_out", "vpp_out_v", 1), ("duty", "duty_pct", 1),
                 ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6)],
                ["f_max_in", "div_ratio", "lock_range"], [("f_max,in / power", ["f_max_in", "power"]), ("Input sensitivity / output swing", ["vin_sens", "vpp_out"]),
                                             ("Division ratio / error", ["div_ratio", "ratio_err"])],
                ["f_max_in", "div_ratio", "lock_range", "vin_sens", "vpp_out", "power", "energy", "ratio_err", "duty", "mc_cv", "area"]),
    "vref_2t": ([("vref", "vref_mv", 1e-3), ("tc_ref", "tc_ppm_c", 1), ("line_sens", "line_sens_pct_v", 1), ("psrr_100", "psrr_100hz_db", 1),
                 ("power", "power_nw", 1e-9), ("min_vdd", "min_vdd_v", 1), ("rout", "rout_kohm", 1e3), ("vref_fom", "fom", 1)],
                ["tc_ref", "vref", "power"], [("TC / V_REF", ["tc_ref", "vref"]), ("Line sensitivity / PSRR", ["line_sens", "psrr_100"]),
                                      ("Min supply / FoM", ["min_vdd", "vref_fom"])],
                ["tc_ref", "vref", "line_sens", "psrr_100", "power", "min_vdd", "rout", "vref_fom", "mc_cv", "area"]),
    "cml_dco_vco": ([("f_center", "f_center_mhz", 1e6), ("f_min", "f_min_mhz", 1e6), ("f_max", "f_max_mhz", 1e6), ("f_err", "abs_freq_err_pct", 1),
                     ("tuning_range", "tuning_range_pct", 1), ("tuning_ratio", "tuning_ratio", 1), ("vpp_diff", "vpp_diff_v", 1),
                     ("energy", "energy_fj", 1e-15), ("power", "power_uw", 1e-6), ("duty", "duty_pct", 1), ("vdd_sens", "vdd_sens_pct_per_v", 1),
                     ("tc_f", "temp_coeff_ppm_c", 1), ("inl", "inl_lsb", 1), ("dnl", "dnl_lsb", 1)],
                    ["f_center", "tuning_range", "power"], [("f_center / power", ["f_center", "power"]), ("Tuning linearity INL / DNL", ["inl", "dnl"]),
                                                   ("Differential swing / f_center", ["vpp_diff", "f_center"])],
                    ["f_center", "f_min", "f_max", "tuning_range", "kdco", "kvco", "vpp_diff", "power", "energy", "inl", "mc_cv", "area"]),
    "bm_iref": ([("i_ref", "iref_ua", 1e-6), ("i_err", "curr_err_pct", 1), ("tc_ref", "tc_ppm_c", 1), ("line_sens", "line_sens_pct_v", 1),
                 ("rout", "rout_mohm", 1e6), ("psrr_100", "psrr_100hz_db", 1), ("v_comp", "v_comp_v", 1), ("min_vdd", "min_vdd_v", 1),
                 ("startup", "startup_ns", 1e-9), ("trim_range", "trim_range_pct", 1), ("power", "power_uw", 1e-6), ("bm_fom", "fom", 1)],
                ["i_ref", "tc_ref", "line_sens"], [("I_REF / line sensitivity", ["i_ref", "line_sens"]), ("R_out / PSRR", ["rout", "psrr_100"]),
                                      ("Start-up / power", ["startup", "power"])],
                ["i_ref", "trim_range", "tc_ref", "line_sens", "rout", "psrr_100", "v_comp", "min_vdd", "startup", "power", "mc_cv", "area"]),
}
for f in ("dco_vco", "cml_dco_vco"):   # K_DCO (per LSB) / K_VCO (per V) share one source field; split by kvco_unit
    FAM[f][0].extend([("kvco", "kvco_mhz_per_unit", 1e6), ("kdco", "kvco_mhz_per_unit", 1e6)])

# values that sit on a generator clip limit are bounds, not measurements -> omitted from results
CLIPS = {
    ("cm_idac", "rout"): (lambda v: v >= 5000.0, "R_out reached the 5000 MΩ clip limit of the |Z_out| extraction"),
    ("cm_idac", "bw"): (lambda v: v <= 0.0, "no −3 dB point found in the AC sweep (BW reported as 0)"),
    ("bm_iref", "tc_ref"): (lambda v: v in (8.0, 450.0), "TC sits on the generator's 8 / 450 ppm/°C clip limit"),
}
PEX_NOTE = "Magic extraction of the full cell (devices + parasitic C, cthresh 0.01 fF; no wire R)"
SAME_NOTE = "; all post-PEX metrics equal the pre-PEX values (DC quantities insensitive to the C-only extraction)"


def stage(c, st, ft):
    m = c.get(f"metrics_{st}")
    if not m:
        return None
    vals, notes = {}, []
    for key, field, scale in FAM[ft][0]:
        v = m.get(field)
        v = v if isnum(v) else None
        if key in ("kvco", "kdco"):
            unit = m.get("kvco_unit") or ""
            if (key == "kvco") != unit.endswith("/V"):
                v = None
        if v is not None and (ft, key) in CLIPS and CLIPS[(ft, key)][0](v):
            notes.append(f"{MLABEL[key]} omitted: {CLIPS[(ft, key)][1]}")
            v = None
        vals[key] = None if v is None else float(f"{v * scale:.6g}")
    vals["mc_cv"] = c.get(f"mc_cv_{st}") if isnum(c.get(f"mc_cv_{st}")) else None
    vals["area"] = c.get("area_um2")
    r = {"metrics": vals}
    p, t = c.get(f"pvt_pass_{st}"), c.get(f"pvt_total_{st}")
    if isnum(t) and t:
        r["pvt"] = {"pass": p, "total": t}
        r["robust"] = p == t
    else:
        r["robust"] = False
    return r, notes


fams = meta["families"]
topo_by = {t["tag"]: (f, t) for f in fams for t in f["topologies"]}
slug = lambda s: "".join(ch if ch.isalnum() else "_" for ch in s.lower()).strip("_")
NAMES = {"ro": "Ring osc", "tcap": "Tunable caps", "tres": "Tunable res", "cm_idac": "Mirrors/IDACs", "dco_vco": "DCOs & VCOs",
         "cml_ro": "CML osc", "clk_div": "Clock dividers", "vref_2t": "2T Vref", "cml_dco_vco": "CML DCO/VCO", "bm_iref": "Beta-mult Iref"}
EST_FAMS = ("ro", "cml_ro", "dco_vco", "cml_dco_vco", "clk_div")

fam_order = {f["tag"]: i for i, f in enumerate(fams)}
topo_order = {t["tag"]: i for f in fams for i, t in enumerate(f["topologies"])}
tgt_order = {(f["tag"], t["tag"]): i for f in fams for i, t in enumerate(f["targets"])}
cards.sort(key=lambda c: (fam_order.get(c["family"], 99), topo_order.get(c["topo"], 99), c["vdd"],
                          tgt_order.get((c["family"], c["target_tag"]), 99), c["card_id"]))


def design_record(c, d):
    cid, ft = c["card_id"], c["family"]
    results = {}
    s = stage(c, "pre", ft)
    if s:
        results["pre"] = s[0]
        if s[1]:
            s[0]["note"] = "; ".join(s[1])
    if c.get("has_post_pex"):
        s = stage(c, "post", ft)
        if s:
            note = PEX_NOTE + ("; MOM lateral comb C added from calibrated model" if "_mom_" in c["topo"] else "")
            if c.get("metrics_pre") == c.get("metrics_post"):
                note += SAME_NOTE
            s[0]["note"] = "; ".join([note] + s[1])
            results["full"] = s[0]
    cf = c.get("files") or {}
    files = {slot: cf[k] for slot, k in (
        ("schematic", "schematic_svg"), ("gds", "gds_gz"), ("netlist", "netlist_spice"), ("pex_netlist", "pex_spice_gz"),
        ("lvs_netlist", "lvs_reference_spice"), ("data", "detail_json")) if cf.get(k) and (docs / cf[k]).is_file()}
    sch_design = cf.get("schematic_design_svg") if cf.get("schematic_design_svg") and (docs / cf["schematic_design_svg"]).is_file() else None
    images = [{"label": "Schematic (design sizing view)", "src": sch_design}] if sch_design else []
    params = {}
    for k, v in (c.get("knobs") or {}).items():
        if v is not None:
            params[f"knob {k}"] = float(f"{v:.4g}") if isnum(v) else v
    if ft == "clk_div" and (c.get("metrics_pre") or {}).get("div_ratio_nom") is not None:
        params["Nominal division ratio"] = f"÷{c['metrics_pre']['div_ratio_nom']}"
    params.update({"Ports": ", ".join(c.get("ports") or []), "MOSFETs": c.get("n_mos"), "Capacitors": c.get("n_caps"),
                   "Resistors": c.get("n_res"), "Parasitic C (PEX)": c.get("parasitic_c_count"),
                   "Generator spec status": c.get("status"), "Artifact SHA-256": c.get("sha256")})
    fl = topo_by.get(c["topo"], (None, {}))[1].get("device_flavor") or c.get("device_flavor") or ""
    rec = {
        "id": cid,
        "title": f"{c['topo_name']} · {c['vdd']} V · {c['target_label']}",
        "summary": (d or {}).get("topo_summary") or "",
        "vdd": c["vdd"],
        "axes": {"topology": c["topo"], "target": c["target_tag"], "flavor": slug(fl)},
        "tags": [t for t in (c.get("family_name"), c.get("device_flavor"), c.get("circuit_style"),
                             "Spec ✓ (generator status pass)" if c.get("status") == "pass" else f"status: {c.get('status')}") if t],
        "physical": {"drc": None if c.get("drc_ok") is None else bool(c["drc_ok"]),
                     "lvs": None if c.get("lvs_ok") is None else bool(c["lvs_ok"]),
                     "pex": None if c.get("pex_ok") is None else bool(c["pex_ok"]),
                     "area_um2": c.get("area_um2"), "width_um": c.get("width_um"), "height_um": c.get("height_um")},
        "results": results,
        "params": {k: v for k, v in params.items() if v is not None and v != ""},
        "files": files,
        "images": images,
    }
    if d:
        write_json(out / "designs" / f"{cid}.json", aux_detail.build(d, files, sch_design))
        rec["detail"] = f"hub/designs/{cid}.json"
    return rec


details = {}
for c in cards:
    dpath = docs / "cards" / c["card_id"] / "detail.json"
    if dpath.is_file():
        details[c["card_id"]] = json.loads(dpath.read_text())

shared_pages = aux_pages.build_shared(docs, out, meta, cards, gmid)
generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
manifest = []
for f in fams:
    ft = f["tag"]
    fcards = [c for c in cards if c["family"] == ft]
    if not fcards:
        continue
    fields, mx, presets, cm = FAM[ft]
    used = {k for k, _, _ in fields} | {"mc_cv", "area"}
    summ = f"{f.get('summary', '').replace('`', '')} Primary metric on the retired site: {f['primary_metric_label']} ({f['primary_metric_unit']})."
    if ft == "clk_div":
        summ += " Note: f_min is the lowest swept input (0.25 GHz) for every card, so the locking range is bounded by the sweep."
    if ft in EST_FAMS:
        summ += " Phase noise / jitter / FoM are analytic estimates and are shown on the design pages only."
    flavors = []
    for t in f["topologies"]:
        v = {"id": slug(t["device_flavor"]), "label": t["device_flavor"]}
        if v not in flavors:
            flavors.append(v)
    fd = (dse.get("families") or {}).get(ft) or {}
    pages = aux_pages.build_family(docs, out, meta, f, fcards, fd, dse, details) + shared_pages
    comp = {
        "schema": "aicdb-hub/2",
        "id": f"aux-{ft}",
        "name": NAMES.get(ft, f["short_name"])[:14],
        "title": f"{f['icon']} {f['name']}",
        "summary": summ,
        "technology": "gf180mcuD",
        "generated": generated,
        "stats": [{"label": "topologies", "value": str(len(f["topologies"]))},
                  {"label": "DSE candidates", "value": f"{len(fd.get('points') or []):,}"},
                  {"label": "PVT corners / card", "value": "15"}, {"label": "MC runs / card", "value": "30"}],
        "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b, digits=dg).items() if v is not None}
                    for k, l, u, si, b, dg in METRICS if k in used],
        "axes": {
            "topology": {"label": "Topology", "values": [{"id": t["tag"], "label": t["short_name"]} for t in f["topologies"]]},
            "flavor": {"label": "Device flavor", "values": flavors},
            "target": {"label": "Target band", "values": [{"id": t["tag"], "label": t["label"]} for t in f["targets"]]},
        },
        "matrix": {"rows": ["topology", "flavor"], "cols": ["target"], "metrics": mx,
                   "presets": [{"label": f"Retired-site headline: {' / '.join(MLABEL[k] for k in mx)}", "metrics": mx}] +
                              [{"label": lab, "metrics": ms} for lab, ms in presets]},
        "card_metrics": cm,
        "pages": pages,
        "designs": [design_record(c, details.get(c["card_id"])) for c in fcards],
    }
    write_json(out / ft / "component.json", comp, 6)
    manifest.append(f"hub/{ft}/component.json")

write_json(out / "component.json", {"schema": "aicdb-hub/2", "id": "aux", "group": "Aux blocks", "components": manifest})
