# Generator repository standard

Every `*-gen-*` generator repository follows this layout and exposes the same commands, so
anyone (person or agent) can work on any generator in the same way. The published website
lives only in the hub ([BUILDERS.md](BUILDERS.md)); generator repositories contain no website.

## 1. Layout

```
<name>-gen-<variant>/
├── README.md          what the generator does, layout, quick start, design-point workflow, publishing
├── AGENTS.md          instructions for coding agents (canonical; tool-specific files such as
│                      GEMINI.md, where they exist, only point here)
├── Makefile           the uniform command interface (§3)
├── points.json        the design-point registry: the single source of truth for what is delivered (§2)
├── <pkg>/             the generator package (sizing, netlisting, layout, simulation, …)
│   └── registry.py    reads points.json for the pipeline (template, identical everywhere)
├── scripts/
│   ├── points.py      add / remove / list / show / check design points (template, identical everywhere)
│   ├── points_hook.py repository-specific id/validation rules for points.py (optional)
│   ├── build.py       (re)build design points through the generator pipeline (§5)
│   └── …              other repository-specific tools
├── hub/
│   ├── export.py      writes the hub export (docs/hub/**) from docs/ + points.json (stdlib only)
│   ├── *.py           exporter helpers
│   ├── content/       prose shown on the hub (methodology, notes) as Markdown
│   └── INVENTORY.md   what the retired website showed and where it lives on the hub
├── docs/              published data, read by the hub (no HTML/JS/CSS)
│   ├── data/          component-level data (indexes, sweeps, design-space data)
│   ├── designs/<id>/  per-design artefacts: *.gds.gz, netlists, schematic SVGs, evidence JSON
│   └── subblocks/<source>/  files shared by many designs (e.g. sibling-library schematics), once
├── build/             intermediate outputs and raw simulation results (git-ignored)
├── .gitignore         starts with templates/gitignore (common block), then repository lines
└── .github/workflows/hub-check.yml   validates the hub export on every push
```

Nothing else is tracked at the top level, except an optional `ref/` with reference papers and
datasheets. Code lives in `<pkg>/` and `scripts/`; raw farm results, layout working files and
caches live in `build/`. A tool-specific instruction file (e.g.
`GEMINI.md`) is optional; if present it is exactly `templates/GEMINI.md` (one line importing AGENTS.md).

- `docs/designs/<id>/` is the default folder of a point. A repository may group folders
  differently (e.g. `docs/designs/<load>/<card>/`, or one folder per topology) when
  `points_hook.artefact_dirs()` says so; folders that are not points are listed in `ignore_dirs()`.
- A file that many designs share is stored once under `docs/subblocks/<source>/` and referenced
  from each design, never copied into every design folder.
- Artefact names for new generators: `data.json` (evidence), `<id>.gds.gz`, `schematic.svg`,
  `netlist.spice`, `lvs_reference.spice`, `pex.spice`. Existing repositories keep their names
  (the hub links them).

`docs/hub/` is generated (`make hub`) and git-ignored. The hub's CI runs `hub/export.py`
itself, so the repository only needs to keep `docs/` and `hub/` up to date.

## 2. Design-point registry (`points.json`)

```jsonc
{
  "schema": "aicdb-points/1",
  "component": "opa",                                   // hub component id
  "id_format": "{arch}_{vdd_tag}_{iclass}_{regime}",    // how ids are formed (documentation)
  "hook": "scripts/points_hook.py",                      // the repository's rules (documentation)
  "notes": "…",                                          // optional: how ids / fields are to be read
  "fields": {                                           // the parameter space of one design point
    "arch":   { "label": "Architecture", "values": ["nmos_5t", "miller", "…"], "doc": "optional explanation" },
    "vdd":    { "label": "Supply (V)",   "values": [1.8, 3.3] },
    "iclass": { "label": "Current class", "values": ["0p1u_1u", "1u_10u", "10u_100u"] }
  },
  "points": [
    { "id": "miller_1v8_1u_10u_weak", "arch": "miller", "vdd": 1.8, "iclass": "1u_10u", "regime": "weak" },
    { "id": "…", "…": "…", "publish": false, "note": "kept for reference, not delivered" }
  ]
}
```

- `points` lists every deliverable design point. The generator pipeline builds exactly
  these, and the hub export publishes exactly these (unless `"publish": false`).
- A point has its field values, a stable `id` (used in URLs and folder names), and optional
  `publish`, `note` and repository-specific settings (e.g. targets, knobs).
- `fields.*.label` is a human-readable name (no code paths; put those in `fields.*.doc`).
- `fields.*.values` documents the allowed values. `scripts/points.py add` validates against it
  (`--allow-new` extends a field when the generator supports a new value).
- Collections of several small generators (e.g. `aux`) add a `family` field; `points_hook.fields_for()`
  returns the field spec of the point's family.
- Generator code never hard-codes the deliverable set: loops over architectures × supplies × classes
  are replaced by `registry.points()`. The parameter space (what *can* be generated) stays in code.

## 3. Commands (identical in every repository)

| command | does |
|---|---|
| `make points` | list the design points (`python3 scripts/points.py list`) |
| `make add POINT="arch=miller vdd=1.8 …"` | add a point to the registry (validated, id derived) |
| `make remove POINT=<id>` | remove a point (`PURGE=1` also deletes `docs/designs/<id>/`) |
| `make build POINT=<id>` | run the generator pipeline for one point (`make build` = all points) |
| `make docs` | regenerate `docs/` from existing build outputs for the registered points |
| `make hub` | write `docs/hub/` and validate it with the hub's `hubkit` |
| `make preview` | build a local hub preview of this repository (http://127.0.0.1:8000) |
| `make check` | registry ↔ docs consistency (missing artefacts, orphan folders) |

Typical change:

```bash
make add POINT="arch=miller vdd=3.3 iclass=1u_10u regime=weak"
make build POINT=miller_3v3_1u_10u_weak     # sizing → simulation → layout → DRC/LVS → PEX → docs
make hub && make preview                    # check it on the hub locally
git add points.json docs && git commit -m "Add Miller 3.3 V 1–10 µA weak-inversion op-amp" && git push
gh workflow run publish.yml -R aicdb/hub-gemini4   # publish now (otherwise within 6 h)
```

Removing a point: `make remove POINT=<id> PURGE=1 && make docs && make hub`, then commit.

`HUB` (default `../hub-gemini4`) points at a checkout of the hub repository for `make hub` /
`make preview`.

## 4. Templates

Copy these from the hub repository unchanged: `templates/scripts/points.py`, `templates/Makefile`,
`templates/registry.py` (into the package) and `templates/.github/workflows/hub-check.yml`;
`templates/GEMINI.md` too, if the repository keeps a tool-specific pointer file.

Start from these and fill them in: `templates/gitignore` (the common block heads `.gitignore`),
`templates/README.md` and `templates/AGENTS.md` (§7).

## 5. `scripts/build.py` contract

```
python3 scripts/build.py --point ID [--point ID …] | --all
                         [--stages s1,s2,…] [--dry-run] [--force]
python3 scripts/build.py --docs-only [--point ID …]
```

- Runs the existing pipeline stages for the selected registered points, in order (typically
  sizing → simulation → layout → DRC/LVS → PEX → post-layout simulation → docs). Stages that
  can only run in batch run for the selected points only; stages that are already done for a point
  are skipped unless `--force`.
- `--dry-run` prints the plan (stages × points, external tools / compute farm needed) and runs nothing.
- `--docs-only` regenerates `docs/` from existing build outputs for the registered points (and
  removes published data of points that are no longer registered).
- `--stages` lists the stage names it accepts in `--help`, which starts by citing this section.
- `--point` may be repeated and takes comma-separated ids; `--all` and `--point` exclude each
  other. Unknown points or stages and registry errors (the rules of `make check`) stop the run
  before anything is done, with exit status 2.
- `--force` redoes the selected points' stages. Stages that work on the whole component
  (look-up tables, global sweeps) are forced only when named in `--stages`.
- `make docs` never loses published data because build outputs are missing: a registered point
  whose outputs are not in `build/` keeps its published files (with a notice), and a missing
  component-level input keeps the published file it would have produced (with a warning). So
  `make docs` in a fresh clone leaves `docs/` unchanged. Removing a point from the registry is
  the only way to unpublish it; the docs stage always runs when asked, also for an empty registry.

## 6. Rules

- `hub/export.py` is standard-library Python and reads only `docs/`, `points.json` and `hub/`
  (the hub's CI checks out only those). CLI: `python3 hub/export.py [--docs docs] [--out docs/hub]`.
  The exporter also:
  - runs in isolated mode (`python3 -I hub/export.py …`, which is how the hub runs it), so it puts its own
    directory on `sys.path` before importing its helper modules;
  - replaces a previous export: if `--out` contains a `component.json` it is cleared first, so removed
    points leave no stale files; if `--out` is not empty and has no `component.json` (e.g. `docs/` itself)
    it stops with an error and writes nothing;
  - prints one warning per registered, published point it cannot export yet (no results), and still succeeds;
  - derives counts and lists that depend on the registered points (designs, topologies, supplies, …)
    from the data instead of writing them into prose;
  - is deterministic: the same `docs/`, `points.json` and `hub/` give byte-identical output (dates
    come from the data, never from the clock or file times);
  - parses its arguments in `main()`, and exits with status 2 (and says how to recover) when it
    refuses an `--out`.
- `docs/` holds published data only: no website files, no pre-rendered layout images (the hub
  renders GDS thumbnails), no uncompressed GDS, no duplicates.
- Results follow the hub's honesty rule (BUILDERS.md §6): only simulated values in `results`;
  model or placeholder values are labelled.
- Generated and intermediate files are git-ignored; scratch, logs and caches are not committed.
- Agent instructions live in `AGENTS.md`. Tool-specific instruction files (e.g. `GEMINI.md`) exist only
  as pointers to it.
- Commit messages describe what changed and why for the repository owners; no tool attribution
  lines.

## 7. README, AGENTS.md and INVENTORY.md

- `README.md` follows `templates/README.md`: the same sections in the same order, and the shared
  text of *Quick start*, *Design points* and *Publishing to the hub*, with this repository's values.
  Examples work when copied. No counts of registered points (`make points` lists them).
- `AGENTS.md` follows the numbered sections of `templates/AGENTS.md`.
- `hub/INVENTORY.md` is written for the owners: what the retired website showed and where each
  item is on the hub, intended differences from the old site, and known gaps.
