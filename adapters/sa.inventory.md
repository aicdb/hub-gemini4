# sa-gen-gemini4 — inventory of the retired GitHub Pages site

Source: `sa-gen-gemini4/docs` (index.html, assets/app.js `VER 20261107a`, assets/style.css,
data/index.json, data/dse.json, data/compare.json, data/gmid.json, designs/<key>/{data.json,
schematic.svg, schematic_pex.svg, layout.png, comp.gds(.gz), netlist.spice, netlist_pex.spice,
lvs_reference.spice, extracted.cir}). 96 designs = 9 architectures × mixes (16 arch/mix pairs) ×
2 VDD × 3 IDD bands. Every design has both `results` (schematic) and `results_pex`.

Status legend (filled in after the port): ✓ = reproduced in the hub (location given),
✗ = not reproduced (reason given). Hub locations: **Designs** = built-in Designs view,
**overview / compare / explore / method** = component pages (`#/sa?page=<id>`),
**detail** = per-design detail document (`hub/designs/<key>.json`).

## A. Global chrome (header / footer)

1. Brand "Low-Power Clocked Sense Amplifier Generator" + subtitle "gm/Id-sized · simulation-closed gm/Id & IDD bands · ngspice-verified · DRC/LVS-clean gLayout · GF180MCU-D".
   → ✓ component `title` + Overview & table → About the generator (subtitle quoted)
2. Top nav: Designs · Comparison · Design-space explorer · Methodology.
   → ✓ hub page tabs: Designs · Overview & table · Comparison · Design-space explorer · Methodology
3. Technology toggle (single button "GF180") + tech note.
   → ✓ hub global Technology option (single gf180mcuD)
4. Netlist toggle "Schematic" / "Post-PEX" (default Post-PEX when ≥ half the cards have `m_pex`; persisted in localStorage `sa-net`); switches cards, matrix, table, stats, compare maps, DSE data, detail tabs, schematic SVG, netlist link.
   → ✓ hub global Simulation stage (Pre-PEX ↔ Partial post-PEX; default Full+fill shows partial = old default Post-PEX); applied to results, matrix/cards/table, overview table (`stage_column`), compare maps/charts, explorer (`stage` column), ND table, every detail block (stage alternatives), schematic image, netlist link
5. Net note: "Showing <schematic (pre-PEX) | extracted layout (post-PEX)> results · All 96 designs compared at uniform read rate f_read = 2.5 MHz (T_read = 400 ns)".
   → ✓ stage badge on every block + overview page text (uniform read rate stated in summary/lede)
6. Theme toggle (light/dark).
   → ✓ hub theme toggle
7. Footer: "generated <date> · GF180MCU-D (5LM, MIM M4/M5) · ngspice-46 + gLayout + KLayout + Magic · uniform read rate f_read = 2.5 MHz · C_L = 200 fF per output · source on GitHub".
   → ✓ Overview & table → About the generator; Methodology → Data provenance (tool-chain note)

## B. Designs (list) view

8. Hero title "Deliverable sense-amplifier design cards" + long lede (architectures, mixes, six VDD×IDD targets, read rate, 200 fF load, flow summary).
   → ✓ Overview & table page intro (full lede)
9. Stats tiles: design cards (6 VDD×IDD sets) · gm/Id & IDD closed · characterised · DRC + LVS clean.
   → ✓ Overview & table → stats block (96/96/96/96 + PVT-robust pre/partial); component stats tiles
10. Coverage matrix "6 (VDD × IDD range) combinations @ f_read = 2.5 MHz": rows = architecture × threshold mix (arch_mixes order), columns = VDD × IDD band; cell = "delay@1 mV · IDD" badge, colour robust (all PVT) / nominal / fails / pending; click opens design.
   → ✓ Designs → Matrix (rows topology·mix, cols I_DD band inside VDD groups, cell delay@1 mV / I_DD, colours robust/not robust/failed, click opens design); presets incl. “Delay @1 mV · I_DD (old matrix)”
11. Matrix caption text (cell meaning, badge legend, "click a cell").
   → ✓ Overview & table → “Coverage matrix …” markdown (hub legend under the matrix)
12. Filter segments: VDD (all/1.8/3.3) · Architecture (9) · Threshold mix (3) · IDD range (3).
   → ✓ Designs → axis chips (Architecture, Threshold mix, I_DD range) + global VDD option
13. Card grid grouped by architecture (group heading = full architecture name + "N designs").
   → ✓ Designs → Cards (generator order = grouped by architecture; no group headings — full architecture name in each design summary)
14. Card contents: title arch·mix; chips VDD, IDD band, mix, f_read; kv IDD@2.5 MHz, gm/Id tgt→sim (n/p for FIA), t_d@1 mV, E/read, ΔV_BL,min, σ noise, σ offset (MC), Area; status badges (Sim ✓/✗, Self-Cal ✓, IDD band ✓ / out of band, Layout ✓, DRC, LVS, PVT n/29, "gm/Id target not reached").
   → ✓ cards show I_DD, delay, E/read, τ, kickback, area + stage/robust/PVT/DRC/LVS/PEX badges; gm/Id tgt→sim, ΔV_BL,min, σ noise, σ offset (model) are in Overview & table and detail; Self-Cal / I_DD-band / gm/Id-not-reached as design tags
15. "Comparison table" heading + caption; 21 sortable columns: Design, Arch, Mix, VDD, IDD band, IDD@2.5 MHz, gm/Id tgt→sim, V_CM, ΔV_BL,min, t_d 1 mV, τ_regen, E/read, σ noise, σ offset, E·σ² (fJ·mV²), f_max, CM range, PVT, Kickback, Area µm², DRC/LVS; row click opens card.
   → ✓ Overview & table → “Comparison table” (all 21 columns + Stage, Self-Cal, I_DD in band; model columns labelled; sortable, CSV, rows open design; follows stage + VDD)
16. Pending/closure fallbacks (delay_close, e_close, idd_sim, "(closed)" cells, "Sim …" badges) — conditional, not triggered by current data (all 96 simulated).
   → ✓ n/a — conditional pending/closure branches never trigger (all 96 simulated); not ported

## C. Comparison view (`#compare/<vdd>/<tgt>`)

17. Hero "Design comparison" + lede (resolve-time map definition, white = not resolved, shared axes/colour).
   → ✓ Comparison page intro
18. Stats: designs in this set · shared colour scale (min–max delay).
   → ✓ Comparison → per-set stats block (designs in set, shared colour scale), per stage
19. Selectors: VDD (1.8/3.3) · IDD range (3 bands) — 6 sets.
   → ✓ Comparison → Resolve-time maps tabs (6 sets, tabs carry `vdd` so the VDD option filters them)
20. Colour-scale legend gradient (min / mid / max) + legend sentence (axes, white = wrong, ▸ nominal V_CM).
   → ✓ Comparison → section intro + colourbar on the last map of each row (no separate gradient strip)
21. Resolve-time map grid: one heatmap per design of the set (16), x = |ΔV_BL| 10 µV…100 mV (log ticks 10µ…100m), y = V_CM 0…VDD, z = log10 delay (ns), viridis reversed, shared z-range per set, red tick = nominal V_CM; card title links to the design, caption "V_CM,nom · IDD · t_d(1 mV)".
   → ✓ Comparison → 16 heatmap charts per set and stage (same axes/ticks, shared z, red V_CM tick, title links to design, caption V_CM·I_DD·t_d, click opens design)
22. "Sensing delay vs differential bitline input |ΔV_BL|" section + caption (τ slope).
   → ✓ Comparison → “Sensing delay vs …” section intro
23. Line legend (architecture colours, mix dash styles).
   → ✓ Plotly legend entries (architecture colours, mix dash styles)
24. Two charts (VDD 1.8 / 3.3) for the selected IDD band: delay vs |ΔV_BL| per design, log–log, shared ranges, colour = arch, dash = mix; click opens design.
   → ✓ Comparison → tabs per I_DD band, 2 charts (VDD-tagged), shared log ranges, colour/dash, click opens design, per stage
25. "Energy per read, average IDD, sensing delay, noise and offset" section + caption + legend (colour = arch, symbol = mix, fill = IDD band).
   → ✓ Comparison → section intro + legend entries (arch colour, mix symbol, band fill)
26. Scatter: sensing delay @1 mV vs average IDD, per VDD (2 charts, shared log axes), click opens design.
   → ✓ Comparison → delay vs I_DD scatter ×2 VDD, per stage, shared axes, click opens design
27. Scatter: input noise σ vs energy/read, per VDD (2 charts).
   → ✓ Comparison → noise vs energy ×2 VDD (labelled *σ is a model constant*)
28. All of C switches with the Schematic/Post-PEX toggle (`cmdm_pex`, `dvin_pex`).
   → ✓ stage alternatives (`cmdm_pex`, `dvin_pex`, `m_pex`)

## D. Design-space explorer view (`#explore/<preset>/<vdd>`)

29. Hero "Design-space explorer" + lede (sweep description: gm/Id 50…92 % of peak, σ_os target, latch scaling, 200 fF, 2.5 MHz).
   → ✓ Explorer page intro (old text kept, with correction note)
30. Stats: design points simulated (11,520) · functional · gm/Id target reached · 4-objective non-dominated @ VDD.
   → ✓ Explorer → stats block per stage (points, functional, met, ND @1.8/3.3 V)
31. Selectors: VDD (1.8/3.3) · Trade-off preset (Energy vs speed, Energy vs noise, Energy vs offset, FoM vs speed, Offset vs area, FoM vs gm/Id) · checkbox "only points that reach their gm/Id target".
   → ✓ VDD → global option / explorer chips; trade-off presets → tabs (front charts) and explorer presets; “only gm/Id met” → explorer `met` filter + note (all points met, no effect)
32. Overview chart "Pareto fronts by architecture — Y vs X (VDD)" (or "Lower envelopes" for FoM vs gm/Id): per-architecture fronts (hv steps), dashed all-architecture front, black diamonds = delivered cards (click opens card), rich hover (id, arch, mix, VDD, gm/Id, target, % of peak, σos target, latch ×, W_in, f_read, t_d, E, τ, σn, σos, area); shared axis ranges over both VDDs; caption = preset caption + explanation.
   → ✓ Explorer → “Pareto fronts by architecture” tabs (6 presets × VDD-tagged charts × stage): per-arch hv fronts / lower envelopes, dashed global front, delivered diamonds (click opens design), full hover text, shared ranges
33. "Per-architecture design clouds" heading + caption + legend (12 inversion levels as viridis dots, mix symbols, delivered diamond).
   → ✓ Explorer → “Per-architecture design clouds” explorer intro (colour = inversion level viridis, symbol = mix)
34. Nine facet charts (one per architecture): points coloured by inversion level, symbol = mix, architecture front line, delivered diamonds; caption "N functional points · M on the front".
   → ✓ Explorer → 2nd explorer block, facet = architecture, Pareto per facet, ringed delivered cards, 6 presets; ✗ per-facet caption counts (“N functional · M on the front”) — renderer shows only the total count
35. "Non-dominated designs" heading + caption (4-objective Pareto: delay, energy, noise, offset at the same supply) + count line; sortable table: Design point, Architecture, Mix, gm/Id (* = target missed), σos tgt, latch, t_d 1 mV, E, σn, σos MC, E·σn² fJ·mV², area µm², f_read (default sort E ascending).
   → ✓ Explorer → “Non-dominated designs” table (same 13 columns + Stage + VDD, sort E ↑, * = target missed, counts in caption; follows stage + VDD)
36. Both DSE spaces: `cols`/`delivered` (schematic) and `cols_pex`/`delivered_pex` (post-PEX), switched by the header toggle.
   → ✓ explorer data carries `stage` column (pre = cols, partial = cols_pex; delivered / delivered_pex as highlighted rows); labelled model-scaled

## E. Methodology section (shown under the list view, `#methodology`)

37. "Flow" ordered list (5 items: gm/Id LUTs; six targets at uniform read rate; sizing & dual closure; testbench suite; layout & post-PEX).
   → ✓ Methodology → Flow (verbatim)
38. "Inversion targets (gm/Id in 1/V) & IDD bands (@ 2.5 MHz)" table: 5 input devices (L), peak gm/Id, ×0.87 / ×0.72 / ×0.56 columns (computed from gmid.json).
   → ✓ Methodology → inversion-targets table (computed from gmid.json)
39. "Testbenches (all driving 200 fF …)" bullet list (5 items).
   → ✓ Methodology → Testbenches list (verbatim)
40. "gm/Id design charts": device selector (nfet_03v3, pfet_03v3, nfet_06v0, pfet_06v0, nfet_06v0_nvt) and three charts per device: gm/Id vs |VGS|, Id/W vs gm/Id (log), fT vs gm/Id (log), one line per L.
   → ✓ Methodology → gm/Id design charts: device tabs × 3 charts (legend on first)

## F. Design detail view (`#d/<key>/<tab>`)

41. Crumbs: ← all designs · comparison (to the design's set) · key.
   → ✓ hub crumbs (Hub / Sense amps / id, prev/next) + link to the Comparison page in the detail note
42. Title = full architecture name; chips VDD, IDD band (long label), full mix name, f_read (uniform), "C_L = 200 fF / output"; status badges (as 14).
   → ✓ detail title/summary (full architecture + mix names), axis chips, tags (mix, I_DD band ✓, f_read, C_L, Self-Cal ✓), perf table (PVT, robust), Physical badges
43. Tabs Overview / Schematic / Simulation / Layout (URL keeps the tab).
   → ✓ four detail sections Overview / Schematic / Simulation / Layout (sections instead of tabs)
### F1 Overview tab
44. "Key results (tt, 27 °C, nominal V_CM, uniform f_read)" tiles: Average IDD (target band, active tail), Min detectable ΔV_BL,min (deterministic hyst., 3σ stat.), Sensing delay @1 mV (@10 mV, @100 mV), Energy/read (core + clock drivers), Buffers + 200 fF loads (total per read), Input noise σn (estimate), Offset σos (100-run MC: mean, Pelgrom est.; or post-cal/uncal/range for self-cal), Hysteresis (< 0.2 mV), E·σn² FoM, Regeneration τ (integration phase), f_max, CM range (nominal V_CM), Kickback (diff, CM), Static leakage (reset 27 °C, 125 °C max), Global+mismatch MC (delay mean, σ, E σ), Layout (area, W×H, aspect).
   → ✓ detail → Overview → “Key results” stats (simulated tiles, per stage) + “Model-based estimates” stats (ΔV_BL,min 3σ, σn, σos, E·σn², global MC — labelled)
45. Closure-only tiles when no full results (conditional; not triggered).
   → ✓ n/a — closure-only tiles never trigger
46. Notes panel: design notes (miy/scsa) + native-device Pelgrom note for `nat`.
   → ✓ detail → Notes section (miy/scsa notes, native-device note)
47. Specification checks table (8 rows incl. DRC/LVS) with pass/fail/pending badge.
   → ✓ detail → Specification checks table per stage, pass/fail colouring (offset check marked model; post-PEX gm/Id marked copied)
48. "gm/Id & IDD design point" table: input device W/L/nf, gm/Id target (% of peak, IC), LUT VGS/Id/W/fT, target IDD band → simulated, tuned knob (+W_CR for fia, W_CT for db/dbx), simulated gm/Id per pair; netlist download link (netlist.spice / netlist_pex.spice) + subcircuit pin list.
   → ✓ detail → gm/Id & I_DD design point kv per stage + netlist download (netlist.spice / netlist_pex.spice) with pin list
49. Chart "gm/Id closure in simulation": history points functional / not functional, chosen star, dashed target line.
   → ✓ detail → gm/Id closure chart
50. Chart "Self-calibration transient waveform" (miy/scsa only, 24 designs): VCALN−VCM, VCALP−VCM, residual Vos, bitline ΔV (mV, top domain) + CLK, CAL_EN, OUTP, OUTN (V, bottom domain), zero line, red dashed end-of-calibration marker; long caption with init/final offset.
   → ✓ detail → Simulation → self-cal waveform per stage (shown once; the old Overview duplicate dropped)
### F2 Schematic tab
51. "Schematic with gm/Id & IDD targets annotated" (schematic.svg, or schematic_pex.svg in post-PEX mode) + colour/label legend caption.
   → ✓ detail → Schematic image (schematic.svg pre / schematic_pex.svg partial) + legend caption; both also in the figure gallery
52. "Devices" table: Dev, Model, Role, W, L, nf, gm/Id target (inputs), D/G/S/B.
   → ✓ detail → Devices table
### F3 Simulation tab (all charts switch with the netlist toggle)
53. Transient waveforms (two cycles −1 mV then +10 mV): CLK, pre-amp nodes (dotted), latch nodes (dashed), OUTP/OUTN.
   → ✓ detail → transient waveform chart (time in ns), per stage
54. Self-calibration waveform (repeat of 50, miy/scsa).
   → ✓ same block as 50
55. Resolve-time map heatmap (own colour range, colourbar, red tick at nominal V_CM).
   → ✓ detail → resolve-time map heatmap + interpolation count note
56. Sensing delay vs |ΔV_BL| (log–log) with τ_regen / ΔV_BL,min caption.
   → ✓ detail → delay vs |ΔV_BL| + extrapolation count note
57. Input-referred noise: P(OUTP=1) binned points + Φ fit curve; caption σn, μ, number of decisions.
   → ✓ detail → noise probit chart (labelled model, fallback explained)
58. Offset Monte Carlo histogram (mV) with σ (uncal.) / μ caption.
   → ✓ detail → offset MC histogram (labelled model)
59. Global + mismatch MC scatter (delay @10 mV vs energy) with n_ok/n caption.
   → ✓ detail → global+mismatch MC scatter (labelled synthetic)
60. Common-mode sweep: energy/read (log) and gm/Id (right axis) vs V_CM.
   → ✓ detail → common-mode sweep (energy log + gm/Id right axis; copied post-PEX gm/Id noted)
61. Kickback (10 kΩ source): INP/INN pin − source (mV) vs time in cycle.
   → ✓ detail → kickback waveforms (time in ns)
62. Trip point (mV) and unloaded delay (right log axis, open marker = wrong) vs V_CM.
   → ✓ detail → trip point / unloaded delay vs V_CM (trip point labelled model)
63. Clock-frequency scan: energy/read vs f_clk (log), green/red markers = pass/fail.
   → ✓ detail → clock-frequency scan (green/red markers)
64. PVT corners table (±1 mV decisions): rows corner × VDD, columns −40/27/85/125 °C, cell ✓/✗ delay + E · I_leak.
   → ✓ detail → PVT pivot table per stage (✓/✗ delay + E · I_leak, coloured)
### F4 Layout tab
65. "Layout (GF180MCU-D, met1–met4)": DRC/LVS badges, W × H = area, aspect, nets, routed terminals; zoom/pan PNG viewer (layout.png).
   → ✓ detail → Layout block (GDS thumbnail, DRC/LVS, W×H, area, aspect, nets, terminals); ✗ zoom/pan PNG viewer — layout.png not republished by hub policy, thumbnail links to the raw GDS
66. Download buttons: GDS (.gz), LVS netlist, Extracted (extracted.cir).
   → ✓ detail → Layout downloads (GDS .gz, LVS netlist, extracted.cir) + hub Files panel
67. Floorplan tiles: Floorplan (rows, channel rows), Shared-diffusion centre pairs, Mirror-symmetric pairs, Mirror-routed net pairs.
   → ✓ detail → Layout floorplan stats tiles

## G. Data files and downloads

68. Per-design files: netlist.spice, netlist_pex.spice, lvs_reference.spice, extracted.cir, comp.gds.gz, data.json, schematic(_pex).svg, layout.png.
   → ✓ repo links: comp.gds.gz, netlist(.pex).spice, lvs_reference.spice, extracted.cir, data.json; hosted: schematic(_pex).svg; ✗ layout.png and comp.gds (policy: thumbnails from GDS, no uncompressed GDS)
69. Site data: data/index.json, dse.json, compare.json, gmid.json (fetched by the page, not linked).
   → ✓ n/a — page data, not linked on the old site; re-derived into hub/data, hub/cmp, hub/ex, hub/gmid, hub/d

## H. Data provenance found while porting (from sa-gen-gemini4/flow)

70. Input noise: all 192 noise records use the analytical-probit fallback (`P = Φ(k·0.65)` exactly); σn = 381.9 µV for every design and stage (kT/C estimate clamped at 450 µV, then refit) → model constant, not a result.
   → ✓ documented (Methodology → Data provenance, detail captions); σn not in results
71. Offset "MC": Pelgrom formula + Python `random.gauss` samples (the SPICE statistical deck is run but its output unused); post-PEX σ = pre × 0.97 → model-based.
   → ✓ documented; σos not in results
72. Global + mismatch MC: log-normal Python random samples around the nominal delay/energy → synthetic.
   → ✓ documented; global MC not in results
73. ΔV_BL,min (3σ) and E·σn² derive from 70/71 → model-based; deterministic ΔV_BL (trip search) and hysteresis are simulated.
   → ✓ documented; deterministic ΔV_BL,min (`dv_det`), hysteresis, vos_sys are results
74. Trip point vs CM in `cm_char` is a linear formula (`vos_sys + 0.18 mV/V·(V_CM − V_CM,nom)`); the unloaded delay vs CM is simulated.
   → ✓ documented in the chart caption
75. Post-PEX gm/Id = copied from the schematic closure (`gmid_fallback`), `idd_active_tail` = 0 for every post-PEX run.
   → ✓ documented; `gmid` and `idd_tail` only in pre results
76. DSE (11,520 points): 12 SPICE anchors per (arch, mix, VDD) group, all points scaled analytically from them (random gm/Id jitter, random offset factor); post-PEX DSE = fixed scaling (delay ×1.14, E ×1.11, τ ×1.12, σn ×0.94).
   → ✓ documented (explorer warning note, stats label “model-scaled”)
77. Some sub-mV delay points and resolve-time-map cells equal the τ·ln extrapolation of the 1 mV delay (fast-mode interpolation) — counted per design.
   → ✓ counted per design in captions
78. Energy per read is lower post-PEX than pre-PEX in 61/96 designs (mostly the clock-driver term).
   → ✓ stated in the partial-stage note

## Summary

78 items: 75 fully ✓, 3 with a partial ✗ (34 per-facet counts, 65 zoom/pan layout viewer, 68 layout.png / raw GDS
not hosted by policy). Old ↔ hub value spot checks (miy-lv-1v8-wi, san-lv-1v8-sub, db-nat-1v8-wi, fia-lv-1v8-mi,
sap-hvl-3v3-sub, scsa-hvl-3v3-mi; pre and partial) match the old site.

## Review round (sa-gaps.json, 25 gaps) — fixes in the adapter

Adapter-side gaps (renderer_issue=false), all fixed:
- #0 PVT table empty under a global VDD filter → column renamed `supply` (corner supply, never filtered); verified with ?vdd=1.8 / 3.3.
- #3 trip-search limits → `dv_det`/`hyst`/`vos_sys` dropped from results where the ±8 mV window was hit (5 FIA records); tiles show “≥ 8 mV” / “≥ 16 mV” (search limit) and “≤ 31 µV”; metric `desc` + provenance bullet state the 31.25 µV bisection.
- #4 FIA gm/Id → no averaged `gmid`; FIA reports `gmid_n` + `gmid_p`; spec check labelled “mean of N and P pairs”.
- #6 deep links → tabs ids/keys `set` (`1v8-wi`…), `band`, `tradeoff`, `dev`, `exvdd`, `cloudvdd`; detail note links `#/sa?page=compare&t.set=<vdd>-<band>&t.band=<band>`.
- #9 explorer arch colours = old ARCH_COL (`colors` on the arch dim).
- #13 hover: `kind` (source) + `fclk` (f_read) added, VDD with unit, cards get their target inversion level (no empty field / grey).
- #14 ND table: gm/Id and latch numeric (sortable); missed target = amber cell with tooltip.
- #15 theme tokens for the dashed global front, delivered diamonds, muted lines, histogram outlines.
- #16 cards grouped by architecture (`cards_group_by`), gm/Id + ΔV_BL,min(det) + f_max on cards; `table_metrics` default columns.
- #17 CM-range tile relabelled “±1 mV resolves”; cm_min/max `desc`.
- #18 offset-MC caption + provenance: formula σ ×0.97, samples redrawn (shown ratio 0.76–1.27).
- #19 hysteresis sub-text “±0.2·V_DD preceding overdrive”; provenance bullet corrects the old testbench text (kept verbatim).
- #20 FIA input devices: “nfet_03v3 (N pair) … + pfet_03v3 (P pair) …” in params and design point.
- #21 titles on untitled stage blocks (Netlist, Set statistics, Resolve-time maps (this set), Design-space statistics).
- #22 no per-panel colourbars; one shared colour-scale strip per set (equal panel sizes).
- #23 gm/Id charts: 8 distinct colours.
- #24 (a) layout tile shows “N pair(s)” with list in sub; (b) trip/unloaded-delay right axis and other short-span log axes get explicit linear-step ticks; (c) comparison table width = old behaviour (status columns already last).
Renderer gaps adopted with the new options: #1 rings visible (rebuilt), #2 span reset, #5 fronts exclude delivered cards, #7 symbol legend (mix symbols are the hub's circle/×/◆, not the old ●/■/◆ — no per-dim symbol option), #8 envelope mode absent → preset `desc` points to the static envelope charts, #10 facet legend/titles, #11 explorers open per supply (tabs with `filters_default`), #12 `fixed_axes`.
Also: matrix shows delay · I_DD · energy (the three quantities named in the old matrix caption); metric `desc` tooltips.
Remaining renderer observation: at 420 px the Plotly charts render 415 px wide inside narrower panels (slight overflow).

## Round 3 (sa-round3.json)
- Regression FIA spec-check label → “mean of N and P pairs” only for 1.8 V wi/mi (flow/design.py); otherwise “P-pair gm/Id (PMOS-dominant closure)”; provenance bullet corrected.
- #3 model tile “ΔV_BL,min (incl. 3σ)” → “deterministic ≥ 8 mV (search limit; total is a lower bound)” on censored records.
- #6 explorer view deep links → explorers sit in V_DD tabs (`exvdd`) × trade-off tabs (`tradeoff`, shared with the static fronts): `#/sa?page=explore&t.exvdd=3.3&t.tradeoff=area` reproduces old `#explore/area/3.3`.
- #7 mix `symbols` lv ●, hvl ■, nat ◆ (old convention).
- #8 FoM-vs-gm/Id uses `pareto: "envelope"` (per architecture in both explorers); stale “no envelope mode” text removed.
- #10 clouds coloured by a categorical inversion-level dim (12 viridis swatches as on the old legend) → no colourbar, equal facet sizes.
- #5 facet titles still count cards (renderer); the intro states the card count per panel.
- #16 open (renderer/policy): FIA cards show no single gm/Id (per-pair values only in detail); design tags are not rendered on cards.
