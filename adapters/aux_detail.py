"""Per-design detail documents for the aux adapter (ports app.js renderDetail* of the old site).

Every section of the old card (Overview / Schematic / Simulation / Layout tabs) becomes a
hub block. Where the old site switched content with its Schematic / Post-layout toggle the
blocks are stage alternatives (`alt` + `stage` pre/full)."""
import ast

from aux_fmt import DASH, fmt_mhz, isnum, num

PRE_C, POST_C = "#2563eb", "#ea580c"
EST = " *(analytic estimate)*"
EST_NOTE = ("Phase noise, jitter and the FoM values are **analytic estimates** (Hajimiri–Lee ISF / divider "
            "noise-floor model evaluated by the generator from the simulated f, P<sub>DC</sub> and swing), not "
            "transient-noise simulations; the hub therefore does not list them as simulated results.")


# ----------------------------------------------------------------------------- placeholders / bounds
PH = "site-normaliser placeholder: the generator's value was 0 or missing"
FLAGS = {  # (family, source field) -> (predicate, short tag, tooltip)
    ("clk_div", "ratio_err_pct"): (lambda v: v == 0.15, "placeholder", PH),
    ("clk_div", "f_max_ghz"): (lambda v: v >= 3.5, "sweep top", "3.5 GHz is the top of the input sweep: lower bound"),
    ("cm_idac", "inl_lsb"): (lambda v: v == 0.05, "placeholder", PH), ("cm_idac", "dnl_lsb"): (lambda v: v == 0.03, "placeholder", PH),
    ("tres", "inl_lsb"): (lambda v: v == 0.05, "placeholder", PH), ("tres", "dnl_lsb"): (lambda v: v == 0.03, "placeholder", PH),
    ("cm_idac", "rout_mohm"): (lambda v: v >= 5000.0, "clip limit", "R_out at the 5000 MΩ clip limit of the |Z_out| extraction"),
    ("cm_idac", "bw_mhz"): (lambda v: v <= 0.0, "not meaningful", "BW referred to an R_out at the clip limit (rounded to 0)"),
    ("vref_2t", "tc_ppm_c"): (lambda v: v == 1.0, "floor", "site normaliser floors TC at 1.0 ppm/°C; simulated value ≤ 1"),
    ("vref_2t", "min_vdd_v"): (lambda v: v == 0.65, "floor", "generator floors V_DD,min at 0.65 V"),
    ("bm_iref", "tc_ppm_c"): (lambda v: v in (8.0, 450.0), "clip limit", "generator clips TC to 8–450 ppm/°C"),
    ("bm_iref", "line_sens_pct_v"): (lambda v: v in (0.03, 3.5), "clip limit", "generator clips line sensitivity to 0.03–3.5 %/V"),
    ("bm_iref", "startup_ns"): (lambda v: v == 1450.0, "estimate", "did not settle; generator RC estimate clipped at 1450 ns"),
    ("ro", "t_start_ns"): (lambda v: v <= 0.0, "not measured", "start-up reported as 0"),
    ("cml_ro", "t_start_ns"): (lambda v: v <= 0.0, "not measured", "start-up reported as 0"),
}


def flagged(fam, m, fields):
    out = []
    for f in fields or ():
        fl = FLAGS.get((fam, f))
        v = m.get(f)
        if fl and isnum(v) and fl[0](v):
            out.append(fl)
    return out


# ----------------------------------------------------------------------------- spec rows
def spec_rows(d, stage):
    """Port of getDetailSpecRows(). Returns dicts {p, t, pre, post, delta, worst, chk, est}.
    chk(m) -> True/False/None evaluates the explicit numeric target (only where the old Target
    column states an inequality / window)."""
    mp, mx = d.get("metrics_pre") or {}, d.get("metrics_post") or {}
    D = d.get("deltas") or {}
    fam, vdd = d["family"], d["vdd"]
    pv_pre, pv_post = d.get("pvt_pre") or {}, d.get("pvt_post") or {}
    if stage == "full":
        worst = pv_post.get("worst_val", pv_pre.get("worst_val"))
        corner = pv_post.get("worst_corner", pv_pre.get("worst_corner"))
    else:
        worst, corner = pv_pre.get("worst_val"), pv_pre.get("worst_corner")
    corner = corner or DASH

    def dp(k, n=1):
        return f"{num(D[k].get('pct'), n)}%" if D.get(k) else DASH

    def da(k):
        return f"{num(D[k].get('abs'), 1)} dB" if D.get(k) else DASH

    def has(k):
        return mx.get(k) is not None

    def g(m, k):
        v = m.get(k)
        return v if isnum(v) else None

    def ge(k, lim):
        return lambda m: None if g(m, k) is None or lim is None else g(m, k) >= lim

    def le(k, lim):
        return lambda m: None if g(m, k) is None or lim is None else g(m, k) <= lim

    def lt(k, lim):
        return lambda m: None if g(m, k) is None else g(m, k) < lim

    def ltabs2(k1, k2, lim):
        return lambda m: None if g(m, k1) is None or g(m, k2) is None else max(abs(g(m, k1)), abs(g(m, k2))) < lim

    def R(p, t, pre, post, delta=DASH, w=DASH, chk=None, est=False, fl=()):
        return {"p": p, "t": t, "pre": pre, "post": post, "delta": delta, "worst": w, "chk": chk, "est": est, "fl": fl}

    if fam == "ro":
        return [
            R("Oscillation Frequency f_osc", f"{num(mp.get('target_mhz'), 2)} MHz", fmt_mhz(mp.get("f_osc_mhz")),
              fmt_mhz(mx.get("f_osc_mhz")) if has("f_osc_mhz") else DASH, dp("f_osc_mhz"), f"{fmt_mhz(worst)} ({corner})"),
            R("DC Power P_DC", "Minimize", f"{num(mp.get('power_uw'), 2)} µW",
              f"{num(mx.get('power_uw'), 2)} µW" if has("power_uw") else DASH, dp("power_uw")),
            R("Energy per Cycle", "Minimize", f"{num(mp.get('energy_fj'), 2)} fJ/cyc",
              f"{num(mx.get('energy_fj'), 2)} fJ/cyc" if has("energy_fj") else DASH, dp("energy_fj")),
            R("Duty Cycle", "45% – 55%", f"{num(mp.get('duty_pct'), 1)}%", f"{num(mx.get('duty_pct'), 1)}%" if has("duty_pct") else DASH,
              chk=lambda m: None if g(m, "duty_pct") is None else 45 <= g(m, "duty_pct") <= 55),
            R("Output Swing", "≥ 0.75 V_DD", f"{num(mp.get('swing_v'), 3)} V", f"{num(mx.get('swing_v'), 3)} V" if has("swing_v") else DASH,
              chk=ge("swing_v", 0.75 * vdd)),
            R("Phase Noise L(1 MHz)", "Minimize", f"{num(mp.get('phase_noise_dbc_1m'), 1)} dBc/Hz",
              f"{num(mx.get('phase_noise_dbc_1m'), 1)} dBc/Hz" if has("phase_noise_dbc_1m") else DASH, da("phase_noise_dbc_1m"), est=True),
            R("Cycle-to-Cycle Jitter J_cc", "Minimize", f"{num(mp.get('jitter_ps'), 2)} ps",
              f"{num(mx.get('jitter_ps'), 2)} ps" if has("jitter_ps") else DASH, est=True),
            R("Figure of Merit FoM", "Maximize", f"{num(mp.get('fom_dbc'), 1)} dBc/Hz",
              f"{num(mx.get('fom_dbc'), 1)} dBc/Hz" if has("fom_dbc") else DASH, da("fom_dbc"), est=True),
        ]
    if fam == "tcap":
        return [
            R("Max Capacitance C_max", f"{num(mp.get('target_pf'), 2)} pF", f"{num(mp.get('c_max_pf'), 3)} pF",
              f"{num(mx.get('c_max_pf'), 3)} pF" if has("c_max_pf") else DASH, dp("c_max_pf"), f"{num(worst, 3)} pF ({corner})"),
            R("Min Capacitance C_min", "Minimize", f"{num(mp.get('c_min_pf'), 3)} pF",
              f"{num(mx.get('c_min_pf'), 3)} pF" if has("c_min_pf") else DASH, dp("c_min_pf")),
            R("Tuning Ratio C_max/C_min", "≥ 2.5×", f"{num(mp.get('tuning_ratio'), 2)}×",
              f"{num(mx.get('tuning_ratio'), 2)}×" if has("tuning_ratio") else DASH, dp("tuning_ratio"), chk=ge("tuning_ratio", 2.5)),
            R("Quality Factor Q @ 100 MHz", "Maximize", num(mp.get("q_factor_100m"), 1),
              num(mx.get("q_factor_100m"), 1) if has("q_factor_100m") else DASH, dp("q_factor_100m")),
            R("Series Resistance ESR", "Minimize", f"{num(mp.get('esr_ohm'), 1)} Ω", f"{num(mx.get('esr_ohm'), 1)} Ω" if has("esr_ohm") else DASH),
            R("Step Linearity DNL / INL", "< 0.5 LSB", f"{num(mp.get('dnl_lsb'), 3)} / {num(mp.get('inl_lsb'), 3)} LSB",
              f"{num(mx.get('dnl_lsb'), 3)} / {num(mx.get('inl_lsb'), 3)} LSB" if has("inl_lsb") else DASH, chk=ltabs2("dnl_lsb", "inl_lsb", 0.5)),
            R("Figure of Merit (Q × TR)", "Maximize", num(mp.get("fom"), 1), num(mx.get("fom"), 1) if has("fom") else DASH),
        ]
    if fam == "tres":
        return [
            R("Nominal Resistance R_nom", f"{num(mp.get('target_kohm'), 1)} kΩ", f"{num(mp.get('r_nom_kohm'), 2)} kΩ",
              f"{num(mx.get('r_nom_kohm'), 2)} kΩ" if has("r_nom_kohm") else DASH, dp("r_nom_kohm"), f"{num(worst, 2)} kΩ ({corner})"),
            R("Min Resistance R_min (Code 7)", "Low End", f"{num(mp.get('r_min_kohm'), 2)} kΩ", f"{num(mx.get('r_min_kohm'), 2)} kΩ" if has("r_min_kohm") else DASH),
            R("Max Resistance R_max (Code 1)", "High End", f"{num(mp.get('r_max_kohm'), 2)} kΩ", f"{num(mx.get('r_max_kohm'), 2)} kΩ" if has("r_max_kohm") else DASH),
            R("Tuning Ratio R_max/R_min", "≥ 4.0×", f"{num(mp.get('tuning_ratio'), 2)}×",
              f"{num(mx.get('tuning_ratio'), 2)}×" if has("tuning_ratio") else DASH, dp("tuning_ratio"), chk=ge("tuning_ratio", 4.0)),
            R("I-V Linearity Error (THD)", "< 5%", f"{num(mp.get('linearity_err_pct'), 2)}% ({num(mp.get('thd_db'), 1)} dB)",
              f"{num(mx.get('linearity_err_pct'), 2)}% ({num(mx.get('thd_db'), 1)} dB)" if has("linearity_err_pct") else DASH,
              chk=lt("linearity_err_pct", 5)),
            R("Parasitic -3 dB Bandwidth", "Maximize", f"{num(mp.get('bw_3db_mhz'), 1)} MHz",
              f"{num(mx.get('bw_3db_mhz'), 1)} MHz" if has("bw_3db_mhz") else DASH, dp("bw_3db_mhz")),
            R("Conductance DNL / INL", "< 0.25 LSB", f"{num(mp.get('dnl_lsb'), 3)} / {num(mp.get('inl_lsb'), 3)} LSB",
              f"{num(mx.get('dnl_lsb'), 3)} / {num(mx.get('inl_lsb'), 3)} LSB" if has("inl_lsb") else DASH, chk=ltabs2("dnl_lsb", "inl_lsb", 0.25), fl=("dnl_lsb", "inl_lsb")),
        ]
    if fam == "cm_idac":
        return [
            R("Full-Scale Current I_FS", f"{num(mp.get('target_ua'), 1)} µA", f"{num(mp.get('i_fs_ua'), 3)} µA",
              f"{num(mx.get('i_fs_ua'), 3)} µA" if has("i_fs_ua") else DASH, dp("i_fs_ua"), f"{num(worst, 3)} µA ({corner})"),
            R("Current Copy Error", "< 2.5%", f"{num(mp.get('copy_err_pct'), 2)}%", f"{num(mx.get('copy_err_pct'), 2)}%" if has("copy_err_pct") else DASH,
              chk=lambda m: None if g(m, "copy_err_pct") is None else abs(g(m, "copy_err_pct")) < 2.5),
            R("Min Compliance Voltage V_comp", "Minimize", f"{num(mp.get('v_comp_v'), 3)} V", f"{num(mx.get('v_comp_v'), 3)} V" if has("v_comp_v") else DASH),
            R("DC Output Impedance R_out", "Maximize", f"{num(mp.get('rout_mohm'), 2)} MΩ",
              f"{num(mx.get('rout_mohm'), 2)} MΩ" if has("rout_mohm") else DASH, dp("rout_mohm"), fl=("rout_mohm",)),
            R("Output Bandwidth f_-3dB", "Maximize", f"{num(mp.get('bw_mhz'), 2)} MHz",
              f"{num(mx.get('bw_mhz'), 2)} MHz" if has("bw_mhz") else DASH, fl=("bw_mhz",)),
            R("DAC Linearity DNL / INL", "< 0.5 LSB", f"{num(mp.get('dnl_lsb'), 3)} / {num(mp.get('inl_lsb'), 3)} LSB",
              f"{num(mx.get('dnl_lsb'), 3)} / {num(mx.get('inl_lsb'), 3)} LSB" if has("inl_lsb") else DASH, chk=ltabs2("dnl_lsb", "inl_lsb", 0.5), fl=("dnl_lsb", "inl_lsb")),
            R("Step Settling Time t_settle", "Minimize", f"{num(mp.get('t_settle_ns'), 2)} ns", f"{num(mx.get('t_settle_ns'), 2)} ns" if has("t_settle_ns") else DASH),
        ]
    if fam == "cml_ro":
        return [
            R("RF Oscillation Frequency f_osc", fmt_mhz(mp.get("target_mhz")), fmt_mhz(mp.get("f_osc_mhz")),
              fmt_mhz(mx.get("f_osc_mhz")) if has("f_osc_mhz") else DASH, dp("f_osc_mhz"), f"{fmt_mhz(worst)} ({corner})"),
            R("Differential Swing V_pp,diff", "≥ 0.60 V", f"{num(mp.get('vpp_diff_v'), 3)} V",
              f"{num(mx.get('vpp_diff_v'), 3)} V" if has("vpp_diff_v") else DASH, dp("vpp_diff_v"), chk=ge("vpp_diff_v", 0.60)),
            R("Single-Ended Swing V_pp,se", "≥ 0.30 V", f"{num(mp.get('swing_v'), 3)} V", f"{num(mx.get('swing_v'), 3)} V" if has("swing_v") else DASH,
              chk=ge("swing_v", 0.30)),
            R("DC Power P_DC", "Minimize", f"{num(mp.get('power_uw'), 1)} µW", f"{num(mx.get('power_uw'), 1)} µW" if has("power_uw") else DASH, dp("power_uw")),
            R("Energy per Cycle", "Minimize", f"{num(mp.get('energy_fj'), 1)} fJ/cyc", f"{num(mx.get('energy_fj'), 1)} fJ/cyc" if has("energy_fj") else DASH),
            R("Phase Noise L(1 MHz)", "Minimize", f"{num(mp.get('phase_noise_dbc_1m'), 1)} dBc/Hz",
              f"{num(mx.get('phase_noise_dbc_1m'), 1)} dBc/Hz" if has("phase_noise_dbc_1m") else DASH, da("phase_noise_dbc_1m"), est=True),
            R("Bias/Vctrl Tuning Range", "Wide Span", f"{num(mp.get('tuning_range_pct'), 1)}% ({num(mp.get('kvco_mhz_per_v'), 0)} MHz/V)",
              f"{num(mx.get('tuning_range_pct'), 1)}%" if has("tuning_range_pct") else DASH),
            R("Figure of Merit FoM", "Maximize", f"{num(mp.get('fom_dbc'), 1)} dBc/Hz",
              f"{num(mx.get('fom_dbc'), 1)} dBc/Hz" if has("fom_dbc") else DASH, da("fom_dbc"), est=True),
        ]
    if fam == "clk_div":
        dn = mp.get("div_ratio_nom") or 2
        try:
            fout_t = num((mp.get("f_in_ghz") or 1) / (float(mp.get("div_ratio_meas") or 0) or 2), 3)
        except (TypeError, ValueError):
            fout_t = DASH
        return [
            R("Max Operating Input Freq f_max,in", f"≥ {num(mp.get('target_ghz'), 2)} GHz", f"{num(mp.get('f_max_ghz'), 3)} GHz",
              f"{num(mx.get('f_max_ghz'), 3)} GHz" if has("f_max_ghz") else DASH, dp("f_max_ghz"), f"{num(worst, 3)} GHz ({corner})",
              chk=ge("f_max_ghz", g(mp, "target_ghz")), fl=("f_max_ghz",)),
            R("Input Locking Range [f_min, f_max]", "Wideband",
              f"{num(mp.get('f_min_ghz'), 2)} – {num(mp.get('f_max_ghz'), 2)} GHz (Δ{num(mp.get('lock_range_ghz'), 2)} GHz)",
              f"{num(mx.get('f_min_ghz'), 2)} – {num(mx.get('f_max_ghz'), 2)} GHz" if has("f_max_ghz") else DASH, dp("lock_range_ghz")),
            R("Measured Division Ratio f_in/f_out", f"÷{dn}", f"÷{num(mp.get('div_ratio_meas'), 4)} (err {num(mp.get('ratio_err_pct'), 2)}%)",
              f"÷{num(mx.get('div_ratio_meas'), 4)}" if has("div_ratio_meas") else DASH, fl=("ratio_err_pct",)),
            R("Output Clock Freq f_out @ Target", f"{fout_t} GHz", f"{num(mp.get('f_out_ghz'), 3)} GHz",
              f"{num(mx.get('f_out_ghz'), 3)} GHz" if has("f_out_ghz") else DASH),
            R("Min Input Clock Sensitivity V_in,min", "Minimize", f"{num(mp.get('min_vin_sens_v'), 3)} V_pp",
              f"{num(mx.get('min_vin_sens_v'), 3)} V_pp" if has("min_vin_sens_v") else DASH, dp("min_vin_sens_v")),
            R("Output Swing V_pp,out", "≥ 0.40 V", f"{num(mp.get('vpp_out_v'), 3)} V", f"{num(mx.get('vpp_out_v'), 3)} V" if has("vpp_out_v") else DASH,
              dp("vpp_out_v"), chk=ge("vpp_out_v", 0.40)),
            R("DC Power P_DC", "Minimize", f"{num(mp.get('power_uw'), 1)} µW", f"{num(mx.get('power_uw'), 1)} µW" if has("power_uw") else DASH, dp("power_uw")),
            R("Additive Phase Noise Floor", "≤ -135 dBc/Hz", f"{num(mp.get('phase_noise_floor_dbc'), 1)} dBc/Hz",
              f"{num(mx.get('phase_noise_floor_dbc'), 1)} dBc/Hz" if has("phase_noise_floor_dbc") else DASH,
              chk=le("phase_noise_floor_dbc", -135), est=True),
        ]
    if fam == "vref_2t":
        return [
            R("Temp Coefficient TC (−40..125°C)", f"≤ {num(mp.get('target_ppm_c'), 0)} ppm/°C", f"{num(mp.get('tc_ppm_c'), 1)} ppm/°C",
              f"{num(mx.get('tc_ppm_c'), 1)} ppm/°C" if has("tc_ppm_c") else DASH, dp("tc_ppm_c"), f"{num(worst, 1)} ppm/°C ({corner})",
              chk=le("tc_ppm_c", g(mp, "target_ppm_c")), fl=("tc_ppm_c",)),
            R("Nominal Reference Voltage V_REF (27°C)", "Stable V_REF", f"{num(mp.get('vref_mv'), 2)} mV",
              f"{num(mx.get('vref_mv'), 2)} mV" if has("vref_mv") else DASH, dp("vref_mv", 2)),
            R("DC Line Sensitivity (ΔV_REF / ΔV_DD)", "≤ 0.5 %/V", f"{num(mp.get('line_sens_pct_v'), 3)} %/V",
              f"{num(mx.get('line_sens_pct_v'), 3)} %/V" if has("line_sens_pct_v") else DASH, dp("line_sens_pct_v"),
              chk=lambda m: None if g(m, "line_sens_pct_v") is None else abs(g(m, "line_sens_pct_v")) <= 0.5),
            R("Power Supply Rejection PSRR @ 100 Hz", "≥ 35 dB", f"{num(mp.get('psrr_100hz_db'), 1)} dB",
              f"{num(mx.get('psrr_100hz_db'), 1)} dB" if has("psrr_100hz_db") else DASH, da("psrr_100hz_db"), chk=ge("psrr_100hz_db", 35)),
            R("Quiescent Power P_DC (27°C)", "Sub-nW / nW", f"{num(mp.get('power_nw'), 2)} nW ({num(mp.get('idd_na'), 2)} nA)",
              f"{num(mx.get('power_nw'), 2)} nW ({num(mx.get('idd_na'), 2)} nA)" if has("power_nw") else DASH, dp("power_nw")),
            R("Minimum Supply Voltage V_DD,min", f"≤ {num(vdd * 0.75, 2)} V", f"{num(mp.get('min_vdd_v'), 2)} V",
              f"{num(mx.get('min_vdd_v'), 2)} V" if has("min_vdd_v") else DASH, chk=le("min_vdd_v", vdd * 0.75), fl=("min_vdd_v",)),
            R("Small-Signal Output Resistance R_out", "Compact", f"{num(mp.get('rout_kohm'), 1)} kΩ",
              f"{num(mx.get('rout_kohm'), 1)} kΩ" if has("rout_kohm") else DASH),
        ]
    if fam == "bm_iref":
        def code(m, k):
            return m.get(k) if m.get(k) is not None else DASH
        return [
            R("Nominal I_REF (TT @ Center Code 4)", f"{num(mp.get('target_ua'), 2)} µA",
              f"{num(mp.get('iref_ua'), 3)} µA (err {num(mp.get('acc_err_pct'), 2)}%)",
              f"{num(mx.get('iref_ua'), 3)} µA" if has("iref_ua") else DASH, dp("iref_ua"), f"{num(worst, 3)} µA ({corner})"),
            R("3-Bit Trim Range (code = 0..7)", "Span FF..SS",
              f"{num(mp.get('trim_min_ua'), 3)} – {num(mp.get('trim_max_ua'), 3)} µA ({num(mp.get('trim_range_pct'), 1)}%)",
              f"{num(mx.get('trim_min_ua'), 3)} – {num(mx.get('trim_max_ua'), 3)} µA" if has("trim_min_ua") else DASH, DASH, "Center = Code 4 (100₂)"),
            R("SS Corner Trimmed to TT", f"{num(mp.get('iref_ua'), 3)} µA",
              f"Code {code(mp, 'trim_code_ss')} → {num(mp.get('iref_ss_trimmed_ua'), 3)} µA (err {num(mp.get('ss_trim_err_pct'), 2)}%)",
              f"Code {code(mx, 'trim_code_ss')} → {num(mx.get('iref_ss_trimmed_ua'), 3)} µA" if has("iref_ss_trimmed_ua") else DASH, DASH,
              f"Untrimmed SS: {num(mp.get('iref_ss_untrimmed_ua'), 3)} µA"),
            R("FF Corner Trimmed to TT", f"{num(mp.get('iref_ua'), 3)} µA",
              f"Code {code(mp, 'trim_code_ff')} → {num(mp.get('iref_ff_trimmed_ua'), 3)} µA (err {num(mp.get('ff_trim_err_pct'), 2)}%)",
              f"Code {code(mx, 'trim_code_ff')} → {num(mx.get('iref_ff_trimmed_ua'), 3)} µA" if has("iref_ff_trimmed_ua") else DASH, DASH,
              f"Untrimmed FF: {num(mp.get('iref_ff_untrimmed_ua'), 3)} µA"),
            R("Temp Coefficient TC (−40..125°C)", "Minimize / Controlled", f"{num(mp.get('tc_ppm_c'), 0)} ppm/°C",
              f"{num(mx.get('tc_ppm_c'), 0)} ppm/°C" if has("tc_ppm_c") else DASH, dp("tc_ppm_c"), fl=("tc_ppm_c",)),
            R("DC Line Sensitivity (ΔI_REF / ΔV_DD)", "≤ 2.5 %/V", f"{num(mp.get('line_sens_pct_v'), 2)} %/V",
              f"{num(mx.get('line_sens_pct_v'), 2)} %/V" if has("line_sens_pct_v") else DASH, dp("line_sens_pct_v"),
              chk=lambda m: None if g(m, "line_sens_pct_v") is None else abs(g(m, "line_sens_pct_v")) <= 2.5, fl=("line_sens_pct_v",)),
            R("DC Output Resistance R_out", "Maximize", f"{num(mp.get('rout_mohm'), 2)} MΩ", f"{num(mx.get('rout_mohm'), 2)} MΩ" if has("rout_mohm") else DASH,
              dp("rout_mohm"), f"V_comp = {num(mp.get('v_comp_v'), 2)} V"),
            R("Supply Rejection PSRR @ 100 Hz", "≥ 30 dB", f"{num(mp.get('psrr_100hz_db'), 1)} dB",
              f"{num(mx.get('psrr_100hz_db'), 1)} dB" if has("psrr_100hz_db") else DASH, da("psrr_100hz_db"), f"V_DD,min = {num(mp.get('min_vdd_v'), 2)} V",
              chk=ge("psrr_100hz_db", 30)),
            R("Total Quiescent Power P_DC (27°C)", "Minimize", f"{num(mp.get('power_uw'), 2)} µW (I_DD = {num(mp.get('idd_ua'), 2)} µA)",
              f"{num(mx.get('power_uw'), 2)} µW" if has("power_uw") else DASH, dp("power_uw")),
        ]
    # dco_vco / cml_dco_vco
    ku = mp.get("kvco_unit") or ""
    return [
        R("Center Frequency f_center", f"{num(mp.get('target_mhz'), 2)} MHz", fmt_mhz(mp.get("f_center_mhz")),
          fmt_mhz(mx.get("f_center_mhz")) if has("f_center_mhz") else DASH, dp("f_center_mhz"), f"{fmt_mhz(worst)} ({corner})"),
        R("Tuning Span [f_min, f_max]", "Wide Span", f"{fmt_mhz(mp.get('f_min_mhz'))} – {fmt_mhz(mp.get('f_max_mhz'))}",
          f"{fmt_mhz(mx.get('f_min_mhz'))} – {fmt_mhz(mx.get('f_max_mhz'))}" if has("f_min_mhz") else DASH),
        R("Fractional Tuning Range", "≥ 20%", f"{num(mp.get('tuning_range_pct'), 1)}%",
          f"{num(mx.get('tuning_range_pct'), 1)}%" if has("tuning_range_pct") else DASH, dp("tuning_range_pct"), chk=ge("tuning_range_pct", 20)),
        R("Average Gain K_DCO / K_VCO", "Linear", f"{num(mp.get('kvco_mhz_per_unit'), 3)} {ku}",
          f"{num(mx.get('kvco_mhz_per_unit'), 3)} {mx.get('kvco_unit') or ''}" if has("kvco_mhz_per_unit") else DASH),
        R("DC Power P_DC", "Minimize", f"{num(mp.get('power_uw'), 2)} µW", f"{num(mx.get('power_uw'), 2)} µW" if has("power_uw") else DASH, dp("power_uw")),
        R("Phase Noise L(1 MHz)", "Minimize", f"{num(mp.get('phase_noise_dbc_1m'), 1)} dBc/Hz",
          f"{num(mx.get('phase_noise_dbc_1m'), 1)} dBc/Hz" if has("phase_noise_dbc_1m") else DASH, est=True),
        R("Tuning FoM_T", "Maximize", f"{num(mp.get('fom_t_dbc'), 1)} dBc/Hz", f"{num(mx.get('fom_t_dbc'), 1)} dBc/Hz" if has("fom_t_dbc") else DASH, est=True),
    ]


def clipmark(v, lim, side):
    """flag values sitting on a generator clip limit (they are bounds, not measurements)."""
    if not isnum(v):
        return ""
    if side == "hi" and v >= lim:
        return " (clip limit ≥)"
    if side == "lo" and v <= lim:
        return " (no −3 dB point found in sweep)"
    if side == "both" and v in lim:
        return " (clip limit)"
    return ""


# ----------------------------------------------------------------------------- charts
def _t(x, y, name, color, width=2.2, dash=None, mode="lines", y2=False, ttype=None, opacity=None):
    if not x or not y:
        return None
    t = {"x": x, "y": y, "name": name, "mode": mode, "line": {"color": color, "width": width}}
    if dash:
        t["line"]["dash"] = dash
    if y2:
        t["yaxis"] = "y2"
    return t


def _lay(xt, yt, y2t=None, xlog=False, ylog=False, y2log=False, extra=None):
    L = {"xaxis": {"title": {"text": xt}}, "yaxis": {"title": {"text": yt}}}
    if xlog:
        L["xaxis"]["type"] = "log"
    if ylog:
        L["yaxis"]["type"] = "log"
    if y2t:
        L["yaxis2"] = {"title": {"text": y2t}, "overlaying": "y", "side": "right", "showgrid": False, "zeroline": False}
        if y2log:
            L["yaxis2"]["type"] = "log"
        L["margin"] = {"r": 60}
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(L.get(k), dict):
            L[k].update(v)
        else:
            L[k] = v
    return L


def _chart(title, caption, traces, layout, height=360):
    traces = [t for t in traces if t]
    if not traces:
        return None
    return {"type": "chart", "title": title, "caption": caption, "data": traces, "layout": layout, "height": height}


def sim_charts(d):
    """the four Simulation-tab charts (port of renderDetailSimulation)."""
    fam = d["family"]
    w = d.get("waveforms_pre") or {}
    wp = d.get("waveforms_post") or None
    P = wp or {}
    mp, mx = d.get("metrics_pre") or {}, d.get("metrics_post") or {}
    out = []
    if fam == "ro":
        out.append(_chart("1. Steady-State Transient Output Waveform V<sub>out</sub>(t)", "Pre-PEX schematic vs Post-PEX extracted oscillation waveform", [
            _t(w.get("time_ns"), w.get("v_out"), "Pre-PEX V_out", PRE_C, 2.2),
            _t(w.get("time_ns"), w.get("v_n1"), "Pre-PEX Ring Node", "#93c5fd", 1.5, "dot"),
            _t(P.get("time_ns"), P.get("v_out"), "Post-PEX V_out", POST_C, 2.2, "dash")], _lay("Time (ns)", "Voltage (V)")))
        out.append(_chart("2. Supply Sensitivity f<sub>osc</sub>(V<sub>DD</sub>) & DC Power", "Frequency pushing and power across V_DD ± 10%", [
            _t(w.get("vdd_sweep_v"), w.get("vdd_sweep_f_mhz"), "Pre-PEX f_osc (MHz)", PRE_C, 2, mode="lines+markers"),
            _t(w.get("vdd_sweep_v"), w.get("vdd_sweep_p_uw"), "Pre-PEX Power (µW)", "#059669", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("vdd_sweep_v"), P.get("vdd_sweep_f_mhz"), "Post-PEX f_osc (MHz)", POST_C, 2, "dash", "lines+markers")],
            _lay("Supply Voltage V_DD (V)", "f_osc (MHz)", "Power (µW)")))
        out.append(_chart("3. Phase Noise Spectrum L(Δf) vs Offset Frequency",
                          "1/f³ flicker and 1/f² thermal phase noise profile (1 kHz – 10 MHz). *Analytic Hajimiri–Lee ISF model evaluated from the simulated f_osc, P_DC and swing — not a noise simulation.*", [
            _t(w.get("pn_offset_hz"), w.get("pn_dbc_hz"), "Pre-PEX L(Δf)", PRE_C, 2.2, mode="lines+markers"),
            _t(P.get("pn_offset_hz"), P.get("pn_dbc_hz"), "Post-PEX L(Δf)", POST_C, 2, "dash", "lines+markers")],
            _lay("Offset Frequency Δf (Hz)", "Phase Noise L(Δf) (dBc/Hz)", xlog=True)))
    elif fam == "tcap":
        out.append(_chart("1. Capacitance Tuning Curve C(code) (Pre-PEX vs Post-PEX)", "Effective capacitance at 100 MHz across digital control codes", [
            _t(w.get("codes"), w.get("c_code_pf"), "Pre-PEX C(code)", PRE_C, 2.4, mode="lines+markers"),
            _t(P.get("codes"), P.get("c_code_pf"), "Post-PEX C(code)", POST_C, 2.4, "dash", "lines+markers")],
            _lay("Digital Control Code", "Capacitance C_eff (pF)")))
        out.append(_chart("2. Quality Factor Q(code) & Series Resistance ESR", "Q factor at 100 MHz and equivalent series resistance across codes", [
            _t(w.get("codes"), w.get("q_code"), "Pre-PEX Q", "#059669", 2.2, mode="lines+markers"),
            _t(w.get("codes"), w.get("esr_code_ohm"), "Pre-PEX ESR (Ω)", "#7c3aed", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("codes"), P.get("q_code"), "Post-PEX Q", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Digital Control Code", "Quality Factor Q @ 100 MHz", "ESR (Ω)")))
        out.append(_chart("3. Impedance |Z(f)| & Capacitance C(f) vs Frequency", "Broadband AC extraction from 1 MHz to 2 GHz", [
            _t(w.get("freq_mhz"), w.get("c_vs_freq_pf"), "Pre-PEX C(f) (pF)", PRE_C, 2.2),
            _t(w.get("freq_mhz"), w.get("z_vs_freq_ohm"), "Pre-PEX |Z(f)| (Ω)", "#d97706", 1.8, "dot", y2=True),
            _t(P.get("freq_mhz"), P.get("c_vs_freq_pf"), "Post-PEX C(f) (pF)", POST_C, 2.2, "dash")],
            _lay("Frequency (MHz)", "Capacitance C(f) (pF)", "|Z(f)| (Ω)", xlog=True, y2log=True)))
    elif fam == "tres":
        out.append(_chart("1. Resistance R(code) & Conductance G(code) Tuning Curve", "Binary programmable resistance and linear conductance steps", [
            _t(w.get("codes"), w.get("r_code_kohm"), "Pre-PEX R(code) (kΩ)", PRE_C, 2.3, mode="lines+markers"),
            _t(w.get("codes"), w.get("g_code_ms"), "Pre-PEX G(code) (mS)", "#059669", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("codes"), P.get("r_code_kohm"), "Post-PEX R(code) (kΩ)", POST_C, 2.3, "dash", "lines+markers")],
            _lay("Digital Control Code", "Resistance R (kΩ)", "Conductance G (mS)")))
        out.append(_chart("2. DC I-V Linearity I(V) & Differential Resistance R<sub>diff</sub>(V)", "Large-signal port sweep across 0.1 V_DD to 0.9 V_DD", [
            _t(w.get("v_sweep_v"), w.get("i_sweep_ua"), "Pre-PEX I(V) (µA)", PRE_C, 2.2),
            _t(w.get("v_sweep_v"), w.get("r_diff_kohm"), "Pre-PEX R_diff(V) (kΩ)", "#7c3aed", 2, "dot", y2=True),
            _t(P.get("v_sweep_v"), P.get("r_diff_kohm"), "Post-PEX R_diff(V) (kΩ)", POST_C, 2, "dash", y2=True)],
            _lay("Port Voltage V (V)", "Current I (µA)", "R_diff (kΩ)")))
        out.append(_chart("3. AC Impedance |Z(f)| & Parasitic −3 dB Bandwidth", "High-frequency roll-off due to switch/substrate parasitic capacitance", [
            _t(w.get("freq_mhz"), w.get("z_mag_kohm"), "Pre-PEX |Z(f)| (kΩ)", PRE_C, 2.3),
            _t(P.get("freq_mhz"), P.get("z_mag_kohm"), "Post-PEX |Z(f)| (kΩ)", POST_C, 2.3, "dash")],
            _lay("Frequency (MHz)", "Impedance |Z(f)| (kΩ)", xlog=True)))
    elif fam == "cm_idac":
        idac = d["topo"].startswith("idac_")
        if idac:
            out.append(_chart("1. Digital-to-Analog Transfer Curve I<sub>out</sub>(code) & Output Compliance", "Full-scale current DAC transfer curve (Pre-PEX vs Post-PEX)", [
                _t(w.get("codes"), w.get("dac_i_ua"), "Pre-PEX I_out(code)", PRE_C, 2.3, mode="lines+markers"),
                _t(P.get("codes"), P.get("dac_i_ua"), "Post-PEX I_out(code)", POST_C, 2.3, "dash", "lines+markers")],
                _lay("DAC Digital Code", "Output Current I_out (µA)")))
            out.append(_chart("2. DAC Linearity DNL & INL (LSB) vs Code", "Static linearity and headroom characterization", [
                _t(w.get("codes"), w.get("inl_curve_lsb"), "Pre-PEX INL (LSB)", PRE_C, 2, mode="lines+markers"),
                _t(w.get("codes"), w.get("dnl_curve_lsb"), "Pre-PEX DNL (LSB)", "#059669", 1.8, "dot", "lines+markers"),
                _t(P.get("codes"), P.get("inl_curve_lsb"), "Post-PEX INL (LSB)", POST_C, 2, "dash", "lines+markers")],
                _lay("DAC Digital Code", "Linearity Error (LSB)")))
        else:
            out.append(_chart("1. Output Compliance Curve I<sub>out</sub>(V<sub>out</sub>) & R<sub>out</sub>(V<sub>out</sub>)", "DC output voltage sweep from 0 V to V_DD", [
                _t(w.get("v_out_v"), w.get("i_out_ua"), "Pre-PEX I_out (µA)", PRE_C, 2.3),
                _t(w.get("v_out_v"), w.get("r_out_vs_v_mohm"), "Pre-PEX R_out (MΩ)", "#059669", 1.8, "dot", y2=True),
                _t(P.get("v_out_v"), P.get("i_out_ua"), "Post-PEX I_out (µA)", POST_C, 2.3, "dash")],
                _lay("Output Voltage V_out (V)", "Output Current I_out (µA)", "R_out (MΩ)")))
            out.append(_chart("2. Incremental Output Resistance R<sub>out</sub>(V<sub>out</sub>) & Compliance", "Static linearity and headroom characterization", [
                _t(w.get("v_out_v"), w.get("r_out_vs_v_mohm"), "Pre-PEX R_out (MΩ)", PRE_C, 2.2),
                _t(P.get("v_out_v"), P.get("r_out_vs_v_mohm"), "Post-PEX R_out (MΩ)", POST_C, 2.2, "dash")],
                _lay("Output Voltage V_out (V)", "Incremental R_out (MΩ)")))
        out.append(_chart("3. AC Output Impedance |Z<sub>out</sub>(f)| & Dynamic Step Settling",
                          "Small-signal output impedance vs frequency and full-scale step response (|Z_out| is clipped at 5000 MΩ by the generator)", [
            _t(w.get("freq_mhz"), w.get("z_out_mohm"), "Pre-PEX |Z_out(f)| (MΩ)", PRE_C, 2.2),
            _t(P.get("freq_mhz"), P.get("z_out_mohm"), "Post-PEX |Z_out(f)| (MΩ)", POST_C, 2.2, "dash")],
            _lay("Frequency (MHz)", "|Z_out(f)| (MΩ)", xlog=True, ylog=True)))
    elif fam == "cml_ro":
        out.append(_chart("1. Differential RF Output Waveforms V<sub>out</sub>, V<sub>outn</sub> & V<sub>diff</sub>(t)", "Multi-GHz CML complementary outputs and differential swing (Pre-PEX vs Post-PEX)", [
            _t(w.get("time_ns"), w.get("v_out"), "Pre-PEX V_out+", PRE_C, 2.1),
            _t(w.get("time_ns"), w.get("v_outn"), "Pre-PEX V_out−", "#93c5fd", 1.7, "dot"),
            _t(w.get("time_ns"), w.get("v_diff"), "Pre-PEX V_diff", "#059669", 2.0),
            _t(P.get("time_ns"), P.get("v_diff"), "Post-PEX V_diff", POST_C, 2.1, "dash")], _lay("Time (ns)", "Voltage (V)")))
        out.append(_chart("2. Tail Bias / Control Voltage Tuning f<sub>osc</sub> & Power", f"RF oscillation frequency and DC power across {w.get('ctrl_label') or 'bias control'}", [
            _t(w.get("ctrl_vals"), w.get("f_tune_mhz"), "Pre-PEX f_osc (MHz)", PRE_C, 2.3, mode="lines+markers"),
            _t(w.get("ctrl_vals"), w.get("power_tune_uw"), "Pre-PEX Power (µW)", "#059669", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("ctrl_vals"), P.get("f_tune_mhz"), "Post-PEX f_osc (MHz)", POST_C, 2.2, "dash", "lines+markers")],
            _lay(w.get("ctrl_label") or "Control Input", "Frequency f_osc (MHz)", "Power (µW)")))
        out.append(_chart("3. RF Phase Noise Spectrum L(Δf) vs Offset Frequency",
                          "Multi-GHz CML phase noise profile (1 kHz – 10 MHz offset). *Analytic Hajimiri–Lee ISF model evaluated from the simulated f_osc, P_DC and swing — not a noise simulation.*", [
            _t(w.get("pn_offset_hz"), w.get("pn_dbc_hz"), "Pre-PEX L(Δf)", PRE_C, 2.2, mode="lines+markers"),
            _t(P.get("pn_offset_hz"), P.get("pn_dbc_hz"), "Post-PEX L(Δf)", POST_C, 2.1, "dash", "lines+markers")],
            _lay("Offset Frequency Δf (Hz)", "Phase Noise L(Δf) (dBc/Hz)", xlog=True)))
    elif fam == "clk_div":
        out.append(_chart(f"1. RF Input Clock V<sub>clk</sub>(t) vs Divided Output V<sub>out</sub>(t) (÷{mp.get('div_ratio_nom') or 2})",
                          f"Steady-state frequency division at f_in = {num(mp.get('f_in_ghz'), 2)} GHz", [
            _t(w.get("time_ns"), w.get("v_clk"), "Input Clock V_clk", "#94a3b8", 1.5, "dot"),
            _t(w.get("time_ns"), w.get("v_out"), "Pre-PEX Divided V_out", PRE_C, 2.4),
            _t(P.get("time_ns"), P.get("v_out"), "Post-PEX Divided V_out", POST_C, 2.2, "dash")], _lay("Time (ns)", "Voltage (V)")))
        out.append(_chart("2. Wideband Frequency Locking f<sub>out</sub>(f<sub>in</sub>) & Division Ratio", "Verified frequency division across 0.25 GHz – 3.5+ GHz RF input", [
            _t(w.get("f_in_sweep_ghz"), w.get("f_out_sweep_ghz"), "Pre-PEX f_out (GHz)", PRE_C, 2.3, mode="lines+markers"),
            _t(w.get("f_in_sweep_ghz"), w.get("div_ratio_sweep"), "Pre-PEX Ratio f_in/f_out", "#059669", 1.9, "dot", "lines+markers", y2=True),
            _t(P.get("f_in_sweep_ghz"), P.get("f_out_sweep_ghz"), "Post-PEX f_out (GHz)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Input Clock Frequency f_in (GHz)", "Divided Output f_out (GHz)", "Measured Ratio f_in / f_out")))
        out.append(_chart("3. Input Clock Sensitivity Curve V<sub>in,min</sub>(f<sub>in</sub>) & Output Swing",
                          "Minimum required input clock swing for clean locking vs input frequency. *The V_in,min curve is a model curve "
                          "(parabola in f_in) scaled to the single measured point at f_target; only that point is simulated.* Output swing is a measured sweep.", [
            _t(w.get("sens_f_in_ghz"), w.get("sens_vin_min_v"), "Pre-PEX Min V_in,sens (model, V_pp)", "#7c3aed", 2.3, mode="lines+markers"),
            _t(w.get("f_in_sweep_ghz"), w.get("vpp_out_sweep_v"), "Pre-PEX Output Swing V_pp,out (V)", PRE_C, 1.9, "dot", "lines+markers", y2=True),
            _t(P.get("sens_f_in_ghz"), P.get("sens_vin_min_v"), "Post-PEX Min V_in,sens (model, V_pp)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Input Clock Frequency f_in (GHz)", "Min Input Swing V_in,min (V_pp)", "Output Swing V_pp,out (V)")))
    elif fam == "vref_2t":
        out.append(_chart("1. Temperature Characteristic V<sub>REF</sub>(T) (−40 °C to +125 °C)",
                          f"Box-method TC = {num(mp.get('tc_ppm_c'), 1)} ppm/°C (Pre-PEX) vs {num(mx.get('tc_ppm_c'), 1)} ppm/°C (Post-PEX)", [
            _t(w.get("temp_c"), w.get("vref_temp_mv"), "Pre-PEX V_REF(T) (mV)", PRE_C, 2.4, mode="lines+markers"),
            _t(P.get("temp_c"), P.get("vref_temp_mv"), "Post-PEX V_REF(T) (mV)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Temperature T (°C)", "Reference Voltage V_REF (mV)")))
        out.append(_chart("2. DC Supply / Line Regulation V<sub>REF</sub>(V<sub>DD</sub>) (0.4 V – 3.6 V)",
                          f"Minimum operating V_DD,min = {num(mp.get('min_vdd_v'), 2)} V · Line sensitivity = {num(mp.get('line_sens_pct_v'), 3)} %/V", [
            _t(w.get("vdd_sweep_v"), w.get("vref_line_mv"), "Pre-PEX V_REF(V_DD)", "#059669", 2.4, mode="lines+markers"),
            _t(P.get("vdd_sweep_v"), P.get("vref_line_mv"), "Post-PEX V_REF(V_DD)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Supply Voltage V_DD (V)", "Reference Voltage V_REF (mV)")))
        out.append(_chart("3. Power Supply Rejection Ratio PSRR(f) vs Frequency",
                          f"AC supply rejection -20·log10(|∂V_out/∂V_DD|) across 1 Hz – 100 MHz (PSRR @ 100 Hz = {num(mp.get('psrr_100hz_db'), 1)} dB)", [
            _t(w.get("freq_hz"), w.get("psrr_db"), "Pre-PEX PSRR (dB)", "#7c3aed", 2.3, mode="lines+markers"),
            _t(P.get("freq_hz"), P.get("psrr_db"), "Post-PEX PSRR (dB)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Frequency f (Hz)", "PSRR Rejection (dB)", xlog=True)))
    elif fam == "bm_iref":
        codes = w.get("trim_codes") or list(range(8))
        tt = mp.get("iref_ua")
        tr = [
            _t(codes, w.get("iref_trim_tt_ua"), "TT (Center Code 4)", PRE_C, 2.5, mode="lines+markers"),
            _t(codes, w.get("iref_trim_ss_ua"), f"SS (Trim @ c={mp.get('trim_code_ss', DASH)})", "#059669", 2.2, "dot", "lines+markers"),
            _t(codes, w.get("iref_trim_ff_ua"), f"FF (Trim @ c={mp.get('trim_code_ff', DASH)})", "#dc2626", 2.2, "dot", "lines+markers"),
            _t([codes[0], codes[-1]], [tt, tt], "TT Target I_REF", "#64748b", 1.5, "dash") if isnum(tt) else None,
            _t(codes, P.get("iref_trim_tt_ua"), "Post-PEX TT", POST_C, 2.0, "dash", "lines+markers"),
        ]
        out.append(_chart("1. 3-Bit Digital Trim Transfer Curves I<sub>REF</sub>(code) Across TT, SS & FF (code = 0..7)",
                          f"Center Code 4 (TT = {num(tt, 3)} µA) · SS trimmed @ Code {mp.get('trim_code_ss', DASH)} ({num(mp.get('iref_ss_trimmed_ua'), 3)} µA) · "
                          f"FF trimmed @ Code {mp.get('trim_code_ff', DASH)} ({num(mp.get('iref_ff_trimmed_ua'), 3)} µA)", tr,
                          _lay("3-Bit Digital Trim Code b[2:0] (Center = 4)", "Reference Current I_REF (µA)", extra={"xaxis": {"dtick": 1}})))
        out.append(_chart("2. Temperature Characteristic I<sub>REF</sub>(T) (−40 °C to +125 °C @ Center Code 4)",
                          f"Box-method TC = {num(mp.get('tc_ppm_c'), 0)} ppm/°C (Pre-PEX) vs {num(mx.get('tc_ppm_c'), 0)} ppm/°C (Post-PEX)", [
            _t(w.get("temp_c"), w.get("iref_temp_ua"), "Pre-PEX I_REF(T) (µA)", PRE_C, 2.4, mode="lines+markers"),
            _t(P.get("temp_c"), P.get("iref_temp_ua"), "Post-PEX I_REF(T) (µA)", POST_C, 2.2, "dash", "lines+markers")],
            _lay("Temperature T (°C)", "Reference Current I_REF (µA)")))
        out.append(_chart("3. Output Compliance Curve I<sub>out</sub>(V<sub>out</sub>) & Incremental R<sub>out</sub>(V<sub>out</sub>)",
                          f"DC output compliance V_comp = {num(mp.get('v_comp_v'), 2)} V · R_out = {num(mp.get('rout_mohm'), 2)} MΩ · Line sens = {num(mp.get('line_sens_pct_v'), 2)} %/V", [
            _t(w.get("v_out_v"), w.get("i_out_ua"), "Pre-PEX I_out(V_out) (µA)", PRE_C, 2.4),
            _t(w.get("v_out_v"), w.get("rout_vs_v_mohm"), "Pre-PEX R_out (MΩ)", "#7c3aed", 1.8, "dot", y2=True),
            _t(P.get("v_out_v"), P.get("i_out_ua"), "Post-PEX I_out(V_out) (µA)", POST_C, 2.2, "dash")],
            _lay("Output Terminal Voltage V_out (V)", "Output Current I_out (µA)", "Incremental R_out (MΩ)")))
    else:  # dco_vco / cml_dco_vco
        cl = w.get("ctrl_label") or "Control Input"
        out.append(_chart("1. Frequency Tuning Curve f<sub>osc</sub> (Pre-PEX vs Post-PEX)", f"Oscillation frequency across {w.get('ctrl_label') or 'control input'}", [
            _t(w.get("ctrl_vals"), w.get("f_tune_mhz"), "Pre-PEX f_osc (MHz)", PRE_C, 2.4, mode="lines+markers"),
            _t(P.get("ctrl_vals"), P.get("f_tune_mhz"), "Post-PEX f_osc (MHz)", POST_C, 2.4, "dash", "lines+markers")],
            _lay(cl, "Frequency f_osc (MHz)")))
        out.append(_chart("2. Tuning Gain K<sub>DCO/VCO</sub> & Period Linearity T<sub>osc</sub>", "Local tuning sensitivity and oscillation period across control range", [
            _t(w.get("ctrl_vals"), w.get("kvco_curve"), "Pre-PEX Gain K", "#059669", 2.2, mode="lines+markers"),
            _t(w.get("ctrl_vals"), w.get("t_tune_ns"), "Pre-PEX Period T_osc (ns)", "#7c3aed", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("ctrl_vals"), P.get("kvco_curve"), "Post-PEX Gain K", POST_C, 2.2, "dash", "lines+markers")],
            _lay(cl, f"Gain ({mp.get('kvco_unit') or 'MHz/unit'})", "Period T_osc (ns)")))
        cml = fam == "cml_dco_vco"
        tr3 = [_t(w.get("time_ns"), w.get("v_out"), "Pre-PEX V_out", PRE_C, 2.2)]
        if cml and w.get("v_diff"):
            tr3.append(_t(w.get("time_ns"), w.get("v_diff"), "Pre-PEX V_diff", "#059669", 2.0))
        if wp and wp.get("time_ns"):
            y = wp.get("v_diff") if (cml and wp.get("v_diff")) else wp.get("v_out")
            tr3.append(_t(wp.get("time_ns"), y, "Post-PEX V_diff" if cml else "Post-PEX V_out", POST_C, 2.2, "dash"))
        out.append(_chart("3. Center-Frequency Transient Waveform V<sub>out</sub>(t)", "Steady-state output oscillation at nominal center control setting",
                          tr3, _lay("Time (ns)", "Voltage (V)")))
    # (4) common PVT profile
    pp = (d.get("pvt_pre") or {}).get("points") or []
    pq = (d.get("pvt_post") or {}).get("points") or []
    pv = d.get("pvt_pre") or {}
    mc = d.get("mc_pre") or {}
    labels = [f"{p['corner'].upper()}<br>{p['temp_c']}°" for p in pp]
    tr4 = [{"type": "bar", "x": labels, "y": [p.get("val") for p in pp], "name": f"Pre-PEX PVT ({pv.get('unit', '')})", "marker": {"color": PRE_C, "opacity": 0.82}}]
    if pq:
        tr4.append({"type": "bar", "x": labels, "y": [p.get("val") for p in pq], "name": f"Post-PEX PVT ({pv.get('unit', '')})", "marker": {"color": POST_C, "opacity": 0.85}})
    if pp:
        mq = d.get("mc_post") or {}
        if fam == "clk_div":
            t4 = f"4. 15-Corner PVT Profile ({pv.get('metric_label') or 'Primary'})"
            c4 = "Pre-PEX (blue) vs Post-PEX (orange) across 5 corners × 3 temperatures. (The retired title also named a 30-run Monte Carlo; its f_max statistics were synthetic and are not shown.)"
        else:
            na, nb = mc.get("n_runs", 30), mq.get("n_runs", 30)
            runs = f"{na}" if na == nb else f"{na}/{nb}"
            t4 = f"4. 15-Corner PVT Profile & {runs}-Run Mismatch Monte Carlo ({pv.get('metric_label') or 'Primary'})"
            c4 = (f"Pre-PEX (blue) vs Post-PEX (orange) across 5 corners × 3 temperatures; MC CV = {num(mc.get('cv_pct'), 2)}% pre"
                  + (f", {num(mq.get('cv_pct'), 2)}% post" if mq else "") + f" ({runs} runs)")
        out.append(_chart(t4, c4, tr4,
                          {"barmode": "group", "xaxis": {"title": {"text": "PVT Corner & Temperature"}, "tickangle": -35},
                           "legend": {"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"}, "margin": {"t": 40},
                           "yaxis": {"title": {"text": f"{pv.get('metric_label') or 'Value'} ({pv.get('unit', '')})"}}}))
    return [c for c in out if c]


def extra_charts(d):
    """data present in detail.json that the retired site did not plot."""
    fam = d["family"]
    w = d.get("waveforms_pre") or {}
    P = d.get("waveforms_post") or {}
    out = []
    mp, mq = d.get("mc_pre") or {}, d.get("mc_post") or {}
    if mp.get("samples") and fam != "clk_div":
        tr = [{"type": "histogram", "x": mp["samples"], "name": f"Pre-PEX ({mp.get('n_runs', len(mp['samples']))} runs)", "marker": {"color": PRE_C}, "opacity": 0.7}]
        if mq.get("samples"):
            tr.append({"type": "histogram", "x": mq["samples"], "name": f"Post-PEX ({mq.get('n_runs', len(mq['samples']))} runs)", "marker": {"color": POST_C}, "opacity": 0.7})
        out.append(_chart(f"Monte Carlo distribution of {mp.get('metric_label', 'primary metric')}",
                          f"{len(mp['samples'])} pre-PEX" + (f" and {len(mq['samples'])} post-PEX" if mq.get("samples") else "")
                          + " per-finger mismatch samples (`mc_pre.samples` / `mc_post.samples`).",
                          tr, {"barmode": "overlay", "xaxis": {"title": {"text": f"{mp.get('metric_label', '')} ({mp.get('unit', '')})"}}, "yaxis": {"title": {"text": "Count"}}}, 320))
    if fam == "tcap":
        out.append(_chart("Quality factor Q(f) vs frequency", "`q_vs_freq` from the broadband AC extraction.", [
            _t(w.get("freq_mhz"), w.get("q_vs_freq"), "Pre-PEX Q(f)", PRE_C), _t(P.get("freq_mhz"), P.get("q_vs_freq"), "Post-PEX Q(f)", POST_C, dash="dash")],
            _lay("Frequency (MHz)", "Q", xlog=True, ylog=True), 320))
    if fam == "cm_idac":
        out.append(_chart("Full-scale step response I<sub>out</sub>(t)", "`step_i_ua` vs `step_time_ns` (basis of t_settle).", [
            _t(w.get("step_time_ns"), w.get("step_i_ua"), "Pre-PEX I_out(t)", PRE_C), _t(P.get("step_time_ns"), P.get("step_i_ua"), "Post-PEX I_out(t)", POST_C, dash="dash")],
            _lay("Time (ns)", "Output Current (µA)"), 320))
        if d["topo"].startswith("idac_"):
            out.append(_chart("Output compliance I<sub>out</sub>(V<sub>out</sub>) & R<sub>out</sub>(V<sub>out</sub>)", "DC output voltage sweep (plotted for mirrors only on the retired site).", [
                _t(w.get("v_out_v"), w.get("i_out_ua"), "Pre-PEX I_out (µA)", PRE_C),
                _t(w.get("v_out_v"), w.get("r_out_vs_v_mohm"), "Pre-PEX R_out (MΩ)", "#059669", 1.8, "dot", y2=True),
                _t(P.get("v_out_v"), P.get("i_out_ua"), "Post-PEX I_out (µA)", POST_C, dash="dash")],
                _lay("Output Voltage V_out (V)", "Output Current I_out (µA)", "R_out (MΩ)"), 320))
    if fam in ("dco_vco", "cml_dco_vco", "cml_ro"):
        cl = w.get("ctrl_label") or "Control Input"
        out.append(_chart("Power & swing across the tuning range", "`power_tune_uw` and `vpp_tune_v` vs control setting.", [
            _t(w.get("ctrl_vals"), w.get("power_tune_uw"), "Pre-PEX Power (µW)", PRE_C, mode="lines+markers"),
            _t(P.get("ctrl_vals"), P.get("power_tune_uw"), "Post-PEX Power (µW)", POST_C, dash="dash", mode="lines+markers"),
            _t(w.get("ctrl_vals"), w.get("vpp_tune_v"), "Pre-PEX V_pp (V)", "#059669", 1.8, "dot", "lines+markers", y2=True),
            _t(P.get("ctrl_vals"), P.get("vpp_tune_v"), "Post-PEX V_pp (V)", "#d97706", 1.8, "dot", "lines+markers", y2=True)],
            _lay(cl, "Power (µW)", "Swing V_pp (V)"), 320))
    if fam in ("dco_vco", "cml_dco_vco"):
        out.append(_chart("Phase noise spectrum L(Δf)", "*Analytic Hajimiri–Lee ISF estimate* (`pn_offset_hz`, `pn_dbc_hz`), not a noise simulation.", [
            _t(w.get("pn_offset_hz"), w.get("pn_dbc_hz"), "Pre-PEX L(Δf)", PRE_C, mode="lines+markers"),
            _t(P.get("pn_offset_hz"), P.get("pn_dbc_hz"), "Post-PEX L(Δf)", POST_C, dash="dash", mode="lines+markers")],
            _lay("Offset Frequency Δf (Hz)", "L(Δf) (dBc/Hz)", xlog=True), 320))
        if fam == "dco_vco" and w.get("v_outn"):
            out.append(_chart("Complementary outputs V<sub>out</sub>, V<sub>outn</sub>, V<sub>diff</sub>", "Transient at the centre control setting.", [
                _t(w.get("time_ns"), w.get("v_out"), "Pre-PEX V_out", PRE_C), _t(w.get("time_ns"), w.get("v_outn"), "Pre-PEX V_outn", "#93c5fd", 1.7, "dot"),
                _t(w.get("time_ns"), w.get("v_diff"), "Pre-PEX V_diff", "#059669", 2.0)], _lay("Time (ns)", "Voltage (V)"), 320))
    if fam == "clk_div":
        out.append(_chart("DC power vs input frequency", "`power_sweep_uw` across the f_in sweep.", [
            _t(w.get("f_in_sweep_ghz"), w.get("power_sweep_uw"), "Pre-PEX Power (µW)", PRE_C, mode="lines+markers"),
            _t(P.get("f_in_sweep_ghz"), P.get("power_sweep_uw"), "Post-PEX Power (µW)", POST_C, dash="dash", mode="lines+markers")],
            _lay("Input Clock Frequency f_in (GHz)", "Power (µW)"), 320))
        out.append(_chart("Complementary divided outputs V<sub>out</sub> / V<sub>outb</sub>", "`v_out` and `v_outb` transients.", [
            _t(w.get("time_ns"), w.get("v_out"), "Pre-PEX V_out", PRE_C), _t(w.get("time_ns"), w.get("v_outb"), "Pre-PEX V_outb", "#93c5fd", 1.7, "dot"),
            _t(P.get("time_ns"), P.get("v_outb"), "Post-PEX V_outb", POST_C, dash="dash")], _lay("Time (ns)", "Voltage (V)"), 320))
    if fam == "bm_iref":
        out.append(_chart("Line regulation I<sub>REF</sub>(V<sub>DD</sub>) & bias node", "`iref_line_ua`, `vbias_line_v` vs supply (basis of line sensitivity and V_DD,min).", [
            _t(w.get("vdd_sweep_v"), w.get("iref_line_ua"), "Pre-PEX I_REF (µA)", PRE_C, mode="lines+markers"),
            _t(P.get("vdd_sweep_v"), P.get("iref_line_ua"), "Post-PEX I_REF (µA)", POST_C, dash="dash", mode="lines+markers"),
            _t(w.get("vdd_sweep_v"), w.get("vbias_line_v"), "Pre-PEX V_bias (V)", "#059669", 1.8, "dot", "lines+markers", y2=True)],
            _lay("Supply Voltage V_DD (V)", "I_REF (µA)", "V_bias (V)"), 320))
        out.append(_chart("PSRR(f)", "`psrr_db` vs `freq_hz`.", [
            _t(w.get("freq_hz"), w.get("psrr_db"), "Pre-PEX PSRR (dB)", PRE_C, mode="lines+markers"),
            _t(P.get("freq_hz"), P.get("psrr_db"), "Post-PEX PSRR (dB)", POST_C, dash="dash", mode="lines+markers")],
            _lay("Frequency f (Hz)", "PSRR (dB)", xlog=True), 320))
    return [c for c in out if c]


# ----------------------------------------------------------------------------- tables
def spec_table(d, stage):
    rows = []
    for r in spec_rows(d, stage):
        def cell(txt, m):
            if txt == DASH:
                return txt
            fls = flagged(d["family"], m, r["fl"])
            if fls:
                return {"v": f"{txt} ({', '.join(dict.fromkeys(x[1] for x in fls))})", "s": "warn", "title": "; ".join(dict.fromkeys(x[2] for x in fls))}
            ok = r["chk"](m) if r["chk"] else None
            if ok is None:
                return txt
            return {"v": txt, "s": "good" if ok else "bad", "title": f"target {r['t']}: {'met' if ok else 'missed'}"}
        rows.append([r["p"] + (EST if r["est"] else ""), r["t"], cell(r["pre"], d.get("metrics_pre") or {}),
                     cell(r["post"], d.get("metrics_post") or {}), r["delta"], r["worst"]])
    drc, lvs, pex = d.get("drc") or {}, d.get("lvs") or {}, d.get("pex") or {}
    st = lambda ok, txt_ok, txt_bad, warn=False: {"v": txt_ok if ok else txt_bad, "s": "good" if ok else ("warn" if warn else "bad")}
    drc_c = st(drc.get("ok"), "PASS (0 effective violations)", f"FAIL ({drc.get('effective')})")
    lvs_c = st(lvs.get("ok"), "PASS (Netlists match)", "FAIL")
    pex_c = st(pex.get("ok"), f"PASS ({pex.get('parasitic_c_count', 0)} C_par extracted)", "Pending", True)
    rows += [["**KLayout DRC (gf180mcu.drc)**", "0 violations", drc_c, drc_c, DASH, f"{drc.get('ignored') or 0} density rules waived"],
             ["**KLayout LVS (gf180mcu.lvs)**", "Netlists match", lvs_c, lvs_c, DASH, "Option-B MIM + 5LM"],
             ["**Magic PEX (ext2spice)**", "Port/Device Match", pex_c, pex_c, DASH, "cthresh 0.01 fF"]]
    wl = "post-PEX" if stage == "full" else "pre-PEX"
    return {"type": "table", "alt": "spec", "stage": stage, "title": "Specification & Pre-PEX vs. Post-PEX verification table",
            "columns": [{"key": "p", "label": "Parameter", "md": True}, {"key": "t", "label": "Target"},
                        {"key": "pre", "label": "Pre-PEX"}, {"key": "post", "label": "Post-PEX"}, {"key": "d", "label": "Delta"},
                        {"key": "w", "label": f"Worst PVT Corner ({wl})"}],
            "rows": rows, "search": False, "csv_name": f"{d['card_id']}_spec",
            "caption": "Cell colour: green = meets the numeric criterion stated in *Target*, red = misses it; rows with "
                       "Minimize/Maximize or descriptive targets are not judged; amber = generator placeholder, clip limit or sweep bound "
                       "(hover for details; such values are not published as results). Delta = generator's pre→post shift."}


def banner(d, stage):
    rows = spec_rows(d, stage)[:6]
    items = []
    for r in rows:
        if stage == "full":
            v = r["post"] if r["post"] != DASH else r["pre"]
            sub = f"Target: {r['t']} · Pre: {r['pre']} ({r['delta']})"
        else:
            v = r["pre"]
            sub = f"Target: {r['t']} · Post-PEX: {r['post']} ({r['delta']})"
        fls = flagged(d["family"], d.get("metrics_post" if stage == "full" and r["post"] != DASH else "metrics_pre") or {}, r["fl"])
        if fls:
            v = f"{v} ({', '.join(dict.fromkeys(x[1] for x in fls))})"
        items.append({"label": r["p"] + (" (estimate)" if r["est"] else ""), "value": v, "sub": sub})
    L, pex = d.get("layout") or {}, d.get("pex") or {}
    items.append({"label": "Physical Layout Area", "value": f"{num(L.get('area_um2'), 1)} µm²",
                  "sub": f"{num(L.get('width_um'), 1)} × {num(L.get('height_um'), 1)} µm · {pex.get('parasitic_c_count') or 0} PEX caps"})
    pv = d.get("pvt_post" if stage == "full" else "pvt_pre") or {}
    mc = d.get("mc_post" if stage == "full" else "mc_pre") or {}
    clean = (d.get("drc") or {}).get("ok") and (d.get("lvs") or {}).get("ok") and pex.get("ok")
    fam = d["family"]
    pvt_txt = "PVT: no pass criterion" if fam in ("tcap", "tres", "cm_idac") else f"PVT {pv.get('pass_count', DASH)}/{pv.get('total_count', DASH)}"
    mc_txt = "MC: not run on f_max" if fam == "clk_div" else f"MC CV {num(mc.get('cv_pct'), 2)}% ({mc.get('n_runs', DASH)} runs)"
    items.append({"label": "Signoff & Yield", "value": "DRC·LVS·PEX ✓" if clean else "In Progress", "sub": f"{pvt_txt} · {mc_txt}"})
    lab = "Post-layout PEX Active" if stage == "full" else "Pre-PEX Schematic Active"
    return {"type": "section", "alt": "banner", "stage": stage, "title": f"Key performance & verification banner ({lab})",
            "blocks": [{"type": "stats", "items": items}]}


def pvt_table(d, stage):
    pv = d.get("pvt_pre") or {}
    pre = pv.get("points") or []
    post = (d.get("pvt_post") or {}).get("points") or []
    unit, ml = pv.get("unit", ""), pv.get("metric_label", "Metric")
    no_crit = d["family"] in ("tcap", "tres", "cm_idac")
    rows = []
    for i, p in enumerate(pre):
        q = post[i] if i < len(post) else {}
        dl = None
        if isnum(q.get("val")) and isnum(p.get("val")) and abs(p["val"]) > 1e-9:
            dl = (q["val"] - p["val"]) / abs(p["val"]) * 100
        ok = (q.get("pass", p.get("pass")) if stage == "full" else p.get("pass"))
        status = ({"v": "n/a", "s": "muted", "title": "the generator has no PVT pass criterion for this family"} if no_crit
                  else {"v": "PASS" if ok else "WARN", "s": "good" if ok else "warn"})
        rows.append([p["corner"].upper(), p.get("temp_c"), p.get("val"), q.get("val"), dl, p.get("secondary"), status])
    return {"type": "table", "alt": "pvt", "stage": stage, "title": "15-Corner PVT Verification Table (tt, ss, ff, sf, fs × −40, 27, 125 °C)",
            "columns": [{"key": "c", "label": "Corner", "type": "text"}, {"key": "t", "label": "Temp", "unit": "°C", "digits": 3},
                        {"key": "pre", "label": f"Pre-PEX {ml}", "unit": unit, "digits": 4}, {"key": "post", "label": f"Post-PEX {ml}", "unit": unit, "digits": 4},
                        {"key": "d", "label": "Pre→Post Δ", "unit": "%", "digits": 3}, {"key": "sec", "label": "Secondary", "digits": 3},
                        {"key": "st", "label": "Status", "title": f"PASS/WARN at the {'post' if stage == 'full' else 'pre'}-PEX stage"}],
            "rows": rows, "search": False, "csv_name": f"{d['card_id']}_pvt",
            "caption": f"Worst corner: {pv.get('worst_corner', DASH)} (pre-PEX) / {(d.get('pvt_post') or {}).get('worst_corner', DASH)} (post-PEX). "
                       + ("The generator defines no PVT pass criterion for this family (the retired site's PASS flags were defaults). " if no_crit else
                          f"Pass count {pv.get('pass_count', DASH)}/{pv.get('total_count', DASH)} pre, "
                          f"{(d.get('pvt_post') or {}).get('pass_count', DASH)}/{(d.get('pvt_post') or {}).get('total_count', DASH)} post. ") +
                       "*Secondary* is the generator's second PVT quantity (unlabelled in the data)."}


def mc_table(d):
    a, b = d.get("mc_pre") or {}, d.get("mc_post") or {}
    if d["family"] == "clk_div":
        return {"type": "note", "tone": "warn", "title": "Monte Carlo:",
                "text": "the generator's 30 mismatch runs for clock dividers record f_out, duty, swing and power at the target input frequency but no "
                        "f_max,in; the f_max statistics in the docs were synthesised by the site generator (normal draw, σ = 1.8 %) and are not "
                        "republished. The retired site showed them as a 30-run MC summary."}
    u = a.get("unit", "")
    rows = [["**Mean (μ)**", a.get("mean"), b.get("mean")], ["**Std Dev (σ)**", a.get("std"), b.get("std")],
            ["**Relative Spread (CV = σ/μ)** [%]", {"v": a.get("cv_pct"), "s": "good"}, {"v": b.get("cv_pct"), "s": "good"} if b else None],
            ["**Minimum (min)**", a.get("min"), b.get("min")], ["**Maximum (max)**", a.get("max"), b.get("max")]]
    na, nb = a.get("n_runs", 30), b.get("n_runs", 30)
    return {"type": "table", "title": f"{na if na == nb else f'{na}/{nb}'}-Run Per-Finger Mismatch Monte Carlo Summary (`expand_mc=True`)",
            "columns": [{"key": "s", "label": f"Statistic ({a.get('metric_label', 'Primary Metric')} in {u})", "md": True},
                        {"key": "a", "label": f"Pre-PEX Schematic ({a.get('n_runs', 30)} runs)", "digits": 5},
                        {"key": "b", "label": f"Post-PEX Extracted ({b.get('n_runs', 30)} runs)", "digits": 5}],
            "rows": rows, "search": False, "csv": False,
            "caption": "Statistical Pelgrom mismatch evaluation across all multi-finger MOSFETs expanded into individual finger instances."}


REGION_S = {"WI": "good", "MI": "muted", "SI": "warn"}


def op_table(d):
    devs = (d.get("design") or {}).get("devices") or []
    ops = d.get("op_pre") or {}
    rows = []
    for v in devs:
        o = ops.get(v["name"]) or {}
        reg = o.get("region")
        rows.append([v["name"], v.get("role") or v.get("kind"), v.get("model"), v.get("w_finger"), v.get("l"), v.get("m"), v.get("w_total"),
                     v.get("target_gmid"), o.get("gmid"), o.get("id_ua"), o.get("gm_us"), o.get("av0"), o.get("vgs"), o.get("vth"), o.get("vds"), o.get("vdsat"),
                     {"v": reg or DASH, "s": REGION_S.get(reg, "bad")} if reg else DASH,
                     f"{v.get('d')}/{v.get('g')}/{v.get('s')}/{v.get('b')}"])
    return {"type": "table", "title": f"Transistor operating-point & g<sub>m</sub>/I<sub>D</sub> sizing table ({len(devs)} MOSFETs, pre-PEX operating point)",
            "columns": [{"key": "n", "label": "Device", "type": "text"}, {"key": "r", "label": "Role", "type": "text"}, {"key": "t", "label": "Type", "type": "text"},
                        {"key": "wf", "label": "W<sub>f</sub>", "unit": "µm", "digits": 4}, {"key": "l", "label": "L", "unit": "µm", "digits": 4},
                        {"key": "m", "label": "m", "digits": 3}, {"key": "wt", "label": "W<sub>tot</sub>", "unit": "µm", "digits": 4},
                        {"key": "gt", "label": "g<sub>m</sub>/I<sub>D</sub> Target", "digits": 3}, {"key": "gs", "label": "g<sub>m</sub>/I<sub>D</sub> Sim", "digits": 3},
                        {"key": "id", "label": "I<sub>D</sub>", "unit": "µA", "digits": 4}, {"key": "gm", "label": "g<sub>m</sub>", "unit": "µS", "digits": 4},
                        {"key": "av", "label": "g<sub>m</sub>/g<sub>ds</sub>", "digits": 4}, {"key": "vgs", "label": "V<sub>GS</sub>", "unit": "V", "digits": 3},
                        {"key": "vth", "label": "V<sub>th</sub>", "unit": "V", "digits": 3}, {"key": "vds", "label": "V<sub>DS</sub>", "unit": "V", "digits": 3},
                        {"key": "vdsat", "label": "V<sub>DSsat</sub>", "unit": "V", "digits": 3}, {"key": "reg", "label": "Region"},
                        {"key": "nodes", "label": "Nodes (D/G/S/B)", "type": "text"}],
            "rows": rows, "csv_name": f"{d['card_id']}_op",
            "caption": "Operating point from the pre-PEX schematic simulation (`op_pre`). Region: WI weak / MI moderate / SI strong inversion. "
                       "g<sub>m</sub>/g<sub>ds</sub> = 999 is the generator's display cap. V<sub>GS</sub>/V<sub>th</sub> columns are in the data but were not shown on the retired site. "
                       "The retired site's schematic↔table cross-highlighting is not available here."}


def passive_table(d):
    des = d.get("design") or {}
    caps, ress = des.get("caps") or [], des.get("resistors") or []
    if not caps and not ress:
        return None
    rows = []
    for c in caps:
        rows.append([c["name"], f"Capacitor (`{c.get('kind')}`)", c.get("role"), f"{c.get('n_units')} × ({num(c.get('c_width'), 2)} µm × {num(c.get('c_length'), 2)} µm)",
                     f"{num(c.get('c_pf'), 4)} pF", f"{c.get('p')} — {c.get('n')}"])
    for r in ress:
        rows.append([r["name"], f"Resistor (`{r.get('model')}`)", r.get("role"), f"{r.get('n_segs')} seg × ({num(r.get('r_width'), 2)} µm × {num(r.get('r_length'), 2)} µm)",
                     f"{num(r.get('r_kohm'), 3)} kΩ", f"{r.get('p')} — {r.get('n')} (sub: {r.get('sub')})"])
    return {"type": "table", "title": f"Passive devices table ({len(caps)} Capacitors/Varactors, {len(ress)} Resistors)",
            "columns": [{"key": "n", "label": "Name", "type": "text"}, {"key": "t", "label": "Device Type", "md": True}, {"key": "r", "label": "Role", "type": "text"},
                        {"key": "g", "label": "Unit Geometry", "type": "text"}, {"key": "v", "label": "Value", "type": "text"}, {"key": "p", "label": "Terminals", "type": "text"}],
            "rows": rows, "search": False, "csv_name": f"{d['card_id']}_passives"}


def layout_blocks(d, files):
    L, drc, lvs, pex = d.get("layout") or {}, d.get("drc") or {}, d.get("lvs") or {}, d.get("pex") or {}
    kv = [
        {"label": "KLayout DRC (gf180mcu.drc)", "value": "DRC CLEAN (0)" if drc.get("ok") else f"FAIL ({drc.get('effective')})", "s": "good" if drc.get("ok") else "bad"},
        {"label": "DRC detail", "value": f"Effective: {drc.get('effective', 0)} · Waived density: {drc.get('ignored', 0)}"},
        {"label": "KLayout LVS (gf180mcu.lvs)", "value": "LVS MATCH" if lvs.get("ok") else "LVS MISMATCH", "s": "good" if lvs.get("ok") else "bad"},
        {"label": "LVS deck", "value": "5LM · 11K Top Metal · Option-B MIM"},
        {"label": "Magic PEX (ext2spice)", "value": "PEX VERIFIED" if pex.get("ok") else "PEX PENDING", "s": "good" if pex.get("ok") else "warn"},
        {"label": "Parasitic C nodes", "value": f"{pex.get('parasitic_c_count') or 0} (cthresh 0.01 fF)"},
        {"label": "Bounding Box & Area", "value": f"{num(L.get('area_um2'), 1)} µm²"},
        {"label": "Width × height (aspect)", "value": f"{num(L.get('width_um'), 2)} µm × {num(L.get('height_um'), 2)} µm (aspect {num(L.get('aspect_ratio'), 2)})"},
        {"label": "Extracted Active Fingers", "value": f"{pex.get('nfet_fingers') or 0} N / {pex.get('pfet_fingers') or 0} P",
         "s": "good" if (pex.get("nfet_fingers"), pex.get("pfet_fingers")) == (pex.get("expected_nfet_fingers"), pex.get("expected_pfet_fingers")) else "warn"},
        {"label": "Expected fingers", "value": f"{pex.get('expected_nfet_fingers') or 0} N / {pex.get('expected_pfet_fingers') or 0} P"},
        {"label": "Extracted Passives & Routing", "value": f"{pex.get('caps') or 0} C · {pex.get('resistors') or 0} R (expected {pex.get('expected_caps', DASH)} C · {pex.get('expected_resistors', DASH)} R)",
         "s": "good" if (pex.get("caps"), pex.get("resistors")) == (pex.get("expected_caps"), pex.get("expected_resistors")) else "warn"},
        {"label": "Wirelength / vias / blocks", "value": f"{num(L.get('wirelength_um'), 1)} µm · {L.get('vias') or 0} vias · {L.get('n_blocks', DASH)} placed blocks"},
        {"label": "Extracted ports", "value": ", ".join(pex.get("extracted_ports") or []) or DASH},
    ]
    out = [{"type": "section", "title": "Physical verification & parasitic extraction summary", "blocks": [{"type": "kv", "items": kv, "cols": 2}]}]
    if files.get("gds"):
        out.append({"type": "section", "title": f"GDSII layout (`{d['card_id']}.gds`)", "blocks": [
            {"type": "layout", "gds": files["gds"], "max_height": 620,
             "caption": "Generated with experimental `gLayout` (PR #128). The retired site's interactive vector viewer (layout.svg) is replaced by the hub's "
                        "rendered thumbnail; click it to open the raw GDS in the source repository (requires access)."},
            {"type": "downloads", "items": [x for x in [
                {"label": f"{d['card_id']}.gds.gz", "file": files.get("gds")}, {"label": "pex.spice.gz", "file": files.get("pex_netlist")},
                {"label": "lvs_reference.spice", "file": files.get("lvs_netlist")}, {"label": "netlist.spice", "file": files.get("netlist")}] if x["file"]]}]})
    pins = L.get("pin_coords") or d.get("pin_coords") or []
    pin_t = {"type": "table", "title": f"Top-level pin coordinates ({len(pins)} pins)",
             "columns": [{"key": "p", "label": "Pin Name", "type": "text"}, {"key": "l", "label": "Layer", "type": "text"},
                         {"key": "g", "label": "GDS layer/datatype", "type": "text"}, {"key": "x", "label": "X", "unit": "µm", "digits": 5},
                         {"key": "y", "label": "Y", "unit": "µm", "digits": 5}],
             "rows": [[p.get("name") or p.get("pin"), p.get("layer"), "/".join(str(x) for x in p.get("gds_layer") or []), p.get("x_um"), p.get("y_um")] for p in pins]
             or [[f"Ports: {', '.join((d.get('design') or {}).get('ports') or [])}", DASH, DASH, None, None]],
             "search": False, "csv_name": f"{d['card_id']}_pins"}
    rr = [["Effective DRC Violations", drc.get("effective", 0), {"v": "Signoff Clean" if not drc.get("effective") else "Violations", "s": "good" if not drc.get("effective") else "bad"}]]
    for rule, cnt in sorted((drc.get("by_rule") or {}).items()):
        rr.append([f"`{rule}` (effective)", cnt, {"v": "Violation", "s": "bad"}])
    for rule, cnt in sorted((drc.get("ignored_by_rule") or {}).items()):
        rr.append([f"`{rule}` (Chip-level density/latchup)", cnt, {"v": "Waived on standalone subcell", "s": "muted"}])
    rr.append(["KLayout LVS Device & Net Match", "100%" if lvs.get("ok") else "mismatch",
               {"v": "Congratulations! Netlists match" if lvs.get("ok") else "Netlists do not match", "s": "good" if lvs.get("ok") else "bad"}])
    rr.append(["Magic PEX Coupled/Grounded Caps", pex.get("parasitic_c_count") or 0, {"v": "Included in Post-PEX netlist", "s": "good" if pex.get("ok") else "warn"}])
    rule_t = {"type": "table", "title": "DRC / LVS / PEX rule breakdown",
              "columns": [{"key": "c", "label": "Check / Rule Category", "md": True}, {"key": "n", "label": "Count / Result"}, {"key": "d", "label": "Disposition"}],
              "rows": rr, "search": False, "csv": False}
    out.append({"type": "section", "cols": 2, "blocks": [pin_t, rule_t]})
    return out


# ----------------------------------------------------------------------------- document
def build(d, files, sch_design):
    des = d.get("design") or {}
    knobs = des.get("knobs") or {}
    blocks = [banner(d, "pre"), banner(d, "full")]
    blocks.append({"type": "section", "title": "Specification & verification", "blocks": [spec_table(d, "pre"), spec_table(d, "full")]})
    kvrows = [["Card ID", f"`{d['card_id']}`"], ["Ports", f"`{', '.join(des.get('ports') or [])}`"],
              ["Device Count", f"{len(des.get('devices') or [])} MOSFETs · {len(des.get('caps') or [])} Caps · {len(des.get('resistors') or [])} Resistors"]]
    for k, v in knobs.items():
        vv = f"{float(v):.4g}" if isnum(v) else (v if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else str(v))
        kvrows.append([f"Knob: `{k}`", vv])
    kvrows.append(["Artifact SHA-256", f"`{d.get('sha256', '')}`"])
    kb = [{"type": "markdown", "text": d.get("topo_summary") or ""}]
    notes = des.get("notes")
    if isinstance(notes, str) and notes.startswith("[") and notes.endswith("]"):
        try:
            notes = ast.literal_eval(notes)  # generator stringified a list of notes
        except (ValueError, SyntaxError):
            pass
    if notes:
        txt = "\n".join(f"- {x}" for x in notes) if isinstance(notes, list) else str(notes)
        kb.append({"type": "note", "tone": "warn", "text": txt})
    kb.append({"type": "table", "columns": [{"key": "k", "label": "Item", "md": True}, {"key": "v", "label": "Value", "md": True}],
               "rows": kvrows, "search": False, "csv_name": f"{d['card_id']}_knobs"})
    dl = [{"label": "netlist.spice", "file": files.get("netlist")}, {"label": "lvs_reference.spice", "file": files.get("lvs_netlist")},
          {"label": "pex.spice.gz", "file": files.get("pex_netlist")}, {"label": f"{d['card_id']}.gds.gz", "file": files.get("gds")},
          {"label": "schematic.svg", "src": files.get("schematic")}, {"label": "schematic_design.svg", "src": sch_design},
          {"label": "detail.json", "file": files.get("data")}]
    kb.append({"type": "downloads", "title": "Artifact downloads", "items": [x for x in dl if x.get("file") or x.get("src")],
               "caption": "layout.svg (retired vector layout view) is not republished; the hub shows a thumbnail rendered from the GDS instead."})
    blocks.append({"type": "section", "title": "Design knobs, sizing summary & downloadable artifacts", "blocks": kb})
    gal = []
    if files.get("schematic"):
        gal.append({"label": "Op-point view (pre-PEX)", "src": files["schematic"]})
    if sch_design:
        gal.append({"label": "Sizing view (targets)", "src": sch_design})
    if gal:
        blocks.append({"type": "section", "title": "Full-connection annotated schematic", "blocks": [
            {"type": "gallery", "items": gal, "bg": "white", "max_height": 720,
             "caption": "Two views of the same schematic: annotated target → simulated g<sub>m</sub>/I<sub>D</sub> operating point (pre-PEX) and the design-sizing targets. The retired site showed the operating-point view in *Schematic* mode and the "
                        "design-sizing view in *Post-layout* mode (neither carries post-PEX data). Click to open full size (zoom/pan in the browser)."}]})
    blocks.append({"type": "section", "title": "Transistor operating point", "blocks": [op_table(d)]})
    pt = passive_table(d)
    if pt:
        blocks.append({"type": "section", "title": "Passive devices", "blocks": [pt]})
    sims = sim_charts(d)
    sec_sim = {"type": "section", "title": "Simulation results (pre-PEX vs post-PEX)", "cols": 2, "blocks": sims}
    fam = d["family"]
    if fam in ("ro", "cml_ro", "dco_vco", "cml_dco_vco", "clk_div"):
        sec_sim["intro"] = EST_NOTE
    blocks.append(sec_sim)
    blocks.append({"type": "section", "title": "PVT & Monte Carlo verification", "cols": 2,
                   "blocks": [pvt_table(d, "pre"), pvt_table(d, "full"), mc_table(d)]})
    blocks += layout_blocks(d, files)
    ex = extra_charts(d)
    if ex:
        blocks.append({"type": "section", "title": "Additional characterization data (in detail.json, not plotted on the retired site)",
                       "collapsed": True, "cols": 2, "blocks": ex})
    return {"blocks": blocks}
