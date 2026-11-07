#!/usr/bin/env python3
"""Bootstrap hub adapter for sdm-gen-gemini4 (schema aicdb-hub/2).

usage: sdm.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus the
documents it references (referenced as "hub/<path>"): one detail doc per design, five pages
(Summary, Macros, Architectures, Design space, Methodology) and chart/explorer data.

Stage mapping (old site "Verification Stage" switch -> hub stage):
  post-less "1. Pre-Layout"   -> pre      schematic netlists, nominal unit caps / ideal coefficients
  "2. Post-Cap-PEX"           -> partial  Magic-extracted, ratio-trimmed SC cap-array macro (+ op-amp
                                          library PEX metrics); no top-level routing parasitics
  "3. Full-Chip PEX"          -> full     cap PEX + extracted sub-block subcircuits + top-level route PEX
9-corner PVT and 100-run MC are derived from the full-chip view only -> attached to `full` only.

Honesty: ENOB/SNDR/SFDR/DR/power/FoM come from the generator's analytical modulator model
(sdmgen.arch.evaluate_sdm_analytical); ngspice transients supply integrator swings and supply
current. Spectra, DR sweeps and DNL/INL profiles are synthesized from those metrics, PVT corners
are fixed offsets + small random noise, MC draws are random and clipped at >= target + 0.12 bit.
The adapter says so wherever these numbers appear. Old-site rendering bugs (fields shown as
"undefined" / "—") are ported with the real data fields instead.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

DOCS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

IDX = json.loads((DOCS / "data" / "index.json").read_text())
SWEEP = json.loads((DOCS / "data" / "sweep.json").read_text())
DIGF = json.loads((DOCS / "data" / "digital_macros.json").read_text())

STAGES = ("pre", "partial", "full")
VIEW_OF = {"pre": "pre", "partial": "post", "full": "full"}
OLD_STAGE = {"pre": "1. Pre-Layout", "partial": "2. Post-Cap-PEX", "full": "3. Full-Chip PEX"}
OLD_STAGE_LONG = {"pre": "1. Pre-Layout (Schematic)", "partial": "2. Post-Cap-PEX (Trimmed SC Macro)",
                  "full": "3. Full-Chip PEX (Route + Cap + Gate-Level sdm2bin)"}
ARCH_COLORS = {"cifb_shared": "#38bdf8", "cifb_split": "#818cf8", "ciff_ff": "#34d399", "crff_sar": "#fbbf24"}
ARCH_ROW = {"cifb_shared": "CIFB-Shared (Shared-Cs)", "cifb_split": "CIFB-Split (Ref-Isolated + VCM OPA)",
            "ciff_ff": "CIFF-FF (Low-Swing Feedforward)", "crff_sar": "CRFF-InZ / SAR3 (Resonator + 3× Quantizer)"}
CAP_LABEL = {"mom": "MOM", "mim": "MIM"}
CAP_AXIS = {"mom": "MOM (M1–M4)", "mim": "MIM (Opt-B 2 fF/µm²)"}
ARCH_ORDER = IDX["arch_order"]
ARCH_SPECS, RES_SPECS, CAP_SPECS = IDX["arch_specs"], IDX["res_specs"], IDX["cap_specs"]
CAP_MACROS, DIG_MACROS = IDX["cap_macros"], IDX["digital_macros"]
NBITS = IDX["nbits_list"]


# ----------------------------------------------------------------------------- helpers
def sig(v, n=5):
    if isinstance(v, bool) or v is None or isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return 0.0 if v == 0 else float(f"{v:.{n}g}")
    return v


def rnd(o, n=5):
    if isinstance(o, dict):
        return {k: rnd(v, n) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [rnd(v, n) for v in o]
    return sig(o, n)


def write(rel, obj):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rnd(obj), separators=(",", ":"), ensure_ascii=False))
    return f"hub/{rel}"


def fx(v, d=2):
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return "—"


def sgn(v, d=2):
    try:
        return f"{float(v):+.{d}f}"
    except (TypeError, ValueError):
        return "—"


def mul(v, k):
    return None if v is None else v * k


def exists(rel):
    return (DOCS / rel).is_file()


def opa_link(key):
    return f"[{key}](#/opa/{key.replace('/', '-')})" if key else "—"


def sa_link(key):
    return f"[{key}](#/sa/{key})" if key else "—"


def sw_link(key):
    # switch keys contain "__", which the hub's inline markdown would turn into bold: code-format the text, %-encode the href
    return f"[`{key}`](#/switch/{key.replace('_', '%5F')})" if key else "—"


def card_link(cid):
    return f"[{cid}](#/sdm/{cid})"


def col(key, label, **kw):
    c = {"key": key, "label": label}
    c.update(kw)
    return c


def table(title, columns, rows, **kw):
    b = {"type": "table", "title": title, "columns": columns, "rows": rows}
    b.update(kw)
    return b


def chart(title, data, layout=None, **kw):
    b = {"type": "chart", "title": title, "data": data, "layout": layout or {}}
    b.update(kw)
    return b


def md(text, **kw):
    b = {"type": "markdown", "text": text}
    b.update(kw)
    return b


def note(text, tone="info", **kw):
    b = {"type": "note", "text": text, "tone": tone}
    b.update(kw)
    return b


def section(title, blocks, **kw):
    b = {"type": "section", "title": title, "blocks": blocks}
    b.update(kw)
    return b


def kv(title, items, cols=2, **kw):
    def fix(x):  # the hub prints bare numbers with 3 significant digits: keep integers exact
        if isinstance(x, list) and len(x) > 1 and isinstance(x[1], int) and not isinstance(x[1], bool):
            return [x[0], f"{x[1]:,}" if abs(x[1]) >= 1e4 else str(x[1])] + x[2:]
        if isinstance(x, dict) and isinstance(x.get("value"), int) and not isinstance(x.get("value"), bool) and "digits" not in x:
            return dict(x, value=str(x["value"]))
        return x
    b = {"type": "kv", "title": title, "items": [fix(x) for x in items], "cols": cols}
    b.update(kw)
    return b


def axis(t, **kw):
    a = {"title": {"text": t}}
    a.update(kw)
    return a


# ----------------------------------------------------------------------------- load designs
CARDS = IDX["cards"]
DATA = {}
for c in CARDS:
    DATA[c["card_id"]] = json.loads((DOCS / "designs" / c["card_id"] / "data.json").read_text())

N_POST_GT_PRE = sum(1 for c in CARDS if c["metrics"]["post"]["enob"] > c["metrics"]["pre"]["enob"])
N_FULL_EQ_POST = sum(1 for c in CARDS if c["metrics"]["full"]["enob"] == c["metrics"]["post"]["enob"])
MAX_ENOB_20 = max(c["metrics"]["full"]["enob"] for c in CARDS if c["nbits"] == 20)
LOOP_ORDERS = ", ".join(f"{n} b: L={RES_SPECS[str(n)]['loop_order']}" for n in NBITS)

MODEL_NOTE = (
    "**How these numbers were produced.** ENOB, SNDR, SNR, SFDR, THD, DR, power and FoMs come from the "
    "generator's *analytical* modulator model (`evaluate_sdm_analytical`), fed with the PEX-extracted cap "
    "ratios, the sibling-library op-amp/comparator/switch metrics and (full view) the top-level routing "
    "parasitics. The ngspice transient runs on the compute farm supply only the integrator swings, the "
    "analog supply current and the first bitstream cycles. The PSD, DR sweep and DNL/INL curves are "
    "synthesized from the model metrics; PVT corners are the nominal full-chip value plus fixed per-corner "
    "offsets and small random noise; Monte Carlo ENOB samples are random draws clipped at ≥ target + 0.12 bit, "
    "so the 100 % yield holds by construction."
)
DATA_CAVEATS = (
    f"Data caveats: ENOB reaches {MAX_ENOB_20:.2f} b on the 20-bit cards (above the resolution target); "
    f"post-cap-PEX ENOB is higher than pre-layout in {N_POST_GT_PRE} of {len(CARDS)} cards and full-chip ENOB "
    f"equals post-cap-PEX in {N_FULL_EQ_POST}; architecture names say “2nd-order” but the loop order is "
    f"{LOOP_ORDERS}."
)
STAGE_NOTES = {
    "pre": "1. Pre-Layout: schematic netlists, nominal unit capacitor and ideal loop coefficients. Metrics from the "
           "analytical model; integrator swings and analog supply current from the ngspice transient.",
    "partial": "2. Post-Cap-PEX: Magic-extracted, ratio-trimmed SC capacitor-array macro (extracted C_u, a1, a2) and "
               "library-PEX op-amp metrics; switches/comparator schematic, no top-level routing parasitics. "
               "Model-based metrics as in pre-layout.",
    "full": "3. Full-Chip PEX: cap-array PEX + extracted sub-block subcircuits + top-level routing PEX; the SPICE "
            "deck carries a compact phase/DAC controller, the multi-bit sdm2bin output is reconstructed bit-exactly "
            "from the bitstream. 9-corner PVT and 100-run MC are model offsets / random draws around this view.",
}


def pvt_count(sim):
    corners = (sim.get("pvt") or {}).get("corners") or []
    return sum(1 for k in corners if k.get("pass")), len(corners)


def view_metrics(v, area):
    m, lin = v["metrics"], v.get("linearity") or {}
    nb = m.get("noise_budget_uv_rms") or {}
    return {
        "enob": m.get("enob"), "sndr": m.get("sndr_db"), "snr": m.get("snr_db"), "sfdr": m.get("sfdr_db"),
        "thd": m.get("thd_db"), "dr": m.get("dr_db"), "msa": m.get("msa_dbfs"), "ntf_slope": m.get("noise_slope_db_dec"),
        "power": mul(m.get("pwr_total_uw"), 1e-6), "p_analog": mul(m.get("pwr_analog_uw"), 1e-6),
        "p_digital": mul(m.get("pwr_digital_uw"), 1e-6), "fom_w": mul(m.get("fom_walden_fj"), 1e-15),
        "fom_s": m.get("fom_schreier_db"), "e_conv": mul(m.get("e_conv_pj"), 1e-12),
        "noise": mul(nb.get("total_inband_noise_uv"), 1e-6), "lsb": mul(nb.get("lsb_diff_uv"), 1e-6),
        "tau": mul(m.get("tau_settle_ns"), 1e-9), "settle_err": mul(m.get("v_settle_err_uv"), 1e-6),
        "swing1": m.get("vout1_swing_vpp"), "swing2": m.get("vout2_swing_vpp"),
        "idd": mul(m.get("spice_idd_analog_ua"), 1e-6), "cu_eff": mul(m.get("cu_eff_ff"), 1e-15),
        "a1_eff": m.get("a1_eff"), "a2_eff": m.get("a2_eff"), "beta1": m.get("beta1"), "beta2": m.get("beta2"),
        "dnl": lin.get("dnl_max_lsb"), "inl": lin.get("inl_max_lsb"), "area": area,
    }


METRICS = [
    # key, label, unit, si, better, digits
    ("enob", "ENOB", "bit", False, "high", 4),
    ("sndr", "SNDR", "dB", False, "high", 4),
    ("snr", "SNR", "dB", False, "high", 4),
    ("sfdr", "SFDR", "dB", False, "high", 4),
    ("thd", "THD", "dB", False, "low", 4),
    ("dr", "Dynamic range", "dB", False, "high", 4),
    ("msa", "Max stable amplitude", "dBFS", False, "high", 3),
    ("ntf_slope", "Out-of-band NTF slope", "dB/dec", False, None, 4),
    ("power", "Total power", "W", True, "low", 4),
    ("p_analog", "Analog power", "W", True, "low", 4),
    ("p_digital", "Digital (sdm2bin) power", "W", True, "low", 4),
    ("fom_w", "FoM Walden", "J/step", True, "low", 4),
    ("fom_s", "FoM Schreier", "dB", False, "high", 5),
    ("e_conv", "Energy per conversion", "J", True, "low", 4),
    ("noise", "In-band noise (input-referred)", "Vrms", True, "low", 3),
    ("lsb", "1 LSB (differential)", "V", True, None, 4),
    ("tau", "Stage-1 settling τ", "s", True, "low", 4),
    ("settle_err", "Incomplete-settling error", "V", True, "low", 3),
    ("swing1", "Integrator-1 swing (SPICE)", "Vpp", True, None, 4),
    ("swing2", "Integrator-2 swing (SPICE)", "Vpp", True, None, 4),
    ("idd", "Analog supply current (SPICE)", "A", True, "low", 4),
    ("cu_eff", "Effective unit cap C_u,eff", "F", True, None, 5),
    ("a1_eff", "Loop coefficient a1 = Cs1/Ci1", "", False, None, 5),
    ("a2_eff", "Loop coefficient a2", "", False, None, 5),
    ("beta1", "Stage-1 feedback factor β1", "", False, None, 4),
    ("beta2", "Stage-2 feedback factor β2", "", False, None, 4),
    ("dnl", "DNL max", "LSB", False, "low", 3),
    ("inl", "INL max", "LSB", False, "low", 3),
    ("pvt_min_enob", "Worst PVT ENOB", "bit", False, "high", 4),
    ("pvt_spread", "PVT ENOB spread", "bit", False, "low", 3),
    ("mc_enob", "MC ENOB mean", "bit", False, "high", 4),
    ("mc_enob_std", "MC ENOB σ", "bit", False, "low", 3),
    ("mc_p5", "MC ENOB P5", "bit", False, "high", 4),
    ("mc_yield", "MC yield", "%", False, "high", 4),
    ("area", "Layout area", "µm²", False, "low", 4),
]


# ============================================================================= detail-doc builders
def kpi_strip(card, v, sim, lay, st):
    m = v["metrics"]
    pvt, mc = sim["pvt"], sim["monte_carlo"]
    return {"type": "stats", "stage": st, "alt": "kpi", "items": [
        {"label": f"ENOB ({OLD_STAGE[st]})", "value": f"{fx(m['enob'])} bits"},
        {"label": "SNDR / SNR", "value": f"{fx(m['sndr_db'])} / {fx(m['snr_db'])} dB"},
        {"label": "SFDR / THD", "value": f"{fx(m['sfdr_db'])} / {fx(m['thd_db'])} dB"},
        {"label": "Dynamic range", "value": f"{fx(m['dr_db'])} dB"},
        {"label": "Total power", "value": f"{fx(m['pwr_total_uw'])} µW"},
        {"label": "Walden FoM", "value": f"{fx(m['fom_walden_fj'], 1)} fJ/step"},
        {"label": "Schreier FoM", "value": f"{fx(m['fom_schreier_db'])} dB"},
        {"label": "9-PVT min ENOB", "value": f"{fx(pvt['enob_min'])} bits", "sub": "full-chip view (model)"},
        {"label": "100-MC mean ± σ", "value": f"{fx(mc['enob_mean'])} ± {fx(mc['enob_std'])} b", "sub": "full-chip view (model)"},
        {"label": "Core footprint", "value": f"{fx(lay['width_um'], 0)} × {fx(lay['height_um'], 0)} µm"},
    ]}


def progression_table(d):
    V = d["sim"]["views"]
    mp, mq, mf = V["pre"]["metrics"], V["post"]["metrics"], V["full"]["metrics"]
    n, vdd = d["nbits"], d["vdd"]
    a1 = d["arch_spec"]["a1"]

    def three(k, dg, unit=""):
        u = f" {unit}" if unit else ""
        return [f"{fx(mp[k], dg)}{u}", f"{fx(mq[k], dg)}{u}", f"{fx(mf[k], dg)}{u}"]

    rows = [
        ["Effective Number of Bits (ENOB)", f"≥ {n}.00 bits", *three("enob", 2, "b"), f"{sgn(mf['enob'] - mp['enob'])} b"],
        ["In-Band SNDR", f"≥ {fx(n * 6.02 + 1.76, 1)} dB", *three("sndr_db", 2, "dB"), f"{sgn(mf['sndr_db'] - mp['sndr_db'])} dB"],
        ["In-Band SNR", "—", *three("snr_db", 2, "dB"), f"{sgn(mf['snr_db'] - mp['snr_db'])} dB"],
        ["Spurious-Free Dynamic Range (SFDR)", f"≥ {n * 6 + 12} dB", *three("sfdr_db", 2, "dB"), f"{sgn(mf['sfdr_db'] - mp['sfdr_db'])} dB"],
        ["Dynamic Range (DR)", f"≥ {n * 6 + 3} dB", *three("dr_db", 2, "dB"), f"{sgn(mf['dr_db'] - mp['dr_db'])} dB"],
        ["Out-of-Band NTF Slope", "-40.0 dB/dec", *three("noise_slope_db_dec", 2, "dB/dec"),
         sgn(mf["noise_slope_db_dec"] - mp["noise_slope_db_dec"])],
        ["Effective Unit Cap C<sub>u,eff</sub>", f"{fx(d['cap_spec']['cu_nom_ff'], 1)} fF", *three("cu_eff_ff", 2, "fF"),
         f"{sgn(mf['cu_eff_ff'] - mp['cu_eff_ff'])} fF"],
        ["Loop Coefficient a<sub>1</sub> = C<sub>s1</sub>/C<sub>i1</sub>", fx(a1, 4), *three("a1_eff", 5),
         f"{sgn((mf['a1_eff'] - mp['a1_eff']) * 100 / mp['a1_eff'], 3)}%"],
        ["Stage-1 Settling Time Constant τ<sub>settle</sub>", f"< {fx(mp['t_phi2_ns'] / 7, 1)} ns", *three("tau_settle_ns", 2, "ns"),
         f"{sgn(mf['tau_settle_ns'] - mp['tau_settle_ns'])} ns"],
        ["Incomplete Settling Error", "< 0.25 LSB", *three("v_settle_err_uv", 2, "µV"),
         f"{sgn(mf['v_settle_err_uv'] - mp['v_settle_err_uv'])} µV"],
        ["Integrator-1 / Integrator-2 Swing", f"< {fx(0.8 * vdd, 2)} Vpp",
         *[f"{fx(x['vout1_swing_vpp'], 3)} / {fx(x['vout2_swing_vpp'], 3)} V" for x in (mp, mq, mf)], "Bounded"],
        ["Total Power (Analog + sdm2bin)", "Low Power", *three("pwr_total_uw", 2, "µW"),
         f"{sgn(mf['pwr_total_uw'] - mp['pwr_total_uw'])} µW"],
        ["Walden FoM<sub>W</sub> / Schreier FoM<sub>S</sub>", "Best-in-Class",
         *[f"{fx(x['fom_walden_fj'], 1)} fJ / {fx(x['fom_schreier_db'], 1)} dB" for x in (mp, mq, mf)],
         f"{sgn(mf['fom_schreier_db'] - mp['fom_schreier_db'])} dB"],
    ]
    cols = [col("m", "Metric", type="text", md=True), col("t", "Target spec", type="text"),
            col("pre", "1. Pre-Layout", type="text"), col("post", "2. Post-Cap-PEX", type="text"),
            col("full", "3. Full-Chip PEX", type="text"), col("d", "Δ (Full − Pre)", type="text")]
    return table("3-Stage Physical Verification Progression (Pre vs Post-Cap-PEX vs Full-Chip PEX)", cols, rows,
                 search=False, csv=True,
                 caption="Direct comparison of schematic ideal caps, Magic-trimmed post-PEX capacitor macro, and "
                         "full-chip extracted routing + gate-level `sdm2bin` co-simulation. Target specs are the old "
                         "site's" + (f" (the −40 dB/dec slope target assumes L = 2; this card has L = {d['res_spec']['loop_order']})"
                                    if d['res_spec']['loop_order'] != 2 else "") + ". All three columns are analytical-model outputs "
                         "except the integrator swings (ngspice transient).")


def loop_param_table(d):
    V = d["sim"]["views"]
    ms = [V[x]["metrics"] for x in ("pre", "post", "full")]
    rows = []
    spec = [
        ("C<sub>u,eff</sub>", "cu_eff_ff", "fF", 3), ("C<sub>s1</sub>", "cs1_ff", "fF", 2), ("C<sub>i1</sub>", "ci1_ff", "fF", 2),
        ("C<sub>s2</sub>", "cs2_ff", "fF", 2), ("C<sub>i2</sub>", "ci2_ff", "fF", 2), ("a<sub>1,eff</sub>", "a1_eff", "", 5),
        ("a<sub>2,eff</sub>", "a2_eff", "", 5), ("β<sub>1</sub>", "beta1", "", 4), ("β<sub>2</sub>", "beta2", "", 4),
        ("τ<sub>settle</sub>", "tau_settle_ns", "ns", 3), ("t<sub>φ2</sub>", "t_phi2_ns", "ns", 2),
        ("Settling error", "v_settle_err_uv", "µV", 3), ("Max stable amplitude", "msa_dbfs", "dBFS", 1),
        ("THD", "thd_db", "dB", 2), ("Analog power", "pwr_analog_uw", "µW", 2), ("Digital power", "pwr_digital_uw", "µW", 2),
        ("Energy / conversion", "e_conv_pj", "pJ", 1), ("Analog supply current (SPICE)", "spice_idd_analog_ua", "µA", 2),
        ("SPICE transient OK", "spice_tran_ok", "", 0),
    ]
    for lab, k, u, dg in spec:
        vals = []
        for m in ms:
            v = m.get(k)
            vals.append(("✓" if v else "✗") if isinstance(v, bool) else f"{fx(v, dg)}{(' ' + u) if u else ''}")
        rows.append([lab, *vals])
    for lab, k in (("Cap bank multiplier", "cap_bank_mult"), ("CDS chopper", "cds_chopper"), ("DWA order", "dwa_order")):
        rows.append([lab, *[str(m.get(k)) for m in ms]])
    cols = [col("p", "Parameter", type="text", md=True), col("pre", "1. Pre-Layout", type="text"),
            col("post", "2. Post-Cap-PEX", type="text"), col("full", "3. Full-Chip PEX", type="text")]
    return table("Loop parameters by verification stage", cols, rows, search=False,
                 caption="Per-view model inputs/outputs from `sim.json` (not tabulated on the old site).")


NOISE_ITEMS = [("kT/C switched-capacitor sampling noise", "ktc_sampling_uv", "#38bdf8"),
               ("Stage-1 & Stage-2 op-amp thermal + 1/f noise", "opamp_thermal_1f_uv", "#818cf8"),
               ("Shaped quantization noise", "quantization_ideal_uv", "#34d399"),
               ("Finite op-amp DC gain NTF leakage", "finite_gain_leakage_uv", "#fbbf24"),
               ("Quantizer comparator input noise", "comparator_noise_uv", "#c084fc"),
               ("Incomplete integrator settling error", "settling_error_uv", "#fb7185")]
POWER_ITEMS = [("Stage-1 low-noise integrator op-amp", "opa_stage1", "#38bdf8"),
               ("Stage-2 loop-filter integrator op-amp", "opa_stage2", "#818cf8"),
               ("Active reference/VCM buffer op-amp", "opa_vcm", "#c084fc"),
               ("Dynamic regenerative quantizer comparator(s)", "quantizer_comp", "#34d399"),
               ("SC array & reference switching", "sc_switches_ref", "#fbbf24"),
               ("OpenROAD sdm2bin digital decimator", "sdm_to_binary_dig", "#fb7185")]


def noise_power_charts(v, st):
    m = v["metrics"]
    nb, pb = m["noise_budget_uv_rms"], m["power_breakdown_uw"]
    tot_n, tot_p = max(nb["total_inband_noise_uv"], 1e-3), max(m["pwr_total_uw"], 1e-3)
    nl = [x[0] for x in NOISE_ITEMS] + ["Total in-band noise (RSS)"]
    nv = [nb.get(x[1], 0.0) for x in NOISE_ITEMS] + [nb["total_inband_noise_uv"]]
    nc = [x[2] for x in NOISE_ITEMS] + ["#64748b"]
    pl = [x[0] for x in POWER_ITEMS]
    pv = [pb.get(x[1], 0.0) for x in POWER_ITEMS]
    pc = [x[2] for x in POWER_ITEMS]
    lay = lambda xt: {"margin": {"l": 10, "r": 30, "t": 10, "b": 45}, "showlegend": False,
                      "yaxis": {"autorange": "reversed", "automargin": True}, "xaxis": axis(xt)}
    return [
        chart(f"Input-referred in-band noise budget (total = {fx(nb['total_inband_noise_uv'])} µV<sub>rms</sub> vs 1 LSB = {fx(nb['lsb_diff_uv'], 1)} µV)",
              [{"type": "bar", "orientation": "h", "y": nl, "x": nv, "marker": {"color": nc},
                "text": [f"{fx(x)} µVrms ({fx(100 * x / tot_n, 1)} %)" for x in nv], "textposition": "auto",
                "hovertemplate": "%{y}: %{x:.3g} µVrms<extra></extra>"}], lay("µV rms"),
              stage=st, alt="noise", height=300,
              caption="Input-referred RMS noise contributions across the passband f<sub>B</sub> (model budget). "
                      "Percentages are value / total as on the old site; contributions add in RSS."),
        chart(f"Total power dissipation breakdown (total = {fx(m['pwr_total_uw'])} µW)",
              [{"type": "bar", "orientation": "h", "y": pl, "x": pv, "marker": {"color": pc},
                "text": [f"{fx(x)} µW ({fx(100 * x / tot_p, 1)} %)" for x in pv], "textposition": "auto",
                "hovertemplate": "%{y}: %{x:.4g} µW<extra></extra>"}], lay("µW"),
              stage=st, alt="power", height=300,
              caption="Static/dynamic power breakdown across analog & digital blocks (model)."),
    ]


def component_tables(d):
    co, sc = d["components"], d.get("selection_candidates") or {}
    o1, o2, ov, cp, si, ss = co["opa1"], co["opa2"], co.get("opa_vcm"), co["comp"], co["sw_in"], co["sw_sc"]
    cc = next((x for x in sc.get("comp", []) if x["key"] == cp["key"]), {})

    def opa_desc(o):
        mp = o.get("m_pex") or o.get("m") or {}
        return (f"{o['arch_title']} · `gm/Id {o['gmid_target']} → {fx(o['gmid_sim'])} V⁻¹` ({o['inversion']}) · "
                f"A<sub>0,PEX</sub> = {fx(mp.get('a0_db'), 1)} dB · UGB = {fx(mul(mp.get('ugb_hz'), 1e-6))} MHz · "
                f"PM = {fx(mp.get('pm_deg'), 1)}° · P = {fx(mp.get('power_uw'), 2)} µW · area {fx(o.get('area_um2'), 0)} µm²")

    ins = cp.get("insitu") or {}
    rows = [["Stage-1 integrator op-amp (`../opa-gen-gemini4`)", opa_link(o1["key"]), opa_desc(o1)],
            ["Stage-2 integrator op-amp (`../opa-gen-gemini4`)", opa_link(o2["key"]), opa_desc(o2)]]
    if ov:
        rows.append(["Active VCM buffer op-amp (`../opa-gen-gemini4`)", opa_link(ov["key"]), opa_desc(ov)])
    rows.append(["Quantizer comparator (`../sa-gen-gemini4`, in-situ characterization via `../sar-gen-gemini4`)",
                 sa_link(cp["key"]),
                 f"{cp['arch'].upper()} ({cp['mix']}) clocked comparator · `gm/Id {cp['gmid_target']} V⁻¹` · "
                 f"in-situ delay = {fx(mul(ins.get('delay_nom_s'), 1e9))} ns · kickback = {fx(cc.get('kickback_mv'))} mV · "
                 f"σ<sub>n</sub> = {fx(cc.get('sigma_noise_uv'), 0)} µV · IDD band {cp.get('idd_band')}"])
    rows.append(["Input & SC switches (`../switch-gen-gemini4`)", f"{sw_link(si['key'])} + {sw_link(ss['key'])}",
                 f"Input: `{si['topo']}` {si.get('short', '')} (R<sub>on,wc</sub> = {fx(si['m'].get('ron_wc'), 1)} Ω, "
                 f"THD = {fx(si['m'].get('thd_db'), 1)} dB) · Summing: `{ss['topo']}` {ss.get('short', '')} "
                 f"(R<sub>on,wc</sub> = {fx(ss['m'].get('ron_wc'), 1)} Ω, |Q|<sub>max</sub> = {fx(mul(ss['m'].get('q_absmax'), 1e15), 2)} fC)"])
    sel = table("Systematic Component Selection from Sibling GF180 Libraries",
                [col("role", "Role", type="text", md=True), col("key", "Library key (hub page)", type="text", md=True),
                 col("d", "Selected design", type="text", md=True)], rows, search=False,
                caption="Multi-objective Pareto selection across **288 Op-Amps** (`../opa-gen-gemini4`), **96 Comparators** "
                        "(`../sa-gen-gemini4` + `../sar-gen-gemini4`), and **125 Switches** (`../switch-gen-gemini4`) to "
                        "satisfy loop settling, thermal noise, slew rate, and low-power targets. Keys link to the reused "
                        "block's page on the hub. The old site printed “—” for the comparator delay/kickback/σ<sub>n</sub> "
                        "and the switch R<sub>on</sub>/Q<sub>inj</sub> (field-name mismatch); the values here come from the "
                        "component record and the comparator candidate list.")

    def opa_rows(role, lst, comp):
        out = []
        for i, c in enumerate(lst):
            chosen = comp is not None and c["key"] == comp["key"]
            out.append({"role": role, "rank": i + 1, "sel": chosen, "key": opa_link(c["key"]), "arch": c.get("arch"),
                        "load": c.get("load_tag"), "cls": c.get("iclass"),
                        "gmid": f"{comp['gmid_target']} → {fx(comp['gmid_sim'], 1)}" if chosen else "—",
                        "a0": c.get("a0_db"), "ugb": mul(c.get("ugb_mhz"), 1e6), "pm": c.get("pm_deg"),
                        "ts": mul(c.get("ts_1pct_ns"), 1e-9), "p": mul(c.get("power_uw"), 1e-6),
                        "vn": mul(c.get("vn_rms_uv"), 1e-6), "vos": mul(c.get("vos_sigma_mv"), 1e-3),
                        "sw": c.get("swing_v"), "score": c.get("score"), "_s": "good" if chosen else None})
        return out

    orows = opa_rows("Stage-1 OPA", sc.get("opa1", []), o1) + opa_rows("Stage-2 OPA", sc.get("opa2", []), o2) + \
        opa_rows("VCM OPA", sc.get("opa_vcm", []), ov)
    for r in orows:
        if r["_s"] is None:
            del r["_s"]
    opa_t = table("Stage-1 & Stage-2 Op-Amp Candidate Ranking (Top Candidates)",
                  [col("role", "Role", type="text"), col("rank", "Rank", digits=0), col("sel", "Selected", type="status"),
                   col("key", "Library key", type="text", md=True), col("arch", "Topology", type="text"),
                   col("load", "Load", type="text"), col("cls", "Current class", type="text"),
                   col("gmid", "gm/I<sub>D</sub> target → sim (V⁻¹)", type="text"),
                   col("a0", "A<sub>0,PEX</sub>", unit="dB", digits=4), col("ugb", "UGB<sub>PEX</sub>", unit="Hz", si=True),
                   col("pm", "PM", unit="°", digits=3), col("ts", "t<sub>s,1%</sub>", unit="s", si=True),
                   col("p", "Power", unit="W", si=True), col("vn", "v<sub>n,rms</sub>", unit="V", si=True),
                   col("vos", "V<sub>os</sub> σ", unit="V", si=True), col("sw", "Swing", unit="V", digits=3),
                   col("score", "Score (lower = better)", digits=4)], orows, search=False,
                  caption="All ranked candidates stored in `data.json` (the old site showed the top 4 of Stage-1/Stage-2; "
                          "VCM-buffer candidates were not shown). The old site repeated the selected op-amp's gm/I<sub>D</sub> "
                          "on every row; here it is shown only for the selected design.")
    crow = []
    for i, c in enumerate(sc.get("comp", [])):
        chosen = c["key"] == cp["key"]
        r = {"blk": "Quantizer SA", "rank": i + 1, "sel": chosen, "key": sa_link(c["key"]),
             "topo": f"{c['arch'].upper()} ({c['mix']})", "size": f"{cp['gmid_target']} V⁻¹ ({c.get('idd_band')})" if chosen else c.get("idd_band"),
             "m1": f"t<sub>d</sub> = {fx(c.get('delay_insitu_ns'))} ns (1 mV: {fx(c.get('delay_1mv_ns'))} ns)",
             "m2": f"σ<sub>n</sub> = {fx(c.get('sigma_noise_uv'), 0)} µV", "m3": f"KB = {fx(c.get('kickback_mv'))} mV",
             "m4": f"E = {fx(c.get('e_decision_fj'), 0)} fJ/decision · walk {fx(c.get('trip_walk_mv'))} mV", "score": c.get("score")}
        if chosen:
            r["_s"] = "good"
        crow.append(r)
    for i, c in enumerate(sc.get("switches", [])):
        chosen = c["key"] in (si["key"], ss["key"])
        r = {"blk": "Input switch" if c.get("role") == "input_boot" else "SC switch", "rank": i + 1, "sel": chosen,
             "key": sw_link(c["key"]), "topo": c.get("topo"), "size": c.get("iclass"),
             "m1": f"R<sub>on</sub> = {fx(c.get('ron_wc_ohm'), 0)} Ω", "m2": f"THD = {fx(c.get('thd_db'), 1)} dB",
             "m3": f"Q<sub>inj</sub> = {fx(c.get('q_inj_fc'))} fC", "m4": f"E<sub>VDD</sub> = {fx(c.get('e_vdd_fj'), 1)} fJ",
             "score": c.get("score")}
        if chosen:
            r["_s"] = "good"
        crow.append(r)
    cs_t = table("Quantizer Comparator & Sampling Switch Candidate Ranking",
                 [col("blk", "Block", type="text"), col("rank", "Rank", digits=0), col("sel", "Selected", type="status"),
                  col("key", "Library key", type="text", md=True), col("topo", "Topology", type="text"),
                  col("size", "gm/I<sub>D</sub> or size", type="text"), col("m1", "Key metric 1", type="text", md=True),
                  col("m2", "Key metric 2", type="text", md=True), col("m3", "Key metric 3", type="text", md=True),
                  col("m4", "Extra", type="text", md=True), col("score", "Score (lower = better)", digits=4)], crow, search=False,
                 caption="All comparator and switch candidates in `data.json` (old site: top 4 each). The switch "
                         "Q<sub>inj</sub> column is a constant 10 fC in the candidate list.")
    return sel, opa_t, cs_t


def gmid_table(d):
    co = d["components"]
    rows = []
    for role, k in (("Stage-1 op-amp", "opa1"), ("Stage-2 op-amp", "opa2"), ("VCM buffer op-amp", "opa_vcm")):
        o = co.get(k)
        if not o:
            continue
        rows.append([f"{role} gm/I<sub>D</sub> annotation", opa_link(o["key"]), f"{o['gmid_target']}", fx(o["gmid_sim"]),
                     "—", f"{o['inversion']} inversion", f"I<sub>ref</sub> = {fx(o['iref_ua'], 4)} µA", o.get("arch_title", "")])
    cp = co["comp"]
    rows.append(["Quantizer latch gm/I<sub>D</sub> annotation", sa_link(cp["key"]), f"{cp['gmid_target']}",
                 fx((cp.get("gmid_sim") or {}).get("n")), fx((cp.get("gmid_sim_pex") or {}).get("n")),
                 f"{cp.get('idd_band')}", f"{cp['arch'].upper()} dynamic latch, reset {cp.get('reset_out')}", cp.get("subckt", "")])
    si, ss = co["sw_in"], co["sw_sc"]
    rows.append(["SC sampling & summing switches", f"{sw_link(si['key'])} / {sw_link(ss['key'])}", "—", "—", "—",
                 f"{si['iclass']} / {ss['iclass']}", f"Input: `{si['topo']}` · Summing: `{ss['topo']}`",
                 f"{si.get('name', '')}; {ss.get('name', '')}"])
    return table("gm/I<sub>D</sub> annotation summary (targets & simulated operating points)",
                 [col("b", "Block", type="text", md=True), col("k", "Library key", type="text", md=True),
                  col("t", "gm/I<sub>D</sub> target (V⁻¹)", type="text"), col("s", "Simulated (V⁻¹)", type="text"),
                  col("sp", "Simulated, PEX (V⁻¹)", type="text"), col("inv", "Regime / class", type="text"),
                  col("x", "Bias / topology", type="text", md=True), col("n", "Design", type="text")], rows, search=False,
                 caption="Old site: “Target → Post-PEX Simulated”. The op-amp records carry a single `gmid_sim` value "
                         "(equal to the target for all cards); the comparator carries schematic and PEX values.")


def schematic_gallery(cid, d):
    base = f"designs/{cid}"
    items = []
    for lab, f, need in (("Top-level ΣΔ ADC + sdm2bin", "schematic.svg", True), ("Stage-1 op-amp", "opa1_schematic.svg", True),
                         ("Stage-2 op-amp", "opa2_schematic.svg", True), ("VCM op-amp", "opa_vcm_schematic.svg", bool(d["components"].get("opa_vcm"))),
                         ("Quantizer SA comp", "comp_schematic.svg", True), ("Sampling switch", "sw_in_schematic.svg", True),
                         ("Digital sdm2bin decimator", "dig_schematic.svg", True)):
        if need and exists(f"{base}/{f}"):
            items.append({"label": lab, "src": f"{base}/{f}"})
    return {"type": "gallery", "title": "Annotated schematic hierarchy (with gm/I<sub>D</sub> targets & simulated operating points)",
            "items": items, "bg": "dark", "max_height": 760,
            "caption": "Select between the top-level 2nd-order switched-capacitor ΣΔ modulator + `sdm2bin` schematic and "
                       "transistor-level schematics of each reused building block (click to open the SVG full size)."}


def chart_psd(v, st, nbits):
    fft, m = v["fft"], v["metrics"]
    f = [x * 1e3 for x in fft["freqs_khz"]]
    p = fft["psd_db"]
    if not f:
        return None
    fb = fft["fb_khz"] * 1e3
    ymin = -175 if min(p) < -130 else -135
    ipk = max(range(len(p)), key=lambda i: p[i])
    data = [
        {"type": "scatter", "mode": "lines", "x": [f[0], fb, fb, f[0]], "y": [ymin, ymin, 0, 0], "fill": "toself",
         "fillcolor": "rgba(52,211,153,0.13)", "line": {"width": 0}, "name": "Passband 0…f<sub>B</sub>", "hoverinfo": "skip"},
        {"type": "scatter", "mode": "lines", "x": f, "y": p, "name": "Bitstream PSD", "line": {"width": 1.2, "color": "#0ea5e9"},
         "hovertemplate": "%{x:.4s}Hz: %{y:.1f} dBFS<extra></extra>"},
        {"type": "scatter", "mode": "lines", "x": [fb, fb], "y": [ymin, 0], "name": f"f<sub>B</sub> = {fft['fb_khz']} kHz",
         "line": {"dash": "dash", "color": "#16a34a", "width": 1.5}, "hoverinfo": "skip"},
        {"type": "scatter", "mode": "markers+text", "x": [f[ipk]], "y": [p[ipk]], "name": "Fundamental",
         "text": [f"  f<sub>in</sub> = {fx(fft['freqs_khz'][ipk])} kHz ({fx(p[ipk], 1)} dBFS)"], "textposition": "middle right",
         "marker": {"size": 9, "color": "#f59e0b"}},
    ]
    return chart("1. Oversampled bitstream PSD & noise shaping", data,
                 {"xaxis": axis("Frequency (Hz, log scale)", type="log"), "yaxis": axis("PSD (dBFS)", range=[ymin, 8])},
                 stage=st, alt="psd", height=340,
                 caption=f"ENOB = {fx(m['enob'])} b · SNDR = {fx(m['sndr_db'])} dB · SFDR = {fx(m['sfdr_db'])} dB · "
                         f"slope = {fx(fft['noise_slope_db_dec'], 1)} dB/dec (+{20 * int(v['metrics'].get('loop_order', 2))} dB/dec NTF shaping above the passband for L = {v['metrics'].get('loop_order')}). "
                         "*Synthesized spectrum: model noise floor + L-th order NTF shape + Gaussian ripple, with tones placed at the "
                         "model SFDR — not an FFT of the SPICE bitstream.*")


def chart_wave(v, st, nbits, fs_hz):
    w, m = v["waveforms"], v["metrics"]
    t = w.get("time_us") or []
    if not t:
        return None
    ts_us = 1e6 / fs_hz
    tw = [round(i * ts_us, 4) for i in w.get("dout_cycle_indices") or []]
    data = [
        {"type": "scatter", "mode": "lines", "x": t, "y": w["vin_diff_v"], "name": "V<sub>in,diff</sub>", "line": {"color": "#34d399", "width": 2}},
        {"type": "scatter", "mode": "lines", "x": t, "y": w["vout1_diff_v"], "name": "V<sub>out1,diff</sub>", "line": {"color": "#38bdf8", "width": 1.2}},
        {"type": "scatter", "mode": "lines", "x": t, "y": w["vout2_diff_v"], "name": "V<sub>out2,diff</sub>", "line": {"color": "#818cf8", "width": 1.1}},
        {"type": "scatter", "mode": "lines", "x": t, "y": w["dout_trace"], "yaxis": "y2", "line": {"shape": "hv", "color": "#f59e0b", "width": 2},
         "name": f"sdm2bin dout[{nbits - 1}:0]"},
    ]
    if tw:
        data.append({"type": "scatter", "mode": "markers", "x": tw, "y": w.get("dout_words"), "yaxis": "y2", "name": "dout_valid word",
                     "marker": {"symbol": "diamond", "size": 8, "color": "#f59e0b", "line": {"width": 1, "color": "#78350f"}}})
    return chart("2. Transient integrator waveforms & sdm2bin binary output", data,
                 {"xaxis": axis("Time (µs)"), "yaxis": axis("Differential voltage (V)"),
                  "yaxis2": {"title": {"text": f"dout code (0…{2 ** nbits - 1})"}, "overlaying": "y", "side": "right",
                             "range": [0, 2 ** nbits - 1], "showgrid": False}},
                 stage=st, alt="wave", height=340,
                 caption=f"V<sub>out1</sub> = {fx(m['vout1_swing_vpp'])} Vpp · V<sub>out2</sub> = {fx(m['vout2_swing_vpp'])} Vpp · "
                         f"{len(w.get('dout_words') or [])} decimated words. Bounded integrator swings & decimated binary output. "
                         "*The ngspice transient covers the first bitstream cycles; the trace is continued with a discrete-time "
                         "behavioral loop to 8 OSR frames, and dout is the bit-exact sdm2bin RTL model applied to that bitstream.*")


def chart_dr(v, st):
    dr = v["dr_sweep"]
    a = dr.get("amps_dbfs") or []
    if not a:
        return None
    lo = min(min(dr["snr_db"]), min(dr["sndr_db"]))
    hi = max(max(dr["snr_db"]), max(dr["sndr_db"]))
    data = [
        {"type": "scatter", "mode": "lines+markers", "x": a, "y": dr["snr_db"], "name": "SNR (dB)", "line": {"color": "#38bdf8", "width": 2}},
        {"type": "scatter", "mode": "lines+markers", "x": a, "y": dr["sndr_db"], "name": "SNDR (dB)", "line": {"color": "#34d399", "width": 2}},
        {"type": "scatter", "mode": "lines", "x": [dr["msa_dbfs"], dr["msa_dbfs"]], "y": [lo, hi], "name": f"MSA = {fx(dr['msa_dbfs'], 1)} dBFS",
         "line": {"dash": "dot", "color": "#f43f5e"}, "hoverinfo": "skip"},
    ]
    return chart("3. Dynamic range (DR) sweep: SNR & SNDR vs input amplitude", data,
                 {"xaxis": axis("Input amplitude (dBFS)"), "yaxis": axis("dB")}, stage=st, alt="dr", height=320,
                 caption=f"DR = {fx(dr['dr_db'])} dB · peak SNDR = {fx(dr['peak_sndr_db'])} dB · MSA = {fx(dr['msa_dbfs'], 1)} dBFS. "
                         "*Analytical curve (SNR shifted by amplitude, SNDR with a harmonic-growth/overload penalty).*")


def chart_lin(v, st):
    lin = v["linearity"]
    if not lin.get("codes"):
        return None
    data = [{"type": "scatter", "mode": "lines", "x": lin["codes"], "y": lin["dnl_lsb"], "name": f"DNL (max {fx(lin['dnl_max_lsb'], 3)} LSB)",
             "line": {"color": "#38bdf8", "width": 1.4}},
            {"type": "scatter", "mode": "lines", "x": lin["codes"], "y": lin["inl_lsb"], "name": f"INL (max {fx(lin['inl_max_lsb'], 3)} LSB)",
             "line": {"color": "#f59e0b", "width": 1.8}}]
    return chart("4. Static linearity: endpoint-fit DNL & INL profiles (LSB)", data,
                 {"xaxis": axis(f"Decimated binary output code (0 … {lin['codes'][-1]})"), "yaxis": axis("LSB")},
                 stage=st, alt="lin", height=320,
                 caption=f"Max |DNL| = {fx(lin['dnl_max_lsb'], 3)} LSB · max |INL| = {fx(lin['inl_max_lsb'], 3)} LSB. "
                         "*Synthesized 64-point profile (amplitude from the cap-ratio error and THD; random ripple).*")


def chart_dc(v, st):
    lin = v["linearity"]
    if not lin.get("dc_vin_v"):
        return None
    data = [{"type": "scatter", "mode": "lines", "x": lin["dc_vin_v"], "y": lin["dc_code_ideal"], "name": "Ideal code", "line": {"dash": "dash", "color": "#64748b"}},
            {"type": "scatter", "mode": "markers+lines", "x": lin["dc_vin_v"], "y": lin["dc_code_sim"], "name": "Model code", "line": {"color": "#0ea5e9"}, "marker": {"size": 4}}]
    return chart("DC transfer curve (decimated code vs differential input)", data,
                 {"xaxis": axis("V<sub>in,diff</sub> (V)"), "yaxis": axis("Output code")}, stage=st, alt="dc", height=320,
                 caption=f"Offset = {fx(lin.get('offset_mv'), 3)} mV · gain error = {fx(lin.get('gain_err_pct'), 4)} %. "
                         "In `sim.json` but not plotted on the old site; model-generated.")


def chart_phase(v, st, vdd):
    w = v["waveforms"]
    v1 = w.get("vout1_traj_v") or w.get("vout1_diff_v") or []
    v2 = w.get("vout2_traj_v") or w.get("vout2_diff_v") or []
    if not v1:
        return None
    s, lim = 0.58 * vdd, 0.75 * vdd
    data = [{"type": "scatter", "mode": "lines", "x": [-s, s, s, -s, -s], "y": [-s, -s, s, s, -s], "name": "Linear op-amp output swing limit (±0.58·V<sub>DD</sub>)",
             "line": {"dash": "dash", "color": "#16a34a"}, "hoverinfo": "skip"},
            {"type": "scatter", "mode": "lines", "x": v1, "y": v2, "name": "Integrator trajectory", "line": {"color": "rgba(14,165,233,0.6)", "width": 1.1}}]
    return chart("5. Integrator state-space phase portrait (V<sub>out1,diff</sub> vs V<sub>out2,diff</sub>)", data,
                 {"xaxis": axis("Stage-1 V<sub>out1,diff</sub> (V)", range=[-lim, lim]), "yaxis": axis("Stage-2 V<sub>out2,diff</sub> (V)", range=[-lim, lim])},
                 stage=st, alt="phase", height=320,
                 caption="Old site: “Bounded 2nd-Order Attractor · Zero Integrator Clipping”. Dashed box = linear op-amp output swing "
                         "limit. Trajectory = SPICE transient continued by the behavioral loop (see chart 2); points outside the box "
                         "are visible as such.")


def chart_mc(mc, nbits):
    counts, edges = mc.get("hist_counts") or [], mc.get("hist_edges") or []
    if not counts or len(edges) != len(counts) + 1:
        return None
    ctr = [(edges[i] + edges[i + 1]) / 2 for i in range(len(counts))]
    wid = [edges[i + 1] - edges[i] for i in range(len(counts))]
    top = max(counts) * 1.1
    data = [{"type": "bar", "x": ctr, "y": counts, "width": wid, "name": "Runs", "marker": {"color": "rgba(14,165,233,0.65)", "line": {"color": "#0284c7", "width": 1}}},
            {"type": "scatter", "mode": "lines", "x": [mc["enob_mean"]] * 2, "y": [0, top], "name": f"mean {fx(mc['enob_mean'], 3)} b", "line": {"dash": "dash", "color": "#16a34a"}},
            {"type": "scatter", "mode": "lines", "x": [mc["enob_p5"]] * 2, "y": [0, top], "name": f"P5 {fx(mc['enob_p5'], 3)} b", "line": {"dash": "dot", "color": "#f59e0b"}}]
    return chart("6. 100-run Monte Carlo mismatch & thermal noise ENOB histogram", data,
                 {"xaxis": axis(f"ENOB (bits) — distribution {fx(edges[0])} b … {fx(edges[-1])} b"), "yaxis": axis("Runs"), "bargap": 0.05},
                 stage="full", alt="mc", height=320,
                 caption=f"Mean = {fx(mc['enob_mean'])} b · σ = {fx(mc['enob_std'], 3)} b · P5 = {fx(mc['enob_p5'])} b · yield = {fx(mc['yield_pct'], 0)} % "
                         f"(target spec ≥ {nbits}.0 b; {round(mc['n_runs'] * mc['yield_pct'] / 100)}/{mc['n_runs']} runs pass). "
                         "*Model draws: nominal − 0.04 + N(0, σ), clipped to [target + 0.12, nominal + 0.22] b — the yield is 100 % by construction.*")


def sim_section(cid, d):
    sim = d["sim"]
    V, n, vdd = sim["views"], d["nbits"], d["vdd"]
    fs_hz = d["res_spec"]["fs_hz"]
    blocks = []
    for st in STAGES:
        v = V[VIEW_OF[st]]
        for b in (chart_psd(v, st, n), chart_wave(v, st, n, fs_hz), chart_dr(v, st), chart_lin(v, st), chart_phase(v, st, vdd)):
            if b:
                blocks.append(b)
    mc, pvt = sim["monte_carlo"], sim["pvt"]
    if (b := chart_mc(mc, n)):
        blocks.append(b)
    for st in STAGES:
        if (b := chart_dc(V[VIEW_OF[st]], st)):
            blocks.append(b)
    blocks.append(kv("Monte Carlo summary (100 runs)", [
        ["Runs", mc["n_runs"]], ["Yield (ENOB ≥ target)", f"{fx(mc['yield_pct'], 1)} %"],
        ["ENOB mean ± σ", f"{fx(mc['enob_mean'], 3)} ± {fx(mc['enob_std'], 3)} b"], ["ENOB P5 / min / max", f"{fx(mc['enob_p5'], 3)} / {fx(mc['enob_min'], 3)} / {fx(mc['enob_max'], 3)} b"],
        ["SNDR mean ± σ", f"{fx(mc['sndr_mean_db'])} ± {fx(mc['sndr_std_db'])} dB"], ["Offset σ", f"{fx(mc['offset_std_mv'], 3)} mV"],
        ["Cap mismatch σ(ΔC/C)", f"{fx(mc['cap_mismatch_sigma_pct'], 4)} %"]], cols=2, stage="full", alt="mcsum"))
    blocks = [{"type": "section", "title": "Multi-Testbench Simulation Suite", "cols": 2, "blocks": blocks,
               "intro": "Coherent FFT spectrum & noise shaping, transient integrator & `sdm2bin` binary output waveforms, Dynamic "
                        "Range (DR) sweep, static DC linearity (DNL/INL), state-space phase portrait, 9-corner PVT resilience, and "
                        "100-run Monte Carlo mismatch analysis. The hub's **Simulation stage** option replaces the old local "
                        "Pre-Layout / Post-Cap-PEX / Full-Chip PEX switch; PVT and MC exist for the full-chip view only."}]
    rows = []
    for r in pvt.get("corners") or []:
        rows.append([r["corner"], r["process"], r["vdd_v"], r["temp_c"], r["enob"], r["sndr_db"], r["sfdr_db"],
                     mul(r["pwr_total_uw"], 1e-6), mul(r["settling_err_uv"], 1e-6), r.get("spice_ok"),
                     {"v": "PASS" if r["pass"] else "MARGINAL", "s": "good" if r["pass"] else "warn"}])
    blocks.append(table("9-Corner PVT Variation Resilience (Process × ±5% V<sub>DD</sub> × −40 °C..125 °C)",
                        [col("c", "Corner", type="text"), col("p", "Process", type="text"), col("vdd", "V<sub>DD</sub>", unit="V", digits=3),
                         col("t", "Temp", unit="°C", digits=3), col("e", "ENOB", unit="bit", digits=4), col("s", "SNDR", unit="dB", digits=5),
                         col("f", "SFDR", unit="dB", digits=5), col("pw", "Power", unit="W", si=True, digits=5),
                         col("se", "Settle err", unit="V", si=True), col("ok", "SPICE deck OK", type="status"), col("st", "Status", type="text")],
                        rows, stage="full", alt="pvt", search=False, vdd_filter=False,
                        caption="Verified across TT, FF, SS, FS, SF corners with full-chip extracted parasitics on the compute farm "
                                "(old-site text). *Corner values = nominal full-chip model ENOB + fixed per-corner offset + N(0, 0.015) b; "
                                "SNDR = 6.02·ENOB + 1.76; power and settling scaled by fixed factors. The SPICE corner flag defaults "
                                "to ✓ when no corner run was found.*"))
    blocks.append(kv("PVT summary", [["Corners", pvt["n_corners"]], ["All pass (ENOB ≥ target)", pvt["all_pass"]],
                                     ["Nominal ENOB", f"{fx(pvt['enob_nom'])} b"], ["Min / max ENOB", f"{fx(pvt['enob_min'])} / {fx(pvt['enob_max'])} b"],
                                     ["Spread", f"{fx(pvt['enob_spread'])} b"], ["Worst corner", pvt["worst_corner"]]], cols=3, stage="full", alt="pvtsum"))
    cs = sim.get("cosim") or {}
    fv = cs.get("frame_verification") or {}
    blocks.append(section("Gate-Level sdm2bin Digital Decimator Co-Simulation", [
        kv(None, [["Digital macro", f"[{cs.get('dig_macro')}](#/sdm?page=macros)"], ["Library", f"`{cs.get('stdcell_library')}`"],
                  ["Synthesized / routed active cells", f"{cs.get('synth_cells')} synth / {cs.get('routed_active_cells')} active"],
                  ["Total physical cells (with fill/decap)", cs.get("total_physical_cells")],
                  ["STA setup slack", f"+{fx(cs.get('setup_slack_ns'))} ns"], ["Digital power", f"{fx(cs.get('digital_power_uw'))} µW"],
                  ["Wirelength / utilization", f"{fx(cs.get('wirelength_um'), 0)} µm / {fx(cs.get('utilization_pct'), 0)} %"],
                  ["DRC / LVS", f"{'DRC = 0' if cs.get('drc_clean') else 'DRC ✗'} / {'LVS match' if cs.get('lvs_match') else 'LVS ✗'}"],
                  ["Gate-level bit-exactness", f"{'100% bit-exact' if cs.get('cosim_bit_exact') else '✗'} ({cs.get('max_code_diff_lsb')} LSB max diff)"]], cols=3),
        table("Frame verification (sim_verify of the macro)",
              [col("f", "Input duty", type="text"), col("c", "Code", digits=0), col("e", "Expected", type="text")],
              [["0 %", fv.get("code_0pct"), "0"], ["25 %", fv.get("code_25pct"), "≈ ¼ full scale"],
               ["50 % (even frame)", fv.get("code_50pct_even"), str(fv.get("expected_mid"))],
               ["50 % (odd frame)", fv.get("code_50pct_odd"), str(fv.get("expected_mid"))],
               ["75 %", fv.get("code_75pct"), "≈ ¾ full scale"], ["100 %", fv.get("code_100pct"), str(fv.get("expected_max"))]],
              search=False, csv=False, caption=f"Overall: {'PASS' if fv.get('pass') else 'FAIL'}."),
    ] + [table(f"Sample decoded binary output words dout[{n - 1}:0] from sdm2bin",
               [col("i", "Frame", digits=0), col("c", "Cycle index", digits=0), col("d", "dout (decimal)", digits=0), col("h", "hex", type="text")],
               [[i + 1, (V[VIEW_OF[st]]["waveforms"].get("dout_cycle_indices") or [None] * 99)[i], wd,
                 f"0x{int(wd):0{math.ceil(n / 4)}X}"] for i, wd in enumerate(V[VIEW_OF[st]]["waveforms"].get("dout_words") or [])],
               stage=st, alt="dout", search=False, csv=False,
               caption="Bit-exact verification of OpenROAD-routed `gf180mcu_fd_sc_mcu7t5v0` standard-cell netlist driven by the "
                       "analog modulator bitstream (old-site text). Words are the sdm2bin RTL model applied to this stage's bitstream.")
         for st in STAGES], cols=1))
    return section("3. Exhaustive Simulations (Pre / Post / Full + PVT + MC)", blocks)


def layout_section(cid, d):
    base = f"designs/{cid}"
    gds = f"{base}/{cid}.gds.gz"
    lay, cm = d["layout"], d.get("cap_macro") or {}
    dm = d.get("digital_macro") or {}
    ana = cm.get("analysis") or {}
    top = lay.get("top_cell")
    blocks = [{"type": "gallery", "style": "grid", "cols": 3, "title": "Physical layout: full-chip GDS, gLayout SC cap macro, OpenROAD sdm2bin macro",
               "items": [{"label": "Full-chip SDM ADC GDS", "gds": gds},
                         {"label": "Custom gLayout SC cap macro", "gds": gds, "cell": f"CAP__{d['cap_key']}"},
                         {"label": "OpenROAD sdm2bin digital macro", "gds": gds, "cell": f"DIG__{d['dig_key']}"}],
               "caption": "Hierarchical GDSII assembly with grounded M3 guard rings, Magic PEX iterative capacitor ratio trimming, "
                          "KLayout DRC = 0, and LVS Match. Thumbnails are rendered by the hub from the GDS (top cell and the "
                          "`CAP__`/`DIG__` sub-cells); the old site's pre-rendered layout SVGs are not used."}]
    dl = [("Full-chip GDSII (.gds.gz)", gds), ("Pre-layout SPICE", f"{base}/netlist_pre.spice"),
          ("Post-Cap-PEX SPICE", f"{base}/netlist_post.spice"), ("Full-chip PEX SPICE", f"{base}/netlist_full.spice"),
          ("Simulation package (sim.json)", f"{base}/sim.json"), ("Card evidence (data.json)", f"{base}/data.json"),
          (f"sdm2bin gate-level netlist ({d['dig_key']})", f"designs/digital/{d['dig_key']}/{d['dig_key']}.spice"),
          (f"sdm2bin standalone GDS ({d['dig_key']})", f"designs/digital/{d['dig_key']}/{d['dig_key']}.gds.gz")]
    blocks.append({"type": "downloads", "title": "Deliverable artifacts",
                   "items": [{"label": l, "file": f} for l, f in dl if exists(f)]})
    th = cm.get("trim_history") or []
    ts = cm.get("trim_state") or {}
    trim_rows = [[it.get("iter"), mul(it.get("cu_ext_ff"), 1e-15), mul(it.get("cs1_ff"), 1e-15), mul(it.get("ci1_ff"), 1e-15),
                  mul(it.get("cdac1_ff"), 1e-15), mul(it.get("cs2_ff"), 1e-15), mul(it.get("ci2_ff"), 1e-15),
                  it.get("a1_ext"), it.get("a2_ext"), it.get("a1_err_pct"), it.get("a2_err_pct"), it.get("max_ratio_err_pct"),
                  it.get("equiv_lsb_err")] for it in th]
    lens = ts.get("mom_branch_finger_lengths") or ts.get("mim_branch_lengths") or {}
    lkind = "MOM finger length" if ts.get("mom_branch_finger_lengths") else "MIM plate length"
    len_rows = [[b, len(v), min(v), max(v), sum(v) / len(v)] for b, v in lens.items() if v]
    br = ana.get("branch_table") or []
    br_rows = [[x.get("name"), x.get("stage"), x.get("node"), x.get("units"), x.get("col_units"), x.get("role"), x.get("sw_phase"),
                x.get("nom_ratio"), x.get("ext_ratio"), x.get("ratio_err_pct"), mul(x.get("c_p_ff"), 1e-15), mul(x.get("c_n_ff"), 1e-15),
                mul(x.get("cpar_bot_ff"), 1e-15), (ana.get("diff_mismatch_pct") or {}).get(x.get("name"))] for x in br]
    fcap = lambda k: mul(ana.get(k), 1e-15)
    trim = [
        kv(None, [["SC cap macro cell", f"`{cm.get('cell_name') or d['cap_key']}`"],
                  ["Unit cells", f"{cm.get('total_units')} ({cm.get('units_per_side')}/side) · bank ×{cm.get('cap_bank_mult', 1)}"],
                  ["Macro size", f"{fx(cm.get('width_um'), 1)} × {fx(cm.get('height_um'), 1)} µm ({fx(cm.get('area_um2'), 0)} µm²)"],
                  {"label": "Extracted unit cap C<sub>u,ext</sub>", "value": fcap("cu_ext_ff"), "unit": "F", "si": True, "digits": 5},
                  ["C<sub>s1</sub> / C<sub>i1</sub> / C<sub>dac1</sub>", f"{fx(ana.get('cs1_ff'), 1)} / {fx(ana.get('ci1_ff'), 1)} / {fx(ana.get('cdac1_ff'), 1)} fF"],
                  ["C<sub>s2</sub> / C<sub>i2</sub>", f"{fx(ana.get('cs2_ff'), 1)} / {fx(ana.get('ci2_ff'), 1)} fF"],
                  {"label": "Post-trim max ratio error", "value": f"{fx(ana.get('max_ratio_err_pct'), 4)} %", "s": "good"},
                  ["a<sub>1,ext</sub> / a<sub>2,ext</sub>", f"{fx(ana.get('a1_ext'), 5)} / {fx(ana.get('a2_ext'), 5)} (nom {ana.get('a1_nom')} / {ana.get('a2_nom')})"],
                  ["Aux ratio (nom → ext)", f"{ana.get('aux_ratio_nom')} → {fx(ana.get('aux_ratio_ext'), 5)} ({fx(ana.get('aux_err_pct'), 4)} %)"],
                  ["β<sub>1,ext</sub> / β<sub>2,ext</sub>", f"{fx(ana.get('beta1_ext'), 4)} / {fx(ana.get('beta2_ext'), 4)}"],
                  ["C<sub>par,int1</sub> / C<sub>par,int2</sub>", f"{fx(ana.get('cpar_int1_ff'), 2)} / {fx(ana.get('cpar_int2_ff'), 2)} fF"],
                  ["Equivalent LSB error", fx(ana.get("equiv_lsb_err"), 4)],
                  ["DRC / LVS", f"{'clean' if (cm.get('drc') or {}).get('clean') else '✗'} / {'match' if (cm.get('lvs') or {}).get('match') else '✗'}"]], cols=2),
        table("Trim iterations", [col("i", "Iter", digits=0), col("cu", "C<sub>u,ext</sub>", unit="F", si=True, digits=5),
                                  col("cs1", "C<sub>s1</sub>", unit="F", si=True, digits=5), col("ci1", "C<sub>i1</sub>", unit="F", si=True, digits=5),
                                  col("cd", "C<sub>dac1</sub>", unit="F", si=True, digits=5), col("cs2", "C<sub>s2</sub>", unit="F", si=True, digits=5),
                                  col("ci2", "C<sub>i2</sub>", unit="F", si=True, digits=5), col("a1", "a<sub>1,ext</sub>", digits=6),
                                  col("a2", "a<sub>2,ext</sub>", digits=6), col("e1", "a<sub>1</sub> err", unit="%", digits=3),
                                  col("e2", "a<sub>2</sub> err", unit="%", digits=3), col("em", "Max ratio error", unit="%", digits=3),
                                  col("lsb", "Equiv. LSB err", digits=3)], trim_rows, search=False,
              caption="Closed-loop finger/length calibration of custom `gLayout` MOM/MIM unit cells to cancel fringing & trunk "
                      "routing parasitics. (The old site's trim table printed “—”: it read non-existent fields.)"),
    ]
    if len(th) > 1:
        trim.append(chart("Trim convergence", [
            {"type": "scatter", "mode": "lines+markers", "x": [it["iter"] for it in th], "y": [abs(it.get("max_ratio_err_pct") or 0) for it in th], "name": "max |ratio error|"},
            {"type": "scatter", "mode": "lines+markers", "x": [it["iter"] for it in th], "y": [abs(it.get("a1_err_pct") or 0) for it in th], "name": "|a1 error|"},
            {"type": "scatter", "mode": "lines+markers", "x": [it["iter"] for it in th], "y": [abs(it.get("a2_err_pct") or 0) for it in th], "name": "|a2 error|"}],
            {"xaxis": axis("Trim iteration", dtick=1), "yaxis": axis("Error (%)", type="log")}, height=260))
    if len_rows:
        trim.append(table(f"Final trimmed {lkind}s per branch (µm)", [col("b", "Branch", type="text"), col("n", "Units", digits=0),
                                                                    col("mn", "Min", unit="µm", digits=5), col("mx", "Max", unit="µm", digits=5),
                                                                    col("av", "Mean", unit="µm", digits=5)], len_rows, search=False, csv=False))
    if br_rows:
        trim.append(table("Extracted branch table", [col("n", "Branch", type="text"), col("s", "Stage", digits=0), col("nd", "Node", type="text"),
                                                     col("u", "Units", digits=0), col("cu", "Col units", digits=0), col("r", "Role", type="text"),
                                                     col("ph", "Switch phase", type="text"), col("nr", "Nominal ratio", digits=5),
                                                     col("er", "Extracted ratio", digits=6), col("e", "Ratio err", unit="%", digits=3),
                                                     col("cp", "C<sub>p</sub>", unit="F", si=True, digits=5), col("cn", "C<sub>n</sub>", unit="F", si=True, digits=5),
                                                     col("cb", "C<sub>bot,par</sub>", unit="F", si=True, digits=4), col("dm", "P/N mismatch", unit="%", digits=3)],
                          br_rows, search=False))
    blocks.append(section("Magic PEX Iterative Capacitor Ratio Trimming Convergence", trim))
    areas = [("SC cap array", "cap_area_um2"), ("Op-amps", "opa_area_um2"), ("Switches", "sw_area_um2"), ("Comparator", "comp_area_um2"),
             ("sdm2bin digital", "dig_area_um2"), ("Routing / whitespace", "routing_area_um2")]
    fl = [
        kv(None, [["Top cell", f"`{top}`"], ["Full-chip core dimensions", f"{fx(lay.get('width_um'), 1)} × {fx(lay.get('height_um'), 1)} µm"],
                  ["Area", f"{fx((lay.get('area_um2') or 0) / 1e6, 4)} mm² ({fx(lay.get('area_um2'), 0)} µm²)"],
                  {"label": "Summing-node routing C<sub>route,int1</sub>", "value": mul(lay.get("cpar_int1_route_ff"), 1e-15), "unit": "F", "si": True, "digits": 4},
                  {"label": "C<sub>route,int2</sub>", "value": mul(lay.get("cpar_int2_route_ff"), 1e-15), "unit": "F", "si": True, "digits": 4},
                  {"label": "C<sub>route,out1</sub> / C<sub>route,out2</sub>", "value": f"{fx(lay.get('cpar_out1_route_ff'), 2)} / {fx(lay.get('cpar_out2_route_ff'), 2)} fF"},
                  {"label": "C<sub>route,x12</sub> (int1–int2 coupling)", "value": mul(lay.get("cpar_x12_route_ff"), 1e-15), "unit": "F", "si": True, "digits": 3},
                  {"label": "Physical signoff", "value": f"DRC = {lay.get('drc_violations')} · {'LVS match' if lay.get('lvs_match') else 'LVS ✗'}",
                   "s": "good" if lay.get("drc_clean") and lay.get("lvs_match") else "bad"},
                  ["Op-amp family / VCM op-amp placed", f"{lay.get('opa_family')} / {'yes' if lay.get('use_vcm_opa') else 'no'}"],
                  ["Isolation", "Grounded M3 guard ring isolates analog core from `sdm2bin`"]], cols=2),
        chart("Full-chip area breakdown", [{"type": "bar", "x": [a[0] for a in areas], "y": [lay.get(a[1]) for a in areas],
                                            "text": [f"{fx(lay.get(a[1]), 0)} µm²" for a in areas], "textposition": "auto"}],
              {"yaxis": axis("Area (µm²)"), "showlegend": False}, height=280),
        note("The old site's floorplan-zone table (zone X/Y ranges) was empty: the export carries no zone coordinates. "
             "The routing-PEX values above are the `cpar_*_route_ff` fields of the layout record (the old site printed “—”).", "muted"),
        {"type": "code", "title": "Top-level ports", "text": " ".join(lay.get("ports") or []), "max_height": 120},
    ]
    blocks.append(section("Full-Chip Floorplan Zone Breakdown & Top-Level Routing PEX", fl,
                          intro="Abutted 4-zone mixed-signal floorplan with isolated analog/digital supplies and extracted inter-macro RC parasitics."))
    if dm:
        blocks.append(kv(f"OpenROAD sdm2bin macro `{dm.get('cell_name')}`", [
            ["Die / core", f"{fx(dm.get('die_width_um'), 1)} × {fx(dm.get('die_height_um'), 1)} µm / {fx(dm.get('core_width_um'), 1)} × {fx(dm.get('core_height_um'), 1)} µm"],
            ["Utilization", f"{fx(dm.get('utilization_pct'), 0)} %"], ["Synth cells / area", f"{dm.get('synth_cell_count')} / {fx(dm.get('synth_area_um2'), 0)} µm²"],
            ["Routed active / physical / total cells", f"{dm.get('routed_active_cells')} / {dm.get('routed_physical_cells')} / {dm.get('routed_total_cells')}"],
            ["Wirelength / vias", f"{fx(dm.get('wirelength_um'), 0)} µm / {dm.get('vias_count')}"], ["DRT violations", dm.get("drt_violations")],
            ["Setup slack / data arrival", f"+{fx(dm.get('slack_ns'))} ns / {fx(dm.get('data_arrival_ns'))} ns (WNS {dm.get('wns_ns')}, TNS {dm.get('tns_ns')})"],
            ["Power (OpenROAD)", f"{fx(dm.get('power_uw'))} µW"], ["Gate-sim / DRC / LVS",
                                                                     f"{'pass' if (dm.get('sim_verify') or {}).get('pass') else '✗'} / {(dm.get('drc') or {}).get('effective')} / {'match' if (dm.get('lvs') or {}).get('match') else '✗'}"]],
            cols=3, caption="All 12 macros: see the **Macros** page."))
    return section("4. Layout (gLayout + OpenROAD + Full-Chip GDS)", blocks)


def spec_section(d):
    a, r, c = d["arch_spec"], d["res_spec"], d["cap_spec"]
    sim = d["sim"]
    mc_runs = (sim.get("monte_carlo") or {}).get("runs") or []
    return section("Architecture, resolution & capacitor specification", [
        kv(f"Architecture `{a['id']}` — {a['name']}", [["Short name", a["short"]], ["Family", a["family"]], ["Input & loop", a["input_arch"]],
                                                       ["a1 / a2", f"{a['a1']} / {a['a2']}"], ["b1 / b2", f"{a['b1']} / {a['b2']}"],
                                                       ["c1 / c2", f"{a['c1']} / {a['c2']}"], ["g1 (resonator)", a["g1"]],
                                                       ["Shared Cs / DAC", a["shared_cs_dac"]], ["VCM op-amp (arch spec)", a["use_vcm_opa"]],
                                                       ["Quantizer votes", a["multi_vote"]], ["SQNR boost", f"{a['sqnr_boost_db']} dB"],
                                                       ["Reference", a.get("ref", "")]], cols=2, caption=a.get("desc", "")),
        kv(f"Resolution spec ({r['nbits']}-bit)", [["OSR", r["osr"]], {"label": "f<sub>s</sub>", "value": r["fs_hz"], "unit": "Hz", "si": True},
                                                   {"label": "f<sub>B</sub>", "value": r["fb_hz"], "unit": "Hz", "si": True},
                                                   {"label": "f<sub>Nyq</sub>", "value": r["fnyq_hz"], "unit": "Hz", "si": True},
                                                   ["FFT cycles", r["n_fft_cycles"]], ["Loop order L", r["loop_order"]], ["Sinc order", r["sinc_order"]],
                                                   ["Cap bank multiplier", r["cap_bank_mult"]], ["CDS chopper", r["cds_chopper"]], ["DWA order", r["dwa_order"]],
                                                   ["C<sub>u</sub> units s1 / i1 / s2 / i2", f"{r['cu_units_s1']} / {r['cu_units_i1']} / {r['cu_units_s2']} / {r['cu_units_i2']}"],
                                                   ["Target ENOB min / nominal goal", f"{r['target_enob_min']} / {r['nom_enob_goal']} b"]], cols=3),
        kv(f"Capacitor `{c['id']}` — {c['name']}", [["C<sub>u,nom</sub>", f"{c['cu_nom_ff']} fF"]], cols=1, caption=c.get("desc", "")),
        table("Monte Carlo run samples (first 40 of 100 stored)", [col("r", "Run", digits=0), col("e", "ENOB", unit="bit", digits=5),
                                                                   col("s", "SNDR", unit="dB", digits=5), col("o", "Offset", unit="mV", digits=4),
                                                                   col("c", "Cap error", unit="%", digits=4)],
              [[x["run"], x["enob"], x["sndr_db"], x["offset_mv"], x["cap_err_pct"]] for x in mc_runs], stage="full", alt="mcruns",
              caption="Random draws of the MC model (offset and cap error are not fed back into the ENOB draw)."),
    ], collapsed=True)


def detail_doc(c, d):
    cid = c["card_id"]
    sim, lay = d["sim"], d["layout"]
    blocks = [note(MODEL_NOTE + " " + DATA_CAVEATS, "warn")]
    for st in STAGES:
        blocks.append(kpi_strip(c, sim["views"][VIEW_OF[st]], sim, lay, st))
    sel, opa_t, cs_t = component_tables(d)
    ov = [progression_table(d), loop_param_table(d)]
    np_blocks = []
    for st in STAGES:
        np_blocks += noise_power_charts(sim["views"][VIEW_OF[st]], st)
    ov.append(section("In-Band Noise Budget & Power Breakdown", np_blocks, cols=2))
    ov += [sel, opa_t, cs_t]
    blocks.append(section("1. Overview & Systematic Component Selection", ov))
    blocks.append(section("2. Schematic (gm/Id Annotated)", [schematic_gallery(cid, d), gmid_table(d)]))
    blocks.append(sim_section(cid, d))
    blocks.append(layout_section(cid, d))
    blocks.append(spec_section(d))
    return {"blocks": blocks}


# ============================================================================= designs
designs = []
DES_IDS = set()
for c in CARDS:
    cid = c["card_id"]
    d = DATA[cid]
    sim, lay = d["sim"], d["layout"]
    area = lay.get("area_um2")
    results = {}
    for st in STAGES:
        v = sim["views"][VIEW_OF[st]]
        results[st] = {"metrics": view_metrics(v, area), "note": STAGE_NOTES[st]}
    pvt, mc = sim["pvt"], sim["monte_carlo"]
    fm = results["full"]["metrics"]
    fm.update({"pvt_min_enob": pvt.get("enob_min"), "pvt_spread": pvt.get("enob_spread"), "mc_enob": mc.get("enob_mean"),
               "mc_enob_std": mc.get("enob_std"), "mc_p5": mc.get("enob_p5"), "mc_yield": mc.get("yield_pct")})
    p_ok, p_tot = pvt_count(sim)
    results["full"]["pvt"] = {"pass": p_ok, "total": p_tot}
    results["full"]["mc"] = {"pass": round(mc["n_runs"] * mc["yield_pct"] / 100.0), "total": mc["n_runs"]}
    results["full"]["robust"] = bool(pvt.get("all_pass")) and (mc.get("yield_pct") or 0) >= 100.0
    results["full"]["note"] += " Robust = all 9 PVT corners and all 100 MC runs meet ENOB ≥ target (model; MC clipped above target)."

    base = f"designs/{cid}"
    files = {k: f"{base}/{v}" for k, v in (("schematic", "schematic.svg"), ("gds", f"{cid}.gds.gz"), ("netlist", "netlist_pre.spice"),
                                            ("pex_netlist", "netlist_full.spice"), ("data", "data.json")) if exists(f"{base}/{v}")}
    co = d["components"]
    images = [{"label": lbl, "src": f"{base}/{f}"} for lbl, f, need in (
        ("Stage-1 op-amp", "opa1_schematic.svg", True), ("Stage-2 op-amp", "opa2_schematic.svg", True),
        ("VCM op-amp", "opa_vcm_schematic.svg", bool(co.get("opa_vcm"))), ("Quantizer comparator", "comp_schematic.svg", True),
        ("Sampling switch", "sw_in_schematic.svg", True), ("sdm2bin decimator", "dig_schematic.svg", True)) if need and exists(f"{base}/{f}")]
    if "gds" in files:
        images += [{"label": "Layout: SC cap array", "gds": files["gds"], "cell": f"CAP__{c['cap_key']}"},
                   {"label": "Layout: sdm2bin macro", "gds": files["gds"], "cell": f"DIG__{c['dig_key']}"}]
    downloads = [{"label": l, "file": f} for l, f in (("Post-Cap-PEX netlist", f"{base}/netlist_post.spice"), ("Simulation package (sim.json)", f"{base}/sim.json"),
                                                      (f"sdm2bin gate-level netlist", f"designs/digital/{c['dig_key']}/{c['dig_key']}.spice"),
                                                      (f"sdm2bin standalone GDS", f"designs/digital/{c['dig_key']}/{c['dig_key']}.gds.gz")) if exists(f)]
    rs, a, cs = d["res_spec"], d["arch_spec"], c["components_summary"]
    tags = [c["arch_name"], d["cap_spec"]["name"], f"{c['nbits']}-bit target (OSR {c['osr']})", f"L = {rs['loop_order']} loop", f"sinc{rs['sinc_order']}"]
    if rs.get("cds_chopper"):
        tags.append("CDS chopper")
    if rs.get("dwa_order"):
        tags.append(f"DWA order {rs['dwa_order']}")
    if a.get("multi_vote", 1) > 1:
        tags.append(f"{a['multi_vote']}× voted quantizer")
    tags += [f"cap macro {c['cap_key']}", f"OpenROAD {c['dig_key']}"]
    if lay.get("drc_clean"):
        tags.append("KLayout DRC = 0")
    if lay.get("lvs_match"):
        tags.append("KLayout LVS match")
    if pvt.get("all_pass"):
        tags.append(f"9-corner PVT pass (min {fx(pvt['enob_min'])} b, model)")
    tags.append(f"100-run MC yield {fx(mc['yield_pct'], 0)} % (model)")
    if (sim.get("cosim") or {}).get("cosim_bit_exact"):
        tags.append("gate-level sdm2bin bit-exact")
    o1, o2 = co["opa1"], co["opa2"]
    params = {
        "OSR": c["osr"], "f_s": f"{c['fs_mhz']} MHz", "f_B": f"{c['fb_khz']} kHz", "f_Nyq": f"{rs['fnyq_hz'] / 1e3:g} kHz",
        "Loop order": rs["loop_order"], "Decimator": f"sinc{rs['sinc_order']} ({c['dig_key']})",
        "Coefficients a1 / a2 / b1": f"{a['a1']} / {a['a2']} / {a['b1']}",
        "Cap macro": c["cap_key"], "C_u,nom": f"{d['cap_spec']['cu_nom_ff']} fF",
        "Cap ratio error (post-trim)": f"{fx(c['layout_summary']['max_ratio_err_pct'], 4)} %",
        "Stage-1 op-amp": f"{o1['key']} ({cs['opa1_arch']}, gm/Id {cs['opa1_gmid_target']}→{cs['opa1_gmid_sim']})",
        "Stage-2 op-amp": f"{o2['key']} ({cs['opa2_arch']}, gm/Id {cs['opa2_gmid_target']}→{cs['opa2_gmid_sim']})",
        "VCM op-amp": cs.get("opa_vcm_key"), "Quantizer": f"{cs['comp_key']} ({cs['comp_arch']}, gm/Id {cs['comp_gmid_target']})",
        "Input switch": f"{cs['sw_in_key']} ({cs['sw_in_topo']})", "SC switch": cs.get("sw_sc_key"),
        "Cap / op-amp / switch area": f"{fx(lay.get('cap_area_um2'), 0)} / {fx(lay.get('opa_area_um2'), 0)} / {fx(lay.get('sw_area_um2'), 0)} µm²",
        "Comparator / digital / routing area": f"{fx(lay.get('comp_area_um2'), 0)} / {fx(lay.get('dig_area_um2'), 0)} / {fx(lay.get('routing_area_um2'), 0)} µm²",
        "Top cell": lay.get("top_cell"),
    }
    detail = write(f"designs/{cid}.json", detail_doc(c, d))
    designs.append({
        "id": cid,
        "title": f"{c['nbits']}-bit · {c['vdd']} V · {CAP_LABEL[c['cap_type']]} · {c['arch_short']}",
        "summary": f"{c['subtitle']} — {a['input_arch']}. {rs['loop_order']}th-order-loop configuration at OSR {c['osr']} "
                   f"(f<sub>s</sub> = {c['fs_mhz']} MHz, f<sub>B</sub> = {c['fb_khz']} kHz) with {d['cap_spec']['name']} and the "
                   f"`{c['dig_key']}` decimator. *Performance numbers are model-based — see the note below.*".replace("2th", "2nd").replace("3th", "3rd"),
        "vdd": c["vdd"],
        "axes": {"topology": c["arch_id"], "resolution": f"{c['nbits']}b", "cap": c["cap_type"]},
        "tags": tags,
        "physical": {"drc": lay.get("drc_clean"), "lvs": lay.get("lvs_match"), "pex": True,
                     "area_um2": area, "width_um": lay.get("width_um"), "height_um": lay.get("height_um")},
        "results": results,
        "params": params,
        "files": files,
        "images": images,
        "downloads": downloads,
        "detail": detail,
    })
    DES_IDS.add(cid)


# ============================================================================= pages
def stage_metrics(c, st):
    return c["metrics"][VIEW_OF[st]]


def kpi_banner(st):
    v = VIEW_OF[st]
    mx = {n: 0.0 for n in NBITS}
    fw, fsd, pmin, pmax = math.inf, -math.inf, math.inf, -math.inf
    for c in CARDS:
        m = c["metrics"][v]
        mx[c["nbits"]] = max(mx[c["nbits"]], m["enob"])
        fw, fsd = min(fw, m["fom_walden_fj"]), max(fsd, m["fom_schreier_db"])
        pmin, pmax = min(pmin, m["power_uw"]), max(pmax, m["power_uw"])
    nclean = sum(1 for c in CARDS if DATA[c["card_id"]]["layout"].get("drc_clean") and DATA[c["card_id"]]["layout"].get("lvs_match"))
    npvt = sum(1 for c in CARDS if c["variation"].get("pvt_pass"))
    nmom = sum(1 for k in CAP_MACROS.values() if k["cap_type"] == "mom")
    maxerr = max((k.get("analysis") or {}).get("max_ratio_err_pct", 0) for k in CAP_MACROS.values())
    ndig = sum(1 for k in DIG_MACROS.values() if (k.get("drc") or {}).get("clean"))
    nlvs = sum(1 for k in DIG_MACROS.values() if (k.get("lvs") or {}).get("match"))
    return {"type": "stats", "stage": st, "alt": "kpibanner", "items": [
        {"label": "Deliverable ΣΔ ADC cards", "value": f"{len(CARDS)} / {IDX['total_cards']}",
         "sub": f"{', '.join(f'{n}b' for n in NBITS)} · DRC/LVS clean {nclean}/{len(CARDS)} · PVT pass {npvt}/{len(CARDS)}"},
        {"label": "Custom gLayout SC cap macros", "value": f"{len(CAP_MACROS)} / {IDX['cap_macros_count']}",
         "sub": f"{nmom} MOM (M1–M4) + {len(CAP_MACROS) - nmom} MIM (Opt-B) · ≤ {maxerr:.4f}% ratio err"},
        {"label": "OpenROAD sdm2bin macros", "value": f"{len(DIG_MACROS)} / {IDX['digital_macros_count']}",
         "sub": f"{NBITS[0]}b..{NBITS[-1]}b direct binary output · {ndig} DRC clean / {nlvs} LVS match"},
        {"label": f"Peak ENOB ({NBITS[0]}b .. {NBITS[-1]}b)", "value": f"{mx[NBITS[0]]:.2f}b .. {mx[NBITS[-1]]:.2f}b",
         "sub": " · ".join(f"{n}b: {mx[n]:.2f}b" for n in NBITS[2:])},
        {"label": "Best Walden / Schreier FoM", "value": f"{fw:.2f} fJ / {fsd:.1f} dB", "sub": f"Power range: {pmin:.1f} – {pmax:.1f} µW"},
        {"label": "Variation resilience", "value": "9 PVT + 100 MC",
         "sub": f"{sum(1 for c in CARDS if c['variation']['mc_yield_pct'] >= 100)}/{len(CARDS)} cards 100 % yield across "
                f"{100 * len(CARDS):,} MC + {9 * len(CARDS)} PVT runs (full-chip view, model)"},
    ], "caption": f"Active stage: {OLD_STAGE_LONG[st]}."}


def master_rows():
    rows = []
    for st in STAGES:
        for c in CARDS:
            m = stage_metrics(c, st)
            var, ls = c["variation"], c["layout_summary"]
            lay = DATA[c["card_id"]]["layout"]
            rows.append({"stage": st, "id": c["card_id"], "res": f"{c['nbits']}-bit", "vdd": c["vdd"], "cap": c["cap_type"].upper(),
                         "arch": c["arch_short"], "osr": c["osr"], "fs": c["fs_mhz"] * 1e6, "fb": c["fb_khz"] * 1e3,
                         "enob": m["enob"], "sndr": m["sndr_db"], "sfdr": m["sfdr_db"], "dr": m["dr_db"],
                         "p": m["power_uw"] * 1e-6, "fw": m["fom_walden_fj"] * 1e-15, "fs_db": m["fom_schreier_db"],
                         "pvt": var["pvt_min_enob"], "mcs": var["mc_enob_std"], "cerr": ls["max_ratio_err_pct"],
                         "area": ls["area_mm2"], "drc": bool(lay.get("drc_clean")), "lvs": bool(lay.get("lvs_match")),
                         "_design": c["card_id"]})
    return rows


MASTER_COLS = [col("stage", "Stage", type="text"), col("id", "Card ID", type="design"), col("res", "Res", type="text"),
               col("vdd", "V<sub>DD</sub>", unit="V", digits=2), col("cap", "Cap", type="text"), col("arch", "Architecture", type="text"),
               col("osr", "OSR", digits=0), col("fs", "f<sub>s</sub>", unit="Hz", si=True), col("fb", "f<sub>B</sub>", unit="Hz", si=True),
               col("enob", "ENOB", unit="bits", digits=4, better="high"), col("sndr", "SNDR", unit="dB", digits=5, better="high"),
               col("sfdr", "SFDR", unit="dB", digits=5, better="high"), col("dr", "DR", unit="dB", digits=5, better="high"),
               col("p", "Power", unit="W", si=True, digits=5, better="low"), col("fw", "FoM<sub>W</sub>", unit="J/step", si=True, digits=4, better="low"),
               col("fs_db", "FoM<sub>S</sub>", unit="dB", digits=5, better="high"),
               col("pvt", "PVT min ENOB (full-chip)", unit="bits", digits=4, better="high"),
               col("mcs", "MC σ (full-chip)", unit="bits", digits=3, better="low"), col("cerr", "Cap err", unit="%", digits=3, better="low"),
               col("area", "Area", unit="mm²", digits=4, better="low"), col("drc", "DRC", type="status"), col("lvs", "LVS", type="status")]


def comp_summary_rows():
    rows = []
    for c in CARDS:
        cs = c["components_summary"]
        var = c["variation"]
        rows.append({"id": c["card_id"], "vdd": c["vdd"],
                     "o1": f"{cs['opa1_arch']} (`gm/Id {cs['opa1_gmid_target']}→{cs['opa1_gmid_sim']}`) {opa_link(cs['opa1_key'])}",
                     "o2": f"{cs['opa2_arch']} (`gm/Id {cs['opa2_gmid_target']}→{cs['opa2_gmid_sim']}`) {opa_link(cs['opa2_key'])}",
                     "ov": opa_link(cs.get("opa_vcm_key")),
                     "q": f"{sa_link(cs['comp_key'])} (`gm/Id {cs['comp_gmid_target']}`)",
                     "sw": f"{cs['sw_in_topo']}: {sw_link(cs['sw_in_key'])} + {sw_link(cs.get('sw_sc_key'))}",
                     "dig": f"`{c['dig_key']}`", "capm": f"`{c['cap_key']}`",
                     "pvt": var["pvt_min_enob"], "mcs": var["mc_enob_std"], "_design": c["card_id"]})
    return rows


summary_page = {"intro": "Old-site landing view of the **Switched-Capacitor ΣΔ ADC Generator (8-bit to >20-bit ENOB)** — "
                         "GF180MCU-D · 180 nm 5LM · 96 deliverable designs · 1.8 V & 3.3 V · 8b / 10b / 12b / 16b / 18b / 20b "
                         "(>22b peak ENOB) · custom `gLayout` MOM & Option-B MIM · OpenROAD `sdm2bin` decimator. The coverage matrix, "
                         "card grid (with resolution / V<sub>DD</sub> / cap / architecture filters and the ENOB / power / FoM / area "
                         "sorts) and the sortable comparison table are the hub's built-in **Designs** view; the hub's global "
                         "**Simulation stage** option is the old “Verification Stage” switch (Pre-Layout → Pre-PEX, Post-Cap-PEX → "
                         "Partial post-PEX, Full-Chip PEX → Full post-PEX).",
                "blocks": [note(MODEL_NOTE + " " + DATA_CAVEATS, "warn")] + [kpi_banner(st) for st in STAGES] + [
                    md("Click any cell in the **2 V<sub>DD</sub> × 6 Resolutions (8b, 10b, 12b, 16b, 18b, 20b) × 2 Capacitor Types × 4 Loop "
                       "Architectures** matrix to inspect its annotated schematic, multi-testbench simulations, and full-chip GDS layout. "
                       "Matrix legend of the old site: DRC = 0 · LVS Match · 9-Corner PVT Pass · Showing: <active stage>.",
                       title="Interactive 96-Card Deliverable Coverage Matrix (8-bit to >20-bit ENOB)",
                       caption="The matrix itself is the **Designs → Matrix** view (rows = loop architecture, column groups = V<sub>DD</sub>, "
                               "columns = resolution × capacitor; the *Cell metric* menu offers the old cell contents: ENOB/SNDR, "
                               "power/FoM<sub>S</sub>, PVT worst ENOB/MC σ)."),
                    table("Master 48-Card Deliverable Verification Table", MASTER_COLS, master_rows(), stage_column="stage", page_size=100,
                          caption="Complete metric summary across all designs for the active verification stage (old title says 48; "
                                  "there are 96 cards). Click any row to inspect. PVT/MC columns come from the full-chip view at every stage."),
                    table("Deliverable card component summary (old card-grid contents)",
                          [col("id", "Card", type="design"), col("vdd", "V<sub>DD</sub>", unit="V", digits=2),
                           col("o1", "Stage-1 OPA", type="text", md=True), col("o2", "Stage-2 OPA", type="text", md=True),
                           col("ov", "VCM OPA", type="text", md=True), col("q", "Quantizer", type="text", md=True),
                           col("sw", "Switches", type="text", md=True), col("dig", "Decimator", type="text", md=True),
                           col("capm", "Cap macro", type="text", md=True), col("pvt", "9-PVT min", unit="bits", digits=4),
                           col("mcs", "MC σ", unit="bits", digits=3)], comp_summary_rows(), page_size=100,
                          caption="Click any card to open the Deep-Dive Inspector (Schematic + Simulation + Layout) — on the hub, the "
                                  "design page. Op-amp / comparator / switch keys link to the reused designs in the sibling tabs."),
                    kv("Provenance (old-site footer)", [
                        ["Project", IDX.get("project", "")], ["PDK", IDX.get("pdk", "")],
                        ["Toolchain", "`hpretl/iic-osic-tools` + `gLayout` + OpenROAD"],
                        ["Library commits", " · ".join(f"`{k.replace('_commit', '')}:{v}`" for k, v in sorted((IDX.get("provenance") or {}).items()))],
                        ["Repository", "[aicdb/sdm-gen-gemini4](https://github.com/aicdb/sdm-gen-gemini4)"]], cols=1),
                ]}


# ----------------------------------------------------------------------------- macros page
def cap_macro_rows():
    rows = []
    for k in sorted(CAP_MACROS, key=lambda k: (CAP_MACROS[k]["nbits"], CAP_MACROS[k]["cap_type"] != "mom", ARCH_ORDER.index(CAP_MACROS[k]["arch_id"]))):
        cm = CAP_MACROS[k]
        ana, ts = cm.get("analysis") or {}, cm.get("trim_state") or {}
        lens = [x for v in (ts.get("mom_branch_finger_lengths") or ts.get("mim_branch_lengths") or {}).values() for x in v]
        wl = (f"L_f = {min(lens):.5g}–{max(lens):.5g} µm" if ts.get("mom_branch_finger_lengths") else f"plate L = {min(lens):.4g}–{max(lens):.4g} µm") if lens else "—"
        rows.append({"cell": cm["cell_name"], "res": f"{cm['nbits']}-bit (OSR {cm['osr']})", "cap": cm["cap_type"].upper(), "arch": cm["arch_id"],
                     "ups": cm["units_per_side"], "tu": cm["total_units"], "bank": cm.get("cap_bank_mult", 1), "wl": wl,
                     "cu": mul(ana.get("cu_ext_ff"), 1e-15), "a1": f"{ana.get('a1_nom')} → {fx(ana.get('a1_ext'), 5)}",
                     "a2": f"{ana.get('a2_nom')} → {fx(ana.get('a2_ext'), 5)}", "err": ana.get("max_ratio_err_pct"),
                     "lsb": ana.get("equiv_lsb_err"), "iters": len(cm.get("trim_history") or []),
                     "dim": f"{fx(cm['width_um'], 1)} × {fx(cm['height_um'], 2)}", "area": cm.get("area_um2"),
                     "drc": bool((cm.get("drc") or {}).get("clean")), "lvs": bool((cm.get("lvs") or {}).get("match"))})
    return rows


def cap_macro_tab(k):
    cm = CAP_MACROS[k]
    ana = cm.get("analysis") or {}
    users = sorted(c["card_id"] for c in CARDS if c["cap_key"] == k)
    host = next((u for u in users if "_1v8_" in u), users[0] if users else None)
    blocks = []
    if host:
        blocks.append({"type": "layout", "title": f"`{k}` (sub-cell `CAP__{k}` of `{host}`)", "gds": f"designs/{host}/{host}.gds.gz",
                       "cell": f"CAP__{k}", "max_height": 360})
    blocks.append(kv(None, [["Used by", " · ".join(card_link(u) for u in users)], ["Units", f"{cm['total_units']} ({cm['units_per_side']}/side), bank ×{cm.get('cap_bank_mult', 1)}"],
                            ["Size", f"{fx(cm['width_um'], 2)} × {fx(cm['height_um'], 2)} µm = {fx(cm['area_um2'], 1)} µm²"],
                            ["C<sub>u,ext</sub>", f"{fx(ana.get('cu_ext_ff'), 4)} fF"],
                            ["a<sub>1</sub> nom → ext (err)", f"{ana.get('a1_nom')} → {fx(ana.get('a1_ext'), 6)} ({fx(ana.get('a1_err_pct'), 4)} %)"],
                            ["a<sub>2</sub> nom → ext (err)", f"{ana.get('a2_nom')} → {fx(ana.get('a2_ext'), 6)} ({fx(ana.get('a2_err_pct'), 4)} %)"],
                            ["Max ratio error / equiv. LSB", f"{fx(ana.get('max_ratio_err_pct'), 4)} % / {fx(ana.get('equiv_lsb_err'), 4)}"],
                            ["β<sub>1</sub> / β<sub>2</sub> (ext)", f"{fx(ana.get('beta1_ext'), 4)} / {fx(ana.get('beta2_ext'), 4)}"],
                            ["C<sub>par,int1</sub> / C<sub>par,int2</sub>", f"{fx(ana.get('cpar_int1_ff'), 3)} / {fx(ana.get('cpar_int2_ff'), 3)} fF"],
                            ["DRC / LVS", f"{'clean' if (cm.get('drc') or {}).get('clean') else '✗'} ({(cm.get('drc') or {}).get('effective')} effective) / {'match' if (cm.get('lvs') or {}).get('match') else '✗'}"]], cols=2))
    th = cm.get("trim_history") or []
    blocks.append(table("Magic PEX trim iterations", [col("i", "Iter", digits=0), col("cu", "C<sub>u,ext</sub>", unit="fF", digits=6),
                                                      col("cs1", "C<sub>s1</sub>", unit="fF", digits=6), col("ci1", "C<sub>i1</sub>", unit="fF", digits=6),
                                                      col("cs2", "C<sub>s2</sub>", unit="fF", digits=6), col("ci2", "C<sub>i2</sub>", unit="fF", digits=6),
                                                      col("a1", "a<sub>1,ext</sub>", digits=6), col("a2", "a<sub>2,ext</sub>", digits=6),
                                                      col("em", "Max err", unit="%", digits=3)],
                        [[x["iter"], x.get("cu_ext_ff"), x.get("cs1_ff"), x.get("ci1_ff"), x.get("cs2_ff"), x.get("ci2_ff"),
                          x.get("a1_ext"), x.get("a2_ext"), x.get("max_ratio_err_pct")] for x in th], search=False, csv=False))
    br = ana.get("branch_table") or []
    blocks.append(table("Branch table", [col("n", "Branch", type="text"), col("u", "Units", digits=0), col("r", "Role", type="text"),
                                         col("ph", "Phase", type="text"), col("nr", "Nominal", digits=5), col("er", "Extracted", digits=6),
                                         col("e", "Err", unit="%", digits=3), col("c", "C<sub>avg</sub>", unit="fF", digits=6),
                                         col("cb", "C<sub>bot</sub>", unit="fF", digits=4)],
                        [[x["name"], x["units"], x["role"], x["sw_phase"], x["nom_ratio"], x["ext_ratio"], x["ratio_err_pct"], x["c_avg_ff"], x["cpar_bot_ff"]] for x in br],
                        search=False, csv=False))
    return {"label": f"{k}", "blocks": blocks}


def dig_rows():
    rows = []
    for k, dm in sorted(DIG_MACROS.items(), key=lambda kv_: (kv_[1]["vdd"], kv_[1]["nbits"])):
        sv = dm.get("sim_verify") or {}
        rows.append({"cell": dm["cell_name"], "res": f"{dm['nbits']}-bit", "osr": dm["osr"], "vdd": dm["vdd"], "fs": dm["fs_hz"],
                     "fn": dm["fnyq_hz"], "sc": dm["synth_cell_count"], "sa": dm.get("synth_area_um2"), "ssa": dm.get("synth_seq_area_um2"),
                     "ra": f"{dm['routed_active_cells']} / {dm['routed_total_cells']}", "rp": dm.get("routed_physical_cells"),
                     "die": f"{fx(dm['die_width_um'], 1)} × {fx(dm['die_height_um'], 1)}",
                     "core": f"{fx(dm.get('core_width_um'), 1)} × {fx(dm.get('core_height_um'), 1)}", "util": dm.get("utilization_pct"),
                     "wl": dm["wirelength_um"], "vias": dm.get("vias_count"), "drt": dm.get("drt_violations"), "slack": dm["slack_ns"] * 1e-9,
                     "arr": mul(dm.get("data_arrival_ns"), 1e-9), "p": dm["power_uw"] * 1e-6, "sim": bool(sv.get("pass")),
                     "drc": bool((dm.get("drc") or {}).get("clean")), "lvs": bool((dm.get("lvs") or {}).get("match"))})
    return rows


def dig_tab(k):
    dm = DIG_MACROS[k]
    base = f"designs/digital/{k}"
    sv = dm.get("sim_verify") or {}
    users = sorted(c["card_id"] for c in CARDS if c["dig_key"] == k)
    types = sorted(set(dm.get("cells_by_type") or {}) | set(dm.get("routed_cells_by_type") or {}))
    short = [t.replace("gf180mcu_fd_sc_mcu7t5v0__", "") for t in types]
    blocks = []
    if exists(f"{base}/{k}.gds.gz"):
        blocks.append({"type": "layout", "title": f"`{k}` standalone GDS", "gds": f"{base}/{k}.gds.gz", "max_height": 380})
    if exists(f"{base}/schematic.svg"):
        blocks.append({"type": "image", "title": "sdm2bin block schematic", "src": f"{base}/schematic.svg", "bg": "dark", "max_height": 420})
    blocks.append(kv(None, [["Used by", " · ".join(card_link(u) for u in users)], ["Liberty", f"`{dm.get('liberty', '').split('/')[-1]}`"],
                            ["Die / core area", f"{fx(dm.get('die_area_um2'), 1)} / {fx(dm.get('core_area_um2'), 1)} µm² (design {fx(dm.get('design_area_um2'), 0)} µm², util {dm.get('utilization_pct')} %)"],
                            ["Synth area (sequential)", f"{fx(dm.get('synth_area_um2'), 1)} ({fx(dm.get('synth_seq_area_um2'), 1)}) µm²"],
                            ["Timing", f"slack +{fx(dm.get('slack_ns'))} ns · arrival {fx(dm.get('data_arrival_ns'))} ns · WNS {dm.get('wns_ns')} · TNS {dm.get('tns_ns')}"],
                            ["DRC", f"{(dm.get('drc') or {}).get('mode')} · {(dm.get('drc') or {}).get('total')} total / {(dm.get('drc') or {}).get('effective')} effective"],
                            ["LVS", (dm.get("lvs") or {}).get("log_tail", "")]], cols=2))
    blocks.append(chart("Standard cells by type (synthesized vs routed)", [
        {"type": "bar", "orientation": "h", "y": short, "x": [(dm.get("cells_by_type") or {}).get(t, 0) for t in types], "name": "Synthesized"},
        {"type": "bar", "orientation": "h", "y": short, "x": [(dm.get("routed_cells_by_type") or {}).get(t, 0) for t in types], "name": "Routed (active)"}],
        {"barmode": "group", "xaxis": axis("Cells"), "yaxis": {"automargin": True}}, height=max(300, 18 * len(types) + 80)))
    blocks.append(table("Gate-level frame verification", [col("f", "Input duty", type="text"), col("c", "Code", digits=0)],
                        [["0 %", sv.get("code_0pct")], ["25 %", sv.get("code_25pct")], ["50 % even", sv.get("code_50pct_even")],
                         ["50 % odd", sv.get("code_50pct_odd")], ["75 %", sv.get("code_75pct")], ["100 %", sv.get("code_100pct")],
                         ["expected mid / max", f"{sv.get('expected_mid')} / {sv.get('expected_max')}"]], search=False, csv=False,
                        caption=f"Result: {'PASS' if sv.get('pass') else 'FAIL'}"))
    blocks.append({"type": "code", "title": "Ports", "text": " ".join(dm.get("ports") or []), "max_height": 100})
    blocks.append({"type": "downloads", "items": [{"label": l, "file": f} for l, f in (("GDS", f"{base}/{k}.gds.gz"), ("Gate-level SPICE netlist", f"{base}/{k}.spice"),
                                                                                       ("Metrics (metrics.json)", f"{base}/metrics.json")) if exists(f)]})
    return {"label": k, "blocks": blocks}


cap_rows = cap_macro_rows()
macros_page = {"blocks": [
    section("Custom gLayout Switched-Capacitor Array Generator", [
        note(f"Old panel title: “24 Macros: 12 MOM + 12 Option-B MIM” — the export holds {len(CAP_MACROS)} macros "
             f"({sum(1 for r in cap_rows if r['cap'] == 'MOM')} MOM + {sum(1 for r in cap_rows if r['cap'] == 'MIM')} MIM), one per "
             "resolution × cap type × architecture, shared by the 1.8 V and 3.3 V cards.", "muted"),
        table("SC cap macros", [col("cell", "Macro cell name", type="text"), col("res", "Res", type="text"), col("cap", "Cap type", type="text"),
                                col("arch", "Architecture", type="text"), col("ups", "Units / side", digits=0), col("tu", "Total units", digits=0),
                                col("bank", "Bank ×", digits=0), col("wl", "Trimmed finger / plate length", type="text"),
                                col("cu", "C<sub>u,ext</sub>", unit="F", si=True, digits=5), col("a1", "a<sub>1,target</sub> → a<sub>1,ext</sub>", type="text"),
                                col("a2", "a<sub>2,target</sub> → a<sub>2,ext</sub>", type="text"), col("err", "Max ratio err", unit="%", digits=3, better="low"),
                                col("lsb", "Equiv. LSB err", digits=3), col("iters", "Trim iters", digits=0), col("dim", "Dimensions (µm)", type="text"),
                                col("area", "Area", unit="µm²", digits=5), col("drc", "DRC", type="status"), col("lvs", "LVS", type="status")],
              cap_rows, page_size=100,
              caption="The old “Trimmed W / L” column printed “—×—µm” (it read non-existent fields); here it shows the range of the "
                      "final trimmed MOM finger lengths / MIM plate lengths over all branches."),
        chart("Post-trim max ratio error per macro", [
            {"type": "bar", "x": [r["cell"] for r in cap_rows if r["cap"] == t], "y": [r["err"] for r in cap_rows if r["cap"] == t], "name": t}
            for t in ("MOM", "MIM")], {"xaxis": {"tickangle": -60, "automargin": True}, "yaxis": axis("Max ratio error (%)"),
                                       "legend": {"orientation": "h", "x": 0, "y": 1.12}}, height=400),
        {"type": "tabs", "style": "select", "label": "Macro", "title": "Per-macro detail (layout sub-cell, trim history, branch table)",
         "tabs": [cap_macro_tab(r["cell"]) for r in cap_rows]},
    ], intro="Built using experimental `gLayout` (`../gLayout-ASAP7` with PR #128 merged on `FinFET-Backend`). Common-centroid "
             "differential placement with dummy perimeter rings, parasitic-insensitive bottom-plate NMOS discharge switches, and "
             "Magic 8.3 PEX iterative ratio trimming (≤ 0.0190% max ratio error, 24/24 DRC Clean, 24/24 LVS Match)."),
    section("Open-Source Digital Implementation Flow: sdm2bin Sinc<sup>3</sup> Decimator & Clock Generator", [
        note(f"Old panel title: “6 Macros”, prose “LVS (6/6 match)” — the export holds {len(DIG_MACROS)} macros (6 resolutions × 2 supplies). "
             f"The title says Sinc³; the resolution spec lists sinc{RES_SPECS[str(NBITS[0])]['sinc_order']}…sinc{RES_SPECS[str(NBITS[-1])]['sinc_order']}, "
             "and each macro schematic is titled “Synthesized Sinc2 + Sinc1 CIC Decimator”.", "muted"),
        kv("Flow summary (digital_macros.json)", [["Flow", DIGF.get("flow")], ["Site", f"`{DIGF.get('site')}`"],
                                                  ["Clock", f"{DIGF.get('clock_period_ns')} ns ({DIGF.get('clock_freq_mhz')} MHz)"],
                                                  ["Macros", DIGF.get("count")], ["All DRC clean / LVS match / sim pass",
                                                                                  f"{DIGF.get('all_drc_clean')} / {DIGF.get('all_lvs_match')} / {DIGF.get('all_sim_pass')}"]], cols=3),
        table("OpenROAD sdm2bin macros", [col("cell", "Digital macro", type="text"), col("res", "Target res", type="text"), col("osr", "OSR", digits=0),
                                         col("vdd", "V<sub>DD</sub>", unit="V", digits=2), col("fs", "f<sub>s</sub>", unit="Hz", si=True),
                                         col("fn", "f<sub>Nyq</sub>", unit="Hz", si=True), col("sc", "Synth cells", digits=0),
                                         col("sa", "Synth area", unit="µm²", digits=5), col("ssa", "Seq. area", unit="µm²", digits=5),
                                         col("ra", "Routed active / total cells", type="text"), col("rp", "Physical (fill/tap) cells", digits=0),
                                         col("die", "Die size (µm)", type="text"), col("core", "Core (µm)", type="text"), col("util", "Util", unit="%", digits=3),
                                         col("wl", "Wirelength", unit="µm", digits=5), col("vias", "Vias", digits=0), col("drt", "DRT viol.", digits=0),
                                         col("slack", "Setup slack", unit="s", si=True, digits=5), col("arr", "Data arrival", unit="s", si=True, digits=4),
                                         col("p", "Power", unit="W", si=True, digits=4), col("sim", "Gate-sim", type="status"),
                                         col("drc", "DRC", type="status"), col("lvs", "LVS", type="status")], dig_rows(), search=False),
        chart("sdm2bin scaling with resolution", [
            {"type": "scatter", "mode": "lines+markers", "x": [r["res"] for r in dig_rows() if r["vdd"] == v], "y": [r["p"] * 1e6 for r in dig_rows() if r["vdd"] == v],
             "name": f"Power @ {v} V", "meta": {"vdd": v}} for v in IDX["vdds"]] + [
            {"type": "scatter", "mode": "lines+markers", "x": [r["res"] for r in dig_rows() if r["vdd"] == IDX["vdds"][0]],
             "y": [r["sc"] for r in dig_rows() if r["vdd"] == IDX["vdds"][0]], "name": "Synth cells", "yaxis": "y2", "line": {"dash": "dot"}}],
            {"xaxis": axis("Resolution"), "yaxis": axis("Power (µW)"), "yaxis2": {"title": {"text": "Synthesized cells"}, "overlaying": "y", "side": "right", "showgrid": False}},
            height=300),
        {"type": "tabs", "style": "select", "label": "Macro", "title": "Per-macro detail (layout, schematic, cells, verification)",
         "tabs": [dig_tab(r["cell"]) for r in dig_rows()]},
    ], intro="Synthesized with **Yosys 0.65**, placed-and-routed with **OpenROAD 26Q2** in `gf180mcu_fd_sc_mcu7t5v0`, verified bit-exact "
             "with **Icarus Verilog** gate-level simulation, and signed off with **KLayout DRC (0 violations) & LVS (6/6 match)**. Converts "
             "the oversampled PDM bitstream directly into binary-encoded words `dout[N-1:0]` + `dout_valid`."),
]}


# ----------------------------------------------------------------------------- architectures page
def arch_md(aid):
    a = ARCH_SPECS[aid]
    return md(f"*Input & loop:* {a['input_arch']}\n\n{a['desc']}\n\n"
              "| a<sub>1</sub> | a<sub>2</sub> | b<sub>1</sub> | b<sub>2</sub> | c<sub>1</sub> | c<sub>2</sub> | g<sub>1</sub> |\n|---|---|---|---|---|---|---|\n"
              f"| {a['a1']} | {a['a2']} | {a['b1']} | {a['b2']} | {a['c1']} | {a['c2']} | {a['g1']} |\n\n"
              f"Shared C<sub>s</sub>/DAC: **{'yes' if a['shared_cs_dac'] else 'no'}** · VCM op-amp (arch spec): **{'yes' if a['use_vcm_opa'] else 'no'}** · "
              f"quantizer votes: **{a['multi_vote']}** · SQNR boost: **{a['sqnr_boost_db']} dB**\n\n*Reference:* {a.get('ref', '')}",
              title=f"{a['short']} — {a['name']}")


def group_mean_rows(key, label_of):
    rows = []
    for st in STAGES:
        v = VIEW_OF[st]
        groups = {}
        for c in CARDS:
            groups.setdefault(c[key], []).append(c["metrics"][v])
        for g, ms in groups.items():
            n = len(ms)
            rows.append({"stage": st, "g": label_of(g), "n": n, "enob": sum(m["enob"] for m in ms) / n,
                         "emax": max(m["enob"] for m in ms), "p": sum(m["power_uw"] for m in ms) / n * 1e-6,
                         "fs": sum(m["fom_schreier_db"] for m in ms) / n, "fsb": max(m["fom_schreier_db"] for m in ms),
                         "fw": sum(m["fom_walden_fj"] for m in ms) / n * 1e-15, "fwb": min(m["fom_walden_fj"] for m in ms) * 1e-15})
    return rows


MEAN_COLS = [col("stage", "Stage", type="text"), col("g", "Group", type="text"), col("n", "Cards", digits=0),
             col("enob", "Mean ENOB", unit="bits", digits=4), col("emax", "Best ENOB", unit="bits", digits=4),
             col("p", "Mean power", unit="W", si=True), col("fs", "Mean FoM<sub>S</sub>", unit="dB", digits=4),
             col("fsb", "Best FoM<sub>S</sub>", unit="dB", digits=4), col("fw", "Mean FoM<sub>W</sub>", unit="J/step", si=True),
             col("fwb", "Best FoM<sub>W</sub>", unit="J/step", si=True)]

tradeoff = {"columns": {k: [] for k in ("power", "enob", "sndr", "sfdr", "dr", "fom_s", "fom_w", "area", "arch", "cap", "res", "vdd", "stage", "design", "label")}}
for st in STAGES:
    for c in CARDS:
        m = c["metrics"][VIEW_OF[st]]
        T = tradeoff["columns"]
        for k, v in (("power", m["power_uw"] * 1e-6), ("enob", m["enob"]), ("sndr", m["sndr_db"]), ("sfdr", m["sfdr_db"]), ("dr", m["dr_db"]),
                     ("fom_s", m["fom_schreier_db"]), ("fom_w", m["fom_walden_fj"] * 1e-15), ("area", c["layout_summary"]["area_um2"]),
                     ("arch", c["arch_id"]), ("cap", c["cap_type"]), ("res", f"{c['nbits']}b"), ("vdd", c["vdd"]), ("stage", st),
                     ("design", c["card_id"]), ("label", c["card_id"])):
            T[k].append(v)
ARCH_DIM = {"key": "arch", "label": "Architecture", "type": "cat", "labels": {a: ARCH_SPECS[a]["short"] for a in ARCH_ORDER}, "order": ARCH_ORDER}
CAP_DIM = {"key": "cap", "label": "Capacitor", "type": "cat", "labels": CAP_LABEL, "order": ["mom", "mim"]}
RES_DIM = {"key": "res", "label": "Resolution", "type": "cat", "order": [f"{n}b" for n in NBITS]}
arch_page = {"blocks": [
    note(MODEL_NOTE, "warn"),
    section("4 Switched-Capacitor ΣΔ Input & Loop Architectures Explored",
            [arch_md(a) for a in ARCH_ORDER] + [
                table("Per-architecture means (24 cards each)", MEAN_COLS, group_mean_rows("arch_id", lambda g: ARCH_SPECS[g]["short"]),
                      stage_column="stage", search=False, span=2,
                      caption="The old cards printed “12-Card Mean (<stage>)” — each architecture has 24 cards (6 resolutions × 2 caps × 2 supplies). "
                              "The old cards also printed “undefined” for the description, c<sub>ff</sub>, g<sub>res</sub> and STF/swing notes "
                              "(fields absent from the data); the cards above show the stored description and all seven coefficients.")],
            cols=2, intro="Quantitative comparison of the 4 distinct loop topologies across signal transfer function (STF), noise transfer "
                          "function (NTF), integrator output swing reduction, op-amp linearity requirements, and reference buffer isolation."),
    {"type": "explorer", "title": "Architecture Performance Tradeoff Chart (ENOB vs Power & FoM)", "src": write("data/arch_tradeoff.json", tradeoff),
     "dims": [{"key": "power", "label": "Total power", "unit": "W", "si": True, "log": True, "better": "low"},
              {"key": "enob", "label": "ENOB", "unit": "bit", "better": "high"}, {"key": "sndr", "label": "SNDR", "unit": "dB", "better": "high"},
              {"key": "sfdr", "label": "SFDR", "unit": "dB", "better": "high"}, {"key": "dr", "label": "DR", "unit": "dB", "better": "high"},
              {"key": "fom_s", "label": "FoM Schreier", "unit": "dB", "better": "high"},
              {"key": "fom_w", "label": "FoM Walden", "unit": "J/step", "si": True, "log": True, "better": "low"},
              {"key": "area", "label": "Layout area", "unit": "µm²", "better": "low"}, ARCH_DIM, CAP_DIM, RES_DIM],
     "x": "power", "y": "enob", "color": "arch", "symbol": "cap", "filters": ["arch", "cap", "res"], "design_key": "design", "label_key": "label",
     "hover": ["fom_s", "fom_w", "arch", "cap"], "height": 460,
     "presets": [{"label": "ENOB vs power (old chart)", "x": "power", "y": "enob", "color": "arch", "symbol": "cap"},
                 {"label": "FoM_S vs power", "x": "power", "y": "fom_s", "color": "arch"},
                 {"label": "FoM_W vs ENOB", "x": "enob", "y": "fom_w", "color": "arch"},
                 {"label": "Per resolution", "x": "power", "y": "enob", "facet": "res"}],
     "caption": "All 96 cards at the selected stage, power (log) vs ENOB, colour = architecture, symbol = capacitor (old chart: MIM drawn "
                "with bigger dots). Click a point to open the card."},
    section("MOM (M1–M4 Interdigitated) vs Option-B MIM (M4–M5) Capacitor Tradeoffs", [
        md(f"**C<sub>u,nom</sub> = {CAP_SPECS[t]['cu_nom_ff']} fF**\n\n{CAP_SPECS[t]['desc']}", title=f"Custom gLayout {CAP_SPECS[t]['name']}")
        for t in ("mom", "mim")] + [
        table("Per-capacitor means (48 cards each)", MEAN_COLS, group_mean_rows("cap_type", lambda g: CAP_SPECS[g]["name"]), stage_column="stage",
              search=False, span=2, caption="The old cards printed “undefined” for layers, density, notes, bottom-plate parasitic and Pelgrom "
                                             "A<sub>C</sub> (fields absent from `cap_specs`); the stored description is shown instead."),
        table("Cap-macro statistics by type", [col("t", "Type", type="text"), col("n", "Macros", digits=0), col("cu", "Mean C<sub>u,ext</sub>", unit="F", si=True),
                                               col("area", "Mean macro area", unit="µm²", digits=5), col("err", "Worst ratio error", unit="%", digits=3)],
              [[t.upper(), len(ms), sum(m["analysis"]["cu_ext_ff"] for m in ms) / len(ms) * 1e-15, sum(m["area_um2"] for m in ms) / len(ms),
                max(m["analysis"]["max_ratio_err_pct"] for m in ms)] for t in ("mom", "mim") for ms in [[m for m in CAP_MACROS.values() if m["cap_type"] == t]]],
              search=False, csv=False, span=2),
    ], cols=2),
]}


# ----------------------------------------------------------------------------- design-space page
SW = SWEEP
cloud, pareto, sel_cards = SW["cloud_points"], SW["pareto_points"], SW["selected_cards"]
GROUPS = list((SW.get("pareto_by_group") or {}).keys())


def pt_label(p):
    return f"{p['nbits']}b · OSR {p['osr']} · {p['vdd']} V · {p['cap_type'].upper()} · {ARCH_SPECS[p['arch_id']]['short']} · C_u×{p.get('cu_scale')}"


def hover_pt(p):
    s = (f"<b>{pt_label(p)}</b><br>ENOB {p['enob']} b · SNDR {p.get('sndr_db')} dB<br>P = {p['power_uw']} µW · FoM_W {p.get('fom_walden_fj')} fJ · "
         f"FoM_S {p.get('fom_schreier_db')} dB<br>f_s {p.get('fs_mhz')} MHz · f_B {p.get('fb_khz')} kHz")
    if p.get("opa1_id"):
        s += f"<br>OPA1 {p['opa1_id']} · OPA2 {p.get('opa2_id')} · comp {p.get('comp_id')}"
    return s


def group_charts(g):
    pts = pareto if g == "all" else SW["pareto_by_group"][g]
    out = []
    for name, xk, yk, xt, yt, xl, yl in (("pareto", "power_uw", "enob", "Total power (µW, log scale)", "ENOB (bits)", True, False),
                                          ("fom", "fom_walden_fj", "fom_schreier_db", "Walden FoM (fJ/step, log)", "Schreier FoM (dB)", True, False)):
        data = [{"type": "scattergl", "mode": "markers", "x": [p[xk] for p in cloud], "y": [p[yk] for p in cloud], "name": f"Sampled cloud ({len(cloud)})",
                 "marker": {"size": 4, "color": "rgba(100,116,139,0.35)"}, "hoverinfo": "skip"}]
        for a in ARCH_ORDER:
            sub = [p for p in pts if p["arch_id"] == a]
            if sub:
                data.append({"type": "scatter", "mode": "markers", "x": [p[xk] for p in sub], "y": [p[yk] for p in sub],
                             "name": f"Pareto · {ARCH_SPECS[a]['short']}", "marker": {"size": 9, "color": ARCH_COLORS[a]},
                             "text": [hover_pt(p) for p in sub], "hovertemplate": "%{text}<extra></extra>"})
        fig = {"data": data, "layout": {"xaxis": axis(xt, type="log" if xl else "linear"), "yaxis": axis(yt)}}
        out.append(write(f"data/dse/{g}_{name}.json", fig))
    return out, len(pts)


facet_tabs = []
for g in ["all"] + GROUPS:
    (f1, f2), npts = group_charts(g)
    lab = (f"All 16 Groups Combined ({SW['total_evaluated']:,} Evaluated · {SW['pareto_count']} Global Pareto)" if g == "all"
           else f"{g} ({npts} Pareto Points)")
    facet_tabs.append({"label": lab, "blocks": [
        {"type": "chart", "title": "Pareto Frontier: ENOB (bits) vs Total Power (µW)", "src": f1, "height": 380, "span": 1,
         "caption": f"{SW['total_evaluated']:,} evaluated · {SW['feasible_count']:,} feasible · {npts} Pareto"
                    + ("" if npts else " — this group has no Pareto points (no feasible 1.8 V configuration in the sweep).")},
        {"type": "chart", "title": "Schreier FoM (dB) vs Walden FoM (fJ/conv-step) across Topologies", "src": f2, "height": 380, "span": 1,
         "caption": "Showing feasible cloud + Pareto frontier (the stored cloud is an 809-point sample incl. infeasible points)."}]})

# columnar explorer data (cloud + pareto + delivered cards; exact duplicates of a Pareto point dropped from the cloud)
ex = {k: [] for k in ("enob", "sndr", "power", "fom_w", "fom_s", "area", "fs", "fb", "osr", "nbits", "cu_scale", "cu", "a0", "leak", "tau",
                      "t_phi2", "settle_ratio", "sigma_c", "yield", "arch", "cap", "supply", "set", "feasible", "group", "res", "vdd",
                      "design", "delivered", "label", "opa1", "opa2", "comp")}
pkey = lambda p: (p["nbits"], p["osr"], p["vdd"], p["cap_type"], p["arch_id"], p.get("cu_scale"), p["enob"], p["power_uw"])
pset = {pkey(p) for p in pareto}


def ex_add(p, setname, design=None):
    E = ex
    vt = "1v8" if p["vdd"] < 2.5 else "3v3"
    for k, v in (("enob", p.get("enob")), ("sndr", p.get("sndr_db")), ("power", mul(p.get("power_uw"), 1e-6)), ("fom_w", mul(p.get("fom_walden_fj"), 1e-15)),
                 ("fom_s", p.get("fom_schreier_db")), ("area", p.get("area_um2")), ("fs", mul(p.get("fs_mhz"), 1e6)), ("fb", mul(p.get("fb_khz"), 1e3)),
                 ("osr", p.get("osr")), ("nbits", p.get("nbits")), ("cu_scale", p.get("cu_scale")), ("cu", mul(p.get("cu_ff"), 1e-15)),
                 ("a0", p.get("a0_1_db")), ("leak", p.get("leak_enob_loss")), ("tau", mul(p.get("tau_settle_ns"), 1e-9)),
                 ("t_phi2", mul(p.get("t_phi2_ns"), 1e-9)), ("settle_ratio", p.get("settle_ratio")), ("sigma_c", p.get("sigma_dc_c_pct")),
                 ("yield", p.get("yield_pct")), ("arch", p["arch_id"]), ("cap", p["cap_type"]), ("supply", f"{p['vdd']} V"), ("set", setname),
                 ("feasible", "yes" if p.get("feasible", True) else "no"), ("group", f"{vt}_{p['cap_type']}_{p['arch_id']}"),
                 ("res", f"{p['nbits']}b"), ("vdd", p["vdd"]), ("design", design), ("delivered", design is not None),
                 ("label", design or pt_label(p)), ("opa1", p.get("opa1_id")), ("opa2", p.get("opa2_id")), ("comp", p.get("comp_id"))):
        E[k].append(v)


for p in cloud:
    if pkey(p) not in pset:
        ex_add(p, "cloud")
for p in pareto:
    ex_add(p, "pareto")
for p in sel_cards:
    ex_add(p, "delivered", p["card_id"] if p["card_id"] in DES_IDS else None)
n_dup = len(cloud) + len(pareto) + len(sel_cards) - len(ex["enob"])

DSE_DIMS = [
    {"key": "power", "label": "Total power", "unit": "W", "si": True, "log": True, "better": "low"},
    {"key": "enob", "label": "ENOB", "unit": "bit", "better": "high"},
    {"key": "sndr", "label": "SNDR", "unit": "dB", "better": "high"},
    {"key": "fom_w", "label": "FoM Walden", "unit": "J/step", "si": True, "log": True, "better": "low"},
    {"key": "fom_s", "label": "FoM Schreier", "unit": "dB", "better": "high"},
    {"key": "area", "label": "Area (sweep model)", "unit": "µm²", "log": True, "better": "low"},
    {"key": "fs", "label": "Sampling rate f_s", "unit": "Hz", "si": True},
    {"key": "fb", "label": "Signal bandwidth f_B", "unit": "Hz", "si": True, "log": True, "better": "high"},
    {"key": "osr", "label": "OSR", "log": True},
    {"key": "nbits", "label": "Target resolution", "unit": "bit"},
    {"key": "cu_scale", "label": "C_u scale"},
    {"key": "cu", "label": "Unit cap C_u (Pareto only)", "unit": "F", "si": True},
    {"key": "a0", "label": "Stage-1 op-amp A0", "unit": "dB", "better": "high"},
    {"key": "leak", "label": "Finite-gain ENOB loss", "unit": "bit", "better": "low"},
    {"key": "tau", "label": "Stage-1 settling τ", "unit": "s", "si": True, "log": True, "better": "low"},
    {"key": "t_phi2", "label": "φ2 time (Pareto only)", "unit": "s", "si": True},
    {"key": "settle_ratio", "label": "t_φ2/τ (Pareto only)"},
    {"key": "sigma_c", "label": "Cap mismatch σ(ΔC/C)", "unit": "%", "better": "low"},
    {"key": "yield", "label": "Parametric ENOB yield", "unit": "%", "better": "high"},
    ARCH_DIM, CAP_DIM,
    {"key": "supply", "label": "Supply", "type": "cat", "order": ["1.8 V", "3.3 V"]},
    {"key": "set", "label": "Point set", "type": "cat", "labels": {"cloud": "Sampled cloud", "pareto": "Global Pareto", "delivered": "Delivered card"},
     "order": ["cloud", "pareto", "delivered"]},
    {"key": "feasible", "label": "Feasible", "type": "cat", "order": ["yes", "no"]},
    {"key": "group", "label": "Group (V_DD × cap × arch)", "type": "cat", "order": GROUPS},
    {"key": "res", "label": "Resolution", "type": "cat", "order": [f"{n}b" for n in sorted({p['nbits'] for p in cloud} | set(NBITS))]},
]


def sc(x, y, name, **kw):
    t = {"type": "scatter", "mode": "markers", "x": x, "y": y, "name": name}
    t.update(kw)
    return t


F = SW["facets"]


def facet_tab(key):
    f = F[key]
    title = f["title"]
    blocks = []
    if key in ("fom_walden_vs_enob", "fom_schreier_vs_power", "area_vs_enob"):
        xk, yk = f["x_key"], f["y_key"]
        lab = {"enob": "ENOB (bits)", "fom_walden_fj": "FoM Walden (fJ/conv-step)", "power_uw": "Total power (µW)",
               "fom_schreier_db": "FoM Schreier (dB)", "area_um2": "Total macro area (µm², sweep model)"}
        data = [sc([p[xk] for p in f["pareto"] if p["arch_id"] == a], [p[yk] for p in f["pareto"] if p["arch_id"] == a], ARCH_SPECS[a]["short"],
                   marker={"size": 9, "color": ARCH_COLORS[a]}, text=[hover_pt(p) for p in f["pareto"] if p["arch_id"] == a],
                   hovertemplate="%{text}<extra></extra>") for a in ARCH_ORDER]
        logx = xk in ("power_uw",)
        logy = yk in ("fom_walden_fj", "area_um2")
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis(lab[xk], type="log" if logx else "linear"), "yaxis": axis(lab[yk], type="log" if logy else "linear")}}), "height": 420,
            "caption": f"{len(f['pareto'])} global Pareto points, coloured by architecture."})
    elif key == "osr_vs_sndr":
        data = []
        for a in ARCH_ORDER:
            cur = f["curves_by_arch"].get(a) or []
            for k2, dash, nm in (("max_sndr_db", "solid", "max"), ("p90_sndr_db", "dot", "P90"), ("mean_sndr_db", "dash", "mean")):
                data.append({"type": "scatter", "mode": "lines+markers", "x": [x["osr"] for x in cur], "y": [x[k2] for x in cur],
                             "name": f"{ARCH_SPECS[a]['short']} {nm}", "line": {"color": ARCH_COLORS[a], "dash": dash}, "legendgroup": a})
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("OSR", type="log", tickvals=SW["sweep_dimensions"]["osrs"]), "yaxis": axis("SNDR (dB)")}}), "height": 420,
            "caption": "Mean / P90 / max SNDR of the sampled configurations per OSR and architecture."})
    elif key == "gain_a0_vs_leakage":
        arches = sorted({p["opa1_arch"] for p in f["points"]})
        data = [sc([p["a0_1_db"] for p in f["points"] if p["opa1_arch"] == oa], [p["leak_enob_loss"] for p in f["points"] if p["opa1_arch"] == oa], oa,
                   text=[f"{p['nbits']}b OSR {p['osr']} {p['vdd']} V {p['arch_id']} · ENOB {p['enob']}" for p in f["points"] if p["opa1_arch"] == oa],
                   hovertemplate="A0 %{x} dB · loss %{y} b<br>%{text}<extra></extra>") for oa in arches]
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("Stage-1 op-amp DC gain A0 (dB)"), "yaxis": axis("Finite-gain NTF leakage ENOB loss (bits)")}}), "height": 400,
            "caption": f"{len(f['points'])} points, coloured by the Stage-1 op-amp architecture."})
    elif key == "bandwidth_fb_vs_power":
        data = []
        for fe, colr in ((False, "rgba(100,116,139,0.45)"), (True, "#16a34a")):
            sub = [p for p in f["points"] if bool(p.get("feasible")) == fe]
            if sub:
                data.append(sc([p["fb_khz"] * 1e3 for p in sub], [p["power_uw"] for p in sub], "feasible" if fe else "infeasible",
                               marker={"size": 6 if fe else 4, "color": colr}, text=[hover_pt(p) for p in sub], hovertemplate="%{text}<extra></extra>"))
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("Passband bandwidth f_B (Hz)", type="log"), "yaxis": axis("Total power (µW)", type="log")}}), "height": 400,
            "caption": f"{len(f['points'])} sampled points."})
    elif key in ("cap_type_mom_vs_mim", "architecture_comparison", "vdd_1v8_vs_3v3"):
        s = f["summary"]
        ks = list(s.keys())
        cols_all = sorted({c2 for v in s.values() for c2 in v.keys()} - {"name", "short"})
        nice = {"count": "Feasible count", "mean_enob": "Mean ENOB (b)", "max_enob": "Max ENOB (b)", "mean_power_uw": "Mean power (µW)",
                "best_fom_schreier_db": "Best FoM_S (dB)", "best_fom_walden_fj": "Best FoM_W (fJ)", "cu_nom_ff": "C_u,nom (fF)",
                "mean_area_um2": "Mean area (µm²)", "vdd": "V_DD (V)"}
        rows = [[k2, s[k2].get("name") or s[k2].get("short") or k2] + [s[k2].get(c2) for c2 in cols_all] for k2 in ks]
        blocks.append(table(title, [col("k", "Key", type="text"), col("n", "Name", type="text")] + [col(c2, nice.get(c2, c2), digits=5) for c2 in cols_all],
                            rows, search=False, csv=True,
                            caption="Summary over the feasible sweep points." + (" The 1.8 V domain has no feasible point in the sweep." if key == "vdd_1v8_vs_3v3" else "")))
        if "mean_enob" in cols_all:
            blocks.append(chart(None, [{"type": "bar", "x": [s[k2].get("short") or s[k2].get("name") or k2 for k2 in ks], "y": [s[k2].get("mean_enob") for k2 in ks], "name": "Mean ENOB"},
                                       {"type": "bar", "x": [s[k2].get("short") or s[k2].get("name") or k2 for k2 in ks], "y": [s[k2].get("best_fom_schreier_db") for k2 in ks],
                                        "name": "Best FoM_S", "yaxis": "y2"}],
                                {"barmode": "group", "yaxis": axis("Mean ENOB (bits)"), "yaxis2": {"title": {"text": "Best FoM_S (dB)"}, "overlaying": "y", "side": "right", "showgrid": False}},
                                height=300))
    elif key == "settling_vs_clock_freq":
        data = [sc([p["fs_mhz"] * 1e6 for p in f["points"] if p["arch_id"] == a], [p["tau_settle_ns"] for p in f["points"] if p["arch_id"] == a],
                   f"τ_settle · {ARCH_SPECS[a]['short']}", marker={"color": ARCH_COLORS[a], "size": 8},
                   text=[f"{p['nbits']}b OSR {p['osr']} {p['vdd']} V {p['cap_type']} · t_φ2 {p['t_phi2_ns']} ns · ratio {p['settle_ratio']} · ENOB {p['enob']}"
                         for p in f["points"] if p["arch_id"] == a], hovertemplate="f_s %{x:.3s}Hz · τ %{y} ns<br>%{text}<extra></extra>") for a in ARCH_ORDER]
        data.append(sc([p["fs_mhz"] * 1e6 for p in f["points"]], [p["t_phi2_ns"] for p in f["points"]], "available φ2 time t_φ2",
                       marker={"symbol": "line-ew-open", "size": 12, "color": "#e11d48"}))
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("Clock frequency f_s (Hz)"), "yaxis": axis("τ_settle / t_φ2 (ns)", type="log")}}), "height": 400,
            "caption": f"{len(f['points'])} points; the red dashes mark the available φ2 half-period for each point."})
    elif key == "mismatch_sigma_vs_yield":
        data = [sc([p["sigma_dc_c_pct"] for p in f["points"] if p["cap_type"] == t], [p["yield_pct"] for p in f["points"] if p["cap_type"] == t],
                   CAP_LABEL[t], marker={"size": 8}, text=[f"{p['nbits']}b {p['arch_id']} C_u×{p['cu_scale']} · ENOB {p['enob']}" for p in f["points"] if p["cap_type"] == t],
                   hovertemplate="σ %{x} % · yield %{y} %<br>%{text}<extra></extra>") for t in ("mom", "mim")]
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("Capacitor ratio mismatch σ(ΔC/C) (%)"), "yaxis": axis("Parametric ENOB yield (%)")}}), "height": 380,
            "caption": f"{len(f['points'])} points."})
    elif key == "deliverable_48_overlay":
        cards = f["cards"]
        data = [sc([p["power_uw"] for p in pareto], [p["enob"] for p in pareto], "Global Pareto (sweep)", marker={"size": 7, "color": "rgba(100,116,139,0.6)"},
                   text=[hover_pt(p) for p in pareto], hovertemplate="%{text}<extra></extra>")]
        for a in ARCH_ORDER:
            sub = [p for p in cards if p["arch_id"] == a]
            data.append(sc([p["power_uw"] for p in sub], [p["enob"] for p in sub], f"Delivered · {ARCH_SPECS[a]['short']}",
                           marker={"size": 10, "color": ARCH_COLORS[a], "symbol": ["diamond" if p["cap_type"] == "mim" else "circle" for p in sub],
                                   "line": {"width": 1, "color": "#0f172a"}},
                           customdata=[p["card_id"] for p in sub], text=[f"<b>{p['card_id']}</b><br>ENOB {p['enob']} · P {p['power_uw']} µW · FoM_S {p['fom_schreier_db']} dB" for p in sub],
                           hovertemplate="%{text}<extra>click to open</extra>"))
        blocks.append({"type": "chart", "title": title, "src": write(f"data/dse/facet_{key}.json", {"data": data, "layout": {
            "xaxis": axis("Total power (µW)", type="log"), "yaxis": axis("ENOB (bits)")}}), "height": 440, "link_designs": True,
            "caption": f"All {len(cards)} delivered cards (old title says 48) over the {len(pareto)} sweep Pareto points; diamonds = MIM. "
                       "Click a card to open it."})
    return {"label": title.split(" — ")[0][:60], "blocks": blocks}


win_rows = []
for w in sel_cards:
    win_rows.append({"facet": f"{w['nbits']}b · {w['vdd']}V · {w['cap_type'].upper()}", "arch": w["arch_id"], "id": w["card_id"], "osr": w["osr"],
                     "fs": w["fs_mhz"] * 1e6, "fb": w["fb_khz"] * 1e3, "enob": w["enob"], "sndr": w["sndr_db"], "sfdr": w.get("sfdr_db"),
                     "p": w["power_uw"] * 1e-6, "fw": w["fom_walden_fj"] * 1e-15, "fs_db": w["fom_schreier_db"], "area": w.get("area_um2"),
                     "o1": opa_link(DATA[w["card_id"]]["components"]["opa1"]["key"]) if w["card_id"] in DATA else w.get("opa1_id"),
                     "o2": opa_link(DATA[w["card_id"]]["components"]["opa2"]["key"]) if w["card_id"] in DATA else w.get("opa2_id"),
                     "cmp": sa_link(w.get("comp_id")),
                     "swi": sw_link(w.get("sw_in_id")), "vdd": w["vdd"], "_design": w["card_id"] if w["card_id"] in DES_IDS else None})
for r in win_rows:
    if r["_design"] is None:
        del r["_design"]

dims_rows = [[k, ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)] for k, v in SW["sweep_dimensions"].items()]
dse_page = {"intro": "Exhaustive design-space exploration across OSR, sampling rate f<sub>s</sub>, unit capacitance C<sub>u</sub>, Stage-1/2 op-amps, "
                     "comparators, switches, and loop topologies. Select any facet below to inspect its Pareto frontier and feasible cloud.",
            "blocks": [
                note(f"The sweep (`sdmgen.sweep`) evaluates the analytical modulator model only — no SPICE. It spans target resolutions "
                     f"{SW['sweep_dimensions']['resolutions'][0]}–{SW['sweep_dimensions']['resolutions'][-1]} b and OSR "
                     f"{SW['sweep_dimensions']['osrs'][0]}–{SW['sweep_dimensions']['osrs'][-1]}, so the delivered 16–20-bit cards (OSR 512–2048) lie "
                     f"outside its grid; their points use the sweep's `selected_cards` numbers (ENOB/power equal the full-chip view, area is the sweep's "
                     f"area model). The file stores an {len(cloud)}-point sample of the {SW['total_evaluated']:,} evaluations (incl. infeasible points) "
                     f"plus the {len(pareto)} global Pareto points; none of the 1.8 V configurations is feasible, so all Pareto points are 3.3 V.", "warn"),
                {"type": "stats", "items": [{"label": "Evaluated configurations", "value": f"{SW['total_evaluated']:,}"},
                                            {"label": "Feasible", "value": f"{SW['feasible_count']:,}"},
                                            {"label": "Global Pareto points", "value": str(SW["pareto_count"])},
                                            {"label": "Stored cloud sample", "value": str(len(cloud))},
                                            {"label": "Library combos per V_DD", "value": str(SW["sweep_dimensions"].get("lib_combos_per_vdd"))},
                                            {"label": "Sweep run time", "value": f"{SW.get('elapsed_sec')} s"}],
                 "title": "12-Facet Parametric Design-Space Explorer (362,880 Evaluated Configurations)"},
                table("Sweep dimensions", [col("k", "Dimension", type="text"), col("v", "Values", type="text")], dims_rows, search=False, csv=False),
                {"type": "tabs", "style": "select", "label": "Select facet (Res × VDD × Cap)", "title": "Pareto frontier & feasible cloud per group",
                 "tabs": [{"label": t["label"], "blocks": [section(None, t["blocks"], cols=2)]} for t in facet_tabs],
                 "caption": "Old-site facet selector: 16 groups V<sub>DD</sub> × capacitor × architecture (despite the “Res × V<sub>DD</sub> × Cap” "
                            "label). Grey = stored cloud sample, colour = Pareto points of the selected group by architecture."},
                table("Winning cards (sweep selected_cards)", [
                    col("facet", "Facet", type="text"), col("arch", "Architecture", type="text"), col("id", "Winning card ID", type="design"),
                    col("osr", "OSR", digits=0), col("fs", "f<sub>s</sub>", unit="Hz", si=True), col("fb", "f<sub>B</sub>", unit="Hz", si=True),
                    col("enob", "ENOB", unit="bits", digits=4, better="high"), col("sndr", "SNDR", unit="dB", digits=5), col("sfdr", "SFDR", unit="dB", digits=5),
                    col("p", "Power", unit="W", si=True, digits=5, better="low"), col("fw", "FoM<sub>W</sub>", unit="J/step", si=True, digits=5, better="low"),
                    col("fs_db", "FoM<sub>S</sub>", unit="dB", digits=5, better="high"), col("area", "Area (model)", unit="µm²", digits=5),
                    col("o1", "Stage-1 OPA", type="text", md=True), col("o2", "Stage-2 OPA", type="text", md=True), col("cmp", "Comparator", type="text", md=True),
                    col("swi", "Input switch", type="text", md=True), col("vdd", "V<sub>DD</sub>", unit="V", digits=2)], win_rows, page_size=100,
                      caption="Click a row to open the card. The old C<sub>u</sub> column was always “—” (not stored) and is omitted."),
                {"type": "explorer", "title": "Design-space explorer (all stored points)", "src": write("data/dse_explorer.json", {"columns": ex}),
                 "dims": DSE_DIMS, "x": "power", "y": "enob", "color": "arch", "symbol": "set",
                 "filters": ["set", "arch", "cap", "supply", "feasible", "res", "group", "enob", "power"],
                 "highlight": "delivered", "highlight_label": "Delivered cards", "design_key": "design", "label_key": "label",
                 "hover": ["sndr", "fom_w", "fom_s", "osr", "fs", "cu_scale", "set", "feasible", "opa1", "opa2", "comp"], "pareto_default": True, "height": 540,
                 "presets": [{"label": "ENOB vs power (old chart 1)", "x": "power", "y": "enob", "color": "arch", "pareto": True},
                             {"label": "FoM_S vs FoM_W (old chart 2)", "x": "fom_w", "y": "fom_s", "color": "arch", "pareto": False},
                             {"label": "FoM_W vs ENOB", "x": "enob", "y": "fom_w", "color": "arch", "logy": True},
                             {"label": "FoM_S vs power", "x": "power", "y": "fom_s", "color": "arch"},
                             {"label": "Area vs ENOB", "x": "enob", "y": "area", "color": "cap"},
                             {"label": "f_B vs power", "x": "fb", "y": "power", "color": "feasible", "logy": True},
                             {"label": "A0 vs leakage loss", "x": "a0", "y": "leak", "color": "arch", "pareto": False},
                             {"label": "Settling τ vs f_s", "x": "fs", "y": "tau", "color": "arch", "pareto": False},
                             {"label": "Mismatch σ vs yield", "x": "sigma_c", "y": "yield", "color": "cap", "pareto": False},
                             {"label": "Per architecture", "x": "power", "y": "enob", "facet": "arch"},
                             {"label": "Per supply", "x": "power", "y": "enob", "facet": "supply"},
                             {"label": "Per capacitor", "x": "power", "y": "enob", "facet": "cap"}],
                 "caption": f"{len(ex['enob'])} points = {len(cloud)} cloud + {len(pareto)} Pareto + {len(sel_cards)} delivered cards"
                            f"{f' ({n_dup} cloud duplicates of Pareto points dropped)' if n_dup else ''}. Highlighted rings = delivered cards (click to "
                            "open). Use the *Group* chips to reproduce the old facet selector, *Point set* to hide the cloud."},
                {"type": "tabs", "style": "select", "label": "Facet", "title": "The 12 stored facets of sweep.json",
                 "tabs": [facet_tab(k) for k in F],
                 "caption": "`sweep.json` stores twelve facet views; the old page drew only the two charts above. All twelve are reproduced here."},
            ]}


# ----------------------------------------------------------------------------- methodology page
method_page = {"blocks": [
    section("End-to-End Automated Mixed-Signal ΣΔ ADC Design & Verification Flow", [
        md("- **Op-Amps (`../opa-gen-gemini4`, 288 designs)**: Multi-objective scoring across DC gain A<sub>0,PEX</sub> (suppressing NTF zero "
           "leakage), unity-gain bandwidth UGB<sub>PEX</sub> (≥ 8–12× f<sub>s</sub> for <0.1 LSB incomplete settling), input-referred noise, and power.\n"
           "- **Quantizers (`../sa-gen-gemini4` + `../sar-gen-gemini4`, 96 designs)**: Dynamic regenerative StrongArm & Miyahara latches selected for "
           "minimum kickback, decision delay, and energy/decision.\n"
           "- **Switches (`../switch-gen-gemini4`, 125 designs)**: Bootstrapped DNW switches for low-THD input sampling and low-charge-injection "
           "transmission gates for summing junctions.", title="1. Systematic Component Selection from GF180 Libraries",
           caption="Reused blocks are browsable in the hub's [Op-amps](#/opa), [Sense amps](#/sa), [SAR ADCs](#/sar) and [Switches](#/switch) tabs; "
                   "each card's component table links to the exact designs."),
        md("- Built on experimental `gLayout` (`../gLayout-ASAP7` with PR #128 merged on `FinFET-Backend`).\n"
           "- Generates 24 common-centroid differential capacitor macros with dummy perimeter shields, dedicated North sampling plates, and on-macro "
           "NMOS bottom-plate discharge switches.\n"
           "- **Closed-Loop Magic PEX Ratio Trimming**: Iteratively adjusts unit finger length / MIM plate dimensions until extracted loop coefficients "
           "a<sub>1</sub>, a<sub>2</sub> match target specs within ≤ 0.0190%.", title="2. Custom `gLayout` MOM & Option-B MIM SC Cap Generator",
           caption=f"The export contains {len(CAP_MACROS)} cap macros (see **Macros**)."),
        md("- Implements a 3rd-order Cascaded Integrator-Comb (Sinc<sup>3</sup>) decimation filter, frame controller, and non-overlapping two-phase "
           "clock generator in Verilog RTL.\n"
           "- Synthesized with **Yosys 0.65** and placed-and-routed with **OpenROAD 26Q2** in `gf180mcu_fd_sc_mcu7t5v0` across all 6 "
           "(Resolution × V<sub>DD</sub>) corners.\n"
           "- Verified bit-exact with **Icarus Verilog** gate-level simulation and signed off with **KLayout DRC (0 violations) & flat LVS (6/6 match)**.",
           title="3. Open-Source Digital Flow for `sdm2bin` Sinc<sup>3</sup> Decimator",
           caption=f"The export contains {len(DIG_MACROS)} sdm2bin macros (6 resolutions × 2 supplies). Inconsistency in the source data: the "
                   f"per-resolution spec lists sinc{RES_SPECS[str(NBITS[0])]['sinc_order']}…sinc{RES_SPECS[str(NBITS[-1])]['sinc_order']}, "
                   "while every macro schematic is titled “Synthesized Sinc2 + Sinc1 CIC Decimator”."),
        md("- All SPICE transient simulations execute remotely on the 33-node compute farm via `sc submit` using `ngspice-46` with GF180MCU-D models "
           "(including `sm141064.ngspice cap_mim`).\n"
           "- Evaluates 3 physical stages (`Pre-Layout`, `Post-Cap-PEX`, `Full-Chip PEX`), coherent FFT ENOB/SNDR/SFDR, Dynamic Range sweep, DNL/INL "
           "linearity, **9-Corner PVT**, and **100-Run Monte Carlo** mismatch resilience.", title="4. Compute-Farm Multi-Testbench SPICE & Variation Resilience",
           caption="See the note below for which of these quantities come from SPICE and which from the analytical model."),
    ], cols=2),
    section("Verification stages on the hub", [
        md("| Old site (Verification Stage) | Hub simulation stage | What is extracted / simulated |\n|---|---|---|\n"
           + "\n".join(f"| {OLD_STAGE[st]} | {lab} | {STAGE_NOTES[st]} |" for st, lab in
                       (("pre", "Pre-PEX"), ("partial", "Partial post-PEX"), ("full", "Full post-PEX"))), title="Stage mapping"),
        note(MODEL_NOTE, "warn"), note(DATA_CAVEATS, "warn"),
        md("- **From SPICE (ngspice transient, compute farm):** integrator output swings (V<sub>out1</sub>, V<sub>out2</sub>), analog supply current, "
           "the first bitstream cycles of each view, per-corner deck success flags.\n"
           "- **From the analytical model:** ENOB, SNDR, SNR, SFDR, THD, DR, MSA, NTF slope, power breakdown, FoMs, noise budget, settling.\n"
           "- **Synthesized from model metrics:** the 512-bin PSD, DR sweep, DNL/INL profile, DC transfer curve, the behavioral continuation of the "
           "waveforms beyond the SPICE window.\n- **From the digital flow:** sdm2bin synthesis/P&R/STA/DRC/LVS numbers and gate-level frame "
           "verification; the per-card dout words are the bit-exact RTL model applied to the bitstream.\n"
           "- **From layout/PEX:** cap-macro trim history and extracted ratios, full-chip dimensions, block areas, routing parasitics, DRC/LVS.",
           title="Data provenance"),
    ]),
]}

pages = [
    {"id": "summary", "title": "Summary & master table", "src": write("pages/summary.json", summary_page)},
    {"id": "macros", "title": "Cap & sdm2bin macros", "src": write("pages/macros.json", macros_page)},
    {"id": "arch", "title": "Architectures", "src": write("pages/arch.json", arch_page)},
    {"id": "dse", "title": "Design space", "src": write("pages/dse.json", dse_page)},
    {"id": "method", "title": "Methodology", "src": write("pages/method.json", method_page)},
]

# ============================================================================= component
comp = {
    "schema": "aicdb-hub/2",
    "id": "sdm",
    "name": "ΣΔ ADCs",
    "title": "GF180 Switched-Capacitor ΣΔ ADC Generator (8-bit to >20-bit ENOB)",
    "summary": f"{len(CARDS)} low-power switched-capacitor sigma-delta ADCs: four loop architectures (shared-Cs and split-DAC CIFB, "
               "feedforward CIFF, resonator CRFF with voted quantizer) at 8–20 bits, custom gLayout MOM or Option-B MIM capacitor arrays, "
               "1.8 V and 3.3 V, each with an OpenROAD sdm2bin decimator. Reported at pre-layout, post-cap-PEX and full-chip PEX; "
               "performance figures come from the generator's analytical model (see Methodology).",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "stats": [{"label": "gLayout SC cap macros", "value": str(len(CAP_MACROS))},
              {"label": "OpenROAD sdm2bin macros", "value": str(len(DIG_MACROS))},
              {"label": "sweep configurations", "value": f"{SW['total_evaluated']:,}"},
              {"label": "PVT + MC runs (model)", "value": f"{9 * len(CARDS)} + {100 * len(CARDS):,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u or None, si=si or None, better=b, digits=dg).items() if v is not None}
                for k, l, u, si, b, dg in METRICS],
    "axes": {
        "topology": {"label": "Loop architecture", "values": [{"id": a, "label": ARCH_ROW.get(a, ARCH_SPECS[a]["short"])} for a in ARCH_ORDER]},
        "resolution": {"label": "Resolution", "values": [{"id": f"{n}b", "label": f"{n}-bit · OSR {RES_SPECS[str(n)]['osr']}"} for n in NBITS]},
        "cap": {"label": "Cap array", "values": [{"id": t, "label": CAP_AXIS.get(t, t)} for t in IDX["cap_types"]]},
    },
    "matrix": {"rows": ["topology"], "cols": ["resolution", "cap"], "metrics": ["enob", "sndr"],
               "presets": [{"label": "Power & FoM_S", "metrics": ["power", "fom_s"]},
                           {"label": "PVT worst ENOB & MC σ (full)", "metrics": ["pvt_min_enob", "mc_enob_std"]},
                           {"label": "FoM_W & DR", "metrics": ["fom_w", "dr"]},
                           {"label": "SFDR & THD", "metrics": ["sfdr", "thd"]},
                           {"label": "Integrator swings (SPICE)", "metrics": ["swing1", "swing2"]},
                           {"label": "Area & power", "metrics": ["area", "power"]}]},
    "card_metrics": ["enob", "sndr", "sfdr", "power", "fom_s", "fom_w", "area"],
    "pages": pages,
    "designs": designs,
}
(OUT / "component.json").write_text(json.dumps(rnd(comp), separators=(",", ":"), ensure_ascii=False))
