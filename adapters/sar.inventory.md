# sar — inventory of the retired site (sar-gen-gemini4/docs) and where each item lives on the hub

Old site: `docs/index.html` + `assets/app.js` (custom SVG charts, card modal with 6 panes) + `data/{index,sweep,compchar}.json`
+ `designs/<card>/{data.json, *.svg, *.gds.gz, netlist.spice}`. Enumerated from the HTML, a full read of `app.js`,
headless screenshots of all 4 views and all 6 modal panes of 4 cards (ULP 1 kS/s 8-bit MOM, monotonic 10-bit MOM,
loop-unrolled 10-bit MIM, majority-vote 12-bit MIM), plus spot checks of the failed-FFT and EOC-issue cards.

Hub locations: **D** = built-in Designs view of tab *SAR ADCs* (matrix / cards / table), **P:x** = page `x`
(`overview`, `explore`, `resilience`, `libraries`), **Dd:n** = design detail page, tab *n* of the detail tabs block,
**Dd:top** = detail header area (figures gallery, performance-by-stage table, physical, parameters, files, card summary,
caveat notes).

Legend: ✓ ported · ≈ ported with a deliberate change (reason given) · ✗ not ported (reason given)

## A. Header / global

| # | old item | status | hub location / note |
|---|---|---|---|
| 1 | Title "GF180MCU-D Low-Power Redundant SAR ADC Catalog" + PDK badge (180 nm · 5LM · Option-B MIM) | ✓ | component `title`; PDK text in P:overview intro |
| 2 | Hero subtitle paragraph (gLayout CC CDAC, sibling selection, EOC sleep gating, redundancy, 108 cards, rate tiers) | ✓ | P:overview intro |
| 3 | KPI "Deliverable design cards 108/108" + sub (36 ULP + 48 HS + 12 UHS + 12 LU · 1:1 square) | ✓ | P:overview stats (computed from index.json) |
| 4 | KPI "Post-PEX variance & CDACs 24/24 (0 fail)" + sub | ✓ | P:overview stats; component header stat |
| 5 | KPI "Design-space combinations 13,063,680" + sub (6 regimes × 72 comps × 125 switches × 288 op-amps) | ✓ | P:overview stats (sub quoted as the old wording; sweep.json library_counts 96/125/336 shown next to it); header stat |
| 6 | KPI "Lowest 1 kS/s power & leakage" (static 26.1 nW = 21.4 + 4.66 nW; live JS value 33.2 nW from placeholder) | ≈ | P:overview: published live value + static text, and hub value recomputed from SPICE energy (26.1 nW) |
| 7 | KPI "Best Walden FoM" (static 8.7, live 12.2 fJ/step) | ≈ | P:overview: published value + hub value (ULP recomputed) |
| 8 | KPI "Peak speed 400.0 MS/s (2 GS/s TI ready)" + sub | ✓ | P:overview stats; header stat |
| 9 | Nav tabs: cards / explorer / resilience / libraries | ✓ | Designs + pages `explore`, `resilience`, `libraries` (+ `overview`) |

## B. Deliverable design cards view

| # | old item | status | hub location / note |
|---|---|---|---|
| 10 | Filter: sample-rate tier (6 tiers + counts) | ✓ | D axis filter *Sample-rate tier* (with counts) |
| 11 | Filter: resolution 8/10/12 | ✓ | D axis filter *Resolution* |
| 12 | Filter: supply 1.8 / 3.3 V | ✓ | global V<sub>DD</sub> filter (hub rule: supply is not an axis) |
| 13 | Filter: CDAC array MOM / MIM | ✓ | D axis filter *CDAC capacitor* |
| 14 | Filter: architecture (ULP group, UHS, LU, mono, smono, VCM, mvote) | ✓ | D axis filters *Operating mode* (sleep-gated ULP / continuous HS / UHS / loop-unrolled — the old grouped "EOC sleep-gated ULP" chip) + *Architecture* |
| 15 | Sort: default / power / leakage / FoM / ENOB / fs ↑ / fs ↓ | ≈ | D cards/table sort (best/worst of every card metric incl. power, p_leak, fom_w, enob, fs); leakage sort covers ULP only because non-ULP "leakage" is a model value, not a result |
| 16 | Card: id, arch title, DRC/LVS ✓ badge | ✓ | D cards (title, id, DRC/LVS badges); arch title in tags & summary |
| 17 | Card badges: n-bit (k_sw steps), VDD, cap · 1:1 CC, tier/TI/UHS/EOC badge, 3× LSB vote | ✓ | design `tags` + axes chips (Dd:top) |
| 18 | Card weights box with redundant duplicates starred | ✓ | params "CDAC weights (* = redundant)"; Dd:1 architecture kv |
| 19 | Card metrics: post-PEX ENOB, SNDR/SFDR, Walden FoM, sample rate, total power, standby P_leak | ≈ | D `card_metrics` (enob, sndr, fom_w, fs, power, p_leak, sfdr, …) — partial-stage values; ULP recomputed; failed-FFT and loop-unrolled cards show no ENOB/SNDR/FoM (loop-unrolled: synthesized codes → *ENOB (raw codes)*); ENOB shown to 4 digits |
| 20 | Card previews: schematic thumbnail + 1:1 layout thumbnail with dims | ≈ | card thumbnail = hub-rendered GDS thumbnail (layout.svg not allowed); schematic in the detail gallery |
| 21 | Card footer: comparator key, dims, "1:1 Layout →", "Inspect →" | ✓ | params (comparator), physical dims, card link → detail page (gallery tabs Layout / Schematic) |

## C. Systematic design-space explorer view

| # | old item | status | hub location / note |
|---|---|---|---|
| 22 | Chart: Walden FoM (log) vs ENOB — grey cloud (first 900 pts) + 108 cards coloured 8/10/12-bit, tooltips | ✓ | P:explore chart "Walden FoM vs ENOB — as on the old site" (all 2,600 cloud pts, cards clickable) + explorer preset |
| 23 | Chart: total power vs fs log-log — cloud (first 1,200) + cards coloured LU2G / UHS / 1.8 V / 3.3 V | ✓ | P:explore chart "Total power vs sample rate" + explorer preset |
| 24 | Table: multi-rate sample-regime exploration (8 columns) | ✓ | P:explore table (combined cells split into 14 numeric columns) |
| 25 | Table: architecture trade-off summary (7 columns) | ≈ | P:explore table, retitled to its real scope (3.125–20 MS/s regime only, 334,410 feasible) |
| 26 | Chart header text "Gray = 13,063,680 swept designs" | ≈ | corrected in P:explore intro: the cloud is a 2,600-point sample (all 8-bit); the 13.1 M points are not in docs |
| 27 | sweep.json data not shown: pareto_by_group (140 pts / 36 groups), sweep meta (resolutions, supplies, archs, regimes, library counts) | ✓ | P:explore explorer (all point sets, every dimension) + "Pareto-front points per group" table + intro |

## D. Post-PEX CDAC variance & redundancy resilience view

| # | old item | status | hub location / note |
|---|---|---|---|
| 28 | Table: 24 extracted CDAC macros (macro, spec, C_u/C_B, nominal ENOB, worst redundant, worst binary, max errors, 5-corner status) + "24/24 · 0 failures" badge | ✓ | P:resilience first table (+ cards using it, source record link); intro states 24/24 |
| 29 | Chart: ENOB vs injected σ, redundant vs binary, 8/10/12-bit (hard-coded in app.js) | ✓ | P:resilience "Old-site figure" (labelled hard-coded) + data-driven per-macro tabs (8/10/12-bit) |
| 30 | Chart: 12-bit 5-corner residue trajectory (hard-coded) | ✓ | P:resilience "Old-site figure" + per-macro residue charts (dropdown, 24 macros) |
| 31 | Static table: redundant weight sequences (3 rows × 7 cols) | ✓ | P:resilience table (caption adds the per-card speed-ups) |
| 32 | Chart: incomplete DAC settling resilience 8/10/12-bit (hard-coded) | ✓ | P:resilience old figure + per-card behavioural records |
| 33 | Chart: dynamic comparator offset/kickback resilience (hard-coded) | ✓ | P:resilience old figure + per-card behavioural records |

## E. Reused component libraries & architecture matrix view

| # | old item | status | hub location / note |
|---|---|---|---|
| 34 | Static table: seven input & switching architectures (5 columns) | ✓ | P:libraries first table |
| 35 | Table: complete 108-card matrix (card, spec, CDAC, comparator, switch, VCM op-amp, ENOB, FoM; row click → modal) | ✓ | P:libraries matrix (row click → design; component cells link to the sibling hub designs; + input op-amp; published and hub ENOB/FoM side by side) |
| 36 | (not on the old site) component reuse counts | ✓ | P:libraries "Sibling component reuse" |

## F. Card modal (one detail document per design, 108)

| # | old item | status | hub location / note |
|---|---|---|---|
| 37 | Modal title "CID — arch title" + subtitle (VDD · raw resolution & k_sw · CDAC · input S/H) | ✓ | Dd:top title/summary + "Card summary" kv |
| 38 | Modal tabs 1–6 | ✓ | detail `tabs` block with the same 6 tabs (+ tab 7) |
| 39 | P1 annotated top-level schematic + "Open full SVG" + "Download SPICE netlist" | ✓ | Dd:top gallery "Schematic" (click = full size) + Files (netlist, repo link) |
| 40 | P1 full-chip layout (layout.svg) with dims/aspect + download .gds.gz | ≈ | Dd:top gallery "Layout" = hub GDS thumbnail + GDS repo link; dims in Dd:6 (layout.svg cannot be hosted) |
| 41 | P1 CDAC macro layout (cdac_layout.svg) + "DRC = 0 · LVS match" | ≈ | Dd:top gallery "CDAC macro layout" = GDS thumbnail of cell `cdac_<key>`; badge text in Dd:6 (noted: flags set unconditionally) |
| 42 | P1 table: sub-block gm/Id target vs "post-PEX simulated" gm/Id (6 cols) | ✓ | Dd:1 table; caption: the "simulated" values are target × fixed factors |
| 43 | P1 reused comparator schematic | ✓ | Dd:1 sub-block schematic grid + Dd:top gallery |
| 44 | P1 reused S/H switch schematic | ✓ | Dd:1 grid + gallery |
| 45 | opa_schematic.svg (in docs, not shown) | ✓ | Dd:1 grid + gallery "VCM op-amp schematic" |
| 46 | P2 FFT spectrum (stems, signal bin highlighted, ENOB/SNDR/SFDR/THD/fs header, f_in) | ✓ | Dd:2 chart (Plotly stems; header in caption); failed-FFT cards: note; loop-unrolled cards: raw-SPICE-code spectrum + the published (synthesized) spectrum, labelled |
| 47 | P2 table pre-layout vs post-CDAC-PEX vs full-chip PEX (10 rows) | ✓ | Dd:2 table; pre/full columns labelled model estimates; ULP cards get a 4th column recomputed from SPICE energy |
| 48 | P2 table sub-block energy & leakage breakdown (5 rails × 5 cols) | ≈ | Dd:2 table; ULP shows the SPICE per-rail values (old site showed zeros) + total; HS caption says the split is fixed fractions, UHS/LU caption says leakage columns are constants |
| 49 | P2 chart CDAC top-plate convergence (TOP_P, TOP_N, VCM_INT) | ✓ | Dd:2 chart |
| 50 | P2 chart async SAR clocking (PHI_S, COMP_CLK, EOC) | ✓ | Dd:2 chart |
| 51 | P2 table 3-cycle conversion verification (7 cols) | ✓ | Dd:2 table; loop-unrolled cards: labelled post-fit + raw TT SPICE codes/errors |
| 52 | (not shown) vdiff_top / code_reconstructed traces, ULP step decisions | ✓ | Dd:2 extra chart / table |
| 53 | P3 chart DNL vs code (max in legend) | ✓ | Dd:3 chart |
| 54 | P3 chart INL vs code | ✓ | Dd:3 chart |
| 55 | P3 table thermal noise & static linearity budget (7 rows) | ✓ | Dd:3 kv (+ ceiling, step error, attenuation) |
| 56 | P3 table Magic post-PEX capacitor group weights (6 cols) | ≈ | Dd:3 table, weights matched to groups by `step_idx` (old site paired by row index — wrong on 60 split arrays); step weight + group share + C to top / sub-DAC |
| 57 | (not shown) CDAC extraction summary, behavioural noise model | ✓ | Dd:3 kv blocks |
| 58 | P4 chart post-PEX injected variance sweep + "5/5 corners pass" badge | ✓ | Dd:4 chart 1 (+ uncalibrated curve, failure markers); pass text in title — uses the card's **own** CDAC macro (48 records in docs point at the `*_uhs` macro; note on those pages) |
| 59 | P4 chart bit-cycling residue under variance (corners 0–3) | ✓ | Dd:4 chart 2 (all 5 corners) |
| 60 | P4 table 5-corner verification (7 cols) + worst redundant / binary header | ✓ | Dd:4 table (17 cols incl. description, σ, bridge, atten., CM bounce, uncal. ENOB, missing codes); worst values in caption |
| 61 | (not shown) per-corner V_diff transients | ✓ | Dd:4 chart |
| 62 | P4 chart settling resilience | ✓ | Dd:4 chart 3 (labelled behavioural model) |
| 63 | P4 chart dynamic offset / kickback | ✓ | Dd:4 chart 4 |
| 64 | P4 chart bridge capacitor variation ±15 % | ✓ | Dd:4 chart 5 |
| 65 | P4 table per-step correction window (4 cols) | ✓ | Dd:4 table |
| 66 | P5 table 5-corner PVT (7 cols) | ✓ | Dd:5 table + *Source* column (TT SPICE / anchor / scaled / multipliers); PASS flagged as hard-coded |
| 67 | P5 chart active input-driver co-sim (VIP, TOP_P, TOP_N) | ✓ | Dd:5 chart (+ VIN); caption: shared anchor simulation |
| 68 | (not shown) driver co-sim conversion cycles | ✓ | Dd:5 table |
| 69 | P5 histogram MC ENOB (100 runs, mean) | ✓ | Dd:5 Plotly histogram (14 bins) + stats caption |
| 70 | P5 histogram MC INL_max | ✓ | Dd:5 histogram |
| 71 | P6 full-chip layout with dims, "1.00:1 square / DRC 0 / LVS match" badges, GDS download | ✓ | Dd:6 kv + `layout` block (thumbnail + repo link) + downloads |
| 72 | P6 CDAC macro layout | ✓ | Dd:6 `layout` block, cell `cdac_<key>` |
| 73 | P6 table floorplan sub-block placement (name/colour, origin, W×H, area) | ✓ | Dd:6 table (colour as tooltip) + floorplan sketch chart drawn from it |
| 74 | (not shown) sibling candidates & m_pex metrics | ✓ | Dd:1 "Reused sub-blocks" (links to sa/switch/opa hub designs) + Dd:7 candidate tables with the used component marked (ranking overridden on ULP/UHS/LU cards); design `uses` → hub "Built from" / "Used in" |
| 75 | Downloads per card: GDS, netlist, (data.json) | ✓ | Dd:top Files (repo links: GDS, data.json, netlist) + Dd:6 downloads |

## G. Other docs content

| # | item | status | hub location / note |
|---|---|---|---|
| 76 | data/compchar.json (72 comparator burst/CM runs, 48 control-line drive configs) — not shown by the old site | ✓ | P:libraries collapsed section, two tables |
| 77 | designs/*/layout.svg, cdac_layout.svg | ✗ | hub rule: pre-rendered layout images are never hosted; replaced by GDS thumbnails (top cell + CDAC sub-cell) |
| 78 | sweep.json `selected_cards` | ✓ | identical to index.json cards → Designs view |

## Verification (Phase C)

- `hubkit validate ../sar-gen-gemini4/docs --id sar` → ✓ 108 designs (108 detail docs), 4 pages, 569 hosted files
  (24.2 MB) + 216 layout thumbnails (top cell + `cdac_<key>` sub-cell), 0 warnings. Build: 38.8 MB hosted.
- Headless screenshots of Designs (matrix / cards / table), all 4 pages and all 7 detail tabs of 8 designs
  (ULP 1 kS/s 8 b MOM, mono 10 b 3.3 V MOM, LU2G 10 b MIM, mvote 12 b MIM, failed-FFT ULP 12 b, UHS 10 b MIM EOC-issue)
  — no console errors, no block render failures. Detail docs hold 41–47 leaf blocks each.
- Totals: 78 items → 66 ✓, 11 ≈ (deliberate changes: #6, #7, #15, #19, #20, #25, #26, #40, #41, #48, #56), 1 ✗ (#77, by hub rule).

## Review fix round (sar-gaps.json, 30 gaps)

Fixed (26 adapter gaps): loop-unrolled synthesized FFT codes (dynamic metrics nulled, raw-code ENOB metric + spectrum, notes,
params, overview caveat, twin-note wording); LU 3-cycle table labelled post-fit + raw codes; group-weight table by step_idx;
library-selection "used" marker and honest caption; SNR metric dropped + short-FFT caveat; analytical-noise caveat +
SPICE-only ENOB/SNDR params (HS); arch summary retitled (HS regime only); real sweep decomposition and library-size wording;
stage tags (dse `stage` column, replica traces `meta.stage`, SPICE blocks `stage: partial`); replica charts split by supply
(`meta.vdd`) + hidden "as published" traces + retitled + omitted cards named + P_leak hover; wrap/reorder of wide tables;
`vdd` columns on library tables; renderer-default legends, no backticks in trace names; matrix `status` on ENOB shortfall
(failed-FFT / LU cells grey); "None / None" row removed; ENOB/DNL/INL/FoM digits; physical PEX status (see below); cloud sampling and 11–14 b infeasibility explained; explorer hover extended; detail tabs
`id: pane` + deep links `?t.pane=3`, per-macro tabs ids; operating-mode axis (grouped ULP filter); presets reset Pareto;
Pareto `group` column + preset; short metric labels with `desc`; floorplan short labels.
Renderer issues (4) were fixed in the hub. New: `builds_on` + per-design `uses` (comparator, S/H switch, VCM buffer,
input driver; all 432 resolve against the sa/switch/opa builds).

## Round 3 (sar-round3.json)

- **ENOB above N (hub issue):** 44 cards' 16/32-point SPICE FFTs (8–16 independent, non-integer reconstructed codes) give
  ENOB > N / SNDR above the ideal N-bit limit. ENOB, SNDR and FoMs of these cards are no longer in `results`; the values stay,
  labelled, in the parameters, a warning note, the FFT caption and the tab-2 summary table. The metric description no longer claims ±0.3 b.
- Tables: 24-macro table regrouped (fits at 1440 px); Pareto and 5-corner tables put the key result columns first (still
  scroll for the descriptive tail); per-step table labels shortened. Matrix: rows Architecture × CDAC, columns resolution
  (fits at 1440 px). Long op-amp keys in Parameters get spaces around "/" (420 px overflow).
- Overview stage row/caveat (SNR, loop-unrolled exclusions) corrected; published-FoM tooltips per reason; raw-error colouring
  uses the ±1 LSB threshold; `enob_raw` removed from card metrics. Preset `show` leak fixed in the renderer.
- `physical.pex: "partial"` on all 108 designs (amber "PEX partial" badge): only the CDAC macro is Magic-extracted; the
  sub-blocks use the siblings' PEX netlists; top level not extracted. The former "PEX coverage" parameter was dropped.

## Results / honesty mapping

- `results.partial` only (SPICE with extracted CDAC + sibling PEX blocks, schematic SAR logic, no top-level routing). `robust` = all five injected-variance corners without redundant switching failure for the card's own CDAC macro.
- Pre-layout / full-chip values: model estimates, in the Dd:2 table and params only.
- ULP (36 cards): power, energy, FoMs recomputed from `waveform_post.tot`; published placeholder values kept in params and in the Dd:2 table.
- `sar_12b_3v3_ulp100k_mom`, `sar_12b_3v3_ulp1m_mom`: FFT failed → dynamic metrics null. `sar_10b_1v8_uhs100m_mim`: EOC note.
- No PVT pass count is emitted (corner flags hard-coded, non-TT corners scaled for most cards).
- Standby leakage is a result for ULP cards only (sleep-window SPICE); for continuous-mode cards it is the op-amp bias + a constant.
