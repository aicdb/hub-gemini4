# sdm — old-site inventory (sdm-gen-gemini4/docs) → hub port checklist

Old site: single page `index.html` + `assets/app.js` (custom canvas charts, no Plotly). Data:
`data/index.json` (cards, specs, cap + digital macros), `data/sweep.json`, per-card
`designs/<id>/data.json` (= card meta + components + candidates + cap/digital macro + layout + a copy of
`sim.json`). `data/{sim_summary,layout_summary,cap_macros,digital_macros}.json` are not fetched by the
page (their content reaches it through index.json / data.json); `digital_macros.json` flow header is used.

Hub locations: **Designs** = built-in matrix/cards/table; **D:<sec>** = design detail doc section;
pages **Summary**, **Macros**, **Arch**, **DSE**, **Method** (`#/sdm?page=summary|macros|arch|dse|method`).
Verified on the built preview (Phase C) for 8b/1v8/MOM/CIFB-Split (pre), 10b/1v8/MOM/CIFB-Split (partial, no fill),
12b/3v3/MIM/CIFF (partial), 16b/1v8/MIM/CIFB-Shared (full), 18b/1v8/MOM/CIFF (pre), 20b/3v3/MIM/CRFF (full).

## A. Global chrome
1. Title, badge, subtitle line. — ✓ component title/summary + Summary page intro (verbatim subtitle content).
2. Global Verification Stage switch (Pre-Layout / Post-Cap-PEX / Full-Chip PEX). — ✓ hub Simulation option (fix round 2):
   Pre-PEX → view 1; Partial post-PEX → view 3 (assembled "full-chip" deck = library sub-block PEX + cap PEX + routing C, compact
   controller instead of the routed sdm2bin → partial coverage per §6) with view 2 (cap-array PEX) as an alternative tab
   (one tabs block per staged item, unique ids `view_<alt>`, short labels "3. Full-Chip PEX (assembled)" /
   "2. Post-Cap-PEX (cap only)"; no horizontal page scroll at 420 px). No Full post-PEX stage (Methodology → Stage mapping explains why).
   `results` hold only SPICE (analog I_DD, I_DD·V_DD, integrator swings) and extraction (C_u, a1, a2 at partial); all model
   figures (ENOB/SNDR/power/FoM/PVT/MC) are labelled model blocks (stage alternatives per view).
3. Section nav tabs with counts. — ✓ Designs + 5 page tabs; counts in header stats (48 cap macros, 12 sdm2bin, 362,880 sweep).
4. Footer project/toolchain/repo/library commits. — ✓ Summary → "Provenance (old-site footer)" kv.
5. Deep link `#card=<id>`. — ✓ hub URL `#/sdm/<card_id>` (same ids).

## B. KPI banner (stage-dependent)
6–11. All six tiles, recomputed per old view with the old JS formulas (pre: 9.29b..22.41b / 90.89 fJ / 194.4 dB / 99.6–2715.2 µW;
   full-chip view: 9.29b..22.43b / 89.79 fJ / 194.6 dB / 99.6–2720.1 µW). — ✓ Summary → staged `stats` (alt `kpibanner`; partial = tabs
   view 3 / view 2), ENOB/FoM/power/variation tiles labelled "model". Static counts also as component header `stats`.

## C. sec-cards
12. Coverage matrix (rows VDD × arch, cols res × cap with OSR; cell ENOB/SNDR/power/FoM_S/PVT ≥/DRC-LVS; click → design). — ✓ old layout and
    cell contents (model figures) → Summary "Interactive 96-Card … Coverage Matrix — model figures" (staged per view, ENOB links open the card).
    Designs → Matrix (round 3): rows resolution × cap (12), cols architecture (4 per V_DD = 8, fits 1440 px); cells = SPICE analog power,
    Int-1/Int-2 swing, extracted a1 (+ presets I_DD/power, swings, extracted C_u/a1/a2). The Summary model matrix keeps the old
    8 × 12 orientation with compact cells (fits 1440 px).
13. Filter pills (resolution w/ OSR, VDD, cap, architecture) + count line. — ✓ Designs axis filter chips (labels carry OSR) + global VDD option.
14. Sort select (matrix order, ENOB, power, FoM_W, FoM_S, area). — ✓ model sorts: Summary master table (sortable by every model column);
    Designs → Cards/Table sort by SPICE/extraction metrics (generator order = old matrix order). Area: physical (full precision).
15. Card grid (metrics + component summary + PVT min/MC σ). — ✓ Designs → Cards (SPICE/extraction metrics); model ENOB/SNDR/power/FoM → Summary;
    component lines + PVT min + MC σ → Summary → "Deliverable card component summary" table (links to sibling designs) and design `params`.
16. Master verification table (20 columns, stage-dependent, row click). — ✓ Summary → "Master 48-Card Deliverable Verification Table"
    (all 20 columns grouped Model / Model full-chip / SPICE / Layout, + SPICE analog power column, exact f_s, staged per view, row links, CSV).

## D. sec-inspector (per design detail doc)
17. Header badges. — ✓ design tags (target/OSR, cap macro, OpenROAD macro, DRC = 0, LVS match, 9-corner PVT pass (min), MC yield, bit-exact) + axis chips.
18. Title + subtitle. — ✓ title + summary (arch name + input arch); the old "undefined · undefined" (missing stf/swing notes) dropped.
19. Switch-card select + "All 48 cards". — ✓ approximated: hub breadcrumbs, prev/next links, search; no dropdown (built-in UI).
20. KPI strip (10 tiles, stage). — ✓ D: "Model figures — <view>" `stats` (staged: pre / partial tabs view 3, view 2).
21. 3-stage progression table (13 rows × target/pre/post/full/Δ). — ✓ D:1 "3-Stage Physical Verification Progression" (ported formulas; Δ signs
    printed correctly instead of the old "+-"); extra "Loop parameters by verification stage" table (22 per-view parameters).
22. Noise budget (6 bars) + power breakdown (6 bars), stage-dependent. — ✓ D:1 staged section "In-Band Noise Budget & Power Breakdown (model)".
23. Component selection prose + cards (OPA1, OPA2, VCM, comparator, switches). — ✓ D:1 "Systematic Component Selection…" table, keys link to
    `#/opa/<load>-<id>`, `#/sa/<key>`, `#/switch/<key>` (all ids verified in sibling docs); old "—" fields filled from real data.
24. Op-amp candidate ranking. — ✓ D:1 table with all 8 + 8 + 6 (VCM) candidates, selected row marked, extra columns (t_s, v_n, V_os σ);
    the candidate "swing" (0.8·VDD placeholder) is not shown.
25. Comparator & switch candidate ranking. — ✓ D:1 table, all 4 comparators + 9 switches, switch ranks per role; Q_inj = 10 fC placeholder dropped.
26. Schematic block switcher (7 SVGs, VCM only if present), zoom, Open SVG. — ✓ D:2 gallery (tabs) + design Figures gallery (`files.schematic` +
    `images[]`); click opens the SVG full size (replaces zoom buttons).
27. gm/Id annotation cards. — ✓ D:2 "gm/I_D annotation summary" table (target, sim, PEX sim, regime, I_ref, topologies).
28. Local stage switch + prose. — ✓ global Simulation option; prose = D:3 section intro.
29–33. Charts 1–5 (PSD, transient + sdm2bin staircase, DR sweep, DNL/INL, phase portrait) + DC transfer. — ✓ D:3 staged
    "Multi-Testbench Simulation Suite" (pre section / partial tabs view 3, view 2), Plotly, synthesized/model captions; PSD floor and
    phase-portrait range follow the data; dout_valid markers limited to the plotted window (all 8 words in the dout table).
34. Chart 6 MC histogram + meta. — ✓ D:3 "Variation analysis (model, full-chip view — shown at every stage)", bars from `hist_edges`,
    mean/P5 lines, clipping caveat; MC summary kv.
35. 9-corner PVT table. — ✓ D:3 stage-less table + PVT summary (model, full-chip view). Not in `results` (no pvt/mc/robust there).
36. Gate-level sdm2bin co-sim summary + sample dout words (dec + hex). — ✓ D:3 "Gate-Level sdm2bin…" section: kv (macro deep-links to
    Macros `t.digm`), frame-verification table, staged dout-word table (cycle index, hex).
37. Layout switcher (full chip / cap macro / sdm2bin, pre-rendered SVGs). — ✓ D:4 gallery grid of hub GDS thumbnails: top cell, `CAP__<cap_key>`,
    `DIG__<dig_key>` (+ same in the Figures gallery); layout SVGs not referenced.
38. Download bar (GDS + 3 netlists). — ✓ D:4 "Deliverable artifacts" (repo links) + design `files`/`downloads` (also sim.json, data.json, sdm2bin netlist/GDS).
39. Magic PEX trim convergence (cell, units, caps, ratio error, iteration table). — ✓ D:4 kv + "Trim iterations" table (real fields; old table was all "—")
    + convergence chart + final finger/plate lengths + extracted branch table.
40. Floorplan zones & routing PEX. — ✓ dims, area, routing parasitics (int1/int2/out1/out2/x12), signoff, isolation, area-breakdown chart, ports.
    ✗ zone X/Y table: no zone coordinates exist in the data (empty on the old site too) — stated in a note.

## E. sec-macros
41. Cap-macro prose + 48-row table. — ✓ Macros: prose verbatim + count note, table with all columns (+ bank ×, equiv. LSB err, trim iters, area);
    "Trimmed W/L" shows real finger/plate length ranges; per-macro tabs (`t.capm=<cell>` deep link from each design) with GDS thumbnail
    (`CAP__` sub-cell of the 1.8 V card), kv, trim iterations, branch table; bar chart of post-trim error.
42. Digital-macro prose + 12-row table. — ✓ Macros: prose verbatim + count/sinc-order notes, flow kv (digital_macros.json header), table with all
    columns (+ synth area, physical cells, core, util, vias, DRT, arrival), scaling chart, per-macro tabs with standalone GDS thumbnail, block
    schematic, cells-by-type chart, frame verification, ports, downloads (tabs `t.digm=<macro>`, follow the VDD filter).

## F. sec-arch
43. Arch prose + 4 cards + per-arch stage means. — ✓ Arch: prose verbatim, 4 markdown cards (desc, input arch, all 7 coefficients, flags,
    reference — the old "undefined" fields replaced by real ones), "Per-architecture means (24 cards each)" table (`stage_column`; old said 12-card).
44. Tradeoff chart (power vs ENOB, colour = arch, MIM bigger). — ✓ Arch explorer over 96 × 3 views (stage column + "Old verification view"
    chips, old arch colours, symbol = cap with legend, clickable, presets incl. "Model vs SPICE power"). Per-arch / per-cap means staged per view.
45. MOM vs MIM cards. — ✓ Arch: two markdown cards (C_u,nom + stored description); per-cap means by stage; cap-macro statistics.
    ✗ density / layers / notes / bottom-plate % / Pelgrom A_C: not in `cap_specs` (old site printed "undefined"/NaN) — noted in caption.

## G. sec-sweep (Design space)
46. Title + prose. — ✓ DSE page intro (verbatim) + stats (evaluated, feasible, Pareto, cloud sample, lib combos, run time) + honesty note.
47. Facet select (All + 16 groups, Pareto counts). — ✓ DSE tabs (select, id `grp`, keyed by group, 1v8/3v3 tabs follow the VDD filter) with the
    17 old option labels.
48. Chart ENOB vs power (cloud grey + Pareto by arch, meta counts). — ✓ per group (`hub/data/dse/<group>_pareto.json`; SVG scatter, traces
    split by `meta.vdd`).
49. Chart FoM_S vs FoM_W. — ✓ per group (`hub/data/dse/<group>_fom.json`).
50. Winners table (96 rows, row click). — ✓ DSE "Winning cards" table (exact f_s, + f_B, SFDR, area model, OPA/comp/switch links); C_u dropped (always "—").
51. 12 stored facets + dimensions + summaries. — ✓ DSE "The 12 stored facets of sweep.json" tabs (id `facet`, short labels; VDD-split traces,
    side-by-side bars, corrected "configs with a feasible best combo" wording, deliverable overlay clickable) + "Sweep dimensions" table +
    main explorer over 1,041 points (809 cloud + 83 global Pareto + 53 further per-group Pareto + 96 delivered with Feasible = n/a; old arch
    colours; Pareto off by default and restricted to feasible points; "old chart 1" preset shows the stored Pareto set; facet-like presets
    labelled "(cloud sample)"). Round 3: column "Pareto of its group" — one *Group* chip + *yes* reproduces each old facet-selector
    Pareto set exactly (counts 13/13/13/15/12/12/13/12 verified).

## H. sec-method
52. 4 methodology cards verbatim. — ✓ Method page (markdown, verbatim bullets) + captions on count/sinc inconsistencies, stage-mapping table,
    model/caveat notes and a data-provenance list (SPICE vs model vs synthesized vs digital flow vs layout).

## I. Data not drawn on the old site
53. DC transfer, MC extras/runs, PVT summary, layout areas/route parasitics/ports, branch tables, digital cells/ports/frame verification, full
    component metrics. — ✓ D:3 DC transfer chart + MC summary kv, D:3 PVT summary, D:4 floorplan kv/chart/ports, D:4 branch table,
    D:spec (collapsed) arch/res/cap spec kv + MC run samples, Macros per-macro tabs. Full component metric sets: ✓ key figures in D:1 tables
    (complete records stay in the repo-linked data.json).

## J. Hierarchy (fix round 2)
54. `builds_on` opa / sa / switch and per-design `uses` (stage-1/stage-2 integrator OTA, VCM buffer, quantizer comparator, input + SC
    switches; hub ids `<load>-<card_id>`, sa keys, switch keys). — ✓ all 96 × 5–6 entries resolve (build: 612 design-level links, 0
    unresolved); "Built from" on sdm pages, "Used in" on op-amp/sense-amp/switch pages. No sar-gen design is instantiated (sar-gen only
    supplies comparator characterization data), so no `sar` entry.

Coverage: 54 items — 52 ✓, 2 partial ✗ (zone coordinates, cap-spec density/Pelgrom fields: absent from the data, empty/undefined on the old site).
Review fix round: 25 non-renderer gaps fixed (see report); renderer gaps 21/22/27 fixed in the hub. Round 3: gaps 4, 7, 9, 22, the view-tab regression and the shared `t.view` id fixed; gm/I_D table and card component summary fit at 1440 px (wide numeric tables — master, candidates, macro tables — still scroll inside their own frame, as on the old site).
