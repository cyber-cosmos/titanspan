# Roadmap

Titanspan is in Phase 0. These phases are capability milestones, not calendar
promises. Each phase should ship coherent vertical slices with tests and
documentation before expanding its surface area.

## Phase 0 — Engineering foundation

- Repository configuration and community health files.
- Installable package, lockfile, CLI, and minimal application lifecycle.
- CI, security automation, and documentation build.
- Coding standards and working Hello World example.

## Phase 1 — Application foundation

- Application lifecycle and service providers.
- Service container conventions, contracts, and configuration repository.
- Context-aware facades and shared utilities.

## Phase 2 — Web and developer tooling

- Routing, controllers, and middleware conventions.
- HTTP client integration and structured logging.
- CLI generators and application test utilities.

## Phase 3 — AI orchestration

- Model provider adapters, agents, and authorized tools.
- Typed workflow builder on LangGraph.
- Checkpointing, streaming, human-in-the-loop execution, and deterministic
  workflow tests.

## Phase 4 — Data and concurrency

- SQLAlchemy-backed persistence, migrations, and query conventions.
- Eager, lazy, and async collections.
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
- Public API stabilization after compatibility and migration policies are
  established.
