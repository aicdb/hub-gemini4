#!/usr/bin/env python3
"""Design-point registry CLI (points.json, schema "aicdb-points/1").

This file is identical in every generator repository (source: aicdb/hub-gemini4,
templates/scripts/points.py). Repository-specific behaviour lives in scripts/points_hook.py.

  python3 scripts/points.py list  [--where field=value ...] [--json]
  python3 scripts/points.py show  ID
  python3 scripts/points.py add   field=value ... [--id ID] [--note TEXT] [--unpublished] [--allow-new]
  python3 scripts/points.py remove ID [--purge]
  python3 scripts/points.py check

Hook (optional) scripts/points_hook.py may define:
  make_id(point: dict) -> str               id for a new point (default: points.json "id_format")
  validate(point: dict) -> list[str]        extra validation errors (e.g. unsupported combination)
  artefact_dirs(point_id: str) -> list[str] published folders of a point, relative to the repo
                                            (default: ["docs/designs/<id>"]; [] = none expected,
                                            e.g. a point marked n/a)
  ignore_dirs() -> list[str]                folders under docs/designs that are not design points
  fields_for(point: dict) -> dict           the field spec that applies to this point (e.g. per family)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "points.json"
SCHEMA = "aicdb-points/1"


def load_hook():
    p = ROOT / "scripts" / "points_hook.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("points_hook", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOOK = load_hook()


def hook(name, *args, default=None):
    fn = getattr(HOOK, name, None) if HOOK else None
    return fn(*args) if fn else default


def load() -> dict:
    reg = json.loads(REGISTRY.read_text())
    if reg.get("schema") != SCHEMA:
        sys.exit(f"{REGISTRY}: schema must be {SCHEMA!r}")
    return reg


def save(reg: dict) -> None:
    """Stable, diff-friendly formatting: one field and one point per line."""
    one = lambda v: json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
    out = ["{"]
    for k, v in reg.items():
        if k in ("fields", "points"):
            continue
        out.append(f"  {json.dumps(k)}: {one(v)},")
    if "fields" in reg:
        f = reg["fields"]
        out.append('  "fields": {')
        out.append(",\n".join(f"    {json.dumps(n)}: {one(spec)}" for n, spec in f.items()))
        out.append("  },")
    out.append('  "points": [')
    out.append(",\n".join(f"    {one(p)}" for p in reg["points"]))
    out.append("  ]")
    out.append("}")
    REGISTRY.write_text("\n".join(out) + "\n")


def parse_kv(items: list[str]) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            sys.exit(f"expected field=value, got {it!r}")
        k, v = it.split("=", 1)
        try:
            out[k] = json.loads(v)          # numbers, true/false, quoted strings
        except json.JSONDecodeError:
            out[k] = v                      # bare strings
    return out


def artefact_dirs(point_id: str) -> list[str]:
    dirs = hook("artefact_dirs", point_id, default=None)
    return [f"docs/designs/{point_id}"] if dirs is None else list(dirs)


def fields_for(reg: dict, point: dict) -> dict:
    return hook("fields_for", point, default=None) or reg.get("fields", {})


def make_id(reg: dict, point: dict) -> str:
    pid = hook("make_id", point)
    if pid:
        return pid
    fmt = reg.get("id_format")
    if not fmt:
        sys.exit("cannot derive an id: pass --id or define id_format / points_hook.make_id")
    try:
        return fmt.format(**point)
    except KeyError as e:
        sys.exit(f"id_format needs field {e}")


def validate(reg: dict, point: dict, allow_new: bool) -> list[str]:
    errs = []
    spec = fields_for(reg, point)
    for name, f in spec.items():
        if name not in point and not f.get("optional"):
            errs.append(f"missing field {name!r}")
        elif name in point and "values" in f and point[name] not in f["values"] and not allow_new:
            errs.append(f"{name}={point[name]!r} is not one of {f['values']} (use --allow-new if the generator supports it)")
    errs += hook("validate", point, default=[]) or []
    return errs


def cmd_list(reg, a):
    where = parse_kv(a.where or [])
    pts = [p for p in reg["points"] if all(p.get(k) == v for k, v in where.items())]
    if a.json:
        print(json.dumps(pts, indent=1, ensure_ascii=False))
        return 0
    for p in pts:
        flag = "" if p.get("publish", True) else "  (unpublished)"
        print(f"{p['id']}{flag}")
    print(f"# {len(pts)} of {len(reg['points'])} points", file=sys.stderr)
    return 0


def find(reg, pid):
    for p in reg["points"]:
        if p["id"] == pid:
            return p
    sys.exit(f"no design point {pid!r} (see: make points)")


def cmd_show(reg, a):
    print(json.dumps(find(reg, a.id), indent=1, ensure_ascii=False))
    return 0


def cmd_add(reg, a):
    point = parse_kv(a.fields)
    errs = validate(reg, point, a.allow_new)
    if errs:
        sys.exit("cannot add point:\n  " + "\n  ".join(errs))
    pid = a.id or make_id(reg, point)
    if any(p["id"] == pid for p in reg["points"]):
        sys.exit(f"design point {pid!r} already exists")
    if a.allow_new:
        spec = reg.get("fields", {})
        for k, v in point.items():
            if k in spec and "values" in spec[k] and v not in spec[k]["values"]:
                spec[k]["values"].append(v)
    entry = {"id": pid, **point}
    if a.unpublished:
        entry["publish"] = False
    if a.note:
        entry["note"] = a.note
    reg["points"].append(entry)
    save(reg)
    print(f"added {pid} — next: make build POINT={pid}")
    return 0


def cmd_remove(reg, a):
    p = find(reg, a.id)
    reg["points"].remove(p)
    save(reg)
    print(f"removed {a.id} from points.json")
    if a.purge:
        for d in artefact_dirs(a.id):
            path = ROOT / d
            if path.is_dir():
                shutil.rmtree(path)
                print(f"deleted {d}/")
    print("next: make docs && make hub")
    return 0


def cmd_check(reg, a):
    errs, warns = [], []
    ids = [p["id"] for p in reg["points"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate ids in points.json")
    for p in reg["points"]:
        for e in validate(reg, p, allow_new=False):
            errs.append(f"{p['id']}: {e}")
        if p.get("publish", True):
            for d in artefact_dirs(p["id"]):
                if not (ROOT / d).is_dir():
                    warns.append(f"{p['id']}: no published artefacts in {d}/ (not built yet?)")
    known = set()
    for p in reg["points"]:
        for d in artefact_dirs(p["id"]):
            known.add(str(Path(d)))
    ignore = set(hook("ignore_dirs", default=None) or [])
    for base in sorted({str(Path(d).parent) for d in known}):
        bp = ROOT / base
        if not bp.is_dir():
            continue
        for sub in sorted(bp.iterdir()):
            rel = str(sub.relative_to(ROOT))
            if sub.is_dir() and rel not in known and rel not in ignore and sub.name not in ignore:
                warns.append(f"orphan folder {rel}/ is not a registered design point")
    for w in warns:
        print(f"warn: {w}")
    for e in errs:
        print(f"ERROR: {e}")
    print(f"{len(reg['points'])} points, {len(errs)} errors, {len(warns)} warnings")
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="list design points")
    s.add_argument("--where", nargs="*", metavar="FIELD=VALUE")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("show", help="show one design point")
    s.add_argument("id")
    s = sub.add_parser("add", help="add a design point")
    s.add_argument("fields", nargs="+", metavar="FIELD=VALUE")
    s.add_argument("--id")
    s.add_argument("--note")
    s.add_argument("--unpublished", action="store_true", help="keep it out of the hub")
    s.add_argument("--allow-new", action="store_true", help="accept field values not listed yet")
    s = sub.add_parser("remove", help="remove a design point")
    s.add_argument("id")
    s.add_argument("--purge", action="store_true", help="also delete its published artefacts")
    sub.add_parser("check", help="registry <-> docs consistency")
    a = ap.parse_args(argv)
    reg = load()
    return {"list": cmd_list, "show": cmd_show, "add": cmd_add, "remove": cmd_remove, "check": cmd_check}[a.cmd](reg, a)


if __name__ == "__main__":
    sys.exit(main())
