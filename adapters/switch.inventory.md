# switch — old-site inventory (switch-gen-gemini4/docs) and hub mapping

Source: `index.html` + `assets/app.js` (697 lines) + `data/index.json`, `data/sweep.json`, `data/gmid.json`,
`designs/<key>/{data.json, schematic.svg, schematic_post.svg, layout.png, <key>.gds.gz, <key>.pex.spice,
netlist.spice, lvs_reference.spice}`. 130 cards = 13 topologies × 2 VDD × 5 current classes; 125 characterised,
5 `boot_03v3 @ 3.3 V` cards are "not applicable" (only `data.json` with the reason).

Hub locations: **D** = built-in Designs view, **P:overview / P:compare / P:explore / P:method** = component pages,
**T:Overview / T:Schematic / T:Simulation / T:Layout** = tabs of the per-design detail doc (`hub/designs/<id>.json`).
"pre / post alt" = stage alternatives (`stage` + `alt`) switched by the global *Simulation stage* option.

Result: 54 items — 54 ✓ ported; 4 ✗ sub-features noted inline (10 range-bar graphic, 22 SVG hover, 36 PNG pan-zoom + layer legend, 53 layout.png hosting) — each covered another way.

**Fix round (review switch-gaps.json, 25 gaps):** all 23 non-renderer gaps addressed — see the "(fix)" notes below.
Stage model of the page views (round 3, fallback-aware alternatives): Pre-PEX = schematic; **Partial post-PEX** = the 90
unit-bank extractions; **Full post-PEX + fill from earlier stage** (default) = all 125 extracted cards (35 full + 90 partial
filled in, marked per card); **Full post-PEX, fill off** = the 35 complete cells only. Tables and the
interactive explorer use `stage_group` (each design shows its best stage ≤ the selection). All tabs have ids (deep links,
selection survives global-option changes): detail `t.tab`, explorer `t.tradeoff` / `t.exvdd`, compare `t.vdd`, method `t.vsb`.

## Data caveats found while porting (affect stage labels)
- **Unit-bank layouts (90 of 125 cards).** The published GDS of every card whose switch is wider than the generator's
  physical bank limit contains only **one unit bank** (e.g. `boot_dnw_dum__3p3v__100m-1`: GDS 86 × 72 µm, reported cell
  733 × 611 µm). The reported cell width/height/area/banks/aux grid are a formula estimate (`swgen/layout.py`,
  `scale_ratio > 1.02` branch), DRC/LVS/PEX ran on the unit bank, and the "post-PEX" netlist is that extraction with
  devices multiplied (`m=`) to full width and parasitic C scaled (`swgen/pex.py`). The adapter detects this from docs/
  alone (stdlib GDS bounding-box reader vs reported size): those cards' post-PEX results are exported as **`partial`**,
  the 35 complete cells as **`full`**; the estimated area is **not** a `results` metric for them (shown as "≈ … (estimated)"
  in pages/params, physical dims = drawn GDS).
- The generator multiplies extracted `ntop–vss` / `vb–vss` capacitances by 0.25 (65 PEX netlists) — stated in the results note.
- The old site's post-PEX Simulation tab crashed (`TypeError … reading 'n_c'`: `d.post.pex` does not exist; data is in
  `verify.pex`). The hub uses `verify.pex`.
- The old site showed the unit-bank `layout.png` for multi-bank cells under the full-cell dimensions.

## Global / chrome
1. ✓ Header title + subtitle → component `title`/`summary`; subtitle line in P:overview intro (small print).
2. ✓ Netlist toggle pre/post → global *Simulation stage* (Pre-PEX / Partial / Full post-PEX); every page/detail block has stage alternatives. (fix) Page views have pre / partial (90 unit-bank) / full+fb (all 125, as the old post view) / full no-fb (35 complete cells) alternatives; stats blocks have titles. Explorer/table at Partial: the 35 complete cells fall back to schematic rows (stated in the captions).
3. ✓ Nav → sub-tabs Designs · Overview · Topology comparison · Design-space explorer · Methodology; theme toggle = hub's.
4. ✓ Footer (generated date, tools, source link) → P:method closing note.

## Designs (list) view
5. ✓ Hero "Deliverable design cards" + lede → P:overview intro (verbatim).
6. ✓ Stats tiles (6, view-dependent) → P:overview stats per supply ("Design cards at 1.8 V / 3.3 V", follow the V_DD filter; pre / partial / full alt, + n/a tile) and component header stats.
7. ✓ Coverage matrix (valid range % + area, green/amber/red, n/a cells with reason, click → design) → D matrix with `matrix.status` on valid range (green > 97 %, amber > 0, red none — the old colour code), n/a cells with reason tooltip, preset "Valid range & area"; and P:overview "Coverage matrix" heatmaps, one per supply (follow the V_DD filter), pre / partial / full alt, clickable incl. n/a cells, ≈ marks estimated areas, "partial only" cells at Full post-PEX.
8. ✓ Filters: VDD → global V_DD; Current / Topology → D axis chips; Status DRC+LVS → global *Verified*; Status rail-to-rail → (fix) search tags `r2r-pre` (70) / `r2r-post` (49), no substring overlap, + matrix colours; R_on grade → tag `R_on grade B` and sortable tables.
9. ✓ Group headers "R_on points at I_max: A/B/C/D" → P:overview table "R_on points per supply and current class" (labelled as specification thresholds).
10. ✓ Design card → D cards, (fix) valid-range intervals as search tags (`valid … (pre)` / `(post)`); 9 card metrics (valid range, R_on, R_on wc, t_on, t_off, E/cycle, Q_inj, max |Q|, area where drawn) + stage/robust/PVT/DRC/LVS/PEX badges, grouped by current class (`cards_group_by`); valid-range intervals in params ("Valid range (pre-PEX / … post-PEX)"). ✗ sub-feature: the range-bar graphic.
11. ✓ n/a cards → (fix) 5 design records with `"na": reason` (n/a matrix cells with reason tooltip, "not applicable" card badge, detail page with the reason + topology description; old ids resolve) + P:overview "Not applicable cards" table (wrapped, rows link) + heatmap n/a cells + header stat.
12. ✓ Comparison table (all 17 columns, sortable, rows open the design) → P:overview "Comparison table" (fix: one table, `stage_column` + `stage_group`, generator order by default; + V_DD, Range %, Layout, Stage columns, CSV) and D Table view.

## Detail view (tabs Overview / Schematic / Simulation / Layout → `tabs` block in the detail doc)
13. ✓ Header (round 3: schematics moved to `images[]` with `bg: "dark"`, so the gallery shows them without a white frame; gallery order Layout · Schematic · post-PEX schematic): title, axis chips (topology, class), tags (devices, grade, r2r-pre/post, "unit-bank layout (physical area = drawn unit bank)" / complete layout), R_on target in `params` + summary (unit-bank cards start with the drawn-vs-estimated size statement), DRC/LVS/PEX badges (Physical panel), figure gallery (schematic, layout thumbnail, post-PEX schematic), Performance-by-stage table, files.
14. ✓ Post-PEX note → T:Overview note (post stage only; adds the partial-extraction explanation for unit-bank cells).
15. ✓ Topology panel (description + circuit notes) → T:Overview "Topology".
16. ✓ Key results (12 tiles with sub-notes) → T:Overview `stats` (pre / post alt); area tile reads "Area (estimated)" with drawn unit-bank size for multi-bank cells.
17. ✓ Specification checks (pass/fail coloured) → T:Overview table (pre / post alt; Result column first, long text wraps); DRC/LVS rows say "drawn unit bank" where applicable.
18. ✓ Design point (W_s, knobs, aux slices, R_on target) → T:Overview `kv`.
19. ✓ Knob exploration (chosen row highlighted, estimated area labelled) → T:Overview table (fix: W_s printed as on the old site, 1 decimal µm / 2 decimals mm).
20. ✓ netlist.spice link → T:Overview downloads (repo link) + Files panel.
21. ✓ n/a "Not applicable" panel (reason + description) → P:overview n/a table + Topologies table.
22. ✓ Schematic with gm/I_D annotation (schematic.svg / schematic_post.svg + explanation) → T:Schematic image (pre / post alt, dark bg). ✗ sub-feature: inline-SVG hover (the hub shows SVGs as images; caption rephrased, device table carries the operating points).
23. ✓ Devices table (14 columns, WI/MI/SI coloured, ×naux) → T:Schematic table (pre / post alt).
24. ✓ Capacitors table → T:Schematic table (when caps).
25. ✓ Post-PEX extraction note (n_c, r_path, coupling) → T:Simulation note (post alt, from `verify.pex`; old site crashed here). (fix) States the generator's scaling law (C × (1 + 0.22·(W/W_drawn − 1))) and calls the IN/OUT stripe R an estimate (formula).
26. ✓ R_on vs input (15 PVT grey, tt, worst dashed, other-netlist tt dotted, target + A/C/D lines, valid shading, log y range) → T:Simulation chart (pre / post alt).
27. ✓ Off leakage vs input (15 PVT, 125 °C/27 °C colouring, limit line, log) → chart (pre / post alt).
28. ✓ Turn-on edge (ck / switch gate / output, caption) → chart.
29. ✓ Turn-off edge → chart.
30. ✓ Full on/off cycle → chart.
31. ✓ Charge injection vs input → chart.
32. ✓ Off-isolation (log f) → chart.
33. ✓ Tracking distortion harmonic bars H2…H9 (dBc, base −160) + both THD values → chart.
34. ✓ Timing and energy over PVT (corner × temperature grid) → T:Simulation table with temperature column groups (t_on, t_off, E), pre / post alt.
35. ✓ Charge injection over PVT → T:Simulation table (pre / post alt).
36. ✓ Layout panel: DRC/LVS, size, area, aspect, banks, aux slices/grid, GDS + LVS downloads → T:Layout: GDS thumbnail (`layout` block, repo link), `kv` (incl. drawn unit-bank size, estimated cell size, PEX details), downloads (GDS, LVS, PEX). ✗ sub-features: the PNG pan/zoom viewer and the PNG's layer legend (hub rule: GDS thumbnails, no layout images).
37. ✓ Switch-array table incl. stripe R (est.) and % of R_on target → T:Layout table (estimate labelled).
38. ✓ Stripe-R explanation, EM line, floorplan paragraph (+ deep-mode DRC flag) → T:Layout caption + markdown.
39. ✓ Conditional states (layout timeout, pending, EM ✗, reduced extraction, overstress / EM-limited badges) → ported in the adapter code paths (not triggered by current data; overstress/EM-limited become tags).

## Topology comparison view
40. ✓ Hero + lede + stats (cards at VDD, rail-to-rail) → P:compare intro + per-VDD stats (pre / partial / full alt, titled).
41. ✓ VDD selector + 13-topology colour legend → `tabs` with `vdd` (follows the global V_DD filter) + legend-only chart.
42. ✓ Eight charts vs current class (area, energy, |Q|, t_on, range, THD, R_on·C_off, flatness; log/lin as old; click → card) → P:compare charts (pre / partial / full alt); area chart marks estimated multi-bank areas with open markers; (fix) axis titles, decade ticks on log axes, taller legend.

## Design-space explorer view
43. ✓ Hero + lede → P:explore intro (verbatim).
44. ✓ Stats pre (2,025 / 2,025 / 1,603 / 1600/1603) and post (125 / 125 + per-view front counts) → P:explore stats (pre / partial / full alt) + per-trade-off stats (pre: samples / front points; post: cards / front cards). (fix) A note at the top links to the Pre-PEX sweep view.
45. ✓ VDD (default 3.3 V) + 6 trade-off selectors with captions → "Trade-off views": tabs per trade-off → V_DD tabs (default 3.3 V, follow global V_DD); also explorer presets. (fix) Deep links `t.tradeoff=<i>&t.exvdd=<j>` replace `#explore/<preset>/<vdd>`.
46. ✓ (partial / full alternatives for the post views; card diamonds now mid grey, visible in both themes) "Pareto fronts by topology" overlay (13 hv fronts, filled/open = 15-PVT robust, card diamonds clickable, full hover) / post: "Post-PEX Pareto fronts of the design cards" → chart (pre / post alt, `link_designs`).
47. ✓ Per-topology design clouds (13 charts, n/a box, legend paragraph) / post variant → 3-column section of 13 charts (pre / post alt).
48. ✓ Front designs table (11 columns + 15-PVT flag) / post variant (card links, R_on point) → table (pre / partial / full alt; fix: estimated areas greyed with tooltip, per-row extraction column).
- (new, fixed) Interactive explorer — `stage_group: "design"` (Full post-PEX + fallback: 35 full + 90 partial cards; without fallback: 35), topology colours = old TCOL palette, hover always shows R_on wc and R_on·area, card I_max = 5 % VDD / R_on,wc like the sweep (class target in its own dim), presets reset facet/Pareto. Over all 2,025 sweep samples + 125 cards with all sweep dimensions (R_on wc, area est., |Q|, E, t_on, range, R_on·area, THD, I_max, W_s, 15-PVT ratio, 7 knobs, card-only metrics), categorical topology / supply / class / source / layout / PVT / front filters, delivered cards highlighted and clickable, 10 presets; follows the global stage (pre = sweep + card schematic results; post = cards by extraction coverage).

## Methodology
49. ✓ Flow, 9 steps (full prose) → P:method "Flow" (+ one sentence mapping the header switch to the hub's stage option — fix: Full for complete cells, Partial for unit-bank extractions).
50. ✓ Testbenches (8 items) → P:method "Testbenches".
51. ✓ Devices table (+ W_min) → P:method table (fix: full width, description wraps).
52. ✓ gm/I_D charts with V_SB selector 0.0 / 0.9 / 1.8 V → P:method tabs (`t.vsb`) × 2 charts.

## Data / files
53. ✓ Per-design downloads → `files` (GDS, netlist, PEX, LVS, data.json as repo links) + T:Layout downloads. ✗ `layout.png` not hosted (hub rule; replaced by the GDS thumbnail).
54. ✓ data/index.json, sweep.json, gmid.json → P:method "Data files" (repo links) + hosted explorer data.

## Review gaps not changed / notes
- Gap 18 (card diamonds): the renderer has no themed sentinel colour for chart markers; the diamonds are now mid grey with a
  white outline (visible in light and dark mode) and the captions say "grey diamonds".
- Gap 25 (layout area in `results` at every stage): kept for the 35 complete cells (needed for the area matrix preset and card
  metric) with a metric `desc` "layout property of the drawn cell, identical at every stage"; not emitted for unit-bank cells.
- Gaps 19 and 24 were renderer issues (fixed in the hub); presets also set `facet`/`pareto` explicitly.
- Round 3 not changed: scroll position reset on a global-option change (renderer `window.scrollTo(0,0)`); r2r/grade badges on
  cards (the renderer does not show tags on cards; they are search tags and detail chips); heatmap pastel colours stay
  fixed (readable in dark mode, but bright). Compare legend chart made taller (290 px) so it does not scroll at phone width.
- Default Designs-matrix cell: valid range + R_on wc (area is real only for 35 cells; available via the "Valid range & area" preset).
