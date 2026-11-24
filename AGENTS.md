# Agent Guidance for Titanspan

This file is the durable project-specific instruction set for coding agents.
Read it together with `ARCHITECTURE.md`, `ROADMAP.md`, and the relevant ADRs.

## Before changing code

- Inspect the current checkout and `git status` first; preserve existing work.
- Read architecture documentation before major changes or new module
  boundaries.
- Preserve the project's modular, async-first direction and the decisions in
  accepted ADRs. Propose an ADR when a major decision changes.
- Use Laravel as an architectural and developer-experience reference, not as
  PHP syntax to translate. Preserve idiomatic Python conventions.
- Verify third-party APIs and compatibility against current official
  documentation before relying on them.

## Architecture

- Prefer mature libraries over recreating servers, dependency resolvers, ORM
  engines, queue systems, or graph runtimes.
- Keep abstractions thin and tied to a real public API, contract, lifecycle, or
  test seam. Avoid speculative frameworks inside the framework.
- Prefer composition, protocols, explicit providers, and replaceable adapters.
- Prevent circular dependencies. Keep optional AI, database, queue, and
  infrastructure adapters out of core module imports.
- Keep async I/O explicit, propagate cancellation, and do not block the event
  loop. Bound concurrency and memory use for large inputs.
- Preserve access to the underlying library APIs.
- Clearly label planned modules and do not advertise unimplemented behavior as
  supported functionality.

## Python quality

- Support Python 3.12 and later versions verified by CI.
- Use uv for Python dependency, environment, lock, build, and publish commands.
- Use four-space indentation, 80-column lines, explicit types, and meaningful
  docstrings for public APIs.
- Keep strict Pyright and Ruff checks enabled. Avoid unexplained `Any`, blanket
  ignores, broad exception handling, wildcard imports, blocking calls, and
  mutable defaults.
- Use timezone-aware datetimes and `pathlib` for filesystem paths.

## Tests and verification

- Follow test-driven development for meaningful behavior: write and run a
  failing test before implementation.
- Test success, failure, cleanup, scope isolation, cancellation, and concurrent
  behavior where they apply.
- Run `make check` after code changes and the relevant docs, build, security,
  integration, or platform checks for the files changed.
- Report only checks actually run. Never fabricate test, CI, build, benchmark,
  or coverage results.
- Never fabricate throughput or performance claims.
- Do not make the default test suite depend on paid services or live commercial
  AI APIs.

## Dependencies and public APIs

- Add dependencies only when the functionality needs them. Keep integrations
  optional unless the framework's core lifecycle depends on them.
- Verify maintenance status, Python support, async behavior, licensing, and
  known advisories before selecting a new dependency.
- Update `uv.lock` with `uv lock`; commit the lockfile with dependency changes.
- Preserve backward compatibility where applicable. Document public API
  changes in the README or relevant guide and `CHANGELOG.md`.
- Never remove a user's unrelated data or make unrelated edits.

## Security and operations

- Never commit credentials, private user data, or real `.env` files.
- Do not introduce paid services, paid GitHub features, or billable cloud or AI
  infrastructure without explicit authorization.
- Do not publish a package or release without explicit authorization.
- Do not force-push, rewrite shared history, or bypass a repository protection
  rule.
- Do not send messages to third parties without explicit authorization.

## Collaboration and commits

- Keep changes small and focused. Use meaningful Conventional Commit messages.
- Avoid generated placeholders and unrelated files.
- Before committing, inspect the diff and confirm that tests and documentation
  match the implemented behavior.

