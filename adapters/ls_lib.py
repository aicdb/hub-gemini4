"""Helpers for the ls (level-shifter) bootstrap adapter: rounding/JSON output, a tiny HTML->markdown
converter for the old report's static prose, JS-compatible fixed-point formatting, and Plotly figure
builders that port the old report's hand-written SVG charts.  Python >= 3.9 stdlib only."""
from __future__ import annotations

import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path


# ----------------------------------------------------------------------------- numbers / output
class Keep(float):
    """A float that clean()/sig() leave unrounded (e.g. layout areas the old site printed with 2 decimals)."""


def sig(x, n=5):
    """Round a float to n significant digits; integral values become ints (compact JSON)."""
    if isinstance(x, Keep):
        return float(x)
    if isinstance(x, bool) or not isinstance(x, float):
        return x
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0
    y = float(f"{x:.{n}g}")
    if y == int(y) and abs(y) < 1e15:
        return int(y)
    return y


def clean(o, n=5):
    if isinstance(o, float):
        return sig(o, n)
    if isinstance(o, dict):
        return {k: clean(v, n) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v, n) for v in o]
    return o


class Out:
    """Writes compact JSON under the adapter output dir and returns the "hub/<rel>" reference."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = 0
        self.bytes = 0

    def put(self, rel: str, obj, n=5) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        s = json.dumps(clean(obj, n), separators=(",", ":"), ensure_ascii=False)
        p.write_text(s)
        self.files += 1
        self.bytes += len(s.encode())
        return "hub/" + rel


def tofixed(x, n):
    """JavaScript Number.prototype.toFixed semantics (exact binary value, ties away from zero)."""
    return float(Decimal(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def fx(x, n=1, na="—"):
    """String like JS fmt(v, n) of the old report."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return na
    return str(Decimal(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)) if n > 0 else \
        str(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def mul(x, k):
    return None if x is None else x * k


PS, NW, FJ, UW, MHZ = 1e-12, 1e-9, 1e-15, 1e-6, 1e6


# ----------------------------------------------------------------------------- tiny DOM + markdown
VOID = {"br", "img", "input", "meta", "link", "hr", "col", "source", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    def cls(self):
        return (self.attrs.get("class") or "").split()

    def iter(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def find_all(self, tag=None, cls=None):
        return [n for n in self.iter() if (tag is None or n.tag == tag) and (cls is None or cls in n.cls())]

    def find(self, tag=None, cls=None, id=None):
        for n in self.iter():
            if (tag is None or n.tag == tag) and (cls is None or cls in n.cls()) and (id is None or n.attrs.get("id") == id):
                return n
        return None

    def kids(self, tag=None):
        return [c for c in self.children if isinstance(c, Node) and (tag is None or c.tag == tag)]

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [], None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        c = self.cur
        while c is not None and c.tag != tag:
            c = c.parent
        if c is not None and c.parent is not None:
            self.cur = c.parent

    def handle_data(self, d):
        self.cur.children.append(d)


def parse_html(src: str) -> Node:
    p = _Parser()
    p.feed(src)
    p.close()
    return p.root


LINK_MAP = {"#appendix": "#/ls?page=appendix", "#unitinv": "#/ls?page=unitinv", "#explore": "#/ls?page=explore",
            "#hvt": "#/ls?page=hvt", "#overview": "#/ls?page=overview"}


def _wrap(inner, a, b=None):
    b = a if b is None else b
    m = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.S)
    return f"{m.group(1)}{a}{m.group(2)}{b}{m.group(3)}" if m.group(2) else inner


def md_inline(n) -> str:
    if isinstance(n, str):
        return re.sub(r"[ \t\r\n]+", " ", n)
    t = n.tag
    if t == "br":
        return "\n"
    if t in ("script", "style", "select", "option", "button", "input", "table"):
        return ""
    if t == "code":
        s = re.sub(r"\s+", " ", n.text())
        return f"`{s}`" if "`" not in s else s
    inner = "".join(md_inline(c) for c in n.children)
    if t in ("strong", "b"):
        return _wrap(inner, "**")
    if t in ("em", "i"):
        return _wrap(inner, "*")
    if t in ("sub", "sup", "small", "u"):
        return f"<{t}>{inner}</{t}>"
    if t == "a":
        href = n.attrs.get("href", "")
        href = LINK_MAP.get(href, href)
        return f"[{inner.strip()}]({href})" if href and inner.strip() else inner
    return inner


def to_md(n) -> str:
    s = md_inline(n)
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# ----------------------------------------------------------------------------- figures
GRAY_IN = "#8a8780"
CORNER_COL = {"tt_27C": "#2a78d6", "ss_-40C": "#cf222e", "ff_125C": "#9a6700", "pilot": "#2a78d6"}
PAL6 = ["#2a78d6", "#eb6834", "#1baf7a", "#9a6700", "#52514e", "#cf222e"]
EXTRA_COL = ["#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5"]


def corner_label(k: str) -> str:
    if k == "pilot":
        return "VOUT (tt 27 °C)"
    if k.startswith("seed_"):
        return f"VOUT seed {k[5:]}"
    m = re.match(r"^(\w\w)_(-?\d+)C$", k)
    return f"VOUT {m.group(1)} {m.group(2).replace('-', '−')} °C" if m else k


def wave_fig(waves: dict, vssl, vddl, vssh, vddh, title: str, legend_note=True):
    """Port of renderWaveformSVG: dashed VIN (first entry), one VOUT per corner/seed, rail guides."""
    entries = [(k, w) for k, w in waves.items() if w and len(w.get("t_ns") or []) > 2]
    if not entries:
        return None
    first = entries[0][1]
    ymin = min(vssl, vssh, 0.0) - 0.15
    ymax = max(vddl, vddh, 3.3) + 0.25
    tr = [{"type": "scatter", "mode": "lines", "name": f"VIN [{fx(vssl, 1)}..{fx(vddl, 2)} V]",
           "x": first["t_ns"], "y": first["vin"], "line": {"color": GRAY_IN, "dash": "dash", "width": 1.6},
           "hovertemplate": "VIN %{y:.3f} V @ %{x:.2f} ns<extra></extra>"}]
    extra = 0
    for idx, (k, w) in enumerate(entries):
        if k in CORNER_COL:
            col, width = CORNER_COL[k], 2.2
        elif k.startswith("seed_"):
            col, width = PAL6[idx % 6], 1.8
        else:
            col, width = EXTRA_COL[extra % len(EXTRA_COL)], 1.2
            extra += 1
        tr.append({"type": "scatter", "mode": "lines", "name": corner_label(k), "x": w["t_ns"], "y": w["vout"],
                   "line": {"color": col, "width": width},
                   "hovertemplate": f"{corner_label(k)} %{{y:.3f}} V @ %{{x:.2f}} ns<extra></extra>"})
    shapes = [{"type": "line", "xref": "paper", "x0": 0, "x1": 1, "y0": v, "y1": v,
               "line": {"color": "#74726c", "dash": "dot", "width": 1}} for v in (vssh, vddh)]
    ann = [{"xref": "paper", "x": 1, "xanchor": "right", "y": vddh, "yanchor": "bottom", "showarrow": False,
            "text": f"VDDH {fx(vddh, 2)} V", "font": {"size": 10, "color": "#74726c"}},
           {"xref": "paper", "x": 1, "xanchor": "right", "y": vssh, "yanchor": "top", "showarrow": False,
            "text": f"VSSH {fx(vssh, 2)} V", "font": {"size": 10, "color": "#74726c"}}]
    lay = {"title": {"text": title, "font": {"size": 13}, "x": 0.01},
           "xaxis": {"title": {"text": "Time (ns)"}},
           "yaxis": {"title": {"text": "Voltage (V)"}, "range": [ymin, ymax]},
           "shapes": shapes, "annotations": ann, "margin": {"t": 44, "b": 125},
           "legend": {"orientation": "h", "x": 0, "xanchor": "left", "y": -0.3, "yanchor": "top", "font": {"size": 10}}}
    return {"data": tr, "layout": lay}


def band_scale(fail_col, ov_col, lo_col, hi_col, mid_col=None):
    """Colour scale for z in [-2, 1]: -2 fail, -1 over-voltage/other, [0,1] value gradient."""
    s = [[0, fail_col], [0.3, fail_col], [0.3, ov_col], [0.64, ov_col], [0.665, lo_col]]
    if mid_col:
        s.append([0.8325, mid_col])
    s.append([1, hi_col])
    return s


def custom_scale(fn, n=11):
    return [[i / (n - 1), fn(i / (n - 1))] for i in range(n)]


def delay_color(t):
    """Port of the VSS2D delayColor gradient (emerald -> violet -> rose)."""
    r = round(16 + t * 228)
    g = round(185 - t * 110)
    b = round(129 + (t * 220 if t < 0.5 else (1 - t) * 180))
    return f"rgb({r},{g},{b})"


def blue_color(t):
    return f"rgb({round(227 - t * 71)},{round(238 - t * 44)},{round(251 - t * 12)})"


def norm(v, lo, hi, log=False):
    if v is None:
        return None
    if log:
        if v <= 0 or lo <= 0:
            return 0.0
        v, lo, hi = math.log10(v), math.log10(lo), math.log10(hi)
    return max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi > lo else 0.0


def heat_trace(x, y, z, text, hover, scale, zmin=-2, zmax=1, axis=""):
    t = {"type": "heatmap", "x": x, "y": y, "z": z, "text": text, "hovertext": hover,
         "texttemplate": "%{text}", "textfont": {"size": 9, "color": "#111111"},
         "hovertemplate": "%{hovertext}<extra></extra>", "colorscale": scale, "zmin": zmin, "zmax": zmax,
         "showscale": False, "xgap": 2, "ygap": 2}
    if axis:
        t["xaxis"], t["yaxis"] = f"x{axis}", f"y{axis}"
    return t
