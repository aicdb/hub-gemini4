# AICDB Analog Hub

One GitHub Pages site for every analog generator repo: **<https://aicdb.github.io/hub-gemini4/>**

- One tab per component type (switches, sense amps, level shifters, op-amps, aux blocks, LDOs,
  ECG AFEs, SAR ADCs, ΣΔ ADCs). Each tab has:
  - **Designs:** coverage matrix with a cell-metric selector, cards, and a sortable table
    with CSV export.
  - **Generator pages:** design-space explorers, methodology, comparisons and databases.
  - **A detail page per design** with every analysis section.
- A shared options bar applies to all tabs and pages: **technology**, **simulation stage**
  (pre-PEX / partial post-PEX / full post-PEX, with optional fallback to an earlier stage),
  **V<sub>DD</sub>**, **verification** (DRC+LVS / PVT-robust) and a search box that spans
  all components.
- The hub hosts only what it displays. Layouts are shown as thumbnails rendered from the GDS
  at build time; GDS files, netlists and evidence JSON link to the raw file in the
  **private** source repository, pinned to the exported commit.

## How it works

```
sources.json ──► publish.yml ──► sparse clone docs/ + hub/ of each source repo (HUB_SOURCES_TOKEN)
                                    │
                                    ▼
                     tools/hubkit.py build
                       • the repo's own hub/export.py (REPO_STANDARD.md), or a
                         committed docs/hub/component.json
                       • validate component, pages, design detail docs and all blocks
                       • copy only referenced (hosted) files to c/<id>/
                       • render GDS thumbnails (tools/gdsthumb.py, cached)
                       • web/ → site root, data/catalog.json, data/components/<id>.json
                                    │
                                    ▼
                             GitHub Pages deploy
```

Triggers: push to `main`, manual or `repository_dispatch` (`source-updated`), and a 6-hourly
schedule. The scheduled run skips the build if neither the hub nor any source repo changed.

The renderer for pages and detail docs is `web/assets/blocks.js`, which supports sections,
markdown, tables, Plotly charts, the design-space explorer, figures, layouts, downloads and
tabs. The full vocabulary is specified in [BUILDERS.md](BUILDERS.md).

## For repo builders

Read **[REPO_STANDARD.md](REPO_STANDARD.md)** (repository layout, design-point registry, `make`
interface) and **[BUILDERS.md](BUILDERS.md)** (export contract). In short: `make add` /
`make remove` / `make build` design points, `make hub` + `make preview` to check, push, then
`gh workflow run publish.yml -R aicdb/hub-gemini4`.

## Maintainer setup

1. **Secret `HUB_SOURCES_TOKEN`:** a fine-grained PAT with *Contents: read-only* on the
   `aicdb/*-gen-gemini4` repos (they are private). Set it with
   `gh secret set HUB_SOURCES_TOKEN -R aicdb/hub-gemini4`.
2. Settings → Pages → Source: **GitHub Actions** (already set).
3. **Adding a generator:** append it to `sources.json`. Add a technology label there too if
   it uses a new PDK.

## Local build

```bash
pip install gdstk pillow           # for layout thumbnails (cached in ~/.cache/aicdb-hub/thumbs)
# all sources checked out next to this repo (../opa-gen-gemini4, …)
python3 tools/hubkit.py build --root .. --out _site --serve 8000
```
