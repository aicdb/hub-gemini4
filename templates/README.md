# `<repo>` — GF180MCU-D <component> generator

<!-- Skeleton for generator READMEs (REPO_STANDARD.md §7). Keep the section order and the
     shared text of "Quick start", "Design points" and "Publishing to the hub"; replace <…>.
     Do not write counts of registered points here — `make points` lists them. -->

<One paragraph: what the generator produces, the flow (sizing → simulation → layout →
DRC/LVS → PEX → post-layout simulation), and where the results are shown.>

Results are published on the AICDB hub: <https://aicdb.github.io/hub-gemini4/#/<id>>.
The repository follows the [AICDB generator standard](https://github.com/aicdb/hub-gemini4/blob/main/REPO_STANDARD.md).

## Overview

<The design space: fields of a design point, architectures/topologies, supplies, targets.
What is simulated and verified for each point.>

## Repository layout

```
README.md            this file
AGENTS.md            instructions for coding agents
Makefile             the uniform command interface (make help)
points.json          the design-point registry (what is delivered)
<pkg>/               the generator package
  registry.py        reads points.json (shared template)
scripts/
  points.py          add / remove / list / check design points (shared template)
  points_hook.py     id and validation rules of this repository
  build.py           runs the pipeline for selected points
hub/
  export.py          writes the hub export from docs/ + points.json
  content/           prose shown on the hub
  INVENTORY.md       what the retired website showed and where it is on the hub
docs/                published data (read by the hub)
build/               intermediate outputs (git-ignored)
.github/workflows/hub-check.yml   checks the registry and the hub export on every push
```

## Quick start

Requirements: Python <3.x> or newer. The registry commands, `make docs` and `make hub` use the
standard library only; the full pipeline also needs <container / compute farm / tools>.

```bash
make help                                    # list the commands
make points                                  # list the registered design points
make check                                   # registry ↔ docs/ consistency
make build POINT=<id> BUILD_ARGS=--dry-run   # show what rebuilding one point would run
make docs                                    # regenerate docs/ from the build outputs
make hub                                     # write docs/hub/ and validate it (HUB=../hub-gemini4)
make preview                                 # local hub on http://127.0.0.1:8000
```

## Design points

`points.json` lists every delivered design point; the pipeline builds exactly these and the hub
publishes exactly these. A point has these fields:

| field | values | meaning |
|---|---|---|
| `<field>` | <values> | <meaning> |

Ids are formed as `<id_format>`, e.g. `<example id>`.

Remove a point and add it back:

```bash
make remove POINT=<example id> PURGE=1          # unregister it and delete its published files
make docs && make hub                           # republish without it
make add POINT="<field=value …>"                # register it again (the id is derived)
make build POINT=<example id>                   # run the pipeline for it
make hub && make preview                        # check it on the hub locally
git add points.json docs && git commit -m "<what changed>" && git push
```

A value that is not listed in `fields` (for example a new supply) needs generator support first;
then add the point with `python3 scripts/points.py add … --allow-new`. <Repository-specific rules,
e.g. combinations that are not allowed.>

## Pipeline stages

`make build POINT=<id>` runs these stages for the selected points (`BUILD_ARGS="--stages a,b"`
selects stages, `--force` redoes stages that are already done, `--dry-run` only prints the plan):

| stage | does | tools | outputs |
|---|---|---|---|
| `<stage>` | <…> | <…> | <…> |

## Publishing to the hub

```bash
make hub                                         # export + validate
git add points.json docs hub && git commit -m "<what changed>" && git push
gh workflow run publish.yml -R aicdb/hub-gemini4 # publish now (otherwise within 6 hours)
```

The hub's CI runs `hub/export.py` on `docs/`, `points.json` and `hub/` of the pushed commit;
`docs/hub/` is generated and not committed. Every push also runs
`.github/workflows/hub-check.yml` (registry check and export validation).

## Published data (`docs/`)

<What is under docs/data/ and docs/designs/<id>/ (and docs/subblocks/ if used), file by file.>
