# Publishing a generator repo on the AICDB hub

The hub (<https://aicdb.github.io/hub-gemini4/>) is the **only** public site for the
`*-gen-*` generator repos. Each repo keeps building its own `docs/` folder as before; the
hub's CI pulls `docs/` from every repo, renders a unified tab per component type, and
also serves the repo's own page as the "Classic report" at `c/<id>/`.

What a repo builder must do:

1. Write an exporter that produces **`docs/hub/component.json`** (spec below).
2. Validate and preview it locally with `hubkit.py`.
3. Commit + push `docs/`, then trigger the hub publish.
4. Delete the repo's own `.github/workflows/pages.yml` and disable Pages in the repo settings.
5. Stay within the size budget (§5).

Until a repo ships its own `docs/hub/component.json`, the hub uses a bootstrap adapter
at `adapters/<id>.py` in the hub repo. **Use the adapter as your starting point**: copy
it to `scripts/export_hub.py` in your repo, make it run as the last step of your docs
build, and improve it. Once `docs/hub/component.json` exists in your repo, the hub ignores
the adapter.

---

## 1. Quick start

```bash
# from your repo root, with the hub checked out next to it (../hub-gemini4)
python3 scripts/export_hub.py docs docs/hub/component.json    # your exporter
python3 ../hub-gemini4/tools/hubkit.py validate docs           # must print ✓
python3 ../hub-gemini4/tools/hubkit.py preview docs            # http://127.0.0.1:8000
git add docs && git commit -m "Update hub export" && git push
gh workflow run publish.yml -R aicdb/hub-gemini4               # publish now
```

The hub also republishes on its own every 6 hours if any source repo has a new commit.
Running `gh workflow run` just makes it immediate. The publish takes about 5–10 minutes.
Watch it with `gh run watch -R aicdb/hub-gemini4`.

## 2. Component ids (fixed, must match `sources.json`)

| id | repo | tab |
|---|---|---|
| `switch` | switch-gen-gemini4 | Switches |
| `sa` | sa-gen-gemini4 | Sense amps |
| `ls` | ls-gen-gemini4 | Level shifters |
| `opa` | opa-gen-gemini4 | Op-amps |
| `aux` | aux-gen-gemini4 | Aux blocks |
| `ldo` | ldo-gen-gemini4 | LDOs |
| `ecg` | ecg-gen-gemini4 | ECG AFEs |
| `sar` | sar-gen-gemini4 | SAR ADCs |
| `sdm` | sdm-gen-gemini4 | ΣΔ ADCs |

New generator repos are added by appending to `sources.json` in the hub repo.

## 3. `docs/hub/component.json` — schema `aicdb-hub/1`

All file paths are **relative to `docs/`**. All numbers are plain JSON numbers (no strings,
no NaN — use `null`).

```jsonc
{
  "schema": "aicdb-hub/1",
  "id": "opa",                                  // §2
  "name": "Op-amps",                            // short tab label (≤ 14 chars)
  "title": "GF180 Op-Amp Design Library",       // tab heading
  "summary": "Twelve architectures …",          // 1–3 sentences, plain text
  "technology": "gf180mcuD",                    // default technology id for all designs
  "generated": "2026-11-07T12:00:00Z",          // when the export ran (UTC ISO-8601)
  "classic": "index.html",                      // optional: your full report inside docs/
  "stats": [ { "label": "farm simulations", "value": "43,386" } ],  // optional extra tiles

  "metrics": [                                  // every metric the UI may show, in display order
    { "key": "a0",    "label": "DC gain", "unit": "dB",  "digits": 3, "better": "high" },
    { "key": "ugb",   "label": "UGB",     "unit": "Hz",  "si": true,  "better": "high" },
    { "key": "power", "label": "Power",   "unit": "W",   "si": true,  "better": "low" },
    { "key": "area",  "label": "Area",    "unit": "µm²", "digits": 4, "better": "low" }
  ],

  "axes": {                                     // categorical dimensions, values in display order
    "topology": { "label": "Architecture", "values": [ { "id": "nmos_5t", "label": "5-T NMOS" } ] },
    "class":    { "label": "Current class", "values": [ { "id": "1u_10u", "label": "1–10 µA" } ] }
  },

  "matrix": { "rows": ["topology"], "cols": ["class"], "metrics": ["ugb", "a0"] },
  "card_metrics": ["a0", "ugb", "power", "area"],  // first one is the headline number

  "families": [ … ],                            // optional, see §3.3
  "designs":  [ … ]                             // §3.1
}
```

**Metric formatting.** `si: true` means the value is in base SI units (`Hz`, `W`, `A`, `F`,
`Ω`, `s`, `V`) and the hub picks the prefix (2.65e6 Hz → "2.65 MHz"). Without `si`, the
value is shown as-is with `unit`, rounded to `digits` significant digits (default 3).
`better` is used for sorting and for colouring the stage-to-stage deltas on the detail page.
Only declare metrics that were really simulated or measured. Leave out placeholders and
constants (e.g. a fixed noise number copied onto every card), because the hub can't tell
them apart from real results.

**Supply voltage is not an axis.** Every design has a numeric `vdd` field. The hub
shows it as a global filter and as the outer column group of the matrix.

### 3.1 Design record

```jsonc
{
  "id": "folded_cascode_nmos_1v8_10u_100u_weak",   // unique, [A-Za-z0-9._-], stable across releases
  "title": "Folded-Cascode NMOS · 1.8 V · 10–100 µA · weak inversion",
  "family": "ro",                                  // only if "families" is used
  "technology": "gf180mcuD",                       // optional, defaults to component technology
  "vdd": 1.8,                                      // volts, or null if meaningless
  "axes": { "topology": "folded_cascode_nmos", "class": "10u_100u" },
  "tags": ["NMOS input", "2 pF load"],             // free-form chips

  "physical": { "drc": true, "lvs": true, "pex": true,
                "area_um2": 3914.1, "width_um": 54.1, "height_um": 72.35 },

  "results": {                                     // keyed by simulation stage, §3.2
    "pre":  { "metrics": { "a0": 97.8, "ugb": 2.65e6 }, "pvt": { "pass": 17, "total": 17 },
              "mc": { "pass": 50, "total": 50 }, "robust": true },
    "full": { "metrics": { "a0": 97.8, "ugb": 2.60e6 }, "pvt": { "pass": 17, "total": 17 },
              "robust": true, "note": "Magic RC extraction of the full cell" }
  },

  "params": { "W_in": "12 µm", "L_in": "1 µm", "Ibias": "5 µA" },   // optional sizing / knobs

  "files": {                                       // standard slots (all optional)
    "schematic":   "designs/x/schematic.svg",
    "gds":         "designs/x/x.gds.gz",           // the hub renders the layout from this, live
    "thumbnail":   "designs/x/thumb.png",          // optional ≤ 40 KB card preview (default: schematic)
    "netlist":     "designs/x/netlist.spice",
    "pex_netlist": "designs/x/pex.spice",
    "lvs_netlist": "designs/x/lvs_ref.spice",
    "data":        "designs/x/card.json"           // your full evidence JSON
  },
  "images":    [ { "label": "PVT corners", "path": "designs/x/pvt.png" } ],   // extra figures
  "downloads": [ { "label": "Testbench", "path": "designs/x/tb.spice" } ],    // extra files
  "links":     { "classic": "index.html#/2p/x" }   // deep link into your own report
}
```

**Layouts are rendered from the GDS in the browser.** Don't publish pre-rendered layout
images (`layout.svg` and the like). They are as large as the GDS itself and were ~40% of all
published bytes. The detail page draws `files.gds` (`.gds` or `.gds.gz`) live, with pan/zoom,
a cell picker for sub-cells (cap arrays, digital macros …) and layer toggles. Put pin names in
GDS TEXT elements so they show up as labels. `files.layout` still exists for a design
without a GDS, but it is never used when `gds` is present. To show layouts in your own
classic report, copy the hub's standalone viewer `web/assets/gdsview.js` into your
`docs/assets/` and call `GDSView.mount(element, "designs/x/x.gds.gz", {tech: "gf180mcuD"})`.

`physical.drc`/`lvs`/`pex`: `true` = clean or done, `false` = failed, `null` = not run.
`pvt`/`mc` counts are optional. `robust` is **your repo's own pass criterion** at that stage
(for example "all PVT corners and MC samples meet spec"). The hub's "PVT-robust" filter uses
it.

### 3.2 Simulation stages

The global **Simulation** selector on the hub picks which `results.<stage>` every tab shows.

| key | label | meaning |
|---|---|---|
| `pre` | Pre-PEX | schematic netlist, ideal wiring |
| `partial` | Partial post-PEX | only **part of the design's layout** is extracted, the rest ideal: e.g. only the CDAC / cap array, extracted sub-blocks without top-level routing, or only caps on a subset of nets |
| `full` | Full post-PEX | the **complete layout of this design** extracted (top-level cell incl. its routing) and simulated |

"Partial" means partial *coverage* of the layout, not the kind of extraction. A whole-cell
C-only extraction is `full`. Say `"note": "C-only extraction (no wire R)"` so readers know.

Rules:
- Only emit a stage you actually simulated. Never copy pre numbers into `full`.
- For a leaf cell (one layout, e.g. a switch or an op-amp), the extracted cell result is
  `full`. Use `partial` only when part of the design was extracted.
- If you have several partial levels, put the most complete one in `partial` and say what
  was extracted in `note`.
- When a design has no result for the selected stage, the hub by default shows the nearest
  *lower* stage and marks the value (e.g. "pre"). The user can turn the fallback off.

### 3.3 Families (only for multi-family repos such as `aux`)

If one repo holds several unrelated block types (ring oscillators, current mirrors, …),
declare them and set `design.family`. Each family can override `matrix` and `card_metrics`
and becomes a sub-tab:

```jsonc
"families": [
  { "id": "ro", "label": "Ring oscillators", "summary": "…",
    "matrix": { "rows": ["topology"], "cols": ["target"], "metrics": ["fosc", "power"] },
    "card_metrics": ["fosc", "power", "area"] }
]
```

### 3.4 Matrix

`matrix.rows` is a list of axis keys whose combinations label the rows (e.g.
`["topology", "regime"]`). `matrix.cols` is a list of axes under the `vdd` column group.
`matrix.metrics` are the 1–2 metrics printed in each cell. If several designs land in one
cell (e.g. two load conditions), the hub shows the first and a "+n" badge. Add a filter
axis (e.g. `load`) so users can narrow it down.

## 4. Conventions

- **Technology ids:** `gf180mcuD`. Future PDKs get new ids (e.g. `sky130A`, `ihp-sg13g2`).
  Add the label to `technologies` in the hub's `sources.json` in the same PR.
- **Units:** base SI with `si: true` whenever the quantity has an SI unit. dB, %, degrees,
  ENOB bits, FoM numbers are plain with `unit`.
- **Stable ids:** design ids appear in URLs (`#/opa/<id>`). Don't rename casually.
- **Determinism:** sort `designs` the way you want them listed. Don't include timestamps
  per design. This keeps git diffs readable.
- **Self-contained:** everything referenced must be inside `docs/`. No absolute URLs to
  your repo, because the source repos are private.

## 5. Size budget

GitHub Pages limits the whole site to **1 GB**. Nine repos share it, so the budget per
component is **100 MB**, enforced as a warning by `hubkit validate`. The hub build fails if
the total exceeds 1 GB. Files matching `sources.json → exclude` (currently `**/*.gds`, i.e.
uncompressed GDS) are never published.

How to slim down, by impact:
1. **Layout renders:** stop publishing `layout.svg`, `cap_layout.svg` and the like (§3.1).
   The hub renders the `.gds.gz`. This alone removes ~355 MB across the repos (sdm 150 MB,
   sar 114 MB, opa 39 MB, aux 27 MB, ldo 19 MB).
2. **Duplicates:** don't ship near-identical files (e.g. `schematic.svg` +
   `schematic_design.svg`, or `index.html` that inlines `report_data.json`).
3. **Many small files:** merge per-design netlists (`netlist.spice`, `lvs_ref.spice`,
   `pex.spice`) into one `netlists.spice` with clearly delimited sections. Don't gzip
   files under 20 KB.
4. **Raw sweep data:** keep giant DSE/sweep JSON out of `docs/`, or decimate it.

## 6. Retiring the per-repo Pages site

After your first successful hub publish:
```bash
git rm .github/workflows/pages.yml && git commit -m "Publish via aicdb hub" && git push
gh api -X DELETE repos/aicdb/<repo>/pages      # disables the old site
```
Keep `docs/` building as before: it is the hub's input.
