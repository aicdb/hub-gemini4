# aux-gen-gemini4 — old-site inventory and where each item lives on the hub

Old site: `aux-gen-gemini4/docs` (index.html + assets/app.js + data/{index,dse,library,gmid}.json;
`data/bundle.js` = index + dse + gmid inlined for file:// viewing; cards/<id>/{detail.json, schematic*.svg,
layout.svg, gds.gz, netlists}). Adapter: `adapters/aux.py` (+ `aux_detail.py`, `aux_pages.py`, `aux_fmt.py`).

Layout on the hub: a **collection** (BUILDERS §4.3) — `component.json` is a manifest (group "Aux blocks") listing ten
components `aux-<fam>` (`aux-ro`, `aux-tcap`, `aux-tres`, `aux-cm_idac`, `aux-dco_vco`, `aux-cml_ro`, `aux-clk_div`,
`aux-vref_2t`, `aux-cml_dco_vco`, `aux-bm_iref`), each its own top-level tab grouped under **Aux blocks**.
Per tab: **D** = Designs view (`#/aux-<fam>`), **FO** = page Overview (`?page=overview`), **EX** = page Design space
(`?page=explore`, tabs `t.preset`, `t.supply`), **ME** = shared page Methodology (`?page=method`), **ALL** = shared page
"All aux blocks" (`?page=all`), **DD** = design detail (`#/aux-<fam>/<id>`; header/gallery/perf table/params/files from the
design record, sections from `hub/designs/<id>.json`). Stage = hub global *Simulation stage* (Pre-PEX / Full post-PEX).

Legend: ✓ ported · ≈ ported with a deliberate difference (reason given) · ✗ not ported (reason given).

## A. Global chrome
1. ✓ Brand title + subtitle — nav group "Aux blocks" + hub overview group header; title/subtitle verbatim in ALL intro.
2. ✓ Results toggle Schematic / Post-layout (PEX) → global stage. pre = `metrics_pre`, full = `metrics_post`
   (whole-cell Magic C-only extraction, noted per design). Stage alternatives in DD (banner, spec table, PVT table),
   FO / ALL master tables, EX static charts (trace-level stage alternatives: ◆+★ at pre, ★ only at full); EX explorer `stage` column
   reproduces both retired modes (pre: DSE + pre + post points; full: DSE + post).
3. ✓ Post-layout mode banner text — FO and ALL note blocks shown only at Full post-PEX.
4. ✓ Nav Designs / Design-space explorer / Methodology → per tab D, EX ("Design space"), ME (+ FO, ALL).
5. ✓ library.json download — FO hosts this family's slice (same structure); ALL links the full file in the repo.
   Source ↗ → hub repo link.
   ≈ Theme toggle: the hub's own.
6. ✓ Family switch (10 families, icons, counts) → ten top-level tabs under "Aux blocks" (tab name + count; title = icon + name).
   "All (408)" → ALL master table + coverage summary (links into every family tab).
7. ✓ Supply switch → global V<sub>DD</sub> filter (matrix outer column group, tables with `vdd` column, EX explorer, EX static charts via
   per-supply traces with `meta.vdd`; explorer stats show per-supply counts).
8. ✓ Footer downloads library.json / index.json / dse.json / gmid.json — FO: hosted per-family slices + gmid.json; ALL: full
   files as repo links + gmid.json (avoids ten hosted copies of 6 MB).
   ✗ bundle.js not republished (pure duplicate of index+dse+gmid, said so in the caption). Old pages URL listed as metadata.

## B. Designs view
9. ✓ Hero eyebrow + h1 + full lede — ALL intro, verbatim (HTML → markdown); family intro in FO.
10. ✓ Hero stats (6 tiles) — ALL stats (all families) and FO stats (this family); filter-dependent recomputation → ALL "Coverage by family and supply" / FO "Coverage by supply" tables
    (follows global V<sub>DD</sub>; cards, topologies, DRC+LVS+PEX clean, post-PEX characterized, PVT all-pass pre/post).
11. ✓ "Interactive coverage matrices…" heading + text — ALL section (verbatim + hub pointer).
12. ✓ Per-family matrix title / primary metric — tab title (icon + family name) + summary ("Primary metric on the retired site: …").
13. ✓ Rows = topology (short name + device flavor) × cols supply × target band — D matrix rows `[topology, flavor]`, cols `target`, V<sub>DD</sub> outer group.
14. ≈ Cell: headline + 2 secondary values + PVT + signoff — D matrix with 3 metrics (headline + both old secondary values),
    PVT n/n, DRC/LVS ✓, robust colouring; presets incl. "Retired-site headline". Δ badges → DD performance table deltas.
15. ≈ Search — hub global search (id, title, tags = family, flavor, circuit style, status; axes). Design notes are not searchable (shown on DD).
16. ≈ Verification status filter — hub DRC+LVS / PVT-robust; "Pass" (all 408 cards are status pass) → tag "Spec ✓ (generator status pass)"; "Post-PEX verified" = Full post-PEX stage without fallback.
17. ✓ Sort options — D Cards/Table sort by any card metric (primary ↑↓, area ↑↓); |Post-PEX shift| → FO / ALL table column.
18. ✓ Topology pills — D axis filter chips. (+ device-flavor chips where a family has >1 flavor.)
19. ✓ Target band pills — D axis filter chips.
20. ✓ Design cards — D Cards view (GDS thumbnail, title, id, V<sub>DD</sub>, up to 12 card metrics per family mirroring the old
    6 tiles incl. combined ones, badges stage/robust/PVT/DRC/LVS/PEX). Device counts → DD Parameters.
21. ✓ Master comparison table — the retired per-family column sets (10 variants, incl. the estimate columns marked "(est.)",
    clip-limit cells amber) → FO "Sortable master comparison table" (stage alternatives); D Table view lists every published metric;
    "All families" variant → ALL master table (Card, Family, Topology, VDD, Target, Headline, Primary value, Secondary, MC σ/μ, Area, PVT,
    Signoff, |shift|; stage alternatives; rows link into the family tabs).
22. ✓ CSV export — D Table "Download CSV" and every hub table's CSV button.

## C. Design detail header
23. ✓ Breadcrumb + h1 — DD crumbs (Hub / family tab / id), design-jump dropdown, title "topo name · VDD · target".
24. ✓ Chips supply / target / flavor / style / viewing mode — DD axis chips + tags + eyebrow "showing <stage>".
25. ✓ Badges Spec/DRC/LVS/PEX/PVT — DD Physical badges, perf table PVT row, tag "Spec ✓", banner signoff tile.
26. ≈ Tabs Overview/Schematic/Simulation/Layout — DD sections in the same order (all visible; no tab clicking needed).

## D. Detail – Overview
27. ✓ Key performance banner — DD section "Key performance & verification banner" (stats tiles; stage alt pre/full;
    value/other-stage/Δ text as on the old site; estimate rows labelled). ≈ signoff tile shows the PVT/MC of the shown stage (old always showed pre and defaulted missing PVT to 15).
28. ✓ Spec & Pre/Post table (10 family variants, ported string formatting) — DD "Specification & verification"
    (stage alt for the worst-PVT column) + **pass/fail colouring** where the Target states a numeric criterion.
29. ✓ DRC/LVS/PEX rows — same table, coloured.
30. ✓ Design knobs panel (topology summary, notes banner, card id, ports, device count, all knobs, SHA-256) — DD
    "Design knobs, sizing summary…" (full SHA; stringified note lists rendered as bullets) + DD Parameters panel.
31. ✓ Artifact downloads — DD downloads block + Files panel (netlist, LVS ref, PEX, GDS, detail.json → repo links;
    schematic.svg / schematic_design.svg hosted). ✗ layout.svg (hub rule: no layout images; GDS thumbnail instead).

## E. Detail – Schematic
32. ≈ Annotated schematic, both views — DD gallery "Target → simulated gm/ID (pre-PEX)" / "Design sizing view" +
    figure gallery. Not stage-switched (the design view is not post-PEX data; caption explains the old mapping). Zoom = open full size.
33. ✗ Schematic ↔ table cross-highlighting — no renderer support (feature request).
34. ✓ Operating-point / gm/ID table (16 columns + VGS, Vth from the data; region colouring WI/MI/SI/other) — DD, stage `pre`.
35. ✓ Passive devices table (conditional, 219 cards) — DD "Passive devices".

## F. Detail – Simulation (Plotly, pre + post traces, colours as on the old site)
36. ✓ ro charts 1–3. 37. ✓ tcap 1–3. 38. ✓ tres 1–3. 39. ✓ cm_idac mirror/IDAC variants 1–3.
40. ✓ dco_vco / cml_dco_vco 1–3 (V_diff for CML). 41. ✓ cml_ro 1–3. 42. ✓ clk_div 1–3. 43. ✓ vref_2t 1–3.
44. ✓ bm_iref 1–3 (TT/SS/FF trim curves + target line) — all in DD "Simulation results", 2-column grid, with dual axes/log axes.
    Phase-noise charts captioned as analytic model output.
45. ✓ Chart 4 PVT bars pre vs post — DD.
46. ✓ 15-corner PVT table (stage alt for PASS/WARN) — DD "PVT & Monte Carlo verification".
47. ✓ MC summary (μ, σ, CV, min, max; pre & post) — DD; + MC histogram (samples were in detail.json, not plotted before).
    + extra collapsed section "Additional characterization data" (tcap Q(f), cm_idac step response & IDAC compliance,
    DCO/VCO power & swing vs control and PN, clk_div power vs f_in & V_outb, bm_iref line regulation & PSRR).

## G. Detail – Layout
48. ✓ Physical verification & PEX summary tiles — DD kv grid (+ expected vs extracted colouring, extracted ports, n_blocks).
49. ≈ Interactive GDSII vector viewer (layout.svg) — hub-rendered GDS thumbnail (DD gallery + "GDSII layout" section) + raw GDS / PEX / LVS / netlist links.
50. ✓ Pin coordinates — DD table (≈ fixes the old bug that showed empty pin names: data key is `name`, old code read `pin`).
51. ✓ DRC / LVS / PEX rule breakdown — DD table (dispositions now conditional on the actual results).

## H. Design-space explorer
52. ✓ Hero + stats — EX intro (verbatim + hub note) and stats tiles (candidates, deliverables, topologies, total).
53. ✓ Family switch → the family tabs (EX of each tab; ALL links "design space" per family); supply switch → global V<sub>DD</sub>.
54. ✓ Trade-off presets + descriptions — explorer presets with `desc` (shown when selected; explicit axes/colour/filters so presets
    do not stack) + facet by topology / supply, delivered-only, colour by supply / generator front; static section tabs per preset.
55. ✓ X/Y axis options with log flags; colour by topology/supply/area — explorer dims = every non-constant numeric field
    and knob of dse.json (base SI units), categorical topology/supply/target/kind/string knobs/pareto flag; old topology palette.
56. ✓ Multi-topology Pareto overlay with generator fronts, ◆ pre / ★ post deliverables, click → card — EX static charts, one per preset
    (`t.preset=<id>`), following the global V<sub>DD</sub> (per-supply traces + per-supply generator fronts; the both-supply fronts are
    legend-only at "All") and stage (pre: ◆+★, full: ★ only). Explorer: delivered cards ringed (`highlight`); generator front membership per
    preset as "On generator front" colour dims (keeps the area-preset fronts that lost their placeholder-area cloud).
57. ✓ Facet grid with locked shared axes + legend — EX static facet figure (same ranges, 3 columns) + explorer facet presets.
58. ✓ Deliverable table — EX table with every axis option (pre & post, grouped) + area; rows link to cards.

## I. Methodology
59. ✓ Hero — ME intro verbatim (one hosted page shared by all ten tabs).
60. ✓ Panel 1 (4 numbered items) — ME markdown, verbatim.
61. ✓ Panel 2 (3 items + nested bullets) — ME markdown, verbatim.
62. ✓ gm/ID charts: device × VDS-domain switches × 3 charts (reversed x, log y) — ME nested tabs (domain tabs carry `vdd`).
63. ✓ Topology catalogue table — ME table (70 rows, links to the family tabs), old caption kept with a correction note;
    each FO also lists its own topologies.

## Data caveats applied (honesty)
- Not published as results (shown only in labelled DD tables/charts and EX dims): phase noise, jitter, oscillator/divider FoM,
  FoM_T (Hajimiri–Lee / noise-floor models from simulated f, P, swing); tres "equivalent THD" (= 20·log10(lin_err/220)).
- Omitted placeholders: tcap power/leakage, dco_vco INL/DNL (0.12/0.08), dco_vco "V_pp,diff" (= single-ended swing),
  clk_div f_min (sweep floor 0.25 GHz; lock range labelled sweep-bounded), DSE area = 450 µm² (8 families) and other DSE constants.
- Clip-limit values nulled in results with a per-design note and flagged in DD tables: cm_idac R_out = 5000 MΩ (1 card),
  cm_idac BW = 0 (1), bm_iref TC at 8/450 ppm/°C (8 cards).
- 34 cards (vref_2t, bm_iref) have identical pre/post metrics — noted in their full-stage note.
- DSE area for vref_2t / bm_iref is a generator estimate (labelled); deliverables use layout area.

## Review fix round (independent 4-lens review, 38 gaps) — mapped to the per-family tabs
Fixed in the adapter (all renderer_issue=false gaps):
- clk_div MC is synthetic (site.py draws N(μ, 1.8 %)) → `mc_cv` null + note, MC table/histogram replaced by a note, stat "MC runs: n/a".
- `x or default` placeholders → omitted with per-design note and amber spec cells: clk_div ratio_err 0.15 % (38 card-stages),
  cm_idac INL 0.05 / DNL 0.03 (14/20), tres INL/DNL (3).
- Clip/floor values omitted + flagged: bm_iref start-up 1450 ns (46), bm_iref line-sens 0.03/3.5 %/V (2), vref_2t TC floor 1.0 (6),
  vref_2t V_DD,min floor 0.65 V (6), ro t_start = 0 (18); clk_div f_max,in = 3.5 GHz kept with "sweep top" note + label/desc.
- cml_ro K_VCO restored (48 cards; metric desc explains the bias-node ΔV for I_bias-tuned topologies).
- tcap/tres/cm_idac: no PVT pass criterion in the generator → no `pvt`/`robust` in results, PVT status "n/a" in tables.
- Derived values removed from results: tcap C LSB, dco/cml_dco tuning ratio; clk_div energy labelled "per input cycle"; cm_idac BW
  digits/desc (10 kHz source rounding); MC run counts < 30 noted, "MC runs / card: up to 30", MC table titles use real counts.
- "Spec ✓" tag/badge/param dropped (raw status was "nominal"/missing for 8 families); device flavor no longer duplicated as a tag;
  generator notes appended to the design summary.
- clk_div sensitivity chart labelled as a model curve scaled to the measured point.
- Explorer: failed DSE runs excluded; fabricated DSE fields (cml_ro K_VCO, f supply sensitivity, frequency error vs placeholder target)
  and DSE-only constants kept for delivered cards only (restores cml_ro tuning range axis); alias columns dropped; curated labels;
  presets explicit + descriptions; highlight rings; FoM-direction note only where FoM dims exist; family order as on the retired page.
- EX static charts follow the global V<sub>DD</sub> (meta.vdd) — replaces the supply tabs; facet subtitles wrap instead of truncating.
- FO "Pre→post-PEX shifts" table (generator deltas, retired Δ badges); OP table always shown (labelled pre-PEX operating point);
  methodology catalogue and topology tables wrap.
Not adopted: star symbol for post-PEX in the interactive explorer (renderer has no per-value symbol mapping; ✕ is used, ★ in static charts).
Hierarchy (BUILDERS §4.5): aux blocks instantiate no cells from other hub components (transistor-level generators) → leaves, no `builds_on`/`uses`.

## Round 3 (final verification) — remaining items
- clk_div: chart-4 title/caption no longer quote the synthetic MC; `mc_cv` removed from the clk_div metrics/card metrics.
- "All aux blocks" master table: headline / secondary / primary-value cells flagged amber where they sit on a placeholder, clip limit,
  floor or sweep bound (36 rows), same rules as the family pages.
- Explorer: delivered-card values that are placeholders / clip limits / "not measured" (e.g. ro t_start = 0) are not plotted;
  duplicate quantities removed (t_rise/tr, C target, C LSB, R target, target current, accuracy-vs-current error); curated labels
  (knobs as W_n, C_load …); Point kind uses `symbols` (◆ pre-PEX, ★ post-PEX, as the retired site) and `theme:ink` for pre-PEX (dark-mode safe).
- MC run counts: chart-4 titles/captions and the MC histogram caption use the real run counts.
- Phone width: shorter matrix preset label ("Headline (retired site)") and schematic gallery tab labels.
- Pre→post shift tables: family metric labels, alias keys dropped.
Renderer-side (not adapter): explorer power axes `minexponent` (prefix/decimal mix), design-page "Partial post-PEX" column,
thumbnail vs physical dims, search over design summaries (generator notes are in `summary`, not added as long tag chips).
