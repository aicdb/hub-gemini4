# ls (level shifters) — old-site inventory and hub coverage

Old site: `ls-gen-gemini4/docs/index.html` (single 12 MB page, data inlined = `report_data.json`,
verified byte-identical) + `assets/schem_TOP*.svg`, `assets/layout_TOP*.png`, `assets/layout_REF_UNIT_INV.png`.
Hub: `adapters/ls.py` (designs, detail docs, shared figures), `adapters/ls_pages.py` (13 pages),
`adapters/ls_lib.py` (helpers). Page ids below are `#/ls?page=<id>`; design pages `#/ls/<TOPx>.<crossing>`.
Stage handling: every pre/post-PEX variant is a stage alternative (`stage` + `alt`); the hub's global
*Simulation stage* option replaces the old toggle. Pre-PEX-only content (DSE) carries `stage: "pre"` and is
shown as a marked fallback at full post-PEX (or "not available" with fallback off, = old `[N/A]`).

Legend: ✓ reproduced (location) · ≈ reproduced with a different control · ✗ not reproduced (reason).

## Header / global
1. ✓ H1 title → component `title`.
2. ✓ Badge row (GF180MCU, 11 topologies, HV-tolerant, gLayout+PEX, GitHub link) → `overview` page, first markdown block.
3. ✓ Subtitle paragraph → `overview` page markdown.
4. ≈ "Simulation Data View: Pre-PEX / Post-PEX" toggle (hero buttons, checkbox, nav buttons, status text, per-section mode badges) → global Simulation stage option; stage badge on every stage-specific block; explanatory note on `overview`.
5. ✓ KPI tiles (6, different set/labels in pre vs post mode, computed from hvt_grid/hvt_speed/pilot) → `overview` stats block (stage alternatives; JS `initKPIs` ported, values verified: pre 11,188 / 4.80 V / 200 MHz / 887 ps / 260.1 ps). Topology names in the pre labels are now derived from the data (the old page hard-coded TOP10 for a TOP9 value; review gap 25).
6. ✓ Total-sims numbers → also component header `stats` (pre 11,188, post 6,984, DSE 3,152).
7. ≈ Tab navigation (13 sections, hash routing `#overview` …) → 13 hub pages with the same order.
8. ✗ "All Tabs: ON/OFF" (show every section on one long page) — UI convenience only; the hub shows one page at a time (no content lost).
9. ✓ Footer (vlsipool / server-coordinator / ngspice-46, links) → `overview` muted note. The link to the retiring aicdb.github.io Pages site is dropped (repo link kept).

## 1. Architecture Portfolio & Flagship 6-Domain Benchmark (`overview`)
10. ✓ Section title + intro prose (verbatim from index.html). Old-control wording ("When toggled to Post-PEX … [N/A]") reworded for the hub's Simulation option.
11. ✓ 1.1 portfolio table: topology id/name, citation links (+ full-reference tooltips → separate *Literature* column), coupling, schematic area (tooltip: MOS/R/C breakdown) + MOS+passive split, gLayout&PEX area (tooltip: bbox, Cp, Rp) + bbox/Cpar, 6 domain cells PASS·tpd·Pstat / FAIL·swing (each links to the design page), pass score → table, stage alternatives.
12. ✓ 1.2 pilot detail table (13 columns: topology, rails, status, VOL, VOH, swing, tpLH, tpHL, tpd, trise, tfall, Pstat, Edyn; post mode shows N/A rows) → table (+ Ptot, domain id, design links), stage alternatives. Numeric VDDH column added, so the global VDD option filters the rows.
13. ≈ 1.2 "Filter by domain / topology" dropdowns → table filter box (caption explains).
14. ✓ Per-design benchmark rows also in every design detail ("Nominal benchmark" kv).

## 2. Design-Space Explorer (`explore`)
15. ✓ Title + intro prose + "Pre-PEX Sizing Cloud" badge (stage badge).
16. ✓ 4 stat tiles per domain (total DSE+PVT sims, feasible/total, 4-objective ND count, robust speed-front points).
17. ≈ Domain segmented filter (5 domains) → tabs. Tabs `id=dse_dom` with domain keys (deep link `t.dse_dom=<domain>`), `vdd` = the domain's VDDH.
18. ≈ Trade-off segmented filter (6 presets) → tabs `id=dse_trade` (keys speed/energy/area/leakage/sym/drv) for 2.1 + 6 unfaceted and 6 faceted explorer presets for 2.2.
19. ✓ 2.1 Pareto-front overlay per domain × trade-off (grey feasible cloud, per-architecture hv-step fronts, filled = PVT-robust / open = fails corner, dashed for arch ≥ 7, black diamonds = ULP/BAL/HS cards, legend with feasible counts, shared log ranges, drv preset = s_drv-bin upper envelope) → 30 Plotly charts (`data/dse/overlay_*.json`), dynamic title + caption.
20. ✓ 2.2 11-panel per-architecture clouds → explorer per domain (`data/dse/explorer_*.json`): one *“<trade-off> · 11 facets”* preset per trade-off (facet = architecture, fixed shared axes, colour = PVT status blue/orange/grey, per-panel front incl. the delivered cards like the old fronts, per-facet point/front counts, preset text naming the architectures with 0 feasible samples); delivered cards ringed, BAL rings open the hub design; architecture colours equal the 2.1 palette. The old per-panel captions are in the *2.2 Per-architecture panel summary* table, per trade-off (samples plotted · front · PVT-robust). Hub-encoding intro; old legend text kept in the caption. Round 3: delivered cards drawn with their own symbols (▼ ULP, ◆ BAL, ▲ HS, as the old diamonds) and only BAL cards with a hub design are ringed, so the explorer's “click a ringed point” line is accurate; preset texts describe the per-colour front lines; TOP6/TOP11 colours changed to mid-tones that are visible in dark mode (also in 2.1 and the unit-inverter charts).
21. ✓ Hover text of every point (topology, card, tpd/tpLH/tpHL/Fmax, Edyn/Psw/Pstat/FoM, areas, 5 knobs, PVT status) → 2.1 front/card hovers + explorer hover dims. Grey cloud points now carry the full old hover text too (compact `customdata`); explorer hover adds tpLH/tpHL/Fmax/MOS/passive area.
22. ✓ 2.3 deliverable sizing cards table (12 columns incl. badges, knobs, status+swing, PVT robustness) → per-domain table. BAL links only when the DSE delay agrees with the linked pilot within 5 % (TOP4 BAL cards are not linked: earlier netlist revision; stated in the caption). Card / knob cells are two-line markdown (table no longer forced wide).
23. ✓ 2.4 4-objective non-dominated table, sortable, default FoM desc → per-domain table (+ WC tpd and sample id columns).
24. ≈ 2.4 "Only PVT-checked & robust" checkbox → type `robust` in the filter box (caption); "Show all / top 60" → page_size 60 + "Show more".
25. ✓ Post-PEX mode notice ("DSE is pre-PEX only") → stage `pre` on the domain tabs (fallback badge / not-available note) + caption.
26. ✓ Deep links `#explore/<preset>/<domain>` → `#/ls?page=explore&t.dse_dom=<domain>&t.dse_trade=<preset>` (tabs with ids keep the selection in the URL and across stage changes).

## 3. Schematics, gLayout & PEX (`topologies`)
27. ✓ Title + intro prose.
28. ✓ 3.1 layout/PEX summary table (schematic area MOS+pass, W×H, bbox area, extracted devices, Cp count, total Cpar, Rp count, status) → table (+ total Rpar).
29. ✓ 11 topology buttons (with ★ for PEX) → tabs labelled `n. short_name ★`. Tabs `id=topo`, key = topology id.
30. ✓ 3.2 title, description, origin box (area pill, citation pills, origin note, full reference list with URLs) → markdown per tab (and in every design detail).
31. ✓ Schematic SVG (inline in old page) → image `assets/schem_TOP*.svg` (hosted as-is; identical to the inline SVG) + `files.schematic` of every design.
32. ✓ gLayout layout PNG + metrics bar (BBox, area, devices, Cp (C), Rp) → image `assets/layout_TOP*.png` + caption; also design `images[]`, card thumbnail and detail section.
33. ≈ View toggle "Schematic + gLayout / Schematic only / gLayout only" → both shown side by side (click opens full size).
34. ✓ "Open SVG ↗" / "Open Layout PNG ↗" links → image blocks open the full-size file.
35. ✓ 3.3 SPICE netlist: schematic `.subckt` in pre mode, Magic `.pex.spice` in post mode (+ N/A text) → code blocks, stage alternatives (also in every design detail). Old-control sentence reworded for the hub's Simulation option.
36. ✓ 3.3 caption (devices used, toggle hint) → note.
37. ✓ "View All 11 Topologies Gallery" (origin + schematic + layout per topology) → collapsed section with markdown + 2-item grid gallery per topology.
38. ✓ (added) list of hub design pages per topology.

## 4. HV-tolerant explorer (`hvt`)
39. ✓ Title + problem-statement prose.
40. ✓ 4.1 highest-voltage / highest-speed summary (6 architectures; stack, schematic area, gLayout area + Cpar, safe grid points, max safe VDDH, peak |Vox|, worst MOSFET, fastest safe tpd with VDDL→VDDH, max safe f_max string) → table, stage alternatives (JS ported; values verified against the old page). Areas printed with 2 decimals as on the old page. Round 3: merged two-line cells (area + split, area + Cpar, tpd + rails, f + delay) to narrow the table.
41. ✓ 4.2 architecture select → select-tabs `id=hv_arch` (default TOP10); option labels derived per stage from the data (highest oxide-safe VDDH / frequency) instead of the old hard-coded, partly wrong ones.
42. ✓ 4.2 four VDDL×VDDH heatmaps (peak oxide stress with green/yellow/red classes and worst-MOS labels; Psw µW/nW + Edyn; tpLH; tpHL with blue gradient, ">1.8V" and FAIL cells; per-cell tooltips) → Plotly heatmaps (`data/hvgrid/`), stage alternatives.
43. ✓ 4.2 metrics bar (safe points, highest safe VDDH, fastest tpd, peak stress) → note, stage alternatives.
44. ✓ 4.3 frequency sweep chart (5 curves, peak |Vox| vs f, red markers for oxide-unsafe points, 1.80 V limit line, tooltips; N/A in post if no data) → Plotly chart, stage alternatives.
45. ✓ 4.4 HV waveform viewer (8 operating points select, |Vox| in the label, waveform, info line) → select-tabs `id=hv_wave` with stage-dependent labels (pre / post |Vox|) + charts + notes, stage alternatives.
46. ✓ 4.5 15-corner PVT table (logic pass, oxide safe, combined yield pill ≥12, nominal tpd/|Vox|, WC delay corner/tpd, WC oxide corner/|Vox| + MOS) → table with design links (+ nominal worst MOS), stage alternatives. Round 3: |Vox| and worst MOSFET merged into two-line cells.
47. ✓ (added) raw hvt_grid (432) and hvt_speed (576) records → collapsed tables. Raw tables carry a numeric VDDH (`vdd`) column for the global VDD option. Round 3: `vdd_filter: true` so the sweep VDDH values follow the global VDD option.

## 5. Single-domain comparison vs unit inverter (`unitinv`)
48. ✓ Title + intro prose (with link to the appendix page).
49. ≈ "Scale to:" node select (7 nodes) → select-tabs `id=ui_node` (keys 180nm…7nm) with the old option labels; non-native tabs carry a **"Model projection, not a simulation"** warning.
50. ✓ Mode badge / node badge → stage badges + node in the tab label and block titles.
51. ✓ Scaling banner (target node, κ_L, S_A,MOS + density, MIM density, S_t, S_C,MOS, S_C,cap + ratio, scaling-effect text / native text) → kv + markdown per node.
52. ✓ 5.1 heading (native / scaled variants), description prose, baseline table (VDD, swing pill, Psw, Edyn, tpLH, tpHL, tpd, Pstat, ratio) → table per node, stage alternatives. VDD label column renamed so the global VDD option no longer empties it.
53. ✓ 5.1 REF_UNIT_INV netlist details (pre: spice, post: pex_spice) → collapsed code, stage alternatives. Old "Toggle Pre-PEX / Post-PEX" wording updated.
54. ✓ 5.1 layout card (layout_REF_UNIT_INV.png, 180 nm bbox, active MOS, scaled cell area for other nodes, Magic PEX stats) → image + kv.
55. ≈ 5.2 Y-axis scale select (log/linear) → Plotly buttons in each chart. Buttons above the plot, legend below it (no overlap).
56. ≈ 5.2 topology-group filter (all / TOP1–8 / TOP9–11) → Plotly dropdown in each trend chart.
57. ✓ 5.2 Plot 1/3/4 trend curves (psw/rise/fall multipliers vs VDD, per-topology colours, dashed for ≥TOP7, open red circles for failing power points, 1.0x reference, tooltips) → 3 charts per node × stage.
58. ≈ 5.2 "Single-VDD bar & cost comparison point" select → select-tabs (7 VDDs, default 1.8 V) holding Plot 2 + the 5.4 table. Tabs `id=ui_vdd`.
59. ✓ 5.2 Plot 2 bar comparison at one VDD (3 bars per topology, FAIL rows with attempted Psw/swing, value labels) → horizontal grouped bar chart per node × stage × VDD.
60. ✓ 5.3 11×7 matrix with REF row, architecture/area/GE column and the 4 cell modes (triplet with tooltip, psw, rise, fall; FAIL cells with swing/attempted Psw) → select-tabs × tables per node × stage. Tabs `id=ui_cell`.
61. ✓ (added) sortable long-form topology × VDD table per node × stage.
62. ✓ 5.4 node-scaled cost table (REF row; 180 nm area + GE, node MOS / passive / total area, GE with growth, scaled Edyn/Psw, tpLH/tpHL or FAIL, multipliers) + heading with VDD/node/mode + caption → table per node × stage × VDD.
63. ✓ Scaling model (NODE_SCALING_LAWS, TOPO_SCALING_PROFILE, computeTopoNodeArea, scaleBaselineRow, scaleTopoRow incl. toFixed rounding) ported to Python; cross-checked against the original JS with node: 1,246 values, 0 mismatches.
64. ✓ Deep link `#unitinv/<node>` → `#/ls?page=unitinv&t.ui_node=<node>`.

## 6. 2D operating-region heatmaps (`opregion`)
65. ✓ Title + intro prose.
66. ≈ Topology select (default TOP6) + metric select (6 metrics) → nested select-tabs. Tabs `id=opr_topo` / `opr_metric` (keys = topology / metric).
67. ✓ 10×7 VDDL×VDDH grid with ✓/✗ swing labels or values / FAIL, pass/fail colouring, tooltips (VDDL, VDDH, pass, tpd, Pstat …) → Plotly heatmaps, stage alternatives (passing cells additionally shaded by value).
68. ✓ (added) raw 770-point grid table. Round 3: `vdd_filter: true` on the raw grid.

## 7. Split-rail matrix (`splitrail`)
69. ✓ Title + intro prose.
70. ≈ Cell-metric select (4 modes) → select-tabs. Tabs `id=split_metric`; cells as two-line markdown so the 11 topology columns wrap.
71. ✓ 16 domains × 11 topologies matrix (title, rails, PASS·tpd / tpLH/tpHL / Pstat / Edyn, FAIL, N/A) → tables, stage alternatives. Round 3: VDDH column + `vdd_filter: true`; topology columns no longer forced to 160 px.
72. ✓ (added) long-form table of all 176 runs with every metric. Round 3: `vdd_filter: true`.

## 8. Waveform viewer (`waveforms`)
73. ✓ Title + intro prose.
74. ≈ Topology select (default TOP8) + domain select (default sub-Vt) → nested select-tabs. Tabs `id=wave_topo` / `wave_dom` (keys = topology / domain, domain tabs carry `vdd`); design pages link to the viewer with the topology/domain preselected.
75. ✓ Waveform plot (VIN dashed, VOUT for all 9 stored PVT corners with tt27/ss−40/ff125 highlighted, rail guides, title with stage, pilot fallback) → Plotly charts (`data/wave/`), stage alternatives; also in each design detail.
76. ✓ Metrics bar (PVT yield, nominal tpLH/tpHL/Pstat, WC corner tpLH/tpHL/tr/tf; pilot variant) → note, stage alternatives.

## 9. VSS1 × VSS2 viewer (`vss2d`)
77. ✓ Title + intro prose.
78. ≈ Topology select (default TOP8) + 2D-space mode select (2 modes) → nested select-tabs. Tabs `id=v2_topo` / `v2_mode`.
79. ✓ Plots 1–4 (tpLH, tpHL, Psw+Edyn, Ptot+Pstat) 9×9 maps with the emerald→rose gradient, FAIL cells, two-line labels, axis labels for both modes, tooltips → one 2×2-subplot Plotly figure per topology × mode × stage.
80. ✓ Metrics bar (pass coverage, tpLH/tpHL/Psw/Edyn ranges) → note, stage alternatives.
81. ✓ Power-analysis box (per topology) → warn note, verbatim.

## 10. PVT (`pvt`)
82. ✓ Title + intro prose.
83. ✓ Summary table (66 rows; yield pill, nom tpLH/tpHL, WC corner, WC tpLH/tpHL, WC tr/tf, nom/WC Pstat, nom Edyn) → table (+ nom/WC tpd, WC Pstat corner, design links), stage alternatives. VDDH column for the global VDD option; caption's list of PVT-vs-pilot revision mismatches generated from the data (TOP4, TOP6–TOP11).
84. ≈ Topology / domain filters → filter box.
85. ✓ (old page had an empty chart slot) → added yield heatmap (topology × domain).
86. ✓ (added) all 1,320 corner records → collapsed table; per-design 20-corner table + tpd/Pstat chart in every design detail.

## 11. Monte Carlo (`mc`)
87. ✓ Title + intro prose (3σ acceptance definition).
88. ✓ Ensemble select (21, label with 3σ status and µ+3σ) → select-tabs `id=mc_ens` with stage-dependent labels (pre / post verdict and µ+3σ); tabs carry `vdd`.
89. ✓ 11.1 histogram (12 bins, counts, µ and µ+3σ markers, summary line, N) → bar chart, stage alternatives. Y range leaves room for the bar labels.
90. ✓ 11.2 6-seed waveform overlay → chart, stage alternatives.
91. ✓ 11.3 summary table (13 columns incl. 3σ pill, seed yield, µ−3σ swing colouring, tpd µ/σ/µ+3σ, tpLH/tpHL µ+3σ, Pstat µ/µ+3σ, Edyn) → table, stage alternatives; full MC kv (min/p95/max, σ's) per ensemble and in design details. VDDH column added.

## 12. Insights (`insights`)
92. ✓ Title + intro + 7 insight cards (verbatim) → markdown blocks in a 2-column section.

## 13. Appendix (`appendix`)
93. ✓ Title + intro (link to the unit-inverter page) + 3 framework cards with formulas (verbatim).
94. ✓ 13.1 node table (13 columns + ref notes) → table (+ S_t,RC and Φ_cont, the model's other parameters). Core/IO VDD column renamed so the global VDD option no longer empties it.
95. ≈ 13.2 trajectory metric select (5 metrics) → select-tabs; GE/area stage-independent, tpd/Edyn/Psw× stage alternatives (they use the stage's unit_inv rows, as in the old page). Tabs `id=app_metric`; legend anchored top-right (full-height plot).
96. ✓ 13.2 trajectory chart (11 series over 7 nodes, log axis, κ_L tick labels, legend with 7 nm value) → Plotly charts, labelled as model projections.
97. ✓ 13.3 decomposition table (REF row, MOS/cap/res split, f_cap, f_RC, 5 node areas + GE) → table (+ f_cont).
98. ✓ Cross-links section 5 ↔ 13 → markdown links to `#/ls?page=…`.

## Designs view / design records
99. ✓ 72 designs = 11 topologies × 6 flagship crossings + 6 HV operating points (TOP9–11); `vdd` = output VDDH; axes topology / domain / crossing type / direction / coupling.
100. ✓ Matrix topology × domain (VDDH groups), default cell = tpd / PVT yield / output swing, presets (static power & energy, rise/fall, worst-case PVT, MC µ+3σ, oxide stress, area); hard nominal failures carry `results.<stage>.status = "fail"` (red cell instead of amber); card metrics tpd / PVT yield / Edyn / Pstat / swing / area, cards grouped by topology; metric descriptions; card thumbnail = layout PNG.
101. ✓ Results per stage (pre = schematic dataset, full = Magic RC full-cell PEX): nominal pilot (or 25 MHz HV) metrics, PVT yield & worst case, MC yield/µ/σ/µ+3σ, oxide stress, layout area; PVT/MC counts; robust = all corners pass and MC 3σ pass; notes for nominal failures, PVT-vs-pilot netlist mismatch, Edyn = 0, HV oxide violations. When the PVT/MC runs used an earlier netlist revision than the pilot (TOP4, TOP6–TOP11 pre-PEX) the note says so for PVT **and** Monte Carlo, including the MC mean, and that the worst-case/MC/robust figures describe that revision. Layout area is passed unrounded (the hub formatter shows values ≥ 10⁴ as integers). Round 3: negative output swings (failed outputs) and negative MC µ−3σ swings are not reported as metrics; the stage note states the raw value.
102. ✓ Detail doc per design: topology/origin/references, nominal benchmark kv (all fields) or HV nominal + 15-corner kv + per-point frequency sweep, transient waveforms (9 corners) or HV waveform, PVT kv + chart + 20-corner table, MC kv + histogram + seeds, layout & PEX kv + PNG, netlists (pre/PEX), sibling crossings, and "across the rest of the report" tabs (op-region maps, split-rail, VSS2D, unit-inverter row, DSE sizing cards, HV grid + HV waveforms where applicable).
103. ✗ DRC / LVS status — `drc_clean` / `lvs_clean` are null in report_data.json, so `physical.drc/lvs` are null (no DRC+LVS-clean designs in the hub filter).
104. ✗ GDS files / hub-rendered layout thumbnails — no GDS in docs/; the published layout PNGs are hosted instead.

105. ✓ Block hierarchy (BUILDERS §4.5): the level shifters are leaf cells — no topology instantiates a design of another hub component (switch, sa, opa, aux …), so neither `builds_on` nor `uses` is emitted.

Review round (27 gaps): all 23 adapter-side gaps fixed; the 4 renderer issues (front markers, tab-select overflow, Hz tick suffix, modebar overlap) were fixed in the hub, and the adapter adds explicit PVT/architecture colours for the explorer.
Round 3: annotation and guide colours use theme tokens (`theme:muted/good/warn/bad/ink/paper`) so rail labels, µ / µ+3σ markers, FAIL labels and card diamonds stay readable in dark mode. Tabs keep their `vdd` (the hub now explains an all-hidden tab group).