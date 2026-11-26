# Roadmap

Titanspan is consolidating its engineering foundation before completing the
full application and web composition lifecycle. Native configuration,
logging, Support, and the sync-first container have working implementations
and cross-component application integration. FastAPI route injection still
uses a separate private graph. These phases are capability milestones, not
calendar promises. Each phase should ship coherent vertical slices with tests
and documentation before expanding its surface area.

The standalone Collections component now provides eager and lazy operations
for ordinary Python iterables. Data pipelines, async streams, and large-scale
processing remain planned.

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
- Next: complete established Container capabilities and unify ASGI route
  dependency injection with the native registry without exposing backend
  provider types through ordinary APIs.

## Phase 2 — Web and developer tooling

- Native ASGI request scopes, response construction, initial middleware,
  streaming, and pooled HTTP clients are implemented; see `docs/src/content/docs/http/`.
- Routing, controllers, route-level middleware, HTTP fake transports, bounded
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

- Authentication, authorization, cache, queues, and events.
- Scheduling, notifications, and mail.
- Telemetry, resource quotas, and operational resilience.

## Phase 6 — Ecosystem and stabilization

- Starter kits and reference applications.
- Complete documentation and reproducible performance benchmarks.
- Workflow monitoring and developer experience improvements.
- Public API stabilization after behavioral and migration policies are
  established.
