#!/usr/bin/env python3
"""Bootstrap hub adapter for sar-gen-gemini4.

usage: sar.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.

Stage mapping (see sargen/ sources):
  * The only transistor-level SPICE result per card is `spice.fft_post` / `waveform_post`
    (view="post"): CDAC = Magic-extracted PEX netlist, S/H switch, comparator and VCM OPA = the
    sibling repos' PEX netlists, SAR controller = standard-cell schematic, top-level routing ideal
    (sargen/sar_netlist.py `use_pex_blocks`, sargen/{uhs,lu2g,ulp}.py). That is `partial`.
  * `fft_pre` is post with fixed offsets (+0.12..0.16 dB SNDR, x0.96..0.97 power), never simulated
    (sargen/arch.py populate_pre_pvt_and_driver_caches, uhs.py/lu2g.py/ulp.py `fft_pre[cid] = ...`).
  * `fft_full` is post with fixed offsets (-0.18 dB SNDR, x1.018 power), never simulated
    (sargen/site.py `_derive_full_pex_fft`).
  So only `partial` is emitted; the repo's derived pre/full ENOB estimates go into params.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
index = json.loads((docs / "data" / "index.json").read_text())

METRICS = [
    # key, label, unit, si, better, digits
    ("enob", "ENOB", "bit", False, "high", 3),
    ("sndr", "SNDR", "dB", False, "high", 3),
    ("sfdr", "SFDR", "dB", False, "high", 3),
    ("thd", "THD", "dB", False, "low", 3),
    ("snr", "SNR", "dB", False, "high", 3),
    ("fs", "Sample rate", "S/s", True, "high", 3),
    ("power", "Power", "W", True, "low", 3),
    ("e_conv", "Energy / conv.", "J", True, "low", 3),
    ("fom_w", "Walden FoM", "fJ/step", False, "low", 3),
    ("fom_s", "Schreier FoM", "dB", False, "high", 4),
    ("dnl", "DNL max", "LSB", False, "low", 2),
    ("inl", "INL max", "LSB", False, "low", 2),
    ("enob_var", "Worst ENOB (4σ var.)", "bit", False, "high", 3),
    ("p_leak", "Standby leakage", "W", True, "low", 3),
    ("area", "Layout area", "µm²", False, "low", 4),
]

# Display order and labels mirror the repo's own filter bar (docs/index.html)
ARCHS = [
    ("smono_ulp1k", "ULP 1 kS/s"),
    ("smono_ulp100k", "ULP 100 kS/s"),
    ("smono_ulp1m", "LP 1 MS/s"),
    ("mono_red", "Monotonic"),
    ("smono_red", "Split-monotonic"),
    ("vcm_opa_red", "VCM-OPA"),
    ("mvote_red", "3× majority-vote LSB"),
    ("smono_uhs100m", ">100 MS/s UHS"),
    ("lu_domino_2g", "Loop-unrolled domino"),
]
TIERS = [
    ("1ksps", "1 kS/s ULP"),
    ("100ksps", "100 kS/s ULP"),
    ("1msps", "1 MS/s LP"),
    ("hs", "3–20 MS/s"),
    ("uhs100m", ">100 MS/s UHS"),
    ("lu2g", "250–400 MS/s (2 GS/s TI)"),
]
CAPS = [("mom", "MOM (M1–M4)"), ("mim", "MIM (M4/M5)")]
ARCH_LABEL = dict(ARCHS)
ARCH_ORDER = {a: i for i, (a, _) in enumerate(ARCHS)}

NOTE = ("Transistor-level SPICE FFT with Magic-extracted CDAC and PEX netlists of the S/H switch, "
        "comparator and VCM OPA; SAR logic as schematic, top-level routing not extracted")


def r(v, n=4):
    return None if v is None else float(f"{v:.{n}g}")


def partial_stage(c, d):
    sp = d.get("spice") or {}
    fp = sp.get("fft_post") or {}
    wf = sp.get("waveform_post") or {}
    fs_hz = fp["fs_msps"] * 1e6
    # Two ULP cards have a failed FFT run ("error" key, no codes); their docs values are the
    # thermal-ceiling fallback from sargen/ulp.py, so they are not reported as simulated.
    fft_ok = bool(fp.get("codes")) and "error" not in fp
    sndr = fp.get("sndr_db") if fft_ok else None
    enob = fp.get("enob") if fft_ok else None
    p_leak = None
    if c.get("sleep_gated"):
        # ULP: sargen/ulp.py reads uwf["e_dyn_pj"] but the SPICE result stores it under
        # waveform_post.tot, so docs power is a 28/110 pJ placeholder. Use the measured energy
        # with the repo's own rate-scaling formula (380 ns active window, sleep-gated leakage).
        tot = wf.get("tot") or {}
        e_dyn, leak_nw = tot.get("e_dyn_pj"), tot.get("p_leak_nw")
        if e_dyn is not None and leak_nw is not None:
            duty = max(0.05, 1.0 - min(0.95, 380e-9 * fs_hz))
            power = e_dyn * 1e-12 * fs_hz + leak_nw * 1e-9 * duty
            p_leak = leak_nw * 1e-9
        else:
            power = None
    else:
        power = fp.get("power_uw") * 1e-6 if fp.get("power_uw") is not None else None
    if not c.get("sleep_gated"):
        e_conv = fp["e_conv_pj"] * 1e-12 if fp.get("e_conv_pj") is not None else None
        fom_w = fp.get("fom_walden_fj") if fft_ok else None
        fom_s = fp.get("fom_schreier_db") if fft_ok else None
    else:  # recompute with the repo's formulas from the measured power
        e_conv = power / fs_hz if power else None
        fom_w = fom_s = None
        if power and enob is not None:
            fom_w = power / (fs_hz * 2.0 ** enob) * 1e15
            fom_s = sndr + 10.0 * math.log10(0.5 * fs_hz / power)
    cp = d.get("cdac_pex") or {}
    pv = (d.get("resilience") or {}).get("postpex_variance") or {}
    m = {
        "enob": enob, "sndr": sndr,
        "sfdr": fp.get("sfdr_db") if fft_ok else None,
        "thd": fp.get("thd_db") if fft_ok else None,
        "snr": fp.get("snr_db") if fft_ok else None,
        "fs": fs_hz,
        "power": r(power),
        "e_conv": r(e_conv),
        "fom_w": r(fom_w), "fom_s": r(fom_s, 5),
        "dnl": cp.get("dnl_max"), "inl": cp.get("inl_max"),
        "enob_var": pv.get("worst_redundant_enob"),
        "p_leak": r(p_leak),
        "area": c.get("area_um2"),
    }
    note = NOTE
    if not fft_ok:
        note += "; FFT run failed for this card (no dynamic metrics)"
    elif fp.get("eoc_all_high") is False:
        note += "; EOC not reached on every FFT cycle"
    if c.get("sleep_gated"):
        note += "; power = SPICE energy/conversion × fs + duty-cycled standby leakage"
    # robust = repo's post-PEX criterion: no switching failure at any injected-variance corner
    # (sargen/cdac_variance.py all_redundant_corners_pass, SPICE on the extracted CDAC)
    return {"metrics": m, "robust": bool(pv.get("all_redundant_corners_pass", c.get("postpex_var_pass"))),
            "note": note}


designs = []
for c in sorted(index["cards"], key=lambda c: (ARCH_ORDER[c["arch"]], c["nbits"], c["vdd"], c["cap_type"])):
    cid = c["card_id"]
    base = f"designs/{cid}"
    d = json.loads((docs / base / "data.json").read_text())
    fp = d["spice"]["fft_post"]
    mc = ((d.get("mismatch_mc") or {}).get("mc") or {}).get("enob") or {}
    lay = d.get("layout") or {}
    files = {k: f"{base}/{v}" for k, v in (
        ("schematic", "schematic.svg"), ("layout", "layout.svg"), ("gds", f"{cid}.gds.gz"),
        ("pex_netlist", "netlist.spice"), ("data", "data.json"))
        if (docs / base / v).is_file()}
    images = [{"label": lbl, "path": f"{base}/{f}"} for lbl, f in (
        ("CDAC layout", "cdac_layout.svg"), ("Comparator schematic", "comp_schematic.svg"),
        ("S/H switch schematic", "sw_schematic.svg"), ("VCM OPA schematic", "opa_schematic.svg"))
        if (docs / base / f).is_file()]
    tags = [c["arch_title"], c["cap_title"], f"{c['k_sw']}-step redundant CDAC"]
    if c.get("lsb_votes", 1) > 1:
        tags.append(f"{c['lsb_votes']}× LSB vote")
    if c.get("sleep_gated"):
        tags.append("sleep-gated")
    if c["fs_tier"] == "lu2g":
        tags.append(f"{c['ti_ways_for_2gsps']}× TI → 2 GS/s")
    designs.append({
        "id": cid,
        "title": f"{c['nbits']}-bit · {ARCH_LABEL[c['arch']]} · {c['vdd']} V · {c['cap_type'].upper()}",
        "vdd": c["vdd"],
        "axes": {"topology": c["arch"], "nbits": str(c["nbits"]), "tier": c["fs_tier"], "cap": c["cap_type"]},
        "tags": tags,
        "physical": {"drc": lay.get("drc_clean", c.get("drc_clean")), "lvs": lay.get("lvs_clean", c.get("lvs_clean")),
                     "pex": None,  # only the CDAC macro is extracted, not the full chip
                     "area_um2": c.get("area_um2"), "width_um": c.get("width_um"), "height_um": c.get("height_um")},
        "results": {"partial": partial_stage(c, d)},
        "params": {
            "CDAC weights": ", ".join(str(w) for w in c["weights"]),
            "Redundant weights": ", ".join(str(w) for w in c["redundant_positions"]),
            "Switching scheme": c["switching_scheme"].replace("`", ""),
            "Input / S&H": c["input_arch"],
            "CDAC macro": c["cdac_key"],
            "C_top (fF)": c.get("c_top_ff"),
            "Comparator": c["comp_key"],
            "S/H switch": c["sw_key"],
            "VCM OPA": c["opa_vcm_key"],
            "Input driver OPA": c["opa_in_key"],
            "Thermal-noise ENOB ceiling": (d.get("budget") or {}).get("enob_thermal_ceiling"),
            "Behavioural MC ENOB (mean ± σ, n=100)": f"{mc['mean']} ± {mc['std']}" if mc else None,
            "Binary CDAC worst ENOB under variance": c.get("worst_binary_enob"),
            "Speed-up vs binary": c.get("speedup_vs_binary"),
            "Pre-layout ENOB (repo estimate, not simulated)": c.get("enob_pre"),
            "Full-chip ENOB (repo estimate, not simulated)": c.get("enob_full"),
            "Input tone (MHz)": fp.get("fin_mhz"),
        },
        "files": files,
        "images": images,
        "links": {"classic": "index.html"},  # docs/assets/app.js has no hash routing (modal only)
    })

comp = {
    "schema": "aicdb-hub/1",
    "id": "sar",
    "name": "SAR ADCs",
    "title": "GF180 Redundant SAR ADC Library",
    "summary": "108 sub-binary-redundant SAR ADCs (8/10/12 bit, 1.8 V and 3.3 V, custom MOM or MIM "
               "common-centroid CDAC) from 1 kS/s sleep-gated ULP to 400 MS/s loop-unrolled domino cores "
               "(2 GS/s time-interleaved). Comparators, switches and op-amps reused from the sibling "
               "generators; transistor-level SPICE FFT with Magic-extracted CDAC and injected-variance "
               "switching-failure checks.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [
        {"label": "CDAC macros", "value": str(index.get("total_cdac_macros"))},
        {"label": "DSE points evaluated", "value": f"{index.get('sweep_total_evaluated', 0):,}"},
        {"label": "DSE feasible", "value": f"{index.get('sweep_feasible_count', 0):,}"},
    ],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=si or None, better=b,
                                       digits=None if si else dg).items() if v is not None}
                for k, l, u, si, b, dg in METRICS],
    "axes": {
        "topology": {"label": "Architecture", "values": [{"id": a, "label": l} for a, l in ARCHS]},
        "nbits": {"label": "Resolution", "values": [{"id": str(n), "label": f"{n}-bit"} for n in (8, 10, 12)]},
        "tier": {"label": "Sample-rate tier", "values": [{"id": a, "label": l} for a, l in TIERS]},
        "cap": {"label": "CDAC capacitor", "values": [{"id": a, "label": l} for a, l in CAPS]},
    },
    "matrix": {"rows": ["topology"], "cols": ["nbits", "cap"], "metrics": ["enob", "fom_w"]},
    "card_metrics": ["enob", "fs", "power", "fom_w", "area"],
    "designs": designs,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
