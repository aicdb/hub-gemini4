"""Extra pages for the aux adapter: Overview (hero / all-family table / downloads), Design-space
explorer (ports showExplorerView + drawExplorerCharts) and Methodology (verbatim prose, gm/Id charts,
topology catalogue)."""
import json
import math
import re

from aux_fmt import DASH, fmt_mhz, isnum, num, write_json

PALETTE = ["#2563eb", "#ea580c", "#059669", "#d97706", "#7c3aed", "#db2777", "#0284c7", "#dc2626", "#4f46e5"]
EXPLORER_LABEL = {"ro": "∿ RingOsc (ro)", "tcap": "⊣⊢ TunableCap (tcap)", "tres": "⌇ TunableRes (tres)", "cm_idac": "⇉ Mirrors & IDACs (cm_idac)",
                  "dco_vco": "⟳ DCOs & VCOs (dco_vco)", "cml_ro": "⚡ CML Osc (cml_ro)", "cml_dco_vco": "🎛 CML DCO/VCO (cml_dco_vco)",
                  "clk_div": "÷ ClockDiv (clk_div)", "vref_2t": "⏚ 2T Vref (vref_2t)", "bm_iref": "∮ Beta-Mult Iref (bm_iref)"}
SUPPLY = [("all", "All supplies", None), ("1v8", "1.8 V", 1.8), ("3v3", "3.3 V", 3.3)]

# old FAMILY_AXIS_OPTIONS (key, label, log) — the retired explorer's X/Y choices
AXIS_OPTS = {
    "ro": [("power_uw", "DC Power P_DC (µW)", 1), ("f_osc_mhz", "Oscillation Frequency f_osc (MHz)", 1), ("phase_noise_dbc_1m", "Phase Noise L(1 MHz) (dBc/Hz)", 0),
           ("fom_dbc", "Figure of Merit FoM (dBc/Hz)", 0), ("energy_fj", "Energy per Cycle (fJ/cycle)", 1), ("jitter_ps", "RMS Jitter J_cc (ps)", 1), ("area_um2", "Silicon Area (µm²)", 1)],
    "tcap": [("tuning_ratio", "Tuning Ratio C_max/C_min (×)", 0), ("q_factor_100m", "Quality Factor Q @ 100 MHz", 1), ("c_max_pf", "Max Capacitance C_max (pF)", 1),
             ("c_min_pf", "Min Capacitance C_min (pF)", 1), ("esr_ohm", "Series Resistance ESR (Ω)", 1), ("fom", "FoM = Q × Tuning Ratio", 1), ("area_um2", "Silicon Area (µm²)", 1)],
    "tres": [("tuning_ratio", "Tuning Ratio R_max/R_min (×)", 0), ("thd_db", "Equivalent Linearity THD (dB)", 0), ("linearity_err_pct", "I-V Linearity Error (%)", 1),
             ("r_nom_kohm", "Nominal Resistance R_nom (kΩ)", 1), ("bw_3db_mhz", "-3 dB Bandwidth (MHz)", 1), ("inl_lsb", "Conductance INL (LSB)", 0), ("area_um2", "Silicon Area (µm²)", 1)],
    "cm_idac": [("v_comp_v", "Compliance Voltage V_comp (V)", 0), ("rout_mohm", "Output Impedance R_out (MΩ)", 1), ("copy_err_pct", "Copy Error / Non-Linearity (%)", 1),
                ("i_fs_ua", "Full-Scale Current I_FS (µA)", 1), ("bw_mhz", "Output Bandwidth (MHz)", 1), ("inl_lsb", "DAC INL (LSB)", 0), ("area_um2", "Silicon Area (µm²)", 1)],
    "dco_vco": [("power_uw", "Center-Freq Power P_DC (µW)", 1), ("tuning_range_pct", "Frequency Tuning Range (%)", 0), ("f_center_mhz", "Center Frequency f_center (MHz)", 1),
                ("phase_noise_dbc_1m", "Phase Noise L(1 MHz) (dBc/Hz)", 0), ("fom_t_dbc", "Tuning FoM_T (dBc/Hz)", 0), ("kvco_mhz_per_unit", "Tuning Gain K_DCO / K_VCO", 1),
                ("area_um2", "Silicon Area (µm²)", 1)],
    "cml_ro": [("power_uw", "DC Power P_DC (µW)", 1), ("f_osc_mhz", "Oscillation Frequency f_osc (MHz)", 0), ("vpp_diff_v", "Differential Swing V_pp,diff (V)", 0),
               ("phase_noise_dbc_1m", "Phase Noise L(1 MHz) (dBc/Hz)", 0), ("fom_dbc", "Figure of Merit FoM (dBc/Hz)", 0), ("tuning_range_pct", "Bias/Vctrl Tuning Range (%)", 0),
               ("energy_fj", "Energy per Cycle (fJ/cyc)", 1), ("area_um2", "Silicon Area (µm²)", 1)],
    "clk_div": [("power_uw", "DC Power P_DC (µW)", 1), ("f_max_ghz", "Max Input Frequency f_max,in (GHz)", 0), ("lock_range_ghz", "Locking Bandwidth Δf_lock (GHz)", 0),
                ("min_vin_sens_v", "Min Input Clock Sensitivity V_in,min (V_pp)", 0), ("vpp_out_v", "Output Swing V_pp,out (V)", 0), ("energy_fj", "Energy per Input Cycle (fJ/cyc)", 1),
                ("area_um2", "Silicon Area (µm²)", 1)],
    "vref_2t": [("power_nw", "Quiescent Power P_DC (nW)", 1), ("tc_ppm_c", "Temperature Coefficient TC (ppm/°C)", 1), ("vref_mv", "Reference Voltage V_REF (mV)", 0),
                ("line_sens_pct_v", "DC Line Sensitivity (%/V)", 1), ("psrr_100hz_db", "PSRR @ 100 Hz (dB)", 0), ("min_vdd_v", "Min Supply Voltage V_DD,min (V)", 0),
                ("area_um2", "Silicon Area (µm²)", 1)],
    "cml_dco_vco": [("power_uw", "Center-Freq Power P_DC (µW)", 1), ("tuning_range_pct", "RF Frequency Tuning Range (%)", 0), ("f_center_mhz", "RF Center Frequency f_center (MHz)", 0),
                    ("fom_t_dbc", "Tuning FoM_T (dBc/Hz)", 0), ("phase_noise_dbc_1m", "Phase Noise L(1 MHz) (dBc/Hz)", 0), ("vpp_diff_v", "Differential Swing V_pp,diff (V)", 0),
                    ("kvco_mhz_per_unit", "Tuning Gain K_DCO / K_VCO", 1), ("area_um2", "Silicon Area (µm²)", 1)],
    "bm_iref": [("power_uw", "Quiescent Power P_DC (µW)", 1), ("tc_ppm_c", "Temperature Coefficient TC (ppm/°C)", 1), ("iref_ua", "Reference Current I_REF (µA)", 1),
                ("line_sens_pct_v", "DC Line Sensitivity (%/V)", 1), ("rout_mohm", "Output Resistance R_out (MΩ)", 1), ("psrr_100hz_db", "PSRR @ 100 Hz (dB)", 0),
                ("min_vdd_v", "Min Supply Voltage V_DD,min (V)", 0), ("area_um2", "Silicon Area (µm²)", 1)],
}
# analytic-model quantities (not simulated) and formula-derived ones -> labelled in explorer dims
ESTIMATE_KEYS = {"phase_noise_dbc_1m", "pn_1m_dbc", "pn_100k_dbc", "pn_10m_dbc", "phase_noise_floor_dbc", "jitter_ps", "jitter_rms_ps", "fom_dbc", "fom_t_dbc"}
FORMULA_KEYS = {"thd_db": "formula from linearity error", "area_est_um2": "generator area estimate, not layout"}
SKIP_KEYS = {"idx", "topo", "vdd", "vdd_tag", "knobs", "card_id", "target_tag", "error"}
BETTER = {"power_uw": "low", "power_nw": "low", "p_dc_uw": "low", "energy_fj": "low", "energy_pj": "low", "energy_fj_per_cycle": "low", "energy_fj_per_in_cycle": "low",
          "area_um2": "low", "area_est_um2": "low", "jitter_ps": "low", "jitter_rms_ps": "low", "phase_noise_dbc_1m": "low", "pn_1m_dbc": "low",
          "phase_noise_floor_dbc": "low", "fom_dbc": "low", "fom_t_dbc": "low", "tc_ppm_c": "low", "line_sens_pct_v": "low", "psrr_100hz_db": "high",
          "min_vdd_v": "low", "copy_err_pct": "low", "v_comp_v": "low", "rout_mohm": "high", "bw_mhz": "high", "bw_3db_mhz": "high", "tuning_ratio": "high",
          "tuning_range_pct": "high", "q_factor_100m": "high", "q_min_100m": "high", "esr_ohm": "low", "linearity_err_pct": "low", "thd_db": "low",
          "f_max_ghz": "high", "lock_range_ghz": "high", "min_vin_sens_v": "low", "vpp_out_v": "high", "vpp_diff_v": "high", "f_osc_mhz": "high",
          "f_center_mhz": "high", "c_max_pf": "high", "c_min_pf": "low", "inl_lsb": "low", "dnl_lsb": "low", "r_nom_kohm": "high", "i_fs_ua": "high",
          "iref_ua": "high", "curr_err_pct": "low", "acc_err_pct": "low", "startup_ns": "low", "t_settle_ns": "low", "fom": "high", "ratio_err_pct": "low",
          "c_err_pct": "low", "r_err_pct": "low"}
UNITS = [  # suffix -> (unit, scale, si)
    ("_mhz_per_v", ("Hz/V", 1e6, True)), ("_mhz_per_unit", ("MHz per LSB or per V", 1, False)), ("_pct_per_v", ("%/V", 1, False)),
    ("_pct_v", ("%/V", 1, False)), ("_fj_per_in_cycle", ("J", 1e-15, True)), ("_fj_per_cycle", ("J", 1e-15, True)), ("_ppm_c", ("ppm/°C", 1, False)),
    ("_dbc_1m", ("dBc/Hz", 1, False)), ("_dbc", ("dBc/Hz", 1, False)), ("_db", ("dB", 1, False)), ("_um2", ("µm²", 1, False)), ("_kohm", ("Ω", 1e3, True)),
    ("_mohm", ("Ω", 1e6, True)), ("_ohm", ("Ω", 1, True)), ("_ghz", ("Hz", 1e9, True)), ("_mhz", ("Hz", 1e6, True)), ("_hz", ("Hz", 1, True)),
    ("_uw", ("W", 1e-6, True)), ("_nw", ("W", 1e-9, True)), ("_pf", ("F", 1e-12, True)), ("_ff", ("F", 1e-15, True)), ("_ua", ("A", 1e-6, True)),
    ("_na", ("A", 1e-9, True)), ("_um", ("m", 1e-6, True)), ("_ns", ("s", 1e-9, True)), ("_ps", ("s", 1e-12, True)), ("_fj", ("J", 1e-15, True)),
    ("_pj", ("J", 1e-12, True)), ("_mv", ("V", 1e-3, True)), ("_v", ("V", 1, True)), ("_pct", ("%", 1, False)), ("_lsb", ("LSB", 1, False)),
]
NICE = {"gmid": "g_m/I_D target", "sw_gmid": "switch g_m/I_D", "switch_gmid": "switch g_m/I_D", "target_gmid": "g_m/I_D target", "target_gmid_n": "NMOS g_m/I_D target",
        "target_gmid_p": "PMOS g_m/I_D target", "m_core": "core multiplicity m", "m_p": "PMOS multiplicity m_p", "fom": "Figure of merit", "pareto": "Generator Pareto flag",
        "ok": "Simulation ok flag", "n_phases": "Number of phases", "div_ratio_nom": "Nominal division ratio", "tuning_ratio": "Tuning ratio (max/min)",
        "q_min": "Min Q", "monotonic": "Monotonic", "linearity_r2": "Tuning linearity R²", "load_scale": "Load scale", "c_scale": "Cap scale", "r_scale": "Resistor scale",
        "n_bits": "Number of bits", "k_ratio": "Beta-multiplier ratio K", "center_code": "Trim centre code", "trim_bits": "Trim bits",
        "aspect_ratio_top_bot": "Aspect ratio top/bottom", "mod1_ok": "Modulus-1 ok", "div_ratio_mod0": "Div ratio (mod 0)", "div_ratio_mod1": "Div ratio (mod 1)",
        "div_ratio_meas": "Measured division ratio", "kvco_unit": "Gain unit"}


def strip_unit(label):
    return re.sub(r"\s*\([^()]*\)\s*$", "", label)


def unit_of(key):
    for suf, u in UNITS:
        if key.endswith(suf):
            return u
    return ("", 1, False)


def pretty(key):
    if key in NICE:
        return NICE[key]
    base = key
    for suf, _ in UNITS:
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    return base.replace("_", " ")


# ----------------------------------------------------------------------------- explorer data
ALIASES = {"energy_pj", "i_dd_ua", "jitter_rms_ps", "pn_1m_dbc", "p_dc_uw", "energy_fj_per_cycle", "energy_fj_per_in_cycle", "f_osc_ghz",
           "f_center_ghz", "f_osc_hz", "f_out_mhz", "f_in_mhz", "f_max_mhz", "vpp_v", "i_ref_ua", "f_target_mhz", "target_f_mhz", "abs_freq_err_pct"}
# DSE-only fields the site generator filled with defaults / derived from placeholders (kept for delivered cards only)
DSE_NULL = {"freq_err_pct": "computed against the placeholder target 1.0 in dse.json",
            "vdd_sens_pct_per_v": "site-normaliser default in dse.json",
            "kvco_mhz_per_v": "derived from the 38 % tuning-range placeholder in dse.json"}
NICE.update({"duty_pct": "Duty cycle", "swing_v": "Output swing", "tr_ns": "Rise time", "tf_ns": "Fall time", "t_rise_ps": "Rise time", "t_fall_ps": "Fall time",
             "freq_err_pct": "Frequency error vs target", "idd_ua": "Supply current", "idd_na": "Supply current", "t_start_ns": "Oscillation start-up",
             "settling_drift_pct": "Settling drift", "vdd_sens_pct_per_v": "f supply sensitivity", "temp_coeff_ppm_c": "Temperature coefficient",
             "tuning_range_pct": "Tuning range", "kvco_mhz_per_v": "K_VCO", "vpp_diff_v": "Differential swing V_pp", "vpp_se_v": "Single-ended swing V_pp",
             "vpp_out_v": "Output swing V_pp", "curr_err_pct": "Reference-current error", "acc_err_pct": "Accuracy error at centre code",
             "jitter_ps": "RMS jitter", "phase_noise_dbc_1m": "Phase noise L(1 MHz)", "pn_100k_dbc": "Phase noise L(100 kHz)", "pn_10m_dbc": "Phase noise L(10 MHz)",
             "phase_noise_floor_dbc": "Additive phase-noise floor", "fom_dbc": "FoM", "fom_t_dbc": "Tuning FoM_T", "f_out_ghz": "Output frequency",
             "f_in_ghz": "Input frequency", "div_ratio_meas": "Measured division ratio", "ratio_err_pct": "Division-ratio error", "min_vin_sens_v": "Min input sensitivity",
             "lock_range_ghz": "Locking range", "f_min_ghz": "Lowest locked input", "energy_fj": "Energy per cycle", "power_uw": "DC power", "power_nw": "DC power",
             "c_err_pct": "C_max error", "c_span_pf": "C span", "lsb_pf": "C LSB", "c_lsb_ff": "C LSB", "c_target_pf": "C target", "q_min_100m": "Min Q @ 100 MHz",
             "r_err_pct": "R_nom error", "r_target_kohm": "R target", "r_min_kohm": "R_min", "r_max_kohm": "R_max", "i_target_ua": "Target current",
             "lsb_ua": "I LSB", "v_in_v": "Input node voltage", "t_settle_ns": "Settling time", "vbias_v": "Bias node voltage", "startup_ns": "Start-up time",
             "iref_ss_untrimmed_ua": "SS I_REF untrimmed", "iref_ss_trimmed_ua": "SS I_REF trimmed", "iref_ff_untrimmed_ua": "FF I_REF untrimmed",
             "iref_ff_trimmed_ua": "FF I_REF trimmed", "trim_min_ua": "Trim range min", "trim_max_ua": "Trim range max", "target_ua": "Target current",
             "target_ppm_c": "TC target", "rout_kohm": "Output resistance", "vref_mv": "V_REF", "f_min_mhz": "f_min", "f_max_mhz": "f_max",
             "f_center_mhz": "Center frequency", "f_osc_mhz": "Oscillation frequency", "linearity_r2": "Tuning linearity R²", "inl_lsb": "INL", "dnl_lsb": "DNL",
             "area_est_um2": "Area estimate", "i_lsb_ua": "I LSB", "target_pf": "C target", "target_kohm": "R target", "target_ghz": "f target"})


def family_dse(ft, fd, fmeta, cards, details, mlabel):
    """columnar explorer data for one family + dims + presets + notes."""
    allpts = fd.get("points") or []
    failed = [p for p in allpts if p.get("ok") is not None and not p.get("ok")]
    pts = [p for p in allpts if p not in failed]
    delivs = fd.get("deliverables") or []
    fcards = {c["card_id"]: c for c in cards if c["family"] == ft}
    knob_keys = set()
    for p in pts:
        knob_keys |= set((p.get("knobs") or {}).keys())
    for c in fcards.values():
        knob_keys |= set((c.get("knobs") or {}).keys())
    # generator front membership per preset (all-supply fronts), for DSE points
    fronts = fd.get("fronts") or {}
    on_front = {}
    for pr in fd.get("presets") or []:
        mem = set()
        for t in fmeta["topologies"]:
            mem |= set(fronts.get(f"{pr['id']}|all|{t['tag']}") or [])
        on_front[pr["id"]] = mem
    rows = []
    for i, p in enumerate(allpts):
        if p in failed:
            continue
        r = {k: v for k, v in p.items() if k not in ("knobs",)}
        r.update(p.get("knobs") or {})
        r["_kind"], r["_stage"], r["_design"], r["_label"] = "dse", None, None, p.get("card_id") or f"dse_{ft}_{p.get('idx')}"
        r["_front"] = {pid: ("yes" if i in mem else "no") for pid, mem in on_front.items()}
        rows.append(r)
    for dv in delivs:
        c = fcards.get(dv["card_id"], {})
        # pre-PEX view shows pre + post (as the retired Schematic mode), full post-PEX view shows post only
        for st, kind, stg in (("pre", "pre", "pre"), ("post", "post", "full"), ("post", "post", "pre")):
            m = dv.get(st)
            if not m:
                continue
            r = dict(m)
            r.update(c.get("knobs") or {})
            r.update({"topo": dv["topo"], "vdd": dv["vdd"], "vdd_tag": dv["vdd_tag"], "target_tag": dv["target_tag"], "area_um2": dv.get("area_um2", m.get("area_um2")),
                      "_kind": kind, "_stage": stg, "_design": dv["card_id"], "_label": dv["card_id"], "_front": {}})
            rows.append(r)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys and k not in SKIP_KEYS and k not in ALIASES and k not in FAM_ALIASES.get(ft, ()) and not k.startswith("_"):
                keys.append(k)
    dropped, placeholder_area, dse_only_const = [], False, {}
    num_keys, cat_keys = [], []
    for k in keys:
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        dvals = [p.get(k, (p.get("knobs") or {}).get(k)) for p in pts]
        dvals = [v for v in dvals if v is not None]
        delv = [r.get(k) for r in rows if r["_kind"] != "dse" and r.get(k) is not None]
        if not vals:
            continue
        if all(isinstance(v, str) for v in vals):
            if len(set(vals)) > 1:
                cat_keys.append(k)
            continue
        if not all(isnum(v) for v in vals):
            continue
        if k == "area_um2" and dvals and len(set(dvals)) == 1:
            placeholder_area = dvals[0]
            num_keys.append(k)
            continue
        if dvals and len(set(dvals)) == 1 and len(pts) > 1:
            if len(set(delv)) > 1:          # constant only across DSE points: keep for delivered cards
                dse_only_const[k] = dvals[0]
                num_keys.append(k)
            else:
                dropped.append(f"`{k}` = {dvals[0]}")
            continue
        if len(set(vals)) <= 1:
            continue
        if k in ("pareto", "ok", "monotonic", "mod1_ok") and set(vals) <= {0, 1, 0.0, 1.0}:
            cat_keys.append(k)
            continue
        num_keys.append(k)
    opts = AXIS_OPTS.get(ft, [])
    order = [k for k, _, _ in opts if k in num_keys] + [k for k in num_keys if k not in [o[0] for o in opts] and k not in knob_keys] + \
            [k for k in num_keys if k in knob_keys and k not in [o[0] for o in opts]]
    optlab = {k: (lab, lg) for k, lab, lg in opts}
    dims, cols, dse_nulled = [], {}, []
    for k in order:
        unit, scale, si = unit_of(k)
        lab = strip_unit(optlab[k][0]) if k in optlab else pretty(k)
        if k in knob_keys:
            lab = f"Knob: {lab}"
        if k in ESTIMATE_KEYS:
            lab += " (analytic estimate)"
        if k in FORMULA_KEYS:
            lab += f" ({FORMULA_KEYS[k]})"
        null_dse = k in dse_only_const or k in DSE_NULL or (k == "area_um2" and placeholder_area is not False)
        if k == "area_um2":
            lab = ("Silicon area (layout; deliverables only)" if placeholder_area is not False
                   else "Silicon area (DSE: generator estimate · deliverables: layout)")
        elif k in dse_only_const:
            lab += f" (deliverables only; DSE value is a constant {dse_only_const[k]} placeholder)"
            dse_nulled.append(f"`{k}`")
        elif k in DSE_NULL and any(r.get(k) is not None for r in rows if r["_kind"] == "dse"):
            lab += " (deliverables only)"
            dse_nulled.append(f"`{k}` ({DSE_NULL[k]})")
        vals = []
        for r in rows:
            v = r.get(k)
            if null_dse and r["_kind"] == "dse":
                v = None
            vals.append(v * scale if isnum(v) else None)
        if not any(v is not None for v in vals):
            continue
        pos = [v for v in vals if v is not None and v > 0]
        logdef = bool(optlab[k][1]) if k in optlab else (len(pos) == len([v for v in vals if v is not None]) and pos and max(pos) / min(pos) > 50)
        dm = {"key": k, "label": lab, "log": bool(logdef)}
        if unit:
            dm["unit"] = unit
        if si:
            dm["si"] = True
        if BETTER.get(k):
            dm["better"] = BETTER[k]
        dims.append(dm)
        cols[k] = vals
    order = [d["key"] for d in dims]
    topo_lab = {t["tag"]: t["short_name"] for t in fmeta["topologies"]}
    tgt_lab = {t["tag"]: t["label"] for t in fmeta["targets"]}
    cols["topo"] = [r.get("topo") for r in rows]
    cols["supply"] = [r.get("vdd_tag") for r in rows]
    cols["vdd"] = [r.get("vdd") for r in rows]
    cols["kind"] = [r["_kind"] for r in rows]
    cols["stage"] = [r["_stage"] for r in rows]
    cols["design"] = [r["_design"] for r in rows]
    cols["delivered"] = [r["_kind"] != "dse" for r in rows]
    cols["label"] = [r["_label"] for r in rows]
    cat_dims = [{"key": "topo", "label": "Topology", "type": "cat", "labels": topo_lab, "order": [t["tag"] for t in fmeta["topologies"]],
                 "colors": {t["tag"]: PALETTE[i % len(PALETTE)] for i, t in enumerate(fmeta["topologies"])}},
                {"key": "supply", "label": "Supply", "type": "cat", "labels": {"1v8": "1.8 V", "3v3": "3.3 V"}, "order": ["1v8", "3v3"]},
                {"key": "kind", "label": "Point kind", "type": "cat", "order": ["dse", "post", "pre"],
                 "labels": {"dse": "DSE candidate (pre-PEX)", "pre": "Delivered card · pre-PEX", "post": "Delivered card · post-PEX"},
                 "colors": {"dse": "#94a3b8", "pre": "#0f172a", "post": "#dc2626"}}]
    if any(r.get("target_tag") for r in rows):
        cols["target"] = [r.get("target_tag") for r in rows]
        cat_dims.append({"key": "target", "label": "Target band", "type": "cat", "labels": tgt_lab, "order": [t["tag"] for t in fmeta["targets"]]})
    for pr in fd.get("presets") or []:
        key = f"front_{pr['id']}"
        cols[key] = [r["_front"].get(pr["id"]) for r in rows]
        cat_dims.append({"key": key, "label": f"On generator front: {pr['label']}", "type": "cat", "order": ["yes", "no"],
                         "colors": {"yes": "#e11d48", "no": "#94a3b8"}})
    for k in cat_keys:
        vals = [r.get(k) for r in rows]
        if k in ("pareto", "ok", "monotonic", "mod1_ok"):
            vals = [None if v is None else ("yes" if v else "no") for v in vals]
        else:
            vals = [None if v is None else str(v) for v in vals]
        cols[k] = vals
        lab = pretty(k)
        cat_dims.append({"key": k, "label": (f"Knob: {lab}" if k in knob_keys else lab) + (" (dse.json)" if k == "pareto" else ""), "type": "cat"})
    return {"rows": rows, "cols": cols, "dims": dims + cat_dims, "num_keys": order, "dropped": dropped, "placeholder_area": placeholder_area,
            "knob_keys": knob_keys, "scale": {k: unit_of(k)[1] for k in order}, "failed": failed, "dse_nulled": dse_nulled}


def shared_range(vals, log, pad=0.06):
    c = [v for v in vals if isnum(v) and (not log or v > 0)]
    if not c:
        return None
    lo, hi = min(c), max(c)
    if log:
        lo, hi = math.log10(lo), math.log10(hi)
    span = (hi - lo) or (1.0 if log else (abs(hi) * 0.2 or 1.0))
    return [lo - pad * span, hi + pad * span]


VT = (("1v8", 1.8, "solid"), ("3v3", 3.3, "dot"))


def wrap2(txt, n=46):
    if len(txt) <= n:
        return txt
    cut = txt.rfind(" ", 0, n)
    cut = cut if cut > 10 else n
    rest = txt[cut:].strip()
    return txt[:cut] + "<br>" + (rest if len(rest) <= n + 6 else rest[:n + 4] + "…")


def overlay_figs(ft, fd, fmeta, preset, placeholder_area, failed):
    """static ports of the retired overlay (all topologies) and facet grid for one preset.
    Every trace carries meta.vdd (global V_DD filter) and deliverables meta.stage (pre-PEX view: ◆ pre + ★ post;
    full post-PEX view: ★ only, as on the retired site). Per-supply generator fronts are drawn; the both-supply
    fronts of the retired 'All' view are legend-only traces that disappear when a supply is selected."""
    allpts = fd.get("points") or []
    fidx = {id(p) for p in failed}
    pts = [(i, p) for i, p in enumerate(allpts) if id(p) not in fidx]
    dv = fd.get("deliverables") or []
    xk, yk = preset["x"], preset["y"]
    xlog, ylog = bool(preset.get("x_log")), bool(preset.get("y_log"))
    area_ph = placeholder_area is not False and "area_um2" in (xk, yk)
    if area_ph:
        pts = []
    fronts = fd.get("fronts") or {}
    dpre = [d for d in dv if d.get("pre") and isnum(d["pre"].get(xk)) and isnum(d["pre"].get(yk))]
    dpost = [d for d in dv if d.get("post") and isnum(d["post"].get(xk)) and isnum(d["post"].get(yk))]
    allx = [p.get(xk) for _, p in pts] + [d.get(s, {}).get(xk) for d in dv for s in ("pre", "post") if d.get(s)]
    ally = [p.get(yk) for _, p in pts] + [d.get(s, {}).get(yk) for d in dv for s in ("pre", "post") if d.get(s)]
    xr, yr = shared_range(allx, xlog), shared_range(ally, ylog)

    def ax(text, log, rng, **kw):
        a = {"type": "log" if log else "linear", "title": {"text": text}}
        if rng:
            a["range"] = rng
        a.update(kw)
        return a

    def front_pts(key):
        fr = fronts.get(key) or []
        fp = [allpts[i] for i in fr if 0 <= i < len(allpts) and id(allpts[i]) not in fidx]
        return [p for p in fp if isnum(p.get(xk)) and isnum(p.get(yk))]

    def cloud(topo, col, xa=None, ya=None, legend=True, facet=False):
        out, shown = [], False
        for vtag, vv, dash in VT:
            tp = [p for _, p in pts if p.get("topo") == topo["tag"] and p.get("vdd_tag") == vtag and isnum(p.get(xk)) and isnum(p.get(yk))]
            if tp:
                out.append({"type": "scatter", "mode": "markers", "x": [p[xk] for p in tp], "y": [p[yk] for p in tp],
                            "name": "DSE" if facet else f"{topo['short_name']} (DSE)", "legendgroup": f"c_{topo['tag']}",
                            "marker": {"color": col, "size": 6, "opacity": 0.5 if facet else 0.45}, "showlegend": legend and not shown, "meta": {"vdd": vv},
                            "hovertemplate": (f"{topo['short_name']} ({vv}V)<br>x=%{{x:.3g}}, y=%{{y:.3g}}<extra></extra>" if facet
                                              else f"{topo['short_name']} ({vv}V)<br>{xk}: %{{x:.2f}}<br>{yk}: %{{y:.2f}}<extra></extra>")})
                shown = True
        if area_ph:
            return out
        for vtag, vv, dash in VT:
            fp = front_pts(f"{preset['id']}|{vtag}|{topo['tag']}")
            if len(fp) > 1:
                out.append({"type": "scatter", "mode": "lines+markers", "x": [p[xk] for p in fp], "y": [p[yk] for p in fp],
                            "name": "Pareto" if facet else f"{topo['short_name']} Pareto ({vv} V)", "legendgroup": f"f_{topo['tag']}_{vtag}",
                            "line": {"color": col, "width": 2.2 if facet else 2.4, "shape": "hv", "dash": dash}, "marker": {"color": col, "size": 7},
                            "hoverinfo": "skip", "showlegend": legend, "meta": {"vdd": vv}})
        fp = front_pts(f"{preset['id']}|all|{topo['tag']}")
        if len(fp) > 1:
            out.append({"type": "scatter", "mode": "lines+markers", "x": [p[xk] for p in fp], "y": [p[yk] for p in fp],
                        "name": "Pareto (both supplies)" if facet else f"{topo['short_name']} Pareto (both supplies)", "legendgroup": f"f_{topo['tag']}_all",
                        "line": {"color": col, "width": 2.0, "shape": "hv", "dash": "dashdot"}, "marker": {"color": col, "size": 5},
                        "hoverinfo": "skip", "showlegend": legend, "visible": "legendonly", "meta": {"vdd": "all"}})
        if xa:
            for tr in out:
                tr["xaxis"], tr["yaxis"] = xa, ya
        return out

    def deliv(sub, which, stage, facet=False, xa=None, ya=None, legend=True):
        out = []
        for vtag, vv, _ in VT:
            ss = [d for d in sub if d.get("vdd_tag") == vtag]
            if not ss:
                continue
            if which == "pre":
                t = {"name": "Pre-PEX" if facet else "Deliverable (Pre-PEX)", "marker": {"symbol": "diamond", "size": 9 if facet else 10, "color": "theme:ink", "line": {"color": "theme:paper", "width": 1.2 if facet else 1.5}},
                     "text": [f"{d['card_id']} ({d['target_label']})" if facet else f"<b>{d['card_id']}</b> (Pre-PEX)<br>{d['topo_short']} · {d['vdd']}V · {d['target_label']}" for d in ss]}
            else:
                t = {"name": "Post-PEX" if facet else "Deliverable (Post-PEX)", "marker": {"symbol": "star", "size": 10 if facet else 11, "color": "#dc2626", "line": {"color": "theme:paper", "width": 1.0 if facet else 1.2}},
                     "text": [f"{d['card_id']} Post-PEX ({d['target_label']})" if facet else f"<b>{d['card_id']}</b> (Post-PEX)<br>{d['topo_short']} · {d['vdd']}V · {d['target_label']}" for d in ss]}
            t.update({"type": "scatter", "mode": "markers", "x": [d[which][xk] for d in ss], "y": [d[which][yk] for d in ss], "customdata": [d["card_id"] for d in ss],
                      "hovertemplate": "%{text}<extra></extra>", "showlegend": legend and not out, "legendgroup": f"d_{which}_{stage}",
                      "meta": {"stage": stage, "vdd": vv}})
            if xa:
                t["xaxis"], t["yaxis"] = xa, ya
            out.append(t)
        return out

    def delivs(sub_pre, sub_post, **kw):
        return deliv(sub_pre, "pre", "pre", **kw) + deliv(sub_post, "post", "pre", **kw) + deliv(sub_post, "post", "full", **kw)

    topos = fmeta["topologies"]
    traces = []
    for i, tp in enumerate(topos):
        traces += cloud(tp, PALETTE[i % len(PALETTE)])
    traces += delivs(dpre, dpost)
    ov = {"data": traces, "layout": {"xaxis": ax(preset["x_label"], xlog, None), "yaxis": ax(preset["y_label"], ylog, None), "hovermode": "closest"}}
    ncol = 3
    nrow = max(1, math.ceil(len(topos) / ncol))
    gx, gy = 0.07, 0.42 / nrow
    w = (1 - gx * (ncol - 1)) / ncol
    h = (1 - gy * (nrow - 1)) / nrow
    ft_tr, lay, ann = [], {"showlegend": False, "hovermode": "closest", "margin": {"l": 60, "r": 20, "t": 52, "b": 50}}, []
    grid = "theme:line"
    for i, tp in enumerate(topos):
        r, cidx = divmod(i, ncol)
        n = "" if i == 0 else str(i + 1)
        x0 = cidx * (w + gx)
        y1 = 1 - r * (h + gy)
        lay[f"xaxis{n}"] = ax(preset["x_label"], xlog, xr, domain=[x0, x0 + w], anchor=f"y{n}", gridcolor=grid, title={"text": preset["x_label"], "font": {"size": 10}})
        lay[f"yaxis{n}"] = ax(preset["y_label"], ylog, yr, domain=[y1 - h, y1], anchor=f"x{n}", gridcolor=grid, title={"text": preset["y_label"], "font": {"size": 10}})
        ann.append({"text": f"<b>{tp['short_name']}</b> ({tp['tag']})<br><span style='font-size:9px'>{wrap2(tp['device_flavor'])}</span>",
                    "xref": "paper", "yref": "paper", "x": x0 + w / 2, "y": y1 + 0.01 * 3 / nrow, "xanchor": "center", "yanchor": "bottom", "showarrow": False, "font": {"size": 11}})
        xa, ya = f"x{n}", f"y{n}"
        ft_tr += cloud(tp, PALETTE[i % len(PALETTE)], xa, ya, legend=False, facet=True)
        ft_tr += delivs([d for d in dpre if d["topo"] == tp["tag"]], [d for d in dpost if d["topo"] == tp["tag"]], facet=True, xa=xa, ya=ya, legend=False)
    lay["annotations"] = ann
    return ov, {"data": ft_tr, "layout": lay}, nrow, area_ph


HERO_EXPLORE = ("**MULTI-OBJECTIVE COMPUTE-FARM DSE & PARETO FRONT ANALYSIS**\n\n# Design-space explorer & topology trade-offs\n\n"
                "Explore the compute-farm SPICE design-space exploration (DSE) across all five auxiliary families. Compare multi-topology Pareto fronts in the "
                "overlay chart, or inspect per-topology design clouds in the locked-axis small-multiples grid (`sharedRange` ensures every facet panel shares "
                "identical X and Y limits). Deliverable cards are highlighted as diamonds (Pre-PEX) and stars (Post-PEX); click any deliverable marker to open its card.")
FOM_KEYS = {"fom_dbc", "fom_t_dbc"}
FAM_ALIASES = {"vref_2t": {"power_uw"}, "clk_div": {"vpp_v"}}


def family_explore(out, f, fd, cards, dse, details):
    ft = f["tag"]
    X = family_dse(ft, fd, f, cards, details, None)
    write_json(out / ft / "data" / "dse.json", {"columns": X["cols"]})
    presets = fd.get("presets") or []
    allpts = fd.get("points") or []
    pts = [p for p in allpts if p not in X["failed"]]
    dlv = fd.get("deliverables") or []
    dimkeys = {d["key"] for d in X["dims"]}
    p0 = next((p for p in presets if p["x"] in dimkeys and p["y"] in dimkeys), {})
    base = {"x": p0.get("x"), "y": p0.get("y"), "logx": bool(p0.get("x_log")), "logy": bool(p0.get("y_log"))} if p0 else {}
    allk = {"kind": ["dse", "pre", "post"]}
    ex_presets = [{"label": p["label"], "x": p["x"], "y": p["y"], "logx": bool(p.get("x_log")), "logy": bool(p.get("y_log")), "facet": "", "color": "topo",
                   "show": allk, "desc": p.get("desc") or ""} for p in presets if p["x"] in dimkeys and p["y"] in dimkeys]
    ex_presets += [dict(base, label="Per-topology facet grid (shared axes)", facet="topo", color="topo", show=allk,
                        desc="One panel per topology with locked shared axes (as the retired small-multiples grid)."),
                   dict(base, label="Facet by supply", facet="supply", color="topo", show=allk, desc="1.8 V and 3.3 V side by side."),
                   dict(base, label="Delivered cards only", facet="", color="topo", show={"kind": ["pre", "post"]},
                        desc="Only the delivered cards (pre-PEX and post-PEX points follow the global stage)."),
                   dict(base, label="Colour by supply", facet="", color="supply", show=allk, desc="Colour = supply voltage (retired *Color By* option)."),
                   dict(base, label="Colour by generator front", facet="", color=f"front_{p0.get('id')}", show=allk,
                        desc=f"Red = DSE points on the generator's own Pareto front for *{p0.get('label')}* (both supplies, per topology).")]
    notes = []
    if X["failed"]:
        notes.append(f"{len(X['failed'])} failed DSE run(s) (`ok = 0`, placeholder metrics) are excluded: " + ", ".join(f"`{p.get('card_id')}`" for p in X["failed"]) + ".")
    if X["placeholder_area"] is not False:
        notes.append(f"DSE candidates carry a constant {X['placeholder_area']} µm² placeholder area in dse.json (filled in by the site generator, not a layout result); "
                     "they are left out on area axes, so area views show the delivered layouts only; the *On generator front* colour dims keep the generator's front membership.")
    if X["dse_nulled"]:
        notes.append("Shown for delivered cards only (DSE values are placeholders or derived from placeholders): " + ", ".join(X["dse_nulled"]) + ".")
    if X["dropped"]:
        notes.append("Constant in every point (fixed knobs or placeholders; omitted as dimensions): " + ", ".join(X["dropped"]) + ".")
    if any(k in ESTIMATE_KEYS for k in X["num_keys"]):
        notes.append("Phase-noise, jitter and FoM dimensions are *analytic estimates* from the generator's ISF / noise-floor model, not simulated.")
    if X["placeholder_area"] is False and "area_um2" in X["num_keys"]:
        notes.append("Area of DSE candidates is the generator's pre-layout estimate; delivered cards use the extracted layout area.")
    if any(k in FOM_KEYS for k in X["num_keys"]):
        notes.append("The Pareto toggle uses each dimension's physical direction (FoM in dBc/Hz: lower is better); the generator's own fronts in the static "
                     "charts below use its declared preset directions (it maximises FoM).")
    explorer = {
        "type": "explorer", "title": f"{f['icon']} {f['name']} — interactive design-space explorer", "src": f"hub/{ft}/data/dse.json",
        "dims": X["dims"], "x": base.get("x") or X["num_keys"][0], "y": base.get("y") or X["num_keys"][1],
        "color": "topo", "symbol": "kind", "filters": ["topo", "supply", "kind"] + (["target"] if "target" in X["cols"] else []),
        "highlight": "delivered", "highlight_label": "Delivered cards (click to open)", "design_key": "design", "label_key": "label",
        "hover": ["topo", "supply", "kind"] + (["target"] if "target" in X["cols"] else []), "presets": ex_presets, "preset_default": 0,
        "height": 560, "cat_axes": True,
        "intro": "Delivered cards are ringed. Pre-PEX view: DSE candidates + delivered ◆ pre-PEX and ✕ post-PEX values (as the retired Schematic mode); "
                 "Full post-PEX view: DSE candidates + post-PEX values only. Click a delivered point to open its card.",
        "caption": " ".join(notes),
    }
    ptabs = []
    for p in presets:
        ov, fc, nrow, area_ph = overlay_figs(ft, fd, f, p, X["placeholder_area"], X["failed"])
        bpath = f"{ft}/data/fig/{p['id']}"
        write_json(out / f"{bpath}_ov.json", ov, 5)
        write_json(out / f"{bpath}_fc.json", fc, 5)
        cap = ("Follows the global V<sub>DD</sub> filter (one supply = that supply's points and generator fronts; All = both, solid 1.8 V / dotted 3.3 V fronts; "
               "the retired both-supply fronts are available as legend-only entries). Pre-PEX view: diamonds (pre-PEX) and stars (post-PEX); "
               "Full post-PEX view: stars only, as on the retired site. Click any deliverable marker to open its card.")
        if area_ph:
            cap += " DSE clouds and fronts are omitted on this area axis (placeholder area in dse.json)."
        if X["failed"]:
            cap += " Failed DSE runs are not plotted."
        ptabs.append({"label": p["label"], "key": p["id"], "blocks": [
            {"type": "markdown", "text": p.get("desc") or ""},
            {"type": "chart", "title": f"{f['name']} — {strip_unit(p['y_label'])} vs. {strip_unit(p['x_label'])}",
             "src": f"hub/{bpath}_ov.json", "height": 580, "link_designs": True, "caption": cap},
            {"type": "chart", "title": "Per-topology small-multiples facet grid (locked shared axes)", "src": f"hub/{bpath}_fc.json",
             "height": 310 * nrow + 70, "link_designs": True,
             "caption": "Panels: " + "; ".join(f"**{t['short_name']}** (`{t['tag']}`): {t['device_flavor']} · {t['circuit_style']}" for t in f["topologies"]) + ". "
                        "Every panel locks to the exact same X and Y axis limits (`sharedRange`) for direct visual comparison across topologies. "
                        f"Legend: dots = DSE candidates, line = topology Pareto front (solid 1.8 V, dotted 3.3 V), ◆ = deliverable (Pre-PEX), ★ = deliverable (Post-PEX). "
                        f"All {len(f['topologies'])} facet panels share locked X & Y limits."}]})
    keys_tbl = [(k, lab) for k, lab, _ in AXIS_OPTS.get(ft, []) if k != "area_um2"]
    seen = {k for k, _ in keys_tbl}
    for p in presets:
        for k, lab in ((p["x"], p["x_label"]), (p["y"], p["y_label"])):
            if k not in seen and k != "area_um2":
                keys_tbl.append((k, lab))
                seen.add(k)
    cols = [{"key": "id", "label": "Card ID", "type": "design"}, {"key": "topo", "label": "Topology", "type": "text"}, {"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"},
            {"key": "tgt", "label": "Target", "type": "text"}]
    for k, lab in keys_tbl:
        g = (NICE.get(k) if k == "curr_err_pct" else strip_unit(lab)) + (" (estimate)" if k in ESTIMATE_KEYS else "")
        u = re.search(r"\(([^()]*)\)\s*$", lab)
        u = u.group(1) if u else unit_of(k)[0]
        cols += [{"key": f"{k}_pre", "label": "Pre-PEX", "group": g, "unit": u, "digits": 4}, {"key": f"{k}_post", "label": "Post-PEX", "group": g, "unit": u, "digits": 4}]
    cols.append({"key": "area", "label": "Area", "unit": "µm²", "digits": 5})
    trows = []
    for dv in dlv:
        r = {"id": dv["card_id"], "topo": dv["topo_short"], "vdd": dv["vdd"], "tgt": dv["target_label"], "area": dv.get("area_um2"), "_design": dv["card_id"]}
        for k, _ in keys_tbl:
            r[f"{k}_pre"] = (dv.get("pre") or {}).get(k)
            r[f"{k}_post"] = (dv.get("post") or {}).get(k)
        trows.append(r)

    def per_supply(items):
        return " · ".join(f"{vv} V: {sum(1 for x in items if x.get('vdd_tag') == vt)}" for vt, vv, _ in VT)
    page = {
        "intro": HERO_EXPLORE + f"\n\n*Hub note:* this tab shows the **{f['name']}** family (the retired page's family switch; its text says \"five\" "
                 "families, the data covers ten — the other families are sibling tabs under *Aux blocks*). The interactive explorer offers every numeric field "
                 "and knob of `dse.json` as X / Y / colour, the retired trade-off presets (with their descriptions), facet grids and Pareto fronts; the global "
                 "V<sub>DD</sub> filter replaces the old supply switch.",
        "blocks": [
            {"type": "stats", "items": [{"label": f"Simulated in {f['name']}", "value": f"{len(pts)} Candidates", "sub": per_supply(pts)},
                                        {"label": "DRC + LVS + Magic PEX Clean", "value": f"{len(dlv)} Deliverables", "sub": per_supply(dlv)},
                                        {"label": "Shared-Axis Facet Comparison", "value": f"{len(f['topologies'])} Topologies"},
                                        {"label": "Total Compute-Farm DSE Evals (all families)", "value": f"{dse.get('total_dse_points', 0):,}+"}]},
            explorer,
            {"type": "section", "title": "Multi-topology Pareto front overlay & per-topology facet grid (generator-computed fronts)",
             "intro": "Static port of the retired explorer charts: one coloured DSE cloud and Pareto front (from `dse.json` `fronts`) per topology, "
                      "deliverable cards as ◆ (pre-PEX) and ★ (post-PEX). Pick the trade-off preset; the global *Simulation stage* and V<sub>DD</sub> "
                      "options switch the views like the retired Schematic / Post-layout and supply switches.",
             "blocks": [{"type": "tabs", "id": "preset", "label": "Trade-off preset", "tabs": ptabs}]},
            {"type": "table", "title": "Deliverable cards & Pareto candidates in active family", "columns": cols, "rows": trows,
             "caption": "Click any deliverable row to open its full design card. The retired table showed the currently selected X/Y pair; here every axis "
                        "option and preset quantity is listed (pre & post). Values are as in dse.json (placeholders/clip limits are flagged on the design pages)."},
        ],
    }
    write_json(out / ft / "pages" / "explore.json", page)


# retired getComparisonColumns(): per-family column sets (values converted to base SI where the hub can prefix them)
def _k(m):
    v, u = m.get("kvco_mhz_per_unit"), m.get("kvco_unit") or ""
    return f"{num(v, 2)} {u}".strip() if isnum(v) else None


def _sc(k, f):
    return lambda m: (m.get(k) * f) if isnum(m.get(k)) else None


CMP = {
    "ro": [("f_osc", _sc("f_osc_mhz", 1e6), "Hz", 4), ("Power", _sc("power_uw", 1e-6), "W", 4), ("Energy / cycle", _sc("energy_fj", 1e-15), "J", 4),
           ("L(1 MHz) (est.)", _sc("phase_noise_dbc_1m", 1), "dBc/Hz", 4), ("FoM (est.)", _sc("fom_dbc", 1), "dBc/Hz", 4)],
    "tcap": [("C_max", _sc("c_max_pf", 1e-12), "F", 4), ("C_min", _sc("c_min_pf", 1e-12), "F", 4), ("Tuning ratio", _sc("tuning_ratio", 1), "×", 3),
             ("Q @ 100 MHz", _sc("q_factor_100m", 1), "", 3), ("ESR", _sc("esr_ohm", 1), "Ω", 3), ("INL", _sc("inl_lsb", 1), "LSB", 3)],
    "tres": [("R_nom", _sc("r_nom_kohm", 1e3), "Ω", 4), ("R_min", _sc("r_min_kohm", 1e3), "Ω", 4), ("R_max", _sc("r_max_kohm", 1e3), "Ω", 4),
             ("Tuning ratio", _sc("tuning_ratio", 1), "×", 3), ("Lin. error", _sc("linearity_err_pct", 1), "%", 3), ("BW", _sc("bw_3db_mhz", 1e6), "Hz", 3)],
    "cm_idac": [("I_FS", _sc("i_fs_ua", 1e-6), "A", 4), ("R_out", _sc("rout_mohm", 1e6), "Ω", 3), ("V_comp", _sc("v_comp_v", 1), "V", 3),
                ("Copy error", _sc("copy_err_pct", 1), "%", 3), ("INL", _sc("inl_lsb", 1), "LSB", 3), ("BW", _sc("bw_mhz", 1e6), "Hz", 3)],
    "dco_vco": [("f_center", _sc("f_center_mhz", 1e6), "Hz", 4), ("Tuning", _sc("tuning_range_pct", 1), "%", 3), ("Gain K", _k, None, 0),
                ("Power", _sc("power_uw", 1e-6), "W", 4), ("FoM_T (est.)", _sc("fom_t_dbc", 1), "dBc/Hz", 4)],
    "cml_ro": [("f_osc (RF)", _sc("f_osc_mhz", 1e6), "Hz", 4), ("V_pp,diff", _sc("vpp_diff_v", 1), "V", 3), ("Power", _sc("power_uw", 1e-6), "W", 4),
               ("L(1 MHz) (est.)", _sc("phase_noise_dbc_1m", 1), "dBc/Hz", 4), ("FoM (est.)", _sc("fom_dbc", 1), "dBc/Hz", 4)],
    "clk_div": [("f_max,in", _sc("f_max_ghz", 1e9), "Hz", 4), ("Div ratio", lambda m: f"÷{m.get('div_ratio_nom') or 2} ({num(m.get('div_ratio_meas'), 2)})", None, 0),
                ("Lock Δf", _sc("lock_range_ghz", 1e9), "Hz", 3), ("V_in,sens", _sc("min_vin_sens_v", 1), "V", 3), ("Power", _sc("power_uw", 1e-6), "W", 4)],
    "vref_2t": [("TC", _sc("tc_ppm_c", 1), "ppm/°C", 3), ("V_REF", _sc("vref_mv", 1e-3), "V", 4), ("Line sens.", _sc("line_sens_pct_v", 1), "%/V", 3),
                ("PSRR @ 100 Hz", _sc("psrr_100hz_db", 1), "dB", 3), ("Power", _sc("power_nw", 1e-9), "W", 3)],
    "bm_iref": [("I_REF", _sc("iref_ua", 1e-6), "A", 4), ("TC", _sc("tc_ppm_c", 1), "ppm/°C", 3), ("Line sens.", _sc("line_sens_pct_v", 1), "%/V", 3),
                ("R_out", _sc("rout_mohm", 1e6), "Ω", 3), ("Power", _sc("power_uw", 1e-6), "W", 3)],
}
CMP["cml_dco_vco"] = CMP["dco_vco"]
SI_UNITS = {"Hz", "W", "J", "F", "Ω", "A", "V"}
CLIP_CELLS = {("cm_idac", "R_out"): lambda v: v >= 5000e6, ("cm_idac", "BW"): lambda v: v <= 0, ("bm_iref", "TC"): lambda v: v in (8.0, 450.0),
              ("cm_idac", "INL"): lambda v: v == 0.05, ("vref_2t", "TC"): lambda v: v == 1.0, ("bm_iref", "Line sens."): lambda v: v in (0.03, 3.5),
              ("clk_div", "f_max,in"): lambda v: v >= 3.5e9}
NO_PVT_CRITERION = ("tcap", "tres", "cm_idac")


def signoff(c):
    ok = all(c.get(k) for k in ("drc_ok", "lvs_ok", "pex_ok"))
    return {"v": " · ".join(f"{n} {'✓' if c.get(k) else '✗'}" for n, k in (("DRC", "drc_ok"), ("LVS", "lvs_ok"), ("PEX", "pex_ok"))),
            "s": "good" if ok else "bad"}


def pvt_cell(c, st):
    if c["family"] in NO_PVT_CRITERION:
        return {"v": "n/a", "s": "muted", "title": "no PVT pass criterion in the generator"}
    p, t = c.get(f"pvt_pass_{st}"), c.get(f"pvt_total_{st}")
    return {"v": f"{p}/{t}", "s": "good" if p == t else "warn"}


def family_table(f, fcards, st, hub_st):
    ft = f["tag"]
    spec = CMP.get(ft, [])
    cols = [{"key": "id", "label": "Card ID", "type": "design"}, {"key": "topo", "label": "Topology", "type": "text"}, {"key": "vdd", "label": "VDD", "unit": "V"},
            {"key": "tgt", "label": "Mode" if ft == "vref_2t" else "Target", "type": "text"}]
    for i, (lab, fn, unit, dg) in enumerate(spec):
        if unit is None:
            cols.append({"key": f"c{i}", "label": lab, "type": "text"})
        else:
            c = {"key": f"c{i}", "label": lab, "digits": dg}
            if unit:
                c["unit"] = unit
            if unit in SI_UNITS:
                c["si"] = True
            cols.append(c)
    cols += [{"key": "area", "label": "Area", "unit": "µm²", "digits": 5, "better": "low"}, {"key": "pvt", "label": "PVT"},
             {"key": "sign", "label": "Signoff"}, {"key": "shift", "label": "Post-PEX shift of primary", "unit": "%", "digits": 3}]
    rows = []
    for c in fcards:
        m = c.get(f"metrics_{st}") or {}
        r = {"id": c["card_id"], "topo": c["topo_short"], "vdd": c["vdd"], "tgt": c["target_label"], "area": c.get("area_um2"), "_design": c["card_id"]}
        for i, (lab, fn, unit, dg) in enumerate(spec):
            v = fn(m)
            if isnum(v) and (ft, lab) in CLIP_CELLS and CLIP_CELLS[(ft, lab)](v):
                v = {"v": v, "s": "warn", "title": "generator clip limit, floor, sweep bound or placeholder — not published as a result"}
            r[f"c{i}"] = v
        r["pvt"] = pvt_cell(c, st)
        r["sign"] = signoff(c)
        D = (c.get("deltas") or {}).get(PRIMARY_DELTA.get(ft))
        r["shift"] = D["pct"] if D and isnum(D.get("pct")) else None
        rows.append(r)
    lab = "Post-layout (Magic PEX Extracted)" if st == "post" else "Pre-PEX Schematic"
    return {"type": "table", "alt": "cmp", "stage": hub_st, "title": "Sortable master comparison table", "columns": cols, "rows": rows,
            "csv_name": f"auxgen_{ft}_{st}_cards",
            "caption": f"Showing **{lab}** metrics for all cards of this family (the retired per-family column set). Click any column header to sort or any row to open the card. "
                       "*(est.)* columns are analytic estimates, not simulated. *Post-PEX shift* is the generator's pre→post delta of the primary metric "
                       "(the retired sort option \"|Post-PEX Shift %|\"). Amber cells sit on a generator clip limit, floor, sweep bound or placeholder. "
                       "Signoff no longer shows the retired \"Spec ✓\" badge: the site generator mapped the raw status (\"nominal\" / missing for 8 families) to \"pass\"."}


def pvt_sum(cs, st):
    if cs and cs[0]["family"] in NO_PVT_CRITERION:
        return {"v": "n/a", "s": "muted", "title": "no PVT pass criterion in the generator"}
    n = sum(1 for c in cs if c[f"pvt_pass_{st}"] == c[f"pvt_total_{st}"])
    return {"v": f"{n}/{len(cs)}", "s": "good" if n == len(cs) else "warn"}


DELTA_LABEL = {"f_osc_mhz": ("f_osc", "%"), "f_center_mhz": ("f_center", "%"), "power_uw": ("Power", "%"), "energy_fj": ("Energy/cycle", "%"),
               "phase_noise_dbc_1m": ("L(1 MHz) (est.)", "dB"), "jitter_ps": ("Jitter (est.)", "%"), "fom_dbc": ("FoM (est.)", "dB"),
               "psrr_100hz_db": ("PSRR @ 100 Hz", "dB")}


def delta_table(fcards):
    keys = []
    for c in fcards:
        for k in (c.get("deltas") or {}):
            if k not in keys:
                keys.append(k)
    cols = [{"key": "id", "label": "Card ID", "type": "design"}, {"key": "vdd", "label": "VDD", "unit": "V"}, {"key": "tgt", "label": "Target", "type": "text"}]
    for k in keys:
        lab, u = DELTA_LABEL.get(k, (pretty(k), "dB" if k.endswith("_db") or k.endswith("_dbc") else "%"))
        cols.append({"key": k, "label": lab, "unit": u, "digits": 3, "title": f"generator delta of {k} ({'absolute' if u == 'dB' else 'relative'})"})
    rows = []
    for c in fcards:
        D = c.get("deltas") or {}
        r = {"id": c["card_id"], "vdd": c["vdd"], "tgt": c["target_label"], "_design": c["card_id"]}
        for k in keys:
            x = D.get(k)
            u = cols[[cc["key"] for cc in cols].index(k)]["unit"]
            r[k] = (x.get("abs") if u == "dB" else x.get("pct")) if x else None
        rows.append(r)
    return {"type": "table", "title": "Pre→post-PEX shifts (generator deltas)", "columns": cols, "rows": rows, "csv_name": "pex_shifts",
            "caption": "The retired site showed these as Δ badges next to the values in Post-layout mode (matrix cells, cards, tables). "
                       "Relative shifts in %, dB quantities as absolute dB. Every design page also lists Δ vs pre-PEX per metric."}


def family_overview(docs, out, meta, f, fcards, fd):
    ft = f["tag"]
    clean = sum(1 for c in fcards if c.get("drc_ok") and c.get("lvs_ok") and c.get("pex_ok"))
    post = sum(1 for c in fcards if c.get("has_post_pex"))
    stats = [{"label": "Deliverable Design Cards", "value": f"{len(fcards)} / {meta.get('counts', {}).get('total_cards', len(fcards))}"},
             {"label": f"in {f['name']}", "value": f"{len(set(c['topo'] for c in fcards))} Topologies"},
             {"label": "KLayout DRC + LVS + Magic PEX Clean", "value": f"{clean} / {len(fcards)}"},
             {"label": "Compute-Farm DSE candidates", "value": f"{len(fd.get('points') or []):,}"},
             {"label": "Post-Layout PEX Characterized", "value": f"{post} / {len(fcards)}"},
             {"label": "gf180mcuD (180 nm 5LM, Option-B MIM)", "value": "1.8 V & 3.3 V"}]
    srows = []
    for s in meta["supplies"]:
        cs = [c for c in fcards if c["vdd_tag"] == s["tag"]]
        if cs:
            srows.append({"vdd": s["vdd"], "n": len(cs), "topo": len(set(c["topo"] for c in cs)),
                          "clean": sum(1 for c in cs if c.get("drc_ok") and c.get("lvs_ok") and c.get("pex_ok")), "post": sum(1 for c in cs if c.get("has_post_pex")),
                          "pvt_pre": pvt_sum(cs, "pre"), "pvt_post": pvt_sum(cs, "post")})
    cov = {"type": "table", "title": "Coverage by supply", "search": False, "csv": False, "rows": srows,
           "columns": [{"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"}, {"key": "n", "label": "Cards"}, {"key": "topo", "label": "Topologies"},
                       {"key": "clean", "label": "DRC + LVS + PEX clean"}, {"key": "post", "label": "Post-PEX characterized"},
                       {"key": "pvt_pre", "label": "All 15 PVT pass (pre)"}, {"key": "pvt_post", "label": "All 15 PVT pass (post)"}]}
    topo_rows = [[f"`{t['tag']}`", f"**{t['name']}**", t["short_name"], t["device_flavor"], t["circuit_style"], t.get("summary", "")] for t in f["topologies"]]
    topo_tbl = {"type": "table", "title": f"Topologies ({len(topo_rows)})", "search": False, "rows": topo_rows,
                "columns": [{"key": "t", "label": "Tag", "md": True}, {"key": "n", "label": "Name", "md": True, "wrap": True}, {"key": "s", "label": "Short name", "type": "text"},
                            {"key": "d", "label": "Device flavor", "type": "text", "wrap": True}, {"key": "c", "label": "Circuit style", "type": "text", "wrap": True},
                            {"key": "e", "label": "Engineering summary", "type": "text", "wrap": True}]}
    # per-family slices of the retired data files (exact data, hosted in this tab only)
    ddir = out / ft / "data"
    ddir.mkdir(parents=True, exist_ok=True)
    idx_meta = dict(meta)
    idx_meta["families"] = [f]
    lib = json.loads((docs / "data" / "library.json").read_text())
    lib["cards"] = [c for c in lib.get("cards") or [] if c.get("family") == ft]
    lib["total_cards"] = len(lib["cards"])
    for name, obj in (("library", lib), ("index", {"meta": idx_meta, "cards": fcards}),
                      ("dse", {"families": {ft: fd}, "total_dse_points": len(fd.get("points") or [])})):
        (ddir / f"{name}_{ft}.json").write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    dl = {"type": "downloads", "title": "Machine-readable data", "items": [
        {"label": f"library.json — this family's {len(lib['cards'])} cells (pins, areas, verification, pre/post metrics)", "src": f"hub/{ft}/data/library_{ft}.json"},
        {"label": "index.json — this family's card index (all card metrics, PVT/MC summaries, files)", "src": f"hub/{ft}/data/index_{ft}.json"},
        {"label": "dse.json — this family's DSE points, presets, fronts and deliverables", "src": f"hub/{ft}/data/dse_{ft}.json"},
        {"label": "gmid.json — gm/ID lookup-table curves (all families)", "src": "data/gmid.json"},
        {"label": "Full library.json (all families)", "file": "data/library.json"}, {"label": "Full index.json", "file": "data/index.json"},
        {"label": "Full dse.json", "file": "data/dse.json"}],
        "caption": "Slices contain exactly the retired files' records for this family (same structure). The full files are in the source repository."}
    sib = " · ".join(f"[{x['short_name']}](#/aux-{x['tag']})" for x in meta["families"] if x["tag"] != ft)
    page = {
        "intro": f"**{f['icon']} {f['name']}** (`{ft}`) — {len(fcards)} cards · {len(f['topologies'])} topologies · targets "
                 f"{', '.join(t['label'] for t in f['targets'])} · 1.8 V & 3.3 V\n\n{f.get('summary', '')}\n\n"
                 f"Primary metric on the retired site: **{f['primary_metric_label']} ({f['primary_metric_unit']})**. Coverage matrix, cards and the full metric table: "
                 f"**Designs**; trade-off clouds and Pareto fronts: **Design space**; generator description: **Methodology**; all families together: **All aux blocks**.\n\n"
                 f"Other aux families: {sib}",
        "blocks": [
            {"type": "stats", "items": stats},
            {"type": "note", "stage": "full", "tone": "info",
             "text": f"**Post-layout (Magic PEX) Mode Active:** Displaying extracted post-layout simulation metrics with Pre→Post shift badges across {post} verified cards. Cards without valid Post-PEX data are strictly filtered out."},
            {"type": "section", "blocks": [family_table(f, fcards, "pre", "pre"), family_table(f, fcards, "post", "full")]},
            {"type": "section", "collapsed": True, "title": "Pre→post-PEX shifts", "blocks": [delta_table(fcards)]},
            {"type": "section", "cols": 2, "blocks": [cov, dl]},
            {"type": "section", "blocks": [topo_tbl]},
        ],
    }
    write_json(out / ft / "pages" / "overview.json", page)


# ----------------------------------------------------------------------------- overview
def headline(c, st):
    """port of headlineCellMetric (text) + primaryMetricNumeric."""
    m = c.get(f"metrics_{st}") or {}
    D = c.get("deltas") or {}
    f = c["family"]

    def db(k):
        if st != "post" or not D.get(k):
            return ""
        p = D[k].get("pct")
        return f" (Δ {'+' if (p or 0) >= 0 else ''}{num(p, 1)}%)"
    if not m:
        return "No PEX", "", None
    if f in ("ro", "cml_ro"):
        main, pv = f"{fmt_mhz(m.get('f_osc_mhz'))}{db('f_osc_mhz')}", m.get("f_osc_mhz")
        sub = f"{num(m.get('power_uw'), 1)} µW · {num(m.get('energy_fj'), 1)} fJ" if f == "ro" else f"Vdiff {num(m.get('vpp_diff_v'), 2)}V · {num(m.get('power_uw'), 0)} µW"
    elif f == "tcap":
        main, sub, pv = f"{num(m.get('c_max_pf'), 2)} pF{db('c_max_pf')}", f"TR {num(m.get('tuning_ratio'), 1)}× · Q={num(m.get('q_factor_100m'), 0)}", m.get("c_max_pf")
    elif f == "tres":
        main, sub, pv = f"{num(m.get('r_nom_kohm'), 2)} kΩ{db('r_nom_kohm')}", f"TR {num(m.get('tuning_ratio'), 1)}× · {num(m.get('bw_3db_mhz'), 0)} MHz", m.get("r_nom_kohm")
    elif f == "cm_idac":
        main, sub, pv = f"{num(m.get('i_fs_ua'), 2)} µA{db('i_fs_ua')}", f"Rout {num(m.get('rout_mohm'), 1)} MΩ · Vc {num(m.get('v_comp_v'), 2)}V", m.get("i_fs_ua")
    elif f in ("dco_vco", "cml_dco_vco"):
        main, sub, pv = f"{fmt_mhz(m.get('f_center_mhz'))}{db('f_center_mhz')}", f"TR {num(m.get('tuning_range_pct'), 0)}% · {num(m.get('power_uw'), 0)} µW", m.get("f_center_mhz")
    elif f == "clk_div":
        main, sub, pv = f"{num(m.get('f_max_ghz'), 2)} GHz{db('f_max_ghz')}", f"÷{m.get('div_ratio_nom') or 2} · Δf {num(m.get('lock_range_ghz'), 2)} GHz", m.get("f_max_ghz")
    elif f == "vref_2t":
        p = m.get("power_nw")
        ps = f"{num(p * 1e-3, 2)} µW" if isnum(p) and p >= 1000 else f"{num(p, 2)} nW"
        main, sub, pv = f"{num(m.get('tc_ppm_c'), 1)} ppm/°C{db('tc_ppm_c')}", f"{num(m.get('vref_mv'), 0)} mV · {ps}", m.get("tc_ppm_c")
    elif f == "bm_iref":
        main, sub, pv = f"{num(m.get('iref_ua'), 2)} µA{db('iref_ua')}", f"TC {num(m.get('tc_ppm_c'), 0)} ppm/°C · {num(m.get('line_sens_pct_v'), 2)}%/V", m.get("iref_ua")
    else:
        main, sub, pv = DASH, "", None
    return main, sub, pv


PRIMARY_DELTA = {"ro": "f_osc_mhz", "cml_ro": "f_osc_mhz", "tcap": "c_max_pf", "tres": "r_nom_kohm", "cm_idac": "i_fs_ua", "dco_vco": "f_center_mhz",
                 "cml_dco_vco": "f_center_mhz", "clk_div": "f_max_ghz", "vref_2t": "tc_ppm_c", "bm_iref": "iref_ua"}


def html2md(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"</?strong>", "**", s)
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s)
    s = s.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    return s


def collection_page(docs, out, meta, cards):
    hero = (docs / "index.html").read_text()
    m = re.search(r'<section id="designs">.*?<div class="eyebrow">(.*?)</div>\s*<h1>(.*?)</h1>\s*<p class="lede">(.*?)</p>', hero, re.S)
    eyebrow, h1, lede = (html2md(m.group(i)) for i in (1, 2, 3)) if m else ("", "", "")
    subtitle = re.search(r'<span class="sub">(.*?)</span>', hero, re.S)
    subtitle = html2md(subtitle.group(1)) if subtitle else ""
    cnt = meta.get("counts", {})
    clean = sum(1 for c in cards if c.get("drc_ok") and c.get("lvs_ok") and c.get("pex_ok"))
    post = sum(1 for c in cards if c.get("has_post_pex"))
    stats = [{"label": "Deliverable Design Cards", "value": f"{len(cards)} / {cnt.get('total_cards', len(cards))}"},
             {"label": f"Across {cnt.get('families_present', 10)} Component Families", "value": f"{len(set(c['topo'] for c in cards))} Topologies"},
             {"label": "KLayout DRC + LVS + Magic PEX Clean", "value": f"{clean} / {len(cards)}"},
             {"label": "Compute-Farm DSE + PVT + MC Runs", "value": f"{cnt.get('total_dse_points', 0):,}+"},
             {"label": "Post-Layout PEX Characterized", "value": f"{post} / {len(cards)}"},
             {"label": "gf180mcuD (180 nm 5LM, Option-B MIM)", "value": "1.8 V & 3.3 V"}]
    # per family x supply summary (follows the global VDD filter)
    srows = []
    for fi, f in enumerate(meta["families"]):
        for s in meta["supplies"]:
            cs = [c for c in cards if c["family"] == f["tag"] and c["vdd_tag"] == s["tag"]]
            if not cs:
                continue
            srows.append({"fam": f"{f['icon']} [{f['name']}](#/aux-{f['tag']}) · [design space](#/aux-{f['tag']}?page=explore)", "tag": f"`{f['tag']}`", "vdd": s["vdd"], "n": len(cs),
                          "topo": len(set(c["topo"] for c in cs)), "clean": {"v": sum(1 for c in cs if c.get("drc_ok") and c.get("lvs_ok") and c.get("pex_ok")),
                                                                             "s": "good" if all(c.get("drc_ok") and c.get("lvs_ok") and c.get("pex_ok") for c in cs) else "warn"},
                          "post": sum(1 for c in cs if c.get("has_post_pex")),
                          "pvt_pre": pvt_sum(cs, "pre"), "pvt_post": pvt_sum(cs, "post"),
                          "pm": f"{f['primary_metric_label']} ({f['primary_metric_unit']})"})
    summary_tbl = {"type": "table", "title": "Coverage by family and supply",
                   "columns": [{"key": "fam", "label": "Family", "md": True}, {"key": "tag", "label": "Tag", "md": True}, {"key": "vdd", "label": "V<sub>DD</sub>", "unit": "V"},
                               {"key": "n", "label": "Cards"}, {"key": "topo", "label": "Topologies"}, {"key": "clean", "label": "DRC + LVS + PEX clean"},
                               {"key": "post", "label": "Post-PEX characterized"}, {"key": "pvt_pre", "label": "All 15 PVT pass (pre)"},
                               {"key": "pvt_post", "label": "All 15 PVT pass (post)"}, {"key": "pm", "label": "Primary metric"}],
                   "rows": srows, "search": False,
                   "caption": "Follows the global V<sub>DD</sub> filter (replaces the retired hero tiles, which recomputed per family / supply). Family links open the family's tab."}
    # all-family master comparison table (retired 'All' variant), stage alternatives
    tables = []
    for st, hub_st in (("pre", "pre"), ("post", "full")):
        rows = []
        for c in cards:
            main, sub, pv = headline(c, st)
            D = (c.get("deltas") or {}).get(PRIMARY_DELTA.get(c["family"]))
            sign = all(c.get(k) for k in ("drc_ok", "lvs_ok", "pex_ok"))
            rows.append({"id": f"[{c['card_id']}](#/aux-{c['family']}/{c['card_id']})", "fam": f"[{c['family_short']}](#/aux-{c['family']})", "topo": c["topo_short"], "vdd": c["vdd"], "tgt": c["target_label"],
                         "main": main, "pv": pv, "sub": sub, "mc": None if c["family"] == "clk_div" else c.get(f"mc_cv_{st}"), "area": c.get("area_um2"),
                         "pvt": pvt_cell(c, st), "sign": signoff(c),
                         "shift": abs(D["pct"]) if D and isnum(D.get("pct")) else None, "_href": f"#/aux-{c['family']}/{c['card_id']}"})
        tables.append({"type": "table", "alt": "master", "stage": hub_st, "title": "Sortable master comparison table (all families)",
                       "columns": [{"key": "id", "label": "Card ID", "md": True}, {"key": "fam", "label": "Family", "md": True},
                                   {"key": "topo", "label": "Topology", "type": "text"}, {"key": "vdd", "label": "VDD", "unit": "V"}, {"key": "tgt", "label": "Target", "type": "text"},
                                   {"key": "main", "label": "Headline Metric", "type": "text"}, {"key": "pv", "label": "Primary value (family unit)", "digits": 5},
                                   {"key": "sub", "label": "Secondary Metric", "type": "text"}, {"key": "mc", "label": "MC σ/μ", "unit": "%", "digits": 3, "better": "low"},
                                   {"key": "area", "label": "Area", "unit": "µm²", "digits": 5, "better": "low"}, {"key": "pvt", "label": "PVT"},
                                   {"key": "sign", "label": "Signoff"}, {"key": "shift", "label": "|Post-PEX shift| of primary", "unit": "%", "digits": 3, "better": "low"}],
                       "rows": rows, "page_size": 500, "csv_name": f"auxgen_all_{st}_cards",
                       "caption": f"Showing **{'Post-layout (Magic PEX Extracted)' if st == 'post' else 'Pre-PEX Schematic'}** metrics. Click any column header to sort or any row to open the card. "
                                  "*Primary value* is the family's headline number in its own unit (MHz, pF, kΩ, µA, GHz, ppm/°C). "
                                  "*|Post-PEX shift|* is the generator's pre→post delta of the primary metric (the retired sort option \"|Post-PEX Shift %|\")."})
    downloads = {"type": "downloads", "title": "Machine-readable data (retired site footer / header)", "items": [
        {"label": "library.json — downstream cell library (pins, areas, verification, pre/post metrics)", "file": "data/library.json"},
        {"label": "index.json — card index (all card metrics, PVT/MC summaries, files)", "file": "data/index.json"},
        {"label": "dse.json — design-space exploration points, presets, fronts, deliverables", "file": "data/dse.json"},
        {"label": "gmid.json — gm/ID lookup-table curves", "src": "data/gmid.json"},
        {"label": "Source repository", "url": meta.get("repo", "https://github.com/aicdb/aux-gen-gemini4")}],
        "caption": "Each family tab's **Overview** hosts that family's slice of library.json / index.json / dse.json (same structure); the complete files are "
                   "linked here from the source repository (so they are not copied into all ten tabs). `data/bundle.js` of the retired site was only "
                   "`index.json` + `dse.json` + `gmid.json` inlined for `file://` viewing and is not republished. "
                   f"Data generated {meta.get('generated_utc', '')}."}
    md_meta = [["PDK", meta.get("pdk", "")], ["Supplies", ", ".join(s["label"] for s in meta.get("supplies", []))],
               ["PVT corners", ", ".join(meta.get("pvt_corners", [])) + " × " + ", ".join(f"{t} °C" for t in meta.get("pvt_temps_c", []))],
               ["Generated", meta.get("generated_utc", "")], ["Retired per-repo site", meta.get("pages_url", "")]] + \
              [[k.replace("_", " "), v] for k, v in cnt.items()]
    page = {
        "intro": f"**{eyebrow}**\n\n# {h1}\n\n{lede}\n\n<small>{subtitle}</small>",
        "blocks": [
            {"type": "stats", "items": stats},
            {"type": "note", "stage": "full", "tone": "info",
             "text": f"**Post-layout (Magic PEX) Mode Active:** Displaying extracted post-layout simulation metrics with Pre→Post shift badges across {post} verified cards. Cards without valid Post-PEX data are strictly filtered out."},
            {"type": "section", "title": "Interactive coverage matrices by component family",
             "intro": "Rows are circuit topologies; columns are **Supply (1.8 V / 3.3 V) × Target Band**. Each cell shows the headline metric, 15-corner PVT status, "
                      "and DRC/LVS/PEX signoff badge. Click any cell to open its full card.\n\n*On the hub:* every family is its own tab under **Aux blocks** "
                      "(links below); its **Designs** view holds the matrix — rows are topology (with device flavor), columns are supply × target band, each cell "
                      "shows the retired headline and both secondary values; the *Cell metric* selector offers more presets. Topology / target pills, search, "
                      "verification and sort controls are the hub's filters and Cards/Table views.",
             "blocks": [summary_tbl]},
            {"type": "section", "title": "All families", "blocks": tables},
            {"type": "section", "title": "Library metadata & downloads", "cols": 2,
             "blocks": [{"type": "kv", "items": [[a, str(b)] for a, b in md_meta], "cols": 1}, downloads]},
        ],
    }
    write_json(out / "pages" / "collection.json", page)


# ----------------------------------------------------------------------------- methodology
def methodology_page(docs, out, meta, gmid):
    html = (docs / "index.html").read_text()
    sec = html[html.index('<section id="methodology"'):]
    m = re.search(r'<div class="eyebrow">(.*?)</div>\s*<h1>(.*?)</h1>\s*<p class="lede">(.*?)</p>', sec, re.S)
    eyebrow, h1, lede = (html2md(m.group(i)) for i in (1, 2, 3))

    def panel_md(h3_text):
        i = sec.rindex("<h3>", 0, sec.index(h3_text))
        body = sec[i:]
        depth, k = 0, 0
        for mm in re.finditer(r"<(/?)(ol|ul)\b", body):
            if mm.group(1):
                depth -= 1
                if depth == 0:
                    k = body.index(">", mm.end()) + 1
                    break
            else:
                depth += 1
        body = body[:k]
        head = html2md(re.search(r"<h3>(.*?)</h3>", body, re.S).group(1))
        lines = []
        n = 0
        # structured parse: top-level <li> of the <ol>, nested <ul><li> as sub-bullets
        ol = body[body.index("<ol"):]
        items, cur, depth = [], "", 0
        for tok in re.split(r"(<li>|</li>|<ul>|</ul>|<ol[^>]*>|</ol>)", ol):
            if tok.startswith("<ol"):
                depth += 1
                continue
            if tok == "</ol>":
                depth -= 1
                continue
            if tok == "<ul>":
                depth += 1
                cur += "\n<<UL>>"
                continue
            if tok == "</ul>":
                depth -= 1
                continue
            if tok == "<li>":
                if depth == 1:
                    if cur.strip():
                        items.append(cur)
                    cur = ""
                else:
                    cur += "\n<<LI>>"
                continue
            if tok == "</li>":
                continue
            cur += tok
        if cur.strip():
            items.append(cur)
        for it in items:
            n += 1
            parts = it.split("\n<<UL>>")
            first = html2md(parts[0])
            lines.append(f"{n}. {first}")
            for p in parts[1:]:
                for sub in p.split("\n<<LI>>"):
                    if sub.strip():
                        lines.append(f"  - {html2md(sub)}")
        return head, "\n".join(lines)

    h_1, md_1 = panel_md("1. Unit-Finger")
    h_2, md_2 = panel_md("2. Experimental gLayout")
    lens = gmid.get("lengths_um", [])
    dev_tabs = []
    for dev, dlab in (("nfet_03v3", "nfet_03v3 (NMOS)"), ("pfet_03v3", "pfet_03v3 (PMOS)")):
        vt_tabs = []
        for vt, vlab, vv in (("1v8", "V<sub>DS</sub> = 0.9 V (1.8V Domain)", 1.8), ("3v3", "V<sub>DS</sub> = 1.65 V (3.3V Domain)", 3.3)):
            curves = ((gmid.get("devices") or {}).get(dev) or {}).get(vt) or {}
            if not curves:
                continue

            def mk(yk):
                return [{"type": "scatter", "mode": "lines", "x": c["gm_id"], "y": c[yk], "name": f"L = {L} µm", "line": {"color": PALETTE[i % len(PALETTE)], "width": 2.2}}
                        for i, (L, c) in enumerate(curves.items())]
            xa = {"title": {"text": "Transconductance Efficiency g_m / I_D (V⁻¹)"}, "autorange": "reversed"}
            charts = [
                {"type": "chart", "title": "Current Density I<sub>D</sub>/W (µA/µm) vs g<sub>m</sub>/I<sub>D</sub>",
                 "caption": "Used to compute total width W = I<sub>branch</sub> / J<sub>D</sub>(g<sub>m</sub>/I<sub>D</sub>, L)",
                 "data": mk("id_w_ua_um"), "layout": {"xaxis": xa, "yaxis": {"type": "log", "title": {"text": "Drain Current Density I_D / W (µA/µm)"}}}, "height": 360},
                {"type": "chart", "title": "Intrinsic Gain g<sub>m</sub>/g<sub>ds</sub> (V/V) vs g<sub>m</sub>/I<sub>D</sub>",
                 "caption": "Guides channel length L selection for cascode mirrors & differential stages",
                 "data": mk("gm_gds"), "layout": {"xaxis": xa, "yaxis": {"type": "log", "title": {"text": "Intrinsic Gain g_m / g_ds (V/V)"}}}, "height": 360},
                {"type": "chart", "title": "Transit Frequency f<sub>T</sub> (GHz) vs g<sub>m</sub>/I<sub>D</sub>",
                 "caption": "Defines speed-efficiency frontier for 2 GHz ring oscillators & RF switches (f_T = 0 entries in gmid.json are dropped by the log axis)",
                 "data": mk("ft_ghz"), "layout": {"xaxis": xa, "yaxis": {"type": "log", "title": {"text": "Transit Frequency f_T (GHz)"}}}, "height": 360},
            ]
            vt_tabs.append({"label": vlab, "vdd": vv, "blocks": [{"type": "section", "cols": 3, "blocks": charts}]})
        dev_tabs.append({"label": dlab, "blocks": [{"type": "tabs", "label": "Domain", "tabs": vt_tabs}]})
    rows = []
    for f in meta["families"]:
        for t in f["topologies"]:
            rows.append([f"[{f['short_name']}](#/aux-{f['tag']})", f"`{t['tag']}`", f"**{t['name']}**", t["device_flavor"], t["circuit_style"], t.get("summary", "")])
    cat_tbl = {"type": "table", "title": "Complete catalog of component families & topologies",
               "caption": "All 5 families and 30+ topologies synthesized across 1.8 V and 3.3 V supplies. *(Retired-site wording; the catalogue below lists all "
                          f"{len(meta['families'])} families and {len(rows)} topologies.)*",
               "columns": [{"key": "f", "label": "Family", "md": True}, {"key": "t", "label": "Topology Tag", "md": True}, {"key": "n", "label": "Name", "md": True, "wrap": True},
                           {"key": "d", "label": "Device Flavor", "type": "text", "wrap": True}, {"key": "s", "label": "Circuit Style", "type": "text", "wrap": True},
                           {"key": "e", "label": "Engineering Summary", "type": "text", "wrap": True}],
               "rows": rows, "page_size": 200, "max_height": 900}
    page = {
        "intro": f"**{eyebrow}**\n\n# {h1}\n\n{lede}",
        "blocks": [
            {"type": "section", "cols": 2, "blocks": [{"type": "markdown", "title": h_1, "text": md_1}, {"type": "markdown", "title": h_2, "text": md_2}]},
            {"type": "section", "title": "Interactive GF180MCU-D g<sub>m</sub>/I<sub>D</sub> lookup-table design charts",
             "intro": f"Extracted from `build/data/gmid_lut.npz` across channel lengths L ∈ {{{', '.join(f'{x:.2f}' for x in lens)}}} µm (W<sub>f</sub> = 2.0 µm). "
                      "g<sub>m</sub>/g<sub>ds</sub> = 999 points are the generator's display cap.",
             "blocks": [{"type": "tabs", "label": "Device", "tabs": dev_tabs}]},
            {"type": "section", "blocks": [cat_tbl]},
        ],
    }
    write_json(out / "pages" / "method.json", page)


def build_shared(docs, out, meta, cards, gmid):
    """pages shared by every aux-<family> tab (one hosted file each)."""
    collection_page(docs, out, meta, cards)
    methodology_page(docs, out, meta, gmid)
    return [{"id": "method", "title": "Methodology", "src": "hub/pages/method.json"},
            {"id": "all", "title": "All aux blocks", "src": "hub/pages/collection.json"}]


def build_family(docs, out, meta, f, fcards, fd, dse, details):
    family_overview(docs, out, meta, f, fcards, fd)
    family_explore(out, f, fd, fcards, dse, details)
    return [{"id": "overview", "title": "Overview", "src": f"hub/{f['tag']}/pages/overview.json"},
            {"id": "explore", "title": "Design space", "src": f"hub/{f['tag']}/pages/explore.json"}]
