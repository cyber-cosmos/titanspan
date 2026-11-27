# Changelog

Notable changes to Titanspan are recorded here. The project has not made a
public release.

## Unreleased

- Add native Queue and Bus dispatch with typed jobs, bounded JSON envelopes,
  and Taskiq-backed Redis workers.
- Keep handler scopes, middleware, retries, delayed delivery, ordered chains,
  bounded results, local batches, and scoped fakes.
- Register `queue:work`, `queue:listen`, `make:job`, and
  `make:job-middleware` through native Console.
- Verify Redis workers, retries, delays, chains, and result retrieval against
  a real local Redis service.
- Keep RabbitMQ optional and verify publication, consumption, cleanup, and
  process-crash redelivery against a real broker. Delayed scheduling remains
  unsupported.
- Add explicit synchronous Bus chain execution with member preflight and
  isolated job scopes.
- Add bounded ordered Queue and Bus bulk dispatch through the canonical
  single-job pipeline.
- Add conditional Queue and Bus dispatch helpers with explicit async methods.
- Record every fake chain member and add ordered chain and batch assertions.
- Add selective Queue and Bus fakes for registered job classes. Reject
  filters that would split chains or batches.
- Add ordered application-wide job middleware through Queue providers.
- Emit metadata-only retry events after Taskiq accepts retry publication.
- Let Queue fakes execute recorded handlers through native job scopes.
- Let Queue fakes assert recorded handler failures by exception type.
- Verify concurrent Redis jobs use isolated `JOB`-scoped dependencies.
- Verify real Redis process-crash redelivery after new queue activity. Document
  that Taskiq does not reclaim pending entries while the queue remains idle.
- Verify real Redis async job timeouts report failure and finalize JOB-scoped
  resources exactly once.
- Bound process-local batch history and reject admission when active batches
  fill the configured capacity.
- Defer durable failed-job records, unique jobs, distributed batches, queued
  listeners, and transaction-aware dispatch.
- Serialize middleware response models with their declared Pydantic schemas.
  Render middleware errors through Foundation's exception policy.
- Dispatch asynchronous Cache failover events through Events. Preserve
  completed operations when listeners fail. Release leases after failed
  notifications and refresh scheduling. Isolate memo entries by task and scope.
  Reserve tagged key namespaces. Run synchronous callbacks in AnyIO workers.
- Run Redis backend tests in mandatory integration CI with a disposable
  service.
- Limit async Hashing worker admission before entering AnyIO's general worker
  pool. Bind HTTP fakes created in an Application context to that Application.
- Add the optional Database component over SQLAlchemy and Alembic with
  application-owned named connections, thread-owned sync sessions,
  task-owned async sessions, explicit transactions, Core and ORM query
  builders, typed Active Record models, schema operations, migrations, model
  factories, transactional sync and async Seeders, and native Console
  integration. SQLite and PostgreSQL have real integration coverage;
  PostgreSQL integration fails closed when its mandatory CI service
  configuration is missing. See the Database guide for the verified scope
  and current limitations.
- Distinguish confirmed transaction outcomes from callback failures and
  uncertain commits. Reject cancelled model writes before later autoflush,
  apply model increments atomically, enforce SQLite foreign keys, preserve
  soft-delete visibility across eager loading, and coordinate PostgreSQL and
  MySQL migrations with database locks.
- Add explicit asynchronous route model binding through the native Routing
  callback boundary. Models can select a mapped route-key column, and missing
  rows use the framework's not-found response handling.
- Add asynchronous Database `unique_rule` and `exists_rule` integration with
  Validation, including model connection defaults, trusted constraints, and
  trusted update ignores. Rules delegate SQL construction and binding to the
  native Query Builder.
- Add typed model events for creation, update, save, and hard delete.
  Pre-persistence listeners can cancel writes. Sync and async listeners
  run after commit, in transaction and savepoint registration order.
  Add `DB.after_commit_async()` for task-owned transaction callbacks.
- Add model observer registration through the active Container and Events
  dispatcher, including scoped dependency resolution and async lifecycle hooks.
- Add sync and async database, model, and soft-delete assertions.
  The helpers run real Query Builder and ORM queries through the active
  Database service and reuse the existing Testing lifecycle.
- Add sync and async atomic Query Builder upserts and insert-or-ignore
  operations using SQLAlchemy's supported SQLite, PostgreSQL, and MySQL
  dialect constructs. SQLite and PostgreSQL behavior has real integration
  coverage; MySQL and MariaDB have not been integration-tested.
- Add sync and async model upserts with mapper-derived column names, guarded
  assignments, and automatic timestamp handling. Real SQLite and PostgreSQL
  behavior is integration-tested; bulk model events are not dispatched.
- Add model-scoped `without_events()` contexts for quiet sync and async
  persistence. Suppression is bound to its task or thread and application
  scope, and remains attached to after-commit callbacks.
- Apply named model global predicates to root queries, relationship existence
  checks, and eager-loaded related models. Add reusable typed query
  transformations and per-query global-scope removal.
- Add typed `with_where()` constraints for eager-loaded relationship paths.
- Dispatch cancellable soft-delete, restore, and force-delete events, with
  committed notifications ordered around the standard model delete lifecycle.
- Add sync and async ORM model streaming with bounded SQLAlchemy fetch batches
  and deterministic result cleanup on early exit and cancellation.
- Add sync and async model cursor pagination that delegates keyset ordering and
  cursor validation to Query Builder and hydrates each bounded page through
  SQLAlchemy ORM.
- Add model `"hashed"` casts backed by the application Hashing contract for
  sync, async, and model upsert persistence.
- Add dialect-aware right and full outer joins to the native Query Builder.
  Right joins use SQLAlchemy left-join expressions with the sides reversed.
  Full outer joins use backend support on PostgreSQL and SQLite 3.39 or later.
  PostgreSQL and SQLite behavior has real integration coverage.
- Add scalar subquery projections and subquery operands for `where_in()` and
  `where_not_in()`, including their OR variants, through SQLAlchemy Core.
- Add backend-native random ordering for SQLite, PostgreSQL, and MySQL. Reject
  cursor pagination when query ordering is not stable by columns.
- Add `increment_each()` and `decrement_each()` sync and async operations that
  update multiple numeric columns atomically in one statement.
- Add bound `where_row_values()` and `or_where_row_values()` comparisons using
  SQLAlchemy tuple expressions on SQLite, PostgreSQL, and MySQL dialects.
- Add right, full outer, and cross joins for fluent subqueries through SQLAlchemy
  Core, with the same dialect limits as their table join counterparts.
- Add typed join_with clauses for nested column and bound-value ON conditions
  while preserving left, right, and full join semantics.
- Add correlated Query Builder subqueries that share validated SQLAlchemy
  table expressions for scalar projections and EXISTS predicates.
- Add PostgreSQL inner and left LATERAL joins for correlated query builders.
- Add dialect-native full-text Query Builder predicates for PostgreSQL,
  SQLite FTS, MySQL, and MariaDB.
- Add safe JSON containment, nested key-existence, and array-length predicates
  plus nested JSON updates through supported database JSON functions.
- Add Query Builder SQL compilation and binding inspection with default value
  redaction.
- Add bound EXPLAIN plan inspection through the SQLite, PostgreSQL, MySQL, and
  MariaDB dialects.
- Declare Pydantic as a direct runtime dependency for native schema APIs.
- Add native application Cache services with memory and optional Redis
  backends, explicit backend capabilities, safe JSON serialization, atomic
  operations where supported, owner-token locks, tagged and failover stores,
  execution-local memoization and fakes, metadata-only events, commands, and
  application lifecycle integration. Deferred stale refresh uses caller-owned
  AnyIO task groups. See the Cache guide and component specification.
- Run synchronous Console handlers in managed AnyIO worker threads.
- Allow configuration commands to target an explicit application root.
- Add event inspection and manifest commands to the native Console.
- Add safe, application-rooted Console generators for controllers, middleware,
  providers, commands, events, listeners, Seeders, and application tests.
- Add synchronous and asynchronous application test contexts over the
  production Foundation lifecycle, Container, and ASGI application.
- Extend the clean-install smoke with a multipart document workflow. The
  installed-wheel run verifies Validation, Pipeline, local storage, Events,
  Logging, global and route middleware, named URLs, JSON validation, response
  cookies, generated routes, service fakes, Hashing, Console injection,
  Testing, and shutdown.
- Anchor relative event manifest paths to the effective application root.
- Render malformed native request input as a safe HTTP 400 response.
- Added Pydantic-backed Validation with typed schemas, coercion policy, safe
  field issues, sync and async application rules, result helpers, and
  authoritative HTTP request input. Foundation renders uncaught validation
  failures as safe 422 responses. Native typed routes document the same safe
  422 body schema used by Foundation.
- Added `RouteDefinition.validate_input()` to apply Validation rules to typed
  HTTP inputs while preserving Pydantic request schemas and safe 422 handling.
  `ValidationService.apply_rules_async()` applies those rules without running
  the endpoint schema a second time.
- Added native commands with typed parameters, groups, trusted discovery,
  Container injection, and per-command Foundation lifecycle. Rich output and
  parser tests use shared contracts. `about` reports framework and Python
  versions. Route and event inspection commands use their owning components.
  Native artifact generators write typed starter files without replacing
  existing application files.
- Added `Console.execute_async()` for programmatic command execution from an
  active async runtime. It reuses the active Application or owns a fresh
  Foundation lifecycle when no application context is bound.
- Added real ASGI regressions for stream and WebSocket failures after protocol
  transmission starts. They verify scoped cleanup, context restoration, and
  that Foundation does not send a second HTTP response.
- Added an ordered sync and async Pipeline for transforms, continuation
  middleware, class stages, conditional inclusion, and native Container
  resolution. Pipeline owns no task scheduler or workflow state.
- Facade service resolution now uses one shared typed implementation.
  Temporary `Config.use()` and `Log.use()` replacements use the active
  application Container and restore its graph after normal, exceptional,
  or cancelled execution. Calls without an application context now fail
  explicitly.
- Added a typed Application builder, trusted provider entry points, path and
  environment helpers, and standalone execution. Lifecycle callbacks and
  native exception rendering use the application Container. Unhandled request
  failures return a generic JSON response. Conventional route discovery uses
  the effective application root unless `routing.path` overrides it. Relative
  overrides resolve beneath that root. Uncaught Validation errors use a safe
  422 response. See the Foundation guide and specification.
- Validate outbound URLs before base resolution and again after joining.
  Fail-fast request pools stop accepting callbacks after a failure. Responses
  suppress bodies for `HEAD` and statuses 204, 205, and 304.
- Isolated pooled HTTP cookie state and shared ASGI body limits. Streams now
  close on disconnect or cancellation. Request builders snapshot inputs and
  use shared retry helpers. Routing validates URL constraints and trusted
  domains. Collection intersection checks every iterable. Pytest collection
  rejects tests without category markers.
- Completed native route registration, resource APIs, controller and
  parameter binding, middleware conventions, discovery, inspection, safe JSON
  route metadata caching, WebSocket dispatch, and FastAPI OpenAPI integration.
- Added immutable route middleware parameters through
  `MiddlewareDeclaration` and `ParameterizedHttpMiddleware` for aliases,
  groups, resources, and controllers. The Container applies each middleware
  lifetime, and inspection omits parameter values.
- Unified URI factories, route helpers, dependency injection, and named
  redirects through the application-owned `UriUrlGenerator`. Named route
  helpers default to relative URLs; `Uri.to()` remains absolute. Support's
  `Arr.query` owns query encoding. Built-in converters reject values that
  cannot match; custom Starlette converters remain unsupported. Signed URLs
  remain pending secure application key management.
- Added application-owned named local and memory storage disks over fsspec.
  Sync operations delegate to fsspec; explicit async operations offload sync
  backends through AnyIO. Streaming, safe disk-relative paths, file metadata,
  context-local fakes, and Config and Container integration are available.
  Remote backends require an application-provided fsspec factory and optional
  integration package. See `docs/src/content/docs/filesystem/` and
  `docs/src/content/docs/specifications/filesystem.md`.
- Storage fakes now replace disks at the canonical manager boundary, so
  injected `StorageManager` consumers use the same fake as the `Storage`
  facade. Fake setup validates names without constructing configured storage.
  Custom managers must implement the optional `StorageDiskOverride` contract.
- Foundation now registers Validation, Filesystem, and Hashing providers by
  default. One explicit provider of each type replaces its default and retains
  custom driver configuration. Duplicate built-in providers fail clearly.
- Foundation supplies the canonical `ApplicationPaths` contract to built-in
  providers. Relative local storage and file-log paths resolve beneath the
  effective application root; absolute paths remain unchanged and escaping
  relative paths fail during configuration.
- Foundation exception reports now resolve the active application logger and
  omit exception text and tracebacks by default. Application debug mode or
  `include_details=True` enables detailed diagnostics. Console failures show
  the command and exception class unless bounded details are explicitly
  enabled with `Console(show_exception_details=True)`.
- Foundation uses the logging manager's independent emergency destination
  when reporting occurs after channel shutdown. This path includes the
  exception class but omits its message and traceback.
- Added configuration-driven password hashing over `argon2-cffi` and `bcrypt`
  with Argon2id, Bcrypt verification and upgrades, hash metadata, and bounded
  async methods.
  `HashingServiceProvider` is registered by Foundation and can be replaced
  through its provider extension.
  Authentication and password persistence remain separate component work.
  See `docs/src/content/docs/hashing/` and
  `docs/src/content/docs/specifications/hashing.md`.
- Added ordered event dispatch through Blinker 1.9.0. It supports sync and
  async listeners, Container injection, wildcards, subscribers, discovery,
  context-local fakes, deferral, and bounded event pushes.
  Class-based subscriber methods resolve in each active dispatch scope;
  explicit instance subscribers remain registration-owned.
  Database transactions expose callback registration; transaction-aware
  Events delivery, Queue, and Broadcasting remain pending. Event inspection
  and cache/database commands use the native Console registration boundary.
  See `docs/src/content/docs/events/` and
  `docs/src/content/docs/specifications/events.md`.
- Completed multipart uploads, HTTPX2 fakes, assertions, bounded AnyIO pools,
  SSE parsing, and Starlette CORS, trusted-host, and HTTPS middleware.
  Outbound URL checks reject unsafe schemes and embedded credentials. They do
  not claim comprehensive SSRF protection. Scoped ASGI requests preserve
  bounded body and upload parsing, response streaming cleanup, and scope
  through transmission. Authentication,
  sessions, CSRF, distributed rate limiting, HTTP storage destination policy,
  trusted proxy configuration, and Telemetry remain owning-component
  integrations.
  See `docs/src/content/docs/http/` and
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
