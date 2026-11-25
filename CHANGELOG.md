# Changelog

Notable changes to Titanspan are recorded here. The project has not made a
public release.

## Unreleased

- Added an incremental native asynchronous container API with typed bindings,
  application singletons, execution-scoped values, ordered tags, aliases,
  automatic concrete dependency discovery, bounded graph generations, and
  synchronous and asynchronous generator cleanup, callable injection, method
  callback bindings, and declarative class lifetime decorators. Existing web
  lifecycle integration remains in place; contextual injection, dynamic
  rebinding, and application composition-root integration remain pending. See
  `docs/specifications/container.md` and `docs/container/`.
- Added the native configuration repository, strict typed accessors, trusted
  Python/JSON/TOML source loading, isolated dotenv integration, validated
  settings, application-scoped facade and Dishka contract binding. Added
  secret-safe configuration inspection, atomic JSON caching, and config CLI
  commands. See `docs/config/` and the Laravel compatibility inventory.
- Projected explicitly supplied custom settings fields into configuration
  paths, preserving nested sibling values and file precedence for unset
  defaults.
- Added dependency-independent contracts for mutable configuration, typed
  asynchronous service resolution, and generic Support data/presentation
  interfaces. Existing HTML and message-bag contract identities remain
  canonical. The configuration and async container contracts have no
  production adapters yet; see `docs/contracts/` and the Laravel compatibility
  inventory.
- Added a native structured logging component with RFC severity levels,
  context-local metadata, redaction, channel stacks, file and stream drivers,
  standard-library logging interoperability, bounded background dispatch,
  application lifecycle integration, and native logging fakes. Laravel
  compatibility remains incremental; see `docs/compatibility/laravel-logging.md`.
- Added UTC calendar-month log rotation with bounded archive retention through
  Python's standard timed file handler.
- Added registered, once-per-channel native logging customizers with cleanup
  on initialization failure.
- Established the installable package, CLI, FastAPI application lifecycle,
  Dishka dependency integration, and typed settings.
- Added explicit synchronous and AnyIO-based asynchronous Support sleep
  builders with context-local fakes and upstream-compatible assertions.
- Added Laravel-compatible environment value parsing, scoped mapping adapters,
  and validated dotenv file updates.
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
- Added aware datetime and duration deadline calculations with runtime
  formatting based on Carbon's default interval cascade.
- Added context-local random string factories and secure password generation
  as a Titanspan-specific string utility extension.
- Added initial tests, architecture decisions, contributor documentation, and
  repository automation.
