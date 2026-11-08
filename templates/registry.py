"""Read the design-point registry (points.json) from generator code.

Copy into the generator package as <pkg>/registry.py (identical in every repository).
The pipeline builds exactly the points returned here; add or remove points with
`make add` / `make remove` instead of editing loops in code.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "points.json"


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text())


def points(publish_only: bool = False, **where) -> list[dict]:
    """Registered design points, optionally filtered by field values (e.g. points(vdd=1.8))."""
    out = []
    for p in load_registry()["points"]:
        if publish_only and not p.get("publish", True):
            continue
        if all(p.get(k) == v for k, v in where.items()):
            out.append(p)
    return out


def ids(publish_only: bool = False, **where) -> list[str]:
    return [p["id"] for p in points(publish_only, **where)]


def get(point_id: str) -> dict:
    for p in load_registry()["points"]:
        if p["id"] == point_id:
            return p
    raise KeyError(f"design point {point_id!r} is not in points.json")
