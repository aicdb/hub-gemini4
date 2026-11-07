#!/usr/bin/env python3
"""Bootstrap hub adapter for ls-gen-gemini4 (level shifters).

usage: ls.py DOCS_DIR OUT_JSON

Reads only DOCS_DIR (the repo's published docs/) and writes an aicdb-hub/1 component.
Source: docs/report_data.json, which holds two parallel result sets, "pre" (schematic
netlist) and "pex" (Magic RC extraction of the whole gLayout cell).

A design = one topology operated in one voltage-domain crossing:
  * 11 topologies x 6 benchmark crossings (pilot @ 10 MHz/20 fF, 20-corner PVT, MC subset)
  * + 6 HV-tolerant operating points of TOP9-11 (25 MHz, 15-corner PVT with 1.8 V oxide check)
All crossings of one topology share the same cell (same schematic / layout / area).
`vdd` is the OUTPUT-domain top rail (VDDH); the input rail is in the domain axis and params.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

docs, out = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads((docs / "report_data.json").read_text())
PRE, PEX = data["pre"], data["pex"]

METRICS = [
    # key, label, unit, si, better
    ("tpd", "Delay (avg)", "s", True, "low"),
    ("tplh", "Delay LH", "s", True, "low"),
    ("tphl", "Delay HL", "s", True, "low"),
    ("trise", "Rise time", "s", True, "low"),
    ("tfall", "Fall time", "s", True, "low"),
    ("pstat", "Static power", "W", True, "low"),
    ("ptot", "Total power", "W", True, "low"),
    ("edyn", "Switching energy", "J", True, "low"),
    ("swing", "Output swing", "%", False, "high"),
    ("pvt_yield", "PVT yield", "%", False, "high"),
    ("wc_tpd", "Worst PVT delay", "s", True, "low"),
    ("wc_pstat", "Worst PVT leakage", "W", True, "low"),
    ("mc_yield", "MC yield", "%", False, "high"),
    ("mc_tpd3s", "MC delay μ+3σ", "s", True, "low"),
    ("mc_tpd_sd", "MC delay σ", "s", True, "low"),
    ("vox", "Max oxide stress", "V", True, "low"),
    ("wc_vox", "Worst PVT oxide", "V", True, "low"),
    ("area", "Layout area", "µm²", False, "low"),
    ("dev_area", "Device area", "µm²", False, "low"),
]


def sc(v, k):
    return None if v is None else float(f"{v * k:.6g}")


def nominal_metrics(r):
    """Nominal tt/27 °C transient record (pilot or hvt_speed row) -> metrics."""
    if not r:
        return {}
    # timing is only meaningful when the output actually toggles (repo's logic_pass:
    # swing >= 85 % and valid edges); a failed oxide check alone keeps the timing.
    ok = r.get("logic_pass", r.get("pass"))
    t = 1e-12 if ok else None
    m = {
        "tpd": t and sc(r.get("tpd_ps"), t), "tplh": t and sc(r.get("tplh_ps"), t),
        "tphl": t and sc(r.get("tphl_ps"), t), "trise": t and sc(r.get("trise_ps"), t),
        "tfall": t and sc(r.get("tfall_ps"), t), "pstat": sc(r.get("p_stat_nw"), 1e-9),
        "ptot": sc(r.get("p_tot_uw"), 1e-6), "edyn": sc(r.get("e_dyn_fj"), 1e-15),
        "swing": sc(r.get("swing_ratio"), 100), "vox": r.get("max_vox_v"),
    }
    return m


def index(rows, key=lambda r: (r["topology"], r["domain_label"])):
    return {key(r): r for r in rows}


def stage(src, topo, dom, area, dev_area, hv=False):
    """Build one results.<stage> block from a pre/pex dataset, or None if not simulated."""
    if hv:
        summ = index(src["hvt_pvt_summary"]).get((topo, dom))
        if not summ:
            return None
        nom = next((r for r in src["hvt_speed"] + src["hvt_grid"] if r["topology"] == topo and
                    r["vddl"] == summ["vddl"] and r["vddh"] == summ["vddh"] and r["freq_mhz"] == 25), None)
        m = nominal_metrics(nom)
        m.update(pvt_yield=summ["yield_pct"], wc_tpd=sc(summ.get("wc_tpd_ps"), 1e-12),
                 wc_vox=summ.get("wc_vox_v"))
        mc = None
        notes = [f"15-corner PVT incl. |VGS|,|VGD| < 1.8 V oxide check; worst delay {summ.get('wc_dly_corner')}"]
    else:
        nom = index(src["pilot"]).get((topo, dom))
        summ = index(src["pvt_summary"]).get((topo, dom))
        if not nom and not summ:
            return None
        m = nominal_metrics(nom)
        notes = []
        if summ:
            m.update(pvt_yield=summ["yield_pct"], wc_tpd=sc(summ.get("wc_tpd_ps"), 1e-12),
                     wc_pstat=sc(summ.get("wc_pstat_nw"), 1e-9))
            if nom and summ.get("nom_tpd_ps") != nom.get("tpd_ps"):
                notes.append("PVT sweep was run on an earlier netlist revision than the nominal "
                             "pilot (tt/27 °C delay differs)")
        mc = index(src["mc_summary"]).get((topo, dom))
        if mc:
            m.update(mc_yield=mc["yield_pct"], mc_tpd3s=sc(mc.get("tpd_3sigma_ps"), 1e-12),
                     mc_tpd_sd=sc(mc.get("tpd_std_ps"), 1e-12))
    m["area"], m["dev_area"] = area, dev_area
    s = {"metrics": {k: m.get(k) for k, *_ in METRICS}}
    if summ:
        s["pvt"] = {"pass": summ["n_pass"], "total": summ["n_total"]}
    if mc:
        s["mc"] = {"pass": mc["n_pass"], "total": mc["n_runs"]}
    # repo pass criterion: every PVT corner passes (swing >= 85 %, valid delays, oxide-safe
    # where asserted) and, where MC was run, the 3-sigma MC check (pass_3sigma) holds.
    if summ:
        s["robust"] = bool(summ["n_total"] and summ["n_pass"] == summ["n_total"] and
                           (mc is None or mc.get("pass_3sigma")))
    if nom is not None and not nom.get("pass"):
        notes.insert(0, "fails at the nominal tt/27 °C point")
    if notes:
        s["note"] = "; ".join(notes)
    return s


def fv(v):
    return f"{v:g}"


# ---- domain crossings -------------------------------------------------------------
KIND = {"shared": "Shared GND", "subvt": "Sub-Vt input", "split": "Split rail",
        "disjoint": "Disjoint rails", "hvt": "HV (oxide < 1.8 V)"}
domains = {}  # id -> dict(label, title, vssl, vddl, vssh, vddh, kind, src_label, hv)
for r in PRE["pvt_summary"]:
    dl = r["domain_label"]
    if dl in domains:
        continue
    domains[dl] = dict(
        label=f"{fv(r['vssl'])}–{fv(r['vddl'])} → {fv(r['vssh'])}–{fv(r['vddh'])} V",
        title=r.get("domain_title") or dl, vssl=r["vssl"], vddl=r["vddl"], vssh=r["vssh"],
        vddh=r["vddh"], kind=dl.split("_")[0], src=dl, hv=False)
for r in PRE["hvt_pvt_summary"] + PEX["hvt_pvt_summary"]:
    dl = r["domain_label"]
    did = "hv_" + dl.replace(".", "v").replace("V_to_", "_to_").rstrip("V")
    if did in domains:
        continue
    domains[did] = dict(label=f"{fv(r['vddl'])} → {fv(r['vddh'])} V (HV)",
                        title=f"0-{fv(r['vddl'])}V -> 0-{fv(r['vddh'])}V (HV-tolerant, 25 MHz)",
                        vssl=0.0, vddl=r["vddl"], vssh=0.0, vddh=r["vddh"], kind="hvt", src=dl, hv=True)
dom_order = [k for k in domains if not domains[k]["hv"]] + \
    sorted((k for k in domains if domains[k]["hv"]), key=lambda k: (domains[k]["vddh"], domains[k]["vddl"]))

# ---- designs ------------------------------------------------------------------------
topos = PRE["topologies"]
hv_pairs = {(r["topology"], r["domain_label"]) for r in PRE["hvt_pvt_summary"] + PEX["hvt_pvt_summary"]}
designs = []
for t in topos:
    tid = t["id"]
    pm, ar = t.get("pex_meta") or {}, t.get("area") or {}
    area, dev_area = pm.get("layout_area_um2"), ar.get("total_area_um2")
    files = {k: v for k, v in (("schematic", f"assets/schem_{tid}.svg"),
                               ("layout", f"assets/layout_{tid}.png"),
                               ("data", "report_data.json")) if (docs / v).is_file()}
    for did in dom_order:
        dm = domains[did]
        if dm["hv"] and (tid, dm["src"]) not in hv_pairs:
            continue
        results = {}
        if (s := stage(PRE, tid, dm["src"], area, dev_area, dm["hv"])):
            results["pre"] = s
        if pm.get("has_pex") and (s := stage(PEX, tid, dm["src"], area, dev_area, dm["hv"])):
            s["note"] = "Magic RC extraction (junction + routing) of the full cell" + \
                        (f"; {s['note']}" if s.get("note") else "")
            results["full"] = s
        if not results:
            continue
        up = dm["vddh"] > dm["vddl"]
        designs.append({
            "id": f"{tid}.{did}",
            "title": f"{t['short_name']} · {dm['title']}",
            "vdd": dm["vddh"],
            "axes": {"topology": tid, "domain": did, "kind": dm["kind"],
                     "direction": "up" if up else "down", "coupling": t.get("coupled_type")},
            "tags": [x for x in (t.get("category"), f"{t.get('coupled_type')} coupled",
                                 "step-up" if up else "step-down", t.get("ref")) if x],
            "physical": {"drc": pm.get("drc_clean"), "lvs": pm.get("lvs_clean"),
                         "pex": True if pm.get("has_pex") else None, "area_um2": area,
                         "width_um": pm.get("width_um"), "height_um": pm.get("height_um")},
            "results": results,
            "params": {
                "Input rails": f"{fv(dm['vssl'])} / {fv(dm['vddl'])} V",
                "Output rails": f"{fv(dm['vssh'])} / {fv(dm['vddh'])} V",
                "Test frequency": "25 MHz" if dm["hv"] else "10 MHz", "C_load": "20 fF",
                "MOS / R / C": f"{ar.get('n_mos')} / {ar.get('n_res')} / {ar.get('n_cap')}",
                "Parasitic C (fF)": pm.get("total_cap_ff"), "Parasitic R (Ω)": pm.get("total_res_ohm"),
            },
            "files": files,
            "links": {"classic": "index.html#hvt" if dm["hv"] else "index.html#overview"},
        })

total_sims = PRE.get("total_sims", 0) + PEX.get("total_sims", 0)
dse = PRE.get("dse") or {}
coupling = []
for t in topos:
    if t.get("coupled_type") not in coupling:
        coupling.append(t.get("coupled_type"))

comp = {
    "schema": "aicdb-hub/1",
    "id": "ls",
    "name": "Level shifters",
    "title": "GF180 Level-Shifter Topology Benchmark",
    "summary": f"{len(topos)} level-shifter topologies (DCVS, Wilson current-mirror, near-Vt, cap-boost, "
               "split-rail, envelope-universal, pure AC-coupled and HV-tolerant stacked) benchmarked across "
               "six voltage-domain crossings (core→IO, sub-Vt, split-rail and disjoint, up and down) plus "
               "HV-tolerant operating points up to 4.8 V. The supply shown is the output-domain rail VDDH; "
               "the input rails are in the domain axis. Nominal tt/27 °C transients, 20-corner PVT, "
               "Monte Carlo and Magic full-cell PEX of each gLayout cell.",
    "technology": "gf180mcuD",
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "classic": "index.html",
    "stats": [{"label": "simulations (pre + PEX)", "value": f"{total_sims:,}"},
              {"label": "DSE candidates", "value": f"{dse.get('n_total', 0):,}"}],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=si or None, better=b).items() if v is not None}
                for k, l, u, si, b in METRICS],
    "axes": {
        "topology": {"label": "Topology", "values": [{"id": t["id"], "label": t["short_name"]} for t in topos]},
        "domain": {"label": "Domain crossing", "values": [{"id": k, "label": domains[k]["label"]} for k in dom_order]},
        "kind": {"label": "Crossing type", "values": [{"id": k, "label": v} for k, v in KIND.items()
                                                      if any(d["kind"] == k for d in domains.values())]},
        "direction": {"label": "Direction", "values": [{"id": "up", "label": "Step-up"},
                                                       {"id": "down", "label": "Step-down"}]},
        "coupling": {"label": "Coupling", "values": [{"id": c, "label": c} for c in coupling]},
    },
    "matrix": {"rows": ["topology"], "cols": ["domain"], "metrics": ["tpd", "pvt_yield"]},
    "card_metrics": ["tpd", "pvt_yield", "edyn", "pstat", "area"],
    "designs": designs,
}
out.write_text(json.dumps(comp, indent=1, ensure_ascii=False))
