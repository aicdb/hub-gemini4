# Publishing a generator repo on the AICDB hub (schema `aicdb-hub/2`)

The hub (<https://aicdb.github.io/hub-gemini4/>) is the **only** public site for the
`*-gen-*` generator repos. The per-repo GitHub Pages sites are retired, so **everything a
repo used to show on its own site must be expressed in its hub export**: the design list
and coverage matrix, every design-detail section, the design-space explorer, methodology,
comparisons, databases and so on.

The hub does not copy your site. It publishes only what your export references as
**hosted** files: JSON documents, figures and data. For **repo files** (GDS, netlists,
evidence JSON) it shows a link to the raw file in your private repository, pinned to the
exported commit. People need repo access to download them. Layouts are shown as WebP
thumbnails that the hub renders from your GDS at build time; you never publish layout
images.

What a repo builder must do:

1. Write `scripts/export_hub.py` that produces **`docs/hub/component.json`** plus the files
   it references under `docs/hub/` (spec below). Run it as the last step of your docs build.
2. `python3 ../hub-gemini4/tools/hubkit.py validate docs` must print ✓. Then check it with
   `hubkit.py preview docs` (needs `pip install gdstk pillow` for layout thumbnails).
3. Commit + push, then `gh workflow run publish.yml -R aicdb/hub-gemini4`.

Until a repo ships `docs/hub/component.json`, the hub runs its own bootstrap adapter
`adapters/<id>.py` against your `docs/`. That adapter is the best starting point for your
exporter: it already maps everything your old site showed.

---

## 1. Quick start

```bash
python3 scripts/export_hub.py                                  # writes docs/hub/**
python3 ../hub-gemini4/tools/hubkit.py validate docs           # must print ✓
python3 ../hub-gemini4/tools/hubkit.py preview docs            # http://127.0.0.1:8000
git add docs && git commit -m "Update hub export" && git push
gh workflow run publish.yml -R aicdb/hub-gemini4               # publish now
```

The hub also republishes by itself every 6 hours when any source repo has a new commit.

## 2. Component ids (fixed, must match `sources.json`)

| id | repo | tab |
|---|---|---|
| `switch` | aicdb/switch-gen-gemini4 | Switches |
| `sa` | aicdb/sa-gen-gemini4 | Sense amps |
| `ls` | aicdb/ls-gen-gemini4 | Level shifters |
| `opa` | aicdb/opa-gen-gemini4 | Op-amps |
| `aux` | aicdb/aux-gen-gemini4 | Aux blocks |
| `ldo` | aicdb/ldo-gen-gemini4 | LDOs |
| `ecg` | aicdb/ecg-gen-gemini4 | ECG AFEs |
| `sar` | aicdb/sar-gen-gemini4 | SAR ADCs |
| `sdm` | aicdb/sdm-gen-gemini4 | ΣΔ ADCs |

## 3. Files and paths

```
docs/
  hub/component.json          the component (§4)            ── hosted
  hub/pages/<page>.json       one per extra page (§4.2)      ── hosted
  hub/designs/<id>.json       one detail doc per design      ── hosted
  hub/data/...                chart / table / explorer data  ── hosted
  designs/<id>/schematic.svg  your existing figures          ── hosted when referenced via src
  designs/<id>/<id>.gds.gz    GDS                            ── repo link + rendered thumbnail
  designs/<id>/netlist.spice  netlists, evidence JSON …      ── repo link
```

- A path that starts with `hub/` resolves inside `docs/hub/`. Any other relative path
  resolves inside `docs/`. Absolute paths, `..` and URLs are rejected.
- **Hosted** means copied to the site: `src` of blocks and pages, design `detail`,
  `files.schematic`, `files.thumbnail`, `images[].src`, `downloads[].src`.
- **Repo-linked** means only linked: `files.gds|netlist|pex_netlist|lvs_netlist|data`,
  `downloads[].file`, and the `gds` of layout blocks. The link is
  `https://github.com/<repo>/raw/<commit>/docs/<path>`.
- Never host uncompressed GDS or pre-rendered layout images (`**/*.gds` and
  `**/*layout*.svg` are rejected).
- Hosted JSON should be compact (no indentation), with numbers rounded to about 4–5
  significant digits.

## 4. `docs/hub/component.json`

```jsonc
{
  "schema": "aicdb-hub/2",
  "id": "opa",                                  // §2
  "name": "Op-amps",                            // short tab label (≤ 14 chars)
  "title": "GF180 Op-Amp Design Library",
  "summary": "Twelve architectures …",          // 1–3 sentences (markdown allowed)
  "technology": "gf180mcuD",
  "generated": "2026-11-07T12:00:00Z",
  "stats": [ { "label": "farm simulations", "value": "43,386" } ],   // extra header tiles

  "metrics": [                                  // every metric used by designs, in display order
    { "key": "a0",  "label": "DC gain", "unit": "dB", "digits": 3, "better": "high" },
    { "key": "ugb", "label": "UGB",     "unit": "Hz", "si": true,   "better": "high" }
  ],
  "axes": {                                     // categorical dimensions, values in display order
    "topology": { "label": "Architecture", "values": [ { "id": "nmos_5t", "label": "5-T NMOS" } ] }
  },
  "matrix": { "rows": ["topology"], "cols": ["class"], "metrics": ["ugb", "a0"],   // cell = metrics[0] big, up to 4 more small
              "presets": [ { "label": "Noise & PSRR", "metrics": ["noise", "psrr"] } ] },   // optional; users can also pick any metric
  "card_metrics": ["a0", "ugb", "power", "area"],   // up to 12; the first is the headline
  "cards_group_by": "class",                     // optional axis key (or list) to group the card grid
  "families": [ … ],                            // optional sub-tabs (§4.3)
  "pages": [ … ],                               // extra pages next to "Designs" (§4.2)
  "designs": [ … ]                              // §4.1
}
```

- **Metric description:** optional `desc` (plain text: definition, test condition) is
  shown as a tooltip wherever the metric appears.
- **Metric formatting:** `si: true` means the value is in base SI units (Hz, W, A, F, Ω, s,
  V, V/s …) and the hub picks the prefix. Otherwise the value is printed with `unit`,
  rounded to `digits` significant digits (default 3). `better` (`high`/`low`) drives
  sorting and the colour of stage deltas.
- **Only declare real results.** Leave out placeholders and constants.
- **Supply voltage is not an axis:** every design has a numeric `vdd` (volts). The hub
  shows it as a global filter and as the outer column group of the matrix.

### 4.1 Design record

```jsonc
{
  "id": "2p-folded_cascode_nmos_1v8_10u_100u_weak",   // unique, [A-Za-z0-9._-], stable (used in URLs)
  "title": "Folded-Cascode NMOS · 1.8 V · 10–100 µA · weak inversion · CL 2 pF",
  "summary": "optional markdown paragraph shown under the title",
  "family": "ro",                                      // only with families
  "technology": "gf180mcuD",                           // optional, defaults to the component's
  "vdd": 1.8,
  "axes": { "topology": "folded_cascode_nmos", "class": "10u_100u" },
  "tags": ["NMOS input", "2 pF load"],
  "physical": { "drc": true, "lvs": true, "pex": true, "area_um2": 3914.1, "width_um": 54.1, "height_um": 72.35 },
  "results": {
    "pre":  { "metrics": { "a0": 97.8, "ugb": 2.65e6 }, "pvt": { "pass": 17, "total": 17 },
              "mc": { "pass": 50, "total": 50 }, "robust": true },
    "full": { "metrics": { "a0": 97.8, "ugb": 2.60e6 }, "robust": true, "note": "Magic C-only extraction of the full cell" }
  },
  "params": { "W_in": "12 µm", "gm/Id target": 16.5 },  // short key → value list (sizing / knobs)
  "files": {
    "schematic": "designs/x/schematic.svg",            // hosted
    "thumbnail": "hub/thumbs/x.png",                   // optional hosted card image (default: GDS thumbnail)
    "gds": "designs/x/x.gds.gz",                       // repo link + thumbnail
    "netlist": "designs/x/netlist.spice", "pex_netlist": "designs/x/pex.spice",
    "lvs_netlist": "designs/x/lvs_ref.spice", "data": "designs/x/card.json"   // repo links
  },
  "images": [ { "label": "Annotated schematic (post-PEX)", "src": "designs/x/schematic_pex.svg" },
              { "label": "Cap array", "gds": "designs/x/x.gds.gz", "cell": "sc_cap_16b" } ],
  "downloads": [ { "label": "Testbench", "file": "designs/x/tb.spice" } ],
  "detail": "hub/designs/2p-folded_cascode_nmos_1v8_10u_100u_weak.json"   // §5: all detail sections
}
```

On the design page the hub renders the title, axis chips and tags, a **figure gallery**
(schematic, layout thumbnail, `images[]`), the **performance-by-stage table** (from
`results`), physical status, `params`, file links, and then **every block of the `detail`
document**. The detail document is where all the old card sections go.

### 4.2 Pages

```jsonc
"pages": [
  { "id": "explore", "title": "Design space", "src": "hub/pages/explore.json" },
  { "id": "method",  "title": "Methodology",  "src": "hub/pages/method.json" }
]
```

A page document is `{ "intro": "optional markdown", "blocks": [ … ] }`. Pages appear as
sub-tabs next to **Designs** inside the component's tab (`#/<id>?page=<page id>`). The
built-in Designs view already provides the coverage matrix, cards and a sortable
comparison table with CSV export of all metrics. Use pages for everything else: DSE
explorers, Pareto plots, comparisons, databases with extra columns, methodology, reuse,
cross-checks, appendices.

### 4.3 Families

For repos with several unrelated block types (`aux`): `families: [{id, label, summary,
matrix?, card_metrics?}]` plus `design.family`. Each family becomes a sub-tab of the
Designs view with its own matrix and card metrics.

## 5. Content blocks

Pages and detail documents are lists of blocks. Every block accepts these common keys:

| key | meaning |
|---|---|
| `type` | one of the types below |
| `title`, `caption` | heading (inline markdown) and a markdown note under the block |
| `stage`, `alt` | stage-specific block, see §5.1 |
| `vdd`, `tech` | show only when the global V<sub>DD</sub> / technology filter is "All" or equal |
| `span` | column span inside a multi-column `section` |
| `id` | anchor id |

| type | fields | renders |
|---|---|---|
| `section` | `title`, `intro` (md), `blocks[]`, `cols` (1–4), `collapsed`, `open` | panel with heading; children in a grid when `cols > 1`; collapsible |
| `markdown` | `text` | headings, lists, **bold**, *italic*, `code`, links, pipe tables, blockquotes, fenced code, and `<sub> <sup> <br> <b> <i> <em> <strong> <code> <u> <small>` |
| `note` | `text`, `tone`: info/warn/good/bad/muted | callout |
| `code` | `text`, `max_height` | monospace box (netlist excerpts, commands) |
| `stats` | `items[]: {label, value, unit?, si?, digits?, sub?}` | KPI tiles |
| `kv` | `items[]: [label, value, unit?]` or `{label, value, unit, si, digits, s}`, `cols` | key/value grid; `s` = good/warn/bad colours the value |
| `table` | `columns[]`, `rows[]` or `src`, `sort`, `search`, `csv`, `max_height`, `page_size`, `stage_column`, `vdd_filter` | sortable, filterable table with CSV export |
| `chart` | Plotly figure: `data[]` (traces), `layout{}` or `src` (JSON `{data, layout}`), `height`, `link_designs` | any Plotly chart (lines, scatter, bar, histogram, heatmap, box, …), themed automatically |
| `explorer` | `src` (columnar JSON), `dims[]`, `x`, `y`, `color`, `symbol`, `filters[]`, `facet_default`, `presets[]`, `highlight`, `highlight_label`, `design_key`, `label_key`, `hover[]`, `pareto_default`, `intro`, `height`, `cat_axes` | interactive design-space explorer (§5.3) |
| `image` | `src` (hosted svg/png/webp/jpg) or `gds` + `cell`, `bg`: white/dark/none, `max_height` | figure (click to open full size) |
| `layout` | `gds`, `cell` (optional sub-cell), `max_height` | rendered GDS thumbnail + link to the raw GDS in the repo |
| `gallery` | `items[]: {label, src \| gds, cell?, caption?}`, `style`: tabs/grid, `cols`, `default` | several figures as tabs or a grid |
| `downloads` | `items[]: {label, file \| src \| url, note?}` | link list; `file` → raw file in the repo, `src` → hosted, `url` → external |
| `tabs` | `tabs[]: {label, labels?: {pre, partial, full}, blocks[], vdd?, tech?}` (`labels` = stage-dependent tab label), `style`: tabs/select, `label`, `default`, `id` (selection is kept in the URL as `t.<id>=<index>`, so it can be deep-linked) | switch between alternative block groups (benches, corners, topologies…); more than 12 tabs become a dropdown |

**Table columns:** `{key, label, unit, si, digits, type, group, better, md, align, title, wrap}`
(`wrap: true` lets long text wrap instead of staying on one line).
- `type`: `text`, `num` (default for numbers), `status` (true ✓ / false ✗, coloured),
  `design` (a design id rendered as a link to its page), `link` (cell `{v, href}`).
- `group` adds a grouped header row. `md: true` renders cell text as inline markdown.
- A cell can be a plain value or `{v, s, title, t, href}`: `s` = good/warn/bad/muted colours
  the cell, `title` is a tooltip, `t` is display text for design links.
- A row object can carry `_design` (the whole row links to that design), `_href` (the row
  links to any `#/…` hub URL, e.g. a page with a tab preselected via `t.<tab id>=<index>`, or
  an external URL), and `_s` (row colour).
- Internal links (`#/<component>/<design>` in markdown or `_href`) keep the user's global
  options automatically. Links to sibling components are fine: `[comparator](#/sa/san-lv-1v8-sub)`.
  Escape markdown characters with a backslash (`\_`); underscores inside link URLs are safe.
- `rows` may be arrays in column order instead of objects.
- A column named `vdd` (or `tech`) makes the table follow the global filter.
- `stage_column: "stage"` makes it follow the global simulation stage.

**Charts** are plain Plotly (v2.35) figures. Write traces exactly as you would for
`Plotly.newPlot`:
- Colours, fonts and backgrounds are themed by the hub. Only set them when they carry
  meaning (e.g. pass/fail colours).
- A trace with `meta: {vdd: 1.8}` is hidden when the global V<sub>DD</sub> filter selects
  another supply. A trace with `meta: {stage: "pre"}` is a stage alternative inside one chart:
  only the traces of the resolved stage are drawn (traces without a stage are always drawn).
  This saves duplicating a whole chart per stage.
- With `link_designs: true`, clicking a point whose `customdata` is a design id opens that
  design.
- Use log axes (`layout.xaxis.type = "log"`), subplots, annotations and shapes as needed.

### 5.1 Global options inside pages and detail docs

The hub's shared options apply inside pages and detail documents too:

- **Simulation stage:** give stage-specific alternatives the same `alt` key and their
  `stage`:
  ```jsonc
  { "type": "chart", "alt": "bode", "stage": "pre",  "title": "Loop gain", "src": "hub/data/x_bode_pre.json" },
  { "type": "chart", "alt": "bode", "stage": "full", "title": "Loop gain", "src": "hub/data/x_bode_post.json" }
  ```
  The hub shows the alternative matching the selected stage. With "fill from earlier
  stage" on, it falls back to the nearest earlier stage and marks it. If no alternative
  fits, it shows a short "not available at this stage" note. A block with `stage` but no
  `alt` is shown only at that stage (or as a fallback). Blocks without `stage` are always
  shown.
- **V<sub>DD</sub> / technology:** set `vdd` / `tech` on blocks or tabs that apply to one
  supply or PDK. Explorers and tables with a `vdd` / `tech` column follow the filter.
  Explorers with a `stage` column follow the stage selection.

### 5.2 What goes where (porting checklist)

Everything visible on the old site must exist in the export. Typical mapping:

| old site element | hub |
|---|---|
| coverage matrix, card grid, master comparison table | built-in Designs view (`matrix`, `card_metrics`, `metrics`) |
| per-card banner, spec checks, key results | `results` / `params` + detail `section` with `kv` or `table` |
| PVT corner table, MC summary, operating-point / sizing tables, pin coordinates, DRC/LVS/PEX breakdown | detail `table` blocks (stage alternatives where pre/post differ) |
| waveforms, Bode / PSRR / noise plots, sweeps, histograms, resolve-time maps | detail `chart` blocks (Plotly); many variants → `tabs` |
| annotated schematics, sub-block schematics | `files.schematic` + `images[]`, or `image` blocks |
| layout views (incl. sub-cells such as cap arrays, digital macros) | `files.gds` + `images[{gds, cell}]` / `layout` blocks (thumbnails) |
| design-space explorer, Pareto plots, design clouds, facet grids | page with `explorer` (+ `chart`) blocks; delivered designs via `highlight` + `design_key` |
| comparison / trade-off / sensitivity / cross-check pages | page with `chart` + `table` + `markdown` |
| methodology, flow description, references, appendices | page with `markdown` / `section` / `image` / `table` |
| downloadable artefacts | `files.*` / `downloads` (repo links) |
| global toggles of the old site (pre/post view, load selection, polarity …) | global stage option (§5.1), axes (filters), or `tabs` |

### 5.3 Explorer data

```jsonc
// hub/data/dse.json — columnar, all columns the same length
{ "columns": { "power": [1.2e-6, …], "ugb": [2.1e6, …], "arch": ["miller", …], "vdd": [1.8, …],
               "design": [null, "2p-miller_1v8_…", …], "delivered": [false, true, …] } }
```

```jsonc
{ "type": "explorer", "title": "Measured design space", "src": "hub/data/dse.json",
  "dims": [ { "key": "power", "label": "Power", "unit": "W", "si": true, "log": true, "better": "low" },
            { "key": "ugb", "label": "UGB", "unit": "Hz", "si": true, "log": true, "better": "high" },
            { "key": "arch", "label": "Architecture", "type": "cat", "labels": { "miller": "2-stage Miller" }, "order": ["nmos_5t", "miller"] } ],
  "x": "power", "y": "ugb", "color": "arch", "filters": ["arch", "power"],
  "highlight": "delivered", "highlight_label": "Delivered cards", "design_key": "design",
  "presets": [ { "label": "Gain vs power", "x": "power", "y": "a0" }, { "label": "Per architecture", "facet": "arch" } ] }
```

Dim options: `type: "cat"` (categorical; `labels`, `order`, `colors: {value: "#hex"}`),
`log`, `better`, `unit`/`si`/`digits`. Explorer options: `cat_axes: true` lets categorical
dims be chosen as X/Y (strip plot); `presets[]: {label, x, y, color, symbol, facet, logx,
logy, pareto, show: {catKey: [visible values]}}`; `preset_default` (index applied on load).
Rows with a null `stage` are shown at every stage.

Users can switch X/Y/colour/symbol/facet, toggle log axes and a Pareto front, and filter
by categorical chips and numeric ranges. Clicking a highlighted point opens the design.
Up to ~100k points work well. Decimate bigger sweeps and say so in the caption.

## 6. Simulation stages

| key | label | meaning |
|---|---|---|
| `pre` | Pre-PEX | schematic netlist, ideal wiring |
| `partial` | Partial post-PEX | only **part of the layout** is extracted (e.g. only the cap array / CDAC, sub-blocks without top-level routing, caps on a subset of nets) |
| `full` | Full post-PEX | the **complete layout of this design** extracted (top cell incl. routing) and simulated |

Rules:
- "Partial" means partial *coverage* of the layout. A whole-cell C-only extraction is
  `full`; describe it in `note`.
- Only emit what you simulated. Never copy or scale numbers from another stage. Values
  derived by formula go in `params` or a clearly labelled block, not in `results`.

## 7. Conventions

- **Technology id** `gf180mcuD`. A new PDK gets a new id plus a label in the hub's
  `sources.json`.
- **Units:** base SI with `si: true` wherever the quantity has an SI unit.
- **Stable ids:** design ids appear in URLs.
- **Determinism:** sorted output, no per-design timestamps, so git diffs stay small.

## 8. Size budget

The hub hosts only referenced files (plus ~50 KB per layout thumbnail). Keep each
component under **100 MB** of hosted files: `hubkit validate` prints the total. Decimate
huge sweeps, and keep hosted JSON compact.

## 9. Retiring the per-repo site

After your content is on the hub:
```bash
git rm .github/workflows/pages.yml && git commit -m "Publish via aicdb hub" && git push
gh api -X DELETE repos/aicdb/<repo>/pages
```
Keep `docs/` (and `docs/hub/`) building: the hub reads it.
