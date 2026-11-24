.DEFAULT_GOAL := help

.PHONY: help install sync update lint format format-check types test coverage \
	check fix build clean hooks security serve docs docs-build \
	integration-test benchmark stress-test docker-up docker-down agents-check

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the locked project and all development tools
	uv sync --locked --all-groups

sync: ## Synchronize the environment from uv.lock
	uv sync --locked

update: ## Upgrade dependencies and rewrite uv.lock
	uv lock --upgrade

lint: ## Run Ruff lint checks
	uv run --locked ruff check .

format: ## Format Python source and tests
	uv run --locked ruff format .

format-check: ## Verify Python formatting without changing files
	uv run --locked ruff format --check .

types: ## Run strict Pyright type checking
	uv run --locked pyright

test: ## Run the test suite
	uv run --locked pytest -q

coverage: ## Run tests with the configured coverage threshold
	uv run --locked pytest --cov=titanspan --cov-report=term-missing --cov-report=xml:coverage.xml

agents-check: ## Validate repository-local AI agent configuration
	uv run --locked python scripts/check_agent_configs.py

check: lint format-check types coverage agents-check ## Run read-only quality checks

fix: ## Apply Ruff lint fixes and formatting
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

build: ## Build wheel and source distributions
	uv build --no-sources
	uv run --locked python scripts/check_agent_configs.py --wheel dist/titanspan-*.whl

clean: ## Remove generated build and test artifacts only
	rm -rf build dist .coverage coverage.xml .pytest_cache .ruff_cache .pyright htmlcov

hooks: ## Install the repository's pre-commit hooks
	uv run --locked pre-commit install --install-hooks

security: ## Audit the locked development environment for known vulnerabilities
	uv run --locked pip-audit --local

serve: ## Run the Hello World ASGI example locally
	uv run --locked uvicorn --app-dir examples/hello-world app:app --reload

docs: ## Start the VitePress development server
	npm --prefix docs run docs:dev -- --host 127.0.0.1

docs-build: ## Install locked documentation dependencies and build the site
	npm --prefix docs ci --ignore-scripts --cache .cache/npm
	npm --prefix docs run docs:build

integration-test: ## Run integration tests
	uv run --locked pytest tests/integration -q

benchmark: ## Run informational microbenchmarks
	uv run --locked pytest benchmarks --benchmark-only -m benchmark

stress-test: ## Run repeated lifecycle and stress tests
	uv run --locked pytest tests/stress -m stress -q

docker-up: ## Start local PostgreSQL and Redis services
	docker compose --profile database --profile cache up -d

docker-down: ## Stop local services without deleting named volumes
	docker compose down

