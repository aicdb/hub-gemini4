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

Every generator repository follows [REPO_STANDARD.md](REPO_STANDARD.md): a design-point
registry (`points.json`), the uniform `make` interface, and the exporter `hub/export.py`.
The hub's CI checks out `docs/` and `hub/` of each repository, runs `hub/export.py`, and
builds the site from its output. Nothing generated has to be committed: `docs/hub/` is
git-ignored and only produced locally by `make hub` for checking.

The steps for a repository:

1. Keep `docs/` (published data) and `hub/export.py` up to date. The exporter turns
   `docs/` + `points.json` into the component described below.
2. Run `make hub` (export and validate) and `make preview` (local hub at http://127.0.0.1:8000).
3. Commit and push. The hub republishes within 6 hours, or immediately with
   `gh workflow run publish.yml -R aicdb/hub-gemini4`.

The export is looked up in this order: a committed `docs/hub/component.json` (normally absent:
`docs/hub/` is git-ignored), then the repository's `hub/export.py`, which the hub runs as
`python3 -I hub/export.py --docs docs --out <empty dir>`.

---

## 1. Quick start

```bash
make points                                   # list the design points
make add POINT="arch=miller vdd=3.3 …"        # register a new point
make build POINT=<id>                         # run the generator pipeline for it
make hub                                      # export + validate (HUB=../hub-gemini4)
make preview                                  # http://127.0.0.1:8000
git add points.json docs && git commit -m "…" && git push
gh workflow run publish.yml -R aicdb/hub-gemini4               # publish now
```

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
| `pll` | aicdb/pll-gen-gemini4 | PLLs |

## 3. Files and paths

```
docs/                         (hub/** is written by hub/export.py, git-ignored)
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
              "presets": [ { "label": "Noise & PSRR", "metrics": ["noise", "psrr"] } ],     // optional; users can also pick any metric
              "status": { "metric": "range", "good": 95, "warn": 50 } },   // optional: colour cells by thresholds (direction from metric.better)
  "card_metrics": ["a0", "ugb", "power", "area"],   // up to 12; the first is the headline
  "vdd_labels": { "1.8": "V<sub>DD</sub> = 1.8 V · V<sub>CM</sub> = 0.9 V" },   // optional matrix supply-group headers
  "table_metrics": ["a0", "ugb", "pm", "power", "area"],   // optional default columns of the Designs table (users can show all)
  "cards_group_by": "class",                     // optional axis key (or list) to group the card grid
  "builds_on": [ { "id": "opa", "role": "core OTA" }, { "id": "switch", "role": "chopper switches" } ],  // §4.5
  "families": [ … ],                            // optional sub-tabs (§4.4)
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
                                                       // true = clean/done, false = failed, null = not run; pex may be "partial"
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
  "uses": [ { "component": "opa", "design": "200f-folded_cascode_nmos_1v8_0p1u_1u_subth", "role": "core OTA" },
            { "component": "switch", "design": "cmos__1p8v__10u-100u", "role": "input chopper" } ],   // §4.5
  "detail": "hub/designs/2p-folded_cascode_nmos_1v8_10u_100u_weak.json"   // §5: all detail sections
}
```

**Not-applicable placeholders:** a combination that exists in the old coverage matrix but
was deliberately not designed (e.g. an oxide-overstress case) can be a design record with
`"na": "reason"` and empty `results`. It shows up as an "n/a" matrix cell (the reason is
the tooltip), as a card with a "not applicable" badge, and as a detail page with the reason.

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

### 4.3 Several components from one repository (collections)

A repository that is really a collection of small, unrelated generators (e.g. `aux`) exports
**one component per generator**. Each becomes its own top-level tab, grouped under a shared
label in the navigation. `docs/hub/component.json` is then a manifest:

```jsonc
{ "schema": "aicdb-hub/2", "id": "aux", "group": "Aux blocks",
  "components": [ "hub/ro/component.json", "hub/tcap/component.json", … ] }
```

Every listed file is a complete component (§4) with its own designs, matrix, pages and
detail docs. Its `id` must start with `<source id>-` (e.g. `aux-ro`, `aux-tcap`), and its
`name` is the tab label. The components may share hosted files (e.g. a common methodology
page).

### 4.4 Families

For variants of one generator that need different matrices or metrics: `families: [{id,
label, summary, matrix?, card_metrics?, cards_group_by?}]` plus `design.family`. Each family
becomes a sub-tab of the Designs view. Unrelated generators should be separate components
(§4.3) instead.

### 4.5 Block hierarchy (reuse between components)

Bigger blocks are built from smaller ones: an ECG front end reuses op-amps and switches,
SAR and ΣΔ ADCs reuse comparators, switches and op-amps, LDOs reuse an op-amp as error
amplifier. Declare this so the hub can draw the hierarchy on the overview page and
cross-link designs:

- `builds_on` (component level): the components this generator draws sub-blocks from,
  with a short role. Use component ids, or a collection's source id (e.g. `aux`).
- `uses` (design level): the exact sub-block designs this design instantiates. Give
  `component` (hub component id), `design` (that component's hub design id) and `role`.
  If the design reuses a cell that is not a published hub design (e.g. a variant), you can
  still list it; the hub marks it "not on the hub".

The hub resolves every `uses` entry across components at build time, so ids must match the
other component's hub design ids exactly. It then:
- draws the component graph (cells → sub-systems → systems, above the foundation tier
  described below) on the overview page,
- shows "Built from" / "Used in" chips on each component tab,
- lists "Built from" and the reverse "Used in" designs on every design page (e.g. an op-amp
  page lists every ECG/LDO/ADC design that uses it).

**Foundation tier.** Under the components, the overview draws the technology libraries that
the generators build on: **PDK PCells** (the PDK's primitive devices: MOSFETs, MIM
capacitors, resistors, varactors, plus the devices a generator draws itself on the PDK layers,
such as MOM finger capacitors) and **Stdcell** (the `gf180mcu_fd_sc_mcu7t5v0` standard cells).
This tier is hub-side metadata, not part of your export. It is declared in the hub's
`sources.json` under `foundations`:

```jsonc
"foundations": [
  { "id": "stdcell", "name": "Stdcell", "technology": "gf180mcuD",
    "title": "gf180mcu_fd_sc_mcu7t5v0 standard cells — longer description …",
    "used_by": { "sar": "one-line role, ≤ 80 characters", "sdm": "…" } }
]
```

- `title`: the text before ` — ` is the short description printed on the library's slab;
  the full title appears in its tooltip and in the list view.
- `used_by` keys are component ids or a collection's source id (`aux` covers every `aux-*`
  component, including families added later, so keep its role true for all of them). A
  component id listed as well overrides its collection's role. A component that does not use
  the library is simply left out.

`hubkit.py build` resolves this into `foundations` in `data/catalog.json` (`link_foundations`)
and warns about keys that match no component of the build (a typo, or a component not exported
yet). A slab's design count is the number of designs of the generators that use it (with the
current global options), not a per-design check. When your generator starts or stops using a
library (for example, it begins to instantiate standard cells), or adds a family whose devices
differ, update `used_by` in the hub's `sources.json`, or ask the hub maintainer to.

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
| `image` | `src` (hosted svg/png/webp/jpg) or `gds` + `cell`, `bg`: white/dark/none (use `dark` for figures drawn on a dark background), `max_height` | figure (click to open full size) |
| `layout` | `gds`, `cell` (optional sub-cell), `max_height` | rendered GDS thumbnail + link to the raw GDS in the repo |
| `gallery` | `items[]: {label, src \| gds, cell?, caption?}`, `style`: tabs/grid, `cols`, `default` | several figures as tabs or a grid |
| `downloads` | `items[]: {label, file \| src \| url, note?}` | link list; `file` → raw file in the repo, `src` → hosted, `url` → external |
| `tabs` | `tabs[]: {label, key?, labels?: {pre, partial, full}, blocks[], vdd?, tech?}` (`key` = stable deep-link value, e.g. a design id), (`labels` = stage-dependent tab label), `style`: tabs/select, `label`, `default`, `id` (selection is kept in the URL as `t.<id>=<index>`, so it can be deep-linked) | switch between alternative block groups (benches, corners, topologies…); more than 12 tabs become a dropdown |

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
- A column named `vdd` makes the table follow the global V<sub>DD</sub> filter when all its values
  are design supplies used in the hub (e.g. 1.8 / 3.3). Per-corner supplies (1.62 V …) are
  never filtered; force it with `vdd_filter: true`, or disable it with `vdd_filter: false`.
  A `tech` column follows the technology filter. Explorers apply the same rule to a `vdd` column.
- `stage_column: "stage"` makes it follow the global simulation stage (rows without a stage
  are always shown). Add `stage_group: "<column>"` (e.g. the design-id column) to keep, per
  entity, the row of its best available stage ≤ the selected one. This mixes e.g. full and
  partial extractions in one table, with the stage column telling which is which.

**Charts** are plain Plotly (v2.35) figures. Write traces exactly as you would for
`Plotly.newPlot`:
- Colours, fonts and backgrounds are themed by the hub. Only set them when they carry
  meaning (e.g. pass/fail colours). For colours that must follow light/dark mode, use the
  tokens `"theme:ink"`, `"theme:muted"`, `"theme:line"`, `"theme:paper"`, `"theme:brand"`,
  `"theme:accent"`, `"theme:good"`, `"theme:warn"` and `"theme:bad"` anywhere in traces or layout.
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
  The hub shows the alternative matching the selected stage. An alternative may also carry
  `fb: true` or `fb: false` to apply only when "fill from earlier stage" is on or off. For
  example, a Full post-PEX view mixing full and partial designs (`fb: true`) next to a
  full-only one (`fb: false`). With "fill from earlier
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

Pareto: users choose off / overall front / front per colour group / best-value envelope per
colour group (best y in ~24 x bins, direction from the y dim's `better`); set the initial mode with
`pareto_default` (or a preset's `pareto`): `"all" | "color" | "envelope"`. Fronts exclude the highlighted (delivered) overlay unless
`pareto_include_highlight: true`; restrict the candidates with `pareto_on: {column: [allowed
values]}` (e.g. only feasible points). `fixed_axes: true` keeps the axis ranges over all points
(stable when filtering); `filters_default: {catKey: [visible values]}` sets the initial chips;
`presets[].desc` (markdown) is shown when that preset is selected. `table: {columns: [dim keys or
column objects], title?, page_size?}` adds a linked table under the plot that lists exactly the
points currently shown (it follows the chips, ranges, stage and V<sub>DD</sub>), with CSV export.

Dim options: `type: "cat"` (categorical; `labels`, `order`, `colors: {value: "#hex"}`,
`symbols: {value: "star"}` — any Plotly marker symbol name; colours may be theme tokens such as `"theme:ink"`),
`log`, `better`, `unit`/`si`/`digits`. Explorer options: `cat_axes: true` lets categorical
dims be chosen as X/Y (strip plot); `presets[]: {label, x, y, color, symbol, facet, logx,
logy, pareto, show: {catKey: [visible values]}}`; `preset_default` (index applied on load).
Rows with a null `stage` are shown at every stage. With `stage_group: "<column>"` (e.g. the
design-id column), each entity keeps only its best available stage ≤ the selected one, so
designs with different extraction levels can be shown together.

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

- **Technology ids:** `gf180mcuD` (GF180MCU-D, 1.8 / 3.3 V) and `openrpdk28` (OpenRPDK28,
  0.6 / 0.9 V). A new PDK gets a new id plus a label in the hub's `sources.json`.
- **Units:** base SI with `si: true` wherever the quantity has an SI unit.
- **Stable ids:** design ids appear in URLs.
- **Hard failures:** `results.<stage>.status: "fail"` marks a failure at that stage (e.g. a
  nominal screen fails); the matrix shows it red instead of amber.
- **Determinism:** sorted output, no per-design timestamps, so git diffs stay small.

## 8. Size budget

The hub hosts only referenced files (plus ~50 KB per layout thumbnail). Keep each
component under **150 MB** of hosted files: `hubkit validate` prints the total. Decimate
huge sweeps, and keep hosted JSON compact.

## 9. Per-repository sites

The per-repository GitHub Pages sites are retired: repositories contain no website
(no `index.html`, no `assets/`, no `pages.yml`), and GitHub Pages is disabled for them. The
hub is the only site. Repository-specific pages belong in the export (§4.2).
