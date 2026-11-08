# Uniform generator interface (identical in every aicdb generator repository).
# Standard: https://github.com/aicdb/hub-gemini4/blob/main/REPO_STANDARD.md
PY    ?= python3
HUB   ?= ../hub-gemini4
POINT ?=

.DEFAULT_GOAL := help
.PHONY: help points add remove build docs hub preview check

help: ## show this help
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 10

points: ## list the design points in points.json
	$(PY) scripts/points.py list

add: ## add a design point:   make add POINT="field=value ..."
	$(PY) scripts/points.py add $(POINT)

remove: ## remove a design point:   make remove POINT=<id> [PURGE=1]
	$(PY) scripts/points.py remove $(POINT) $(if $(PURGE),--purge)

build: ## run the generator pipeline:   make build POINT=<id>  (all points without POINT; BUILD_ARGS="--dry-run")
	$(PY) scripts/build.py $(if $(POINT),--point $(POINT),--all) $(BUILD_ARGS)

docs: ## regenerate docs/ from existing build outputs for the registered points
	$(PY) scripts/build.py --docs-only $(BUILD_ARGS)

hub: ## write docs/hub/ and validate it against the hub contract (needs HUB=<hub checkout>)
	$(PY) hub/export.py --docs docs --out docs/hub
	$(PY) $(HUB)/tools/hubkit.py validate docs

preview: ## local hub preview of this repository on http://127.0.0.1:8000
	$(PY) $(HUB)/tools/hubkit.py preview docs

check: ## registry <-> docs consistency
	$(PY) scripts/points.py check
