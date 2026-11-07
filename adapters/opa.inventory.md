# opa — inventory of the retired opa-gen-gemini4 GitHub Pages site

Source: `opa-gen-gemini4/docs` (index.html, assets/app.js, data/**, designs/<load>/<card>/**).
Adapter: `adapters/opa.py` (+ `opa_fmt.py`, JS-faithful formatters). Verified against a local hub build
(Designs view, all 4 pages, detail docs for 2p/200f × standard/ULP at Pre-PEX, Full post-PEX and
Partial-without-fallback; no console errors).

Locations: **D** = built-in Designs view · **OV** = page "Library overview" · **DS** = page "Design space" ·
**DB** = page "Database" · **M** = page "Methodology" · **X** = design detail page (hub header + detail doc).
Stage mapping: old "Pre-PEX" → `pre`; old "Post-PEX" (whole-cell Magic C-only `ext2spice`) → `full` (note on every design);
old "Pre + Post overlay" → collapsed overlay/comparison sections in X and per-stage tables in OV.

**Result: 76 items — 74 ✓, 2 ✗ (both the layout-SVG image, which the hub rejects by policy).**

## G. Global chrome
1. ✓ Brand / title — component `title` "GF180 Op-Amp Design Library".
2. ✓ Load C<sub>L</sub> selector — `load` axis (chips in D, matrix column group in D), load tabs in OV / DS / DB, "same design at C<sub>L</sub> = …" link in every X summary.
3. ✓ View Level selector — global **Simulation** option (pre / full, fill-from-earlier); every stage-dependent block in X, OV, DB has `stage`+`alt`; overlay → X "… pre-PEX vs post-PEX overlay / comparison" sections.
4. ✓ Nav — pages Designs · Library overview · Design space · Database · Methodology; "Source ↗" = hub "Source repo ↗".
5. ✓ Theme toggle — hub theme toggle (charts themed by the hub).
6. ✓ Context line 1 — OV intro.
7. ✓ Context line 2 — OV intro.

## L. Designs (library) view
8. ✓ Eyebrow — OV intro.
9. ✓ H1 + intro paragraph (verbatim) — OV intro.
10. ✓ Stats tiles — OV "Library statistics" (per load: cards, 17/17 PVT pre **and** post, post-ready, DRC/LVS/PEX clean, farm evaluations); hub header tiles (+ farm evals, DSE candidates, boundary sweeps, ULP runs).
11. ✓ Matrix heading / click hint / ULP-column caption — OV "Coverage matrix …" section intro.
12. ✓ Matrix layout — D matrix (rows architecture · regime · load, cols class inside V<sub>DD</sub> groups, ULP class first in 1.8 V; cell UGB / DC gain / PM) and the classic OV table (ULP column + 1.8 V / 3.3 V groups), per load and stage.
13. ✓ ULP cell (A<sub>0</sub>, CL BW, power, PM, PVT, DRC/LVS, frontier "Min … · Max …") — OV classic table (all fields incl. frontier tag); D matrix via cell-metric preset "ULP view: DC gain / CL BW / power / PM" (frontier tag only in OV).
14. ✓ Standard cell (UGB, A<sub>0</sub>, PM, PVT, DRC/LVS, colour) — D matrix (UGB / DC gain / PM, PVT, DRC/LVS; green / amber / red — the one nominal-PM failure is `results.full.status = "fail"` → red) and OV table (good/warn/bad as `statusTuple`).
15. ✓ Cell click → card — D matrix cells; OV table values are links to the design.
16. ✓ Filters — axis chips (architecture, regime, class, load) in D, global V<sub>DD</sub>, global Verified (PVT-robust = 17/17; DRC+LVS — PEX is not a separate filter but all 336 cards are PEX-clean), global search.
17. ✓ Sort cards — D Sort select: best/worst of every card metric (A<sub>0</sub>, power, UGB, PVT-min PM, area, …); "By Architecture & Class" → "Generator order" (the old option actually sorted by UGB, a bug).
18. ✓ Card heading + count — D "N of M have … results" + header tiles.
19. ✓ Card content — D cards: title (arch · V<sub>DD</sub> · class · regime · load), thumbnail (GDS), UGB, DC gain, PM, PVT-min PM, I<sub>DD</sub>, power, noise @1 kHz, area, MC yield, CL BW (ULP only), stage/robust/PVT/DRC/LVS/PEX badges.
20. ✓ Comparison table — D Table view (default columns = the old comparison columns via `table_metrics`, all 30 metrics on demand, axes, PVT, MC, DRC/LVS, sortable, row click); Status and Physical badges in DB.
21. ✓ CSV export — D Table "Download CSV" and every DB table.
22. ✓ Footer downloads — OV "Downloads" (repo links; + ULP JSON, DSE JSONs, loads.json).
23. ✓ Footer prose — OV "Downloads" (verbatim).

## E. Design space
24. ✓ Eyebrow / H1 / intro — DS intro; counts from data (9,312 / 9,311 candidates, 6,186 sweeps); stale static "144 deliverable designs" replaced by the real 168; marker wording adapted to the hub explorer.
25. ✓ Controls — DS explorer: X / Y / colour / symbol / facet / log / Pareto, presets for the old axis pairs; supply + architecture (+ class, regime, PM check, point type) chips, numeric ranges; global V<sub>DD</sub> filters the supply.
26. ✓ Pareto plot — DS explorer per load (tabs 2 pF / 200 fF / both loads): default colour "Architecture (screened grey)" = old look (screened grey ×, feasible per architecture in the original ARCH_COLORS), symbol = point type with legend entries, delivered cards ringed at the selected Simulation stage (◆ pre-PEX / ■ post-PEX, `stage` + `stage_group`), log I<sub>DD</sub>/UGB/FoM, click → design. Pareto front restricted to feasible, PM-passing candidates (`pareto_on`). FoM of delivered points computed with the candidates' formula (labelled).
27. ✓ ULP heading "(5,040 Farm Runs)", download, caption — DS ULP section (title, downloads block, intro incl. criteria from the JSON).
28. ✓ ULP A<sub>0</sub> vs power — DS chart (12 power-scaling curves, original colours).
29. ✓ ULP CL BW vs power — DS chart.
30. ✓ ULP frontier table (8 columns, badges) — DS "ULP frontier by topology" (+ numeric envelope table with ≥90 dB counts and max-FoM design).
31. ✓ Boundary heading, download, criteria caption — DS boundary section (criteria from the JSON).
32. ✓ Boundary overview table (10 columns + Inspect) — DS "Boundary overview"; clicking a row selects that topology below (`_href` → `t.topo=<arch>`).
33. ✓ Per-parameter boundary table (9 columns, coverage badge, summary caption, default 2-stage NMOS Miller) — DS topology select (default `nmos_miller`) → table (+ P5–P95, per-supply core and 1-D ray columns).
34. ✓ Architecture filter linkage — explorer chips; ULP charts via Plotly legend (click / double-click); boundary via its own selector (not linked to one control).

## D. Database
35. ✓ Eyebrow / H1 / intro — DB intro.
36. ✓ Master table (18 columns + Physical, sortable, default UGB ↓, row link, load + level) — DB tables per load (+ both loads) with `stage_column` + `stage_group` (follows the Simulation option; 'All sat.' only for pre-PEX rows — the extracted netlist has no device OP map) and all 40+ summary scalars grouped (superset), Card ID links, Status/Physical coloured, CSV, follows global V<sub>DD</sub>.

## M. Methodology
37. ✓ Eyebrow / H1 / intro — M intro.
38. ✓ Seven-stage pipeline (verbatim) — M markdown.
39. ✓ Architecture portfolio (ID, Architecture, Input, Stages) — M table; titles verbatim, Input/Stages from generator metadata (old static table said `symmetrical_ota` = 1 stage; data = 2, noted); description as tooltip.
40. ✓ NMOS gm/Id vs I<sub>D</sub>/W — M chart (+ caption; bias V<sub>DS</sub> = 0.5 V from the LUT data — the old caption said 0.6 V, noted).
41. ✓ PMOS gm/Id vs I<sub>D</sub>/W — M chart.
42. ✓ NMOS f<sub>T</sub> vs gm/Id — M chart.
43. ✓ PMOS f<sub>T</sub> vs gm/Id — M chart.

## X. Design detail (336 detail docs, both loads)
44. ✓ Back / detail Load / detail Level — hub breadcrumbs + prev/next; twin-load link in the summary; global Simulation option.
45. ✓ Head (card id · CL, arch title, meta line, PVT / physical badges, availability) — X title, axis chips, tags, summary markdown, hub stage/robust/DRC/LVS/PEX badges, performance-by-stage table with post-PEX note.
46. ✓ Six tabs — X sections: Overview · Schematic & gm/Id operating point · Simulation waveforms (+ collapsed overlay) · PVT corners & mismatch MC (+ collapsed comparison) · Physical layout & PEX · Files & provenance.
47. ✓ 12 KPI tiles with pre→post sub-texts, ULP variant — X Overview `stats` (pre / full alternatives); multi-value tiles split (CMRR, PSRR+, PSRR−, SR+, SR−, THD, IM3) so nothing wraps. Old bug fixed: at Pre-PEX level the PVT/MC tiles showed post-PEX numbers; now each stage uses its own PVT/MC.
48. ✓ Verification Signoff Checklist (PASS/WARN/PENDING coloured) — X Overview table (stage alternatives; wrapped text so Status stays visible; MC criterion added).
49. ✓ Design Target & Passive Compensation — X Overview `kv` (stage alternatives).
50. ✓ Schematic downloads — X Schematic section (pre / post SPICE repo links, hosted schematic SVG).
51. ✓ Annotated schematic + caption — X Figures gallery → Schematic (click opens the full-size SVG; no −/+/Fit buttons, browser zoom instead); caption in the Schematic section.
52. ✓ Sizing & OP table (16 columns, negative headroom red) — X table (+ g<sub>m</sub>, g<sub>ds</sub>, V<sub>th</sub>, saturation); OP is pre-PEX only (post-PEX has no device map), labelled.
53. ✓ Simulation caption — X section intros.
54–61. ✓ Gain, phase, CMRR/PSRR±, noise, step/slew, DC transfer, Z<sub>in</sub> 1×/6×, HD2/HD3/THD/IM3 — X charts with pre / full alternatives (original names, colours, axes) + all 8 as pre-solid / post-dashed overlays in the collapsed overlay section.
62–63. ✓ PM and DC gain across 17 PVT corners — X stage alternatives + grouped pre/post bars in the comparison section.
64–65. ✓ MC V<sub>os</sub> histogram, PM vs V<sub>os</sub> — X stage alternatives + overlaid pre/post populations.
66. ✓ All 17 PVT corner evaluations (12 columns, PASS/WARN) — X table (pre / full alternatives; + saturation column; old fixed-decimal precision kept via digits).
67. ✓ DRC / LVS / PEX notice — X note.
68. ✗ (partly) Layout downloads — GDS, LVS reference and PEX netlist are repo links (✓); **"Full-Resolution Layout SVG" ✗** — layout SVGs are rejected by the hub (`**/*layout*.svg`); replaced by the hub-rendered GDS thumbnail.
69. ✗ (partly) Layout view with zoom + footprint — X Figures gallery → Layout (GDS thumbnail) + footprint text in the Physical section ✓; the SVG itself and its zoom tools ✗ (same policy).
70. ✓ Physical verification & extraction summary — X `kv` (DRC/LVS/PEX coloured; + DRC effective/ignored and per-rule counts).
71. ✓ Pin coordinates — X table (raw 3-decimal µm values).
72. ✓ Provenance downloads — X downloads (card JSON, pre / post SPICE, load library manifest) + hub Files panel.
73. ✓ Integration & artifact provenance (subckt signature, models, 3 SHA-256) — X table.

## Data present in docs/ but not shown by the old site (added)
74. ✓ ULP scatter samples, frontier designs, envelopes, ≥90 dB counts — DS ULP envelope table + "ULP exploration samples" explorer (483 samples + curves + frontier designs with knobs).
75. ✓ Boundary 1-D ray samples, achieved-envelope percentiles, valid P5/P95 — DS per topology: envelope table + parameter-ray chart selector (A<sub>0</sub> and PM vs parameter at 1.8 V / 3.3 V, feasible/core markers, N-D band).
76. ✓ Per-card extras — X PVT / MC summary `kv`, "Additional nominal measurements", OP extras, generator knobs in Parameters.

## Review fix round (24 gaps from the independent 4-lens review)
Renderer issues (7, fixed in the hub; verified on a rebuild with the current web/assets): delivered rings visible, narrow-width span collapse,
Pareto excluding screened/delivered (adapter now sets `pareto_on`), symbol legend entries, hard-fail red (adapter now sets
`results.<stage>.status = "fail"` for the post-PEX nominal-PM failure 200f-current\_reuse\_1v8\_ulp\_lt0p1uw\_weak), select overflow, legend overlap.
Thumbnail-vs-footprint size: the Physical text now says the thumbnail line is the GDS bounding box.

Adapter gaps (17) — all fixed: checklist wrap (#1); post-PEX 'All sat.' → n/a (#2); ray traces carry `meta.vdd` (#6); JS-exact
toFixed/toPrecision rounding in opa_fmt (#8); per-load header tiles (#9); LUT caption from data (#10); portfolio stages from metadata +
PVT corner list from data (#11); table digits (#12); raw pin coordinates (#13); delivered points follow the stage (#14); overview matrix
and stats per V<sub>DD</sub> (#15); wrapped wide tables, short topology labels (#16, #22); matrix rows incl. load + PM, CL BW label,
12 card metrics, `table_metrics` (#17); one architecture colour map everywhere (#18); grey screened layer (#19); area only with the
full stage, unrounded (#21); duplicate schematic/layout blocks removed, KPI tiles split (#23).
Also found while re-checking: two table columns keyed `vdd` (boundary V<sub>DD</sub> range, PVT corner supply) were filtered by the global
V<sub>DD</sub> option and hid rows — renamed.
