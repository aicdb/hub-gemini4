# ecg — inventory of the retired site (ecg-gen-gemini4/docs) and where it lives on the hub

Old site: `index.html` + `assets/app.js` (2205 lines) over `data/{summary,library,components,sens,sweep,xsim,lut}.json`
and `designs/<card_id>/{card.json, schematic.svg, layout.svg, <id>.gds.gz, netlist.spice, pex.spice, lvs_ref.spice}`.
Hub export: `adapters/ecg.py` (aicdb-hub/2). Status column filled after Phase C (validate ✓, build + headless-Chrome screenshots of every page and 6 designs at pre/partial, no console errors).

Legend: ✓ = ported (location) · ✗ = not ported (reason) · ✓* = ported with a correction / honesty label.

## Global

| # | Old element | Status / hub location |
|---|---|---|
| 1 | Header brand + nav (Deliverable Cards, Design Space & Trade-offs, Sensitivity & Calibration, Simulator Cross-Check, Component Reuse, Database, Methodology & Papers, Source ↗) | ✓ hub component tab + page nav (Designs, Design Space & Trade-offs, Sensitivity & Calibration, Simulator Cross-Check, Component Reuse, Database, Methodology & Papers, Library notes & caveats); Source ↗ = hub 'Source repo' link |
| 2 | Theme toggle | ✓ hub header ◐ toggle |
| 3 | "View Level" selector (Pre + Post-PEX overlay / Post-PEX / Pre-PEX) — drives stats, matrix, cards, tables, explorer, detail | ✓ global *Simulation* option (pre = Pre-PEX, partial = old 'Post-PEX'); old overlay → 'Pre + post-PEX overlay' sub-tab in every card's waveform tab; DB/explorer charts/arch table follow the stage |
| 4 | Context bar line 1 (GF180MCU-D 3.3 V FETs at 1.8/3.3 V, Option-B MIM, segmented pseudo-R, passband 0.05 Hz–1 kHz, 100 nW–1 µW) | ✓ page *Library notes & caveats* intro |
| 5 | Context bar line 2 (6 architectures × 2 supplies × 3 tiers = 36 cards driving an ADC) | ✓ page *Library notes & caveats* intro |

## Library view (`#`)

| # | Old element | Status / hub location |
|---|---|---|
| 6 | Intro eyebrow + h1 "Low-power chopping ECG front-end driving an ADC" + paragraph | ✓ page *Library notes & caveats* intro (verbatim); short summary in component header |
| 7 | Stats tiles: 36 cards · PVT-robust count (level dependent) · 36/36 DRC/LVS/PEX clean · 3,348 farm evaluations | ✓* page *Library notes & caveats* stats (repo 36/36 forced *and* hub re-check 9/36) + component stat tiles |
| 8 | Coverage-matrix heading + caption | ✓ page *Library notes & caveats* section 'Coverage matrix …' (verbatim caption) + mapping note |
| 9 | Coverage matrix: rows = 6 architectures (name · short + IBL type), cols = V_DD (1.8 V / 3.3 V, with V_CM) × 3 tiers; cell = |Z_in| (big), gain, power, IRN, NEF, "29/29 PVT", "DRC/LVS✓"; colour by PVT status; click → card | ✓* Designs view matrix: rows = architecture + IBL-type subtitle (as old), cols = V_DD × tier; 5 cell values (|Z_in|, power, LNA gain, boost, f_H) + 8 presets; PVT x/29 + robust colour (tagged 'pre' at partial/full). Gain/IRN/NEF are model figures → per card + Database. ✗ V_CM in the group header (renderer has no slot; V_CM in params) |
| 10 | Filter: Architecture | ✓ axis chips 'Chopping + IBL architecture' |
| 11 | Filter: Supply V_DD | ✓ global V_DD |
| 12 | Filter: Power tier | ✓ axis chips 'Power tier' |
| 13 | Filter: Verification (29/29 PVT pass · DRC/LVS/PEX clean) | ✓* global *Verified* (DRC+LVS / PVT-robust, robust = hub re-check) |
| 14 | Sort cards (architecture & tier, power, chopped noise, |Z_in|, NEF, DR, area) | ✓* card *Sort* (power, |Z_in|, area, LNA gain, f_H, THD); noise/NEF/DR (model) sortable in page *Database* |
| 15 | Search (ID, OTA, IBL type …) | ✓ global search (id, title, tags incl. arch title, IBL/HPF type, tier label, core/aux OTA) |
| 16 | Card grid (36): title, chips V_DD/tier/f_chop, PVT + physical badges, 8 KV rows (power, AFE gain + LNA, A_OL, CMRR/PSRR, |Z_in| + boost, IRN/NEF, passband, DR/area), footer (post-PEX gain/Z_in, MC V_os), count text | ✓* Designs view cards grouped by architecture (|Z_in|, power, LNA gain, f_H, f_L, boost, IBL-off |Z_in|, THD, area + badges); model KV rows on each design page Overview tab |
| 17 | Master comparison table: Arch, VDD, Tier, Power, AFE gain, A_OL, LNA gain, f_H, |Z_in|, boost, IRN, NEF, CMRR, PSRR, THD, DR, Area, PVT badge, Physical badge; sortable; row click | ✓ page *Database* table (all columns + PVT repo/hub + Physical, sortable, row click) and Designs view Table view |
| 18 | "Download filtered CSV" | ✓ CSV button on page *Database* table and Designs view table |
| 19 | Footer downloads: library.json, summary.json, sweep.json, components.json, lut.json | ✓ page *Library notes & caveats* 'Downloads' (repo links; + xsim.json, sens.json) |
| 20 | Footer text (ngspice-46 farm, gLayout PR #128, KLayout DRC/LVS, Magic PEX) | ✓ page *Library notes & caveats* (verbatim) |

## Design-space view (`#explore`)

| # | Old element | Status / hub location |
|---|---|---|
| 21 | Intro: eyebrow, h1 "Measured ECG front-end design space (324 DSE candidates + 36 Pre/Post-PEX deliverables)", paragraph | ✓ page *Design Space & Trade-offs* intro (verbatim, count from data) |
| 22 | Filters: supply, architecture | ✓ explorer Architecture / Supply chips + global V_DD |
| 23 | X-axis selector (P_tot, chopped IRN, |Z_in|, NEF, A_mid) and Y-axis selector (IRN, |Z_in|, DR, NEF, A_mid), per-metric log axes | ✓ explorer X/Y selectors over 15 numeric dims + log toggles + 11 presets |
| 24 | "Interactive Pareto trade-off explorer": 324 DSE points coloured by architecture + 36 pre-PEX deliverable diamonds + 36 post-PEX stars, click → card | ✓* Design Space explorer: 324 DSE points + 36 deliverables (best stage ≤ selected, ring = delivered, click → card), old ARCH_COLORS palette, symbol = point type (+ 'Colour by point type' preset for a legend), Pareto, facets; old default-axes bug fixed; text annotated with the stored ranges |
| 25 | Chart "Chopped IRN vs total power" (one line per architecture, 1.8 V or 3.3 V) | ✓ Design Space 'Architecture curves' — one V_DD tab drives both charts, stage alternatives |
| 26 | Chart "Boosted |Z_in(50 Hz)| vs power tier" (grouped bars per architecture, log y) | ✓ page *Design Space & Trade-offs* 'Architecture curves' |Z_in| ✓ same tabs as #25 (|Z_in| bars, boost-range annotation) |
| 27 | "Architecture trade-off comparison" table: architecture + title, IBL mechanism, HPF/DC-offset mechanism, core/aux OTAs, mean gain, mean |Z_in|, mean boost, best LN IRN, best NEF, mean area | ✓ page *Design Space & Trade-offs* trade-off table (stage alternatives; OTA links to opa tab) |
| 28 | DSE dimensions present in sweep.json but not selectable on the old site (iref_core, C_pf size, f_L, f_H, PM, boost, PEF, LNA gain, A_OL, in-window, Pareto flag) | ✓ page *Design Space & Trade-offs* explorer dims I_ref,core, C_pf, f_L, f_H, PM, boost, PEF, LNA gain, A_OL, tier, in-window, Pareto flag |

## Simulator cross-check view (`#xsim`)

| # | Old element | Status / hub location |
|---|---|---|
| 29 | Intro eyebrow + h1 + paragraph (Benchmark A/B description) | ✓ page *Simulator Cross-Check* intro (verbatim) |
| 30 | KPI tiles: mean |ΔGain|, mean |Δf_H|, mean |ΔPower| (Spectre vs ngspice), "<0.05 % engine delta" | ✓ page *Simulator Cross-Check* stats (from xsim.json summary) |
| 31 | "Executive engineering conclusion" — verdict notice (good) + items 1–2 | ✓ page *Simulator Cross-Check* conclusion section (verbatim notes + items 1–2) |
| 32 | Warning notice (gmin / rshunt floor) + items 3–4 | ✓ page *Simulator Cross-Check* (verbatim warning + items 3–4) + hub data-check note (prose vs stored numbers) |
| 33 | Selector: Benchmark A transistor sweep (18 device jobs) | ✓ page *Simulator Cross-Check* 'Benchmark A transistor sweep' dropdown (18 devices, default nfet L=1 µm tt 27 °C) |
| 34 | Selector: Benchmark B card (36) | ✓ page *Simulator Cross-Check* 'Benchmark B ECG front-end card' dropdown (36) |
| 35 | Chart A1: I_D vs V_GS (log), 5 simulator/model/gmin variants | ✓ A1 chart per device (5 old variants + ngspice gmin=1e-15) |
| 36 | Chart A2: g_m/I_D vs V_GS | ✓ A2 chart per device |
| 37 | Chart A3: g_m/g_ds vs V_DS (at V_GS = 0.36 V) | ✓ A3 chart per device |
| 38 | Chart B1: closed-loop |A_CL(f)| ngspice / Spectre / HSPICE for selected card | ✓ B1 chart per card |
| 39 | Chart B2: |Z_in(f)| overlay | ✓ B2 chart per card |
| 40 | Chart B3: 36-card power parity (1:1 line, Spectre, HSPICE) | ✓ page *Simulator Cross-Check* B3 parity chart (click → card) |
| 41 | Benchmark A summary table (device, L, corner/temp, g_m/I_D @0.35 V ×3 sims, I_D @0.35 V ×3 sims, slope S, g_m/g_ds gmin 1e-12 → 1e-15) | ✓ page *Simulator Cross-Check* Benchmark A table (all 11 columns) |
| 42 | Benchmark B summary table (card, arch, VDD, gain ×3, A_OL, LNA gain, f_H ×3, P_core ×2, |Z_in| ×2), row click → card | ✓ page *Simulator Cross-Check* Benchmark B table (all 15 columns, row → card) |

## Component-reuse view (`#reuse`)

| # | Old element | Status / hub location |
|---|---|---|
| 43 | Intro eyebrow + h1 + paragraph (96 OTAs / 25 switches / 32 comparators, 200f library) | ✓ page *Component Reuse* intro (verbatim) |
| 44 | Chart: top-14 200f OTAs, LNA vs Aux score | ✓ page *Component Reuse* OTA score chart |
| 45 | Chart: top-12 switches, chopper vs S&H score | ✓* page *Component Reuse* switch score chart (chopper bars were empty on the old site — field name fixed) |
| 46 | Table 1: reused OTAs (card id, topology, VDD, regime, A0, UGB, PM, noise @1 kHz, CMRR, PSRR, V_os σ, LNA score, Aux score) + caption | ✓ page *Component Reuse* table 1 (+ load lib, power, area, used-by count; ids link to opa tab `200f-<id>`) |
| 47 | Table 2: reused chopper & S&H switches (key, topology, VDD, R_on, |Q_inj|, CFT, I_off, chop score, S&H score) | ✓* page *Component Reuse* table 2 (old table showed '—' — fields mapped to topo/name, R_on min/max, Q_inj, pedestal, leakage, energy; ids link to switch tab) |
| 48 | Table 3: reused clocked comparators (id, topology, VDD, delay, energy, V_os σ, kickback, score) | ✓* page *Component Reuse* table 3 (old table empty — mapped to key, arch/mix, delay_1mv, e_core, vos σ, kickback, PVT, score; ids link to sa tab) |

## Database view (`#db`)

| # | Old element | Status / hub location |
|---|---|---|
| 49 | Intro (eyebrow, h1 "Full 36-card ECG front-end specification database", paragraph) | ✓ page *Database* intro (verbatim) |
| 50 | DB table: Card ID, Arch, VDD, Tier, Power, AFE gain, A_OL, LNA gain, f_H, |Z_in|, boost, IRN, NEF, PEF, CMRR, PSRR, THD, DR, Area, Physical; sortable, row click, follows view level | ✓* Database page: two stage-following tables (simulated/physical/verification and model-derived) carrying every old column; PVT/MC on partial rows tagged '(pre)'; recovered f_H highlighted |

## Methodology view (`#methodology`)

| # | Old element | Status / hub location |
|---|---|---|
| 51 | Intro (eyebrow, h1 "Automated chopping ECG front-end design & verification flow", paragraph) | ✓ page *Methodology & Papers* intro (verbatim) |
| 52 | "Seven-stage automated synthesis & signoff pipeline" (7 items, verbatim) | ✓ page *Methodology & Papers* pipeline list (verbatim) |
| 53 | "Reference IEEE literature in ref/" table (6 rows: reference, technique, portfolio mapping) | ✓ page *Methodology & Papers* literature table (verbatim) |
| 54 | Chart NMOS g_m/I_D vs I_D/W (per L) | ✓ page *Methodology & Papers* LUT chart |
| 55 | Chart PMOS g_m/I_D vs I_D/W | ✓ page *Methodology & Papers* LUT chart |
| 56 | Chart NMOS f_T vs g_m/I_D | ✓ page *Methodology & Papers* LUT chart |
| 57 | Chart PMOS f_T vs g_m/I_D | ✓* page *Methodology & Papers* LUT chart (+ note: captions say V_DS 0.6 V, data 0.5 V) |

## Sensitivity view (`#sens`)

| # | Old element | Status / hub location |
|---|---|---|
| 58 | Intro (eyebrow, h1, paragraph) | ✓ page *Sensitivity & Calibration* intro (verbatim) |
| 59 | KPI tiles: Spectre/HSPICE ok counts, #1 source, #2 source, "8×–12.5×" | ✓* page *Sensitivity & Calibration* stats (S values from data instead of the hard-coded '+11.9' / '+0.92') |
| 60 | "Dominant variation sources" panel: warn notice + items #1–#2, good notice + items #3–#5 (verbatim) | ✓ page *Sensitivity & Calibration* 'Dominant variation sources …' (verbatim) + provenance note |
| 61 | Selector: target metric for tornado (7 metrics) | ✓ page *Sensitivity & Calibration* 'Target metric for tornado plot' dropdown (7) |
| 62 | Selector: inspect specific card (36) | ✓ page *Sensitivity & Calibration* 'Inspect specific design card' dropdown (36) |
| 63 | Chart 1: global 3σ tornado, Spectre vs HSPICE | ✓ page *Sensitivity & Calibration* chart 1 per metric |
| 64 | Chart 2: uncalibrated vs post-calibration 3σ spread (top 7) | ✓* page *Sensitivity & Calibration* chart 2 (labelled: residual = assumed reduction) |
| 65 | Chart 3: architecture sensitivity comparison (top-5 sources × 6 architectures) | ✓ page *Sensitivity & Calibration* chart 3 |
| 66 | Chart 4: selected-card 3σ breakdown (Spectre |Z_in|, HSPICE |Z_in|, Spectre f_H, Spectre V_out) | ✓ page *Sensitivity & Calibration* chart 4 per card |
| 67 | Table: tunability element & calibration-cell design guide (rank, source + category, 3σ spread, S^Zin, 3σ Δ|Z_in| Spectre/HSPICE, S^fH, Δf_H, Δf_L, ΔA_OL, ΔV_out, cell + target, bits + range, post-cal residual) | ✓ page *Sensitivity & Calibration* calibration-cell table (all columns) |
| 68 | Table: architecture-by-architecture dominant sources (arch, IBL & HPF, top-3 sources, ΔZin from ΔCpf, Δf_H from ΔI_bias, Δf_L from ΔR_PR, ΔA_OL from ΔV_th, ΔV_out from ΔV_th,in) | ✓ page *Sensitivity & Calibration* architecture table (all columns) |

## Design detail (`#/<card_id>`, 36 cards)

| # | Old element | Status / hub location |
|---|---|---|
| 69 | Back button + per-detail "Level" selector | ✓ hub breadcrumb/prev-next; level selector = global *Simulation* |
| 70 | Header: eyebrow (card id · arch ref), h1 (arch name — arch title), meta (V_DD, V_CM, tier, target power, f_chop, β_IBL), description, PVT + physical badges, availability line | ✓ design page title, axis chips, tags, summary (card id · ref, V_DD/V_CM, tier/target, f_chop, β_IBL, description), Physical badges, stage table + hub re-check note |
| 71 | Tab bar (8 tabs) | ✓ design page tabs block with the 8 old tab labels |
| 72 | Overview: 12 KPI tiles with "Pre → Post" sub-lines | ✓* Overview tab stats (stage alternatives pre/partial; 'Pre → Post' sub-lines; model tiles labelled) |
| 73 | Overview: Verification Signoff Checklist (8 checks, evidence, PASS/WARN/PENDING) | ✓* Overview tab checklist (repo status + hub re-check column) |
| 74 | Overview: Reused Sub-Blocks & Passive Sizing (9 rows incl. power breakdown) | ✓ Overview tab table (links to opa/switch/sa hub pages) + new 'Nominal spec compliance' table (stage alternatives) |
| 75 | Schematic: downloads (pre-PEX SPICE, post-PEX SPICE, schematic SVG) | ✓ Schematic tab downloads (netlists = repo links, schematic SVG hosted) |
| 76 | Schematic: caption + zoomable connected schematic SVG | ✓ Schematic tab image block (click = full size; zoom buttons → browser zoom) + figure gallery |
| 77 | Schematic: Transistor Sizing & Simulated Operating Point table (16 columns) | ✓* Schematic tab OP table (stage alternatives; g_m column fixed, + g_ds, V_th) |
| 78 | Simulation: TB1 AFE gain hierarchy (total AFE, core A_OL, stage-1 LNA, post total) | ✓ Waveforms tab TB1 (stage alternatives + overlay) |
| 79 | Simulation: TB3 |Z_in(f)| IBL on/off (+ post) | ✓ TB3 |
| 80 | Simulation: TB4 noise PSD chopped/unchopped (+ post) | ✓ TB4 |
| 81 | Simulation: TB2 CMRR & PSRR+ (+ post) | ✓ TB2 CMRR/PSRR |
| 82 | Simulation: TB2 electrode-DC-offset sweep (+ post) | ✓ TB2 EDO |
| 83 | Simulation: TB5 50 Hz FFT (+ post) | ✓ TB5 FFT |
| 84 | Simulation: TB5 THD vs amplitude (+ post) | ✓ TB5 THD vs amplitude |
| 85 | Simulation: TB6 2-beat P-QRS-T ECG → S&H → comparator | ✓ TB6 (pre / partial / overlay=post as before) |
| 86 | Simulation: overlay vs single-level behaviour (solid pre / dashed post) | ✓ Waveforms tab sub-tabs 'At the selected simulation stage' / 'Pre + post-PEX overlay (old default view)' |
| 87 | Robustness: TB7 gain across 29 corners (bar) | ✓* Robustness tab (stage pre; bars coloured by hub spec check) |
| 88 | Robustness: TB7 |Z_in| across 29 corners (bar) | ✓* same |
| 89 | Robustness: TB8-A MC chopped-offset histogram | ✓* (labelled model) |
| 90 | Robustness: TB8-A MC |Z_in| vs gain scatter | ✓ (red = run out of spec) |
| 91 | Robustness: TB8-B ±15 % C_pf sweep (|Z_in|, PM) | ✓* (PM labelled estimate) |
| 92 | Robustness: TB8-C dry-electrode mismatch CMRR (IBL on/off) | ✓* (labelled analytic; + gain-attenuation traces) |
| 93 | Robustness: "All 29 Recorded PVT Corner Evaluations (TB7)" table (11 columns + status) | ✓* Robustness tab PVT table (all columns + LNA gain + hub spec check; failing cells red) + MC summary kv + per-run MC table |
| 94 | Sensitivity tab: info notice + 4 KPI tiles | ✓ Sensitivity tab note + 4 tiles |
| 95 | Sensitivity tab: severity tornado Spectre vs HSPICE (10 sources) | ✓ tornado |
| 96 | Sensitivity tab: uncalibrated vs post-cal (top 6) | ✓* uncal vs post-cal (labelled assumed) |
| 97 | Sensitivity tab: "Ranked Sensitivity & Tunability Cell Specification Table" (12 columns) | ✓ ranked table (all 12 columns) + HSPICE .sens top-elements table |
| 98 | Cross-check tab: info notice + 4 KPI tiles | ✓ Cross-check tab note + 4 tiles |
| 99 | Cross-check tab: |A_CL(f)| ngspice/Spectre/HSPICE | ✓ AC chart |
| 100 | Cross-check tab: |Z_in(f)| ngspice/Spectre/HSPICE | ✓ |Z_in| chart |
| 101 | Cross-check tab: "Side-by-Side Simulator Comparison Table" (10 metrics × 3 sims + |Δ|) | ✓* side-by-side table (+ honesty caption) |
| 102 | Layout tab: info notice (DRC / LVS / PEX) | ✓ Layout tab note |
| 103 | Layout tab: downloads (GDS, layout SVG, LVS reference, PEX netlist) | ✓ Layout tab downloads (GDS, LVS ref, PEX = repo links); ✗ layout SVG — hub rejects layout SVGs, replaced by GDS thumbnail |
| 104 | Layout tab: zoomable layout SVG + footprint | ✓ Layout tab `layout` block (hub-rendered GDS thumbnail + footprint caption); ✗ old zoomable SVG (not allowed) |
| 105 | Layout tab: "Physical Verification & Extraction Summary" (8 rows) | ✓ Layout tab physical summary table (+ DRC by rule) |
| 106 | Layout tab: "Top-Level Pin Coordinates (METAL2 36/10)" table | ✓ Layout tab pin table |
| 107 | Provenance tab: downloads (card JSON, pre/post SPICE, library.json) | ✓ Provenance tab downloads (repo links) |
| 108 | Provenance tab: "Reused Library Components & Artifact Provenance" (subckt signature, 5 reused blocks, PDK models, 3 SHA-256 hashes) | ✓ Provenance tab table (signature from library.json ports, links to reused cells, hashes) |
| 109 | Card data not shown by the old site: HSPICE `.sens` top elements, TB5 transient, MC f_H/power per run, electrode gain attenuation, AC phase | ✓ added: HSPICE .sens table, TB5 transient chart, TB1 phase chart, per-run MC table (f_H/power/offsets), electrode gain attenuation; ✗ none |

## Summary

109 items: all 109 ✓ (23 of them ✓* = ported with a correction or an honesty label); 2 carry a partial ✗ (#103/#104: the per-card
`layout.svg` cannot be hosted on the hub — replaced by the hub-rendered GDS thumbnail and the raw-GDS repo link).

Honesty decisions (details on the *Library notes & caveats* page):
- `results` carry only simulation-derived metrics; model-derived figures (AFE gain incl. ideal VGA, A_OL, chopped
  IRN/NEF/PEF, CMRR/PSRR, DR, IMD3, PM, TB6 waveforms, MC chopped offset, TB8-C) are shown labelled *model*
  (switch `MODEL_IN_RESULTS` in ecg.py to also list them, labelled, in results).
- "post-PEX" → `partial` (nominal only, identical to pre); PVT/MC/robust only at `pre`, re-checked by the hub
  against the library spec windows (repo forces 29/29 + 100 %): 9/36 robust.

## Review fix round (ecg-gaps.json, 23 gaps)

| gap | finding | status |
|---|---|---|
| 0 | f_H conditioned on 9 cards | ✓ adapter detects conditioning from the stored simulated LNA trace; results/spec checks/DB/explorer use the recovered simulated f_H (exact inverse for 6, trace −3 dB for the 3 clipped cards); per-card notes + notes item 7 list all 9 |
| 1 | default stage hides PVT status | ✓ renderer (per-field fallback); notes wording updated |
| 2 | PVT/MC metrics blank at default | ✓ renderer per-metric fallback; presets labelled "(pre-PEX only)"; DB partial rows show "(pre)" values |
| 3 | delivered rings invisible | ✓ renderer (rebuilt, rings visible) |
| 4 | partial = copy of pre | ✓ labelled "Unverified post-PEX run, no measurable parasitic effect" + injected count (41–58 of 100–148 caps) in results note, notes item 1 |
| 5 | explorer colours ≠ charts | ✓ arch dim `colors` = old ARCH_COLORS |
| 6 | point-type encoding / old marker text | ✓ caption rewritten for hub encoding, intro annotated, kind colours + preset |
| 7 | explorer ignores stage | ✓ `stage` column + `stage_group: design` |
| 8 | verbatim numeric claims | ✓ hub annotations (DSE power 137.9–840.9 nW, β_IBL 0.878, C_pf sizes, boost 5.0–21.6×), PM 90°×28 / 72°×8 |
| 9 | double rounding | ✓ results/table/explorer values kept at 9 significant digits |
| 10 | half-even vs toFixed | ✓ Decimal ROUND_HALF_UP in nf/zin_s/pw_s |
| 11 | THD floor on ccia_dsl_1v8_ln | ✓ THD dropped from results, shown "≤ 0.005 % (floor)" |
| 12 | reuse counts | ✓ distinct cards; OTA usage only on 200f rows |
| 13 | VDD filter / deep links | ✓ per-card tabs carry `vdd`, parity traces `meta.vdd`, all tabs have `id` (card, wave, curves, tornado, senscard, xsima, xsimb); Benchmark-B rows carry a *curves* link `t.xsimb=<card id>` (tab `key`, round 3) |
| 14 | wide tables | ✓ column `wrap`, calibration-cell column moved next to source, reuse tables full width, DB split in two, trade-off numbers first |
| 15 | modebar over legends | ✓ renderer |
| 16 | 1B ticks / IRN unit | ✓ renderer SI ticks; IRN dim unit Vrms |
| 17 | number formatting | ✓ xsim f_H columns si, spec value digits 5, LUT x-axis A/m ≡ µA/µm |
| 18 | empty DB at full/fb=0, DB intro | ✓ renderer note; intro reworded to the global Simulation option |
| 19 | card metrics | ✓ f_L, boost, IBL-off |Z_in| added |
| 20 | separate VDD tabs | ✓ one tabs block for both charts |
| 21 | matrix header context | ✓ IBL type as second row axis (old subtitle); V_CM via `vdd_labels` (round 3) |
| 22 | KPI tile overflow | ✓ OTA id removed from the sub-text |

New requirement: `builds_on` (opa, switch, sa) + per-design `uses` (core OTA, aux/DSL/PGA/buffer OTA, chopper, S&H, comparator) — all 162 references resolve in a build with opa/switch/sa (0 unresolved).

## Round 3 (ecg-round3.json)

| item | status |
|---|---|
| gap 14 wide tables | ✓ measured at 1440 px, no overflow on Database (both tables), Sensitivity (guide + architecture), Design space trade-off, Cross-check A/B, Reuse (OTA/switch/comparator), detail OP/sensitivity tables: units moved into headers, grouped headers, merged cells. Remaining: the hub's built-in Designs *Table* view (title + 3 axis columns, renderer-built, nowrap) still scrolls; default columns reduced via `table_metrics` |
| preset colour regression | ✓ every preset sets colour = architecture / symbol = point type except "Colour by point type" |
| DB intro claim | ✓ reworded (no "no horizontal scrolling" claim) |
| notes "PVT/MC not evaluated" wording | ✓ now describes the neutral cell colour + legend |
| new: `vdd_labels` | ✓ V_CM in the supply headers |
| new: tabs `key` | ✓ xsim A/B and sens card tabs keyed by device/card id; Benchmark-B *curves* link |
| forced dtick | none in the adapter |
