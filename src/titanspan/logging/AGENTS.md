# Logging component instructions

Follow the root `AGENTS.md`, `ARCHITECTURE.md`,
`docs/development/standards.md`, and
`docs/architecture/decisions/0012-native-logging.md` before changing this
component. Consult `docs/compatibility/laravel-logging.md` for the pinned
Laravel API inventory and current gaps.

## Responsibility and dependencies

This module owns Titanspan logging records, levels, loggers, channels,
managers, configuration, drivers, formatter and processor contracts, events,
redaction, and test fakes. Keep public filenames and types Titanspan-oriented.
Direct Structlog and standard-library handler integration belongs under
`_backends/`; public signatures and ordinary examples must not require those
backend types.

The module may depend on Python's logging package, Structlog, AnyIO, native
Titanspan configuration, and the application lifecycle boundary. Do not make
logging depend on optional AI, database, workflow, queue, or storage modules.
Those modules can attach execution-local context through explicit integration
hooks when they exist. Do not create a competing event dispatcher, DI
container, formatter engine, or logging service registry.

## Lifecycle and safety

- Keep manager and channel ownership explicit. A stack coordinates children
  but does not own their drivers.
- Use `ContextVar` for execution-local context; never add global mutable log
  context or a global active manager.
- Redact before listeners, buffering, formatting, or transport.
- Bound queued records, retained diagnostics, serialized depth, text, and
  collection sizes.
- Preserve cancellation, surface delivery errors, and report queue acceptance
  separately from destination delivery.
- Do not block an event loop; use the existing async methods and AnyIO
  offloading boundary.
- Do not assume ordinary rotating file handlers are safe across processes.
- Do not log arbitrary object representations or automatically capture
  prompts, request bodies, workflow state, model output, or frame locals.

## Public API and tests

Expose both idiomatic snake_case and explicitly typed Laravel-compatible
camelCase aliases where supported. Keep each pair backed by one
implementation. Add unit tests for every behavior and real integration tests
for handlers, bridges, file operations, lifecycle, and network delivery. Add
deterministic concurrency tests for task isolation, queue bounds, cancellation,
and cleanup. Avoid external services in the default test suite.

Update the compatibility inventory, docs, and changelog for public behavior
changes. Run `uv run --locked ruff check .`,
`uv run --locked ruff format --check .`, `uv run --locked pyright`, the
logging unit and integration tests, and `make check`. Do not weaken coverage or
quality policies when a test exposes a defect.
