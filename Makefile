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

##### TARGETS #####
.PHONY: help install sync lock lint type arch validate harden hooks test integration cov docs docs-build build check ci clean

help:
	@printf "$(BOLD)$(CYAN)$(PROJECT)$(RESET) $(GRAY)· uv · ruff · ty · tach · pytest · zensical — run tracking for agent systems$(RESET)\n\n"
	@awk 'BEGIN{FS=":.*##"} /^[a-z][a-zA-Z0-9_-]*:.*##/{printf "  $(GREEN)%-12s$(RESET) $(GRAY)%s$(RESET)\n",$$1,$$2}' $(MAKEFILE_LIST)

# — env —
install: ## full setup: sync deps + git hooks
	@uv sync
	@uv run prek install
	@printf "$(GREEN)✓ ready$(RESET)\n"

sync: ## sync all deps (main + dev)
	@uv sync

lock: ## refresh uv lockfile
	@uv lock

# — gates —
lint: ## ruff check + format
	@uv run ruff check --fix $(PACKAGE) tests $(wildcard scripts)
	@uv run ruff format $(PACKAGE) tests $(wildcard scripts)

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

integration: ## real services: session fixtures bring sandbox/compose.yml up (collector + Phoenix) and down; needs docker
	@uv run pytest tests -m integration -q -p no:randomly

cov: ## run tests with coverage gate (fail under 100%), benchmarks out like the CI matrix
	@uv run pytest tests $(TESTARGS) --cov --cov-report=term-missing

# — docs —
docs: ## serve docs site live at :8000
	@uv run zensical serve

docs-build: ## strict docs build to site/
	@uv run zensical build --strict

# — release —
build: ## sdist + wheel into dist/, then import the wheel in a clean env (what the release job runs)
	@rm -rf dist && uv build -q
	@uv run --isolated --no-project --with "$$(ls dist/*.whl)[all]" python -I -c "import etrack.logic.api, etrack.providers.drivers.sink.otlp, etrack.providers.adapters.source.langgraph, etrack.processors.layout; print('wheel ok')"

# — aggregate —
check: lint type arch validate test ## fast local gate: lint + type + arch + validate + test
ci: lint type arch validate harden docs-build cov integration build ## full pipeline: every gate CI runs, in one command

clean: ## remove caches + build artifacts
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true
	@rm -rf dist build *.egg-info .coverage .coverage.* .ty_cache site
	@printf "$(GREEN)✓ clean$(RESET)\n"

%:
	@:
