.DEFAULT_GOAL := help

.PHONY: help install sync update lint format format-check docs-check \
	docblocks-check comments-check line-length-check syntax-check types \
	python-standards typecheck architecture-check public-api-check agents-check lock-check \
	workflows-check yaml-check unit-test integration-test feature-test \
	regression-test concurrency-test security-test compatibility-test test \
	coverage audit license-check security benchmark stress-test build \
	docs-build docker-check check ci fix clean hooks hooks-check serve docs \
	docker-up docker-down

PYTEST := uv run --locked pytest
DIFF_COVER_BASE ?= HEAD
BUILD_OUTPUT_DIR ?= dist
ifeq ($(COVERAGE),collect)
PYTEST += --cov=titanspan --cov-branch --cov-append --cov-fail-under=0
endif

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

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

docs-check: ## Verify multiline Python docstrings without changing files
	uv run --locked python scripts/check_python_standards.py --docblocks-only

docblocks-check: docs-check ## Alias for the Python docblock check

comments-check: ## Verify rationale comments at high-risk operations
	uv run --locked python -m scripts.ci.check_comments

line-length-check: ## Enforce the strict 80-column Python source limit
	uv run --locked python scripts/check_python_standards.py \
		--line-length-only

syntax-check: ## Parse maintained Python files without importing them
	uv run --locked python scripts/check_python_standards.py --syntax-only

python-standards: docs-check line-length-check syntax-check ## Check all Python source standards

yaml-check: ## Validate YAML syntax, indentation, and repository style
	uv run --locked yamllint --strict .

types: ## Run strict Pyright over code, tests, and examples
	uv run --locked pyright

typecheck: types ## Alias for strict Pyright verification

architecture-check: ## Enforce implemented module dependency direction
	uv run --locked lint-imports

public-api-check: ## Verify the supported package import surface
	mkdir -p test-results
	$(PYTEST) tests/unit/test_public_api.py -m unit \
		--junitxml=test-results/public-api.xml -q

agents-check: ## Validate agent policy and package boundaries
	uv run --locked python scripts/check_agent_configs.py

lock-check: ## Confirm uv.lock matches project dependency declarations
	uv lock --check

workflows-check: ## Validate Actions syntax, pins, permissions, and graph
	uv run --locked python -m scripts.ci.check_workflow_policy
	uv run --locked python -m scripts.ci.actionlint

unit-test: ## Run isolated unit tests outside specialized categories
	mkdir -p test-results
	$(PYTEST) tests/unit \
		--ignore=tests/unit/support \
		--ignore=tests/unit/logging \
		--ignore=tests/unit/test_public_api.py \
		-m "unit and not feature and not regression and not security and not concurrency" \
		--junitxml=test-results/unit.xml -q

integration-test: ## Run real dependency integration tests
	mkdir -p test-results
	$(PYTEST) tests/integration \
		-m "integration and not feature and not regression and not security and not concurrency" \
		--junitxml=test-results/integration.xml -q

feature-test: ## Run complete user-facing feature tests
	mkdir -p test-results
	$(PYTEST) tests -m feature \
		--junitxml=test-results/feature.xml -q

regression-test: ## Run focused regression tests
	mkdir -p test-results
	$(PYTEST) tests -m regression \
		--junitxml=test-results/regression.xml -q

concurrency-test: ## Run concurrency isolation and lifecycle tests
	mkdir -p test-results
	$(PYTEST) tests -m concurrency \
		--junitxml=test-results/concurrency.xml -q

security-test: ## Run security behavior tests
	mkdir -p test-results
	$(PYTEST) tests -m security \
		--junitxml=test-results/security.xml -q

compatibility-test: ## Run Laravel-inspired Support and logging contracts
	mkdir -p test-results
	$(PYTEST) tests/unit/support tests/unit/logging \
		-m "unit and not regression and not security and not concurrency" \
		--junitxml=test-results/compatibility.xml -q

test: ## Run every collected test exactly once
	$(PYTEST) -q

coverage: ## Enforce independent 95% line and 90% branch coverage
	$(PYTEST) -q --cov=titanspan --cov-branch \
		--cov-fail-under=0 \
		--cov-report=term-missing --cov-report=json:coverage.json \
		--cov-report=xml:coverage.xml
	# The policy validator enforces line and branch thresholds separately;
	# Coverage.py's combined score has a different denominator.
	uv run --locked python scripts/check_coverage.py coverage.json
	uv run --locked diff-cover coverage.xml \
		--compare-branch="$(DIFF_COVER_BASE)" \
		--include "src/titanspan/**" --include-untracked --fail-under=95

audit: ## Audit locked runtime, optional, and development dependencies
	mkdir -p .cache/ci
	uv export --locked --all-groups --all-extras --no-emit-project \
		--format requirements.txt \
		--output-file .cache/ci/audit-requirements.txt >/dev/null
	uv run --locked pip-audit --strict --disable-pip --require-hashes \
		--requirement .cache/ci/audit-requirements.txt

license-check: ## Audit installed dependency license metadata
	uv run --locked python -m scripts.ci.check_licenses

secrets-check: ## Scan tracked files against the reviewed secret baseline
	uv run --locked pre-commit run detect-secrets --all-files

security: ## Run dependency, license, and secret checks
	$(MAKE) audit
	$(MAKE) license-check
	$(MAKE) secrets-check

benchmark: ## Run informational benchmarks without timing thresholds
	mkdir -p benchmark-results
	uv run --locked pytest benchmarks --benchmark-only -m benchmark \
		--benchmark-json=benchmark-results/results.json
	uv run --locked python -m scripts.ci.benchmark_metadata \
		benchmark-results/results.json

stress-test: ## Run lifecycle and high-volume stress tests
	mkdir -p test-results
	uv run --locked pytest tests/stress -m stress \
		--junitxml=test-results/stress.xml -q
	uv run --locked python -m scripts.ci.summarize_junit \
		test-results/stress.xml

build: ## Build and validate wheel and source distributions
	uv build --no-sources --out-dir "$(BUILD_OUTPUT_DIR)"
	uv run --locked twine check --strict "$(BUILD_OUTPUT_DIR)"/*
	uv run --locked python -m scripts.ci.check_distributions \
		"$(BUILD_OUTPUT_DIR)"
	uv run --locked python scripts/check_agent_configs.py --wheel \
		"$(BUILD_OUTPUT_DIR)"/*.whl

docs-build: ## Build and validate the VitePress documentation site
	npm ci --ignore-scripts --prefix docs --cache .cache/npm
	npm --prefix docs run docs:build

docker-check: ## Smoke-test isolated Compose services and the non-root image
	@set -eu; \
	project="titanspan-ci-$$$$"; \
	tag="titanspan-ci:check-$$$$"; \
	mkdir -p test-results; \
	cleanup() { \
		status=$$?; \
		if [ "$$status" -ne 0 ]; then \
			POSTGRES_HOST_PORT=0 REDIS_HOST_PORT=0 \
				docker compose --project-name "$$project" logs \
					--no-color > test-results/docker-compose.log 2>&1 \
				|| true; \
		fi; \
		POSTGRES_HOST_PORT=0 REDIS_HOST_PORT=0 \
			docker compose --project-name "$$project" down \
				--volumes --remove-orphans >/dev/null 2>&1 || true; \
		docker image rm "$$tag" >/dev/null 2>&1 || true; \
		trap - EXIT; \
		exit "$$status"; \
	}; \
	trap cleanup EXIT; \
	export POSTGRES_HOST_PORT=0 REDIS_HOST_PORT=0; \
	docker compose --project-name "$$project" config --quiet; \
	docker compose --project-name "$$project" \
		--profile database --profile cache \
		up --detach --wait --wait-timeout 120 postgres redis; \
	docker compose --project-name "$$project" exec -T postgres \
		pg_isready -U titanspan -d titanspan; \
	docker compose --project-name "$$project" exec -T redis \
		redis-cli ping; \
	docker build --tag "$$tag" .; \
	docker run --rm --entrypoint titanspan "$$tag" --help; \
	docker run --rm --entrypoint titanspan "$$tag" --version

check: lint format-check python-standards comments-check types \
	architecture-check public-api-check agents-check lock-check \
	workflows-check yaml-check coverage ## Run the read-only local quality gate

ci: check security docs-build build docker-check hooks-check ## Run all CI-equivalent checks without duplicating tests

fix: ## Apply safe Ruff lint fixes and formatting
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

clean: ## Remove only generated build, test, and type-check artifacts
	rm -rf build dist .coverage .coverage.* coverage.xml coverage.json \
		test-results .pytest_cache .ruff_cache .pyright htmlcov

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
