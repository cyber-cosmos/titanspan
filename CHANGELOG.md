# Changelog

Notable changes to Titanspan are recorded here. The project has not made a
public release.

## Unreleased

- Isolated pooled HTTP cookie state and shared ASGI body limits. Streams now
  close on disconnect or cancellation. Request builders snapshot inputs and
  use shared retry helpers. Routing validates URL constraints and trusted
  domains. Collection intersection checks every iterable. Pytest collection
  rejects tests without category markers.
- Added native route registration, controller dispatch, request scopes,
  helpers, and URL generation. URI factories and redirects share the active
  application context and route catalog. Titanspan validates redirect
  responses. Signed URLs remain unavailable until secure signing and
  verification exist.
- Added ordered event dispatch through Blinker 1.9.0. It supports sync and
  async listeners, Container injection, wildcards, subscribers, discovery,
  context-local fakes, deferral, and bounded event pushes.
  Queue, Database, Broadcasting, and Console integrations remain pending.
  See `docs/src/content/docs/events/` and
  `docs/src/content/docs/specifications/events.md`.
- Added scoped ASGI requests with bounded body and multipart parsing. HTTP
  provides native responses, SSE, streaming, ordered middleware, and pooled
  sync and async clients. Request scope remains active through transmission.
  HTTP fakes, bounded request pools, multipart client uploads, and SSRF
  enforcement remain pending. See `docs/src/content/docs/http/` and
  `docs/src/content/docs/specifications/http.md`.
- Added a technical writing standard and canonical glossary. Vale checks
  maintained Markdown, Python comments, and docstrings with pinned rules and
  regression cases. Objective terminology errors block CI; other writing
  findings remain advisory. See `docs/src/content/docs/development/writing-standards.md`.
- Added typed eager and lazy collection APIs over Python iterables. Eager
  collections provide stable transformations and grouping; lazy pipelines use
  iterator factories and preserve one-shot sources without caching. Support
  integration reuses `Arr` and `Tappable`; the component has no runtime
  dependencies. See `docs/src/content/docs/collections/` and
  `docs/src/content/docs/specifications/collections.md`.
- Reject nested overrides that would be hidden by an inherited singleton,
  while preserving unaffected singleton identity and resource ownership.
  Configuration injection checks collection values against bare or
  parameterized `list`, `dict`, and `Mapping` annotations through the existing
  typed accessor. Application shutdown can be retried after active scopes or
  overrides exit. See `docs/src/content/docs/specifications/container.md` for behavior and
  limits.
- Standardized pre-release public APIs on one Python `snake_case` spelling.
  Removed duplicate aliases, vendor-named protocol exports, and ignored
  string encoding and locale parameters. Empty iterable endpoints now return
  `None`, and configuration mapping deletion removes the path. See ADR 0016
  for the API policy.
- Corrected sync-safe graphs to resolve synchronously. Async factories and
  resources use explicit async methods. Sync and async application resolution
  share Dishka's graph cache. Scopes finalize resources through their matching
  lifecycle. See ADR 0015 and
  `docs/src/content/docs/specifications/container.md`.
- The native Container provides typed bindings, application singletons,
  execution scopes, tags, aliases, concrete dependency discovery, and bounded
  graph generations. It cleans up sync and async resources. It supports
  callable and method injection, lifetime decorators, contextual bindings,
  `Annotated` injection, extensions, callbacks, and task-local overrides.
  Framework services and native routes use one Container. The Container freezes
  registrations after graph composition. Explicit external provider graphs
  remain an interoperability boundary. See
  `docs/src/content/docs/specifications/container.md` and
  `docs/src/content/docs/container/`.
- Config provides a native repository, typed accessors, trusted Python, JSON,
  and TOML sources, dotenv integration, settings validation, and contract
  registration. It also provides safe inspection, atomic JSON caching, and
  configuration commands. See `docs/src/content/docs/config/` and
  `docs/src/content/docs/specifications/config.md`.
- Projected explicitly supplied custom settings fields into configuration
  paths, preserving nested sibling values and file precedence for unset
  defaults.
- Added domain-organized contracts for configuration, container registration,
  foundation providers, logging, and supported Support display and message
  boundaries. Removed fixture-only data, HTTP, and validation protocols that
  lacked production owners. See `docs/src/content/docs/contracts/` and
  `docs/src/content/docs/specifications/contracts.md`.
- Reorganized shared contracts into `titanspan.contracts.config`,
  `titanspan.contracts.container`, `titanspan.contracts.logging`, and
  `titanspan.contracts.support`. Logging contracts are generic and no longer
  import concrete logging records. Top-level and component imports re-export
  the same objects. Direct imports from the former flat contract modules are
  removed in this unreleased API; see `docs/src/content/docs/specifications/contracts.md`.
- Logging provides structured records, channels, redaction, and native test
  fakes. It also supports file and stream drivers, bounded delivery, lifecycle
  cleanup, and standard logging integration. See its specification for details.
- Configuration, Logging, Facades, providers, and the application Container
  now share one lifecycle. Configuration selects the logging manager. Provider
  boot uses Container injection and cleans up after startup failure. FastAPI
  dependency injection remains a documented adapter. See ADR 0018 and the
  contract integration audit.
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
