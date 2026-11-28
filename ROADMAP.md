# Roadmap

Titanspan's core application and web lifecycle now composes native
configuration, logging, Support, the Container, HTTP, Routing, Filesystem,
Hashing, Validation, Cache, Events, Pipeline, Testing, Console, and the
initial Queue and Bus runtime.
Routing handles registration, dispatch, discovery, inspection, WebSockets, and
OpenAPI through the established ASGI host. Filesystem provides application-
owned local and memory disks over fsspec. Explicit third-party FastAPI
providers remain an interoperability boundary; ordinary Titanspan route
dispatch uses the native Container. These phases are capability milestones,
not calendar promises.

The standalone Collections component now provides eager and lazy operations
for ordinary Python iterables. Pipeline provides ordered synchronous and
asynchronous value transformations. Validation provides Pydantic-backed
schemas, native field errors, application rules, and HTTP request input.
Foundation renders safe validation errors, and Routing integrates typed input
schemas with OpenAPI. Streaming data pipelines and large-scale processing
remain planned.

Hashing provides Argon2id password hashes, Bcrypt verification, safe hash
upgrades, and explicit async access independently of Authentication. Cache
provides application-scoped memory and optional Redis stores, safe JSON values,
leases, named failover, execution-local memoization, and native test fakes.

The Events component provides ordered in-process dispatch, Container-backed
listeners, scoped fakes, deferred dispatch, trusted discovery, and Console
inspection and cache commands. Queue provides typed job declarations, safe
JSON messages, application-scoped workers, retries, Redis Streams transport,
chains, and local batch tracking. Durable failed-job records, distributed
batches, results, unique jobs, queued event listeners, and
transaction-aware dispatch remain planned. Console provides native command
registration and application-aware execution.

Database is a built-in SQLAlchemy and Alembic-backed persistence component
with application-owned connections and sessions, sync and async
query and model APIs, schema operations, migrations, and SQLite and PostgreSQL
integration coverage. Basic model factories support in-memory construction,
states, sequences, and sync and async persistence. Explicit route model
binding resolves configured keys through the active Database service.
Database-backed async `unique_rule` and `exists_rule` values reuse the native
Validation service and bind all query values. Typed model lifecycle events
and Container-resolved observers use the native Events dispatcher and
transaction callbacks. Query-backed assertions reuse the existing Testing
lifecycle. Native Query Builder upserts use SQLAlchemy's SQLite and PostgreSQL
conflict statements with live integration coverage. Relationship
factories, recycling, advanced relationships, scoped or automatic binding,
and model URL generation remain in progress. Seeders support sync and async
execution through Container-owned instances and Database transactions
with native `db:seed` and `make:seeder` commands.

## Phase 0 — Engineering foundation

- Repository configuration and community health files.
- Installable package, lockfile, CLI, and minimal application lifecycle.
- CI, security automation, and documentation build.
- Coding standards and working Hello World example.
- Initial native logging component and its documented operational limits.

## Phase 1 — Application foundation (implemented for current scope)

- Application lifecycle, configuration repository, and execution-local
  facades are implemented. The native container composes framework services,
  and provider registration and boot are lifecycle-integrated.
- Domain-oriented contracts and the native sync and async Container APIs are
  implemented with contract conformance and application identity tests.
- Known execution-scope nesting limits remain documented in the framework
  engineering review. They constrain future overlapping workflow and request
  lifetimes.

## Phase 2 — Web and developer tooling

- The HTTP component provides ASGI request scopes, responses, middleware,
  streaming, and pooled clients. Routing provides native registration,
  controller dispatch, URL generation, discovery, inspection, WebSockets,
  and OpenAPI. See the component specifications for verified behavior.
- Routing integrations remain for Database-backed model binding, key-managed
  signed URLs, and View routes. Parameterized route middleware is implemented.
  HTTP fake transports and bounded concurrent HTTP pools are implemented.
  Structured observability improvements remain with Telemetry.
- Console provides application-rooted generators for controllers, middleware,
  providers, commands, events, listeners, and smoke tests. A full application
  scaffold remains planned. Testing provides synchronous and asynchronous
  application contexts over the production ASGI and Container lifecycles.

## Phase 3 — AI orchestration

- Model provider adapters, agents, and authorized tools.
- Typed workflow builder on LangGraph.
- Checkpointing, streaming, human-in-the-loop execution, and deterministic
  workflow tests.

## Phase 4 — Data and concurrency

- Database persistence, migrations, factories, seeders, model events,
  validation, route binding, and native Console foundations are implemented.
  Native database assertions and one-of-many model relationships are
  implemented. Polymorphic relationships, relationship factories,
  query-count assertions, and database test isolation remain planned.
- Structured concurrency, CPU parallelism, and bounded streaming pipelines.

## Phase 5 — Production infrastructure

- Authentication and authorization remain planned; Hashing supplies their
  password service foundation.
- Scheduling, notifications, and mail.
- Telemetry, resource quotas, and operational resilience.

## Phase 6 — Ecosystem and stabilization

- Starter kits and reference applications.
- Complete documentation and reproducible performance benchmarks.
- Workflow monitoring and developer experience improvements.
- Public API stabilization after behavioral and migration policies are
  established.
