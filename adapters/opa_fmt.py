"""Formatting / rounding helpers for adapters/opa.py.

The string formatters are faithful ports of the retired opa-gen-gemini4 site
(docs/assets/app.js: num, fmtIdd, fmtPwr, si, cmpSub, fmtRange) so that text cells,
KPI tiles and labels read exactly as they did on the old pages.
"""
import math
from decimal import ROUND_HALF_UP, Decimal

MU = "µ"


def to_fixed(v, d):
    """Exact port of JS Number.prototype.toFixed (ties round away from zero on the exact binary value)."""
    q = Decimal(abs(v)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return ("-" if v < 0 else "") + f"{q:.{d}f}"


def to_precision_num(v, p):
    """Number(x.toPrecision(p)) in JS: p significant digits, ties away from zero, back to a float."""
    if v == 0:
        return 0.0
    a = Decimal(abs(v))
    q = a.quantize(Decimal(1).scaleb(a.adjusted() - p + 1), rounding=ROUND_HALF_UP)
    return float(q) * (-1 if v < 0 else 1)


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def jsn(x):
    """JavaScript Number -> String (shortest round-trip, integers without '.0')."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if x is None:
        return "null"
    if math.isfinite(x) and x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def num(v, d=2):
    """app.js num(): toFixed(d) or an em dash."""
    return to_fixed(v, d) if fin(v) else "—"


def fmt_idd(ua):
    if not fin(ua):
        return "—"
    if abs(ua) < 0.1:
        return f"{jsn(float(to_fixed(ua * 1000, 1)))} nA"
    return f"{jsn(float(to_fixed(ua, 2)))} {MU}A"


def fmt_pwr(uw):
    if not fin(uw):
        return "—"
    if abs(uw) < 0.1:
        return f"{jsn(float(to_fixed(uw * 1000, 1)))} nW"
    return f"{jsn(float(to_fixed(uw, 2)))} {MU}W"


_PREFIX = {-15: "f", -12: "p", -9: "n", -6: MU, -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}


def si(v, unit="", digits=3):
    if not fin(v):
        return "—"
    a = abs(v)
    if a == 0:
        return "0 " + unit
    p = max(-15, min(9, math.floor(math.log10(a) / 3) * 3))
    return f"{jsn(to_precision_num(v / 10 ** p, digits))} {_PREFIX[p]}{unit}"


def cmp_sub(pre, post, unit="", d=2):
    if not fin(pre):
        return ""
    if not fin(post):
        return "Pre-PEX nominal"
    delta = post - pre
    sgn = "+" if delta >= 0 else ""
    return f"Pre: {num(pre, d)}{unit} → Post: {num(post, d)}{unit} ({sgn}{num(delta, d)}{unit})"


def fmt_range(lo, hi, d=2, u=""):
    if lo is None or hi is None:
        return "—"
    return f"[{num(lo, d)}, {num(hi, d)}]" + (f" {u}" if u else "")


def r5(v, n=5):
    """Round a float to n significant digits (ints / others unchanged; NaN/inf -> None)."""
    if isinstance(v, bool) or not isinstance(v, float):
        return v
    if not math.isfinite(v):
        return None
    if v == 0:
        return 0
    x = float(f"{v:.{n}g}")
    return int(x) if x.is_integer() and abs(x) < 1e15 else x


def rl(seq, n=5):
    return [r5(x, n) for x in (seq or [])]


def scale(v, k):
    return r5(v * k) if fin(v) else None


def unit_label(u):
    return {"uA": f"{MU}A", "um": f"{MU}m", "pF": "pF"}.get(u, u)
