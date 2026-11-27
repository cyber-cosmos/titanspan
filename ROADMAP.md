# Roadmap

Titanspan is consolidating its engineering foundation and implementing the
application and web composition lifecycle in tested vertical slices. Native
configuration, logging, Support, the sync-first container, HTTP, Routing,
Filesystem, and Hashing integrate with the application lifecycle. Routing covers
registration, dispatch, discovery, inspection, safe metadata snapshots,
WebSockets, and OpenAPI through the established ASGI host. Filesystem provides
application-owned local and memory disks over fsspec. Explicit third-party
FastAPI providers remain an interoperability boundary; ordinary Titanspan
route dispatch uses the native container. These phases are capability
milestones, not calendar promises.

The standalone Collections component now provides eager and lazy operations
for ordinary Python iterables. Pipeline provides ordered synchronous and
asynchronous value transformations. Validation provides Pydantic-backed
schemas, native field errors, application rules, and HTTP request input.
Foundation rendering and Routing schema integration remain with their owners.
Streaming data pipelines and large-scale processing remain planned.

Hashing provides Argon2id password hashes, Bcrypt verification, safe hash
upgrades, and explicit async access independently of Authentication.

The Events component now provides ordered in-process dispatch, Container-backed
listeners, scoped fakes, deferred dispatch, trusted discovery, and Console
inspection commands. Durable queue, transaction, and broadcasting integration
remain planned. Console provides native command registration and
application-aware execution.

## Phase 0 — Engineering foundation

- Repository configuration and community health files.
- Installable package, lockfile, CLI, and minimal application lifecycle.
- CI, security automation, and documentation build.
- Coding standards and working Hello World example.
- Initial native logging component and its documented operational limits.

## Phase 1 — Application foundation (in progress)

- Application lifecycle, configuration repository, and execution-local
  facades are implemented. The native container composes framework services,
  and provider registration and boot are lifecycle-integrated.
- Domain-oriented contracts and a native synchronous-first container API are
  implemented incrementally, with contract conformance and app identity tests.
- Remaining work: complete established Container capabilities and expand
  lifecycle integrations without exposing backend provider types through
  ordinary APIs.

## Phase 2 — Web and developer tooling

- The HTTP component provides ASGI request scopes, responses, middleware,
  streaming, and pooled clients. Routing provides native registration,
  controller dispatch, URL generation, discovery, inspection, WebSockets,
  and OpenAPI. See the component specifications for verified behavior.
- Routing integrations remain for Database-backed model binding, key-managed
  signed URLs, View routes, and parameterized middleware. HTTP fake transports
  and bounded concurrent HTTP pools are implemented. Structured observability
  improvements remain with Telemetry.
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

- SQLAlchemy-backed persistence, migrations, and query conventions.
- Structured concurrency, CPU parallelism, and bounded streaming pipelines.

## Phase 5 — Production infrastructure

- Authentication and authorization remain planned; Hashing supplies their
  password service foundation. Cache and queue infrastructure remain planned.
- Scheduling, notifications, and mail.
- Telemetry, resource quotas, and operational resilience.

## Phase 6 — Ecosystem and stabilization

- Starter kits and reference applications.
- Complete documentation and reproducible performance benchmarks.
- Workflow monitoring and developer experience improvements.
- Public API stabilization after behavioral and migration policies are
  established.
