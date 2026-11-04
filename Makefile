##### CONFIG #####
PROJECT ?= e-track
PACKAGE ?= src/etrack
ARGS     = $(filter-out $@,$(MAKECMDGOALS))

RESET   := \033[0m
BOLD    := \033[1m
GREEN   := \033[0;32m
CYAN    := \033[0;36m
GRAY    := \033[0;90m

SHELL := bash

TESTARGS  ?= -m "not slow and not integration"   ## wall-clock benchmarks and real-service tests leave the gate: make test TESTARGS="-m slow", make integration
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory
export PYTHONPATH := $(CURDIR)/src
UI      := src/etrack/ui

##### TARGETS #####
.PHONY: help install sync lock lint type arch validate harden hooks test integration cov docs docs-serve ui ui-check ui-types build check ci clean

help:
	@printf "$(BOLD)$(CYAN)$(PROJECT)$(RESET) $(GRAY)· uv · ruff · ty · tach · pytest · zensical — run tracking for agent systems$(RESET)\n\n"
	@awk 'BEGIN{FS=":.*##"} /^[a-z][a-zA-Z0-9_-]*:.*##/{printf "  $(GREEN)%-12s$(RESET) $(GRAY)%s$(RESET)\n",$$1,$$2}' $(MAKEFILE_LIST)

# — env —
install: ## full setup: sync deps + canvas deps + git hooks
	@uv sync
	@pnpm -C $(UI) install --frozen-lockfile
	@uv run prek install
	@printf "$(GREEN)✓ ready$(RESET)\n"

sync: ## sync all deps (main + dev)
	@uv sync

lock: ## refresh uv lockfile
	@uv lock

# — gates —
lint: ## ruff check + format
	@uv run ruff check --fix $(PACKAGE) tests
	@uv run ruff format $(PACKAGE) tests

type: ## ty type check
	@uv run ty check

arch: ## enforce import architecture (tach)
	@uv run tach check

validate: ## validate pyproject.toml against schema
	@uv run validate-pyproject pyproject.toml

harden: ## zizmor audit of GitHub Actions workflows
	@uv run zizmor --persona=regular .github/workflows

hooks: ## run all prek hooks on every file (ruff, ty, tach, zizmor, gitleaks)
	@uv run prek run --all-files

# — tests —
test: ## run tests, benchmarks out by default [TESTARGS='-k expr']
	@uv run pytest tests $(TESTARGS) -n auto -q

integration: ui ## real services: tests/sandbox up and down (collector + Phoenix), the viewer end to end in chromium; needs docker
	@uv run playwright install chromium
	@uv run pytest tests -m integration -q -p no:randomly

cov: ## run tests with coverage gate (fail under 100%), benchmarks out like the CI matrix
	@uv run pytest tests $(TESTARGS) --cov --cov-report=term-missing

# — docs —
docs: ## strict docs build to site/ — fails on broken links or missing assets (the fleet's docs module runs this)
	@uv run zensical build --strict --clean

docs-serve: ## serve the docs site live at 127.0.0.1:8000
	@uv run zensical serve -a 127.0.0.1:8000

# — canvas —
ui: ## build the viewer's canvas into src/etrack/ui/dist — the static page the viewer serves at /
	@pnpm -C $(UI) build

ui-check: ## biome + tsc on the canvas, and its TypeScript types still those of the API's wire contract
	@pnpm -C $(UI) check
	@$(MAKE) ui-types
	@git diff --exit-code -- $(UI)/schema.json $(UI)/src/contract.ts

ui-types: ## regenerate the canvas's types from msgspec's JSON Schema of the API (ui/schema.json → src/contract.ts)
	@uv run python -c 'import msgspec, pathlib; from etrack.api.viewer import DIST, ViewerApi; (DIST.parent / "schema.json").write_bytes(msgspec.json.format(msgspec.json.encode(ViewerApi.schema()), indent=2) + b"\n")'
	@pnpm -C $(UI) types

# — release —
build: ui ## canvas, then sdist + wheel into dist/, then import the wheel in a clean env (what the release job runs)
	@rm -rf dist && uv build -q
	@uv run --isolated --no-project --with "$$(ls dist/*.whl)[all]" python -I -c "import etrack.logic.api, etrack.logic.viewer, etrack.providers.adapters.server.granian, etrack.providers.drivers.sink.otlp, etrack.providers.adapters.source.langgraph, etrack.api.viewer as v; assert (v.DIST / 'index.html').is_file(), 'canvas missing from the wheel'; print('wheel ok, canvas in')"

# — aggregate —
check: lint type arch validate test ## fast local gate: lint + type + arch + validate + test
ci: lint type arch validate harden ui-check docs cov integration build ## full pipeline: every gate CI runs, in one command

clean: ## remove caches + build artifacts
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true
	@rm -rf dist build *.egg-info .coverage .coverage.* .ty_cache site
	@printf "$(GREEN)✓ clean$(RESET)\n"

%:
	@:
