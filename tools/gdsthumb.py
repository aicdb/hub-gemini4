#!/usr/bin/env python3
"""Render GDSII (.gds / .gds.gz) layouts to WebP thumbnails for the hub.

Requires gdstk and Pillow (CI installs them; `pip install gdstk pillow`).

  python3 gdsthumb.py in.gds.gz out.webp [--cell NAME] [--size 960] [--tech gf180mcuD]

Used as a library by hubkit (render(), cache_key()).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

RENDER_VERSION = "2"  # bump to invalidate cached thumbnails

# (layer, datatype): (name, rgb, alpha, kind)  kind: fill | cut | mark(hidden)
LAYERS = {
    "gf180mcuD": {
        (21, 0): ("NWELL", "#1e3a8a", 0.45, "fill"),
        (22, 0): ("COMP", "#15803d", 0.75, "fill"),
        (32, 0): ("NPLUS", "#854d0e", 0.38, "fill"),
        (31, 0): ("PPLUS", "#701a75", 0.38, "fill"),
        (30, 0): ("POLY2", "#dc2626", 0.85, "fill"),
        (33, 0): ("CONT", "#f8fafc", 1.0, "cut"),
        (34, 0): ("MET1", "#0284c7", 0.72, "fill"),
        (35, 0): ("VIA1", "#e2e8f0", 1.0, "cut"),
        (36, 0): ("MET2", "#ec4899", 0.70, "fill"),
        (38, 0): ("VIA2", "#fde047", 1.0, "cut"),
        (42, 0): ("MET3", "#10b981", 0.68, "fill"),
        (40, 0): ("VIA3", "#c084fc", 1.0, "cut"),
        (46, 0): ("MET4", "#f59e0b", 0.62, "fill"),
        (41, 0): ("VIA4", "#fb7185", 1.0, "cut"),
        (81, 0): ("MET5", "#a78bfa", 0.55, "fill"),
        (82, 0): ("VIA5", "#fda4af", 1.0, "cut"),
        (53, 0): ("METTOP", "#22d3ee", 0.50, "fill"),
        (75, 0): ("MIM_TOP", "#facc15", 0.45, "fill"),
    }
}
LAYERS["openrpdk28"] = LAYERS["gf180mcuD"]
BG = (26, 18, 16)   # warm dark, matches the hub palette (#1a1210)


def cache_key(gds: Path, cell: str | None, size: int, tech: str) -> str:
    h = hashlib.sha1()
    with open(gds, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    h.update(f"|{cell}|{size}|{tech}|{RENDER_VERSION}".encode())
    return h.hexdigest()[:20]


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def render(gds: Path, out: Path, cell: str | None = None, size: int = 960, tech: str = "gf180mcuD") -> dict:
    import gdstk
    from PIL import Image, ImageDraw

    src = gds
    tmp = None
    if str(gds).endswith(".gz"):
        tmp = tempfile.NamedTemporaryFile(suffix=".gds", delete=False)
        with gzip.open(gds, "rb") as fi:
            shutil.copyfileobj(fi, tmp)
        tmp.close()
        src = Path(tmp.name)
    try:
        lib = gdstk.read_gds(str(src))
    finally:
        if tmp:
            os.unlink(tmp.name)
    cells = {c.name: c for c in lib.cells}
    if cell and cell in cells:
        top = cells[cell]
    else:
        tops = lib.top_level() or lib.cells
        top = max(tops, key=lambda c: len(c.references) + len(c.polygons) + len(c.paths))
    polys = top.get_polygons(apply_repetitions=True, include_paths=True)
    style = LAYERS.get(tech, LAYERS["gf180mcuD"])
    bb = top.bounding_box()
    if bb is None:
        raise ValueError("empty cell")
    (x0, y0), (x1, y1) = bb
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    pad = 12
    s = min((size - 2 * pad) / w, (size * 0.75 - 2 * pad) / h) if w >= h else min((size * 0.75 - 2 * pad) / w, (size - 2 * pad) / h)
    W, H = int(w * s + 2 * pad), int(h * s + 2 * pad)
    img = Image.new("RGB", (W, H), BG)

    by_layer: dict[tuple, list] = {}
    for p in polys:
        k = (p.layer, p.datatype)
        if k in style:
            by_layer.setdefault(k, []).append(p.points)
    order = list(style.keys())
    for k in sorted(by_layer, key=order.index):
        name, color, alpha, kind = style[k]
        mask = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(mask)
        for pts in by_layer[k]:
            xy = [(pad + (x - x0) * s, H - pad - (y - y0) * s) for x, y in pts]
            if len(xy) >= 3:
                d.polygon(xy, fill=255)
        layer_img = Image.new("RGB", (W, H), _hex(color))
        img = Image.composite(layer_img, img, mask.point(lambda v, a=alpha: int(v * a)))
    # top-level pin labels (same as the old pre-rendered layout SVGs)
    try:
        from PIL import ImageFont
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 13)
        except OSError:
            font = ImageFont.load_default(size=13)
        d = ImageDraw.Draw(img)
        seen = set()
        for lb in top.labels[:120]:
            txt = str(lb.text).strip()
            if not txt or len(txt) > 24:
                continue
            x, y = lb.origin
            X, Y = pad + (x - x0) * s, H - pad - (y - y0) * s
            key = (txt, int(X // 40), int(Y // 16))
            if key in seen:
                continue
            seen.add(key)
            d.text((X, Y), txt, fill=(248, 250, 252), font=font, anchor="mm", stroke_width=2, stroke_fill=BG)
    except Exception:
        pass
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    img.save(tmp_out, "WEBP", quality=82, method=4)
    os.replace(tmp_out, out)  # atomic: safe with concurrent builds sharing a cache
    return {"cell": top.name, "width_um": round(w, 3), "height_um": round(h, 3),
            "cells": sorted(cells), "px": [W, H]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gds", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cell")
    ap.add_argument("--size", type=int, default=960)
    ap.add_argument("--tech", default="gf180mcuD")
    a = ap.parse_args()
    print(render(a.gds, a.out, a.cell, a.size, a.tech))
