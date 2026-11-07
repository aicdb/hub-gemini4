#!/usr/bin/env python3
"""hubkit — build, validate and preview the AICDB analog IP hub.

Stdlib only (Python >= 3.9). Three entry points:

  validate DOCS_DIR            Check a component export (DOCS_DIR/hub/component.json)
                               against the aicdb-hub/1 contract (see BUILDERS.md).
  preview  DOCS_DIR            Build a one-component hub from DOCS_DIR and serve it on
                               http://127.0.0.1:8000 so a repo builder can see their tab.
  build                        Assemble the full site from every source in sources.json.

The hub never writes into a source directory: normalized component JSON goes to
OUT/data/components/<id>.json and the source's docs/ tree is copied (or symlinked
with --link) to OUT/c/<id>/.
"""
from __future__ import annotations

import argparse
import fnmatch
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "aicdb-hub/1"
STAGES = ("pre", "partial", "full")
HUB_ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STD_FILES = ("schematic", "layout", "thumbnail", "gds", "netlist", "pex_netlist", "lvs_netlist", "data")
IMAGE_EXT = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")


# ----------------------------------------------------------------------------- validation
class Report:
    def __init__(self, label: str):
        self.label, self.errors, self.warnings = label, [], []

    def err(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def print(self, limit: int = 25):
        for kind, items in (("ERROR", self.errors), ("warn", self.warnings)):
            for m in items[:limit]:
                print(f"  [{kind}] {self.label}: {m}")
            if len(items) > limit:
                print(f"  [{kind}] {self.label}: ... and {len(items) - limit} more")


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_component(comp: dict, docs: Path | None, rep: Report, exclude=()) -> None:
    """Validate a component dict in place-free fashion; file checks only if docs given."""
    if comp.get("schema") != SCHEMA:
        rep.err(f'"schema" must be "{SCHEMA}" (got {comp.get("schema")!r})')
    for k in ("id", "name", "title", "technology", "metrics", "designs"):
        if k not in comp:
            rep.err(f'missing top-level key "{k}"')
    if rep.errors:
        return
    if not ID_RE.match(str(comp["id"])):
        rep.err(f'bad component id {comp["id"]!r}')

    metrics = comp["metrics"]
    mkeys = set()
    if not isinstance(metrics, list) or not metrics:
        rep.err('"metrics" must be a non-empty list')
        metrics = []
    for m in metrics:
        if not isinstance(m, dict) or "key" not in m or "label" not in m:
            rep.err(f"metric needs key+label: {m!r}")
            continue
        if m["key"] in mkeys:
            rep.err(f'duplicate metric key {m["key"]!r}')
        mkeys.add(m["key"])
        if m.get("better") not in (None, "high", "low"):
            rep.err(f'metric {m["key"]}: better must be "high", "low" or absent')

    axes = comp.get("axes", {})
    axis_vals = {}
    for ak, a in axes.items():
        if not isinstance(a, dict) or "label" not in a or not isinstance(a.get("values"), list):
            rep.err(f"axis {ak!r} needs label + values[]")
            continue
        ids = [v.get("id") for v in a["values"] if isinstance(v, dict)]
        if len(ids) != len(set(ids)) or None in ids:
            rep.err(f"axis {ak!r}: value ids must be unique and present")
        axis_vals[ak] = set(ids)

    def check_view(view: dict, where: str):
        mx = view.get("matrix")
        if mx:
            for ak in mx.get("rows", []) + mx.get("cols", []):
                if ak not in axes:
                    rep.err(f"{where}.matrix references unknown axis {ak!r}")
            for k in mx.get("metrics", []):
                if k not in mkeys:
                    rep.err(f"{where}.matrix references unknown metric {k!r}")
            if not mx.get("rows"):
                rep.err(f"{where}.matrix.rows must name at least one axis")
        for k in view.get("card_metrics", []):
            if k not in mkeys:
                rep.err(f"{where}.card_metrics references unknown metric {k!r}")

    check_view(comp, "component")
    fam_ids = set()
    for f in comp.get("families", []) or []:
        if "id" not in f or "label" not in f:
            rep.err(f"family needs id+label: {f!r}")
            continue
        fam_ids.add(f["id"])
        check_view(f, f'families[{f["id"]}]')

    designs = comp["designs"]
    if not isinstance(designs, list) or not designs:
        rep.err('"designs" must be a non-empty list')
        return
    seen = set()
    missing_files = 0
    for d in designs:
        did = d.get("id")
        tag = f"design {did!r}"
        if not did or not ID_RE.match(str(did)):
            rep.err(f"{tag}: id missing or not [A-Za-z0-9._-]")
            continue
        if did in seen:
            rep.err(f"{tag}: duplicate id")
        seen.add(did)
        if not d.get("title"):
            rep.err(f"{tag}: missing title")
        if fam_ids and d.get("family") not in fam_ids:
            rep.err(f"{tag}: family {d.get('family')!r} not declared in families[]")
        if "vdd" not in d or not (d["vdd"] is None or _is_num(d["vdd"])):
            rep.err(f"{tag}: vdd must be a number (volts) or null")
        for ak, av in (d.get("axes") or {}).items():
            if ak not in axis_vals:
                rep.err(f"{tag}: unknown axis {ak!r}")
            elif av not in axis_vals[ak]:
                rep.err(f"{tag}: axis {ak}={av!r} not in axes.{ak}.values")
        res = d.get("results") or {}
        if not res:
            rep.err(f"{tag}: results{{}} is empty — need at least one of {STAGES}")
        for st, r in res.items():
            if st not in STAGES:
                rep.err(f"{tag}: unknown stage {st!r} (use {STAGES})")
                continue
            for mk, mv in (r.get("metrics") or {}).items():
                if mk not in mkeys:
                    rep.warn(f"{tag}: results.{st} has undeclared metric {mk!r} (ignored by UI)")
                elif mv is not None and not _is_num(mv):
                    rep.err(f"{tag}: results.{st}.metrics.{mk} must be number or null")
            for cnt in ("pvt", "mc"):
                c = r.get(cnt)
                if c is not None and not (isinstance(c, dict) and _is_num(c.get("pass")) and _is_num(c.get("total"))):
                    rep.err(f"{tag}: results.{st}.{cnt} must be {{pass, total}}")
        phys = d.get("physical") or {}
        for k in ("drc", "lvs", "pex"):
            if k in phys and phys[k] not in (True, False, None):
                rep.err(f"{tag}: physical.{k} must be true/false/null")
        if docs is not None:
            paths = [p for k, p in (d.get("files") or {}).items() if k in STD_FILES and p]
            paths += [x.get("path") for x in (d.get("images") or []) + (d.get("downloads") or []) if isinstance(x, dict)]
            for p in paths:
                if not p:
                    continue
                if p.startswith(("/", "http:", "https:")) or ".." in p.split("/"):
                    rep.err(f"{tag}: file path must be relative inside docs/: {p!r}")
                    continue
                if not (docs / p).is_file():
                    missing_files += 1
                    if missing_files <= 10:
                        rep.err(f"{tag}: referenced file not found: {p}")
                elif any(fnmatch.fnmatch(p, pat.removeprefix("**/")) or fnmatch.fnmatch("x/" + p, pat) for pat in exclude):
                    rep.warn(f"{tag}: {p} is excluded from publishing by the hub's exclude patterns")
    if missing_files > 10:
        rep.err(f"... {missing_files} referenced files missing in total")


def size_report(docs: Path, exclude, budget_mb: float, rep: Report, top: int = 5):
    total, big, by_ext = 0, [], {}
    for p in iter_files(docs, exclude):
        s = p.stat().st_size
        total += s
        ext = "".join(p.suffixes[-2:]) if p.suffix == ".gz" else p.suffix or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + s
        big.append((s, p))
    mb = total / 1e6
    if mb > budget_mb:
        rep.warn(f"published size {mb:.0f} MB exceeds the per-component budget of {budget_mb:.0f} MB")
        big.sort(reverse=True)
        rep.warn("largest files: " + ", ".join(f"{q.relative_to(docs)} ({s/1e6:.1f} MB)" for s, q in big[:top]))
        rep.warn("bytes by type: " + ", ".join(f"{k} {v/1e6:.0f} MB" for k, v in sorted(by_ext.items(), key=lambda x: -x[1])[:6]))
    return mb


# ----------------------------------------------------------------------------- normalization
def normalize(comp: dict, src: dict, cfg: dict, commit: str | None, origin: str) -> dict:
    """Fill defaults so the web app can stay simple."""
    comp = dict(comp)
    comp.setdefault("repo", src.get("repo"))
    comp["commit"] = commit or comp.get("commit")
    comp["origin"] = origin  # "native" (exported by the repo) or "adapter" (bootstrap in hub)
    comp["base"] = f"c/{comp['id']}/"
    tech_default = comp.get("technology")
    for d in comp["designs"]:
        d.setdefault("technology", tech_default)
        d.setdefault("axes", {})
        d.setdefault("tags", [])
        d.setdefault("physical", {})
        d.setdefault("files", {})
        for st in list(d.get("results", {})):
            d["results"][st].setdefault("metrics", {})
    if not comp.get("card_metrics"):
        comp["card_metrics"] = [m["key"] for m in comp["metrics"][:4]]
    return comp


def compact_rows(comp: dict) -> list:
    """Per-design summary used by the overview tab: [tech, vdd, family, stageMask, physOk, robustMask]."""
    rows = []
    for d in comp["designs"]:
        mask = robust = 0
        for i, st in enumerate(STAGES):
            r = d["results"].get(st)
            if r and (r.get("metrics") or r.get("pvt") or r.get("robust") is not None):
                mask |= 1 << i
                if r.get("robust"):
                    robust |= 1 << i
        ph = d.get("physical", {})
        phys_ok = 1 if (ph.get("drc") and ph.get("lvs")) else 0
        rows.append([d["technology"], d.get("vdd"), d.get("family"), mask, phys_ok, robust])
    return rows


# ----------------------------------------------------------------------------- file helpers
def _excluded(rel: str, exclude) -> bool:
    for pat in exclude:
        if fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:])):
            return True
    return False


def iter_files(root: Path, exclude=()):
    for dp, dns, fns in os.walk(root, followlinks=True):
        dns[:] = [x for x in dns if x != ".git"]
        for f in fns:
            p = Path(dp) / f
            if not _excluded(p.relative_to(root).as_posix(), exclude):
                yield p


def copy_tree(src: Path, dst: Path, exclude):
    n = 0
    for p in iter_files(src, exclude):
        q = dst / p.relative_to(src)
        q.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(p, q)  # cheap when on the same filesystem
        except OSError:
            shutil.copy2(p, q)
        n += 1
    return n


def git_head(path: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except Exception:
        return None


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------- component loading
def load_component(cid: str, docs: Path, rep: Report) -> tuple[dict | None, str]:
    """Return (component dict, origin). Prefer the repo's own export; fall back to a hub adapter."""
    native = docs / "hub" / "component.json"
    if native.is_file():
        try:
            return json.loads(native.read_text()), "native"
        except json.JSONDecodeError as e:
            rep.err(f"{native}: invalid JSON: {e}")
            return None, "native"
    adapter = HUB_ROOT / "adapters" / f"{cid}.py"
    if adapter.is_file():
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "component.json"
            r = subprocess.run([sys.executable, "-I", str(adapter), str(docs), str(out)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not out.is_file():
                rep.err(f"adapter {adapter.name} failed:\n{r.stderr[-2000:]}")
                return None, "adapter"
            return json.loads(out.read_text()), "adapter"
    rep.err(f"no {native.relative_to(docs.parent) if docs.parent != docs else native} and no adapters/{cid}.py")
    return None, "missing"


# ----------------------------------------------------------------------------- build
def build(cfg: dict, sources: list[tuple[dict, Path]], out: Path, link: bool, strict: bool) -> int:
    exclude = cfg.get("exclude", [])
    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "components").mkdir(parents=True)
    (out / "c").mkdir()
    shutil.copytree(HUB_ROOT / "web", out, dirs_exist_ok=True)
    (out / ".nojekyll").write_text("")

    catalog = {"schema": SCHEMA, "site": cfg.get("site", {}), "technologies": cfg.get("technologies", {}),
               "stages": [{"id": "pre", "label": "Pre-PEX"}, {"id": "partial", "label": "Partial post-PEX"},
                          {"id": "full", "label": "Full post-PEX"}],
               "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "components": []}
    build_info = {"generated": catalog["generated"], "hub_commit": git_head(HUB_ROOT),
                  "fingerprint": os.environ.get("HUB_FINGERPRINT"), "sources": {}}
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    failures, total_mb = 0, 0.0

    for src, docs in sources:
        cid = src["id"]
        rep = Report(cid)
        if not docs.is_dir():
            rep.err(f"source directory not found: {docs}")
            rep.print(); failures += 1
            continue
        comp, origin = load_component(cid, docs, rep)
        if comp is not None:
            if comp.get("id") != cid:
                rep.err(f'component.json id {comp.get("id")!r} != sources.json id {cid!r}')
            validate_component(comp, docs, rep, exclude)
        if rep.errors:
            rep.print(); failures += 1
            print(f"✗ {cid}: skipped ({len(rep.errors)} errors)")
            if gha:
                print(f"::error title=hub component '{cid}' not published::" + " | ".join(rep.errors[:5]).replace("\n", " "))
            continue
        commit = src.get("commit") or git_head(docs)
        comp = normalize(comp, src, cfg, commit, origin)
        dst = out / "c" / cid
        if link:
            dst.symlink_to(docs.resolve(), target_is_directory=True)
            nfiles = -1
        else:
            nfiles = copy_tree(docs, dst, exclude)
        mb = size_report(docs, exclude, cfg.get("component_budget_mb", 1e9), rep)
        total_mb += mb
        comp["size_mb"] = round(mb, 1)
        (out / "data" / "components" / f"{cid}.json").write_text(json.dumps(comp, separators=(",", ":")))
        catalog["components"].append({
            "id": cid, "name": comp["name"], "title": comp["title"], "summary": comp.get("summary", ""),
            "repo": comp.get("repo"), "commit": commit, "origin": origin, "classic": comp.get("classic"),
            "generated": comp.get("generated"), "size_mb": comp["size_mb"],
            "families": [{"id": f["id"], "label": f["label"]} for f in comp.get("families", []) or []],
            "rows": compact_rows(comp),
        })
        build_info["sources"][cid] = {"repo": src.get("repo"), "commit": commit, "origin": origin,
                                      "designs": len(comp["designs"]), "size_mb": comp["size_mb"]}
        rep.print()
        if gha and mb > cfg.get("component_budget_mb", 1e9):
            print(f"::warning title=hub component '{cid}' over size budget::{mb:.0f} MB > {cfg.get('component_budget_mb')} MB (see BUILDERS.md §5)")
        print(f"✓ {cid}: {len(comp['designs'])} designs, {mb:.0f} MB, origin={origin}"
              + (f", {nfiles} files" if nfiles >= 0 else ", linked"))

    (out / "data" / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":")))
    (out / "data" / "build.json").write_text(json.dumps(build_info, indent=1))
    budget = cfg.get("budget_mb", 1000)
    print(f"\nsite: {len(catalog['components'])} components, {total_mb:.0f} MB of component files (budget {budget} MB)")
    if total_mb > budget:
        print(f"✗ total exceeds the {budget} MB GitHub Pages budget — slim down the largest components (see BUILDERS.md §5)")
        return 2
    if failures and strict:
        return 1
    return 0


def serve(directory: Path, port: int):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"\nserving {directory} at http://127.0.0.1:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


# ----------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate DOCS_DIR/hub/component.json")
    v.add_argument("docs", type=Path)
    v.add_argument("--id", help="component id (default: read from component.json / adapter name)")

    p = sub.add_parser("preview", help="build a one-component hub from DOCS_DIR and serve it")
    p.add_argument("docs", type=Path)
    p.add_argument("--id", help="component id (default: read from component.json)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--out", type=Path, help="output dir (default: a temp dir)")
    p.add_argument("--no-serve", action="store_true")

    b = sub.add_parser("build", help="assemble the full site")
    b.add_argument("--config", type=Path, default=HUB_ROOT / "sources.json")
    b.add_argument("--root", type=Path, required=True,
                   help="directory holding one checkout per source, named after the repo (e.g. ROOT/opa-gen-gemini4)")
    b.add_argument("--out", type=Path, default=HUB_ROOT / "_site")
    b.add_argument("--only", help="comma-separated component ids")
    b.add_argument("--link", action="store_true", help="symlink sources instead of copying (local preview only)")
    b.add_argument("--strict", action="store_true", help="exit non-zero if any component fails validation")
    b.add_argument("--serve", type=int, metavar="PORT", help="serve the result after building")

    a = ap.parse_args(argv)
    cfg = load_config(HUB_ROOT / "sources.json") if a.cmd != "build" else load_config(a.config)

    if a.cmd == "build":
        only = set(a.only.split(",")) if a.only else None
        sources = []
        for s in cfg["components"]:
            if only and s["id"] not in only:
                continue
            sources.append((s, a.root / s["repo"].split("/")[-1] / s.get("dir", "docs")))
        rc = build(cfg, sources, a.out, a.link, a.strict)
        if a.serve and rc in (0, 1):
            serve(a.out, a.serve)
        return rc

    docs = a.docs.resolve()
    cid = a.id
    native = docs / "hub" / "component.json"
    if not cid and native.is_file():
        cid = json.loads(native.read_text()).get("id")
    if not cid:
        ap.error("pass --id (no hub/component.json to read it from)")
    src = next((s for s in cfg["components"] if s["id"] == cid), {"id": cid, "repo": None})

    if a.cmd == "validate":
        rep = Report(cid)
        comp, origin = load_component(cid, docs, rep)
        if comp is not None:
            validate_component(comp, docs, rep, cfg.get("exclude", []))
            mb = size_report(docs, cfg.get("exclude", []), cfg.get("component_budget_mb", 1e9), rep)
        rep.print(limit=200)
        if rep.errors:
            print(f"✗ {cid}: {len(rep.errors)} errors, {len(rep.warnings)} warnings")
            return 1
        print(f"✓ {cid}: {len(comp['designs'])} designs valid (origin={origin}), "
              f"{mb:.0f} MB published, {len(rep.warnings)} warnings")
        return 0

    if a.cmd == "preview":
        out = a.out or Path(tempfile.mkdtemp(prefix="hub-preview-"))
        src = dict(src, commit=git_head(docs))
        rc = build(cfg, [(src, docs)], out, link=True, strict=True)
        if rc == 0 and not a.no_serve:
            serve(out, a.port)
        return rc


if __name__ == "__main__":
    sys.exit(main())
