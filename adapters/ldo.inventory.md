# ldo — inventory of the retired site (ldo-gen-gemini4/docs) and where it lives on the hub

Source surveyed: `docs/index.html`, `docs/assets/app.js`, `docs/data/{index,db,gmid}.json`,
`docs/designs/<key>/*` as of the regeneration at 2026-11-07 20:47 UTC (192 cards: 12 topologies ×
2 supplies × 8 load classes; the brief's 144-card/6-class state was replaced while this port ran).
Headless-Chrome screenshots of every view (Schematic and Post-layout level) are in the agent scratch dir.

Status legend: **✓** reproduced (location given) · **≈** reproduced with a documented approximation ·
**✗** not reproduced (reason given). Hub locations: *Designs* = built-in Designs view of the `ldo` tab;
*detail* = design page (`#/ldo/<key>`), tabs inside the detail document; *db* / *method* / *about* = the
component pages `?page=db|method|about`.

STATUS after the review fix round (validate ✓ 0 warnings; preview with opa + sa: 192 reuse links resolved; screenshots of cards, matrix
presets, table, detail tabs incl. deep links, DB page, opa “Used in”, hierarchy graph; no console errors): **83 items — 79 ✓, 4 ≈, 0 ✗**
(≈: B8 / H6 noise is a placeholder and not exported; J2 layout SVG viewer → GDS thumbnail (hub rule); D9 best value per load class
instead of per V_OUT). Placeholder / constant
sub-values are labelled (†/‡) instead of shown as results.

Open renderer requests: explorer point counter counting highlighted rows separately and chip lists built from the rows of the current stage; `minexponent` on explorer axes.

## A. Global chrome

| # | old-site element | hub |
|---|---|---|
| A1 | Site title "GF180 Low-Power LDO Generator", subtitle "opa-gen / sa-gen cells · Tian loop gain over PVT + Monte-Carlo · gLayout layouts · GF180MCU-D" | ✓ component `title`; subtitle on *about* → “Old site header / footer” |
| A2 | Top nav: Designs · Database explorer · Methodology | ✓ hub sub-tabs Designs · Database explorer · Methodology (+ About & data notes) |
| A3 | **Schematic / Post-layout** level switch (localStorage), re-renders every view | ✓ global **Simulation stage** (Pre-PEX = Schematic, Full post-PEX = Post-layout); every detail section and the db page are stage alternatives (`stage`+`alt`) |
| A4 | Light/dark theme toggle | ✓ hub theme toggle (built-in) |
| A5 | Footer: "generated <date> · GF180MCU-D (5LM, MIM M4/M5) · ngspice + KLayout + gLayout in hpretl/iic-osic-tools · source on GitHub" | ✓ *about* → “Old site header / footer” (generated date from meta) |

## B. Designs view (`#`)

| # | old-site element | hub |
|---|---|---|
| B1 | Hero h1 "Deliverable LDO design cards" + long lede paragraph (opa-gen / sa-gen reuse, 12 topologies, 2 supplies, 8 classes, 192 cards, verification, level switch) | ✓ *about* → “Deliverable LDO design cards” (verbatim, sibling-site links → hub opa/sa tabs) + a data check line; short form in component `summary` |
| B2 | Stats tiles (Schematic): design targets · with a feasible design · robust over PVT + Monte-Carlo · fully characterised · layouts DRC + LVS clean · simulated candidates (Σ n_points / 2) | ✓ *about* stats (Pre-PEX alternative, titled “Library statistics”) incl. “simulated candidates” labelled †; *db* stats. Header tiles keep only the stage/VDD-neutral “explored design points” (review gap 22) |
| B3 | Stats tiles (Post-layout): … robust post-layout (PVT + MC) · characterised post-layout · … · extracted parasitic capacitors | ✓ *about* stats (Full post-PEX alternative) incl. extracted parasitic capacitors |
| B4 | "Coverage matrix" panel + caption (robust / PVT only / nominal / none legend, "click a cell") | ✓ *Designs* matrix; legend text verbatim on *about* → “Coverage matrix legend” |
| B5 | Matrix **Polarity** selector: Positive (VSS-Ref) / Negative (VDD-Ref) / All (Pos + Neg) | ✓ *Designs* `polarity` axis filter (Positive / Negative / All) |
| B6 | Matrix **Cell Metric** selector — Overview (UGB · PM · Iq · Noise · Area) | ✓ preset “Overview (UGB · PM · Iq · area)” — 4 values per cell; noise omitted (‡ placeholder) |
| B7 | … Bandwidth (UGB & PM): UGB / PM · A0 | ✓ preset “Bandwidth (UGB & PM · A0)” |
| B8 | … Noise & PSRR: noise µV / PSRR 1 kHz | ≈ preset “PSRR 1 kHz & 100 kHz” — noise is a placeholder, not exported as a metric |
| B9 | … Layout Area (µm²): area / W×H | ✓ preset “Layout area (µm², W × H)” = area + width + height metrics |
| B10 | … Quiescent Iq & Dropout: Iq / dropout | ✓ preset “Quiescent Iq & dropout”; extra preset “Robustness (worst PVT / MC PM)” |
| B11 | Matrix layout: rows = architectures of the polarity, column groups "VDD = v V → Vreg = o V", sub-columns = load classes; cell colour = verification level; tooltip (UGB, PM, noise, area, Iq); click opens design | ✓ *Designs* matrix rows = topology (12), column group = VDD, columns = load class, colour = robustness flag, tooltip, click → design (Vreg not in header: fixed per VDD) |
| B12 | Filter bar: Polarity · VDD · Vreg · Iload · Topology · Status (All / PVT+MC robust / DRC+LVS clean) | ✓ axis chips Architecture · Polarity · Vreg · Load current; global VDD; Status → global Verified (DRC+LVS / PVT-robust) |
| B13 | Card grid grouped by **Voltage Class** header ("VDD → Vreg (polarity)", "N design cards across M load classes · external testbench CL (10 pF–500 pF)") and **Load Class** sub-header ("Iload <label>", "N topologies") | ✓ Cards view grouped by Vreg (= voltage class) · load current (`cards_group_by`), with counts; CL note on *about* |
| B14 | Card content: arch short name, polarity chip, VIN→VOUT chip, class chip, reused OTA/comparator chip; Bandwidth (UGB), Noise (10–100k), Layout area, Dimensions, Iq, DC gain / PM, PM PVT / MC, PSRR @ 1 kHz, Dropout / Reg, Step droop; status badges (verification level, Sim, Layout, DRC, LVS) | ✓ hub card: title incl. the reused OTA / comparator id, 12 card metrics (UGB, area, W, H, Iq, DC loop gain, PM, PM PVT, PM MC, PSRR 1k, dropout, load reg; droop as sort option), badges; noise ✗ (placeholder) |
| B15 | "No feasible design point for this target." card text (no-solution cards) | ✓ (no such card in the data) — targets without results would be listed on *about* → “Targets without a feasible design” |
| B16 | "Comparison table": Design, Iq, UGB min, PM nom°, PM PVT°, PM MC°, Loop gain dB, Dropout mV, Line reg mV/V, Load reg mV, PSRR 1k dB, Droop mV, Noise µVrms, FoM ps, Area µm², Status; sortable; rows open the design | ✓ *Designs* → Table view: default columns = old comparison table (`table_metrics`: Iq, UGB, PM nom/PVT/MC, loop gain, dropout, line/load reg, PSRR 1k, droop, FoM, area) + PVT/MC/robust/DRC-LVS status columns; “all metrics” toggle; Noise ✗ (placeholder) |

## C. Methodology (`#methodology`, below the Designs view)

| # | old-site element | hub |
|---|---|---|
| C1 | "Flow" ordered list, 12 items (Error amplifier = opa-gen cell … Compute), verbatim | ✓ *method* → Flow (verbatim, 12 items) |
| C2 | "Stability test conditions" bullet list (6 items), verbatim | ✓ *method* → Stability test conditions (verbatim) |
| C3 | "gm/Id targets (1/V)" table: Role × WI / MI (from meta.gm_targets) + pass-device row "8–24, explored" | ✓ *method* → gm/Id targets table (pass-device row repeated in both columns) |
| C4 | "gm/Id design charts" with nfet_03v3 / pfet_03v3 toggle; 3 charts (Id/W, gm/gds, fT vs gm/Id, reversed x, log y, one trace per L) | ✓ *method* → gm/Id design charts, tabs nfet_03v3 / pfet_03v3, 3 Plotly charts each (reversed x, log y, L ramp colours) |
| C5 | `#nmc` = meta.n_mc inserted in the Robustness flow item | ✓ n_mc inserted from meta in Flow item 6 |

## D. Database explorer (`#db`)

| # | old-site element | hub |
|---|---|---|
| D1 | h1 "Design database explorer" + lede (Schematic) / "Post-layout design database" + lede (Post-layout) | ✓ *db* lede as Pre-PEX / Full post-PEX alternatives + a Pre-PEX correction note (actual filter: valid PM ≥ 35°; counts of points violating the old text's criteria; candidate columns policy) |
| D2 | Stats (Schematic): explored design points · nominally feasible · VIN/VOUT/load targets · analog architectures | ✓ *db* “Database statistics” (Pre-PEX) |
| D3 | Stats (Post-layout): laid-out designs simulated post-layout · robust post-layout · analog architectures | ✓ *db* “Database statistics” (Full post-PEX) |
| D4 | Filters: VIN (All/1.8/3.3, default 3.3) · VOUT · Iload class (default class #1) | ✓ explorer chips V_IN · Load class (+ Polarity, Architecture, Point, input pair) and global VDD; default preset reproduces the old default view (V_IN 3.3 V · 10–100 nA) |
| D5 | x-axis / y-axis selectors over 16 metrics (Iq, UGB, PM, ζ, T0, load reg, Rout, dropout@Imax, dropout@Imin, line reg, PSRR 1k, PSRR 100k, current capability, area, VOUT, output error) with log flags and abs() transforms | ✓ explorer X/Y over all 16 old metrics (+ Architecture as categorical axis); PSRR signed |
| D6 | Scatter "<y> vs <x>": one trace per architecture + black diamonds = delivered analog cards (click opens card); Post-layout: delivered designs only, clickable | ✓ explorer: Pre-PEX = candidates coloured per architecture (symbols = polarity) + rings for delivered cards (click opens); Full post-PEX = delivered designs, coloured and ringed, clickable |
| D7 | Caption "N feasible points shown · black diamonds: delivered analog design cards" / "N laid-out designs shown (extracted netlists)" | ✓ explorer point count + caption |
| D8 | "Distribution per architecture (selection)" box plots of the y metric | ✓ *db* “Distribution per architecture”: Plotly box plots per architecture and supply for every metric (select, stage alternatives) + explorer strip presets (categorical X) |
| D9 | "Best <y> vs V_OUT" line chart per architecture at the selected VIN and class (max for PM, ζ, A0, PSRR, UGB, current capability; min otherwise) | ≈ *db* “Best value per architecture”: one chart per supply (block-level VDD) vs load class, every metric, stage alternatives (V_OUT is fixed per V_IN, so each old selection is one point) |
| D10 | "Database table": Architecture, VIN→VOUT, Load, Iq, UGB, PM°, ζ, Load reg mV, R_out Ω, Dropout mV, Line mV/V, PSRR 1k, Area µm²; first 300 of the selection, sortable; caption "N of M selected points" | ✓ *db* explorer-linked table “Points shown (N)” under the plot: all 13 old columns + Point, target-card link; lists exactly the points shown (chips, ranges, stage, VDD), sortable, CSV (replaces the static table) |
| D11 | Point hover text (arch, VIN→VOUT, class, Iq, UGB, PM, ζ, load reg, dropout, line reg, PSRR1k) | ✓ explorer hover: label + Iq, UGB, PM, ζ, load reg, dropout, line reg, PSRR 1k |

## E. Design detail (`#d/<key>/<tab>`) — header

| # | old-site element | hub |
|---|---|---|
| E1 | Crumbs "← all designs · <key>" | ✓ hub crumbs + prev/next |
| E2 | h1 = arch_name (e.g. "Positive PMOS-Pass Miller-Compensated LDO") | ✓ arch_name in design `summary` (bold) and tags; title = short name · VIN→VOUT · class · reused cell |
| E3 | Chips: VIN, VOUT, Iload class, polarity (≤ Iq budget), CL range, card tags (polarity, family, reused cell) | ✓ `summary` (VIN, VOUT, Iload, polarity ≤ Iq budget, simulated C_L of the class — the old global 10–500 pF chip is quoted as such, exact reused-cell link) + axis chips + tags |
| E4 | Status badges (PVT + MC robust / PVT only / nominal only / post-layout pending; Sim ✓ / Post-layout sim ✓; Layout; DRC; LVS) | ✓ detail “Status” kv (stage alternatives: verification level, Sim / Post-layout sim, Layout, DRC, LVS) + hub Physical badges |
| E5 | Post-layout note: "Post-layout view — every result … N extracted transistors (fingers), M parasitic capacitors" | ✓ detail note (Full post-PEX only) with transistor / parasitic-C counts |
| E6 | Tabs: Overview · Schematic · Simulation · Robustness · Layout (deep-linkable) | ✓ detail `tabs` Overview · Schematic · Simulation · Robustness · Layout, deep-linkable `?t.sec=<overview|schematic|simulation|robustness|layout>`, kept across stage / VDD switches |

## F. Detail — Overview tab (analog)

| # | old-site element | hub |
|---|---|---|
| F1 | "Key results (tt, 27 °C, VIN = v V)" tile grid: Quiescent current (Iq@Imin · @Imax · @Imin/10), Current efficiency, Worst-case loop bandwidth (max), Phase / gain margin (PVT · MC · light load), DC loop gain, Closed-loop damping (overshoot), Dropout @ Imax (@ Imin), Line regulation (@ Imin), Load regulation (Rout), PSRR @ 1 kHz (DC · worst), Output noise 10 Hz–100 kHz (@1 kHz), Load step droop / overshoot (settle), FoM, Start-up (overshoot), Usable VOUT range, Layout area (W × H) | ✓ Overview → “Key results” (both stages); PSRR signed; bench bounds printed (≥ 35 dB GM, ≤ 15 mV dropout, > window settling, ζ clamp); start-up ‡ when the trace never reaches V_reg; derived sub-values †; noise ‡ |
| F2 | "Error amplifier — opa-gen cell" paragraph (cell link, name, inversion, IDD, A0, UGB) | ✓ Overview → “Error amplifier — opa-gen cell” (exact link to the hub design `2p-<cell>`) |
| F3 | "Specification checks" table (Iq budget, nominal PM/GM, PVT, MC, closed-loop step, all saturated [schematic only], |VOUT−VREF|, DRC, LVS) with pass/fail badges | ✓ Overview → “Specification checks” with pass/fail colours; PVT and MC rows annotate the per-point ≥ 35° counts vs the repo flags; “all saturated” n/a (builder constant) |
| F4 | "Design point" panel: candidate counts text, knob table (knobName/knobVal incl. opa-gen link), reference current, netlist.spice link (subckt pins), design notes | ✓ Overview → “Design point”: knob table with exact links; builder defaults / sums marked † with the true values (inversion of the reused cell, DLDO pass cells, individual caps / resistors); netlist link; † note on candidate counts |
| F5 | Post-layout level: nominal values from post.char, PVT/MC from post lists | ✓ Full post-PEX alternatives read data.json `post.char` / `post.pvt` / `post.mc` |

## G. Detail — Schematic tab

| # | old-site element | hub |
|---|---|---|
| G1 | "Schematic with gm/Id annotation" (schematic.svg, annotated operating point) + description text | ✓ Schematic → schematic.svg (Pre-PEX) + description; gallery item “Schematic — pre-PEX operating point” |
| G2 | Post-layout: sizing view (schematic_sizing.svg) + description + extracted-netlist note (pex.spice link, n_mos, n_parasitic_c) | ✓ Schematic → schematic_sizing.svg (Full post-PEX) + sizing text + PEX note; gallery “Sizing view — post-layout” |
| G3 | "Error-amplifier sub-cell — transistor level" (schematic_tl.svg / schematic_tl_sizing.svg) + text with opa-gen link | ✓ Schematic → schematic_tl.svg titled “Error-amplifier sub-cell” or “Comparator sub-cell (sa-gen)” with exact opa / sa link; gallery item with the same label |
| G4 | "Device table (operating point at Imax, tt 27 °C)": Dev, Model, Role, W, L, nf, gm/Id target, gm/Id sim, Id, gm, gm/gds, |VDS|, VDSsat, Region badge (WI/MI/SI/triode colours), D/G/S/B | ✓ Schematic → Device table (Pre-PEX) with OP columns, Region coloured WI/MI/SI/triode; rows without OP marked “no op” |
| G5 | Post-layout "Device table (drawn sizes)": Dev, Model, Role, W, L, nf, gm/Id target, D/G/S/B | ✓ Schematic → Device table (drawn sizes) (Full post-PEX) |
| G6 | "Passives" table: Name, Device (MIM cap_mim_2f0_m4m5 / ppolyf_u_1k), Size, Value, Nodes | ✓ Schematic → Passives table |
| G7 | Digital family: "Block schematic" + "Analog devices" table with grouped array devices | ✓ ported (digital_tabs / grouped devices) but not exercised: no card has family “digital” (all 24 DLDOs are published as analog) |

## H. Detail — Simulation tab (analog; Schematic and Post-layout data)

| # | old-site element | hub |
|---|---|---|
| H1 | Chart "Loop gain T(f) at the class corners (Tian probe)" — |T| dB and ∠T subplots, one colour per (Iload, CL) corner; caption worst PM · GM · UGB range | ✓ Simulation → Loop gain chart (|T| + ∠T subplots, colour per corner) |
| H2 | "Loop-gain summary" table: Condition (+ light-load tag), T0 dB, UGB, PM°, GM dB, step OS, ζ, VOUT err, Iq; text about the break point and the closed-loop check | ✓ Simulation → Loop-gain summary table; second corner's step OS/ζ and the repeated GM marked † (tool-tips) |
| H3 | Chart "Line regulation / dropout" VOUT vs VIN (Imax, Imin); caption dropout @ Imax / Imin, line reg | ✓ Simulation → Line regulation / dropout chart (dropout@Imin †) |
| H4 | Chart "Load regulation and Iq vs load" (log Iload, VOUT + Iq on y2, shaded class band); caption ΔVOUT, 3 % drop current | ✓ Simulation → Load regulation chart (log x, shaded class band, Iq on y2 labelled † constant; 3 % drop current †) |
| H5 | Chart "PSRR" (Imax, Imin); caption @1 kHz / @100 kHz | ✓ Simulation → PSRR chart (caption values signed; note that the old site printed abs()) |
| H6 | Chart "Output noise density"; caption V/√Hz @ 1 kHz, µVrms | ≈ Simulation → “Output noise density” note ‡ — no spectrum exists (old site showed an empty chart + placeholder numbers); chart is emitted automatically if a spectrum appears |
| H7 | Chart "Load transient Imin ↔ Imax" (VOUT per CL, dotted step markers); caption droop/overshoot at CL nom, 10 pF, 100 pF | ✓ Simulation → Load transient chart with dotted step markers; 10 pF / 100 pF numbers marked † (scaled) |
| H8 | Chart "Line transient (VIN +10 %, 1 µs edges, Imax)" VOUT + VIN (y2); caption peak deviation | ✓ Simulation → Line transient chart (V_IN on y2) |
| H9 | Chart "Start-up (VIN, VREF, Iref ramp in 10 µs, Imax)"; caption 98 % time, overshoot | ✓ Simulation → Start-up chart (caption ‡ when the trace does not reach V_reg; overshoot †) |
| H10 | Chart "Output range: VOUT vs VREF" (Imax, Imin, ideal); caption tracking range | ✓ Simulation → Output range chart (I_max + ideal; I_min curve is a copy and is noted, range †) |
| H11 | "Bench warnings" panel (char.errors) | ✓ Simulation → “Bench warnings” section when char.errors is non-empty (none today) |

## I. Detail — Robustness tab (analog)

| # | old-site element | hub |
|---|---|---|
| I1 | "PVT corners (VIN = v V) — worst PM / GM over the 4 class corners": corner × temperature grid, coloured PM/GM badge, ζ, UGB · Iq · err; "in dropout (n/a)" and "sim failed" states | ✓ Robustness → PVT corners table (title “worst PM over the 2 class corners (I_min, I_max at C_L)”, pass/fail colours, UGB · Iq · err); GM 12 dB / ζ 0.68 constants omitted and explained |
| I2 | "Supply extremes" table (corner, temp, VIN, PM/GM cell) | ✓ Robustness → Supply extremes table |
| I3 | Pass-criterion text | ✓ Robustness → pass-criterion text + per-point / overall flag counts |
| I4 | Chart "Monte-Carlo: worst-case phase margin (N samples, global + mismatch)" histogram; caption min · mean · σ | ✓ Robustness → MC PM histogram + min/mean/σ (invalid PM < −180° excluded and reported) |
| I5 | Chart "Monte-Carlo: output error at Imin" histogram (mV); caption mean · σ | ✓ Robustness → MC output-error histogram + mean/σ (title note: data are the I_max error samples) |

## J. Detail — Layout tab

| # | old-site element | hub |
|---|---|---|
| J1 | "Layout (gLayout, GF180MCU-D)": DRC / LVS badges, W × H = area, nets count, routed terminals | ✓ Layout → kv DRC / LVS (coloured), size, nets, routed terminals † |
| J2 | Pan/zoom layout.svg viewer (+ / − / Fit) | ≈ replaced by the hub-rendered GDS thumbnail (layout block, click → GDS in repo); layout SVGs are not republished (hub rule) |
| J3 | Buttons: GDS (.gz), LVS netlist, Extracted (LVS), Post-layout netlist (PEX) | ✓ Layout → downloads GDS (.gz), LVS netlist, Extracted (LVS), PEX netlist (repo links) + hub Files panel |
| J4 | Note: "Pins (METAL2 labels) … CL is off-chip … MIM caps only Cc" | ✓ Layout → pin / CL note (verbatim) |
| J5 | Tiles: Floorplan (tiers · aspect), Interdigitated pairs, Mirror-symmetric pairs | ✓ Layout → kv Floorplan / Interdigitated / Mirror-symmetric (marked † builder constants) |

## K. Conditional content (code paths in app.js)

| # | old-site element | hub |
|---|---|---|
| K1 | "No feasible design point" panel (diag.explanation, failure-reason table, best saturated PM) | ✓ ported to *about* table “Targets without a feasible design” (designs without results cannot be hub designs); none in current data |
| K2 | Digital-LDO tabs (tabOverviewD / tabSimD / tabRobustD: clock, ripple, array, limit-cycle checks, transient + load-capacitance table, PVT / MC tables) | ✓ ported (see G7), untested — no digital-family card exists |
| K3 | "… not ready yet — the flow is still running" pending boxes; post-layout n_done/n_jobs badge | ✓ missing stage → hub “not available at this stage” / fallback; MC / layout pending notes |
| K4 | Matrix "—" for missing targets, "none" for no-solution cells | ✓ hub matrix leaves missing cells empty |

## L. Hub-only requirements (fix round)

| # | element | hub |
|---|---|---|
| L1 | Block hierarchy | ✓ component `builds_on` (opa: error-amplifier sizing, sa: comparator input-pair sizing); every design `uses` its exact sub-block (`opa/2p-<cell>` for 160 analog LDOs, `sa/<cell>` for 32 DLDOs) — all 192 resolve. Roles state the truth found in the published files: flat netlist + flat GDS (sizes reused, no sub-cell instance); DLDOs: input-pair size only, continuous-time 5-T stage, no clocked latch; 30 designs: card characterised at 1.8 V used at V_IN = 3.3 V |
| L2 | Review fixes (29 gaps) | ✓ all non-renderer gaps fixed (PSRR sign, input pair, start-up validity, C_L text, MC annotation, bench bounds, † params, exact links, DB lede, box plots, DB table rows, deep links, card grouping, half-up rounding, area precision, old-default preset, DB labels / stage notes, matrix presets, neutral header tiles, per-supply best charts, gallery labels); policy kept: card-copied candidate columns attributed to cards only |
| L3 | Round-3 fixes | ✓ PVT count now uses PM ≥ 30° (reproduces the repo's robust/PVT flag on all 384 design-stages) + new metric “PVT corners PM ≥ 35°” (Table default column, Robustness matrix preset) + per-design discrepancy note (11 design-stages); reuse caveats on design pages (EA / comparator panel), summary note for the 30 supply-mismatch designs, methodology “hub check” note; DB correction note is a Pre-PEX alternative with a Full-stage variant; JS rounding ties away from zero for negatives; gm/Id ramp violet→orange (≥ 3:1 on light and dark); explorer hover limited to per-point fields; log axes `minexponent: 0` on adapter charts |
