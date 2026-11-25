# Titanspan Agent Instructions

This is the canonical repository-wide instruction file for AI coding agents.
Read it before work, then consult the relevant scoped `AGENTS.md`,
`ARCHITECTURE.md`, `ROADMAP.md`, `CONTRIBUTING.md`, `SECURITY.md`, ADRs, and
development standards. This file is also the source of truth for harness
adapters. Do not maintain a competing copy of these rules.

## Project identity and status

Titanspan is an open-source, async-first Python application framework for
building intelligent systems at scale. It combines Laravel-inspired
developer experience with asynchronous web development, stateful AI workflow
orchestration, agents and tools, structured concurrency, CPU parallelism,
distributed execution, and streaming data processing.

The framework owns expressive APIs, conventions, lifecycle, integration
coordination, and testing support. Mature libraries own their underlying
infrastructure. The package is early-stage: verify implementation and tests
before describing any feature as available. The `ROADMAP.md` is not an API
specification.

## Before meaningful changes

1. Inspect `git status`, the relevant files, tests, and existing conventions.
   Preserve user changes and avoid unrelated edits.
2. Read the applicable scoped instructions and architecture documents.
3. Verify unfamiliar or version-sensitive third-party APIs against official
   documentation and the installed package version.
4. For non-trivial work, state scope, affected modules, behavior, architecture
   impact, tests, risks, and acceptance criteria before implementing.
5. Use test-driven development for meaningful behavior: add a focused failing
   regression test, verify it fails for the intended reason, then implement.
6. Review the final diff and report only checks actually run.

Use [the agent workflow](docs/development/agent-workflow.md) and
[engineering standards](docs/development/standards.md) for details.

## Architecture and library choices

Respect accepted ADRs and the current implementation. Preferred foundations
are FastAPI/Starlette for web, Dishka for dependency resolution, SQLAlchemy
and Alembic for persistence/migrations, Pydantic and Pydantic Settings for
validation/configuration, LangGraph for graph execution, LangChain for AI
integrations, AnyIO for async concurrency, process pools or native libraries
for CPU parallelism, Taskiq for distributed jobs, Blinker for events, Cashews
for caching, Structlog for logging, fsspec for filesystem adapters, HTTPX for
HTTP, Polars and Apache Arrow for data, APScheduler for scheduling, OpenTelemetry
for telemetry, Typer and Rich for the CLI, and Pytest for testing.

These are architecture choices, not a reason to install every package. Do not
add unused or duplicate dependencies. Do not replace an accepted dependency
or architectural decision without verified evidence, a focused proposal, and
an ADR when the change is significant.

- Prefer mature libraries; keep Titanspan wrappers thin, typed, and useful.
- Preserve access to the underlying library APIs and identify delegated
  behavior transparently in code and documentation.
- Use composition and protocols where they establish a real contract or test
  seam. Avoid speculative abstractions, deep inheritance, and metaprogramming.
- Keep core modules independent of optional AI, database, queue, and
  infrastructure adapters. Prevent circular dependencies.
- Put shared, dependency-independent protocols in `titanspan.contracts` only
  when they establish a real boundary. Preserve existing module-owned contract
  identities, especially `titanspan.logging.contracts`; re-export canonical
  types instead of redeclaring them. Contracts do not imply implementations.
- Keep APIs idiomatic Python while using Laravel as a reference for
  conventions, lifecycle, and developer experience. Never translate PHP
  syntax mechanically.
- Use Titanspan domain-oriented filenames for public modules. For example,
  use `container/container.py`, not a vendor-named public file such as
  `container/dishka.py`. Be clear that an implementation delegates to Dishka;
  do not imply Titanspan reimplemented its internals.
- Preserve existing public APIs. Record major architectural changes in ADRs.

The current technology foundation is recorded in
[`ARCHITECTURE.md`](ARCHITECTURE.md) and
[`docs/architecture/decisions/`](docs/architecture/decisions/).

## Async, data, and resource safety

- Do not block the event loop. Offload blocking work appropriately.
- Prefer structured concurrency; give tasks an owner and propagate
  cancellation and timeouts.
- Bound concurrency, buffering, memory, connections, and retries. Use
  backpressure and incremental processing for large or ongoing workloads.
- Never use unbounded `asyncio.gather()` or one task per item for unbounded
  input.
- Distinguish async I/O from CPU parallelism. Use process-based or suitable
  native execution for CPU-bound workloads.
- Do not share mutable SQLAlchemy `AsyncSession` instances across concurrent
  tasks. Keep transaction boundaries explicit.
- Finalize resources on success, failure, cancellation, and shutdown. Make
  retry behavior safe for non-idempotent operations.
- Never claim scalability or performance from `async` syntax alone. Use
  reproducible evidence and record workload, platform, versions, concurrency,
  throughput, latency, and peak memory.

## Python and package standards

- Python 3.12+; UTF-8; LF; four-space indentation; strict 80-column maximum;
  PEP 8 naming; absolute imports; explicit public exports; no wildcard imports,
  dead code, commented-out implementations, or unexplained magic numbers.
- Use comprehensive annotations and explicit returns for production, tests,
  examples, benchmarks, and development scripts. Pyright must remain strict.
  Keep `Any`, unsafe casts, and type suppressions at narrow, documented
  third-party boundaries only.
- Every module, class, function, method, fixture, and test needs a physically
  multi-line Google-style docstring. Add meaningful implementation comments
  for non-obvious rationale, invariants, lifecycle, concurrency, security,
  and error recovery; comments must explain why, not restate code.
- Prefer `pathlib`, context managers, protocols, immutable values when
  appropriate, and explicit side effects.
- Avoid mutable defaults, wildcard imports, unexplained values, broad
  exception handling, unnecessary `Any`, blanket type ignores, and global
  mutable state.
- Use `uv` exclusively for Python dependencies, environments, locking,
  building, and publishing. Preserve `uv.lock`; update it through `uv lock`.
  Do not add Poetry, Pipenv, Conda, global installs, or unjustified packages.
- Use Red-Green-Refactor for every meaningful behavior change: write and run
  the focused failing test before implementation. Bug fixes need regression
  tests. Add unit and real integration coverage for implemented boundaries;
  test success, failures, cleanup, cancellation, isolation, concurrency, and
  validation as applicable.
- Enforce at least 95% statement and 90% branch coverage independently for
  `src/titanspan`. Never lower thresholds, weaken assertions, skip failing
  tests, disable quality policies, or add blanket lint/type suppressions to
  make a change pass. Meaningful comment quality receives human review.
- Keep development tooling and agent assets outside `src/titanspan/`, except
  scoped Markdown instructions where necessary. Confirm built distributions
  do not contain development-only instructions or agent configuration.

Use the existing Make targets and `uv run --locked` for tools. Required
commands include Ruff lint and format checks, strict `pyright`, source line
and docstring validation, import architecture checks, agent configuration
validation, and applicable unit and integration tests. `make check` is
read-only and mirrors required CI; it includes the independently enforced
coverage thresholds. `make ci` adds security, docs, packaging, and extended
validation. Do not claim an unavailable command exists.

## Protected engineering policies

Agents must not:

- Disable or weaken tests, coverage, strict typing, Ruff, security checks,
  hooks, CI, or architecture constraints to make a change pass.
- Lower the coverage threshold, add blanket exclusions or suppressions, or
  alter benchmarks to hide a regression.
- Present placeholders, TODOs, mocks, or planned work as complete behavior.
- Invent APIs, test results, benchmark results, dependency properties, or
  documentation evidence.
- Make unrelated refactors or add dependencies without justification.
- Change these instructions, quality policies, CI, or architectural
  constraints without a focused justification and independent review through
  the repository contribution process.
- Remove mandatory GitHub Actions jobs or omit them from the fail-closed
  `ci-gate`; make a required job best-effort; accept missing, skipped, or
  cancelled results; or fabricate a successful summary.
- Weaken workflow permissions, unpin external actions, suppress security
  findings, bypass hooks, or remove platform and integration checks to make
  a change pass.

CI policy changes need a focused rationale and maintainer review. Keep every
required check independently visible, preserve the exact gate inventory, and
verify workflow syntax and policy locally before changing remote rules.

## Security and repository safety

- Validate untrusted input; bind database parameters; authorize tools and
  tenant boundaries; avoid leaking secrets or private payloads in logs.
- Never commit credentials, private user data, or real `.env` files.
- Do not introduce paid services, commercial AI calls, or hosted
  infrastructure without explicit authorization.
- Do not install coding agents or automatically execute downloaded scripts.
- Preserve sandboxing and approval requirements. Do not add blanket
  permission bypasses, unrestricted shell/network settings, or executable
  agent hooks without an independently reviewed, justified need.
- Do not commit, push, publish, release, deploy, message third parties, or
  modify organization settings unless the current task explicitly authorizes
  that action.
- Never force-push, reset away user work, rewrite shared history, or bypass
  repository protections.

## Git and reporting

When commits are authorized, use small Conventional Commit messages and inspect
the diff first. Update public documentation and `CHANGELOG.md` when behavior or
public APIs change. Report what changed, why, checks run and results, remaining
limits, and risks. Never conceal failed or skipped checks.

## Canonical references

- [`ARCHITECTURE.md`](ARCHITECTURE.md): module boundaries and system design.
- [`ROADMAP.md`](ROADMAP.md): implementation order; planned work only.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): human contribution process.
- [`SECURITY.md`](SECURITY.md): vulnerability reporting and security policy.
- [`docs/development/standards.md`](docs/development/standards.md): detailed
  engineering requirements.
- [`docs/development/agent-workflow.md`](docs/development/agent-workflow.md):
  required agent workflow.
- [`docs/architecture/decisions/`](docs/architecture/decisions/): accepted
  and proposed architecture decisions.
- [`pyproject.toml`](pyproject.toml): executable Python tool configuration.
- [`Makefile`](Makefile): standard development commands.
