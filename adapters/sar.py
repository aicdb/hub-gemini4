#!/usr/bin/env python3
"""Bootstrap hub adapter for sar-gen-gemini4 (schema aicdb-hub/2).

usage: sar.py DOCS_DIR OUT_DIR

Reads only DOCS_DIR (the repo's published docs/) and writes OUT_DIR/component.json plus the
detail documents, pages and data files it references (as "hub/<path>").  Stdlib only.
Everything the retired GitHub Pages site showed is mapped here; see sar.inventory.md.

Stage mapping (semantics checked against sargen/ in the repo):
  * The only transistor-level SPICE result per card is `spice.fft_post` / `waveform_post`
    (view "post"): CDAC = Magic-extracted netlist, S/H switch, comparator and VCM OPA = the
    sibling repos' PEX netlists, SAR controller = standard-cell schematic, top-level routing
    ideal (sargen/sar_netlist.py, uhs.py, lu2g.py, ulp.py).  That is `partial`.
  * `fft_pre` = post + fixed offsets (+0.12..0.16 dB SNDR, x0.96..0.97 power) and `fft_full` =
    post - 0.18 dB SNDR, x1.018 power (sargen/arch.py, site.py `_derive_full_pex_fft`).  Never
    simulated -> shown only as labelled model estimates in the detail documents, not `results`.
  * Sleep-gated ULP cards: the top-level energy / leakage (28 or 110 pJ, 5.2 or 16 nW) are
    placeholders (sargen/ulp.py reads uwf["e_dyn_pj"], but the SPICE result stores it under
    waveform_post.tot).  Power and FoMs are recomputed from the simulated energy with the repo's
    own formula (380 ns active window, duty-cycled sleep leakage); both are shown, labelled.
  * Post-PEX CDAC variance: 48 cards (split-monotonic + ULP) carry the variance record of the
    *_uhs macro instead of their own CDAC; the hub uses each card's own macro (index.json
    postpex_variance_macros + the detailed record of a card that simulated that macro).
"""
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DOCS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
INDEX = json.loads((DOCS / "data" / "index.json").read_text())
SWEEP = json.loads((DOCS / "data" / "sweep.json").read_text())
COMPCHAR = json.loads((DOCS / "data" / "compchar.json").read_text()) if (DOCS / "data" / "compchar.json").is_file() else {}
CARDS = {c["card_id"]: c for c in INDEX["cards"]}
DATA = {cid: json.loads((DOCS / "designs" / cid / "data.json").read_text()) for cid in sorted(CARDS)}

# ----------------------------------------------------------------------------- helpers
GREEN, RED, BLUE, AMBER, PINK, PURPLE, GRAY, CYAN = "#16a34a", "#dc2626", "#2563eb", "#d97706", "#db2777", "#7c3aed", "#64748b", "#0891b2"
NB_COLOR = {8: CYAN, 10: GREEN, 12: AMBER}


def R(v, n=5):
    """round to n significant digits (numbers only)"""
    if v is None or isinstance(v, bool) or isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        if v == 0:
            return 0
        x = float(f"{v:.{n}g}")
        return int(x) if x.is_integer() and abs(x) < 1e15 else x
    return v


def RL(a, n=5, scale=1.0):
    return [R(x * scale if isinstance(x, (int, float)) and not isinstance(x, bool) else x, n) for x in (a or [])]


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def mul(x, f):
    return None if num(x) is None else x * f


PFX = [(1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"),
       (1e-12, "p"), (1e-15, "f"), (1e-18, "a")]


def si(v, unit, d=4):
    if num(v) is None:
        return "—"
    a = abs(v)
    if a == 0:
        return f"0 {unit}"
    f, p = next(((f, p) for f, p in PFX if a >= f * 0.9995), PFX[-1])
    return f"{float(f'{v / f:.{d}g}'):g} {p}{unit}"


def fx(v, unit="", d=4):
    if num(v) is None:
        return "—"
    s = f"{float(f'{v:.{d}g}'):g}"
    return f"{s} {unit}".strip() if unit not in ("%", "°C") else f"{s}{unit}"


def href(comp, key):
    """hub link to a sibling component design (underscores %-encoded: the hub's markdown would
    otherwise read `__x__` as bold inside the URL)"""
    hid = key.replace("/", "-") if comp == "opa" else key
    return f"#/{comp}/{hid}"


def vdd_of_key(key):
    m = re.search(r"(1v8|3v3|1p8v|3p3v)", key or "")
    return None if not m else (1.8 if m.group(1).startswith("1") else 3.3)


def mdlink(comp, key):
    return f"[`{key}`]({href(comp, key)})"


def col(key, label, unit=None, si_=None, digits=None, type_=None, md=None, title=None, group=None, better=None, align=None, wrap=None):
    c = {"key": key, "label": label}
    for k, v in (("unit", unit), ("si", si_), ("digits", digits), ("type", type_), ("md", md), ("title", title),
                 ("group", group), ("better", better), ("align", align), ("wrap", wrap)):
        if v is not None:
            c[k] = v
    return c


def table(title, columns, rows, **kw):
    b = {"type": "table", "title": title, "columns": columns, "rows": rows}
    b.update({k: v for k, v in kw.items() if v is not None})
    return b


def kv(title, items, cols=2, caption=None):
    b = {"type": "kv", "title": title, "cols": cols, "items": items}
    if caption:
        b["caption"] = caption
    return b


def note(text, tone="info", title=None):
    b = {"type": "note", "tone": tone, "text": text}
    if title:
        b["title"] = title
    return b


def md(text, title=None):
    b = {"type": "markdown", "text": text}
    if title:
        b["title"] = title
    return b


def section(title, blocks, cols=None, intro=None, collapsed=None):
    b = {"type": "section", "blocks": [x for x in blocks if x]}
    if title:
        b["title"] = title
    if cols:
        b["cols"] = cols
    if intro:
        b["intro"] = intro
    if collapsed:
        b["collapsed"] = True
    return b


def line(name, x, y, color=None, dash=None, width=2, mode="lines", **kw):
    t = {"type": "scatter", "mode": mode, "name": str(name).replace("`", ""), "x": x, "y": y, "line": {"width": width}}
    if color:
        t["line"]["color"] = color
        if "markers" in mode:
            t["marker"] = {"color": color, "size": 6}
    if dash:
        t["line"]["dash"] = dash
    t.update(kw)
    return t


def chart(title, data, xt=None, yt=None, layout=None, height=None, caption=None, **kw):
    lay = {"xaxis": {"title": {"text": xt or ""}}, "yaxis": {"title": {"text": yt or ""}}}
    for k, v in (layout or {}).items():
        if isinstance(v, dict) and isinstance(lay.get(k), dict):
            lay[k] = {**lay[k], **v}
        else:
            lay[k] = v
    b = {"type": "chart", "title": title, "data": data, "layout": lay}
    if height:
        b["height"] = height
    if caption:
        b["caption"] = caption
    b.update(kw)
    return b


def staged(b, st="partial"):
    """mark a block as a result of one simulation stage (follows the global stage option)"""
    if b:
        b["stage"] = st
    return b


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


# ----------------------------------------------------------------------------- vocabulary
ARCHS = [
    ("smono_ulp1k", "ULP 1 kS/s (sleep-gated)"),
    ("smono_ulp100k", "ULP 100 kS/s (sleep-gated)"),
    ("smono_ulp1m", "LP 1 MS/s (sleep-gated)"),
    ("mono_red", "Monotonic"),
    ("smono_red", "Split-monotonic"),
    ("vcm_opa_red", "VCM-OPA"),
    ("mvote_red", "3× majority-vote LSB"),
    ("smono_uhs100m", ">100 MS/s smaller-cap UHS"),
    ("lu_domino_2g", "Loop-unrolled domino (2 GS/s TI)"),
]
ARCH_LABEL = dict(ARCHS)
ARCH_ORDER = {a: i for i, (a, _) in enumerate(ARCHS)}
TIERS = [
    ("1ksps", "1 kS/s ULP"),
    ("100ksps", "100 kS/s ULP"),
    ("1msps", "1 MS/s ULP"),
    ("hs", "3–20 MS/s high-speed"),
    ("uhs100m", ">100 MS/s smaller-cap UHS"),
    ("lu2g", "250–400 MS/s loop-unrolled (2 GS/s TI)"),
]
TIER_LABEL = dict(TIERS)
CAPS = [("mom", "Custom MOM (M1–M4)"), ("mim", "Option-B MIM (M4/M5)")]
MODES = [("ulp", "EOC sleep-gated ULP"), ("hs", "Continuous high-speed"), ("uhs", ">100 MS/s smaller-cap UHS"), ("lu", "Loop-unrolled domino (2 GS/s TI)")]


def MODE_OF(c):
    return "ulp" if c.get("sleep_gated") else {"uhs100m": "uhs", "lu2g": "lu"}.get(c["fs_tier"], "hs")
CAP_LABEL = dict(CAPS)
SWEEP_ARCH = {"mono_red": "Monotonic (redundant)", "smono_red": "Split-monotonic (redundant)",
              "vcm_opa_red": "VCM-OPA (redundant)", "mvote_red": "3× majority-vote LSB (redundant)",
              "mono_bin": "Monotonic (binary, non-redundant)"}
SUB_LABEL = {
    "sw": "Bootstrapped S/H switches (Xsw_p, Xsw_n)",
    "opa": "VCM reference buffer op-amp (Xopa + 20 pF)",
    "cdac": "Redundant CDAC array & bottom-plate drivers",
    "cmp": "Clocked sense-amplifier comparator (Xcmp)",
    "ctrl": "Asynchronous SAR controller & sequencer (Xctrl)",
}

METRICS = [
    # key, label, unit, si, better, digits
    ("enob", "ENOB", "bit", False, "high", 4,
     "Effective number of bits from the coherent 16/32-point SPICE FFT incl. the generator's analytical thermal-noise term; "
     "short FFTs can give ENOB at or above N (accuracy about ±0.3 b). Not reported for loop-unrolled cards (synthesized codes)."),
    ("enob_loss", "ENOB shortfall", "bit", False, "low", 3,
     "N − ENOB (nominal resolution minus SPICE ENOB). The generator's own feasibility criterion is ≤ 1.8 b; negative values are short-FFT artefacts."),
    ("sndr", "SNDR", "dB", False, "high", 4, "SPICE FFT SNDR incl. the analytical thermal-noise term."),
    ("sfdr", "SFDR", "dB", False, "high", 4, "Spurious-free dynamic range of the SPICE FFT."),
    ("thd", "THD", "dB", False, "low", 4, "Total harmonic distortion (HD2–HD5) of the SPICE FFT."),
    ("enob_raw", "ENOB (raw codes)", "bit", False, "high", 4,
     "Loop-unrolled cards only: ENOB of the raw, uncalibrated SPICE output codes (FFT computed by the hub, no added noise). "
     "The published calibrated codes of these cards are synthesized by the generator."),
    ("fs", "Sample rate", "S/s", True, "high", 4, "Single-channel conversion rate."),
    ("power", "Total power", "W", True, "low", 3,
     "SPICE supply power; sleep-gated ULP cards: SPICE energy/conversion × f_s + duty-cycled SPICE sleep leakage (repo formula)."),
    ("e_conv", "Energy / conv.", "J", True, "low", 3, "Total power / f_s."),
    ("fom_w", "Walden FoM", "fJ/step", False, "low", 4, "P / (f_s · 2^ENOB)."),
    ("fom_s", "Schreier FoM", "dB", False, "high", 4, "SNDR + 10·log10(f_s / 2P)."),
    ("p_leak", "Sleep leakage", "W", True, "low", 3,
     "Sleep-gated ULP cards only: SPICE supply leakage in the sleep window (before duty cycling). Not reported for "
     "continuous-mode cards, whose published 'standby leakage' is op-amp bias + a constant."),
    ("dnl", "DNL max", "LSB", False, "low", 3, "Static DNL from the Magic-extracted CDAC step weights."),
    ("inl", "INL max", "LSB", False, "low", 3, "Static INL from the Magic-extracted CDAC step weights."),
    ("enob_var", "Redundant ENOB (var.)", "bit", False, "high", 4,
     "Worst ENOB of the redundant CDAC over the 5 injected-variance corners (SPICE on the extracted CDAC macro of this card)."),
    ("enob_var_bin", "Binary ENOB (var.)", "bit", False, "high", 4,
     "Worst ENOB of a binary CDAC on the same extracted array over the same 5 corners — the comparison case."),
    ("area", "Layout area", "µm²", False, "low", 4, "Full-chip layout area (1:1 square)."),
]

PARTIAL_NOTE = ("Transistor-level SPICE with the Magic-extracted CDAC and the sibling repos' PEX netlists of "
                "the S/H switch, comparator and VCM OPA; SAR logic as schematic, top-level routing not extracted")

# ----------------------------------------------------------------------------- shared data maps
MACROS = {m["cdac_key"]: m for m in INDEX.get("postpex_variance_macros", [])}
PV_BY_MACRO = {}           # cdac key -> (card that carries its detailed record, record)
for cid in sorted(DATA):
    pv = (DATA[cid].get("resilience") or {}).get("postpex_variance") or {}
    if pv.get("ckey") and pv["ckey"] not in PV_BY_MACRO:
        PV_BY_MACRO[pv["ckey"]] = (cid, pv)


def group_of(fn):
    g = defaultdict(list)
    for cid in sorted(DATA):
        k = fn(DATA[cid])
        if k is not None:
            g[k].append(cid)
    return {cid: [x for x in v if x != cid] for v in g.values() for cid in v}


FFT_TWINS = group_of(lambda d: json.dumps((d["spice"].get("fft_post") or {}).get("codes")) if (d["spice"].get("fft_post") or {}).get("codes") else None)
WF_TWINS = group_of(lambda d: json.dumps((d["spice"].get("waveform_post") or {}).get("traces"), sort_keys=True))


def anchor_of(c):
    return f"sar_{c['nbits']}b_{c['vdd_tag']}_mono_mom"


# ----------------------------------------------------------------------------- per-design results
def ulp_power(c, d):
    """Repo formula (sargen/ulp.py) applied to the SPICE-measured energy & sleep leakage."""
    wf = d["spice"].get("waveform_post") or {}
    tot = wf.get("tot") or {}
    fs_hz = d["spice"]["fft_post"]["fs_msps"] * 1e6
    e_dyn, leak_nw = num(tot.get("e_dyn_pj")), num(tot.get("p_leak_nw"))
    if e_dyn is None or leak_nw is None:
        return None
    duty = max(0.05, 1.0 - min(0.95, 380e-9 * fs_hz))
    p_dyn = e_dyn * 1e-12 * fs_hz
    p_lk = leak_nw * 1e-9 * duty
    return {"e_dyn": e_dyn * 1e-12, "leak": leak_nw * 1e-9, "i_leak": mul(tot.get("i_leak_na"), 1e-9), "duty": duty,
            "p_dyn": p_dyn, "p_leak_eff": p_lk, "power": p_dyn + p_lk}


def own_pv(c, d):
    key = c["cdac_key"]
    rec = PV_BY_MACRO.get(key)
    return (rec[0], rec[1]) if rec else (c["card_id"], (d.get("resilience") or {}).get("postpex_variance") or {})


def fft_ok_of(d):
    fp = d["spice"].get("fft_post") or {}
    return bool(fp.get("codes")) and "error" not in fp


def synth_of(d):
    """loop-unrolled cards: published codes are the generator's calibration fit to an ideal sine plus a
    hard-coded HD2/HD3 term (sargen/lu2g.py _calibrate_lu2g_radix_and_cm_lut), not SPICE output"""
    return d.get("fs_tier") == "lu2g"


def raw_fft(codes, n, m):
    """noise-free coherent FFT metrics of raw codes (same bins as sargen/ulp.py, no added thermal noise)"""
    if not codes or len(codes) != n:
        return None
    mu = sum(codes) / n
    y = [x - mu for x in codes]
    p = []
    for b in range(n // 2 + 1):
        re = sum(y[k] * math.cos(2 * math.pi * b * k / n) for k in range(n))
        im = -sum(y[k] * math.sin(2 * math.pi * b * k / n) for k in range(n))
        p.append((re * re + im * im) / (n / 2.0) ** 2)
    p[0] = 0.0
    ps = p[m]
    nd = [x for i, x in enumerate(p) if i != m]
    pnd = max(sum(nd), 1e-18)
    harm = 0.0
    for h in range(2, 6):
        hb = (h * m) % n
        if hb > n // 2:
            hb = n - hb
        if hb != m and 0 < hb <= n // 2:
            harm += p[hb]
    sndr = 10 * math.log10(max(ps, 1e-18) / pnd)
    spec = [-110.0 if i == 0 else (0.0 if i == m else 10 * math.log10(max(x, 1e-16) / max(ps, 1e-18))) for i, x in enumerate(p)]
    return {"sndr_db": R(sndr, 4), "enob": R((sndr - 1.76) / 6.02, 4), "sfdr_db": R(10 * math.log10(max(ps, 1e-18) / max(max(nd), 1e-18)), 4),
            "thd_db": R(10 * math.log10(max(harm, 1e-18) / max(ps, 1e-18)), 4), "spec_dbc": [R(x, 4) for x in spec]}


def partial_stage(c, d):
    fp = d["spice"]["fft_post"]
    fs_hz = fp["fs_msps"] * 1e6
    ok = fft_ok_of(d) and not synth_of(d)
    sndr = fp.get("sndr_db") if ok else None
    enob = fp.get("enob") if ok else None
    p_leak = None
    if c.get("sleep_gated"):
        u = ulp_power(c, d)
        power = u["power"] if u else None
        p_leak = u["leak"] if u else None
        e_conv = power / fs_hz if power else None
        fom_w = fom_s = None
        if power and enob is not None:
            fom_w = power / (fs_hz * 2.0 ** enob) * 1e15
            fom_s = sndr + 10.0 * math.log10(0.5 * fs_hz / power)
    else:
        power = mul(fp.get("power_uw"), 1e-6)
        e_conv = mul(fp.get("e_conv_pj"), 1e-12)
        fom_w = fp.get("fom_walden_fj") if ok else None
        fom_s = fp.get("fom_schreier_db") if ok else None
    cp = d.get("cdac_pex") or {}
    mac = MACROS.get(c["cdac_key"]) or {}
    _, pv = own_pv(c, d)
    raw = raw_fft(fp.get("codes_uncalibrated"), fp.get("n_fft"), fp.get("m_bin")) if synth_of(d) else None
    m = {
        "enob": enob, "enob_loss": R(c["nbits"] - enob, 4) if enob is not None else None, "sndr": sndr,
        "sfdr": fp.get("sfdr_db") if ok else None,
        "thd": fp.get("thd_db") if ok else None,
        "enob_raw": raw["enob"] if raw else None,
        "fs": R(fs_hz),
        "power": R(power), "e_conv": R(e_conv),
        "fom_w": R(fom_w), "fom_s": R(fom_s),
        "p_leak": R(p_leak),
        "dnl": cp.get("dnl_max"), "inl": cp.get("inl_max"),
        "enob_var": mac.get("worst_redundant_enob", pv.get("worst_redundant_enob")),
        "enob_var_bin": mac.get("worst_binary_enob", pv.get("worst_binary_enob")),
        "area": c.get("area_um2"),
    }
    nt = PARTIAL_NOTE + (f"; {fp.get('n_fft', 32)}-point coherent FFT — SNDR/ENOB/FoMs include an analytical thermal-noise "
                         "term (kT/C + comparator noise) added to the SPICE spectrum, and short FFTs can put ENOB at or above N (±0.3 b)")
    if synth_of(d):
        nt += ("; **dynamic metrics not reported**: the published calibrated codes of loop-unrolled cards are synthesized by the "
               "generator (fit to an ideal sine + hard-coded HD2/HD3), so 'ENOB (raw codes)' gives the uncalibrated SPICE result instead")
    elif not fft_ok_of(d):
        nt += "; **FFT run failed for this card** (ngspice error) — dynamic metrics not available"
    elif fp.get("eoc_all_high") is False:
        nt += "; EOC was not reached on every FFT cycle (incomplete conversions lower ENOB)"
    if c.get("sleep_gated"):
        nt += ("; power = SPICE energy/conversion × fs + duty-cycled SPICE sleep leakage (repo formula; "
               "the transient itself runs at a 650–680 ns conversion period)")
    nt += "; robust = no redundant switching failure in the 5 injected-variance corners (SPICE on the extracted CDAC)"
    robust = bool(mac.get("all_redundant_corners_pass", pv.get("all_redundant_corners_pass", c.get("postpex_var_pass"))))
    return {"metrics": {k: v for k, v in m.items()}, "robust": robust, "note": nt}


# ----------------------------------------------------------------------------- detail document
def weights_str(w, red):
    redset, seen, out = set(red or []), set(), []
    for x in w or []:
        if x in redset and x in seen:
            out.append(f"{x}*")
        else:
            out.append(str(x))
        seen.add(x)
    return ", ".join(out)


def fft_chart(fp, title, stage=None, note_=None):
    f = fp.get("freqs_mhz") or []
    s = fp.get("spec_dbc") or []
    mb = fp.get("m_bin", 3)
    xs, ys, xsig, ysig = [], [], [], []
    for i, (fr, v) in enumerate(zip(f, s)):
        if i == 0:
            continue
        if i == mb:
            xsig.append(R(fr * 1e6)); ysig.append(R(v, 4))
        else:
            xs.append(R(fr * 1e6)); ys.append(R(v, 4))

    def stem(name, x, y, color, size):
        return {"type": "scatter", "mode": "markers", "name": name, "x": x, "y": y,
                "marker": {"color": color, "size": size},
                "error_y": {"type": "data", "symmetric": False, "array": [0] * len(y),
                            "arrayminus": [R(v + 110, 4) for v in y], "width": 0, "thickness": 2, "color": color},
                "hovertemplate": "%{x:.4s}Hz: %{y:.1f} dBc<extra></extra>"}
    head = (f"ENOB = {fp.get('enob')} b · SNDR = {fp.get('sndr_db')} dB · SFDR = {fp.get('sfdr_db')} dB · "
            f"THD = {fp.get('thd_db')} dB · fs = {si(fp.get('fs_msps', 0) * 1e6, 'S/s')} · "
            f"coherent f_in = {si(fp.get('fin_mhz', 0) * 1e6, 'Hz')} (bin {mb} of {fp.get('n_fft')})")
    return chart(title, [stem("spurs / noise bins", xs, ys, BLUE, 6), stem("signal bin", xsig, ysig, GREEN, 9)],
                 "Frequency (Hz)", "Power (dBc)",
                 {"xaxis": {"exponentformat": "SI", "ticksuffix": "Hz"}, "yaxis": {"range": [-112, 6]}},
                 height=340, caption=head + (f"  \n{note_}" if note_ else ""), **({"stage": stage} if stage else {}))


def detail_doc(c, d):
    cid = c["card_id"]
    sp = d["spice"]
    fp, fpre, ffull = sp.get("fft_post") or {}, sp.get("fft_pre") or {}, sp.get("fft_full") or {}
    wf = sp.get("waveform_post") or {}
    tr = wf.get("traces") or {}
    vdd = d["vdd"]
    fs_hz = fp.get("fs_msps", 0) * 1e6
    ok = fft_ok_of(d)
    sleep = bool(d.get("sleep_gated"))
    tier = d.get("fs_tier", "hs")
    u = ulp_power(c, d) if sleep else None
    blocks = []

    # ---- caveats specific to this card
    if not ok:
        blocks.append(note("The coherent SPICE FFT of this card failed (ngspice error in the majority-vote "
                           "netlist). The old site showed fallback values (thermal-noise ceiling) as if simulated: "
                           f"ENOB {fp.get('enob')} b, SNDR {fp.get('sndr_db')} dB. The hub reports no dynamic metrics.",
                           "bad", "FFT failed."))
    syn = synth_of(d)
    raw = raw_fft(fp.get("codes_uncalibrated"), fp.get("n_fft"), fp.get("m_bin")) if syn else None
    if syn:
        blocks.append(note(
            "The published FFT codes of loop-unrolled cards are **not SPICE output**: the generator fits the raw SPICE codes "
            "exactly to an ideal sine (its 'foreground LUT + radix calibration' includes a per-sample basis) and then adds a "
            "hard-coded HD2/HD3 term (sargen/lu2g.py `_calibrate_lu2g_radix_and_cm_lut`). The published ENOB "
            f"{fp.get('enob')} b, SNDR {fp.get('sndr_db')} dB and FoMs are therefore synthetic. The raw, uncalibrated SPICE "
            f"codes give ENOB {raw['enob'] if raw else '—'} b (SNDR {raw['sndr_db'] if raw else '—'} dB, hub FFT without added noise); "
            "the hub reports only that as a result. The 3-cycle conversion table was gain/offset-fitted as well (tab 2).",
            "bad", "Synthesized FFT codes."))
    if ok and not syn and fp.get("eoc_all_high") is False:
        blocks.append(note("EOC (end of conversion) was not reached on every FFT cycle, so part of the conversions "
                           "were incomplete; the SPICE ENOB of this card is correspondingly low.", "warn", "Incomplete conversions."))
    if sleep:
        blocks.append(note(
            f"The top-level energy and leakage of this sleep-gated card are generator placeholders "
            f"(E_dyn = {d.get('e_dyn_pj')} pJ, P_leak = {d.get('p_leak_nw')} nW); the old site's power and FoMs used them. "
            f"The SPICE transient measured E_dyn = {si(u['e_dyn'] if u else None, 'J')} and sleep leakage "
            f"{si(u['leak'] if u else None, 'W')}; the hub recomputes power and FoMs from those with the repo's formula. "
            "The transient runs at a 650–680 ns conversion period; the power at the card's sample rate is extrapolated "
            "(E_dyn × fs + duty-cycled leakage).", "warn", "ULP energy placeholders."))
    twins = WF_TWINS.get(cid) or []
    if twins:
        blocks.append(note("This card shares its SPICE waveform/FFT record with " + ", ".join(f"[`{x}`](#/sar/{x})" for x in twins)
                           + " (same ULP core simulation, different target sample rate).", "muted"))
    elif FFT_TWINS.get(cid):
        blocks.append(note(f"The {fp.get('n_fft')} published FFT output codes of this card are identical to those of "
                           + ", ".join(f"[`{x}`](#/sar/{x})" for x in FFT_TWINS[cid])
                           + (" — both are synthesized by the generator's loop-unrolled calibration fit (see above)." if syn
                              else " (duplicated simulation record in the generator's cache)."), "muted"))
    pv_src, pv = own_pv(c, d)
    old_pv = (d.get("resilience") or {}).get("postpex_variance") or {}
    if old_pv.get("ckey") and old_pv.get("ckey") != c["cdac_key"]:
        blocks.append(note(f"The generator attached the post-PEX variance record of `{old_pv.get('ckey')}` to this card "
                           f"(the old site showed it here). This card uses `{c['cdac_key']}`; the hub shows that macro's record "
                           f"(simulated with card `{pv_src}`).", "warn", "Variance record corrected."))

    # ---- header (old modal title / subtitle)
    blocks.append(kv("Card summary", [
        ["Card", f"`{cid}` — {d['arch_title']}"],
        ["Supply", f"{vdd} V"],
        ["Raw resolution", f"{d['nbits']}-bit ({d['k_sw']} switched redundant steps, {d.get('k_total')} incl. LSB term)"],
        ["CDAC", d["cap_title"]],
        ["Input S/H", d["input_arch"]],
        ["Sample-rate tier", d.get("tier_label") or TIER_LABEL.get(tier, tier)],
    ], cols=2, caption=d.get("description")))

    tabs = []
    # ================================================================== 1 schematic & gm/Id
    comps = d.get("components") or {}
    ga = d.get("gmid_annotations") or []
    t1 = [
        kv("Architecture", [
            ["Switching scheme", d.get("switching_scheme", "")],
            ["CDAC weights (* = redundant duplicate)", f"`[{weights_str(d.get('weights'), d.get('redundant_positions'))}]`"],
            ["Redundant positions", f"`{d.get('redundant_positions')}`"],
            ["Total weight span", f"{d.get('total_weight_span')} LSB"],
            ["Bridge split scale", d.get("split_scale")],
            ["LSB majority votes", d.get("lsb_votes")],
            ["CDAC macro", f"`{d.get('cdac_key')}`"],
            ["Time-interleaving to 2 GS/s", f"{d.get('ti_ways_for_2gsps')}×" if tier == "lu2g" else "—"],
        ], cols=2),
        table("Sub-block gm/Id target vs. annotated gm/Id",
              [col("block", "Sub-block", type_="text", wrap=True), col("lib", "Selected library component", type_="text", wrap=True),
               col("regime", "Inversion regime", type_="text", wrap=True), col("tgt", "Target gm/Id", "V⁻¹", digits=3),
               col("sim", "“Post-PEX simulated” gm/Id (as published)", "V⁻¹", digits=3),
               col("metric", "Key characterized performance", type_="text", wrap=True)],
              [[g.get("block"), g.get("source_lib"), g.get("regime"), g.get("gmid_target_vinv"), g.get("gmid_sim_vinv"),
                g.get("key_metric")] for g in ga],
              caption="The old site labelled the second gm/Id column *post-PEX simulated*. In the generator these values are "
                      "the target scaled by fixed factors (0.93–0.97) or constants (sargen/arch.py `extract_gmid_annotations`, "
                      "ulp/uhs/lu2g.py), not values extracted from a simulation.", search=False, csv=False),
    ]
    rows = []
    cm = (comps.get("comp") or {})
    if cm:
        m = cm.get("m_pex") or {}
        rows.append(["Comparator (sa-gen)", mdlink("sa", cm["key"]), cm.get("area_um2"),
                     f"t_d(10 mV) {si(m.get('delay_10mv'), 's')}, E {si(m.get('e_total'), 'J')}, σ_noise {si(m.get('sigma_noise'), 'V')}, "
                     f"σ_os {si(m.get('vos_sigma'), 'V')}, PVT {m.get('pvt_pass')}/{m.get('pvt_total')}"])
    sw = comps.get("sw") or {}
    if sw:
        m = sw.get("m_pex") or {}
        rows.append(["S/H switch (switch-gen)", mdlink("switch", sw["key"]), sw.get("area_um2"),
                     f"R_on,wc {si(m.get('ron_wc'), 'Ω')}, THD {fx(m.get('thd_db'), 'dB')}, t_on {si(m.get('t_on'), 's')}, "
                     f"E_VDD {si(m.get('e_vdd'), 'J')}, worst leak {si(m.get('leak_wc'), 'A')}"])
    for k, role in (("opa_vcm", "VCM buffer op-amp (opa-gen)"), ("opa_in", "Input driver op-amp (opa-gen)")):
        o = comps.get(k) or {}
        if o:
            m = o.get("m_pex") or {}
            rows.append([role, mdlink("opa", o["key"]), o.get("area_um2"),
                         f"A0 {fx(m.get('a0_db'), 'dB')}, UGB {si(m.get('ugb_hz'), 'Hz')}, PM {fx(m.get('pm_deg'), '°')}, "
                         f"P {si(mul(m.get('power_uw'), 1e-6), 'W')}, v_n {si(mul(m.get('vn_rms_uv'), 1e-6), 'V')} rms, "
                         f"PVT {m.get('pvt_pass')}/{m.get('pvt_total')}"])
    ctrl = comps.get("sar_ctrl") or {}
    if ctrl:
        rows.append(["SAR controller (gf180mcu std cells)", "—", ctrl.get("estimated_gate_area_um2"),
                     f"{ctrl.get('cell_count')} standard cells, {ctrl.get('n_dly_settle')} settle-delay stages (schematic in simulation)"])
    t1.append(table("Reused sub-blocks (links open the sibling component on the hub)",
                    [col("role", "Role", type_="text"), col("key", "Library component", type_="text", md=True),
                     col("area", "Area", "µm²", digits=4), col("m", "Key post-PEX characterization (sibling repo)", type_="text", wrap=True)],
                    rows, search=False, csv=False))
    gal = [{"label": f"Comparator `{cm.get('key', '')}`", "src": f"designs/{cid}/comp_schematic.svg"},
           {"label": f"S/H switch `{sw.get('key', '')}`", "src": f"designs/{cid}/sw_schematic.svg"},
           {"label": f"VCM op-amp `{(comps.get('opa_vcm') or {}).get('key', '')}`", "src": f"designs/{cid}/opa_schematic.svg"}]
    gal = [g for g in gal if (DOCS / g["src"]).is_file()]
    if gal:
        t1.append({"type": "gallery", "title": "Reused sub-block schematics", "style": "grid", "cols": 3, "items": gal, "max_height": 360,
                   "caption": "The annotated top-level schematic, the full-chip layout and the CDAC macro layout are in the *Figures* gallery at the top of this page."})
    tabs.append({"label": "1 · Schematic & gm/Id", "blocks": t1})

    # ================================================================== 2 FFT & waveforms
    t2 = []
    if ok and syn:
        if raw:
            t2.append(fft_chart(dict(fp, spec_dbc=raw["spec_dbc"], enob=raw["enob"], sndr_db=raw["sndr_db"], sfdr_db=raw["sfdr_db"], thd_db=raw["thd_db"]),
                                "FFT spectrum of the raw, uncalibrated SPICE output codes (hub-computed)", stage="partial",
                                note_="Computed by the hub from `codes_uncalibrated` (no added thermal noise)."))
        t2.append(fft_chart(fp, "Published spectrum — synthesized by the generator's calibration fit (not SPICE)",
                            note_="Old-site spectrum, shown for completeness: the codes are an ideal sine plus a hard-coded HD2/HD3 term."))
    elif ok:
        t2.append(fft_chart(fp, "Coherent transistor-level SPICE FFT spectrum (partial post-PEX)", stage="partial"))
    else:
        t2.append(note("No FFT spectrum: the SPICE FFT run failed for this card.", "bad"))
    # pre / post / full summary table
    p_dyn = mul(d.get("p_dyn_uw", fp.get("p_dyn_uw")), 1e-6)
    leak = mul(d.get("p_leak_nw"), 1e-9)
    hdr = [col("m", "Metric", type_="text"),
           col("pre", "Pre-layout (ideal CDAC) — model estimate", type_="text", title="post + fixed offsets; never simulated"),
           col("post", "Post-CDAC-PEX (SPICE, as published)", type_="text"),
           col("full", "Full-chip PEX — model estimate", type_="text", title="post − 0.18 dB SNDR, ×1.018 power; never simulated")]
    if sleep:
        hdr.append(col("rec", "Post-CDAC-PEX — recomputed from SPICE energy (hub)", type_="text"))
    fail = " (synthesized)" if syn else "" if ok else " (fallback, FFT failed)"

    def rowp(label, kp, unit="", d_=4, scale=1.0, siu=None, rec=None):
        f = (lambda v: si(mul(v, scale), siu, d_)) if siu else (lambda v: fx(v, unit, d_))
        sfx = fail if kp not in ("fs_msps", "power_uw") else ""
        r = [label, f(fpre.get(kp)) + sfx, {"v": f(fp.get(kp)) + sfx, "s": "good" if ok and not syn else "warn"}, f(ffull.get(kp)) + sfx]
        if sleep:
            r.append(rec if rec is not None else "—")
        return r
    rec_fom_w = rec_fom_s = None
    if u and ok:
        rec_fom_w = u["power"] / (fs_hz * 2.0 ** fp["enob"]) * 1e15
        rec_fom_s = fp["sndr_db"] + 10 * math.log10(0.5 * fs_hz / u["power"])
    rows = [
        rowp("ENOB", "enob", "b", rec=fx(fp.get("enob"), "b") if ok else "—"),
        rowp("SNDR", "sndr_db", "dB", rec=fx(fp.get("sndr_db"), "dB") if ok else "—"),
        rowp("SFDR", "sfdr_db", "dB", rec=fx(fp.get("sfdr_db"), "dB") if ok else "—"),
        rowp("THD", "thd_db", "dB", rec=fx(fp.get("thd_db"), "dB") if ok else "—"),
        rowp("Sampling rate f_s", "fs_msps", scale=1e6, siu="S/s", rec=si(fs_hz, "S/s")),
        ["Dynamic power P_dyn", si(mul(p_dyn, 0.965), "W"), f"{si(p_dyn, 'W')} ({fx(d.get('e_dyn_pj'), 'pJ')}/conv)", si(mul(p_dyn, 1.018), "W")]
        + ([f"{si(u['p_dyn'], 'W')} ({si(u['e_dyn'], 'J')}/conv)" if u else "—"] if sleep else []),
        ["Standby leakage P_leak", si(leak, "W"), f"{si(leak, 'W')} ({si(mul(d.get('i_leak_na'), 1e-9), 'A')})", si(leak, "W")]
        + ([f"{si(u['leak'], 'W')} measured, × duty {u['duty']:.4g} = {si(u['p_leak_eff'], 'W')}" if u else "—"] if sleep else []),
        rowp("Total supply power", "power_uw", scale=1e-6, siu="W", rec=si(u["power"], "W") if u else "—"),
        rowp("Walden FoM", "fom_walden_fj", "fJ/step", rec=fx(rec_fom_w, "fJ/step") if rec_fom_w else "—"),
        rowp("Schreier FoM", "fom_schreier_db", "dB", rec=fx(rec_fom_s, "dB") if rec_fom_s else "—"),
    ]
    cap = ("Only the **post-CDAC-PEX** column is a SPICE result (partial post-PEX: extracted CDAC and sibling sub-block PEX, "
           "schematic SAR logic, no top-level routing). *Pre-layout* = post + 0.12–0.16 dB SNDR and ×0.96–0.97 power; "
           "*full-chip PEX* = post − 0.18 dB SNDR, −0.35 dB SFDR, ×1.018 power (sargen/arch.py, site.py "
           "`_derive_full_pex_fft`) — model estimates carried over from the old site, never simulated. The old site derived "
           "the P_dyn row as ×0.965 / ×1.018 of post.")
    if tier == "hs":
        cap += (" For continuous-mode cards P_leak is the VCM op-amp's characterized bias power + a 14.5/38 nW constant and "
                "P_dyn = total − op-amp power (sargen/ulp.py), not separate measurements.")
    elif tier in ("uhs100m", "lu2g"):
        cap += " P_leak is the VCM op-amp's measured average power + a constant (sargen/uhs.py, lu2g.py); P_dyn = total − op-amp power."
    t2.append(table("Pre-layout vs. post-CDAC-PEX vs. full-chip PEX — dynamic & leakage summary", hdr, rows,
                    caption=cap, search=False, csv=False))
    # sub-block breakdown
    sub_rows = []
    if sleep:
        src_sub = {k: wf.get(k) or {} for k in SUB_LABEL}
        sub_cap = ("SPICE: per-rail charge in the 380 ns active window (E_dyn) and average current in the sleep window "
                   "(leakage) of the ULP core transient (`waveform_post.<rail>`). The old site read an empty record here and "
                   "showed zeros.")
    else:
        src_sub = d.get("subblock_power") or wf.get("subblock_power") or {}
        if tier == "hs":
            sub_cap = ("**Not simulated per rail:** for continuous-mode cards the generator splits E_dyn by fixed fractions "
                       "(S/H 6 %, CDAC 28 %, comparator 34 %, controller 32 %), uses the op-amp's characterized power for the "
                       "VCM buffer, and constant leakage values (sargen/ulp.py). Shown as published.")
        else:
            sub_cap = ("E_dyn per rail measured with SPICE current meters (vmeas_*) over two conversion cycles. The leakage "
                       "columns are constants for S/H, CDAC, comparator and controller and the op-amp's average power for the "
                       "VCM buffer (sargen/uhs.py) — not measured leakage.")
    for k, lbl in SUB_LABEL.items():
        sb = src_sub.get(k) or {}
        e = mul(sb.get("e_dyn_pj"), 1e-12)
        sub_rows.append([lbl, e, mul(e, fs_hz), mul(sb.get("p_leak_nw"), 1e-9), mul(sb.get("i_leak_na"), 1e-9)])
    if sleep and wf.get("tot"):
        t = wf["tot"]
        e = mul(t.get("e_dyn_pj"), 1e-12)
        sub_rows.append([{"v": "Total (all rails)", "s": "good"}, e, mul(e, fs_hz), mul(t.get("p_leak_nw"), 1e-9), mul(t.get("i_leak_na"), 1e-9)])
    t2.append((staged if tier != "hs" else (lambda x: x))(table(f"Sub-block dynamic energy & standby leakage breakdown ({'EOC autonomous sleep power-gated' if sleep else 'continuous high-speed mode'})",
                    [col("b", "Sub-block rail", type_="text"), col("e", "Dynamic energy / conv. E_dyn", "J", True),
                     col("p", f"Dynamic power @ {si(fs_hz, 'S/s')}", "W", True), col("l", "Standby (sleep) leakage power", "W", True),
                     col("i", "Standby leakage current (27 °C)", "A", True)],
                    sub_rows, caption=sub_cap, search=False, csv=False)))
    t_ns = RL(tr.get("t_ns"), 5)
    if t_ns:
        wf_cap = f"SPICE transient (partial post-PEX), cycles 0 and 1 at +0.75·FS and −0.75·FS. {len(t_ns)} samples (as stored in docs)."
        t2.append(staged(section(None, [
            chart("CDAC top-plate convergence waveform", [
                line("TOP_P (CDAC +)", t_ns, RL(tr.get("top_p"), 4), BLUE),
                line("TOP_N (CDAC −)", t_ns, RL(tr.get("top_n"), 4), PINK),
                line("VCM_INT (OPA buffer)", t_ns, RL(tr.get("vcm_int"), 4), GREEN, "dash", 1.5)],
                "Time (ns)", "Voltage (V)", {"yaxis": {"range": [0, vdd * 1.05]}}, height=320, caption=wf_cap),
            chart("Asynchronous SAR clocking & handshake", [
                line("PHI_S (sample)", t_ns, RL(tr.get("phi_s"), 4), AMBER),
                line("COMP_CLK (async osc.)", t_ns, RL(tr.get("comp_clk"), 4), PURPLE, width=1.5),
                line("EOC (done)", t_ns, RL(tr.get("eoc"), 4), GREEN)],
                "Time (ns)", "Clock / control (V)", {"yaxis": {"range": [-0.1, vdd * 1.1]}}, height=320),
        ], cols=2)))
        extra = []
        if tr.get("vdiff_top"):
            extra.append(line("V(top_p) − V(top_n)", t_ns, RL(tr.get("vdiff_top"), 4), BLUE))
        if tr.get("code_reconstructed"):
            extra.append(line("reconstructed code", t_ns, RL(tr.get("code_reconstructed"), 5), AMBER, yaxis="y2"))
        if extra:
            t2.append(staged(chart("Differential top-plate residue & reconstructed output code", extra, "Time (ns)", "V_diff (V)",
                            {"yaxis2": {"title": {"text": "Code (LSB)"}, "overlaying": "y", "side": "right"}}, height=300,
                            caption="Additional traces stored in docs (`vdiff_top`, `code_reconstructed`); not plotted by the old site.")))
    cyc = []
    tt = next((x for x in (sp.get("pvt_corners") or []) if x.get("corner") == "typical"), {}) if syn else {}
    for i, cy in enumerate(wf.get("cycles") or []):
        vd = num(cy.get("vdiff_v")) or 0.0
        norm = cy.get("norm_in", vd / max(0.1, vdd))
        bits = "".join(map(str, cy["bits"])) if isinstance(cy.get("bits"), list) else str(cy.get("bits", ""))
        err = cy.get("err_lsb")
        cyc.append([f"Cycle {cy.get('cycle', i)}", vd, R(norm * 100, 3), bits, cy.get("code_nbits"),
                    cy.get("expected_code_nbits", cy.get("ideal_code")),
                    {"v": err, "s": "good" if num(err) is not None and abs(err) <= 1 else "warn"},
                    bool(cy.get("eoc_ok", wf.get("eoc_ok", True)))])
        if syn:
            rc = tt.get(f"cyc{i}_code")
            ex = cy.get("expected_code_nbits", cy.get("ideal_code"))
            cyc[-1] += [rc, {"v": R(rc - ex, 4) if num(rc) is not None and num(ex) is not None else None, "s": "bad"}]
    cyc_cols = [col("c", "Cycle", type_="text"), col("v", "Differential input (VIP − VIN)", "V", digits=5),
                col("n", "Input", "% FS", digits=3), col("b", "Redundant output bit stream", type_="text"),
                col("m", "Measured code" + (" (post-fit)" if syn else ""), "LSB", digits=6), col("e", "Expected code", "LSB", digits=6),
                col("err", "Linearity error" + (" (post-fit)" if syn else ""), "LSB", digits=3), col("eoc", "EOC handshake", type_="status")]
    if syn:
        cyc_cols += [col("raw", "Raw SPICE code (TT)", "LSB", digits=6), col("rerr", "Raw error", "LSB", digits=4)]
    t2.append(staged(table("3-cycle transistor-level SPICE conversion verification", cyc_cols, cyc, search=False, csv=False,
                           caption=("**Post-fit codes:** the generator fits cycles 0 and 1 with a 2-point gain/offset correction "
                                    "(errors forced to 0.00 LSB) and clamps the cycle-2 error to ≤ 0.68 LSB (sargen/lu2g.py). The raw "
                                    "SPICE codes of the TT run (`pvt_corners[0]`) and their errors are added on the right.") if syn else None)))
    sd = wf.get("step_decisions_cycle0") or []
    if sd:
        t2.append(staged(table("Bit-cycling decisions, cycle 0 (SPICE)",
                        [col("s", "Step", digits=3), col("w", "Weight", "LSB", digits=5), col("t", "t", "ns", digits=5),
                         col("p", "V(top_p)", "V", digits=4), col("n", "V(top_n)", "V", digits=4),
                         col("d", "V_diff", "mV", digits=4), col("b", "Bit", digits=1)],
                        [[x.get("step"), x.get("weight_lsb"), x.get("t_ns"), x.get("top_p_v"), x.get("top_n_v"), x.get("vdiff_mv"), x.get("bit")] for x in sd],
                        caption="Stored in docs (`waveform_post.step_decisions_cycle0`); not shown by the old site.", search=False, csv=False)))
    tabs.append({"label": "2 · Dynamic FFT & waveforms (SPICE)", "blocks": t2})

    # ================================================================== 3 static linearity & noise
    cp = d.get("cdac_pex") or {}
    lin = cp.get("linearity") or {}
    b = d.get("budget") or {}
    ax = RL(lin.get("code_axis"), 5)
    t3 = [staged(section(None, [
        chart("Post-PEX differential non-linearity (DNL)", [line(f"DNL (max {cp.get('dnl_max')} LSB)", ax, RL(lin.get("dnl"), 4), BLUE)],
              f"Output code (0 … {2 ** d['nbits'] - 1})", "DNL (LSB)", height=300),
        chart("Post-PEX integral non-linearity (INL)", [line(f"INL (max {cp.get('inl_max')} LSB)", ax, RL(lin.get("inl"), 4), AMBER)],
              f"Output code (0 … {2 ** d['nbits'] - 1})", "INL (LSB)", height=300),
    ], cols=2, intro="Static linearity computed from the Magic-extracted CDAC step weights (sargen/cdac_pex.py "
                     "`compute_static_linearity`), not from a SPICE code-density test. "
                     f"{len(ax)} code points as stored in docs; missing codes: {lin.get('missing_codes')}."))]
    t3.append(kv("Thermal noise & static linearity budget (analytical)", [
        ["LSB step (differential)", f"{b.get('v_lsb_mv')} mV (FS_diff = ±{b.get('fs_diff_v')} V)"],
        ["Single-ended top-plate capacitance C_top", f"{b.get('c_top_single_ff')} fF (C_u = {cp.get('cu_ext_ff')} fF, C_B = {cp.get('cb_p_ff')} fF)"],
        ["Differential kT/C sampling noise", f"{b.get('vn_ktc_uv')} µV rms"],
        ["Comparator input-referred noise (raw → effective)", f"{b.get('vn_cmp_raw_uv')} µV → {b.get('vn_cmp_eff_uv')} µV rms ({d.get('lsb_votes')}× LSB vote)"],
        ["Active VCM buffer coupled noise", f"{b.get('vn_ref_eff_uv')} µV rms"],
        ["Total input-referred thermal noise", f"**{b.get('vn_total_uv')} µV rms ({b.get('vn_total_lsb')} LSB)**"],
        ["Thermal-noise SNDR / ENOB ceiling", f"{b.get('sndr_thermal_ceiling_db')} dB / {b.get('enob_thermal_ceiling')} b"],
        ["Post-PEX DNL_max / INL_max", f"{b.get('dnl_max_lsb')} / {b.get('inl_max_lsb')} LSB ({b.get('missing_codes')} missing codes)"],
        ["Max step error", f"{b.get('max_step_error_lsb')} LSB"],
    ] + ([["Attenuation gain / full-scale (diff.)", f"{b.get('atten_gain')} / {b.get('v_fs_diff_v')} V"]]
         if b.get("atten_gain") is not None and b.get("v_fs_diff_v") is not None else []), cols=2, caption="Noise values combine kT/C, the sibling comparator's simulated noise and the op-amp noise analytically (sargen/arch.py)."))
    gt = cp.get("group_table") or []
    sw_ = cp.get("step_weights") or []
    nom_step = defaultdict(float)
    for g in gt:
        if g.get("step_idx") is not None:
            nom_step[g["step_idx"]] += g.get("nom_weight") or 0
    grows = []
    for g in gt:
        si_ = g.get("step_idx")
        stw = sw_[si_] if si_ is not None and si_ < len(sw_) else None
        share = R(stw * (g.get("nom_weight") or 0) / nom_step[si_], 6) if stw is not None and nom_step.get(si_) else None
        grows.append([g.get("name"), str(g.get("node", "")).upper(), g.get("units"), si_ if si_ is not None else "term",
                      g.get("nom_weight"), stw, share, mul(g.get("c_top_ff"), 1e-15), mul(g.get("c_sub_ff"), 1e-15), mul(g.get("c_active_ff"), 1e-15)])
    split = len(gt) > len(sw_)
    t3.append(staged(table(f"Magic post-PEX extracted capacitor group weights (`{d.get('cdac_key')}`)",
                    [col("g", "Group", type_="text"), col("n", "Array node", type_="text"), col("u", "Units", digits=4),
                     col("st", "Step", type_="text"), col("w", "Nominal group weight", "LSB", digits=5),
                     col("p", "Post-PEX step weight", "LSB", digits=6), col("ps", "Post-PEX group share", "LSB", digits=6),
                     col("t", "C to top plate", "F", True), col("s", "C to sub-DAC", "F", True), col("a", "Extracted active cap", "F", True)],
                    grows, search=False,
                    caption=("Post-PEX weights are matched to groups by `step_idx`. " + (
                        "This array splits each step into hi/lo groups, so the step weight is shown on both and the group share = "
                        "step weight × group nominal / step nominal. " if split else "") +
                        "The old site paired step weights with group rows by row index, which mislabels split arrays.")))) 
    t3.append(kv("CDAC extraction summary", [
        ["Unit capacitor C_u (extracted)", f"{cp.get('cu_ext_ff')} fF"],
        ["Bridge capacitor C_B,p / C_B,n", f"{cp.get('cb_p_ff')} / {cp.get('cb_n_ff')} fF"],
        ["Top-plate parasitic / sub-DAC parasitic", f"{cp.get('c_par_top_ff')} / {cp.get('c_par_sub_ff')} fF"],
        ["Attenuation gain", cp.get("atten_gain")],
        ["Macro size", f"{cp.get('width_um')} × {cp.get('height_um')} µm ({cp.get('area_um2')} µm²)"],
    ], cols=2))
    nz = (d.get("mismatch_mc") or {}).get("noise") or {}
    if nz:
        t3.append(kv("Behavioural noise model (mismatch-MC set-up)", [
            ["LSB", si(nz.get("lsb_v"), "V")], ["Quantization noise rms", si(nz.get("q_rms_v"), "V")],
            ["kT/C noise rms", si(nz.get("ktc_rms_v"), "V")], ["Comparator noise rms", si(nz.get("cmp_rms_v"), "V")],
            ["Op-amp noise rms", si(nz.get("opa_rms_v"), "V")], ["Total rms", si(nz.get("total_rms_v"), "V")],
            ["Noise-limited ENOB", f"{nz.get('enob_noise_limit')} b"]], cols=3,
            caption="Stored in docs (`mismatch_mc.noise`); not shown by the old site."))
    tabs.append({"label": "3 · Static linearity (DNL/INL) & noise", "blocks": t3})

    # ================================================================== 4 variation resilience
    r = d.get("resilience") or {}
    vs = pv.get("variance_sweep") or {}
    corners = pv.get("corners") or []
    sm = vs.get("sigma_mult") or []
    fails = [x for x, f in zip(sm, vs.get("switching_failure_binary") or []) if f]
    fails_y = [y for y, f in zip(vs.get("enob_binary") or [], vs.get("switching_failure_binary") or []) if f]
    passtxt = "5/5 corners pass (0 redundant switching failures)" if pv.get("all_redundant_corners_pass") else "redundant switching failure in at least one corner"
    t4 = []
    var_traces = [line(f"Redundant CDAC, calibrated (`{c['cdac_key']}`)", sm, vs.get("enob_redundant_cal") or vs.get("enob_redundant"), GREEN, width=2.6, mode="lines+markers"),
                  line("Redundant CDAC, uncalibrated weights", sm, vs.get("enob_redundant_uncal"), GREEN, "dot", 1.6),
                  line("Binary CDAC (same extracted array)", sm, vs.get("enob_binary_uncal") or vs.get("enob_binary"), RED, "dash", 2.2, mode="lines+markers")]
    if fails:
        var_traces.append({"type": "scatter", "mode": "markers", "name": "binary switching failure", "x": fails, "y": fails_y,
                           "marker": {"symbol": "x", "size": 11, "color": RED}})
    res_cols = [BLUE, GREEN, AMBER, PURPLE, PINK]
    res_tr = []
    for i, co in enumerate(corners):
        y = co.get("trace_res_lsb") or []
        res_tr.append(line(co.get("label", co.get("corner_id")), list(range(len(y))), RL(y, 5), GRAY if i == 0 else res_cols[i % 5],
                           "dash" if i == 0 else None, 1.8 if i == 0 else 2.2, mode="lines+markers"))
    t4.append(staged(section(None, [
        chart(f"1 · Post-PEX injected CDAC variance & switching-failure immunity — {passtxt}", var_traces,
              "Injected variance multiplier (× σ_Pelgrom + ΔC_bridge)", "Post-PEX ENOB (bits)", height=330,
              caption="SPICE on the Magic-extracted CDAC with artificially injected capacitor variance (sargen/cdac_variance.py)."),
        chart("2 · Post-PEX SPICE bit-cycling differential residue under injected variance", res_tr,
              "Bit-cycling step index j", "Residue V_top,p − V_top,n (LSB)", height=330,
              caption="All five corners (the old site plotted the first four)."),
    ], cols=2)))
    t4.append(staged(table("5-corner post-PEX injected CDAC variance & switching-failure verification (extracted Magic netlist)",
                    [col("id", "Corner", type_="text"),
                     col("re", "ENOB (cal.)", "b", digits=4, group="Redundant CDAC"), col("rerr", "Max error", "LSB", digits=3, group="Redundant CDAC"),
                     col("rf", "Switching failure", type_="text", group="Redundant CDAC"),
                     col("be", "ENOB", "b", digits=4, group="Binary CDAC"), col("berr", "Max error", "LSB", digits=4, group="Binary CDAC"),
                     col("bf", "Switching failure", type_="text", group="Binary CDAC"), col("fr", "Final residue", "LSB", digits=3),
                     col("l", "Injected perturbation", type_="text", wrap=True), col("d", "Description", type_="text", wrap=True),
                     col("s", "σ mult.", digits=3), col("bp", "ΔC_B,p", "%", digits=3), col("bn", "ΔC_B,n", "%", digits=3),
                     col("at", "Atten. (SPICE)", digits=5), col("cmb", "CM bounce", "mV", digits=4),
                     col("ru", "Redundant ENOB (uncal.)", "b", digits=4), col("rmc", "Redundant missing codes", digits=3)],
                    [[co.get("corner_id"), co.get("redundant_enob"), co.get("max_code_err_lsb"),
                      {"v": "FAIL" if co.get("switching_failure") else "0 fail (pass)", "s": "bad" if co.get("switching_failure") else "good"},
                      co.get("binary_enob"), co.get("binary_max_err_lsb"),
                      {"v": "FAIL" if co.get("binary_switching_failure") else "pass", "s": "bad" if co.get("binary_switching_failure") else "good"},
                      co.get("final_residue_lsb"), co.get("label"), co.get("description"), co.get("sigma_mult"), mul(co.get("bridge_rel_p"), 100),
                      mul(co.get("bridge_rel_n"), 100), co.get("atten_spice"), co.get("cm_bounce_mv"),
                      (co.get("redundant_uncal") or {}).get("enob"), (co.get("redundant_cal") or {}).get("missing_codes")] for co in corners],
                    caption=f"Worst redundant ENOB **{pv.get('worst_redundant_enob')} b** vs. binary under variance **{pv.get('worst_binary_enob')} b**. "
                            f"Record of macro `{pv.get('ckey')}` (SPICE run with card `{pv_src}`).", search=False)))
    vt = pv.get("traces") or {}
    if vt.get("t_ns") and vt.get("vdiff_by_corner"):
        tt = RL(vt["t_ns"], 5)
        lbl = {co.get("corner_id"): co.get("label") for co in corners}
        t4.append(staged(chart("Post-PEX SPICE differential top-plate transient per variance corner",
                        [line(lbl.get(k, k), tt, RL(v, 4), res_cols[i % 5], width=1.6) for i, (k, v) in enumerate(vt["vdiff_by_corner"].items())],
                        "Time (ns)", "V(top_p) − V(top_n) (V)", height=300,
                        caption="Stored in docs (`postpex_variance.traces`); not plotted by the old site.")))
    ss, ds, bs = r.get("settling_sweep") or {}, r.get("dyn_offset_sweep") or {}, r.get("bridge_variation_sweep") or {}
    beh = "Behavioural Python model of the SAR conversion (sargen/cdac.py `resilience_sweeps`, 128-point FFT), not SPICE."
    t4.append(section(None, [
        chart("3 · Incomplete DAC settling resilience", [
            line(f"Redundant SAR ({d['k_sw']} steps, {ss.get('speedup_factor')}× faster)", ss.get("tau_ratios"), ss.get("enob_redundant"), GREEN, width=2.6),
            line(f"Conventional binary SAR ({d['nbits']} steps)", ss.get("tau_ratios"), ss.get("enob_binary"), RED, "dash")],
            "Per-bit settling window T_bit / τ_DAC", "ENOB (bits)", height=300,
            caption=f"{beh} Minimum T_bit/τ for ENOB ≥ N − 0.5: redundant {ss.get('min_tau_ratio_redundant')}, binary {ss.get('min_tau_ratio_binary')}."),
        chart("4 · Dynamic comparator offset & kickback resilience", [
            line("Redundant SAR (error absorbed by sub-binary steps)", ds.get("sigma_dyn_lsb"), ds.get("enob_redundant"), BLUE, width=2.6),
            line("Conventional binary SAR (no recovery)", ds.get("sigma_dyn_lsb"), ds.get("enob_binary"), RED, "dash")],
            "Dynamic decision error / kickback σ_dyn (LSB)", "ENOB (bits)", height=300, caption=beh),
    ], cols=2))
    red_rows = []
    for row in r.get("redundancy_table") or []:
        red = row.get("redundancy_raw", row.get("redundancy_lsb", 0))
        red_rows.append([f"Step {row.get('step')}", row.get("weight"), row.get("remaining_sum", row.get("remaining_cap")),
                         {"v": red, "s": "good" if (red or 0) > 0 else "muted"}, row.get("redundancy_pct")])
    t4.append(section(None, [
        chart("5 · Bridge capacitor variation resilience (±15 % ΔC_B / C_B)", [
            line("Redundant SAR (with digital weight calibration)", bs.get("cb_delta_pct"), bs.get("enob_redundant_cal"), AMBER, width=2.6),
            line("Uncalibrated binary bridge-split SAR", bs.get("cb_delta_pct"), bs.get("enob_binary_uncal"), GRAY, "dash")],
            "Bridge capacitor variation ΔC_B / C_B (%)", "ENOB (bits)", height=300, caption=beh),
        table("Per-step sub-binary correction window",
              [col("s", "Bit step", type_="text"), col("w", "Step weight", digits=5), col("r", "Sum of remaining lower weights", digits=5),
               col("c", "Correction range ±", "LSB", digits=5), col("p", "Correction range ±", "%", digits=3)],
              red_rows, search=False, csv=False, max_height=330),
    ], cols=2))
    tabs.append({"label": "4 · Variation resilience (redundancy)", "blocks": t4})

    # ================================================================== 5 PVT, MC, OPA driver
    pvt = sp.get("pvt_corners") or []
    anc = anchor_of(d)
    prow = []
    for p in pvt:
        if p.get("corner") == "typical":
            src = "SPICE (TT, this card)"
        elif tier in ("1ksps", "100ksps", "1msps", "uhs100m", "lu2g"):
            src = "model: TT × fixed corner multipliers"
        elif cid == anc:
            src = "SPICE on this anchor card (power ratio clamped 0.75–1.35)"
        else:
            src = f"scaled from anchor {anc} SPICE"
        lk = p.get("p_leak_nw")
        prow.append([p.get("label"), p.get("corner"), p.get("temp_c"), mul(p.get("power_uw"), 1e-6),
                     mul(lk, 1e-9) if lk is not None else {"v": mul(d.get("p_leak_nw"), 1e-9), "s": "muted", "title": "card-level value repeated by the old site (no corner-specific value)"},
                     {"v": p.get("max_err_lsb"), "s": "good" if (p.get("max_err_lsb") or 0) <= 1 else "warn"},
                     {"v": "PASS" if p.get("ok") else "CHECK", "s": "muted", "title": "flag hard-coded true by the generator"}, src])
    t5 = [staged(table("5-corner transistor-level PVT & temperature leakage verification",
                [col("l", "Corner", type_="text"), col("c", "Process", type_="text"), col("t", "Temp", "°C", digits=3),
                 col("p", "Total power", "W", True), col("k", "Standby P_leak", "W", True), col("e", "Max linearity error", "LSB", digits=3),
                 col("s", "Status (as published)", type_="text"), col("src", "Source", type_="text", wrap=True)],
                prow, search=False, csv=False,
                caption="Only the TT row is simulated on every card. Non-TT corners were simulated on six anchor cards "
                        "(`sar_{8,10,12}b_{1v8,3v3}_mono_mom`) and scaled to the other high-speed cards; ULP, UHS and loop-unrolled "
                        "cards use fixed corner multipliers (sargen/arch.py, ulp.py, uhs.py, lu2g.py). The PASS flag is hard-coded, "
                        "so it is not a verification result."))]
    drv = sp.get("opa_driver_cosim") or {}
    dt = drv.get("traces") or {}
    if dt.get("t_ns"):
        tn = RL(dt["t_ns"], 5)
        anc_in = (CARDS.get(anc) or {}).get("opa_in_key")
        t5.append(staged(chart(f"Active front-end input driver co-simulation (opa-gen `{drv.get('in_opa_key', '')}`)", [
            line("VIP (buffered by opa-gen)", tn, RL(dt.get("vip"), 4), GREEN, width=2.2),
            line("VIN (buffered)", tn, RL(dt.get("vin"), 4), GREEN, "dot", 1.4),
            line("TOP_P (sampled & switched)", tn, RL(dt.get("top_p"), 4), BLUE),
            line("TOP_N (sampled & switched)", tn, RL(dt.get("top_n"), 4), PINK)],
            "Time (ns)", "Voltage (V)", {"yaxis": {"range": [0, vdd * 1.05]}}, height=320,
            caption=f"SPICE co-simulation run once per (resolution, supply) on anchor card `{anc}` (input op-amp `{anc_in}`) and shown "
                    f"identically for all 18 cards of that group; it is not a simulation of this card. Driver power {si(mul(drv.get('power_uw'), 1e-6), 'W')}, "
                    f"calibrated FS_diff {drv.get('fs_diff_cal')} V, gain ratio {drv.get('gain_ratio')}.")))
        dc = drv.get("cycles") or []
        if dc:
            t5.append(staged(table("Input-driver co-simulation conversions (anchor card)",
                            [col("c", "Cycle", digits=2), col("v", "V_diff in", "V", digits=4), col("ni", "norm. in", digits=3),
                             col("no", "norm. out", digits=4), col("b", "Bits", type_="text"), col("raw", "Raw code", digits=6),
                             col("m", "Calibrated code", digits=6), col("e", "Expected code", digits=6),
                             col("err", "Error (cal.)", "LSB", digits=4), col("eu", "Error (uncal.)", "LSB", digits=4), col("eoc", "EOC", type_="status")],
                            [[x.get("cycle"), x.get("vdiff_v"), x.get("norm_in"), x.get("norm_out"), x.get("bits"), x.get("raw_code"),
                              x.get("code_nbits"), x.get("expected_code_nbits"), x.get("err_lsb"), x.get("err_lsb_uncal"), x.get("eoc_ok")] for x in dc],
                            caption="Stored in docs (`opa_driver_cosim.cycles`); not shown by the old site.", search=False, csv=False)))
    mc = (d.get("mismatch_mc") or {}).get("mc") or {}
    smp = mc.get("samples") or {}
    if smp:
        e, il = mc.get("enob") or {}, mc.get("inl_max") or {}
        t5.append(section(None, [
            chart(f"{mc.get('n', 100)}-run mismatch & thermal-noise Monte Carlo — ENOB", [
                {"type": "histogram", "x": RL(smp.get("enob"), 4), "nbinsx": 14, "name": "ENOB", "marker": {"color": BLUE, "opacity": 0.8}}],
                "ENOB (bits)", "Runs", height=290, caption=f"mean {e.get('mean')} b, σ {e.get('std')} b, P5 {e.get('p5')} b, P95 {e.get('p95')} b."),
            chart(f"{mc.get('n', 100)}-run Pelgrom capacitor-mismatch Monte Carlo — INL_max", [
                {"type": "histogram", "x": RL(smp.get("inl_max"), 4), "nbinsx": 14, "name": "INL_max", "marker": {"color": AMBER, "opacity": 0.8}}],
                "INL_max (LSB)", "Runs", height=290,
                caption=f"mean {il.get('mean')} LSB, P95 {il.get('p95')} LSB; DNL_max mean {(mc.get('dnl_max') or {}).get('mean')} / P95 {(mc.get('dnl_max') or {}).get('p95')} LSB."),
        ], cols=2, intro="Behavioural Monte Carlo (Python model with Pelgrom capacitor mismatch and thermal noise, sargen/cdac.py "
                         "`run_behavioural_mc`), computed per CDAC configuration — not SPICE."))
    tabs.append({"label": "5 · PVT corners, mismatch MC & OPA driver", "blocks": t5})

    # ================================================================== 6 layout
    lay = d.get("layout") or {}
    gds = f"designs/{cid}/{cid}.gds.gz"
    wq, hq = num(lay.get("width_um")), num(lay.get("height_um"))
    cw, ch = num(cp.get("width_um")), num(cp.get("height_um"))
    t6 = [kv("Physical summary", [
        ["Full-chip size", f"{lay.get('width_um')} × {lay.get('height_um')} µm = {lay.get('area_um2')} µm² (aspect {wq / max(1, hq):.3f}:1)" if wq and hq else "—"],
        ["KLayout DRC", "clean (0 violations)" if lay.get("drc_clean") else "not clean"],
        ["KLayout LVS", "netlists match" if lay.get("lvs_clean") else "mismatch"],
        ["CDAC macro", f"`{d.get('cdac_key')}`: {cp.get('width_um')} × {cp.get('height_um')} µm (aspect {cw / max(1, ch):.3f}:1)" if cw and ch else "—"],
        ["CDAC DRC / LVS (as published)", "DRC = 0 · LVS match — flags set unconditionally in sargen/site.py"],
        ["Floorplan", "1.00:1 square, 2-tier folded concentric common-centroid CDAC"],
    ], cols=2)]
    t6.append(section(None, [
        {"type": "layout", "title": "Full-chip 1:1 square SAR ADC layout", "gds": gds, "max_height": 520},
        {"type": "layout", "title": f"2-tier folded common-centroid CDAC macro (`{d.get('cdac_key')}`)", "gds": gds, "cell": f"cdac_{d.get('cdac_key')}", "max_height": 520},
    ], cols=2))
    regs = lay.get("regions") or []
    if regs:
        t6.append(table("Physical floorplan sub-block placement & silicon area",
                        [col("n", "Functional sub-block", type_="text"), col("x", "Origin x", "µm", digits=5), col("y", "Origin y", "µm", digits=5),
                         col("w", "Width", "µm", digits=5), col("h", "Height", "µm", digits=5), col("a", "Macro area", "µm²", digits=5)],
                        [[{"v": g.get("name"), "title": g.get("color")}, g.get("x0"), g.get("y0"), g.get("w"), g.get("h"), R((g.get("w") or 0) * (g.get("h") or 0), 5)] for g in regs],
                        search=False, csv=False))
        shapes = [{"type": "rect", "x0": g["x0"], "y0": g["y0"], "x1": R(g["x0"] + g["w"]), "y1": R(g["y0"] + g["h"]),
                   "line": {"color": g.get("color", GRAY), "width": 2}, "fillcolor": g.get("color", GRAY), "opacity": 0.35} for g in regs]
        if wq and hq:
            shapes.insert(0, {"type": "rect", "x0": 0, "y0": 0, "x1": wq, "y1": hq, "line": {"color": GRAY, "width": 1, "dash": "dot"}})
        t6.append(chart("Floorplan sketch (from the region table)", [
            {"type": "scatter", "mode": "text", "x": [R(g["x0"] + g["w"] / 2) for g in regs], "y": [R(g["y0"] + g["h"] / 2) for g in regs],
             "text": [str(g.get("name", "")).split(" (")[0].replace("Xopa VCM", "Xopa").replace("SAR Logic", "SAR logic") for g in regs],
             "hovertext": [f"{g.get('name')}: {g.get('w')} × {g.get('h')} µm" for g in regs], "hovertemplate": "%{hovertext}<extra></extra>",
             "textfont": {"size": 10}, "showlegend": False}],
            "x (µm)", "y (µm)", {"shapes": shapes, "yaxis": {"scaleanchor": "x", "scaleratio": 1, "constrain": "domain", "range": [-2, R((hq or 0) + 2)]}, "xaxis": {"constrain": "domain", "range": [-2, R((wq or 0) + 2)]}},
            height=420, caption="Drawn from the placement table above (the old site showed the table only)."))
    t6.append({"type": "downloads", "title": "Files", "items": [
        {"label": "Full-chip GDSII (.gds.gz)", "file": gds},
        {"label": "Simulation netlist (extracted CDAC + sibling PEX sub-blocks, schematic SAR logic)", "file": f"designs/{cid}/netlist.spice"},
        {"label": "Card evidence JSON (all data of this page)", "file": f"designs/{cid}/data.json"}]})
    tabs.append({"label": "6 · Layout (full chip & CDAC) + DRC/LVS", "blocks": t6})

    # ================================================================== 7 selection (not on the old site)
    t7 = []

    def sel_caption(cands, used, comp_id):
        keys = [x["key"] for x in cands]
        if keys and keys[0] == used:
            return "The first row (best score) is the component this card uses (marked ✓)."
        if used in keys:
            return f"The generator overrode the ranking: this card uses {mdlink(comp_id, used)} (row {keys.index(used) + 1}, marked ✓), not the first row."
        return f"The generator overrode the ranking: this card uses {mdlink(comp_id, used)}, which is **not in this candidate list**."

    def cand_table(title, comp_id, used, cands, cols_, rowfn):
        rows = []
        for x in cands:
            r = {"use": x["key"] == used, "k": mdlink(comp_id, x["key"])}
            r.update(rowfn(x))
            if x["key"] == used:
                r["_s"] = "good"
            rows.append(r)
        return table(title, [col("use", "Used", type_="status"), col("k", "Component", type_="text", md=True)] + cols_, rows,
                     search=False, csv=False, caption=sel_caption(cands, used, comp_id))
    if cm.get("candidates"):
        t7.append(cand_table("Comparator candidates (sa-gen)", "sa", cm.get("key"), cm["candidates"], [
            col("a", "Arch", type_="text"), col("mx", "Mix", type_="text"), col("t", "Target", type_="text"), col("e", "Energy", "J", True),
            col("dl", "Delay", "s", True), col("n", "σ_noise", "V", True), col("nl", "Noise", "LSB", digits=3), col("w", "CM walk", "LSB", digits=3),
            col("p", "PVT pass", digits=3), col("s", "Score", digits=4, better="low")],
            lambda x: {"a": x.get("arch"), "mx": x.get("mix"), "t": x.get("target"), "e": R(x.get("e_total_j")), "dl": R(x.get("delay_s")),
                       "n": R(x.get("sigma_noise_v")), "nl": x.get("noise_lsb"), "w": x.get("walk_lsb"), "p": x.get("pvt_pass"), "s": R(x.get("score"), 4)}))
    if sw.get("candidates"):
        t7.append(cand_table("S/H switch candidates (switch-gen)", "switch", sw.get("key"), sw["candidates"], [
            col("t", "Topology", type_="text"), col("i", "Current class", type_="text"), col("r", "R_on,wc", "Ω", True),
            col("thd", "THD", "dB", digits=4), col("e", "E_VDD", "J", True), col("p", "Pedestal", "V", True),
            col("tau", "τ_track", "ns", digits=4), col("s", "Score", digits=4)],
            lambda x: {"t": x.get("topo"), "i": x.get("iclass"), "r": x.get("ron_wc_ohm"), "thd": x.get("thd_db"), "e": R(x.get("e_vdd_j")),
                       "p": R(x.get("ped_v")), "tau": x.get("tau_track_ns"), "s": R(x.get("score"), 4)}))
    for k, lbl in (("opa_vcm", "VCM buffer op-amp candidates (opa-gen)"), ("opa_in", "Input driver op-amp candidates (opa-gen)")):
        o = comps.get(k) or {}
        if o.get("candidates"):
            t7.append(cand_table(lbl, "opa", o.get("key"), o["candidates"], [
                col("a", "Arch", type_="text"), col("i", "Class", type_="text"), col("p", "Power", "W", True), col("u", "UGB", "Hz", True),
                col("pm", "PM", "°", digits=3), col("ts", "t_s,1%", "s", True), col("vn", "v_n rms", "V", True),
                col("icmr", "ICMR span", "V", digits=3), col("s", "Score", digits=4)],
                lambda x: {"a": x.get("arch"), "i": x.get("iclass"), "p": mul(x.get("power_uw"), 1e-6), "u": x.get("ugb_hz"), "pm": x.get("pm_deg"),
                           "ts": mul(x.get("ts_1pct_us"), 1e-6), "vn": mul(x.get("vn_rms_uv"), 1e-6), "icmr": x.get("icmr_span_v"), "s": R(x.get("score"), 4)}))
    if t7:
        t7.insert(0, note("Candidate rankings from the generator's systematic sibling-library selection, stored in docs "
                          "(`components.*.candidates`) but not displayed by the old site. On ULP, UHS and loop-unrolled cards the generator "
                          "picked sub-blocks outside this ranking; each table says which component is actually used.", "muted"))
        tabs.append({"label": "7 · Library selection", "blocks": t7})

    blocks.append({"type": "tabs", "id": "pane", "tabs": tabs})
    return {"blocks": blocks}


# ----------------------------------------------------------------------------- designs
designs, hub_vals = [], {}
order = sorted(CARDS.values(), key=lambda c: (ARCH_ORDER[c["arch"]], c["nbits"], c["vdd"], c["cap_type"]))
(OUT / "designs").mkdir(parents=True, exist_ok=True)
for c in order:
    cid = c["card_id"]
    d = DATA[cid]
    base = f"designs/{cid}"
    lay = d.get("layout") or {}
    part = partial_stage(c, d)
    hub_vals[cid] = part["metrics"]
    fp, fpre, ffull = d["spice"]["fft_post"], d["spice"].get("fft_pre") or {}, d["spice"].get("fft_full") or {}
    mc = ((d.get("mismatch_mc") or {}).get("mc") or {}).get("enob") or {}
    tags = [c["arch_title"], c["cap_title"], f"{c['k_sw']}-step redundant CDAC", "1:1 common-centroid"]
    if c.get("lsb_votes", 1) > 1:
        tags.append(f"{c['lsb_votes']}× LSB vote")
    if c.get("sleep_gated"):
        tags.append("EOC sleep-gated")
    if c["fs_tier"] == "lu2g":
        tags.append(f"{c['ti_ways_for_2gsps']}× TI → 2 GS/s")
    if not fft_ok_of(d):
        tags.append("FFT failed")
    files = {"schematic": f"{base}/schematic.svg", "gds": f"{base}/{cid}.gds.gz", "data": f"{base}/data.json"}
    files = {k: v for k, v in files.items() if (DOCS / v).is_file()}
    images = [{"label": f"CDAC macro layout ({c['cdac_key']})", "gds": f"{base}/{cid}.gds.gz", "cell": f"cdac_{c['cdac_key']}"}]
    for lbl, f in (("Comparator schematic", "comp_schematic.svg"), ("S/H switch schematic", "sw_schematic.svg"),
                   ("VCM op-amp schematic", "opa_schematic.svg")):
        if (DOCS / base / f).is_file():
            images.append({"label": lbl, "src": f"{base}/{f}"})
    u = ulp_power(c, d) if c.get("sleep_gated") else None
    params = {
        "CDAC weights (* = redundant)": weights_str(c["weights"], c["redundant_positions"]),
        "Redundant weights": ", ".join(str(w) for w in c["redundant_positions"]),
        "Switching scheme": c["switching_scheme"].replace("`", ""),
        "Input / S&H": c["input_arch"],
        "CDAC macro": c["cdac_key"],
        "C_top single-ended (fF)": c.get("c_top_ff"),
        "Comparator (sa-gen)": c["comp_key"],
        "S/H switch (switch-gen)": c["sw_key"],
        "VCM op-amp (opa-gen)": c["opa_vcm_key"],
        "Input driver op-amp (opa-gen)": c["opa_in_key"],
        "Sample-rate tier": c.get("tier_label"),
        "FFT": f"{fp.get('n_fft')}-point coherent, f_in = {si(fp.get('fin_mhz', 0) * 1e6, 'Hz')}",
        "Thermal-noise ENOB ceiling (analytical)": (d.get("budget") or {}).get("enob_thermal_ceiling"),
        "Behavioural MC ENOB (mean ± σ, n=100)": f"{mc['mean']} ± {mc['std']}" if mc else None,
        "Settling speed-up vs binary (behavioural model)": c.get("speedup_vs_binary"),
        "ENOB pre-layout (model estimate, not simulated)": fpre.get("enob"),
        "ENOB full-chip PEX (model estimate, not simulated)": ffull.get("enob"),
        "Power pre / full (model estimates, µW)": f"{fpre.get('power_uw')} / {ffull.get('power_uw')}",
    }
    if c.get("sleep_gated"):
        params["Published E_dyn / P_leak (placeholders)"] = f"{d.get('e_dyn_pj')} pJ / {d.get('p_leak_nw')} nW"
        params["Published total power / Walden FoM (from placeholders)"] = f"{fp.get('power_uw')} µW / {fp.get('fom_walden_fj')} fJ"
        if u:
            params["SPICE E_dyn / sleep leakage (hub)"] = f"{si(u['e_dyn'], 'J')} / {si(u['leak'], 'W')}"
    else:
        params["Standby P_leak (published; model)"] = f"{si(mul(c.get('p_leak_nw'), 1e-9), 'W')}"
    if not fft_ok_of(d):
        params["Published ENOB / FoM (fallback, FFT failed)"] = f"{c.get('enob_post')} b / {c.get('fom_walden_fj')} fJ"
    if fp.get("enob_noiseless") is not None:
        params["SPICE-only ENOB / SNDR (without the added thermal-noise term)"] = f"{fp.get('enob_noiseless')} b / {fp.get('sndr_noiseless_db')} dB"
    if synth_of(d):
        params["Published ENOB / SNDR / Walden FoM (generator-synthesized, not SPICE)"] = (
            f"{fp.get('enob')} b / {fp.get('sndr_db')} dB / {fp.get('fom_walden_fj')} fJ")
        rw = raw_fft(fp.get("codes_uncalibrated"), fp.get("n_fft"), fp.get("m_bin"))
        if rw:
            params["Raw uncalibrated SPICE codes: ENOB / SNDR / SFDR (hub FFT)"] = f"{rw['enob']} b / {rw['sndr_db']} dB / {rw['sfdr_db']} dB"
    params["PEX coverage"] = "CDAC macro Magic-extracted; switch, comparator and op-amp from the siblings' PEX netlists; SAR logic schematic; top level not extracted"
    uses = [{"component": "sa", "design": c["comp_key"], "role": "comparator"},
            {"component": "switch", "design": c["sw_key"], "role": "S/H switch"},
            {"component": "opa", "design": c["opa_vcm_key"].replace("/", "-"), "role": "VCM buffer"},
            {"component": "opa", "design": c["opa_in_key"].replace("/", "-"), "role": "input driver"}]
    dump(OUT / "designs" / f"{cid}.json", detail_doc(c, d))
    designs.append({
        "id": cid,
        "title": f"{c['nbits']}-bit · {ARCH_LABEL[c['arch']]} · {c['vdd']} V · {c['cap_type'].upper()}",
        "summary": f"**{c['arch_title']}** — {d.get('description', '')}",
        "vdd": c["vdd"],
        "axes": {"mode": MODE_OF(c), "topology": c["arch"], "nbits": str(c["nbits"]), "tier": c["fs_tier"], "cap": c["cap_type"]},
        "tags": tags,
        "physical": {"drc": lay.get("drc_clean", c.get("drc_clean")), "lvs": lay.get("lvs_clean", c.get("lvs_clean")),
                     "pex": None,  # only the CDAC macro is extracted, not the full chip
                     "area_um2": c.get("area_um2"), "width_um": c.get("width_um"), "height_um": c.get("height_um")},
        "results": {"partial": part},
        "params": {k: v for k, v in params.items() if v not in (None, "")},
        "files": files,
        "images": images,
        "downloads": [{"label": "Simulation netlist (extracted CDAC + sibling PEX sub-blocks, schematic SAR logic)", "file": f"{base}/netlist.spice"}],
        "uses": uses,
        "detail": f"hub/designs/{cid}.json",
    })

# ----------------------------------------------------------------------------- page: overview
cards = list(CARDS.values())
pub_min_p = min(cards, key=lambda c: c["power_uw"])
pub_best_fom = min(cards, key=lambda c: c["fom_walden_fj"])
hub_p = {k: v["power"] for k, v in hub_vals.items() if v.get("power")}
hub_f = {k: v["fom_w"] for k, v in hub_vals.items() if v.get("fom_w")}
hub_min_p = min(hub_p, key=hub_p.get)
hub_best_f = min(hub_f, key=hub_f.get)
ulp1k = [cid for cid in hub_p if CARDS[cid]["fs_tier"] == "1ksps"]
hub_min_1k = min(ulp1k, key=hub_p.get)
u1k = ulp_power(CARDS[hub_min_1k], DATA[hub_min_1k])
tier_n = Counter(c["fs_tier"] for c in cards)
n_ulp = sum(1 for c in cards if c.get("sleep_gated"))
lib = SWEEP.get("library_counts") or {}
peak = max(cards, key=lambda c: c["fs_msps"])
n_mac = len(MACROS)
n_mac_pass = sum(1 for m in MACROS.values() if m.get("all_redundant_corners_pass"))
overview = {
    "intro": ("Automated transistor-level design, custom `gLayout` 2-tier folded concentric common-centroid (1.000:1 aspect "
              "ratio) MOM/MIM ratio-trimmed capacitor array generation, systematic sibling component selection (`sa-gen`, "
              "`switch-gen`, `opa-gen`), event-driven autonomous EOC sleep power-gating, sub-binary variation-resilient redundancy "
              "with post-PEX SPICE artificially injected variance verification, and multi-testbench distributed SPICE "
              f"verification across **{len(cards)} deliverable 1:1 square SAR ADCs** (1 kS/s, 100 kS/s, 1 MS/s ultra-low-power, "
              "3–20 MS/s high-speed, 105–150 MS/s smaller-capacitor UHS, and 250–400 MS/s loop-unrolled domino for 2.0 GS/s "
              "time-interleaving). PDK: GF180MCU-D · 180 nm · 5LM · Option-B MIM."),
    "blocks": [
        {"type": "stats", "title": "Key figures as published on the old site", "items": [
            {"label": "Deliverable design cards", "value": f"{len(cards)} / {INDEX.get('total_cards', len(cards))}",
             "sub": f"{n_ulp} ULP + {tier_n['hs']} HS + {tier_n['uhs100m']} UHS + {tier_n['lu2g']} loop-unrolled (2 GS/s TI) · 1.00:1 square"},
            {"label": "Post-PEX variance-verified CDACs", "value": f"{n_mac_pass} / {n_mac} ({n_mac - n_mac_pass} fail)",
             "sub": "2-tier common-centroid · post-PEX 5-corner variance pass"},
            {"label": "Design-space combinations", "value": f"{SWEEP.get('total_evaluated', 0):,}",
             "sub": "old wording: 6 regimes × 72 comps × 125 switches × 288 op-amps. Actual: 7 res. × 9 C_u × 5 arch × (48 comps × 18 switches × 4 op-amps per supply × 2 supplies) × 6 regimes"},
            {"label": "Lowest power (old site, live value)", "value": si(pub_min_p["power_uw"] * 1e-6, "W", 3),
             "sub": f"`{pub_min_p['card_id']}` — from the 28 pJ placeholder; the static header said 26.1 nW = 21.4 nW P_dyn + 4.66 nW P_leak"},
            {"label": "Best Walden FoM (old site, live value)", "value": f"{pub_best_fom['fom_walden_fj']:.1f} fJ/step",
             "sub": f"`{pub_best_fom['card_id']}` (static header: 8.7 fJ/step)"},
            {"label": "Peak speed (2.0 GS/s TI ready)", "value": si(peak["fs_msps"] * 1e6, "S/s", 4),
             "sub": "5×/6×/8× TI → 2.0 GS/s · loop-unrolled domino SAR"},
        ]},
        {"type": "stats", "title": "The same figures from the hub's partial post-PEX results", "items": [
            {"label": "Lowest 1 kS/s power (SPICE energy)", "value": si(hub_p[hub_min_1k], "W", 3),
             "sub": f"`{hub_min_1k}`: P_dyn {si(u1k['p_dyn'], 'W', 3)} + P_leak {si(u1k['p_leak_eff'], 'W', 3)}"},
            {"label": "Lowest power overall", "value": si(hub_p[hub_min_p], "W", 3), "sub": f"`{hub_min_p}`"},
            {"label": "Best Walden FoM", "value": f"{hub_f[hub_best_f]:.1f} fJ/step", "sub": f"`{hub_best_f}`"},
            {"label": "DRC / LVS clean", "value": f"{INDEX.get('drc_pass_count')} / {INDEX.get('lvs_pass_count')}", "sub": "KLayout, full chip"},
            {"label": "Feasible DSE points", "value": f"{SWEEP.get('feasible_count', 0):,}", "sub": f"of {SWEEP.get('total_evaluated', 0):,} evaluated (analytical sweep)"},
            {"label": "Sibling library sizes", "value": f"{lib.get('sa_comparators')} / {lib.get('switches')} / {lib.get('opamps')}",
             "sub": "comparators / switches / op-amps (sweep.json library_counts); the sweep used all comparators but only 18 switches and 4 op-amps per supply"},
        ]},
        md("""### What was simulated (stage mapping)

| item | how it was obtained | hub stage |
|---|---|---|
| ENOB, SNDR, SFDR, THD, SNR, total power, energy, FoMs | transistor-level SPICE (ngspice) with the Magic-extracted CDAC and the sibling repos' extracted switch / comparator / VCM op-amp; SAR logic as standard-cell schematic; no top-level routing extraction | **Partial post-PEX** (`results.partial`) |
| "Pre-layout" and "full-chip PEX" columns of the old site | post value + fixed offsets (pre: +0.12–0.16 dB SNDR, ×0.96–0.97 power; full: −0.18 dB SNDR, ×1.018 power) | model estimate — shown labelled on each design page, never as a result |
| DNL / INL | static analysis of the extracted CDAC step weights | partial |
| injected-variance switching-failure check (5 corners) | SPICE on the extracted CDAC with injected capacitor variance | partial (drives *robust*) |
| PVT corners | TT on every card; other corners on 6 anchor cards and scaled / multiplied for the rest; PASS flag hard-coded | table on each design page |
| settling / dynamic-offset / bridge sweeps, mismatch MC, noise budget | behavioural Python models | labelled charts on each design page |
| design-space exploration (13,063,680 points) | analytical sweep model (sargen/sweep.py); docs keep 2,600 sampled + 140 Pareto points | *Design space* page |
"""),
        note("""- **ULP energy placeholders:** all 36 sleep-gated cards publish E_dyn = 28 / 110 pJ and P_leak = 5.2 / 16 nW (1.8 / 3.3 V) at top level — placeholders. The simulated energy and sleep leakage are stored under `waveform_post.tot`; the hub recomputes power and FoMs from them with the repo's own formula and shows both on every ULP page.
- **Failed FFTs:** `sar_12b_3v3_ulp100k_mom` and `sar_12b_3v3_ulp1m_mom` (ngspice error in the majority-voter netlist); the old site showed fallback values. The hub reports no dynamic metrics for them.
- **Incomplete conversions:** `sar_10b_1v8_uhs100m_mim` did not reach EOC on every FFT cycle (ENOB 7.77 b).
- **Shared records:** ULP 1 kS/s and 100 kS/s cards (and some 1 MS/s ones) reuse the same ULP-core transient; the input-driver co-simulation is shared by the 18 cards of each (resolution, supply); several FFT code records are duplicated between cards. Each design page says so.
- **Variance record:** 48 cards (split-monotonic and ULP) carry the variance record of the `*_uhs` CDAC macro instead of their own; the hub uses each card's own macro.
- **PVT:** the corner PASS flag is hard-coded true and only 6 anchor cards simulate non-TT corners, so the hub does not report a PVT pass count.
- **Annotated gm/Id "simulated" values** are target × fixed factors, not simulation outputs.
- **Loop-unrolled cards (12):** the published FFT codes are synthesized by the generator's calibration fit (an exact fit to an ideal sine plus a hard-coded HD2/HD3 term) and the 3-cycle table is gain/offset-fitted. The hub reports no ENOB/SNDR/FoM for them; *ENOB (raw codes)* gives the uncalibrated SPICE result (3.4–8 b).
- **Noise model in ENOB:** SNDR/ENOB/FoMs add an analytical thermal-noise term (kT/C + comparator noise) to the 16/32-point SPICE FFT; short FFTs can give ENOB at or above N (±0.3 b). The SPICE-only values of the high-speed cards are listed in their parameters. The old site's SNR column is not ported.
- **CDAC group weights:** the old site paired post-PEX step weights with capacitor groups by row index; the hub matches them by step.""", "warn", "Data caveats."),
    ],
}
dump(OUT / "pages" / "overview.json", overview)

# ----------------------------------------------------------------------------- page: design space
COLS = ["source", "nbits", "vdd", "supply", "arch", "tier", "cap", "cu", "comp", "sw", "opa", "enob", "sndr", "fs", "power",
        "p_dyn", "p_leak", "e_dyn", "fom_w", "fom_s", "area", "design", "delivered", "label", "stage", "group"]
colsd = {k: [] for k in COLS}


def add_pt(src, p, group=None):
    colsd["source"].append(src)
    colsd["stage"].append("partial" if src == "delivered" else None)
    colsd["group"].append(group)
    colsd["nbits"].append(f"{p['nbits']}-bit")
    colsd["vdd"].append(p["vdd"])
    colsd["supply"].append(f"{p['vdd']} V")
    colsd["arch"].append(p["arch"])
    colsd["tier"].append(p["fs_tier"])
    colsd["cap"].append(p["cap_type"])
    colsd["cu"].append(R(mul(p.get("cu_ff"), 1e-15), 4))
    colsd["comp"].append(p.get("comp"))
    colsd["sw"].append(p.get("sw"))
    colsd["opa"].append(p.get("opa"))
    colsd["enob"].append(R(p.get("enob"), 4))
    colsd["sndr"].append(R(p.get("sndr_db"), 4))
    colsd["fs"].append(R(p["fs_msps"] * 1e6, 5))
    colsd["power"].append(R(mul(p.get("power_uw"), 1e-6), 4))
    colsd["p_dyn"].append(R(mul(p.get("p_dyn_uw"), 1e-6), 4))
    colsd["p_leak"].append(R(mul(p.get("p_leak_nw"), 1e-9), 4))
    colsd["e_dyn"].append(R(mul(p.get("e_dyn_pj"), 1e-12), 4))
    colsd["fom_w"].append(R(p.get("fom_walden_fj"), 4))
    colsd["fom_s"].append(R(p.get("fom_schreier_db"), 5))
    colsd["area"].append(R(mul(p.get("area_mm2"), 1e6), 4))
    colsd["design"].append(p.get("_design"))
    colsd["delivered"].append(bool(p.get("_design")))
    colsd["label"].append(p.get("_label") or f"{SWEEP_ARCH.get(p['arch'], p['arch'])} · {p.get('comp')} · {p.get('sw')} · {p.get('opa')}")


for p in SWEEP.get("cloud_points") or []:
    add_pt("cloud", p)
for g in sorted(SWEEP.get("pareto_by_group") or {}):
    for p in SWEEP["pareto_by_group"][g]:
        add_pt("pareto", p, g)
for c in order:
    cid = c["card_id"]
    h = hub_vals[cid]
    d = DATA[cid]
    u = ulp_power(c, d) if c.get("sleep_gated") else None
    p = {"nbits": c["nbits"], "vdd": c["vdd"], "arch": c["arch"], "fs_tier": c["fs_tier"], "cap_type": c["cap_type"],
         "cu_ff": (d.get("cdac_pex") or {}).get("cu_ext_ff"), "comp": c["comp_key"], "sw": c["sw_key"], "opa": c["opa_vcm_key"],
         "enob": h["enob"], "sndr_db": h["sndr"], "fs_msps": c["fs_msps"], "power_uw": mul(h["power"], 1e6),
         "p_dyn_uw": mul(u["p_dyn"], 1e6) if u else c.get("p_dyn_uw"), "p_leak_nw": mul(u["leak"], 1e9) if u else c.get("p_leak_nw"),
         "e_dyn_pj": mul(u["e_dyn"], 1e12) if u else c.get("e_dyn_pj"), "fom_walden_fj": h["fom_w"], "fom_schreier_db": h["fom_s"],
         "area_mm2": c.get("area_mm2"), "_design": cid, "_label": cid}
    add_pt("delivered", p)
dump(OUT / "data" / "dse.json", {"columns": colsd})

TIER_ORDER = [t for t, _ in TIERS]
ARCH_ALL = {**SWEEP_ARCH, **ARCH_LABEL}
dims = [
    {"key": "enob", "label": "ENOB", "unit": "bit", "better": "high"},
    {"key": "fom_w", "label": "Walden FoM", "unit": "fJ/step", "log": True, "better": "low"},
    {"key": "fs", "label": "Sample rate", "unit": "S/s", "si": True, "log": True, "better": "high"},
    {"key": "power", "label": "Total power", "unit": "W", "si": True, "log": True, "better": "low"},
    {"key": "p_dyn", "label": "Dynamic power", "unit": "W", "si": True, "log": True, "better": "low"},
    {"key": "p_leak", "label": "Standby leakage", "unit": "W", "si": True, "log": True, "better": "low"},
    {"key": "e_dyn", "label": "Dynamic energy / conv.", "unit": "J", "si": True, "log": True, "better": "low"},
    {"key": "sndr", "label": "SNDR", "unit": "dB", "better": "high"},
    {"key": "fom_s", "label": "Schreier FoM", "unit": "dB", "better": "high"},
    {"key": "cu", "label": "Unit capacitor C_u", "unit": "F", "si": True, "log": True},
    {"key": "area", "label": "Area", "unit": "µm²", "log": True, "better": "low"},
    {"key": "source", "label": "Point set", "type": "cat", "labels": {"cloud": "Sampled sweep cloud", "pareto": "Pareto fronts (per group)", "delivered": "Delivered cards"}, "order": ["cloud", "pareto", "delivered"]},
    {"key": "nbits", "label": "Resolution", "type": "cat", "order": ["8-bit", "9-bit", "10-bit", "12-bit"]},
    {"key": "supply", "label": "Supply", "type": "cat", "order": ["1.8 V", "3.3 V"]},
    {"key": "tier", "label": "Sample-rate regime", "type": "cat", "labels": TIER_LABEL, "order": TIER_ORDER},
    {"key": "arch", "label": "Architecture", "type": "cat", "labels": ARCH_ALL, "order": list(dict.fromkeys(list(SWEEP_ARCH) + [a for a, _ in ARCHS]))},
    {"key": "cap", "label": "CDAC capacitor", "type": "cat", "labels": CAP_LABEL, "order": ["mom", "mim"]},
    {"key": "comp", "label": "Comparator", "type": "cat"},
    {"key": "sw", "label": "S/H switch", "type": "cat"},
    {"key": "opa", "label": "Op-amp", "type": "cat"},
    {"key": "group", "label": "Pareto group (bits_supply_regime)", "type": "cat"},
]


def scat(name, xs, ys, ids=None, color=None, size=5, opacity=0.8, text=None):
    t = {"type": "scatter", "mode": "markers", "name": name, "x": xs, "y": ys, "marker": {"size": size, "opacity": opacity}}
    if color:
        t["marker"]["color"] = color
    if ids:
        t["customdata"] = ids
    if text:
        t["text"] = text
        t["hovertemplate"] = "%{text}<extra></extra>"
    return t


cl = SWEEP.get("cloud_points") or []
deliv = [(c["card_id"], hub_vals[c["card_id"]]) for c in order]
missing_enob = [cid for cid, h in deliv if h.get("enob") is None]
miss_txt = ("Not plotted (no hub ENOB): the 12 loop-unrolled cards (synthesized FFT codes) and the two failed-FFT cards "
            "`sar_12b_3v3_ulp100k_mom`, `sar_12b_3v3_ulp1m_mom`.")
VDDS = (1.8, 3.3)


def leak_txt(cid):
    c = CARDS[cid]
    if c.get("sleep_gated"):
        u = ulp_power(c, DATA[cid])
        return f"P_leak {si(u['leak'] if u else None, 'W')} (SPICE sleep)"
    return f"P_leak {si(mul(c.get('p_leak_nw'), 1e-9), 'W')} (published, model)"


def with_meta(t, **m):
    t["meta"] = m
    return t


ch1 = []
for v in VDDS:
    pts = [p for p in cl if p["vdd"] == v]
    ch1.append(with_meta(scat(f"sampled sweep cloud, {v} V (8-bit)", [p["enob"] for p in pts], [p["fom_walden_fj"] for p in pts], color="#94a3b8", size=4, opacity=0.45),
                         vdd=v))
    ch1[-1]["legendgroup"] = "cloud"
for nb in (8, 10, 12):
    for v in VDDS:
        sel = [(cid, h) for cid, h in deliv if CARDS[cid]["nbits"] == nb and CARDS[cid]["vdd"] == v and h.get("enob") is not None and h.get("fom_w")]
        t = with_meta(scat(f"{nb}-bit delivered ({v} V)", [h["enob"] for _, h in sel], [h["fom_w"] for _, h in sel], [cid for cid, _ in sel],
                           NB_COLOR[nb], 9, 1, [f"{cid}<br>ENOB {h['enob']} b, FoM {h['fom_w']} fJ/step" for cid, h in sel]), vdd=v, stage="partial")
        t["legendgroup"] = f"nb{nb}"
        ch1.append(t)
pub = [(c["card_id"], c) for c in order]
for v in VDDS:
    sel = [(cid, c) for cid, c in pub if c["vdd"] == v]
    t = with_meta(scat(f"as published on the old site ({v} V)", [c["enob_post"] for _, c in sel], [c["fom_walden_fj"] for _, c in sel],
                       [cid for cid, _ in sel], GRAY, 7, 0.9, [f"{cid}<br>published ENOB {c['enob_post']} b, FoM {c['fom_walden_fj']} fJ/step" for cid, c in sel]), vdd=v)
    t["marker"]["symbol"] = "diamond-open"
    t["visible"] = "legendonly"
    t["legendgroup"] = "pub"
    ch1.append(t)
grp2 = [("Loop-unrolled (2 GS/s TI)", lambda c: c["fs_tier"] == "lu2g", GREEN), ("UHS >100 MS/s", lambda c: c["fs_tier"] == "uhs100m", AMBER),
        ("other, 1.8 V", lambda c: c["fs_tier"] not in ("lu2g", "uhs100m") and c["vdd"] < 2.5, CYAN),
        ("other, 3.3 V", lambda c: c["fs_tier"] not in ("lu2g", "uhs100m") and c["vdd"] >= 2.5, PINK)]
ch2 = []
for v in VDDS:
    pts = [p for p in cl if p["vdd"] == v]
    t = with_meta(scat(f"sampled sweep cloud, {v} V", [p["fs_msps"] * 1e6 for p in pts], [R(p["power_uw"] * 1e-6, 4) for p in pts], color="#94a3b8", size=4, opacity=0.45), vdd=v)
    t["legendgroup"] = "cloud"
    ch2.append(t)
for name, fn, colr in grp2:
    for v in VDDS:
        sel = [(cid, h) for cid, h in deliv if fn(CARDS[cid]) and CARDS[cid]["vdd"] == v and h.get("power")]
        if not sel:
            continue
        t = with_meta(scat(name if "V" in name else f"{name} ({v} V)", [h["fs"] for _, h in sel], [h["power"] for _, h in sel], [cid for cid, _ in sel], colr, 9, 1,
                           [f"{cid}<br>fs {si(h['fs'], 'S/s')}, P {si(h['power'], 'W')}, {leak_txt(cid)}" for cid, h in sel]), vdd=v, stage="partial")
        t["legendgroup"] = name
        ch2.append(t)
for v in VDDS:
    sel = [(cid, c) for cid, c in pub if c["vdd"] == v]
    t = with_meta(scat(f"as published on the old site ({v} V)", [c["fs_msps"] * 1e6 for _, c in sel], [R(c["power_uw"] * 1e-6, 4) for _, c in sel],
                       [cid for cid, _ in sel], GRAY, 7, 0.9, [f"{cid}<br>published P {si(c['power_uw'] * 1e-6, 'W')}, P_leak {si(mul(c.get('p_leak_nw'), 1e-9), 'W')}" for cid, c in sel]), vdd=v)
    t["marker"]["symbol"] = "diamond-open"
    t["visible"] = "legendonly"
    t["legendgroup"] = "pub"
    ch2.append(t)
rs = SWEEP.get("rate_summary") or {}
asum = SWEEP.get("arch_summary") or {}
pareto_rows = []
for g in sorted(SWEEP.get("pareto_by_group") or {}):
    for p in SWEEP["pareto_by_group"][g]:
        pareto_rows.append([g, p["nbits"], p["vdd"], p["arch"], p["fs_tier"], p["cap_type"].upper(),
                            R(mul(p.get("cu_ff"), 1e-15)), p.get("comp"), p.get("sw"), p.get("opa"), p.get("enob"), p.get("sndr_db"),
                            R(p["fs_msps"] * 1e6), R(mul(p.get("power_uw"), 1e-6)), R(mul(p.get("p_dyn_uw"), 1e-6)), R(mul(p.get("p_leak_nw"), 1e-9)),
                            R(mul(p.get("e_dyn_pj"), 1e-12)), p.get("fom_walden_fj"), p.get("fom_schreier_db"), p.get("area_mm2")])
hs_feas = (rs.get("hs") or {}).get("count_feasible")


def mm(a, b, f):
    return f"{f(a)} / {f(b)}"


explore = {
    "intro": ("Systematic design-space exploration of the generator (sargen/sweep.py), an **analytical model**: "
              f"**{SWEEP.get('total_evaluated', 0):,} combinations evaluated** = 7 resolutions ({', '.join(map(str, SWEEP.get('resolutions_swept', [])))} b) × "
              "9 unit capacitors (5 MOM + 4 MIM) × 5 architectures "
              f"({', '.join('`' + a + '`' for a in SWEEP.get('architectures_swept', []))}) × per supply (1.8 / 3.3 V) 48 comparators × 18 switches × "
              f"4 op-amps × 6 rate regimes ({', '.join('`' + a + '`' for a in SWEEP.get('rate_regimes_swept', []))}). "
              f"**{SWEEP.get('feasible_count', 0):,} are feasible** (model ENOB ≥ N − 1.8 b within the regime's timing). The sibling libraries hold "
              f"{lib.get('sa_comparators')} comparators, {lib.get('switches')} switches and {lib.get('opamps')} op-amps; the sweep used all comparators "
              "but only the first 18 switches and 4 op-amps per supply.\n\n"
              "**The 13.1 M points are not in docs/.** docs keep: a cloud of "
              f"{len(cl):,} feasible points — a 0.5 % random draw truncated at 2,600 in loop order, so it covers only 8-bit designs (1.8 V MOM/MIM and "
              f"3.3 V MOM with C_u ≤ 2.2 fF); {len(pareto_rows)} Pareto-front points (ENOB-max / FoM-min per resolution × supply × regime, 36 groups); "
              "and the summary statistics below. The model's maximum ENOB is 8.97 b, so it finds **no feasible point at 11–14 b** and the 10/12-bit "
              "delivered cards have no model counterpart. The old site labelled its grey cloud '13,063,680 swept designs'; it is this 2,600-point sample."),
    "blocks": [
        {"type": "explorer", "title": "Design-space explorer (sampled cloud + Pareto fronts + 108 delivered cards)", "src": "hub/data/dse.json",
         "dims": dims, "x": "enob", "y": "fom_w", "color": "source", "symbol": "",
         "filters": ["source", "nbits", "supply", "tier", "arch", "cap", "enob", "power"],
         "highlight": "delivered", "highlight_label": "Delivered cards (click to open)", "design_key": "design", "label_key": "label",
         "hover": ["source", "nbits", "supply", "arch", "tier", "cap", "comp", "sw", "opa", "cu", "fs", "power", "p_leak", "sndr", "fom_s", "e_dyn", "area", "group"],
         "presets": [
             {"label": "Walden FoM vs ENOB (old chart 1)", "x": "enob", "y": "fom_w", "color": "nbits", "logy": True, "pareto": False},
             {"label": "Power vs sample rate (old chart 2)", "x": "fs", "y": "power", "color": "tier", "logx": True, "logy": True, "pareto": False},
             {"label": "Pareto: FoM vs ENOB", "x": "enob", "y": "fom_w", "color": "tier", "logy": True, "pareto": True},
             {"label": "Sweep Pareto fronts (per group)", "x": "enob", "y": "fom_w", "color": "group", "logy": True, "pareto": False, "show": {"source": ["pareto"]}},
             {"label": "Schreier FoM vs sample rate", "x": "fs", "y": "fom_s", "color": "arch", "logx": True, "pareto": False},
             {"label": "Leakage vs sample rate", "x": "fs", "y": "p_leak", "color": "tier", "logx": True, "logy": True, "pareto": False},
             {"label": "Energy vs C_u", "x": "cu", "y": "e_dyn", "color": "cap", "logx": True, "logy": True, "pareto": False},
             {"label": "Per regime", "x": "enob", "y": "fom_w", "color": "arch", "facet": "tier", "logy": True, "pareto": False},
         ],
         "caption": "Delivered cards use the hub's partial post-PEX values (ULP power recomputed from SPICE energy) and follow the global stage option; "
                    + miss_txt + " Their standby-leakage values are the published ones (model) except for ULP cards (SPICE sleep leakage). "
                    "Cloud and Pareto points are analytical-model estimates and show at every stage."},
        section(None, [
            chart("Walden FoM vs. ENOB — old-site layout, hub partial post-PEX values", ch1, "ENOB (bits)", "Walden FoM (fJ/conv-step)",
                  {"yaxis": {"type": "log"}}, height=440, link_designs=True,
                  caption="Grey: sampled sweep cloud (the old site drew its first 900 points). Coloured: delivered cards (cyan 8 b, green 10 b, amber 12 b) — "
                          "click to open. " + miss_txt + " The hidden trace *as published on the old site* (click its legend entry) shows the old positions "
                          "(ULP placeholders, fallback and synthesized values)."),
            chart("Total power vs. sample rate (log-log) — old-site layout, hub values", ch2, "Sample rate (S/s)", "Total supply power (W)",
                  {"xaxis": {"type": "log", "exponentformat": "SI"}, "yaxis": {"type": "log", "exponentformat": "SI"}}, height=440, link_designs=True,
                  caption="1 kS/s → 400 MS/s single channel (2.0 GS/s TI). Grey: sampled cloud (old site: first 1,200). Delivered cards coloured by regime / "
                          "supply; hover shows P_leak. The hidden *as published* trace shows the old positions (35 ULP cards moved: placeholder energy)."),
        ], cols=2),
        table("Multi-rate sample-regime exploration (feasible points per regime)",
              [col("r", "Sample-rate regime", type_="text", wrap=True), col("n", "Feasible designs", digits=0),
               col("e", "ENOB P90 / max", type_="text"), col("p", "Total power min / median", type_="text"),
               col("pd", "P_dyn median", "W", True), col("ed", "E_dyn min / median", type_="text"),
               col("l", "Standby P_leak min / median", type_="text"), col("f", "Walden FoM best / P10", type_="text"),
               col("fs9", "Schreier FoM P90", "dB", digits=4)],
              [[r.get("label", k), r.get("count_feasible"), mm(r.get("enob_p90"), r.get("enob_max"), lambda x: fx(x, "b")),
                mm(mul(r.get("power_min_uw"), 1e-6), mul(r.get("power_median_uw"), 1e-6), lambda x: si(x, "W", 3)),
                mul(r.get("p_dyn_median_uw"), 1e-6), mm(mul(r.get("e_dyn_min_pj"), 1e-12), mul(r.get("e_dyn_median_pj"), 1e-12), lambda x: si(x, "J", 3)),
                mm(mul(r.get("p_leak_min_nw"), 1e-9), mul(r.get("p_leak_median_nw"), 1e-9), lambda x: si(x, "W", 3)),
                mm(r.get("fom_walden_min_fj"), r.get("fom_walden_p10_fj"), lambda x: fx(x, "fJ")), r.get("fom_schreier_p90_db")] for k, r in rs.items()],
              search=False),
        table(f"Architecture trade-off summary — 3.125–20 MS/s high-speed regime only ({hs_feas:,} feasible of {SWEEP.get('feasible_count', 0):,})" if hs_feas else
              "Architecture trade-off summary (high-speed regime)",
              [col("a", "Architecture", type_="text"), col("al", "Description", type_="text", wrap=True), col("n", "Feasible designs", digits=0),
               col("e9", "ENOB P90", "b", digits=3), col("em", "ENOB max", "b", digits=3), col("fmin", "Best Walden FoM", "fJ/step", digits=3),
               col("f10", "Walden FoM P10", "fJ/step", digits=3), col("fs9", "Schreier FoM P90", "dB", digits=4),
               col("pm", "Median power", "W", True), col("fm", "Median f_s", "S/s", True)],
              [[k, SWEEP_ARCH.get(k, k), a.get("count_feasible"), a.get("enob_p90"), a.get("enob_max"), a.get("fom_walden_min_fj"), a.get("fom_walden_p10_fj"),
                a.get("fom_schreier_p90_db"), mul(a.get("power_median_uw"), 1e-6), mul(a.get("fs_median_msps"), 1e6)] for k, a in asum.items()], search=False,
              caption="sweep.py accumulates `arch_summary` only for points in the `hs` regime (the old site titled it 'across 13,063,680 evaluated "
                      "combinations'); the feasible counts add up to the high-speed regime's count."),
        table("Pareto-front points per group (sweep.json pareto_by_group)",
              [col("g", "Group", type_="text"), col("nb", "Bits", digits=2), col("vdd", "V_DD", "V", digits=2), col("a", "Arch", type_="text"),
               col("t", "Regime", type_="text"), col("c", "Cap", type_="text"), col("cu", "C_u", "F", True), col("cmp", "Comparator", type_="text"),
               col("sw", "Switch", type_="text"), col("op", "Op-amp", type_="text"), col("e", "ENOB", "b", digits=3), col("s", "SNDR", "dB", digits=4),
               col("fs", "f_s", "S/s", True), col("p", "Power", "W", True), col("pd", "P_dyn", "W", True), col("pl", "P_leak", "W", True),
               col("ed", "E_dyn", "J", True), col("fw", "Walden FoM", "fJ/step", digits=3), col("fsc", "Schreier FoM", "dB", digits=4),
               col("ar", "Area", "mm²", digits=3)],
              pareto_rows, page_size=200, caption="Not displayed by the old site (it is in docs/data/sweep.json). Follows the global supply filter; "
                                                  "the explorer preset *Sweep Pareto fronts* plots these points per group."),
    ],
}
dump(OUT / "pages" / "explore.json", explore)

# ----------------------------------------------------------------------------- page: resilience
mac_rows = []
for k in sorted(MACROS, key=lambda k: (MACROS[k]["nbits"], MACROS[k]["cap_type"], MACROS[k]["scheme"])):
    m = MACROS[k]
    src = PV_BY_MACRO.get(k, (None, {}))[0]
    users = sorted(cid for cid, c in CARDS.items() if c["cdac_key"] == k)
    mac_rows.append([f"`{k}`", m["nbits"], m["cap_type"].upper(), m["scheme"].upper(), mul(m.get("cu_ff"), 1e-15), mul(m.get("cb_ff"), 1e-15),
                     m.get("nom_enob"), m.get("worst_redundant_enob"), {"v": m.get("worst_binary_enob"), "s": "bad"},
                     m.get("max_redundant_err_lsb"), {"v": m.get("max_binary_err_lsb"), "s": "bad"},
                     {"v": "5/5 PASS (0 switching failures)" if m.get("all_redundant_corners_pass") else "CHECK", "s": "good" if m.get("all_redundant_corners_pass") else "bad"},
                     len(users), f"[`{src}`](#/sar/{src}?t.pane=3)" if src else "—"])
mac_tabs = []
for nb in (8, 10, 12):
    tr_ = []
    for i, k in enumerate(sorted(x for x in PV_BY_MACRO if MACROS.get(x, {}).get("nbits") == nb)):
        vs = PV_BY_MACRO[k][1].get("variance_sweep") or {}
        colr = [BLUE, GREEN, AMBER, PURPLE, PINK, CYAN, RED, GRAY][i % 8]
        tr_.append(line(f"{k} redundant", vs.get("sigma_mult"), vs.get("enob_redundant_cal") or vs.get("enob_redundant"), colr, width=2.4, legendgroup=k))
        tr_.append(line(f"{k} binary", vs.get("sigma_mult"), vs.get("enob_binary_uncal") or vs.get("enob_binary"), colr, "dash", 1.6, legendgroup=k))
    mac_tabs.append({"label": f"{nb}-bit macros", "blocks": [chart(f"{nb}-bit extracted CDAC macros: ENOB vs injected variance (SPICE)", tr_,
                     "Injected variance multiplier (× σ_Pelgrom + ΔC_bridge)", "Post-PEX ENOB (bits)", height=420,
                     caption="Solid = redundant weights (calibrated), dashed = binary weights on the same extracted array.")]})
macro_detail = []
for k in sorted(PV_BY_MACRO, key=lambda k: (MACROS.get(k, {}).get("nbits", 0), k)):
    src, pv = PV_BY_MACRO[k]
    rel = f"data/macro_{k}.json"
    corners = pv.get("corners") or []
    figs = {"data": [line(co.get("label"), list(range(len(co.get("trace_res_lsb") or []))), RL(co.get("trace_res_lsb"), 5), [GRAY, BLUE, GREEN, AMBER, PURPLE][i % 5],
                          "dash" if i == 0 else None, mode="lines+markers") for i, co in enumerate(corners)],
            "layout": {"xaxis": {"title": {"text": "Bit-cycling step index j"}}, "yaxis": {"title": {"text": "Residue V_diff (LSB)"}}}}
    dump(OUT / rel, figs)
    macro_detail.append({"label": k, "blocks": [
        chart(f"`{k}`: 5-corner bit-cycling residue (SPICE)", None, height=360, src=f"hub/{rel}",
              caption=f"Record simulated with card [`{src}`](#/sar/{src}?t.pane=3); the full corner table is on that card's page (tab 4)."),
        table(f"`{k}`: corner summary", [col("id", "Corner", type_="text"), col("l", "Perturbation", type_="text"), col("re", "Redundant ENOB", "b", digits=4),
                                         col("be", "Binary ENOB", "b", digits=4), col("rerr", "Max err. red.", "LSB", digits=3), col("berr", "Max err. bin.", "LSB", digits=4),
                                         col("rf", "Red. switching failure", type_="status"), col("bf", "Bin. switching failure", type_="status")],
              [[co.get("corner_id"), co.get("label"), co.get("redundant_enob"), co.get("binary_enob"), co.get("max_code_err_lsb"), co.get("binary_max_err_lsb"),
                {"v": bool(co.get("switching_failure")), "s": "bad" if co.get("switching_failure") else "good"},
                {"v": bool(co.get("binary_switching_failure")), "s": "bad" if co.get("binary_switching_failure") else "good"}] for co in corners],
              search=False, csv=False)]})
for b in macro_detail:     # chart with src: drop the inline data key
    b["blocks"][0].pop("data", None)


def beh_groups(key):
    """distinct behavioural sweep results (shared across cards) with a readable label"""
    g = defaultdict(list)
    for cid in sorted(DATA):
        rr = (DATA[cid].get("resilience") or {}).get(key) or {}
        g[json.dumps(rr, sort_keys=True)].append(cid)
    out = []
    for kk, cids in sorted(g.items(), key=lambda kv_: (CARDS[kv_[1][0]]["nbits"], kv_[1][0])):
        cs = [CARDS[x] for x in cids]
        caps = "/".join(sorted({c["cap_type"].upper() for c in cs}))
        mv = {c["lsb_votes"] > 1 for c in cs}
        lab = f"{cs[0]['nbits']}-bit {caps}{' · 3× vote' if mv == {True} else ''} ({len(cids)} cards)"
        out.append((lab, json.loads(kk), cs[0]["nbits"]))
    return out


sg = beh_groups("settling_sweep")
dg = beh_groups("dyn_offset_sweep")
bg = beh_groups("bridge_variation_sweep")
tau = [1.2, 1.5, 1.8, 2.2, 2.6, 3.0, 3.5, 4.2, 5.0, 6.5, 8.0]
dynx = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.5, 6.0, 8.0]
sigx = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
HC = "Curves hard-coded in the old site's JavaScript (assets/app.js) — illustrative, not traceable to a dataset in docs/. Reproduced for completeness; the data-driven chart next to it uses the per-card records."
resil = {
    "intro": (f"Systematic post-PEX SPICE verification of **all {n_mac} extracted CDAC macros** with artificially injected capacitor variance "
              "(5 corners: nominal, MSB major-carry +3.5σ, upper redundant pair ±4σ, bridge −6 % + ±3.5σ, lower redundant pair & P/N skew ±4.5σ), "
              f"comparing the sub-binary redundant weights with a binary CDAC on the same extracted array. **{n_mac_pass} / {n_mac} macros: 0 redundant "
              "switching failures.** Settling, comparator-offset and bridge-variation sweeps are behavioural-model results."),
    "blocks": [
        table(f"Post-PEX artificially injected CDAC variance & switching-failure verification (all {n_mac} extracted macros)",
              [col("k", "Extracted CDAC macro", type_="text", md=True), col("nb", "Bits", digits=2), col("c", "Cap", type_="text"), col("s", "Scheme", type_="text"),
               col("cu", "Unit C_u", "F", True), col("cb", "Bridge C_B", "F", True), col("ne", "Nominal post-PEX ENOB", "b", digits=4),
               col("wr", "Worst 4σ redundant ENOB", "b", digits=4, better="high"), col("wb", "Worst binary ENOB (switching fail)", "b", digits=4),
               col("er", "Max error redundant", "LSB", digits=3), col("eb", "Max error binary", "LSB", digits=4),
               col("st", "5-corner SPICE status", type_="text", wrap=True), col("u", "Cards using it", digits=3), col("src", "Detailed record from", type_="text", md=True)],
              mac_rows, search=False,
              caption="From docs/data/index.json `postpex_variance_macros`. 48 card records in docs point at the `*_uhs` macro instead of their own; the hub "
                      "links every card to its own macro."),
        section("Post-PEX SPICE injected variance sweep — ENOB vs injected σ (redundant vs binary)", [
            chart("Old-site figure (8/10/12-bit, hard-coded)", [
                line("12-bit redundant", sigx, [11.98, 11.98, 11.97, 11.96, 11.94, 11.92, 11.89, 11.86, 11.83, 11.72, 11.55], AMBER, width=2.6),
                line("12-bit binary", sigx, [11.96, 11.42, 10.68, 9.95, 9.35, 8.92, 8.62, 8.42, 8.27, 8.15, 8.05], AMBER, "dash", 1.9),
                line("10-bit redundant", sigx, [9.99, 9.99, 9.98, 9.98, 9.97, 9.96, 9.95, 9.94, 9.93, 9.85, 9.72], GREEN, width=2.6),
                line("10-bit binary", sigx, [9.98, 9.52, 8.95, 8.48, 8.12, 7.86, 7.68, 7.55, 7.45, 7.38, 7.32], GREEN, "dash", 1.9),
                line("8-bit redundant", sigx, [7.99, 7.99, 7.99, 7.98, 7.97, 7.96, 7.95, 7.93, 7.91, 7.85, 7.76], CYAN, width=2.6),
                line("8-bit binary", sigx, [7.98, 7.62, 7.25, 6.96, 6.76, 6.62, 6.53, 6.46, 6.41, 6.37, 6.34], CYAN, "dash", 1.9)],
                "Injected variance multiplier (× σ_Pelgrom + ΔC_bridge)", "Post-PEX ENOB (bits)", height=380, caption=HC),
            {"type": "tabs", "id": "mbits", "title": "Per-macro SPICE data (from the card records)", "tabs": mac_tabs},
        ], cols=2),
        section("Post-PEX SPICE 5-corner bit-cycling residue trajectory V(top_p) − V(top_n)", [
            chart("Old-site figure (12-bit, hard-coded)", [
                line("Nominal post-PEX (0σ)", list(range(15)), [450.5, -573.4, -61.5, 194.6, -61.5, 66.5, 2.5, -29.5, 2.5, -13.5, 2.5, -5.5, -1.5, 0.5, -0.5], GRAY, "dash", 1.9),
                line("+3.5σ MSB split skew (v1)", list(range(15)), [450.5, -589.2, -77.3, 178.8, -77.3, 50.7, -13.3, 18.7, -13.3, 2.7, -5.3, 2.7, -1.3, 0.7, -0.3], BLUE, width=2.5),
                line("+4.0σ redundancy stress (v2)", list(range(15)), [450.5, -568.0, -56.1, 208.4, -47.7, 80.3, 16.3, -15.7, 16.3, 0.3, -7.7, 0.3, -3.7, -1.7, -0.7], GREEN, width=2.5),
                line("−6 % bridge + 3σ group skew (v3)", list(range(15)), [450.5, -576.1, -64.2, 191.9, -64.2, 63.8, 3.6, -26.5, 3.6, -11.4, 3.6, -3.9, -0.2, 1.7, -0.2], AMBER, width=2.3)],
                "Bit-cycling step index j", "Residue V_diff (LSB)", height=380, caption=HC),
            {"type": "tabs", "id": "macro", "style": "select", "label": "Macro", "title": "Per-macro SPICE residue trajectories", "tabs": macro_detail},
        ]),
        table("Sub-binary redundant weight sequences & variation error-correction mechanism",
              [col("r", "Target raw resolution", type_="text"), col("k", "Switched steps (K_sw)", type_="text"), col("w", "Redundant bit-weight sequence", type_="text", md=True, wrap=True),
               col("d", "Duplicate redundant positions", type_="text"), col("s", "Total span", "LSB", digits=5), col("b", "Bridge-split ratio", type_="text", wrap=True),
               col("sp", "Settling speed-up vs binary", type_="text")],
              [["8-bit redundant", "10 + 1 term", "`[128, 64, 32, 32, 16, 8, 4, 4, 2, 1]`", "32, 4", 292, "MSB÷8 (Cu×18) + LSB (Cu×16)", "1.67× faster"],
               ["10-bit redundant", "13 + 1 term", "`[512, 256, 128, 128, 64, 32, 16, 16, 8, 4, 4, 2, 1]`", "128, 16, 4", 1172, "MSB÷16 (Cu×36) + LSB (Cu×20)", "1.75× faster"],
               ["12-bit redundant", "15 + 1 term", "`[2048, 1024, 512, 512, 256, 128, 64, 64, 32, 16, 8, 8, 4, 2, 1]`", "512, 64, 8", 4684, "MSB÷32 (Cu×72) + LSB (Cu×24)", "1.83× faster"]],
              search=False, csv=False,
              caption="Static table of the old site. The per-card behavioural sweeps give speed-ups of "
                      + ", ".join(sorted({f"{CARDS[c]['nbits']}b {CARDS[c]['speedup_vs_binary']}×" for c in CARDS})) + "."),
        section("Incomplete DAC settling resilience (redundant vs binary)", [
            chart("Old-site figure (hard-coded)", [
                line("12-bit redundant", tau, [8.4, 9.8, 10.9, 11.5, 11.75, 11.82, 11.85, 11.86, 11.86, 11.86, 11.86], AMBER, width=2.5),
                line("12-bit binary", tau, [5.8, 6.9, 8.1, 9.2, 10.1, 10.8, 11.3, 11.65, 11.8, 11.85, 11.86], AMBER, "dash", 1.8),
                line("10-bit redundant", tau, [7.5, 8.8, 9.45, 9.75, 9.84, 9.86, 9.86, 9.86, 9.86, 9.86, 9.86], GREEN, width=2.5),
                line("10-bit binary", tau, [5.4, 6.5, 7.6, 8.5, 9.15, 9.55, 9.75, 9.84, 9.86, 9.86, 9.86], GREEN, "dash", 1.8),
                line("8-bit redundant", tau, [6.4, 7.4, 7.78, 7.88, 7.9, 7.9, 7.9, 7.9, 7.9, 7.9, 7.9], CYAN, width=2.5),
                line("8-bit binary", tau, [4.9, 5.9, 6.8, 7.35, 7.68, 7.82, 7.88, 7.9, 7.9, 7.9, 7.9], CYAN, "dash", 1.8)],
                "Per-bit settling window T_bit / τ_DAC", "ENOB (bits)", height=360, caption=HC),
            chart("Per-card behavioural model results (distinct records)",
                  [t for lab, rr, nb in sg for t in (line(f"{lab} redundant", rr.get("tau_ratios"), rr.get("enob_redundant"), NB_COLOR.get(nb), width=2.2, legendgroup=lab),
                                                     line(f"{lab} binary", rr.get("tau_ratios"), rr.get("enob_binary"), NB_COLOR.get(nb), "dash", 1.4, legendgroup=lab))],
                  "Per-bit settling window T_bit / τ_DAC", "ENOB (bits)", height=360,
                  caption="Behavioural Python model (sargen/cdac.py), one curve pair per distinct record stored in the card data."),
        ], cols=2),
        section("Dynamic comparator offset / kickback resilience (redundant vs binary)", [
            chart("Old-site figure (hard-coded)", [
                line("12-bit redundant", dynx, [11.85, 11.84, 11.82, 11.78, 11.72, 11.65, 11.48, 11.15, 10.75, 10.2], AMBER, width=2.5),
                line("12-bit binary", dynx, [11.85, 11.4, 10.6, 9.5, 8.7, 8.1, 7.3, 6.5, 5.9, 5.4], AMBER, "dash", 1.8),
                line("10-bit redundant", dynx, [9.86, 9.85, 9.83, 9.79, 9.73, 9.64, 9.42, 9.05, 8.6, 8.1], GREEN, width=2.5),
                line("8-bit redundant", dynx, [7.9, 7.89, 7.87, 7.82, 7.75, 7.65, 7.4, 6.95, 6.45, 5.95], CYAN, width=2.5)],
                "Dynamic comparator offset / kickback σ_dyn (LSB)", "ENOB (bits)", height=360, caption=HC),
            chart("Per-card behavioural model results (distinct records)",
                  [t for lab, rr, nb in dg for t in (line(f"{lab} redundant", rr.get("sigma_dyn_lsb"), rr.get("enob_redundant"), NB_COLOR.get(nb), width=2.2, legendgroup=lab),
                                                     line(f"{lab} binary", rr.get("sigma_dyn_lsb"), rr.get("enob_binary"), NB_COLOR.get(nb), "dash", 1.4, legendgroup=lab))],
                  "Dynamic comparator offset / kickback σ_dyn (LSB)", "ENOB (bits)", height=360,
                  caption="Behavioural model; note that these per-card records differ markedly from the old site's hard-coded curves."),
        ], cols=2),
        chart("Bridge capacitor variation resilience — per-card behavioural records (per-card view only on the old site)",
              [t for lab, rr, nb in bg for t in (line(f"{lab} redundant (calibrated)", rr.get("cb_delta_pct"), rr.get("enob_redundant_cal"), NB_COLOR.get(nb), width=2.2, legendgroup=lab),
                                                 line(f"{lab} binary (uncalibrated)", rr.get("cb_delta_pct"), rr.get("enob_binary_uncal"), NB_COLOR.get(nb), "dash", 1.4, legendgroup=lab))],
              "Bridge capacitor variation ΔC_B / C_B (%)", "ENOB (bits)", height=380),
    ],
}
dump(OUT / "pages" / "resilience.json", resil)

# ----------------------------------------------------------------------------- page: libraries
ARCH_TABLE = [
    ["`mono_red`", "Direct constant-V_GS bootstrapped S/H (`switch-gen`)", "Monotonic set-and-up redundant CDAC", "Single-cycle low-noise MI comparator",
     "50 % lower CDAC switching energy, single-sided upward bit steps"],
    ["`smono_red`", "Isolated-DNW bulk-bootstrapped Q-cancelled S/H (`switch-gen`)", "Split-capacitor constant-common-mode redundant CDAC",
     "Constant VDD/2 comparator input CM", "Eliminates signal-dependent comparator dynamic offset walk"],
    ["`vcm_opa_red`", "High-isolation bootstrapped T-switch / dummy S/H (`switch-gen`)", "Active `opa-gen` VCM-buffered merged redundant CDAC",
     "Low-impedance active reference regulation", "Fastest sub-DAC VCM recovery & lowest reference ripple"],
    ["`mvote_red`", "Active `opa-gen` unity-gain front-end buffer + bootstrapped S/H", "Split-monotonic redundant CDAC + 3-vote majority LSB",
     "Hardware 3-cycle majority voter (NAND2×3 + NAND3)", "Suppresses comparator thermal noise by 1.73× (+2.4 dB SNR)"],
    ["`smono_ulp1k` / `ulp100k` / `ulp1m`", "Low-energy bootstrapped S/H (`switch-gen`) + thick-oxide 6 V sleep clamps",
     "Split-monotonic redundant CDAC + event-driven autonomous EOC power-gating", "Subthreshold / weak-inversion comparator + 3-cycle majority LSB on 12 b",
     "Eliminates standby crowbar & bias current during sleep (`P_leak = 0.6–6.6 nW` @ 1.8 V, `26 nW` total @ 1 kS/s)"],
    ["`smono_uhs100m` (>100 MS/s)", "4× parallel wide bootstrapped S/H (`switch-gen`, 1.2–1.4 ns track) + 80 pF decap",
     "Smaller-capacitor bridge-split CDAC (`Cu = 2.03 fF` MOM / reduced-split MIM, 2.1–4.5× lower C_top) + 18–32× wide L = 0.28 µm drivers",
     "4× parallel unstarved double-tail comparator (t_clk2q ≈ 75 ps) + thin-oxide L = 0.28 µm async SAR loop",
     "Achieves 105.26–150.0 MS/s in 180 nm CMOS with τ_DAC < 18 ps and ~380 ps/bit async loop"],
    ["`lu_domino_2g` (250–400 MS/s → 2.0 GS/s TI)", "6× parallel ultra-low-R_on bootstrapped S/H (< 6 ps track RC, 0.38–0.50 ns track) + 150 pF decap",
     "Scaled smaller-capacitor UHS redundant CDAC (`Cu = 0.91–8.80 fF`, `C_top = 62–112 fF`) + direct comparator-driven tapered buffers",
     "Unrolled bank of K_tot dedicated double-tail comparators (10/13/15) + domino completion chain (nand2_val → nand2_clk)",
     "Removes comparator reset & shift-register overhead from the critical loop: 400 MS/s (8 b, 5× TI → 2 GS/s), 333.33 MS/s (10 b, 6×), 250 MS/s (12 b, 8×)"],
]
mat_rows = []
for c in order:
    cid = c["card_id"]
    h = hub_vals[cid]
    pub_bad = (not fft_ok_of(DATA[cid])) or c.get("sleep_gated") or synth_of(DATA[cid])
    mat_rows.append({"_design": cid, "card": cid, "spec": f"{c['nbits']}-bit / {c['vdd']:.1f} V", "vdd": c["vdd"],
                     "cdac": f"{c['cap_type'].upper()} ({c['scheme'].upper()})",
                     "comp": mdlink("sa", c["comp_key"]), "sw": mdlink("switch", c["sw_key"]), "opa": mdlink("opa", c["opa_vcm_key"]),
                     "opai": mdlink("opa", c["opa_in_key"]),
                     "enob_p": {"v": c["enob_post"], "s": "warn" if (not fft_ok_of(DATA[cid]) or synth_of(DATA[cid])) else None,
                                "title": "fallback value — FFT failed" if not fft_ok_of(DATA[cid]) else "synthesized by the generator's calibration fit" if synth_of(DATA[cid]) else None},
                     "fom_p": {"v": c["fom_walden_fj"], "s": "warn" if pub_bad else None, "title": "uses placeholder energy / failed FFT" if pub_bad else None},
                     "enob_h": h["enob"], "fom_h": h["fom_w"], "enob_r": h.get("enob_raw")})
reuse = []
for kind, comp_id, key in (("Comparator", "sa", "comp_key"), ("S/H switch", "switch", "sw_key"), ("VCM op-amp", "opa", "opa_vcm_key"), ("Input driver op-amp", "opa", "opa_in_key")):
    cnt = Counter(c[key] for c in cards)
    for k, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0])):
        reuse.append([kind, mdlink(comp_id, k), vdd_of_key(k), n, ", ".join(sorted({c["arch"] for c in cards if c[key] == k}))])
cc_rows = []
for k, v in sorted((COMPCHAR.get("comp") or {}).items()):
    cmd = v.get("cm_delays_s") or {}
    cc_rows.append([mdlink("sa", k), vdd_of_key(k), v.get("ok"), v.get("reset_out"), v.get("out_polarity"), v.get("burst_ok"), v.get("delay_nom_s"),
                    v.get("delay_burst_mean_s"), v.get("cm_walk_v"), v.get("sigma_noise_calc_v"),
                    "; ".join(f"{float(a):.3g} V: {si(b, 's', 3)}" for a, b in sorted(cmd.items(), key=lambda x: float(x[0])))])
ctl_rows = []
for k, v in sorted((COMPCHAR.get("ctl") or {}).items(), key=lambda kv_: (kv_[0].split("_")[0], int(kv_[0].split("_")[1][1:]), kv_[0])):
    parts = k.split("_")
    ctl_rows.append([k, v.get("vdd", float(parts[0][1:])), v.get("n_cols", int(parts[1][1:])), v.get("buf", "_".join(parts[2:])), v.get("ok"),
                     mul(v.get("t_ctl50_ns"), 1e-9), mul(v.get("t_settle_999_ns"), 1e-9)])
libs = {
    "intro": ("Every SAR ADC reuses characterized, layout-verified sub-blocks from the sibling generators — comparators from "
              "[sa-gen](#/sa), S/H switches from [switch-gen](#/switch) and op-amps from [opa-gen](#/opa) — selected systematically per card. "
              "Component links open the sibling design on the hub."),
    "blocks": [
        table("Seven input & switching architectures explored across all resolutions & supplies",
              [col("a", "Architecture id", type_="text", md=True, wrap=True), col("i", "Input front-end S/H topology", type_="text", md=True, wrap=True),
               col("s", "CDAC switching scheme", type_="text", md=True, wrap=True), col("n", "LSB noise suppression", type_="text", md=True, wrap=True),
               col("k", "Key advantage", type_="text", md=True, wrap=True)], ARCH_TABLE, search=False, csv=False),
        table(f"Complete {len(cards)}-card deliverable matrix & selected sibling library components",
              [col("card", "Card", type_="design"), col("spec", "Spec", type_="text"), col("vdd", "V_DD", "V", digits=2), col("cdac", "CDAC", type_="text"),
               col("comp", "Comparator (sa-gen)", type_="text", md=True), col("sw", "Switch (switch-gen)", type_="text", md=True),
               col("opa", "VCM op-amp (opa-gen)", type_="text", md=True), col("opai", "Input op-amp (opa-gen)", type_="text", md=True),
               col("enob_p", "ENOB", "b", digits=4, group="As published (old site)"), col("fom_p", "Walden FoM", "fJ/step", digits=4, group="As published (old site)"),
               col("enob_h", "ENOB", "b", digits=4, group="Hub (partial post-PEX)", better="high"), col("fom_h", "Walden FoM", "fJ/step", digits=4, group="Hub (partial post-PEX)", better="low"),
               col("enob_r", "ENOB raw codes (LU)", "b", digits=4, group="Hub (partial post-PEX)")],
              mat_rows, page_size=200,
              caption="Click a row to open the card. Amber published values: fallback (failed FFT), derived from the ULP energy placeholders, or "
                      "synthesized by the loop-unrolled calibration fit."),
        table("Sibling component reuse", [col("k", "Role", type_="text"), col("c", "Component", type_="text", md=True), col("vdd", "V_DD", "V", digits=2), col("n", "Cards", digits=3),
                                          col("a", "Used by architectures", type_="text")], reuse, page_size=100),
        section("Comparator & control-line characterization (docs/data/compchar.json)", [
            table("Comparator burst / common-mode characterization", [
                col("k", "Comparator", type_="text", md=True), col("vdd", "V_DD", "V", digits=2), col("ok", "OK", type_="status"), col("r", "Reset output", type_="text"),
                col("p", "Output polarity", digits=2), col("b", "Burst OK", type_="status"), col("d", "Nominal delay", "s", True),
                col("db", "Burst mean delay", "s", True), col("w", "CM walk", "V", True), col("n", "σ_noise (calc.)", "V", True),
                col("cm", "Delay vs input common mode", type_="text")], cc_rows, page_size=100),
            table("CDAC control-line drive (buffer sizing)", [
                col("k", "Config", type_="text"), col("vdd", "V_DD", "V", digits=2), col("c", "Columns", digits=3), col("b", "Buffer", type_="text"),
                col("ok", "OK", type_="status"), col("t50", "t_ctl,50%", "s", True), col("ts", "t_settle,99.9%", "s", True)], ctl_rows, page_size=100),
        ], intro="Generator-side characterization runs stored in docs/data/compchar.json; this file was not displayed by the old site.", collapsed=True),
    ],
}
dump(OUT / "pages" / "libraries.json", libs)

# ----------------------------------------------------------------------------- component
gen = datetime.fromtimestamp(int(os.path.getmtime(DOCS / "data" / "index.json")), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
comp = {
    "schema": "aicdb-hub/2",
    "id": "sar",
    "name": "SAR ADCs",
    "title": "GF180MCU-D Low-Power Redundant SAR ADC Catalog",
    "summary": (f"{len(cards)} sub-binary-redundant SAR ADCs (8/10/12 bit, 1.8 V and 3.3 V, custom MOM or MIM common-centroid CDAC) "
                "from 1 kS/s sleep-gated ULP to 400 MS/s loop-unrolled domino cores (2 GS/s time-interleaved), built from the "
                "sibling comparators, switches and op-amps; transistor-level SPICE with the Magic-extracted CDAC (partial post-PEX) "
                "and injected-variance switching-failure checks on all 24 CDAC macros."),
    "technology": "gf180mcuD",
    "generated": gen,
    "stats": [
        {"label": "CDAC macros (variance-verified)", "value": f"{n_mac_pass} / {n_mac}"},
        {"label": "DSE combinations evaluated", "value": f"{SWEEP.get('total_evaluated', 0):,}"},
        {"label": "DSE feasible", "value": f"{SWEEP.get('feasible_count', 0):,}"},
        {"label": "peak single-channel rate", "value": si(peak["fs_msps"] * 1e6, "S/s", 4)},
    ],
    "metrics": [{k: v for k, v in dict(key=k, label=l, unit=u, si=s or None, better=b, digits=dg, desc=ds).items() if v is not None}
                for k, l, u, s, b, dg, ds in METRICS],
    "axes": {
        "mode": {"label": "Operating mode", "values": [{"id": a, "label": l} for a, l in MODES]},
        "topology": {"label": "Architecture", "values": [{"id": a, "label": l} for a, l in ARCHS]},
        "nbits": {"label": "Resolution", "values": [{"id": str(n), "label": f"{n}-bit"} for n in (8, 10, 12)]},
        "tier": {"label": "Sample-rate tier", "values": [{"id": a, "label": l} for a, l in TIERS]},
        "cap": {"label": "CDAC capacitor", "values": [{"id": a, "label": l} for a, l in CAPS]},
    },
    "matrix": {"rows": ["topology"], "cols": ["nbits", "cap"], "metrics": ["enob", "fom_w", "power"],
               "status": {"metric": "enob_loss", "good": 1.8, "warn": 3},
               "presets": [{"label": "Power & sample rate", "metrics": ["power", "fs", "e_conv"]},
                           {"label": "SNDR, SFDR & THD", "metrics": ["sndr", "sfdr", "thd"]},
                           {"label": "Energy & Schreier FoM", "metrics": ["e_conv", "fom_s"]},
                           {"label": "Static linearity (INL/DNL)", "metrics": ["inl", "dnl"]},
                           {"label": "Variance robustness (redundant vs binary)", "metrics": ["enob_var", "enob_var_bin"]},
                           {"label": "ULP power & sleep leakage", "metrics": ["power", "p_leak", "e_conv"]},
                           {"label": "Loop-unrolled: raw-code ENOB", "metrics": ["enob_raw", "power", "fs"]},
                           {"label": "Area", "metrics": ["area", "enob"]}]},
    "card_metrics": ["enob", "sndr", "fom_w", "fs", "power", "p_leak", "sfdr", "e_conv", "enob_raw", "enob_var", "fom_s", "area"],
    "builds_on": [{"id": "sa", "role": "comparator"},
                  {"id": "switch", "role": "S/H switch"},
                  {"id": "opa", "role": "VCM buffer"}, {"id": "opa", "role": "input driver"}],
    "pages": [
        {"id": "overview", "title": "Overview & KPIs", "src": "hub/pages/overview.json"},
        {"id": "explore", "title": "Design space (13.1 M pts)", "src": "hub/pages/explore.json"},
        {"id": "resilience", "title": "CDAC variance & redundancy", "src": "hub/pages/resilience.json"},
        {"id": "libraries", "title": "Libraries & architectures", "src": "hub/pages/libraries.json"},
    ],
    "designs": designs,
}
dump(OUT / "component.json", comp)
