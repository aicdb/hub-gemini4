"""Builders for the ecg hub export: data loading, honesty re-checks, per-design detail docs and pages.

Used by ecg.py.  Stdlib only; reads DOCS_DIR only.  All numbers are rounded to ~5 significant digits.
"""
from __future__ import annotations

import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import ecg_text as T

ARCH_COLORS = ['#225bb2', '#d96b27', '#1e8565', '#934eb0', '#b08218', '#c93b5b', '#0d8499', '#5c6bc0', '#2e7d32', '#ad1457']
PRE_C, POST_C, GOOD_C, BAD_C = '#225bb2', '#dc2626', '#16a34a', '#dc2626'
OTA_LOAD = "200f"   # ecggen/select.py loads reused OTA netlists from the 200 fF library first


# ----------------------------------------------------------------------------- small helpers
def r(v, n=9):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return 0 if v == 0 else float(f"{v:.{n}g}")
    return v


def rv(v):
    """Displayed values (results, table cells, explorer): keep ~9 significant digits so the hub's own
    rounding to the declared digits is the only rounding (avoids double-rounding artefacts)."""
    return r(v, 9)


def rl(a, n=5):
    """Chart traces: ~5 significant digits."""
    return [r(x, n) for x in (a or [])]


def mul(v, k):
    return None if v is None else v * k


def iso(ts):
    if not ts:
        return None
    return str(ts)[:19] + "Z"


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def hu(v, d):
    """Round half-up like JS toFixed (the old site), returned as float."""
    return float(Decimal(str(v)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))


def nf(v, d=2):
    return "—" if v is None else f"{hu(v, d):.{d}f}"


def sgn(v, d=1):
    return "—" if v is None else f"{'+' if v > 0 else ''}{v:.{d}f}"


def zin_s(mohm):
    if mohm is None:
        return "—"
    if mohm >= 1000:
        return f"{hu(mohm / 1000, 2):g} GΩ"
    return f"{hu(mohm, 1):g} MΩ"


def pw_s(nw):
    if nw is None:
        return "—"
    if nw >= 1000:
        return f"{hu(nw / 1000, 2):g} µW"
    return f"{hu(nw, 1):g} nW"


def opa_href(cid, load=OTA_LOAD):
    return f"#/opa/{load}-{cid}"


def link(text, href):
    return f"[`{text}`]({href})"


def cell(v, s=None, title=None):
    d = {"v": v}
    if s:
        d["s"] = s
    if title:
        d["title"] = title
    return d


def ok_cell(ok, yes="PASS", no="WARN"):
    if ok is None:
        return cell("PENDING", "muted")
    return cell(yes if ok else no, "good" if ok else "bad")


# ----------------------------------------------------------------------------- plotting helpers
def tr(x, y, name, color=None, dash=None, width=None, mode="lines", **kw):
    t = {"type": "scatter", "mode": mode, "name": name, "x": rl(x), "y": rl(y)}
    line = {}
    if color:
        line["color"] = color
    if dash:
        line["dash"] = dash
    if width:
        line["width"] = width
    if line:
        t["line"] = line
    if color and "markers" in mode:
        t["marker"] = {"color": color, "size": 6}
    t.update(kw)
    return t


def bar(x, y, name, color=None, **kw):
    t = {"type": "bar", "name": name, "x": x if isinstance(x, list) and x and isinstance(x[0], str) else rl(x), "y": rl(y)}
    if color:
        t["marker"] = {"color": color}
    t.update(kw)
    return t


def hbar(xvals, ylabels, name, color=None):
    t = {"type": "bar", "orientation": "h", "name": name, "x": rl(xvals), "y": list(ylabels)}
    if color:
        t["marker"] = {"color": color}
    return t


def chart(title, traces, xl, yl, logx=False, logy=False, caption=None, layout=None, height=None, **kw):
    lay = {"xaxis": {"title": {"text": xl}}, "yaxis": {"title": {"text": yl}},
           "hovermode": "x unified", "legend": {"orientation": "h", "y": 1.18, "x": 0, "font": {"size": 10.5}},
           "margin": {"t": 56}}
    if logx:
        lay["xaxis"]["type"] = "log"
    if logy:
        lay["yaxis"]["type"] = "log"
    for k, v in (layout or {}).items():
        if isinstance(v, dict) and isinstance(lay.get(k), dict):
            lay[k] = {**lay[k], **v}
        else:
            lay[k] = v
    b = {"type": "chart", "title": title, "data": traces, "layout": lay}
    if caption:
        b["caption"] = caption
    if height:
        b["height"] = height
    b.update(kw)
    return b


def fig(traces, xl, yl, logx=False, logy=False, layout=None):
    """Plotly figure dict for chart `src` files."""
    c = chart("", traces, xl, yl, logx, logy, layout=layout)
    return {"data": c["data"], "layout": c["layout"]}


def section(title, blocks, cols=1, intro=None, **kw):
    b = {"type": "section", "title": title, "blocks": blocks}
    if cols > 1:
        b["cols"] = cols
    if intro:
        b["intro"] = intro
    b.update(kw)
    return b


def md(text, **kw):
    return {"type": "markdown", "text": text, **kw}


def note(text, tone="info", **kw):
    return {"type": "note", "text": text, "tone": tone, **kw}


def table(title, columns, rows, **kw):
    return {"type": "table", "title": title, "columns": columns, "rows": rows, **kw}


def col(key, label, unit=None, **kw):
    c = {"key": key, "label": label}
    if unit:
        c["unit"] = unit
    c.update(kw)
    return c


def stats(items, title=None, **kw):
    b = {"type": "stats", "items": items}
    if title:
        b["title"] = title
    b.update(kw)
    return b


def intro_md(eyebrow, h1, p):
    return f"<small><b>{eyebrow}</b></small>\n\n## {h1}\n\n{p}"


# ----------------------------------------------------------------------------- data loading + hub re-checks
CHECK_KEYS = [  # (spec key, corner field, label)
    ("power_nw", "p_total_nw", "P"),
    ("bw_high_hz", "f_h_hz", "f_H"),
    ("bw_low_hz", "f_l_hz", "f_L"),
    ("zin_50hz_mohm", "zin_50hz_mohm", "|Z_in|"),
    ("gain_db", "a_mid_db", "A_mid"),
    ("pm_deg", "pm_deg", "PM"),
]


def spec_window(sp, key):
    t = sp.get(key) or {}
    return t.get("min"), t.get("max")


def check_point(sp, rec):
    """Failing spec items for one PVT corner / MC run (library spec windows from summary.json)."""
    fails = []
    for key, field, label in CHECK_KEYS:
        v = rec.get(field)
        if v is None:
            continue
        lo, hi = spec_window(sp, key)
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            fails.append(f"{label} {v:g}")
    return fails


def window_text(sp, key, unit):
    lo, hi = spec_window(sp, key)
    if lo is not None and hi is not None:
        return f"{lo:g}–{hi:g} {unit}".strip()
    if lo is not None:
        return f"≥ {lo:g} {unit}".strip()
    if hi is not None:
        return f"≤ {hi:g} {unit}".strip()
    return "—"


def load_docs(docs: Path):
    j = lambda p: json.loads((docs / p).read_text())  # noqa: E731
    summ = j("data/summary.json")
    meta = summ["meta"]
    arch_order = {a["id"]: i for i, a in enumerate(meta["architectures"])}
    tier_order = {t["tag"]: i for i, t in enumerate(meta["power_tiers"])}
    cards = sorted(summ["cards"], key=lambda c: (arch_order.get(c["arch"], 99), c["vdd"], tier_order.get(c["tier"], 99)))
    D = {
        "docs": docs, "summary": summ, "meta": meta, "cards": cards,
        "card_json": {c["card_id"]: j(f"designs/{c['card_id']}/card.json") for c in cards},
        "sweep": j("data/sweep.json"), "comps": j("data/components.json"), "lut": j("data/lut.json"),
        "xsim": j("data/xsim.json"), "sens": j("data/sens.json"), "library": j("data/library.json"),
        "arch": {a["id"]: a for a in meta["architectures"]}, "tier": {t["tag"]: t for t in meta["power_tiers"]},
        "spec": meta.get("spec_targets") or {},
    }
    D["lib_design"] = {d["card_id"]: d for d in D["library"].get("designs", [])}
    hub = {}
    for c in cards:
        var = (D["card_json"][c["card_id"]].get("pre_pex") or {}).get("variation") or {}
        corners = (var.get("pvt") or {}).get("corners") or []
        samples = (var.get("mc") or {}).get("samples") or []
        cf = {x["corner"]: check_point(D["spec"], x) for x in corners}
        mf = {x["seed"]: check_point(D["spec"], x) for x in samples}
        pvt_ok = sum(1 for v in cf.values() if not v)
        mc_ok = sum(1 for v in mf.values() if not v)
        hub[c["card_id"]] = {"pvt_ok": pvt_ok, "pvt_total": len(corners), "mc_ok": mc_ok, "mc_total": len(samples),
                             "robust": bool(corners) and pvt_ok == len(corners) and mc_ok == len(samples),
                             "corner_fails": cf, "mc_fails": mf}
    D["hubcheck"] = hub
    D["fh"], D["thd_floor"], D["pex_inj"] = {}, {}, {}
    for c in cards:
        cj = D["card_json"][c["card_id"]]
        D["fh"][c["card_id"]] = {st: fh_check(cj, st, (c.get(k) or {}).get("f_h_hz")) for st, k in (("pre", "pre"), ("partial", "post"))}
        D["thd_floor"][c["card_id"]] = {st: (c.get(k) or {}).get("thd_pct") is not None and c[k]["thd_pct"] <= THD_FLOOR
                                        for st, k in (("pre", "pre"), ("partial", "post"))}
        pex = docs / "designs" / c["card_id"] / "pex.spice"
        D["pex_inj"][c["card_id"]] = len(re.findall(r"(?im)^\s*Cpex", pex.read_text())) if pex.is_file() else None
    D["fh_affected"] = [cid for cid, v in D["fh"].items() if v["pre"]["affected"]]
    return D


THD_FLOOR = 0.005   # sim.py: thd_pct = min(1.4, max(0.005, ...))
FH_LO, FH_HI = 780.0, 1220.0   # sim.py: simulated f_H outside this window is replaced by clip(0.35 f + 653.25, 815, 1185)


def lna_fh_from_trace(ac):
    """-3 dB high cutoff of the stored *simulated* LNA response (log-interpolated; the stored trace is
    down-sampled to 72 points, so this reads ~1 % low versus the farm value)."""
    f, g = ac.get("freq_hz") or [], ac.get("lna_gain_db") or []
    mid = [b for a, b in zip(f, g) if 5 <= a <= 80]
    if not mid:
        return None
    t = max(mid) - 3.0
    for i in range(len(f) - 1):
        if f[i] >= 40 and g[i] >= t >= g[i + 1] and g[i] != g[i + 1]:
            fr = (g[i] - t) / (g[i] - g[i + 1])
            return 10 ** (math.log10(f[i]) + fr * (math.log10(f[i + 1]) - math.log10(f[i])))
    return None


def fh_check(card, stage, rep_fh):
    """Detect the repo's f_H conditioning and recover the simulated value.
    returns {rep, sim, src: repo|inverse|trace, affected}"""
    out = {"rep": rep_fh, "sim": rep_fh, "src": "repo", "affected": False, "trace": None}
    tr_ = ((_nom(card, stage).get("traces") or {}).get("ac")) or {}
    ft = lna_fh_from_trace(tr_)
    out["trace"] = ft
    if rep_fh is None or ft is None:
        return out
    if (ft < FH_LO or ft > FH_HI) and abs(ft / rep_fh - 1) > 0.03:
        out["affected"] = True
        if 815.0 < rep_fh < 1185.0:          # not clipped: the transform is invertible exactly
            out["sim"], out["src"] = (rep_fh - 653.25) / 0.35, "inverse"
        else:                                # clipped at 815 / 1185 Hz: only the trace is left
            out["sim"], out["src"] = ft, "trace"
    return out


def fh_text(fh, d=1):
    if not fh["affected"]:
        return f"{nf(fh['sim'], d)} Hz"
    return f"{'≈' if fh['src'] == 'trace' else ''}{nf(fh['sim'], d)} Hz"


def fh_note(fh):
    if not fh["affected"]:
        return ""
    how = ("inverting `sim.py`'s conditioning (f = (f_rep − 653.25 Hz)/0.35)" if fh["src"] == "inverse" else
           "the −3 dB point of the stored simulated LNA trace (72-point trace, ≈1–2 % accuracy; the repo value sits at the 1185 Hz clip)")
    return (f"f_H = {fh_text(fh)} recovered by the hub from {how}; the repo reports the conditioned value "
            f"{fh['rep']:g} Hz (simulated f_H outside 780–1220 Hz is replaced by clip(0.35·f + 653.25, 815, 1185) in `ecggen/sim.py`).")


SPEC_TEXT = ("library spec windows (P 100–1000 nW, f_H 750–1350 Hz, f_L 0.005–0.5 Hz, |Z_in| ≥ 50 MΩ, "
             "A_mid 88–104 dB, PM ≥ 50°)")


def pre_note(c, hub, fh=None, thd_floor=False):
    f_note = (" " + fh_note(fh)) if fh and fh["affected"] else ""
    if thd_floor:
        f_note += " THD is not listed: the stored 0.005 % is `sim.py`'s floor (true THD ≤ 0.005 %)."
    return ("Schematic netlist (ngspice-46), nominal TB1–TB6. PVT/MC pass counts and the robust flag are the hub's "
            f"re-check of the 29 stored corners / 30 MC runs against the {SPEC_TEXT}; the repo reports 29/29 and "
            "100 % yield for every card because `scripts/refresh_all_36_farm.py` forces each corner to pass. "
            "Model-derived figures (AFE gain incl. ideal VGA, A_OL, chopped noise, NEF/PEF, CMRR/PSRR, DR, PM) are not "
            "listed here — see the Overview tab." + (f_note if f_note else " The repo's f_H conditioning (simulated values outside 780–1220 Hz are "
            "replaced in `sim.py`) does not apply to this card."))


def partial_note(c, card, n_inj=None, fh=None, thd_floor=False):
    n_c = (c.get("physical") or {}).get("parasitic_c_count")
    same = (card.get("pre_pex") or {}).get("nominal", {}).get("metrics") == (card.get("post_pex") or {}).get("nominal", {}).get("metrics")
    return ("<b>Unverified post-PEX run, no measurable parasitic effect.</b> Nominal TB1–TB6 on the schematic ecg_afe netlist with only "
            f"the Magic-extracted parasitic capacitors on named top-level AFE nets injected ({n_inj if n_inj is not None else '?'} of {n_c} "
            "extracted caps; C only, internal-net parasitics and wiring R not back-annotated). PVT/MC were not re-run post-layout "
            "(the repo's post-PEX PVT/MC numbers are copies of the pre-PEX ones and are not shown)."
            + (" Every reported metric and trace equals the pre-PEX value to all stored digits although the injected caps "
               "(a few fF on vin/vout) should move |Z_in| and f_H by ~0.5–1 %, so it is unclear whether the parasitics took effect." if same else "")
            + ((" " + fh_note(fh)) if fh and fh["affected"] else "")
            + (" THD not listed (stored value is the 0.005 % floor)." if thd_floor else ""))


def design_summary(c, card):
    return (f"<small>`{c['card_id']}` · {card.get('arch_ref', '')}</small><br>"
            f"**{c['arch_name']} — {c['arch_title']}** · V<sub>DD</sub> = {c['vdd']:.1f} V (V<sub>CM</sub> = {c['vcm']:.2f} V) · "
            f"{c['tier_label']} (target {c['p_target_nw']:.0f} nW) · f<sub>chop</sub> = {c['f_chop_hz'] / 1e3:.1f} kHz · "
            f"β<sub>IBL</sub> = {c['beta_ibl']:.3f}<br>{card.get('description', '')}")


# ----------------------------------------------------------------------------- detail document
def _nom(card, stage):
    return ((card.get("pre_pex" if stage == "pre" else "post_pex") or {}).get("nominal")) or {}


def kpi_block(D, c, card, stage):
    nom = _nom(card, stage)
    m = nom.get("metrics") or {}
    pre_m = _nom(card, "pre").get("metrics") or {}
    post_m = _nom(card, "partial").get("metrics") or {}
    var = (card.get("pre_pex") or {}).get("variation") or {}
    pvt, mc = var.get("pvt") or {}, var.get("mc") or {}
    hub = D["hubcheck"][c["card_id"]]
    fh = D["fh"][c["card_id"]][stage]

    def cmp(k, unit, d):
        a, b = pre_m.get(k), post_m.get(k)
        if a is None:
            return ""
        if b is None:
            return "pre-PEX nominal"
        return f"pre {a:.{d}f}{unit} → partial post-PEX {b:.{d}f}{unit} ({'+' if b - a >= 0 else ''}{b - a:.{d}f}{unit})"

    M = " <small>(model)</small>"
    pvt_item = ({"label": "29-corner PVT & 30-run MC", "value": f"{hub['pvt_ok']}/{hub['pvt_total']} · {hub['mc_ok']}/{hub['mc_total']}",
                 "sub": f"PVT corners · MC runs in spec (hub re-check); repo reports {pvt.get('pass_count', '—')}/{pvt.get('total_count', '—')} (forced) · "
                        f"chopped V<sub>os</sub> {nf(mc.get('vos_chop_mean_uv'))} ± {nf(mc.get('vos_chop_sigma_uv'))} µV (model)"}
                if stage == "pre" else
                {"label": "29-corner PVT & 30-run MC", "value": "not re-run",
                 "sub": "post-layout PVT/MC not simulated (repo copies the pre-PEX numbers)"})
    items = [
        {"label": "Total power consumption", "value": pw_s(m.get("p_total_nw")),
         "sub": cmp("p_total_nw", " nW", 1) or f"Target: {c['p_target_nw']:g} nW"},
        {"label": "Total cascaded AFE gain" + M, "value": f"{nf(m.get('a_mid_db'))} dB",
         "sub": f"Stage-1 CCIA {nf(m.get('a_lna_db'))} dB (sim) + post-LNA VGA {nf(m.get('vga_gain_db'))} dB (ideal formula)"},
        {"label": "Core OTA open-loop A<sub>OL</sub>" + M, "value": f"{nf(m.get('a_ol_db'))} dB",
         "sub": "blend of the reused core OTA's A0 and the simulated g<sub>m</sub>/g<sub>ds</sub>"},
        {"label": "Passband [f<sub>L</sub>, f<sub>H</sub>]", "value": f"{nf(m.get('f_l_hz'), 3)} Hz – {fh_text(fh)}",
         "sub": (f"simulated f<sub>H</sub> recovered by the hub; repo reports the conditioned {fh['rep']:g} Hz" if fh["affected"] else cmp("f_h_hz", " Hz", 1))},
        {"label": "Input impedance |Z<sub>in</sub>(50 Hz)|", "value": zin_s(m.get("zin_50hz_ibl_on_mohm")),
         "sub": f"IBL OFF: {zin_s(m.get('zin_50hz_ibl_off_mohm'))} ({nf(m.get('zin_boost_factor'), 1)}× boost)"},
        {"label": "Chopped IRN (0.5 Hz–1 kHz)" + M, "value": f"{nf(m.get('irn_rms_chopped_uv'))} µVrms",
         "sub": f"Unchopped: {nf(m.get('irn_rms_unchopped_uv'))} µVrms ({nf(m.get('noise_reduction_x'), 1)}× reduction)"},
        {"label": "NEF / PEF" + M, "value": f"{nf(m.get('nef'))} / {nf(m.get('pef'))}",
         "sub": f"1 Hz chopped PSD: {nf(m.get('vn_1hz_chopped_nv_rthz'), 1)} nV/√Hz"},
        {"label": "CMRR / PSRR @ 50 Hz" + M, "value": f"{nf(m.get('cmrr_50hz_db'), 1)} / {nf(m.get('psrr_50hz_db'), 1)} dB",
         "sub": f"Electrode DC offset tolerance: ±{nf(m.get('edo_tolerance_mv'), 0)} mV"},
        {"label": "THD (@ 4 mVpp, 50 Hz)", "value": (f"≤ {nf(m.get('thd_pct'), 3)}% (floor)" if D["thd_floor"][c["card_id"]][stage] else f"{nf(m.get('thd_pct'), 3)}% ({nf(m.get('thd_db'), 1)} dB)"),
         "sub": f"SFDR: {nf(m.get('sfdr_db'), 1)} dB · IMD3: {nf(m.get('imd3_db'), 1)} dBc (model)"},
        {"label": "Dynamic range (@ 1% THD)" + M, "value": f"{nf(m.get('dr_db'), 1)} dB",
         "sub": f"Max linear input: {nf(m.get('vin_max_1pct_mvpp'))} mVpp (model)"},
        {"label": "ADC S&H + sense-amp drive" + M, "value": f"{nf(m.get('qrs_peak_out_mv'), 1)} mV R-peak",
         "sub": f"S&H tracking error: {nf(m.get('sh_tracking_error_mv'), 3)} mV"},
        pvt_item,
    ]
    return stats(items, stage=stage, alt="kpi",
                 caption="Tiles marked *(model)* are closed-form / model-derived in `ecggen/sim.py` (see the spec table below); "
                         "they are not part of the hub's simulation-stage results.")


def provenance_of(key):
    return {
        "power_nw": ("sim", "static I·V from ngspice OP + chopper/ADC switching energy of the reused cells"),
        "gain_db": ("model", "simulated LNA gain + ideal post-LNA VGA formula"),
        "a_ol_db": ("model", "0.65·reused-OTA A0 + 0.35·2.05·sim g_m/g_ds, clipped 93.8–112.4 dB"),
        "a_lna_db": ("sim", "TB1 AC"),
        "bw_high_hz": ("sim", "TB1 AC; pulled toward 1 kHz when outside 780–1220 Hz"),
        "bw_low_hz": ("sim", "TB1 AC; capped at 0.22 Hz"),
        "zin_50hz_mohm": ("sim", "TB3 AC input current"),
        "zin_boost_x": ("sim", "TB3 IBL on / off"),
        "irn_uvrms": ("model", "white floor from per-architecture NEF constant × BJT limit"),
        "nef": ("model", "from the model chopped IRN"),
        "thd_pct": ("sim", "TB5 transient FFT, floored at 0.005 %"),
        "dr_db": ("model", "formula input ceiling / model IRN"),
        "cmrr_db": ("model", "72 % analytic model + 28 % clipped simulation"),
        "psrr_db": ("model", "72 % analytic model + 28 % clipped simulation"),
        "edo_max_mv": ("sim", "TB2 LNA gain vs EDO (+ constant VGA); floored at 300 mV"),
        "pm_deg": ("model", "estimate from passband peaking"),
    }.get(key, ("—", ""))


SPEC_FIELD = {"power_nw": "p_total_nw", "gain_db": "a_mid_db", "a_ol_db": "a_ol_db", "a_lna_db": "a_lna_db",
              "bw_high_hz": "f_h_hz", "bw_low_hz": "f_l_hz", "zin_50hz_mohm": "zin_50hz_ibl_on_mohm",
              "zin_boost_x": "zin_boost_factor", "irn_uvrms": "irn_rms_chopped_uv", "nef": "nef", "thd_pct": "thd_pct",
              "dr_db": "dr_db", "cmrr_db": "cmrr_50hz_db", "psrr_db": "psrr_50hz_db", "edo_max_mv": "edo_tolerance_mv",
              "pm_deg": "pm_deg"}


def spec_table(D, c, card, stage):
    m = _nom(card, stage).get("metrics") or {}
    fh = D["fh"][c["card_id"]][stage]
    floor = D["thd_floor"][c["card_id"]][stage]
    rows = []
    for key, t in D["spec"].items():
        v = m.get(SPEC_FIELD.get(key, key))
        prov, how = provenance_of(key)
        shown = rv(v)
        if key == "bw_high_hz" and fh["affected"]:
            v = fh["sim"]
            shown = cell(rv(v), None, f"hub-recovered simulated f_H; repo value {fh['rep']:g} Hz is conditioned")
            prov, how = "sim (recovered)", fh_note(fh)
        if key == "thd_pct" and floor:
            shown = f"≤ {v:g} (floor)"
        lo, hi = t.get("min"), t.get("max")
        ok = None if v is None else not ((lo is not None and v < lo) or (hi is not None and v > hi))
        if isinstance(shown, dict):
            shown["s"] = None if ok is None else ("good" if ok else "bad")
        else:
            shown = cell(shown, None if ok is None else ("good" if ok else "bad"))
        rows.append({"spec": t.get("label", key), "window": window_text(D["spec"], key, t.get("unit", "")),
                     "value": shown, "unit": t.get("unit", ""),
                     "status": ok_cell(ok, "PASS", "FAIL"), "prov": cell(prov, "muted" if prov == "model" else None, how)})
    tier = D["tier"][c["tier"]]
    for label, field, lo, hi, unit, prov in (
            (f"Tier power window ({c['tier'].upper()})", "p_total_nw", tier["p_min_nw"], tier["p_max_nw"], "nW", "sim"),
            (f"Tier noise ceiling ({c['tier'].upper()})", "irn_rms_chopped_uv", None, tier["noise_max_uvrms"], "µVrms", "model"),
            (f"Tier DR floor ({c['tier'].upper()})", "dr_db", tier["dr_min_db"], None, "dB", "model")):
        v = m.get(field)
        ok = None if v is None else not ((lo is not None and v < lo) or (hi is not None and v > hi))
        win = f"{lo:g}–{hi:g} {unit}" if lo is not None and hi is not None else (f"≥ {lo:g} {unit}" if lo is not None else f"≤ {hi:g} {unit}")
        rows.append({"spec": label, "window": win, "value": cell(rv(v), "good" if ok else "bad"), "unit": unit,
                     "status": ok_cell(ok, "PASS", "FAIL"), "prov": cell(prov, "muted" if prov == "model" else None)})
    return table("Nominal spec compliance (hub check of the stored nominal values)",
                 [col("spec", "Specification"), col("window", "Library window"), col("value", "Value", align="r", digits=5),
                  col("unit", "Unit"), col("status", "Status"), col("prov", "Provenance", title="sim = simulation-derived; model = closed-form in ecggen/sim.py (hover for details)")],
                 rows, stage=stage, alt="spec", search=False,
                 caption=f"Repo `spec_pass` flag: **{'PASS' if _nom(card, stage).get('spec_pass') else 'FAIL'}** "
                         "(the repo checks the tier noise ceiling, not the global 7.5 µVrms one, and its own conditioned f_H). Hover a provenance cell for how the value is obtained.")


def checklist(D, c, card):
    pre = _nom(card, "pre")
    m = pre.get("metrics") or {}
    post = _nom(card, "partial")
    var = (card.get("pre_pex") or {}).get("variation") or {}
    pvt, mc, ibl = var.get("pvt") or {}, var.get("mc") or {}, var.get("ibl_variation") or {}
    ph = card.get("physical") or {}
    hub = D["hubcheck"][c["card_id"]]
    bad_corners = [k for k, v in hub["corner_fails"].items() if v]
    spec_fails = [row for row in spec_table(D, c, card, "pre")["rows"] if row["status"]["v"] == "FAIL"]
    rows = [
        ["Nominal Spec Compliance (100nW–1µW, 1kHz BW)",
         f"Power = {nf(m.get('p_total_nw'), 1)} nW, Gain = {nf(m.get('a_mid_db'))} dB, Band = [{nf(m.get('f_l_hz'), 3)} Hz, {nf(m.get('f_h_hz'), 1)} Hz]",
         ok_cell(bool(pre.get("spec_pass"))),
         cell("PASS", "good") if not spec_fails else cell(f"{len(spec_fails)} item(s) outside window", "warn",
                                                           "; ".join(f"{x['spec']}: {x['value']['v']}" for x in spec_fails))],
        ["Input Impedance Boost (IBL ON vs OFF)",
         f"|Zin(50Hz)| = {zin_s(m.get('zin_50hz_ibl_on_mohm'))} ({nf(m.get('zin_boost_factor'), 1)}× boost over unboosted {zin_s(m.get('zin_50hz_ibl_off_mohm'))})",
         ok_cell((m.get("zin_50hz_ibl_on_mohm") or 0) >= 50), ok_cell((m.get("zin_50hz_ibl_on_mohm") or 0) >= 50)],
        ["29-Corner PVT Resilience (TB7)",
         f"{pvt.get('pass_count', '—')}/{pvt.get('total_count', '—')} corners pass (tt/ss/ff/sf/fs × −40/27/85°C × ±10% VDD)",
         ok_cell(pvt.get("pass_count") == pvt.get("total_count")),
         cell(f"{hub['pvt_ok']}/{hub['pvt_total']} in spec", "good" if hub["pvt_ok"] == hub["pvt_total"] else "bad",
              ", ".join(bad_corners) or None)],
        ["30-Run Per-Finger Mismatch Monte Carlo (TB8-A)",
         f"Yield {nf(mc.get('yield_pct'), 1)}%, Chopped Vos = {nf(mc.get('vos_chop_mean_uv'))} µV (Unchopped σ = {nf(mc.get('vos_unchop_sigma_mv'))} mV)",
         ok_cell((mc.get("yield_pct") or 0) >= 95),
         cell(f"{hub['mc_ok']}/{hub['mc_total']} runs in spec", "good" if hub["mc_ok"] == hub["mc_total"] else "bad")],
        ["±15% IBL Capacitor Variation Stability (TB8-B)",
         "Unconditionally stable across ΔCpf/Cpf ∈ [−15%, +15%] (min PM ≥ 60°)",
         ok_cell(bool(ibl.get("unconditionally_stable"))),
         cell("not verifiable", "muted", "the PM in this sweep is a peaking-based estimate, constant across the sweep")],
        ["KLayout GF180 DRC Signoff (gf180mcu.drc)",
         "0 effective DRC violations (PASS)" if ph.get("drc_ok") else "Pending", ok_cell(ph.get("drc_ok")),
         cell(f"{ph.get('drc_effective', 0)} effective / {ph.get('drc_ignored', 0)} ignored", "good" if ph.get("drc_ok") else "bad")],
        ["KLayout GF180 LVS Signoff (gf180mcu.lvs)", ph.get("lvs_conclusion") or "Pending", ok_cell(ph.get("lvs_ok")),
         ok_cell(ph.get("lvs_ok"))],
        ["Magic Parasitic Extraction & Post-PEX Farm Closure",
         f"{ph.get('nfet_fingers')} NFET + {ph.get('pfet_fingers')} PFET fingers, {ph.get('mim_caps')} MIM caps, "
         f"{ph.get('poly_resistors')} poly res, {ph.get('parasitic_c_count')} parasitic caps" if ph.get("pex_ok") else "Pending",
         ok_cell(bool(ph.get("pex_ok") and post)),
         cell("partial", "warn", "C-only, top-level named nets only; nominal TB1–TB6 only")],
    ]
    return table("Verification Signoff Checklist",
                 [col("check", "Verification check", md=True, wrap=True), col("ev", "Evidence summary", md=True, wrap=True), col("repo", "Repo status"), col("hub", "Hub re-check", wrap=True)],
                 [{"check": f"<b>{a}</b>", "ev": b, "repo": rs, "hub": hs} for a, b, rs, hs in rows], search=False, csv=False,
                 caption="Repo status = the old site's PASS/WARN/PENDING badge; hub re-check = the same evidence against the library spec windows (hover for details).")


def reuse_table(D, c, card):
    rb = card.get("reused_blocks") or {}
    sz = card.get("sizing") or {}
    m = _nom(card, "pre").get("metrics") or {}
    aux = rb.get("aux_ota_id")
    rows = [
        ["Reused Core LNA OTA (`opa-gen`)", f"{link(rb.get('core_ota_id'), opa_href(rb.get('core_ota_id')))} (I<sub>core</sub> = {nf(sz.get('i_core_na'), 1)} nA)"],
        ["Reused Aux / DSL / PGA OTA (`opa-gen`)", (f"{link(aux, opa_href(aux))}" if aux else "`None (Passive IBL)`") + f" (I<sub>aux</sub> = {nf(sz.get('i_aux_na'), 1)} nA)"],
        ["Reused Chopper Switch (`switch-gen`)", f"{link(rb.get('chop_sw_key'), '#/switch/' + rb.get('chop_sw_key', ''))} @ f<sub>chop</sub> = {c['f_chop_hz'] / 1e3:.1f} kHz"],
        ["Reused Bootstrapped S&H Switch (`switch-gen`)", f"{link(rb.get('sh_sw_key'), '#/switch/' + rb.get('sh_sw_key', ''))} driving C<sub>adc</sub> = {nf(sz.get('c_adc_ff'), 1)} fF"],
        ["Reused Clocked Sense-Amp (`sa-gen`)", f"{link(rb.get('comp_key'), '#/sa/' + rb.get('comp_key', ''))} @ f<sub>s,ADC</sub> = 2.0 kS/s"],
        ["Input / Feedback MIM Caps (C<sub>in</sub> / C<sub>fb</sub>)", f"C<sub>in</sub> = {nf(sz.get('c_in_pf'), 3)} pF ({sz.get('n_cin')}× {sz.get('c_in_um')}μm) · C<sub>fb</sub> = {nf(sz.get('c_fb_ff'), 1)} fF ({sz.get('c_fb_um')}μm)"],
        ["IBL Positive-Feedback Cap (C<sub>pf</sub>)", f"C<sub>pf</sub> = {nf(sz.get('c_pf_ff'), 1)} fF ({sz.get('c_pf_um')}μm, β<sub>IBL</sub> = {c['beta_ibl']:.3f})"],
        ["Anti-Aliasing LPF Cap (C<sub>lpf</sub>)", f"C<sub>lpf</sub> = {nf(sz.get('c_lpf_pf'), 3)} pF ({sz.get('n_clpf')}× {sz.get('c_lpf_um')}μm)"],
        [f"Power Breakdown (Total = {pw_s(m.get('p_total_nw'))})",
         f"LNA: {nf(m.get('p_lna_nw'), 1)} nW · Aux: {nf(m.get('p_aux_nw'), 1)} nW · Chop: {nf(m.get('p_chop_nw'), 1)} nW · ADC S&H/Comp: {nf(m.get('p_adc_nw'), 1)} nW "
         "<small>(LNA/Aux split is a fixed ratio of the simulated static power; chop/ADC from reused-cell energy × f)</small>"],
    ]
    return table("Reused Sub-Blocks & Passive Sizing", [col("k", "Item", md=True, wrap=True), col("v", "Value", md=True, wrap=True)],
                 [{"k": a, "v": b} for a, b in rows], search=False, csv=False,
                 caption="Links open the reused cell on its own hub tab (op-amps: 200 fF-load library, which `ecggen/select.py` loads first).")


def device_table(card, stage):
    devs = _nom(card, stage).get("devices") or []
    rows = []
    for d in devs:
        reg = d.get("region") or "sat"
        rows.append({"inst": d.get("inst"), "block": d.get("block"), "role": d.get("role"), "model": d.get("model"),
                     "wf": r(d.get("w_finger_um")), "l": r(d.get("l_um")), "m": d.get("m"), "wt": r(d.get("w_total_um")),
                     "tg": r(d.get("target_gmid")), "gs": r(d.get("gmid_sim")), "id": r(d.get("id_na")),
                     "gm": r(mul(d.get("gm_us"), 1e3)), "gds": r(d.get("gds_ns")), "vgs": r(d.get("vgs_mv")),
                     "vds": r(d.get("vds_mv")), "vth": r(d.get("vth_mv")), "vdsat": r(d.get("vdsat_mv")),
                     "reg": cell(reg, "bad" if "triode" in reg.lower() else "good" if "sat" in reg.lower() else None)})
    return table("Transistor Sizing & Simulated Operating Point Table (Nominal TT, 27 °C)",
                 [col("inst", "Instance"), col("block", "Sub-block"), col("role", "Role"), col("model", "Model"),
                  col("wf", "W<sub>f</sub>", "μm"), col("l", "L", "μm"), col("m", "m"), col("wt", "W<sub>tot</sub>", "μm"),
                  col("tg", "g<sub>m</sub>/I<sub>D</sub> target", "V⁻¹"), col("gs", "g<sub>m</sub>/I<sub>D</sub> sim", "V⁻¹", digits=4),
                  col("id", "I<sub>D</sub>", "nA", digits=4), col("gm", "g<sub>m</sub>", "nS", digits=4), col("gds", "g<sub>ds</sub>", "nS", digits=3),
                  col("vgs", "V<sub>GS</sub>", "mV", digits=4), col("vds", "V<sub>DS</sub>", "mV", digits=4), col("vth", "V<sub>th</sub>", "mV", digits=4),
                  col("vdsat", "V<sub>DSAT</sub>", "mV", digits=3), col("reg", "Region")],
                 rows, stage=stage, alt="devices", search=False,
                 caption="g<sub>m</sub> converted from the stored µS value (the old site showed this column empty); g<sub>ds</sub> and V<sub>th</sub> added from the same OP record.")


def tb_charts(card, c, mode, fh_info=None):
    """Port of the old 'Simulation Waveforms' tab.  mode: pre | partial | overlay (old Pre + Post overlay)."""
    pre, post = _nom(card, "pre"), _nom(card, "partial")
    tp, tq = pre.get("traces") or {}, post.get("traces") or {}
    pm_, qm = pre.get("metrics") or {}, post.get("metrics") or {}
    rb = card.get("reused_blocks") or {}
    show_pre = mode in ("pre", "overlay")
    show_post = mode in ("partial", "overlay") and bool(post)
    dash_post = "dash" if mode == "overlay" else None
    m = qm if mode in ("partial", "overlay") and post else pm_
    fhs = fh_info.get("partial" if mode in ("partial", "overlay") and post else "pre") if fh_info else None
    tag = {"pre": "Pre-PEX", "partial": "Partial post-PEX", "overlay": "Post-PEX"}
    out = []

    def add(alt, block):
        if mode != "overlay":
            block["stage"] = mode
            block["alt"] = alt
        out.append(block)

    # TB1
    s = []
    if show_pre and tp.get("ac", {}).get("freq_hz"):
        a = tp["ac"]
        s.append(tr(a["freq_hz"], a["gain_db"], f"Pre-PEX Total AFE Gain ({nf(pm_.get('a_mid_db'))} dB, fH={nf(pm_.get('f_h_hz'), 0)}Hz)", PRE_C, width=2.5))
        if a.get("ol_gain_db"):
            s.append(tr(a["freq_hz"], a["ol_gain_db"], f"Core OTA Open-Loop Gain AOL ({nf(pm_.get('a_ol_db'), 1)} dB, model)", "#934eb0", "dot", 2))
        if a.get("lna_gain_db"):
            s.append(tr(a["freq_hz"], a["lna_gain_db"], f"Stage-1 CCIA LNA Gain ({nf(pm_.get('a_lna_db'))} dB = Cin/Cfb)", "#1e8565", "dashdot", 1.9))
    if show_post and tq.get("ac", {}).get("freq_hz"):
        a = tq["ac"]
        s.append(tr(a["freq_hz"], a["gain_db"], f"{tag['partial'] if mode == 'partial' else 'Post-PEX'} Total AFE Gain ({nf(qm.get('a_mid_db'))} dB, fH={nf(qm.get('f_h_hz'), 0)}Hz)", POST_C, dash_post, 2.3))
        if mode == "partial":
            if a.get("ol_gain_db"):
                s.append(tr(a["freq_hz"], a["ol_gain_db"], f"Core OTA Open-Loop Gain AOL ({nf(qm.get('a_ol_db'), 1)} dB, model)", "#934eb0", "dot", 2))
            if a.get("lna_gain_db"):
                s.append(tr(a["freq_hz"], a["lna_gain_db"], f"Stage-1 CCIA LNA Gain ({nf(qm.get('a_lna_db'))} dB)", "#1e8565", "dashdot", 1.9))
    if s:
        add("tb1", chart("TB1: AFE Gain Hierarchy — Cascaded AFE |A_AFE(f)|, Core OTA |A_OL(f)| & Stage-1 LNA |A_LNA(f)|", s,
                         "Frequency (Hz)", "Magnitude Gain (dB)", logx=True,
                         caption=f"Cascaded AFE Gain = {nf(m.get('a_mid_db'))} dB (Stage-1 LNA {nf(m.get('a_lna_db'))} dB + Post-LNA VGA {nf(m.get('vga_gain_db'))} dB) · "
                                 f"Core OTA AOL = {nf(m.get('a_ol_db'), 1)} dB · Passband [{nf(m.get('f_l_hz'), 3)} Hz, {fh_text(fhs) if fhs else nf(m.get('f_h_hz'), 1) + ' Hz'}]. "
                                 + (f"*Hub: {fh_note(fhs)}* " if fhs and fhs["affected"] else "") +
                                 "*Hub note: the LNA curve is simulated; the AFE curve adds an analytic VGA shape and the A_OL curve is an analytic two-pole model.*"))
    # TB1 phase (not on the old site)
    if mode != "overlay" and (tp if mode == "pre" else tq).get("ac", {}).get("phase_deg"):
        a = (tp if mode == "pre" else tq)["ac"]
        add("tb1ph", chart("TB1: Closed-loop phase response", [tr(a["freq_hz"], a["phase_deg"], "Phase", PRE_C if mode == "pre" else POST_C)],
                           "Frequency (Hz)", "Phase (°)", logx=True, caption="Phase of the simulated closed-loop output (stored in `card.json`, not plotted by the old site)."))
    # TB3
    s = []
    if show_pre and tp.get("zin", {}).get("freq_hz"):
        z = tp["zin"]
        s.append(tr(z["freq_hz"], z["ibl_on_mohm"], f"Pre-PEX IBL ON (@50Hz: {zin_s(pm_.get('zin_50hz_ibl_on_mohm'))})", "#1e8565"))
        s.append(tr(z["freq_hz"], z["ibl_off_mohm"], f"Pre-PEX IBL OFF (@50Hz: {zin_s(pm_.get('zin_50hz_ibl_off_mohm'))})", "#64748b", "dot"))
    if show_post and tq.get("zin", {}).get("freq_hz"):
        z = tq["zin"]
        s.append(tr(z["freq_hz"], z["ibl_on_mohm"], f"{'Partial post' if mode == 'partial' else 'Post'}-PEX IBL ON (@50Hz: {zin_s(qm.get('zin_50hz_ibl_on_mohm'))})", POST_C, dash_post))
        if mode == "partial":
            s.append(tr(z["freq_hz"], z["ibl_off_mohm"], f"Partial post-PEX IBL OFF (@50Hz: {zin_s(qm.get('zin_50hz_ibl_off_mohm'))})", "#64748b", "dot"))
    if s:
        add("tb3", chart("TB3: Input Impedance Boost |Zin(f)| — IBL ON vs. IBL OFF", s, "Frequency (Hz)", "Input Impedance |Zin| (MΩ)",
                         logx=True, logy=True, caption=f"{nf(m.get('zin_boost_factor'), 1)}× impedance boost at 50 Hz via {c['ibl_type']}"))
    # TB4
    s = []
    if show_pre and tp.get("noise", {}).get("freq_hz"):
        n = tp["noise"]
        s.append(tr(n["freq_hz"], n["vn_unchopped_nv_rthz"], f"Unchopped 1/f + Thermal (IRN={nf(pm_.get('irn_rms_unchopped_uv'))} µVrms)", "#94a3b8", "dot"))
        s.append(tr(n["freq_hz"], n["vn_chopped_nv_rthz"], f"Pre-PEX Chopped @ {c['f_chop_hz'] / 1e3:.0f}kHz (IRN={nf(pm_.get('irn_rms_chopped_uv'))} µVrms)", PRE_C))
    if show_post and tq.get("noise", {}).get("freq_hz"):
        n = tq["noise"]
        if mode == "partial":
            s.append(tr(n["freq_hz"], n["vn_unchopped_nv_rthz"], f"Unchopped 1/f + Thermal (IRN={nf(qm.get('irn_rms_unchopped_uv'))} µVrms)", "#94a3b8", "dot"))
        s.append(tr(n["freq_hz"], n["vn_chopped_nv_rthz"], f"{'Partial post' if mode == 'partial' else 'Post'}-PEX Chopped (IRN={nf(qm.get('irn_rms_chopped_uv'))} µVrms)", POST_C, dash_post))
    if s:
        add("tb4", chart("TB4: Input-Referred Noise PSD — Chopped vs. Unchopped", s, "Frequency (Hz)", "Input-Referred Noise Density (nV/√Hz)",
                         logx=True, logy=True,
                         caption=f"Chopping suppresses 1 Hz noise from {nf(m.get('vn_1hz_unchopped_nv_rthz'), 0)} nV/√Hz down to {nf(m.get('vn_1hz_chopped_nv_rthz'), 1)} nV/√Hz "
                                 f"({nf(m.get('noise_reduction_x'), 1)}× integrated RMS reduction). *Hub note: the chopped PSD is a model (white floor = per-architecture NEF "
                                 "constant × BJT limit with a chopper-folding shape); the unchopped PSD is ngspice `.noise` with that model floor substituted above 300 Hz.*"))
    # TB2 CMRR/PSRR
    s = []
    if show_pre and tp.get("ac", {}).get("cmrr_db"):
        a = tp["ac"]
        s.append(tr(a["freq_hz"], a["cmrr_db"], f"Pre-PEX CMRR (@50Hz: {nf(pm_.get('cmrr_50hz_db'), 1)} dB)", PRE_C))
        s.append(tr(a["freq_hz"], a["psrr_db"], f"Pre-PEX PSRR+ (@50Hz: {nf(pm_.get('psrr_50hz_db'), 1)} dB)", "#d96b27"))
    if show_post and tq.get("ac", {}).get("cmrr_db"):
        a = tq["ac"]
        lab = "Partial post" if mode == "partial" else "Post"
        s.append(tr(a["freq_hz"], a["cmrr_db"], f"{lab}-PEX CMRR (@50Hz: {nf(qm.get('cmrr_50hz_db'), 1)} dB)", PRE_C, "dash"))
        s.append(tr(a["freq_hz"], a["psrr_db"], f"{lab}-PEX PSRR+ (@50Hz: {nf(qm.get('psrr_50hz_db'), 1)} dB)", "#d96b27", "dash"))
    if s:
        add("tb2", chart("TB2: Common-Mode & Power-Supply Rejection (CMRR & PSRR+)", s, "Frequency (Hz)", "Rejection Ratio (dB)", logx=True,
                         caption="Includes 0.04% MIM capacitor mismatch and finite OTA common-mode rejection. *Hub note: both curves are 72 % analytic model + "
                                 "28 % clipped simulation (`ecggen/sim.py`).*"))
    # TB2 EDO
    s = []
    if show_pre and tp.get("edo", {}).get("edo_mv"):
        s.append(tr(tp["edo"]["edo_mv"], tp["edo"]["gain_db"], "Pre-PEX Midband Gain vs EDO", PRE_C, mode="lines+markers"))
    if show_post and tq.get("edo", {}).get("edo_mv"):
        s.append(tr(tq["edo"]["edo_mv"], tq["edo"]["gain_db"], f"{'Partial post' if mode == 'partial' else 'Post'}-PEX Midband Gain vs EDO", POST_C, dash_post, mode="lines+markers"))
    if s:
        add("edo", chart("TB2: Electrode DC Offset (EDO) Tolerance Sweep (±350 mV)", s, "Differential Electrode DC Offset V_EDO (mV)", "Midband Gain (dB)",
                         caption=f"AC-coupled input blocking + {c['hpf_type']} maintains flat gain across ±{nf(m.get('edo_tolerance_mv'), 0)} mV EDO. "
                                 "*Hub note: simulated LNA gain at each offset + the constant ideal VGA gain.*"))
    # TB5 FFT
    s = []
    if show_pre and tp.get("linearity", {}).get("fft_freq_hz"):
        s.append(tr(tp["linearity"]["fft_freq_hz"], tp["linearity"]["fft_mag_db"], f"Pre-PEX Spectrum (THD={nf(pm_.get('thd_pct'), 3)}%)", PRE_C))
    if show_post and tq.get("linearity", {}).get("fft_freq_hz"):
        s.append(tr(tq["linearity"]["fft_freq_hz"], tq["linearity"]["fft_mag_db"], f"{'Partial post' if mode == 'partial' else 'Post'}-PEX Spectrum (THD={nf(qm.get('thd_pct'), 3)}%)", POST_C, dash_post))
    if s:
        add("fft", chart("TB5: Coherent 50 Hz Output FFT Spectrum (4 mVpp Input)", s, "Frequency (Hz)", "Normalized Magnitude (dBc)",
                         caption=f"HD2 = {nf(m.get('hd2_db'), 1)} dBc · HD3 = {nf(m.get('hd3_db'), 1)} dBc · SFDR = {nf(m.get('sfdr_db'), 1)} dB"))
    # TB5 THD vs amplitude
    s = []
    if show_pre and tp.get("linearity", {}).get("amp_mvpp"):
        s.append(tr(tp["linearity"]["amp_mvpp"], tp["linearity"]["thd_pct"], f"Pre-PEX THD vs Amplitude (DR={nf(pm_.get('dr_db'), 1)} dB)", "#1e8565", mode="lines+markers"))
    if show_post and tq.get("linearity", {}).get("amp_mvpp"):
        s.append(tr(tq["linearity"]["amp_mvpp"], tq["linearity"]["thd_pct"], f"{'Partial post' if mode == 'partial' else 'Post'}-PEX THD vs Amplitude (DR={nf(qm.get('dr_db'), 1)} dB)", POST_C, dash_post, mode="lines+markers"))
    if s:
        add("thd", chart("TB5: Total Harmonic Distortion (THD) vs. Input Amplitude", s, "Differential Input Amplitude Vin,pp (mVpp)", "THD (%)", logx=True, logy=True,
                         caption=f"1% THD linear input ceiling = {nf(m.get('vin_max_1pct_mvpp'))} mVpp → Dynamic Range = {nf(m.get('dr_db'), 1)} dB. "
                                 "*Hub note: only the 4 mVpp point is simulated; the other amplitudes and the 1 % ceiling are a closed-form extrapolation.*"))
    # TB5 transient (not on the old site)
    lin = (tp if mode == "pre" else tq).get("linearity", {})
    if mode != "overlay" and lin.get("tran_t_ms"):
        add("tran", chart("TB5: 50 Hz single-tone transient (4 mVpp)", [
            tr(lin["tran_t_ms"], lin["tran_vin_mv"], "Differential input v<sub>in</sub> (mV)", "#64748b", "dot"),
            tr(lin["tran_t_ms"], lin["tran_vout_mv"], "Output v<sub>out</sub> − DC (mV)", PRE_C if mode == "pre" else POST_C, yaxis="y2")],
            "Time (ms)", "Input (mV)", layout={"yaxis2": {"title": {"text": "Output (mV)"}, "overlaying": "y", "side": "right"}},
            caption="Transient behind the FFT above (stored in `card.json`, not plotted by the old site)."))
    # TB6
    ecg = (tq if (show_post and tq.get("ecg_adc", {}).get("t_ms")) else tp).get("ecg_adc") or {}
    if mode == "pre":
        ecg = tp.get("ecg_adc") or {}
    if ecg.get("t_ms"):
        add("ecg", chart("TB6: 2-Beat Lead-II P-QRS-T ECG Transient Driving Reused ADC S&H + Sense-Amp Comparator", [
            tr(ecg["t_ms"], ecg["vout_v"], "AFE Amplified ECG Output Vout(t)", PRE_C, width=2.5),
            tr(ecg["t_ms"], ecg["vsh_v"], f"Bootstrapped S&H Staircase Vsh(t) ({rb.get('sh_sw_key')})", "#1e8565", "dot", 1.9, line={"color": "#1e8565", "width": 1.9, "dash": "dot", "shape": "hv"}),
            tr(ecg["t_ms"], ecg["comp_outp_v"], f"Sense-Amp R-Wave Strobe ({rb.get('comp_key')})", "#d96b27", None, 1.5, line={"color": "#d96b27", "width": 1.5, "shape": "hv"})],
            "Cardiac Time (ms) [2 Beats @ 75 BPM]", "Output Voltage Around VCM (V)",
            caption=f"1.55 mV Lead-II P-QRS-T input amplified to +{nf(m.get('qrs_peak_out_mv'), 1)} mV R-peak above VCM · S&H tracking error = {nf(m.get('sh_tracking_error_mv'), 3)} mV. "
                    "*Hub note: model waveform — an ideal band-pass of the synthetic ECG × LNA gain, scaled by a clipped (0.92–1.06) simulated span ratio; "
                    "the S&H staircase and comparator strobe are constructed analytically, not simulated.*"))
    return out


def robustness_blocks(D, c, card):
    var = (card.get("pre_pex") or {}).get("variation") or {}
    pvt, mc = var.get("pvt") or {}, var.get("mc") or {}
    ibl, el = var.get("ibl_variation") or {}, var.get("electrode_mismatch") or {}
    hub = D["hubcheck"][c["card_id"]]
    corners = pvt.get("corners") or []
    labels = [x["corner"] for x in corners]
    cols = [GOOD_C if not hub["corner_fails"].get(x["corner"]) else BAD_C for x in corners]
    charts = []
    if corners:
        lay = {"xaxis": {"type": "category", "tickangle": -40}, "margin": {"l": 58, "r": 20, "t": 44, "b": 96}, "hovermode": "closest"}
        charts.append(chart("TB7: Midband Gain Across All 29 PVT Corners",
                            [bar(labels, [x["a_mid_db"] for x in corners], "Midband Gain (dB)", None, marker={"color": cols})],
                            "PVT Corner (Process / Temp / Supply)", "Midband Gain (dB)", layout=lay, height=420,
                            caption=f"Gain envelope: [{nf(pvt.get('a_mid_min_db'))} dB, {nf(pvt.get('a_mid_max_db'))} dB] across tt/ss/ff/sf/fs × −40/27/85°C × ±10% VDD. "
                                    "*Hub: red bars = corner outside the library spec windows. The stored corner gains were rewritten by the refresh script "
                                    "(LNA deviations > 2.2 dB compressed ×0.25, then + ideal VGA).*"))
        charts.append(chart("TB7: Boosted Input Impedance |Zin(50Hz)| Across All 29 PVT Corners",
                            [bar(labels, [x["zin_50hz_mohm"] for x in corners], "|Zin @ 50Hz| (MΩ)", None, marker={"color": cols})],
                            "PVT Corner (Process / Temp / Supply)", "|Zin @ 50Hz| (MΩ)", layout=lay, height=420,
                            caption=f"Worst-case PVT input impedance = {zin_s(pvt.get('zin_min_mohm'))} (>50 MΩ target across all 29 corners). *Hub: red bars = corner outside the spec windows.*"))
    samples = mc.get("samples") or []
    if samples:
        charts.append(chart("TB8-A: 30-Run Per-Finger Mismatch MC — Chopped Input Offset (µV)",
                            [{"type": "histogram", "x": rl([s["vos_chop_uv"] for s in samples]), "nbinsx": 12, "marker": {"color": PRE_C},
                              "name": f"Chopped Vos (mean={nf(mc.get('vos_chop_mean_uv'))} µV, σ={nf(mc.get('vos_chop_sigma_uv'))} µV)"}],
                            "Residual Chopped Input-Referred Offset Vos,chop (µV)", "MC Sample Count", layout={"hovermode": "closest"},
                            caption=f"Unchopped static input offset σ = {nf(mc.get('vos_unchop_sigma_mv'))} mV → Chopping reduces offset to {nf(mc.get('vos_chop_mean_uv'))} µV. "
                                    "*Hub note: model — V<sub>os,chop</sub> = |V<sub>os,unchop</sub>|/180 + 0.85·|sin(1.7·seed)| µV; only the unchopped offset is simulated.*"))
        charts.append(chart("TB8-A: 30-Run Mismatch MC — Boosted |Zin(50Hz)| vs. Midband Gain",
                            [tr([s["a_mid_db"] for s in samples], [s["zin_50hz_mohm"] for s in samples], "MC Runs (n=30)", "#1e8565", mode="markers",
                                marker={"color": ["#1e8565" if not hub["mc_fails"].get(s["seed"]) else BAD_C for s in samples], "size": 8.5},
                                text=[f"seed {s['seed']}" for s in samples])],
                            "Midband Gain A_mid (dB)", "Boosted |Zin @ 50Hz| (MΩ)", layout={"hovermode": "closest"},
                            caption=f"Gain σ = {nf(mc.get('a_mid_std_db'), 3)} dB · 5th-percentile |Zin| = {zin_s(mc.get('zin_p5_mohm'))}. "
                                    "*Hub: red = run outside the spec windows; the stored gain σ is floored at 0.08 dB by the refresh script.*"))
    if ibl.get("delta_cpf_pct"):
        charts.append(chart("TB8-B: ±15% IBL Capacitor Ratio Variation Sweep (Stability & |Zin|)", [
            tr(ibl["delta_cpf_pct"], ibl["zin_50hz_mohm"], "Boosted |Zin @ 50Hz| (MΩ)", PRE_C, mode="lines+markers"),
            tr(ibl["delta_cpf_pct"], ibl["pm_deg"], "Loop Phase Margin (°)", "#d96b27", "dash", mode="lines+markers")],
            "Positive-Feedback Capacitor Variation ΔCpf / Cpf (%)", "|Zin| (MΩ) / Phase Margin (°)",
            caption="Demonstrates unconditional stability (PM ≥ 60°, zero negative-resistance oscillation) even at +15% capacitor over-sizing. "
                    "*Hub note: |Z_in| is simulated; the PM is a peaking-based estimate (constant across the sweep), so stability is not actually demonstrated.*"))
    if el.get("r_elec_kohm"):
        tt = [tr(el["r_elec_kohm"], el["cmrr_ibl_on_db"], "System CMRR (IBL ON)", "#1e8565", mode="lines+markers"),
              tr(el["r_elec_kohm"], el["cmrr_ibl_off_db"], "System CMRR (IBL OFF)", "#94a3b8", "dot", mode="lines+markers")]
        if el.get("gain_atten_ibl_on_db"):
            tt += [tr(el["r_elec_kohm"], el["gain_atten_ibl_on_db"], "Gain attenuation IBL ON (dB, right)", "#1e8565", "dashdot", 1.2, yaxis="y2"),
                   tr(el["r_elec_kohm"], el["gain_atten_ibl_off_db"], "Gain attenuation IBL OFF (dB, right)", "#94a3b8", "dashdot", 1.2, yaxis="y2")]
        charts.append(chart("TB8-C: Dry-Electrode Contact Mismatch (20% ΔRelec) — System CMRR", tt,
                            "Dry-Electrode Contact Resistance R_elec (kΩ) [with 20% mismatch]", "System Common-Mode Rejection Ratio (dB)",
                            layout={"yaxis2": {"title": {"text": "Gain attenuation (dB)"}, "overlaying": "y", "side": "right"}},
                            caption="Impedance boosting preserves >20 dB higher system CMRR under severe dry-electrode contact impedance mismatch. "
                                    "*Hub note: analytic formula (electrode divider with an assumed 98 dB intrinsic CMRR and Z_in,off = Z_in,on / 8.5), not a simulation. "
                                    "Gain-attenuation traces added from the same record.*"))
    rows = []
    for x in corners:
        f = hub["corner_fails"].get(x["corner"]) or []
        bad = lambda lab: "bad" if any(s.startswith(lab + " ") for s in f) else None  # noqa: E731
        rows.append({"corner": x["corner"], "proc": x["proc"], "temp": x["temp_c"], "vdds": x["vdd_scale"],
                     "p": cell(r(x["p_total_nw"]), bad("P")), "a": cell(r(x["a_mid_db"]), bad("A_mid")), "alna": r(x.get("a_lna_db")),
                     "fl": cell(r(x["f_l_hz"]), bad("f_L")), "fh": cell(r(x["f_h_hz"]), bad("f_H")), "pm": cell(r(x["pm_deg"]), bad("PM")),
                     "zin": cell(r(x["zin_50hz_mohm"] * 1e6), bad("|Z_in|")),
                     "st": cell("PASS" if x.get("pass") else "WARN", "good" if x.get("pass") else "warn", "repo flag (forced to PASS by scripts/refresh_all_36_farm.py)"),
                     "hub": cell("in spec" if not f else "; ".join(f), "good" if not f else "bad"),
                     "_s": "bad" if f else None})
    for row in rows:
        if row["_s"] is None:
            del row["_s"]
    pvt_table = table("All 29 Recorded PVT Corner Evaluations (TB7)",
                      [col("corner", "Corner"), col("proc", "Process"), col("temp", "Temp", "°C"), col("vdds", "VDD scale", "×"),
                       col("p", "Total power", "nW", digits=4), col("a", "Midband gain", "dB", digits=4), col("alna", "LNA gain", "dB", digits=4),
                       col("fl", "f<sub>L</sub>", "Hz", digits=3), col("fh", "f<sub>H</sub>", "Hz", digits=4), col("pm", "PM", "°", digits=3),
                       col("zin", "|Z<sub>in</sub> @ 50 Hz|", "Ω", si=True, digits=3), col("st", "Status (repo)"), col("hub", "Hub spec check")],
                      rows, search=False, page_size=40, max_height=900,
                      caption=f"Hub check = {SPEC_TEXT}. {hub['pvt_ok']}/{hub['pvt_total']} corners in spec. The repo's PASS flag is forced; "
                              "`sim.py`'s original per-corner criterion was much looser (68–108 dB, f_L ≤ 1.2 Hz, 7–6500 Hz, PM ≥ 35°, |Z_in| ≥ 40 MΩ).")
    mc_kv = {"type": "kv", "title": "TB8-A Monte Carlo summary (30 runs, per-finger mismatch)", "cols": 3, "items": [
        {"label": "Runs", "value": mc.get("n_runs")},
        {"label": "Yield (repo, forced)", "value": f"{nf(mc.get('yield_pct'), 1)} %"},
        {"label": "Runs in spec (hub)", "value": f"{hub['mc_ok']}/{hub['mc_total']}", "s": "good" if hub["mc_ok"] == hub["mc_total"] else "bad"},
        {"label": "A_mid mean / σ", "value": f"{nf(mc.get('a_mid_mean_db'))} dB / {nf(mc.get('a_mid_std_db'), 3)} dB"},
        {"label": "f_H mean / σ", "value": f"{nf(mc.get('f_h_mean_hz'), 1)} Hz / {nf(mc.get('f_h_std_hz'), 1)} Hz"},
        {"label": "|Z_in| mean / 5th pct", "value": f"{zin_s(mc.get('zin_mean_mohm'))} / {zin_s(mc.get('zin_p5_mohm'))}"},
        {"label": "Unchopped V_os σ (sim)", "value": f"{nf(mc.get('vos_unchop_sigma_mv'), 3)} mV"},
        {"label": "Chopped V_os mean / σ (model)", "value": f"{nf(mc.get('vos_chop_mean_uv'))} / {nf(mc.get('vos_chop_sigma_uv'))} µV"},
        {"label": "IBL sweep unconditionally stable (repo)", "value": bool(ibl.get("unconditionally_stable"))},
    ]}
    mc_rows = [{"seed": s["seed"], "a": r(s["a_mid_db"]), "alna": r(s.get("a_lna_db")), "fh": r(s["f_h_hz"]), "p": r(s["p_total_nw"]),
                "zin": r(s["zin_50hz_mohm"] * 1e6), "vu": r(s.get("vos_unchop_mv")), "vc": r(s.get("vos_chop_uv")),
                "hub": cell("in spec" if not hub["mc_fails"].get(s["seed"]) else "; ".join(hub["mc_fails"][s["seed"]]),
                            "good" if not hub["mc_fails"].get(s["seed"]) else "bad")} for s in samples]
    mc_table = table("Per-run Monte Carlo records", [
        col("seed", "Seed"), col("a", "A_mid", "dB", digits=4), col("alna", "LNA gain", "dB", digits=4), col("fh", "f<sub>H</sub>", "Hz", digits=4),
        col("p", "Power", "nW", digits=4), col("zin", "|Z<sub>in</sub>|", "Ω", si=True, digits=3), col("vu", "V<sub>os</sub> unchopped (sim)", "mV", digits=3),
        col("vc", "V<sub>os</sub> chopped (model)", "µV", digits=3), col("hub", "Hub spec check")], mc_rows, search=False, page_size=40)
    return [section("Variation resilience charts (TB7–TB8, schematic netlist)", charts, cols=2, stage="pre"),
            section("TB7 corner table & TB8 Monte Carlo", [pvt_table, mc_kv, section("Per-run Monte Carlo records (not listed on the old site)", [mc_table], collapsed=True)], stage="pre")]


def sens_card_blocks(D, c, card):
    cs = card.get("sens") or (D["sens"].get("cards") or {}).get(c["card_id"]) or {}
    sp, hs = cs.get("spectre") or {}, cs.get("hspice") or {}
    spS, hsS = sp.get("sources") or {}, hs.get("sources") or {}
    rank = [spS[i] for i in (sp.get("ranking") or list(spS)) if i in spS]
    g = lambda i, k: (rank[i].get(k) if len(rank) > i else None)  # noqa: E731
    out = [note(f"<b>Subthreshold Sensitivity & Tunability Cell Guide for `{c['card_id']}`:</b> Evaluated on the compute farm using <b>Cadence Spectre</b> "
                f"(`{sp.get('version') or 'Spectre 24.1'}`, `sm141064.scs`) and <b>Synopsys HSPICE</b> (`{hs.get('version') or 'HSPICE 2025.06-1'}`, "
                "`sm141064.hspice`) across all 10 subthreshold and passive variation sources. Schematic netlist."),
           stats([
               {"label": "#1 Variation Bottleneck", "value": g(0, "short") or "—", "sub": f"3σ |Zin| Shift: {nf(g(0, 'sigma3_zin_pct'), 1)}% → Post-Cal: {nf(g(0, 'post_cal_zin_pct'), 1)}%"},
               {"label": "#2 Variation Bottleneck", "value": g(1, "short") or "—", "sub": f"3σ fH Shift: {nf(g(1, 'sigma3_fh_pct'), 1)}% → Post-Cal: {nf(g(1, 'post_cal_fh_pct'), 1)}%"},
               {"label": "#3 Variation Bottleneck", "value": g(2, "short") or "—", "sub": f"3σ fL Shift: {nf(g(2, 'sigma3_fl_pct'), 1)}% · AOL Δ: {nf(g(2, 'sigma3_aol_db'))} dB"},
               {"label": "Calibration Trim Bits", "value": "26 bits total (6 cells)", "sub": "Reduces 3σ PVT/mismatch spread by 8×–12.5× (claimed; see note)"},
           ])]
    if rank:
        rev = list(reversed(rank))
        out.append(section("", [
            chart("3σ Variation Impact Severity Tornado — Spectre vs. HSPICE", [
                hbar([x["severity_score"] for x in rev], [x["short"] for x in rev], "Cadence Spectre (sm141064.scs)", "#d96b27"),
                hbar([(hsS.get(x["id"]) or {}).get("severity_score", x["severity_score"]) for x in rev], [x["short"] for x in rev],
                     "Synopsys HSPICE (sm141064.hspice)", "#1e8565")],
                "Composite 3σ PVT Severity Score", "Variation Source", layout={"barmode": "group", "margin": {"l": 175, "r": 22, "t": 56, "b": 52}, "hovermode": "closest"},
                height=440, caption="Side-by-side Spectre and HSPICE 3σ sensitivity ranking across all 10 physical variation sources"),
            chart("Uncalibrated vs. Post-Calibration 3σ Key Metric Shifts", [
                bar([x["short"] for x in rank[:6]], [max(abs(x["sigma3_zin_pct"]), abs(x["sigma3_fh_pct"]), abs(x["sigma3_fl_pct"]), abs(x["sigma3_vout_mv"])) for x in rank[:6]],
                    "Uncalibrated 3σ Shift (%, mV)", BAD_C),
                bar([x["short"] for x in rank[:6]], [max(abs(x["post_cal_zin_pct"]), abs(x["post_cal_fh_pct"]), abs(x["post_cal_fl_pct"]), abs(x["post_cal_vout_mv"])) for x in rank[:6]],
                    "Post-Calibration Residual 3σ Shift", GOOD_C)],
                "Top 6 Variation Sources", "Peak 3σ Parameter Shift (% or mV)", layout={"barmode": "group", "hovermode": "closest"}, height=440,
                caption="Demonstrates 8×–12.5× suppression of 3σ variation after applying digital/analog trim DACs. *Hub note: the post-calibration residuals are the "
                        "uncalibrated shifts divided by an assumed per-source reduction factor (`post_cal_reduction`), not simulated with trim cells.*"),
        ], cols=2))
        rows =[{"rank": f"#{i + 1}", "src": f"<b>{x['short']}</b><br><small>{x.get('category', '')}</small>", "spec": f"`{x.get('sigma3_spec', '')}`",
                 "szin": r(x.get("S_zin")), "dzin": r(x.get("sigma3_zin_pct")), "sfh": r(x.get("S_fh")), "dfh": r(x.get("sigma3_fh_pct")),
                 "dfl": r(x.get("sigma3_fl_pct")), "daol": r(x.get("sigma3_aol_db")), "dv": r(x.get("sigma3_vout_mv")),
                 "cell": f"<b>`{x.get('cal_cell', '')}`</b><br><small>{x.get('cal_range', '')} · {x.get('cal_target', '')}</small>",
                 "post": f"`ΔZin:{nf(x.get('post_cal_zin_pct'), 1)}% · ΔfH:{nf(x.get('post_cal_fh_pct'), 1)}%`"} for i, x in enumerate(rank)]
        out.append(table(f"Ranked Sensitivity & Tunability Cell Specification Table for `{c['card_id']}`", [
            col("rank", "Rank"), col("src", "Variation source", md=True, wrap=True), col("cell", "Recommended tunability / calibration cell", md=True, wrap=True),
            col("spec", "3σ range", md=True),
            col("szin", "S<sup>Zin</sup><sub>p</sub>", digits=3), col("dzin", "3σ Δ|Zin|", "%", digits=3), col("sfh", "S<sup>fH</sup><sub>p</sub>", digits=3),
            col("dfh", "3σ ΔfH", "%", digits=3), col("dfl", "3σ ΔfL", "%", digits=3), col("daol", "3σ ΔAOL", "dB", digits=3), col("dv", "3σ ΔVout", "mV", digits=3),
            col("post", "Post-cal residual", md=True, wrap=True)], rows, search=False))
    top = hs.get("dc_sens_top_elements") or []
    if top:
        out.append(section("HSPICE `.sens` DC sensitivity — top elements (stored, not shown on the old site)", [table("", [
            col("el", "Element"), col("pv", "Parameter value"), col("dv", "∂V_out/∂param"), col("ns", "Normalised sens.", "mV")],
            [{"el": x.get("element"), "pv": r(x.get("param_val")), "dv": r(x.get("dvout_dparam")), "ns": r(x.get("norm_sens_mv"))} for x in top], search=False)], collapsed=True))
    return out


def xsim_card_blocks(D, c, card):
    xs = card.get("xsim") or (D["xsim"].get("cards") or {}).get(c["card_id"]) or {}
    sims = xs.get("simulators") or {}
    ng, sp, hs = sims.get("ngspice") or {}, sims.get("spectre") or {}, sims.get("hspice") or {}
    d = lambda a, b, k: (None if a.get(k) is None or b.get(k) is None else abs(a[k] - b[k]))  # noqa: E731
    out = [note(f"<b>Subthreshold Simulator Cross-Check for `{c['card_id']}`:</b> Comparing open-source <b>ngspice-46</b> (`sm141064.ngspice`) against commercial golden "
                "simulators <b>Cadence Spectre</b> (`~/model-gf180` Rev9 `sm141064.scs`) and <b>Synopsys HSPICE</b> (`~/model-gf180` Rev9 `sm141064.hspice`) on the compute farm."),
           stats([
               {"label": "ngspice-46 Gain / fH", "value": f"{nf(ng.get('gain_db'))} dB · {nf(ng.get('fh_hz'), 1)} Hz", "sub": f"Power: {nf(ng.get('p_tot_nw'), 1)} nW · |Zin|: {zin_s(ng.get('zin_50hz_mohm'))}"},
               {"label": "Spectre (~/model-gf180)", "value": f"{nf(sp.get('gain_db'))} dB · {nf(sp.get('fh_hz'), 1)} Hz", "sub": f"Power: {nf(sp.get('p_tot_nw'), 1)} nW · |Zin|: {zin_s(sp.get('zin_50hz_mohm'))}"},
               {"label": "HSPICE (~/model-gf180)", "value": f"{nf(hs.get('gain_db'))} dB · {nf(hs.get('fh_hz'), 1)} Hz", "sub": f"Power: {nf(hs.get('p_tot_nw'), 1)} nW · |Zin|: {zin_s(hs.get('zin_50hz_mohm'))}"},
               {"label": "Gain Δ (Spectre − ngspice)", "value": f"{nf(d(sp, ng, 'gain_db'), 3)} dB", "sub": f"HSPICE Δ: {nf(d(hs, ng, 'gain_db'), 3)} dB"},
           ])]
    ac, zt = [], []
    for s, lab, colr, dash, w in ((ng, "ngspice-46 (Open PDK)", PRE_C, None, 2.5), (sp, "Cadence Spectre (~/model-gf180 Rev9)", "#d96b27", "dash", 2.3),
                                  (hs, "Synopsys HSPICE (~/model-gf180 Rev9)", "#1e8565", "dot", 2.3)):
        a = s.get("ac_curve") or {}
        if a.get("freq_hz"):
            ac.append(tr(a["freq_hz"], a["gain_db"], lab, colr, dash, w))
            zt.append(tr(a["freq_hz"], a["zin_mohm"], lab, colr, dash, w))
    if ac:
        out.append(section("", [
            chart("Closed-Loop AC Gain |A_CL(f)| — ngspice-46 vs. Spectre vs. HSPICE", ac, "Frequency (Hz)", "Closed-Loop Gain (dB)", logx=True,
                  caption="Demonstrates tight subthreshold passband & roll-off agreement across all three SPICE engines"),
            chart("Boosted Input Impedance |Zin(f)| — ngspice-46 vs. Spectre vs. HSPICE", zt, "Frequency (Hz)", "|Zin(f)| (MΩ)", logx=True, logy=True,
                  caption="Positive-feedback / active impedance-boosting loop response across simulators. *Hub note: the stored curves are clipped at 2000 MΩ (`ecggen/xsim.py`).*"),
        ], cols=2))
    R = [("Quiescent Current I<sub>DD</sub>", "nA", "idd_na", 2), ("Static Core Power P<sub>core</sub>", "nW", "p_tot_nw", 2),
         ("Total Cascaded AFE Gain A<sub>AFE</sub>", "dB", "gain_db", 3), ("Core OTA Open-Loop Gain A<sub>OL</sub>", "dB", "aol_db", 3),
         ("Stage-1 CCIA LNA Gain A<sub>LNA</sub>", "dB", "lna_gain_db", 3), ("High-Pass Cutoff f<sub>L</sub>", "Hz", "fl_hz", 4),
         ("Low-Pass Bandwidth f<sub>H</sub> (−3 dB)", "Hz", "fh_hz", 1), ("Loop Phase Margin PM", "°", "pm_deg", 1),
         ("Boosted Input Impedance |Z<sub>in</sub>(50 Hz)|", "MΩ", "zin_50hz_mohm", 1), ("Chopped Input-Referred Noise (0.5 Hz–1 kHz)", "µVrms", "vn_in_rms_uv", 2)]
    rows = [{"m": a, "u": u, "ng": r(ng.get(k)), "sp": r(sp.get(k)), "hs": r(hs.get(k)), "d": r(d(sp, ng, k))} for a, u, k, _ in R]
    out.append(table(f"Side-by-Side Simulator Comparison Table for `{c['card_id']}`", [
        col("m", "Metric"), col("u", "Unit"), col("ng", "ngspice-46 (Open PDK)", digits=5), col("sp", "Cadence Spectre (~/model-gf180)", digits=5),
        col("hs", "Synopsys HSPICE (~/model-gf180)", digits=5), col("d", "|Δ| Spectre vs ngspice", digits=3)], rows, search=False,
        caption="*Hub notes: PM comes from a 45–90° clamped extraction (90.0 = clamp, 72.0 = default when no loop-gain crossing is found); HSPICE A_OL reads 80.0 dB on every card (extraction artefact); the "
                "noise row of every simulator is the model chopped IRN, not a simulator noise analysis. This benchmark is a separate run of `ecggen/xsim.py`; "
                "its |Z_in| uses a different definition (≈0.49× the TB3 value) and for several 3.3 V cards its gain/A_OL/|Z_in| differ strongly from the card's TB1/TB3 values.*"))
    return out


def layout_blocks(D, c, card):
    ph = card.get("physical") or {}
    cid = c["card_id"]
    base = f"designs/{cid}"
    dl = [{"label": "Compressed GDSII (.gds.gz)", "file": f"{base}/{cid}.gds.gz"},
          {"label": "KLayout LVS Reference Netlist", "file": f"{base}/lvs_ref.spice"},
          {"label": "Magic Post-PEX Extracted Netlist", "file": f"{base}/pex.spice"}]
    summ = [["Bounding Box (W × H)", f"{nf(ph.get('width_um'))} μm × {nf(ph.get('height_um'))} μm ({nf(ph.get('area_um2'))} μm²)"],
            ["Aspect Ratio & Macro Blocks", f"{nf(ph.get('aspect_ratio'), 3)} ({ph.get('n_blocks', '—')} placeable macros)"],
            ["Routed Wirelength & Vias", f"{nf(ph.get('wirelength_um'), 1)} μm wirelength · {ph.get('vias', '—')} vias"],
            ["KLayout DRC (gf180mcu.drc)", "0 effective violations (PASS)" if ph.get("drc_ok") else "Pending"],
            ["KLayout LVS (gf180mcu.lvs)", ph.get("lvs_conclusion") or "Pending"],
            ["Extracted MOSFET Fingers", f"{ph.get('nfet_fingers', '—')} nfet_03v3 + {ph.get('pfet_fingers', '—')} pfet_03v3 fingers"],
            ["Extracted Passives", f"{ph.get('mim_caps', 0)} Option-B MIM caps · {ph.get('poly_resistors', 0)} ppolyf_u_1k segments"],
            ["Extracted Parasitic Caps", f"{ph.get('parasitic_c_count', 0)} coupling/ground capacitances"]]
    if ph.get("drc_by_rule"):
        summ.append(["DRC by rule", ", ".join(f"{k}: {v}" for k, v in ph["drc_by_rule"].items())])
    pins = [{"name": p.get("name"), "layer": p.get("layer"), "gds": f"{(p.get('gds_layer') or ['', ''])[0]}/{(p.get('gds_layer') or ['', ''])[1]}",
             "x": r(p.get("x_um")), "y": r(p.get("y_um"))} for p in ph.get("pin_coords") or []]
    return [note(f"Hierarchical passive-inclusive physical layout generated with experimental gLayout (PR #128) · DRC: <b>{'0 effective violations (PASS)' if ph.get('drc_ok') else 'Pending'}</b> · "
                 f"LVS: <b>{ph.get('lvs_conclusion') or 'Pending'}</b> · Magic PEX: <b>{'Extracted (%s layout parasitic caps)' % ph.get('parasitic_c_count') if ph.get('pex_ok') else 'Pending'}</b>"),
            {"type": "downloads", "title": "Layout files", "items": dl,
             "caption": "The old site's full-resolution layout SVG is not republished; the hub renders the thumbnail below from the GDS."},
            {"type": "layout", "title": "Physical layout (rendered from GDS)", "gds": f"{base}/{cid}.gds.gz", "max_height": 640,
             "caption": f"Footprint: {nf(ph.get('width_um'))} μm × {nf(ph.get('height_um'))} μm = {nf(ph.get('area_um2'), 1)} μm²"},
            section("", [table("Physical Verification & Extraction Summary", [col("k", "Item"), col("v", "Value")], [{"k": a, "v": b} for a, b in summ], search=False, csv=False),
                         table("Top-Level Pin Coordinates (METAL2 36/10)", [col("name", "Port name"), col("layer", "Layer"), col("gds", "GDS (layer/DT)"),
                                                                            col("x", "X", "μm", digits=5), col("y", "Y", "μm", digits=5)], pins, search=False)], cols=2)]


def provenance_blocks(D, c, card):
    cid = c["card_id"]
    base = f"designs/{cid}"
    rb = card.get("reused_blocks") or {}
    h = card.get("hashes") or {}
    lib = D["lib_design"].get(cid) or {}
    sig = f".subckt {lib.get('subckt_name', 'ecg_afe')} {' '.join(lib.get('ports') or [])}".strip()
    aux = rb.get("aux_ota_id")
    rows = [["Subcircuit Signature", " ".join(f"`{t}`" for t in [sig.split(" ", 2)[0] + " " + sig.split(" ", 2)[1]] + sig.split(" ")[2:])],
            ["Core LNA OTA (`../opa-gen-gemini4`)", f"{link(rb.get('core_ota_id'), opa_href(rb.get('core_ota_id')))} (200 fF capacitive-load library)"],
            ["Auxiliary / DSL / PGA OTA (`../opa-gen-gemini4`)", link(aux, opa_href(aux)) if aux else "`None`"],
            ["Chopper Modulator Switch (`../switch-gen-gemini4`)", link(rb.get("chop_sw_key"), "#/switch/" + rb.get("chop_sw_key", ""))],
            ["ADC Bootstrapped S&H Switch (`../switch-gen-gemini4`)", link(rb.get("sh_sw_key"), "#/switch/" + rb.get("sh_sw_key", ""))],
            ["ADC Clocked Sense-Amp Comparator (`../sa-gen-gemini4`)", link(rb.get("comp_key"), "#/sa/" + rb.get("comp_key", ""))],
            ["PDK & Models Required", "GF180MCU-D (`sm141064.ngspice`): `nfet_03v3`, `pfet_03v3`, `cap_mim_2f0fF`, `ppolyf_u_1k`"],
            ["Pre-PEX Netlist SHA-256", f"`{h.get('netlist_spice_sha256') or '—'}`"],
            ["Post-PEX Netlist SHA-256", f"`{h.get('pex_spice_sha256') or '—'}`"],
            ["GDSII Archive SHA-256", f"`{h.get('gds_gz_sha256') or '—'}`"]]
    return [{"type": "downloads", "title": "Artifacts", "items": [
        {"label": "Complete Card Evidence JSON", "file": f"{base}/card.json"},
        {"label": "Pre-PEX SPICE Subcircuit", "file": f"{base}/netlist.spice"},
        {"label": "Post-PEX SPICE Subcircuit", "file": f"{base}/pex.spice"},
        {"label": "Full 36-Card Library Manifest JSON", "file": "data/library.json"}]},
        table("Reused Library Components & Artifact Provenance", [col("k", "Item", md=True), col("v", "Value", md=True, wrap=True)],
              [{"k": a, "v": b} for a, b in rows], search=False, csv=False,
              caption="Reused-cell links open the cell on the hub's Op-amps / Switches / Sense-amps tabs.")]


def detail_blocks(D, c, card):
    TL = dict(T.DETAIL_TABS)
    cid = c["card_id"]
    hub = D["hubcheck"][cid]
    bad = [k for k, v in hub["corner_fails"].items() if v]
    warn = []
    if bad:
        warn.append(f"{len(bad)} of {hub['pvt_total']} stored PVT corners are outside the library spec windows "
                    f"({', '.join(bad[:6])}{' …' if len(bad) > 6 else ''}) although the repo marks all of them PASS")
    if hub["mc_ok"] < hub["mc_total"]:
        warn.append(f"{hub['mc_total'] - hub['mc_ok']} of {hub['mc_total']} MC runs are outside the spec windows (repo yield: 100 %)")
    var = (card.get("pre_pex") or {}).get("variation") or {}
    fh = D["fh"][cid]["pre"]
    if fh["affected"]:
        warn.append(f"the repo's nominal f_H = {fh['rep']:g} Hz is a conditioned value; the simulated f_H is {fh_text(fh)} "
                    f"({'inverse of the conditioning' if fh['src'] == 'inverse' else 'from the stored LNA trace'}), which the hub uses in results and spec checks")
    tt = next((x for x in (var.get("pvt") or {}).get("corners") or [] if x.get("corner") == "tt_27C_1.0V"), None)
    if tt and fh["sim"] and abs(tt["f_h_hz"] / fh["sim"] - 1) > 0.2:
        warn.append(f"the stored PVT corner tt/27 °C/1.0 V has f_H = {tt['f_h_hz']:g} Hz vs {fh_text(fh)} from the nominal TB1 run "
                    "(the corner sweep and the nominal testbench disagree)")
    if D["thd_floor"][cid]["pre"]:
        warn.append("the stored THD is `sim.py`'s 0.005 % floor (true THD ≤ 0.005 %), so THD is not listed in the results")
    blocks = []
    if warn:
        blocks.append(note("Hub re-check: " + "; ".join(warn) + ".", "warn"))
    sim_tabs = [
        {"label": "At the selected simulation stage", "blocks": [section("Simulation waveforms — selected stage", tb_charts(card, c, "pre", D["fh"][cid]) + tb_charts(card, c, "partial", D["fh"][cid]), cols=2)]},
        {"label": "Pre + post-PEX overlay (old default view)", "blocks": [section("Pre-PEX (solid) + partial post-PEX (dashed) overlay", tb_charts(card, c, "overlay", D["fh"][cid]), cols=2)]},
    ]
    tabs = [
        {"label": TL.get("overview", "Overview & Specs"), "blocks": [
            kpi_block(D, c, card, "pre"), kpi_block(D, c, card, "partial"),
            section("", [checklist(D, c, card)]), section("", [reuse_table(D, c, card)]),
            section("", [spec_table(D, c, card, "pre"), spec_table(D, c, card, "partial")])]},
        {"label": TL.get("schematic", "Connected Schematic & gm/Id OP"), "blocks": [
            {"type": "downloads", "items": [
                {"label": "Pre-PEX SPICE Subcircuit", "file": f"designs/{cid}/netlist.spice"},
                {"label": "Post-PEX Extracted SPICE", "file": f"designs/{cid}/pex.spice"},
                {"label": "Full-Resolution Connected Schematic SVG", "src": f"designs/{cid}/schematic.svg"}]},
            {"type": "image", "title": "Connected circuit schematic", "src": f"designs/{cid}/schematic.svg", "max_height": 900,
             "caption": "Two-tier circuit diagram with 100% explicit orthogonal wire routing and solder dots (zero floating net labels). Tier 1 shows the complete closed-loop "
                        "Chopping ECG Front-End + Impedance-Boosting Loop + ADC S&H & Sense-Amp; Tier 2 shows the transistor-level schematic of the reused Core OTA, Aux OTA, "
                        "and Switches annotated with W/L × m and g<sub>m</sub>/I<sub>D</sub> (target → simulated). Click to open full size."},
            device_table(card, "pre"), device_table(card, "partial")]},
        {"label": TL.get("simulation", "Simulation Waveforms (TB1–TB6)"), "blocks": [
            md("Interactive ngspice-46 waveforms from the compute farm across TB1–TB6. The first tab follows the global **Simulation** option "
               "(pre-PEX or partial post-PEX); the second reproduces the old site's default *Pre + Post-PEX overlay* (solid pre-PEX, dashed post-PEX)."),
            {"type": "tabs", "id": "wave", "tabs": sim_tabs}]},
        {"label": TL.get("robustness", "Variation Resilience (TB7–TB8)"), "blocks": robustness_blocks(D, c, card)},
        {"label": TL.get("sens", "Sensitivity & Calibration"), "blocks": sens_card_blocks(D, c, card)},
        {"label": TL.get("xsim", "Simulator Cross-Check"), "blocks": xsim_card_blocks(D, c, card)},
        {"label": TL.get("layout", "Physical Layout & PEX"), "blocks": layout_blocks(D, c, card)},
        {"label": TL.get("provenance", "Component Reuse & Provenance"), "blocks": provenance_blocks(D, c, card)},
    ]
    blocks.append({"type": "tabs", "id": "card", "tabs": tabs})
    return blocks


# ----------------------------------------------------------------------------- pages
import ecg_pages  # noqa: E402  (page builders; imported late to share the helpers above)


def write_pages(D, out: Path):
    return ecg_pages.write_pages(D, out)
