# Roadmap

Titanspan is consolidating its engineering foundation and implementing the
application and web composition lifecycle in tested vertical slices. Native
configuration, logging, Support, the sync-first container, HTTP, and Routing
have application integration. Routing covers registration, dispatch,
discovery, inspection, safe metadata snapshots, WebSockets, and OpenAPI
through the established ASGI host. Explicit third-party FastAPI providers
remain an interoperability boundary; ordinary Titanspan route dispatch uses
the native container. These phases are capability milestones, not calendar
promises.

The standalone Collections component now provides eager and lazy operations
for ordinary Python iterables. Data pipelines, async streams, and large-scale
processing remain planned.

The Events component now provides ordered in-process dispatch, Container-backed
listeners, scoped fakes, deferred dispatch, and trusted discovery. Durable
queue, transaction, broadcasting, and Console integrations remain planned.

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
  signed URLs, View routes, parameterized middleware, Console route listing,
  and Foundation base-path discovery. HTTP fake transports, bounded
  concurrent HTTP pools, and structured observability improvements remain.
- CLI generators and application test utilities.

## Phase 3 — AI orchestration

- Model provider adapters, agents, and authorized tools.
- Typed workflow builder on LangGraph.
- Checkpointing, streaming, human-in-the-loop execution, and deterministic
  workflow tests.

## Phase 4 — Data and concurrency

- SQLAlchemy-backed persistence, migrations, and query conventions.
- Structured concurrency, CPU parallelism, and bounded streaming pipelines.
- Filesystem integrations.

## Phase 5 — Production infrastructure

- Authentication, authorization, cache, and queue infrastructure.
- Scheduling, notifications, and mail.
- Telemetry, resource quotas, and operational resilience.

## Phase 6 — Ecosystem and stabilization

- Starter kits and reference applications.
- Complete documentation and reproducible performance benchmarks.
- Workflow monitoring and developer experience improvements.
- Public API stabilization after behavioral and migration policies are
  established.
