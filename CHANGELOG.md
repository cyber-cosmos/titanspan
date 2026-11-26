# Changelog

Notable changes to Titanspan are recorded here. The project has not made a
public release.

## Unreleased

- Reject temporary overrides that would be hidden by application singletons,
  and keep application shutdown retryable while scopes or overrides are
  active. Configuration injection now reports missing and incompatible values
  through the existing typed configuration accessors. See
  `docs/specifications/container.md` for scope and override boundaries.
- Standardized pre-release public APIs on one Python `snake_case` spelling.
  Removed duplicate aliases, vendor-named protocol exports, and ignored
  string encoding and locale parameters. Empty iterable endpoints now return
  `None`, and configuration mapping deletion removes the path. See ADR 0016
  for the API policy.
- Corrected the native container to resolve sync-safe graphs synchronously and
  expose explicit async resolution methods for async factories and resources.
  Application-level synchronous and asynchronous resolution share Dishka's
  graph cache; sync and async scopes close their owned resources through their
  matching lifecycle. See ADR 0015 and `docs/specifications/container.md`.
- Added an incremental native asynchronous container API with typed bindings,
  application singletons, execution-scoped values, ordered tags, aliases,
  automatic concrete dependency discovery, bounded graph generations, and
  synchronous and asynchronous generator cleanup, callable injection, method
  callback bindings, and declarative class lifetime decorators. The container
  now supports consumer-specific bindings, `Annotated` injection, ordered
  service extensions, root-resolution callbacks, and task-local overrides
  with matching synchronous or asynchronous resource cleanup. Framework
  services resolve through the application container; FastAPI route injection
  remains a separate adapter. Registrations freeze after graph composition.
  See `docs/specifications/container.md` and `docs/container/`.
- Added the native configuration repository, strict typed accessors, trusted
  Python/JSON/TOML source loading, isolated dotenv integration, validated
  settings, application-scoped facade and native contract registration. Added
  secret-safe configuration inspection, atomic JSON caching, and config CLI
  commands. See `docs/config/` and `docs/specifications/config.md`.
- Projected explicitly supplied custom settings fields into configuration
  paths, preserving nested sibling values and file precedence for unset
  defaults.
- Added domain-organized contracts for configuration, container registration,
  foundation providers, logging, and supported Support display and message
  boundaries. Removed fixture-only data, HTTP, and validation protocols that
  lacked production owners. See `docs/contracts/` and
  `docs/specifications/contracts.md`.
- Reorganized shared contracts into `titanspan.contracts.config`,
  `titanspan.contracts.container`, `titanspan.contracts.logging`, and
  `titanspan.contracts.support`. Logging contracts are generic and no longer
  import concrete logging records. Top-level and component imports re-export
  the same objects. Direct imports from the former flat contract modules are
  removed in this unreleased API; see `docs/specifications/contracts.md`.
- Added a native structured logging component with RFC severity levels,
  context-local metadata, redaction, channel stacks, file and stream drivers,
  standard-library logging interoperability, bounded background dispatch,
  application lifecycle integration, and native logging fakes. See
  `docs/specifications/logging.md` for implemented boundaries.
- Unified configuration, logging, facades, native service providers, and the
  application container. Configuration now drives the default logging
  manager; facade resolution shares one application context; provider boot is
  injected through the native container and cleaned up on startup failure.
  FastAPI route dependency injection remains a separately documented adapter.
  See ADR 0018 and `docs/architecture/contract-integration.md`.
- Added UTC calendar-month log rotation with bounded archive retention through
  Python's standard timed file handler.
- Added registered, once-per-channel native logging customizers with cleanup
  on initialization failure.
- Established the installable package, CLI, FastAPI application lifecycle,
  Dishka dependency integration, and typed settings.
- Added explicit synchronous and AnyIO-based asynchronous Support sleep
  builders with context-local fakes and native assertions.
- Added dotenv value parsing, scoped mapping adapters, and validated dotenv
  file updates.
- Added synchronous and AnyIO-based asynchronous retry helpers backed by
  Tenacity.
- Added locale-aware numeric formatting, parsing, spelling, summaries, and
  context-local locale and currency scopes through the optional `numbers`
  extra.
- Added UUID and ULID binary codecs with typed custom codec registration and
  Python byte interoperability.
- Added configuration URL parsing for common database schemes, nested query
  options, driver aliases, and SQL Server DSN values.
- Added namespaced item key parsing with an instance-local cache.
- Added wrapper call delegation with fluent identity preservation.
- Added aware datetime and duration deadline calculations with readable
  interval formatting.
- Added context-local random string factories and secure password generation
  as a Titanspan-specific string utility extension.
- Added initial tests, architecture decisions, contributor documentation, and
  repository automation.
