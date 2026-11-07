"""Formatting helpers for the aux adapter: ports of the old site's JS number formatting
(`num(v, d)` = Number(v).toFixed(d), `fmtFreqMhz`) plus compact JSON output."""
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DASH = "—"


def isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def tofixed(v, d):
    """JavaScript Number(v).toFixed(d) (half-up on the exact binary value)."""
    q = Decimal(1).scaleb(-d) if d > 0 else Decimal(1)
    s = str(Decimal(float(v)).quantize(q, rounding=ROUND_HALF_UP))
    if s.startswith("-") and float(s) == 0:
        s = s[1:]
    return s


def num(v, d=2):
    """old site `num()`: '—' for null / non-finite, else toFixed(d)."""
    if v is None or isinstance(v, str):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return DASH
    if isinstance(v, bool):
        v = float(v)
    if not isnum(v):
        return DASH
    return tofixed(v, d)


def fmt_mhz(mhz):
    """old site `fmtFreqMhz()`."""
    if not isnum(mhz):
        return DASH
    v = float(mhz)
    if v >= 1000:
        return f"{tofixed(v / 1000, 2)} GHz"
    if v >= 100:
        return f"{tofixed(v, 1)} MHz"
    if v >= 10:
        return f"{tofixed(v, 2)} MHz"
    return f"{tofixed(v, 3)} MHz"


def sig(v, n=5):
    """round a float to n significant digits (keeps ints)."""
    if isinstance(v, bool) or not isinstance(v, float):
        return v
    if not math.isfinite(v):
        return None
    if v == 0:
        return 0
    r = round(v, n - 1 - int(math.floor(math.log10(abs(v)))))
    return int(r) if r == int(r) and abs(r) < 1e15 else r


def compact(o, n=5):
    if isinstance(o, dict):
        return {k: compact(v, n) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [compact(v, n) for v in o]
    return sig(o, n)


def write_json(path: Path, obj, n=5):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compact(obj, n), separators=(",", ":"), ensure_ascii=False))
