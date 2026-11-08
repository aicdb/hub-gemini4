#!/usr/bin/env python3
"""Bootstrap hub adapter for ecg-gen-gemini4 (schema aicdb-hub/2).

usage: ecg.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus the
pages, per-design detail documents and chart/explorer data it references (as "hub/<path>").
Verbatim prose of the retired site lives in ecg_text.py; the page/detail builders in ecg_blocks.py.

Stage mapping (ecggen/pex.py, ecggen/sim.py, scripts/refresh_all_36_farm.py in the repo):
  pre     = schematic netlist, nominal TB1-TB6 + 29-corner PVT (TB7) + 30-run MC (TB8-A).
  partial = nominal TB1-TB6 re-run on the "post-PEX" netlist: the *schematic* ecg_afe subcircuit with
            only the Magic-extracted parasitic capacitors that land on named top-level AFE nets injected
            (C only, no wiring R, internal-net parasitics dropped).  PVT/MC were not re-run; the repo's
            "post" PVT/MC/robust numbers are copies of the pre-PEX ones and are therefore not emitted.

Honesty rules applied (see the "Library notes" page for the full list):
  * results[] carry only simulation-derived quantities.  Figures the repo derives from closed-form
    models (total AFE gain = simulated LNA + ideal VGA formula, core-OTA A_OL blend, chopped noise /
    NEF / PEF, 72 %-model CMRR/PSRR, DR, IMD3, PM estimate, TB6 S&H/comparator traces, MC chopped
    offset, TB8-C electrode CMRR) are shown in the detail docs and pages, labelled "model".
  * PVT / MC pass counts and the robust flag are the hub's re-evaluation of the stored corners/runs
    against the library's own spec windows (summary.json meta.spec_targets); the repo forces every
    corner to PASS and the MC yield to 100 %.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ecg_blocks as B  # noqa: E402

# Results metrics: only simulation-derived values.  (key, label, unit, si, digits, better, getter, pre_only)
# getter(stage_scalar, ctx) -> value in the declared unit (base SI when si=True)
MODEL_IN_RESULTS = False   # True would also list model-derived figures (labelled "model") in results


def _g(field, scale=1.0):
    return lambda s, x: (None if s.get(field) is None else s[field] * scale)


METRICS = [
    ("zin", "|Z_in| @ 50 Hz (IBL on)", "Ω", True, 4, "high", _g("zin_50hz_ibl_on_mohm", 1e6), False),
    ("power", "Total power", "W", True, 4, "low", _g("p_total_nw", 1e-9), False),
    ("a_lna", "Stage-1 LNA gain", "dB", False, 4, None, _g("a_lna_db"), False),
    ("f_h", "High cutoff f_H", "Hz", True, 4, None, _g("f_h_hz"), False),
    ("f_l", "Low cutoff f_L", "Hz", True, 3, "low", _g("f_l_hz"), False),
    ("boost", "Z_in boost (IBL on / off)", "×", False, 3, "high", _g("zin_boost_factor"), False),
    ("zin_off", "|Z_in| @ 50 Hz (IBL off)", "Ω", True, 4, "high", _g("zin_50hz_ibl_off_mohm", 1e6), False),
    ("zin_10", "|Z_in| @ 10 Hz (IBL on)", "Ω", True, 4, "high", _g("zin_10hz_ibl_on_mohm", 1e6), False),
    ("zin_1k", "|Z_in| @ 1 kHz (IBL on)", "Ω", True, 4, "high", _g("zin_1khz_ibl_on_mohm", 1e6), False),
    ("idd", "Static supply current", "A", True, 4, "low", _g("idd_na", 1e-9), False),
    ("thd", "THD (4 mVpp, 50 Hz)", "%", False, 3, "low", _g("thd_pct"), False),
    ("hd2", "HD2 (4 mVpp)", "dBc", False, 4, "low", _g("hd2_db"), False),
    ("hd3", "HD3 (4 mVpp)", "dBc", False, 4, "low", _g("hd3_db"), False),
    ("sfdr", "SFDR (4 mVpp)", "dB", False, 4, "high", _g("sfdr_db"), False),
    ("vos_out", "Output DC offset", "V", True, 3, None, _g("vos_dc_mv", 1e-3), False),
    ("area", "Layout area", "µm²", False, 5, "low", lambda s, x: x["area"], False),
    ("zin_min", "Worst-PVT |Z_in| @ 50 Hz", "Ω", True, 4, "high", lambda s, x: B.mul(x["pvt"].get("zin_min_mohm"), 1e6), True),
    ("fh_pvt_min", "Lowest PVT f_H", "Hz", True, 4, "high", lambda s, x: x["pvt"].get("f_h_min_hz"), True),
    ("fh_pvt_max", "Highest PVT f_H", "Hz", True, 4, "low", lambda s, x: x["pvt"].get("f_h_max_hz"), True),
    ("p_pvt_max", "Worst-PVT power", "W", True, 4, "low", lambda s, x: B.mul(x["pvt"].get("p_max_nw"), 1e-9), True),
    ("fh_mc_std", "MC σ(f_H)", "Hz", True, 3, "low", lambda s, x: x["mc"].get("f_h_std_hz"), True),
    ("zin_mc_p5", "MC 5th-percentile |Z_in|", "Ω", True, 4, "high", lambda s, x: B.mul(x["mc"].get("zin_p5_mohm"), 1e6), True),
]
MODEL_METRICS = [  # only used when MODEL_IN_RESULTS
    ("gain", "AFE gain A_mid (model: sim LNA + ideal VGA)", "dB", False, 4, None, _g("a_mid_db"), False),
    ("a_ol", "Core OTA A_OL (model)", "dB", False, 4, "high", _g("a_ol_db"), False),
    ("irn", "Chopped IRN 0.5 Hz–1 kHz (model)", "V", True, 4, "low", _g("irn_rms_chopped_uv", 1e-6), False),
    ("nef", "NEF (model)", "", False, 3, "low", _g("nef"), False),
    ("pef", "PEF (model)", "", False, 3, "low", _g("pef"), False),
    ("cmrr", "CMRR @ 50 Hz (model)", "dB", False, 4, "high", _g("cmrr_50hz_db"), False),
    ("psrr", "PSRR @ 50 Hz (model)", "dB", False, 4, "high", _g("psrr_50hz_db"), False),
    ("dr", "DR @ 1 % THD (model)", "dB", False, 4, "high", _g("dr_db"), False),
]


def metric_decl(m):
    key, label, unit, si, digits, better, _, _ = m
    d = {"key": key, "label": label}
    if unit:
        d["unit"] = unit
    if si:
        d["si"] = True
    if digits:
        d["digits"] = digits
    if better:
        d["better"] = better
    return d


def stage_metrics(scalar, ctx, pre_stage, fh=None, thd_floor=False):
    out = {}
    for m in METRICS + (MODEL_METRICS if MODEL_IN_RESULTS else []):
        key, getter, pre_only = m[0], m[6], m[7]
        if pre_only and not pre_stage:
            continue
        v = getter(scalar, ctx)
        if v is not None:
            out[key] = B.rv(v)          # full precision: the hub rounds to the declared digits
    if fh and fh["affected"]:
        out["f_h"] = B.rv(fh["sim"])    # repo value is sim.py's conditioned f_H -> recovered simulated value
    if thd_floor:
        out.pop("thd", None)            # stored value is sim.py's 0.005 % floor, not a measurement
    return out


def main():
    docs, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    D = B.load_docs(docs)
    meta = D["summary"]["meta"]

    designs = []
    for c in D["cards"]:
        cid = c["card_id"]
        card = D["card_json"][cid]
        ph = c.get("physical") or {}
        pre_var = (card.get("pre_pex") or {}).get("variation") or {}
        pvt, mc = pre_var.get("pvt") or {}, pre_var.get("mc") or {}
        hub = D["hubcheck"][cid]
        ctx = {"area": ph.get("area_um2"), "pvt": pvt, "mc": mc}

        results = {}
        fh, floor = D["fh"][cid], D["thd_floor"][cid]
        if c.get("pre"):
            results["pre"] = {
                "metrics": stage_metrics(c["pre"], ctx, True, fh["pre"], floor["pre"]),
                "pvt": {"pass": hub["pvt_ok"], "total": hub["pvt_total"]},
                "mc": {"pass": hub["mc_ok"], "total": hub["mc_total"]},
                "robust": hub["robust"],
                "note": B.pre_note(c, hub, fh["pre"], floor["pre"]),
            }
        post_nom = (card.get("post_pex") or {}).get("nominal") or {}
        if c.get("post") and post_nom.get("ok", True):
            results["partial"] = {"metrics": stage_metrics(c["post"], ctx, False, fh["partial"], floor["partial"]),
                                  "note": B.partial_note(c, card, D["pex_inj"][cid], fh["partial"], floor["partial"])}

        base = f"designs/{cid}"
        files = {k: f"{base}/{v}" for k, v in (
            ("schematic", "schematic.svg"), ("gds", f"{cid}.gds.gz"), ("netlist", "netlist.spice"),
            ("pex_netlist", "pex.spice"), ("lvs_netlist", "lvs_ref.spice"), ("data", "card.json"))
            if (docs / base / v).is_file()}
        sz = card.get("sizing") or {}
        rb = card.get("reused_blocks") or {}
        params = {
            "Target power": f"{c['p_target_nw']:g} nW ({c['tier_label']})",
            "V_CM": f"{c['vcm']:g} V",
            "f_chop": f"{c['f_chop_hz'] / 1e3:g} kHz",
            "β_IBL = C_pf / C_fb": c.get("beta_ibl"),
            "I_core / I_aux": f"{sz.get('i_core_na', 0):g} nA / {sz.get('i_aux_na', 0):g} nA",
            "I_ref,core / I_ref,aux": f"{sz.get('iref_core_na', 0):g} nA / {sz.get('iref_aux_na', 0):g} nA",
            "C_in / C_fb": f"{sz.get('c_in_pf', 0):g} pF / {sz.get('c_fb_ff', 0):g} fF",
            "C_pf": f"{sz.get('c_pf_ff', 0):g} fF",
            "C_LPF / C_ADC": f"{sz.get('c_lpf_pf', 0):g} pF / {sz.get('c_adc_ff', 0):g} fF",
            "Core OTA (opa-gen, 200 fF lib)": rb.get("core_ota_id"),
            "Aux OTA (opa-gen, 200 fF lib)": rb.get("aux_ota_id") or "none (passive IBL)",
            "Chopper switch (switch-gen)": rb.get("chop_sw_key"),
            "S&H switch (switch-gen)": rb.get("sh_sw_key"),
            "Comparator (sa-gen)": rb.get("comp_key"),
            "Routed wirelength / vias": f"{ph.get('wirelength_um', 0):g} µm / {ph.get('vias', 0)}",
            "Extracted parasitic caps": ph.get("parasitic_c_count"),
        }
        uses = [{"component": "opa", "design": f"{B.OTA_LOAD}-{rb['core_ota_id']}", "role": "core LNA OTA"}]
        if rb.get("aux_ota_id"):
            uses.append({"component": "opa", "design": f"{B.OTA_LOAD}-{rb['aux_ota_id']}",
                         "role": {"ccia_dsl": "DC-servo-loop OTA", "ccia_2stage_pga": "PGA OTA", "ccia_precharge": "precharge buffer OTA",
                                  "ccia_buf_ibl": "IBL buffer OTA"}.get(c["arch"], "aux OTA")})
        if rb.get("chop_sw_key") == rb.get("sh_sw_key"):
            uses.append({"component": "switch", "design": rb["chop_sw_key"], "role": "chopper & S&H switch"})
        else:
            uses += [{"component": "switch", "design": rb["chop_sw_key"], "role": "chopper switch"},
                     {"component": "switch", "design": rb["sh_sw_key"], "role": "bootstrapped S&H switch"}]
        uses.append({"component": "sa", "design": rb["comp_key"], "role": "ADC comparator"})
        detail_rel = f"designs/{cid}.json"
        B.write_json(out / detail_rel, {"blocks": B.detail_blocks(D, c, card)})
        designs.append({
            "id": cid,
            "title": f"{c['arch_name']} · {c['arch_short']} · {c['vdd']:g} V · {c['tier'].upper()} {c['tier_short']}",
            "summary": B.design_summary(c, card),
            "vdd": c["vdd"],
            "axes": {"topology": c["arch"], "ibl": f"ibl_{c['arch']}", "tier": c["tier"]},
            "tags": [t for t in (c.get("arch_title"), c.get("ibl_type"), c.get("hpf_type"), c.get("tier_label"),
                                 f"core {rb.get('core_ota_id')}", f"aux {rb['aux_ota_id']}" if rb.get("aux_ota_id") else None,
                                 f"f_chop {c['f_chop_hz'] / 1e3:g} kHz") if t],
            "physical": {"drc": ph.get("drc_ok"), "lvs": ph.get("lvs_ok"), "pex": ph.get("pex_ok"),
                         "area_um2": ph.get("area_um2"), "width_um": ph.get("width_um"), "height_um": ph.get("height_um")},
            "results": results,
            "params": {k: v for k, v in params.items() if v is not None},
            "files": files,
            "uses": uses,
            "detail": f"hub/{detail_rel}",
        })

    pages = B.write_pages(D, out)
    archs = [{"id": a["id"], "label": f"{a['name']} · {a['short']}"} for a in meta["architectures"]]
    tiers = [{"id": t["tag"], "label": f"{t['short_label']} ({t['tag'].upper()})"} for t in meta["power_tiers"]]
    n_robust = sum(1 for h in D["hubcheck"].values() if h["robust"])
    comp = {
        "schema": "aicdb-hub/2",
        "id": "ecg",
        "name": "ECG AFEs",
        "title": "GF180 Chopping ECG Front-End Library",
        "summary": ("Six capacitively-coupled chopper instrumentation amplifier (CCIA) architectures with input-impedance "
                    "boosting (PFB, buffered IBL, DC-servo loop, capacitor flipping, precharge, two-stage LNA + PGA) at "
                    "1.8 V and 3.3 V in three sub-µW power tiers, driving a reused S&H + clocked comparator. "
                    "29-corner PVT, 30-run MC, gLayout DRC/LVS-clean layouts and Magic C extraction on top-level nets. "
                    f"Hub re-check: {n_robust}/36 cards stay inside the library spec windows over all PVT corners and MC "
                    "runs (the repo reports 36/36 because its refresh script forces every corner to pass)."),
        "technology": "gf180mcuD",
        "generated": B.iso(meta.get("updated")),
        "stats": [
            {"label": "farm simulations", "value": f"{meta.get('total_farm_sims', 0):,}"},
            {"label": "DSE candidates", "value": f"{meta.get('dse_points_count', 0):,}"},
            {"label": "PVT-robust (hub re-check)", "value": f"{n_robust}/{len(designs)}"},
            {"label": "reused cells scored", "value": "96 + 25 + 32"},
        ],
        "metrics": [metric_decl(m) for m in METRICS + (MODEL_METRICS if MODEL_IN_RESULTS else [])],
        "axes": {
            "topology": {"label": "Chopping + IBL architecture", "values": archs},
            "ibl": {"label": "Impedance-boost mechanism", "values": [{"id": f"ibl_{a['id']}", "label": a["ibl_type"]} for a in meta["architectures"]]},
            "tier": {"label": "Power tier", "values": tiers},
        },
        "matrix": {
            "rows": ["topology", "ibl"], "cols": ["tier"], "metrics": ["zin", "power", "a_lna", "boost", "f_h"],
            "presets": [
                {"label": "|Z_in|, power, LNA gain, boost, f_H (default)", "metrics": ["zin", "power", "a_lna", "boost", "f_h"]},
                {"label": "LNA gain & f_H", "metrics": ["a_lna", "f_h"]},
                {"label": "Z_in boost & IBL-off |Z_in|", "metrics": ["boost", "zin_off"]},
                {"label": "THD & SFDR", "metrics": ["thd", "sfdr"]},
                {"label": "Worst-PVT |Z_in| & power (pre-PEX only)", "metrics": ["zin_min", "p_pvt_max"]},
                {"label": "PVT f_H range (pre-PEX only)", "metrics": ["fh_pvt_min", "fh_pvt_max"]},
                {"label": "Monte Carlo σ(f_H) & 5th-pct |Z_in| (pre-PEX only)", "metrics": ["fh_mc_std", "zin_mc_p5"]},
                {"label": "Layout area & power", "metrics": ["area", "power"]},
            ],
        },
        "card_metrics": ["zin", "power", "a_lna", "f_h", "f_l", "boost", "zin_off", "thd", "area"],
        "table_metrics": ["zin", "power", "a_lna", "f_h", "boost", "thd"],
        "cards_group_by": "topology",
        "vdd_labels": {f"{sp['vdd']:g}": f"V<sub>DD</sub> = {sp['vdd']:g} V (V<sub>CM</sub> = {sp['vcm']:.2f} V)" for sp in meta.get("supplies") or []},
        "builds_on": [{"id": "opa", "role": "core LNA OTA + DSL / PGA / buffer OTAs (200 fF library)"},
                      {"id": "switch", "role": "input chopper & bootstrapped S&H switches"},
                      {"id": "sa", "role": "ADC clocked comparator"}],
        "pages": pages,
        "designs": designs,
    }
    B.write_json(out / "component.json", comp)


if __name__ == "__main__":
    main()
