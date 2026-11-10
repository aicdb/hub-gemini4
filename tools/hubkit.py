#!/usr/bin/env python3
"""hubkit — build, validate and preview the AICDB analog hub (schema aicdb-hub/2).

  validate DOCS_DIR [--id ID]    check a component export (DOCS_DIR/hub/component.json, or the
                                 output of the repo's hub/export.py) incl. pages, detail docs, blocks
  preview  DOCS_DIR [--id ID]    build a one-component hub and serve it on http://127.0.0.1:8000
  build    --root DIR            assemble the full site from every source in sources.json

What gets published: ONLY files referenced as hosted (`src` of blocks, pages, design detail docs,
`files.schematic`, `files.thumbnail`), plus WebP thumbnails rendered from every referenced GDS.
GDS files, netlists and other `file` references are NOT published; the site links to the raw
file in the (private) source repository at the exported commit.

Paths: "hub/..." resolves inside the export directory (docs/hub/ for a committed export, the
exporter's output dir otherwise); any other relative path resolves inside docs/.
Python >= 3.9 stdlib; thumbnails additionally need `pip install gdstk pillow`.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import fnmatch
import functools
import gzip
import hashlib
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

SCHEMA = "aicdb-hub/2"
STAGES = ("pre", "partial", "full")
HUB_ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HOSTED_FILE_KEYS = ("schematic", "thumbnail")
REPO_FILE_KEYS = ("gds", "netlist", "pex_netlist", "lvs_netlist", "data")
BLOCK_TYPES = {"section", "markdown", "note", "code", "stats", "kv", "image", "layout", "gallery",
               "downloads", "tabs", "table", "chart", "explorer"}
DEFAULT_THUMB_CACHE = Path(os.environ.get("HUB_THUMB_CACHE", Path.home() / ".cache" / "aicdb-hub" / "thumbs"))


# ----------------------------------------------------------------------------- reporting
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


def _excluded(rel: str, exclude) -> bool:
    for pat in exclude:
        if fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:])):
            return True
    return False


# ----------------------------------------------------------------------------- export access
class Export:
    """A loaded component export: component dict + where its files live."""

    def __init__(self, cid: str, docs: Path, hubdir: Path, comp: dict, origin: str, tmp=None):
        self.cid, self.docs, self.hubdir, self.comp, self.origin, self._tmp = cid, docs, hubdir, comp, origin, tmp

    def path(self, rel: str) -> Path:
        if rel.startswith("hub/"):
            return self.hubdir / rel[4:]
        return self.docs / rel

    def close(self):
        if self._tmp:
            self._tmp.cleanup()


def _run_export(script: Path, args: list[str], cid: str, rep: Report, label: str, origin: str, docs: Path) -> Export | None:
    script = script.resolve()        # it runs with cwd = its own directory, so never pass a relative path
    tmp = tempfile.TemporaryDirectory(prefix=f"hub-{cid}-")
    out = Path(tmp.name)
    # -I: isolated mode (no PYTHON* env, no user site-packages, script dir not implied) — exporters are stdlib only
    r = subprocess.run([sys.executable, "-I", str(script), *args(docs.resolve(), out.resolve())], capture_output=True, text=True,
                       cwd=str(script.parent))
    if r.returncode != 0 or not (out / "component.json").is_file():
        rep.err(f"{label} failed (exit {r.returncode}):\n{(r.stderr or r.stdout)[-3000:]}")
        tmp.cleanup()
        return None
    try:
        comp = json.loads((out / "component.json").read_text())
    except json.JSONDecodeError as e:
        rep.err(f"{label} output is not valid JSON: {e}")
        tmp.cleanup()
        return None
    return Export(cid or comp.get("id"), docs, out, comp, origin, tmp)


def load_export(cid: str | None, docs: Path, rep: Report, exporter: str = "hub/export.py") -> Export | None:
    """Order: committed docs/hub/component.json → the repo's own exporter (<repo>/hub/export.py, run
    isolated with --docs/--out into a fresh temp dir)."""
    native = docs / "hub" / "component.json"
    repo_exporter = docs.parent / exporter
    if not native.is_file() and repo_exporter.is_file():
        return _run_export(repo_exporter, lambda d, o: ["--docs", str(d), "--out", str(o)], cid, rep,
                           f"repo exporter {exporter}", "repo", docs)
    if native.is_file():
        try:
            comp = json.loads(native.read_text())
        except json.JSONDecodeError as e:
            rep.err(f"{native}: invalid JSON: {e}")
            return None
        return Export(cid or comp.get("id"), docs, docs / "hub", comp, "native")
    rep.err(f"no docs/hub/component.json and no {exporter} next to {docs} (see REPO_STANDARD.md)")
    return None


# ----------------------------------------------------------------------------- reference collection
class Refs:
    def __init__(self):
        self.hosted: dict[str, str] = {}     # rel path -> where it was referenced
        self.containers: list[tuple[str, str]] = []  # (rel path, where) — JSON docs holding blocks
        self.gds: dict[tuple[str, str], str] = {}    # (gds rel, cell) -> where
        self.repo: dict[str, str] = {}       # rel path -> where


def walk_blocks(blocks, where: str, refs: Refs, rep: Report, depth=0):
    if blocks is None:
        return
    if not isinstance(blocks, list):
        rep.err(f"{where}: blocks must be a list")
        return
    for i, b in enumerate(blocks):
        w = f"{where}[{i}]"
        if not isinstance(b, dict):
            rep.err(f"{w}: block must be an object")
            continue
        t = b.get("type")
        if t not in BLOCK_TYPES:
            rep.err(f"{w}: unknown block type {t!r} (known: {', '.join(sorted(BLOCK_TYPES))})")
            continue
        w = f"{w}<{t}{(':' + str(b.get('title'))[:40]) if b.get('title') else ''}>"
        if b.get("stage") is not None and b["stage"] not in STAGES:
            rep.err(f"{w}: stage must be one of {STAGES}")
        if "src" in b and t in ("image", "chart", "table", "explorer"):
            if not isinstance(b["src"], str):
                rep.err(f"{w}: src must be a string path")
            else:
                refs.hosted.setdefault(b["src"], w)
        if t == "image" and not (b.get("src") or b.get("gds")):
            rep.err(f"{w}: image needs src (hosted image) or gds")
        if t in ("image", "layout") and b.get("gds"):
            refs.gds.setdefault((b["gds"], b.get("cell") or ""), w)
            refs.repo.setdefault(b["gds"], w)
        if t == "layout" and not b.get("gds"):
            rep.err(f"{w}: layout needs gds")
        if t == "chart" and not (b.get("src") or isinstance(b.get("data"), list)):
            rep.err(f"{w}: chart needs data[] (Plotly traces) or src")
        if t == "table" and not (b.get("src") or isinstance(b.get("rows"), list)):
            rep.err(f"{w}: table needs rows[] or src")
        if t == "explorer" and not b.get("src"):
            rep.err(f"{w}: explorer needs src (columnar JSON)")
        if t == "gallery":
            for j, it in enumerate(b.get("items") or []):
                if it.get("src"):
                    refs.hosted.setdefault(it["src"], f"{w}.items[{j}]")
                elif it.get("gds"):
                    refs.gds.setdefault((it["gds"], it.get("cell") or ""), f"{w}.items[{j}]")
                    refs.repo.setdefault(it["gds"], f"{w}.items[{j}]")
                else:
                    rep.err(f"{w}.items[{j}]: needs src or gds")
        if t == "downloads":
            for j, it in enumerate(b.get("items") or []):
                if it.get("file"):
                    refs.repo.setdefault(it["file"], f"{w}.items[{j}]")
                elif it.get("src"):
                    refs.hosted.setdefault(it["src"], f"{w}.items[{j}]")
                elif not it.get("url"):
                    rep.err(f"{w}.items[{j}]: needs file (repo), src (hosted) or url")
        if t == "section":
            walk_blocks(b.get("blocks"), w, refs, rep, depth + 1)
        if t == "tabs":
            for j, tab in enumerate(b.get("tabs") or []):
                walk_blocks(tab.get("blocks"), f"{w}.tabs[{j}]", refs, rep, depth + 1)


def check_data_file(ex: Export, rel: str, where: str, rep: Report):
    """Light structural check of chart/table/explorer JSON referenced by src."""
    if not rel.endswith(".json"):
        return
    p = ex.path(rel)
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        rep.err(f"{where}: {rel} is not valid JSON ({e})")
        return
    if "<chart" in where and not isinstance(d.get("data"), list):
        rep.err(f"{where}: {rel} must be a Plotly figure {{data: [...], layout: {{...}}}}")
    if "<table" in where and not isinstance(d.get("rows"), list):
        rep.err(f"{where}: {rel} must contain rows[] (and optionally columns[])")
    if "<explorer" in where:
        cols = d.get("columns")
        if not (isinstance(cols, dict) or isinstance(d.get("rows"), list)):
            rep.err(f"{where}: {rel} must contain columns{{key: [...]}} (columnar) or rows[]")
        elif isinstance(cols, dict):
            lens = {len(v) for v in cols.values() if isinstance(v, list)}
            if len(lens) > 1:
                rep.err(f"{where}: {rel} columns have different lengths {sorted(lens)}")


# ----------------------------------------------------------------------------- validation
def validate(ex: Export, rep: Report, exclude=()) -> Refs:
    comp = ex.comp
    refs = Refs()
    if comp.get("schema") != SCHEMA:
        rep.err(f'"schema" must be "{SCHEMA}" (got {comp.get("schema")!r})')
    for k in ("id", "name", "title", "technology", "metrics", "designs"):
        if k not in comp:
            rep.err(f'missing top-level key "{k}"')
    if rep.errors:
        return refs
    if not ID_RE.match(str(comp["id"])):
        rep.err(f'bad component id {comp["id"]!r}')
    mkeys = set()
    for m in comp["metrics"] if isinstance(comp["metrics"], list) else []:
        if not isinstance(m, dict) or "key" not in m or "label" not in m:
            rep.err(f"metric needs key+label: {m!r}")
            continue
        if m["key"] in mkeys:
            rep.err(f'duplicate metric key {m["key"]!r}')
        mkeys.add(m["key"])
        if m.get("better") not in (None, "high", "low"):
            rep.err(f'metric {m["key"]}: better must be "high", "low" or absent')
    if not mkeys:
        rep.err('"metrics" must be a non-empty list')

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

    for j, b in enumerate(comp.get("builds_on") or []):
        if not (isinstance(b, dict) and b.get("id")):
            rep.err(f"builds_on[{j}]: needs id (+ optional role)")
    page_ids = set()
    for i, pg in enumerate(comp.get("pages", []) or []):
        w = f"pages[{i}]"
        if not isinstance(pg, dict) or not pg.get("id") or not pg.get("title"):
            rep.err(f"{w}: page needs id + title")
            continue
        if pg["id"] in page_ids:
            rep.err(f"{w}: duplicate page id {pg['id']!r}")
        page_ids.add(pg["id"])
        if pg.get("src"):
            refs.hosted.setdefault(pg["src"], w)
            refs.containers.append((pg["src"], f"page {pg['id']}"))
        elif isinstance(pg.get("blocks"), list):
            walk_blocks(pg["blocks"], f"page {pg['id']}", refs, rep)
        else:
            rep.err(f"{w}: page needs src (JSON with blocks) or inline blocks")

    designs = comp["designs"]
    if not isinstance(designs, list) or not designs:
        rep.err('"designs" must be a non-empty list')
        return refs
    seen = set()
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
        if not res and not d.get("na"):
            rep.err(f"{tag}: results{{}} is empty — need at least one of {STAGES} (or set \"na\": \"reason\" for a not-applicable placeholder)")
        for st, r in res.items():
            if st not in STAGES:
                rep.err(f"{tag}: unknown stage {st!r} (use {STAGES})")
                continue
            for mk, mv in (r.get("metrics") or {}).items():
                if mk not in mkeys:
                    if mv is not None:
                        rep.warn(f"{tag}: results.{st} has undeclared metric {mk!r} (ignored by UI)")
                elif mv is not None and not _is_num(mv):
                    rep.err(f"{tag}: results.{st}.metrics.{mk} must be number or null")
            for cnt in ("pvt", "mc"):
                c = r.get(cnt)
                if c is not None and not (isinstance(c, dict) and _is_num(c.get("pass")) and _is_num(c.get("total"))):
                    rep.err(f"{tag}: results.{st}.{cnt} must be {{pass, total}}")
        phys = d.get("physical") or {}
        for k in ("drc", "lvs", "pex"):
            ok = (True, False, None, "partial") if k == "pex" else (True, False, None)
            if k in phys and phys[k] not in ok:
                rep.err(f"{tag}: physical.{k} must be true/false/null" + (' or "partial"' if k == 'pex' else ''))
        files = d.get("files") or {}
        if "layout" in files:
            rep.err(f"{tag}: files.layout is not supported in aicdb-hub/2 — give files.gds (thumbnail is rendered)")
        for k in HOSTED_FILE_KEYS:
            if files.get(k):
                refs.hosted.setdefault(files[k], f"{tag}.files.{k}")
        for k in REPO_FILE_KEYS:
            if files.get(k):
                refs.repo.setdefault(files[k], f"{tag}.files.{k}")
        if files.get("gds"):
            refs.gds.setdefault((files["gds"], ""), f"{tag}.files.gds")
        for j, im in enumerate(d.get("images") or []):
            if im.get("src"):
                refs.hosted.setdefault(im["src"], f"{tag}.images[{j}]")
            elif im.get("gds"):
                refs.gds.setdefault((im["gds"], im.get("cell") or ""), f"{tag}.images[{j}]")
                refs.repo.setdefault(im["gds"], f"{tag}.images[{j}]")
            else:
                rep.err(f"{tag}.images[{j}]: needs src or gds")
        for j, it in enumerate(d.get("downloads") or []):
            if it.get("file"):
                refs.repo.setdefault(it["file"], f"{tag}.downloads[{j}]")
            elif it.get("src"):
                refs.hosted.setdefault(it["src"], f"{tag}.downloads[{j}]")
            elif not it.get("url"):
                rep.err(f"{tag}.downloads[{j}]: needs file, src or url")
        if d.get("detail"):
            refs.hosted.setdefault(d["detail"], f"{tag}.detail")
            refs.containers.append((d["detail"], f"{tag}.detail"))
        for j, u in enumerate(d.get("uses") or []):
            if not (isinstance(u, dict) and u.get("component") and u.get("design")):
                rep.err(f"{tag}.uses[{j}]: needs component + design (+ optional role)")

    # container docs (pages, design details): parse and walk their blocks
    for rel, where in refs.containers:
        p = ex.path(rel)
        if not p.is_file():
            continue  # reported below as a missing hosted file
        try:
            doc = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            rep.err(f"{where}: {rel} invalid JSON: {e}")
            continue
        if not isinstance(doc.get("blocks"), list):
            rep.err(f"{where}: {rel} must be an object with blocks[]")
            continue
        walk_blocks(doc["blocks"], f"{where}:{rel}", refs, rep)

    # existence checks
    missing = 0
    for rel, where in refs.hosted.items():
        if rel.startswith(("/", "http:", "https:")) or ".." in rel.split("/"):
            rep.err(f"{where}: hosted path must be relative inside the export/docs: {rel!r}")
            continue
        if not ex.path(rel).is_file():
            missing += 1
            if missing <= 15:
                rep.err(f"{where}: hosted file not found: {rel}")
        elif _excluded(rel, exclude):
            rep.err(f"{where}: {rel} matches the hub's exclude patterns and cannot be hosted")
    if missing > 15:
        rep.err(f"... {missing} hosted files missing in total")
    for rel, where in list(refs.hosted.items()):
        if "<" in where and ex.path(rel).is_file():
            check_data_file(ex, rel, where, rep)
    rmissing = 0
    for rel, where in refs.repo.items():
        if rel.startswith("hub/"):
            rep.err(f"{where}: repo file references must be docs-relative, not hub/: {rel}")
        elif not (ex.docs / rel).is_file():
            rmissing += 1
            if rmissing <= 10:
                rep.warn(f"{where}: repo file not found in docs/ (link would be dead): {rel}")
    for (g, _cell), where in refs.gds.items():
        if not g.endswith((".gds", ".gds.gz", ".gdsii")):
            rep.err(f"{where}: gds must point to a .gds or .gds.gz file: {g}")
    return refs


# ----------------------------------------------------------------------------- thumbnails
def _thumb_job(args):
    gds, cell, tech, cache_dir = args
    sys.path.insert(0, str(HUB_ROOT / "tools"))
    import gdsthumb  # noqa: E402
    key = gdsthumb.cache_key(Path(gds), cell or None, 960, tech)
    img, meta = Path(cache_dir) / f"{key}.webp", Path(cache_dir) / f"{key}.json"
    if img.is_file() and meta.is_file():
        return key, json.loads(meta.read_text()), None
    try:
        info = gdsthumb.render(Path(gds), img, cell or None, 960, tech)
        tmp = meta.with_name(f".{meta.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(info))
        os.replace(tmp, meta)
        return key, info, None
    except Exception as e:  # noqa: BLE001
        return key, None, f"{type(e).__name__}: {e}"


def render_thumbs(ex: Export, refs: Refs, cache_dir: Path, rep: Report, jobs: int) -> tuple[dict, dict[str, bytes]]:
    if not refs.gds:
        return {}, {}
    try:
        import gdstk  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        rep.warn("gdstk/Pillow not installed — layout thumbnails skipped (pip install gdstk pillow)")
        return {}, {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    default_tech = ex.comp.get("technology", "gf180mcuD")
    gds_tech = {d.get("files", {}).get("gds"): d.get("technology") or default_tech
                for d in ex.comp.get("designs", []) if d.get("files", {}).get("gds")}
    tasks, keys = [], []
    for (g, cell), where in refs.gds.items():
        p = ex.docs / g
        if not p.is_file():
            rep.warn(f"{where}: GDS not found for thumbnail: {g}")
            continue
        tasks.append((str(p), cell, gds_tech.get(g, default_tech), str(cache_dir)))
        keys.append((g, cell))
    thumbs = {}
    blobs: dict[str, bytes] = {}
    with cf.ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        for (g, cell), (key, info, err) in zip(keys, pool.map(_thumb_job, tasks, chunksize=4)):
            if err:
                rep.warn(f"thumbnail failed for {g}{' cell ' + cell if cell else ''}: {err}")
                continue
            raw_webp = (cache_dir / f"{key}.webp").read_bytes()
            wkey = hashlib.sha1(raw_webp).hexdigest()[:16]
            rel_t = f"thumbs/{wkey}.webp"
            if rel_t not in blobs:
                blobs[rel_t] = json.dumps(base64.b64encode(raw_webp).decode("ascii")).encode("ascii")
            thumbs[f"{g}|{cell}"] = {"src": rel_t, "cell": info.get("cell"),
                                     "width_um": info.get("width_um"), "height_um": info.get("height_um")}
    return thumbs, blobs


# ----------------------------------------------------------------------------- normalization
def normalize(ex: Export, src: dict, commit: str | None, shard_base: str = "") -> dict:
    comp = dict(ex.comp)
    comp.setdefault("repo", src.get("repo"))
    comp["commit"] = commit or comp.get("commit")
    comp["origin"] = ex.origin
    comp["base"] = f"{shard_base}c/{comp['id']}/"
    if comp.get("repo") and comp["commit"]:
        comp["repo_raw"] = f"https://github.com/{comp['repo']}/raw/{comp['commit']}/{src.get('dir', 'docs')}/"
    tech_default = comp.get("technology")
    for d in comp["designs"]:
        d.setdefault("technology", tech_default)
        d.setdefault("axes", {})
        d.setdefault("tags", [])
        d.setdefault("physical", {})
        d.setdefault("files", {})
        d.setdefault("results", {})
        for st in list(d.get("results", {})):
            d["results"][st].setdefault("metrics", {})
    if not comp.get("card_metrics"):
        comp["card_metrics"] = [m["key"] for m in comp["metrics"][:4]]
    return comp


def compact_rows(comp: dict) -> list:
    """Per-design summary for the overview: [tech, vdd, family, stageMask, physOk, robustMask, verMask]
    (verMask: stages that carry a robust verdict, for per-field fallback)."""
    rows = []
    for d in comp["designs"]:
        mask = robust = ver = 0
        for i, st in enumerate(STAGES):
            r = d["results"].get(st)
            if r is not None:
                mask |= 1 << i
                if r.get("robust") is not None:
                    ver |= 1 << i
                if r.get("robust"):
                    robust |= 1 << i
        ph = d.get("physical", {})
        rows.append([d["technology"], d.get("vdd"), d.get("family"), mask, 1 if (ph.get("drc") and ph.get("lvs")) else 0, robust, ver])
    return rows


def git_head(path: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- build
def publish_files(ex: Export, refs: Refs, dst: Path, link: bool, extra_blobs: dict[str, bytes] | None = None) -> tuple[int, int, list[list[str]]]:
    n = size = bsz = 0
    packs: list[list[str]] = []
    batch: list[tuple[str, bytes]] = []

    def flush():
        nonlocal n, size, bsz
        if not batch:
            return
        raw = b"{" + b",".join(json.dumps(r).encode() + b":" + b for r, b in batch) + b"}"
        comp_bytes = gzip.compress(raw, compresslevel=6, mtime=0)
        q = dst / f"_pack_{len(packs)}.bin"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes(comp_bytes)
        packs.append([r for r, _ in batch])
        batch.clear()
        bsz = 0
        n += 1
        size += len(comp_bytes)

    if extra_blobs:
        for rel, b in sorted(extra_blobs.items()):
            if batch and bsz + len(b) > 8_000_000:
                flush()
            batch.append((rel, b))
            bsz += len(b)
        flush()

    for rel in sorted(refs.hosted):
        sp = ex.path(rel)
        if not sp.is_file():
            continue
        if (rel.endswith(".json") or rel.endswith(".svg")) and "downloads" not in refs.hosted.get(rel, ""):
            b = sp.read_bytes().strip()
            if rel.endswith(".svg"):
                b = json.dumps(b.decode("utf-8", errors="replace")).encode("utf-8")
            if batch and bsz + len(b) > 8_000_000:
                flush()
            batch.append((rel, b))
            bsz += len(b)
            continue
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if q.exists() or q.is_symlink():
            q.unlink()
        if link and ex.origin == "native":
            q.symlink_to(sp.resolve())
        else:
            shutil.copy2(sp, q)
        n += 1
        size += sp.stat().st_size
    flush()
    return n, size, packs


def expand_manifest(ex: Export, source_id: str, rep: Report) -> list[tuple[Export, str | None]]:
    """A source may export several components: docs/hub/component.json is then a manifest
    {"schema", "id": <source id>, "group": "<nav group label>", "components": ["hub/<x>/component.json", ...]}.
    Each listed component is a full component whose id starts with "<source id>-"."""
    m = ex.comp
    if "components" not in m:
        return [(ex, None)]
    if m.get("schema") != SCHEMA:
        rep.err(f'manifest "schema" must be "{SCHEMA}"')
    if m.get("id") != source_id:
        rep.err(f'manifest id {m.get("id")!r} != sources.json id {source_id!r}')
    out, seen = [], set()
    for rel in m.get("components") or []:
        p = ex.path(rel)
        try:
            sub = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            rep.err(f"manifest entry {rel}: cannot read ({e})")
            continue
        sid = sub.get("id", "")
        if not str(sid).startswith(f"{source_id}-"):
            rep.err(f"manifest entry {rel}: component id {sid!r} must start with '{source_id}-'")
            continue
        if sid in seen:
            rep.err(f"manifest: duplicate component id {sid!r}")
            continue
        seen.add(sid)
        out.append((Export(sid, ex.docs, ex.hubdir, sub, ex.origin), m.get("group")))
    if not out:
        rep.err("manifest lists no components")
    return out


def build_one(cfg, src, ex: Export, group, commit, out, link, cache_dir, jobs, catalog, build_info, gha) -> tuple[bool, int]:
    cid = ex.cid
    rep = Report(cid)
    exclude = cfg.get("exclude", [])
    if group is None and ex.comp.get("id") != src["id"]:
        rep.err(f'component.json id {ex.comp.get("id")!r} != sources.json id {src["id"]!r}')
    refs = validate(ex, rep, exclude)
    if rep.errors:
        rep.print()
        print(f"✗ {cid}: skipped ({len(rep.errors)} errors)")
        if gha:
            print(f"::error title=hub component '{cid}' not published::" + " | ".join(rep.errors[:5]).replace("\n", " "))
        return False, 0
    shard_id = src.get("shard") if not link else None
    shard_cfg = (cfg.get("shards") or {}).get(shard_id) if shard_id else None
    shard_base = shard_cfg.get("base", "") if shard_cfg else ""
    comp = normalize(ex, src, commit, shard_base=shard_base)
    if shard_cfg and shard_cfg.get("path"):
        shard_root = HUB_ROOT / shard_cfg["path"]
        shard_root.mkdir(parents=True, exist_ok=True)
        (shard_root / ".nojekyll").write_text("")
        dst = shard_root / "c" / cid
        if dst.exists():
            shutil.rmtree(dst)
    else:
        dst = out / "c" / cid
    comp["thumbs"], thumb_blobs = render_thumbs(ex, refs, cache_dir, rep, jobs)
    nt = len(thumb_blobs)
    nfiles, size, packs = publish_files(ex, refs, dst, link, extra_blobs=thumb_blobs)
    if packs:
        comp["packs"] = packs
    mb = size / 1e6
    comp["size_mb"] = round(mb, 1)
    comp["group"] = group
    comp["source"] = src["id"]
    if mb > cfg.get("component_budget_mb", 1e9):
        rep.warn(f"hosted size {mb:.0f} MB exceeds the per-component budget of {cfg.get('component_budget_mb')} MB")
        if gha:
            print(f"::warning title=hub component '{cid}' over size budget::{mb:.0f} MB")
    (out / "data" / "components" / f"{cid}.json").write_text(json.dumps(comp, separators=(",", ":"), ensure_ascii=False))
    catalog["components"].append({
        "id": cid, "name": comp["name"], "title": comp["title"], "summary": comp.get("summary", ""),
        "group": group, "source": src["id"],
        "repo": comp.get("repo"), "commit": commit, "origin": ex.origin,
        "generated": comp.get("generated"), "size_mb": comp["size_mb"],
        "families": [{"id": f["id"], "label": f["label"]} for f in comp.get("families", []) or []],
        "pages": [{"id": p["id"], "title": p["title"]} for p in comp.get("pages") or []],
        "rows": compact_rows(comp),
    })
    build_info["sources"][cid] = {"repo": src.get("repo"), "source": src["id"], "commit": commit, "origin": ex.origin,
                                  "designs": len(comp["designs"]), "pages": len(comp.get("pages") or []),
                                  "hosted_files": nfiles, "thumbnails": nt, "size_mb": comp["size_mb"]}
    rep.print()
    print(f"✓ {cid}: {len(comp['designs'])} designs, {len(comp.get('pages') or [])} pages, "
          f"{nfiles} hosted files + {nt} thumbnails, {mb:.1f} MB, origin={ex.origin}")
    return True, size


def link_hierarchy(out: Path, catalog: dict):
    """Resolve design-level `uses` across components, build reverse `used_by`, and the component graph."""
    aliases = {"aux-cml_ro": "aux-ro", "aux-cml_dco_vco": "aux-dco_vco"}
    comps = {}
    for c in catalog["components"]:
        f = out / "data" / "components" / f"{c['id']}.json"
        comps[c["id"]] = (f, json.loads(f.read_text()))
    groups = {}
    for cid, (_, comp) in comps.items():
        if comp.get("group"):
            groups.setdefault(comp.get("source"), []).append(cid)
        for b in comp.get("builds_on") or []:
            if b.get("id") in aliases:
                b["id"] = aliases[b["id"]]
        for d in comp["designs"]:
            for u in d.get("uses") or []:
                if u.get("component") in aliases:
                    u["component"] = aliases[u["component"]]
    titles = {cid: {d["id"]: d["title"] for d in comp["designs"]} for cid, (_, comp) in comps.items()}
    edges = {}   # (from, to) -> {roles:set, users:set, targets:set, declared:bool}
    dangling = 0
    for cid, (_, comp) in comps.items():
        used_cids = {u.get("component") for d in comp["designs"] for u in d.get("uses") or [] if u.get("component") in comps}
        for b in comp.get("builds_on") or []:
            if b["id"] in comps:
                targets = [b["id"]]
            else:
                grp = groups.get(b["id"], [])
                targets = [t for t in grp if t in used_cids] or grp
            for to in targets:
                e = edges.setdefault((cid, to), {"roles": set(), "users": set(), "targets": set(), "declared": False})
                e["declared"] = True
                if b.get("role") and (b["id"] in comps or not any(u.get("component") == to and u.get("role") for d in comp["designs"] for u in d.get("uses") or [])):
                    e["roles"].add(b["role"])
        for d in comp["designs"]:
            for u in d.get("uses") or []:
                to, tid = u.get("component"), u.get("design")
                if to not in comps or tid not in titles[to]:
                    dangling += 1
                    if dangling <= 12:
                        print(f"  [warn] {cid}/{d['id']}: uses {to}/{tid} which is not in the hub")
                    u["missing"] = True
                    continue
                u["title"] = titles[to][tid]
                u["component_name"] = comps[to][1]["name"]
                tgt = comps[to][1].setdefault("used_by", {}).setdefault(tid, [])
                tgt.append({"component": cid, "component_name": comp["name"], "design": d["id"], "title": d["title"], "role": u.get("role")})
                e = edges.setdefault((cid, to), {"roles": set(), "users": set(), "targets": set(), "declared": False})
                e["users"].add(d["id"]); e["targets"].add(tid)
                if u.get("role"):
                    e["roles"].add(u["role"])
    if dangling > 12:
        print(f"  [warn] ... {dangling} unresolved cross-component uses in total")
    for cid, (f, comp) in comps.items():
        comp["builds_on_resolved"] = [{"id": to, "roles": sorted(e["roles"]), "users": len(e["users"]), "targets": len(e["targets"])}
                                      for (fr, to), e in sorted(edges.items()) if fr == cid]
        comp["used_in"] = [{"id": fr, "roles": sorted(e["roles"]), "users": len(e["users"]), "targets": len(e["targets"])}
                           for (fr, to), e in sorted(edges.items()) if to == cid]
        f.write_text(json.dumps(comp, separators=(",", ":"), ensure_ascii=False))
    catalog["graph"] = [{"from": fr, "to": to, "roles": sorted(e["roles"]), "users": len(e["users"]), "targets": len(e["targets"])}
                        for (fr, to), e in sorted(edges.items())]
    if catalog["graph"]:
        print(f"hierarchy: {len(catalog['graph'])} component edges, "
              f"{sum(e['users'] for e in catalog['graph'])} design-level reuse links")


def link_foundations(cfg: dict, catalog: dict):
    """Bottom tier of the block hierarchy: technology-level foundations (PDK primitive devices, standard
    cells) declared in sources.json `foundations`, with the components that build on them.
    `used_by` keys are component ids or source ids (a source id covers every component of a collection;
    a component id given as well overrides that role)."""
    built = {c["id"] for c in catalog["components"]}
    configured = {s["id"] for s in cfg.get("components") or []}
    by_source: dict[str, list[str]] = {}
    for c in catalog["components"]:
        by_source.setdefault(c["source"], []).append(c["id"])
    tiers = []
    for f in cfg.get("foundations") or []:
        roles: dict[str, str] = {}
        used = f.get("used_by") or {}
        for key, role in used.items():            # collections first …
            if key not in built:
                for cid in by_source.get(key, []):
                    roles[cid] = role
        for key, role in used.items():            # … then single components override
            if key in built:
                roles[key] = role
        # a key of a source left out of this build (`--only`, `preview`) is fine; warn only about typos
        unknown = [k for k in used if k not in built and k not in by_source and k not in configured
                   and not any(k.startswith(f"{s}-") and s not in by_source for s in configured)]
        if unknown:
            print(f"  [warn] foundation {f.get('id')}: used_by names no component of this build "
                  f"(a typo, or not exported yet): {', '.join(unknown)}")
        users = [{"component": c["id"], "role": roles[c["id"]]} for c in catalog["components"] if c["id"] in roles]
        tiers.append({k: f[k] for k in ("id", "name", "title", "technology") if k in f} | {"users": users})
    catalog["foundations"] = tiers
    if tiers:
        print("foundations: " + ", ".join(f"{t['name']} ← {len(t['users'])} component{'' if len(t['users']) == 1 else 's'}" for t in tiers))


def build(cfg: dict, sources: list[tuple[dict, Path]], out: Path, link: bool, strict: bool,
          cache_dir: Path, jobs: int) -> int:
    exclude = cfg.get("exclude", [])
    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "components").mkdir(parents=True)
    (out / "c").mkdir()
    shutil.copytree(HUB_ROOT / "web", out, dirs_exist_ok=True)
    (out / ".nojekyll").write_text("")
    catalog = {"schema": SCHEMA, "site": cfg.get("site", {}), "technologies": cfg.get("technologies", {}),
               "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "components": []}
    build_info = {"generated": catalog["generated"], "hub_commit": git_head(HUB_ROOT),
                  "fingerprint": os.environ.get("HUB_FINGERPRINT"), "sources": {}}
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    failures, total = 0, 0

    for src, docs in sources:
        cid = src["id"]
        rep = Report(cid)
        if not docs.is_dir():
            rep.err(f"source directory not found: {docs}")
            rep.print(); failures += 1
            continue
        ex = load_export(cid, docs, rep, src.get("exporter", "hub/export.py"))
        if ex is None:
            rep.print(); failures += 1
            print(f"✗ {cid}: skipped")
            if gha:
                print(f"::error title=hub component '{cid}' not published::" + " | ".join(rep.errors[:5]).replace("\n", " "))
            continue
        try:
            subs = expand_manifest(ex, cid, rep)
            if rep.errors:
                rep.print(); failures += 1
                print(f"✗ {cid}: manifest invalid")
                continue
            commit = src.get("commit") or git_head(docs)
            for sub, group in subs:
                ok, size = build_one(cfg, src, sub, group, commit, out, link, cache_dir, jobs, catalog, build_info, gha)
                total += size
                failures += 0 if ok else 1
        finally:
            ex.close()

    link_hierarchy(out, catalog)
    link_foundations(cfg, catalog)
    (out / "data" / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":"), ensure_ascii=False))
    (out / "data" / "build.json").write_text(json.dumps(build_info, indent=1))
    budget = cfg.get("budget_mb", 1000)
    print(f"\nsite: {len(catalog['components'])} components, {total / 1e6:.0f} MB hosted (budget {budget} MB)")
    if total / 1e6 > budget:
        print(f"✗ total exceeds the {budget} MB budget")
        return 2
    if not catalog["components"]:
        print("✗ no component could be built — refusing to produce an empty site")
        return 3
    if failures and strict:
        return 1
    return 0


def serve(directory: Path, port: int):
    cfg = json.loads((HUB_ROOT / "sources.json").read_text()) if (HUB_ROOT / "sources.json").is_file() else {}
    shards = {s["base"]: (HUB_ROOT / s["path"]).resolve()
              for s in (cfg.get("shards") or {}).values() if s.get("base") and s.get("path")}

    class ShardHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            for base, sroot in shards.items():
                if path.startswith(base):
                    rel = path[len(base):].split("?", 1)[0].split("#", 1)[0]
                    return str(sroot / rel)
            return super().translate_path(path)

    handler = functools.partial(ShardHandler, directory=str(directory))
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
    v = sub.add_parser("validate", help="validate a component export")
    v.add_argument("docs", type=Path)
    v.add_argument("--id")
    p = sub.add_parser("preview", help="build a one-component hub and serve it")
    p.add_argument("docs", type=Path)
    p.add_argument("--id")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--out", type=Path)
    p.add_argument("--no-serve", action="store_true")
    b = sub.add_parser("build", help="assemble the full site")
    b.add_argument("--config", type=Path, default=HUB_ROOT / "sources.json")
    b.add_argument("--root", type=Path, required=True, help="dir with one checkout per source repo, named like the repo")
    b.add_argument("--out", type=Path, default=HUB_ROOT / "_site")
    b.add_argument("--only", help="comma-separated component ids")
    b.add_argument("--link", action="store_true", help="symlink hosted files of native exports (local preview)")
    b.add_argument("--strict", action="store_true")
    b.add_argument("--serve", type=int, metavar="PORT")
    for x in (p, b):
        x.add_argument("--thumb-cache", type=Path, default=DEFAULT_THUMB_CACHE)
        x.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args(argv)
    cfg = json.loads((a.config if a.cmd == "build" else HUB_ROOT / "sources.json").read_text())

    if a.cmd == "build":
        only = set(a.only.split(",")) if a.only else None
        sources = [(s, a.root.resolve() / s["repo"].split("/")[-1] / s.get("dir", "docs"))
                   for s in cfg["components"] if not only or s["id"] in only]
        rc = build(cfg, sources, a.out, a.link, a.strict, a.thumb_cache, a.jobs)
        if a.serve and rc in (0, 1):
            serve(a.out, a.serve)
        return rc

    docs = a.docs.resolve()
    cid = a.id
    native = docs / "hub" / "component.json"
    if not cid and native.is_file():
        cid = json.loads(native.read_text()).get("id")
    if not cid and (docs.parent / "hub" / "export.py").is_file():
        # the repository's own exporter knows its id: run it once to find out
        probe = load_export(None, docs, Report("probe"))
        if probe is not None:
            cid = probe.cid
            probe.close()
    if not cid:
        ap.error("pass --id (no docs/hub/component.json and no hub/export.py to read it from)")
    src = next((s for s in cfg["components"] if s["id"] == cid), {"id": cid, "repo": None, "dir": "docs"})

    if a.cmd == "validate":
        rep = Report(cid)
        ex = load_export(cid, docs, rep)
        if ex is None:
            rep.print(limit=300)
            print(f"✗ {cid}: export could not be loaded")
            return 1
        rc = 0
        try:
            subs = expand_manifest(ex, cid, rep)
            if rep.errors:
                rep.print(limit=300)
                print(f"✗ {cid}: manifest invalid")
                return 1
            for sub, group in subs:
                r2 = Report(sub.cid)
                if group is None and sub.comp.get("id") != cid:
                    r2.err(f'component.json id {sub.comp.get("id")!r} != {cid!r}')
                refs = validate(sub, r2, cfg.get("exclude", []))
                hosted = sum(sub.path(r).stat().st_size for r in refs.hosted if sub.path(r).is_file())
                r2.print(limit=300)
                if r2.errors:
                    print(f"✗ {sub.cid}: {len(r2.errors)} errors, {len(r2.warnings)} warnings")
                    rc = 1
                    continue
                npages = len(sub.comp.get("pages") or [])
                ndetail = sum(1 for d in sub.comp["designs"] if d.get("detail"))
                print(f"✓ {sub.cid}{f' [{group}]' if group else ''}: {len(sub.comp['designs'])} designs ({ndetail} with detail docs), {npages} pages, "
                      f"{len(refs.hosted)} hosted files ({hosted / 1e6:.1f} MB) + {len(refs.gds)} layout thumbnails, "
                      f"{len(refs.repo)} repo-linked files, origin={sub.origin}, {len(r2.warnings)} warnings")
        finally:
            ex.close()
        return rc

    out = a.out or Path(tempfile.mkdtemp(prefix="hub-preview-"))
    src = dict(src, commit=git_head(docs))
    rc = build(cfg, [(src, docs)], out, link=True, strict=True, cache_dir=a.thumb_cache, jobs=a.jobs)
    if rc == 0 and not a.no_serve:
        serve(out, a.port)
    return rc


if __name__ == "__main__":
    sys.exit(main())
