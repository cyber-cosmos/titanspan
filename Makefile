.DEFAULT_GOAL := help

.PHONY: help install sync update lint format format-check python-standards \
	types docs-check unit-test integration-test feature-test regression-test \
	security-test test coverage architecture-check agents-check secrets-check \
	security benchmark stress-test build lock-check yaml-check check ci fix clean \
	hooks hooks-check serve docs docs-build docker-up docker-down

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the locked package and development tools
	uv sync --locked --all-groups

sync: ## Synchronize the environment from uv.lock
	uv sync --locked

update: ## Upgrade dependencies and update uv.lock
	uv lock --upgrade

lint: ## Run strict Ruff lint checks
	uv run --locked ruff check .

format: ## Format maintained Python files with Ruff
	uv run --locked ruff format .

format-check: ## Verify Python formatting without changing files
	uv run --locked ruff format --check .

python-standards: ## Check strict source line and docstring requirements
	uv run --locked python scripts/check_python_standards.py

yaml-check: ## Validate YAML syntax, indentation, and repository style
	uv run --locked yamllint --strict .

lock-check: ## Confirm uv.lock matches the project configuration
	uv lock --check

types: ## Run strict Pyright over code, tests, and examples
	uv run --locked pyright

docs-check: ## Install locked docs tools and build VitePress
	npm ci --ignore-scripts --prefix docs --cache .cache/npm
	npm --prefix docs run docs:build

docs-build: docs-check ## Build the VitePress documentation site

unit-test: ## Run isolated unit tests
	uv run --locked pytest tests/unit -m unit -q

integration-test: ## Run real integration-boundary tests
	uv run --locked pytest tests/integration -m integration -q

feature-test: ## Run user-visible feature tests
	uv run --locked pytest -m feature -q

regression-test: ## Run regression tests
	uv run --locked pytest -m regression -q

security-test: ## Run security-focused tests
	uv run --locked pytest -m security -q

test: ## Run the complete Pytest suite
	uv run --locked pytest -q

coverage: ## Enforce independent 95% line and 90% branch coverage
	uv run --locked pytest -q --cov=titanspan --cov-branch \
		--cov-report=term-missing --cov-report=json:coverage.json \
		--cov-report=xml:coverage.xml
	uv run --locked python scripts/check_coverage.py coverage.json

architecture-check: ## Enforce implemented module dependency direction
	uv run --locked lint-imports

agents-check: ## Validate agent policy and wheel packaging rules
	uv run --locked python scripts/check_agent_configs.py

secrets-check: ## Scan tracked files against the reviewed secret baseline
	uv run --locked pre-commit run detect-secrets --all-files

security: ## Audit Python dependencies and scan for secrets
	uv run --locked pip-audit --local
	$(MAKE) secrets-check

benchmark: ## Run informational benchmarks without timing thresholds
	uv run --locked pytest benchmarks --benchmark-only -m benchmark

stress-test: ## Run lifecycle and high-volume stress tests
	uv run --locked pytest tests/stress -m stress -q

build: ## Build distributions and audit the wheel contents
	uv build --no-sources
	uv run --locked python scripts/check_agent_configs.py --wheel dist/titanspan-*.whl

check: lint format-check python-standards types architecture-check \
	yaml-check lock-check agents-check coverage ## Run the read-only quality gate

ci: check security-test security docs-check stress-test build hooks-check ## Run all required local CI checks

fix: ## Apply safe Ruff lint fixes and formatting
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

clean: ## Remove only generated build, test, and type-check artifacts
	rm -rf build dist .coverage .coverage.* coverage.xml coverage.json \
		.pytest_cache .ruff_cache .pyright htmlcov

hooks: ## Install repository pre-commit hooks
	uv run --locked pre-commit install --install-hooks

hooks-check: ## Run all configured hooks against tracked files
	uv run --locked pre-commit run --all-files

serve: ## Run the Hello World ASGI example locally
	uv run --locked uvicorn --app-dir examples/hello-world app:app --reload

docs: ## Start the VitePress documentation development server
	npm --prefix docs run docs:dev -- --host 127.0.0.1

docker-up: ## Start local PostgreSQL and Redis services
	docker compose --profile database --profile cache up -d

docker-down: ## Stop local services without deleting named volumes
	docker compose down
