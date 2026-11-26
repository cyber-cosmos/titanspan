# Container module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns
Titanspan's dependency registration API and lifecycle integration over
Dishka.

- Keep Dishka as the graph resolver and resource finalizer. Do not implement
  a competing dependency-resolution engine.
- Keep public names domain-oriented (currently `container/container.py`), not
  vendor-oriented. State clearly that graph resolution is delegated to Dishka.
- Keep Dishka types behind `container._backends` for ordinary APIs. The
  ASGI `Application.providers` input remains a transitional web route
  interoperability boundary; framework services already use the native
  application container and structural service providers. Do not expand the
  raw provider surface. Remove it only with route-scope, cleanup, and migration
  coverage.
- Keep the synchronous-first `ServiceContainer` and async-only
  `AsyncServiceContainer` protocols canonical in
  `titanspan.contracts.container`. Ordinary resolution uses `make`/`get` for
  sync-safe graphs; `make_async`/`get_async` explicitly allow async resources.
- At application scope, keep one Dishka async graph for both `get_sync` and
  `get`, because those operations share its cache. Scope-local sync graphs
  must register cleanup with their owning sync or async scope. Never block,
  start an event loop, or return an awaitable from a sync method.
- Do not claim cross-thread safety for mixed-mode access unless a separate
  verified synchronization contract is implemented.
- Validate registration graphs before serving. Freeze production
  registrations after boot; avoid shared mutable runtime mutation.
- Model transient, application, request, job, workflow, and tool lifecycles
  only where concrete code and scope semantics justify them.
- Ensure scoped objects do not leak across concurrent requests or jobs, and
  finalize resources on failure and cancellation.
- Use a failing test first. Test actual Dishka integration for resolution,
  scope isolation, resource initialization/finalization, startup failure, and
  cleanup; cover invalid graphs and overrides at the appropriate boundary.
- Strictly type and document every declaration with a multi-line docstring.
  Explain non-obvious scope ownership and cleanup ordering in comments.
- Consult `ARCHITECTURE.md` and ADRs 0005 and 0009. Run `make test`,
  `make integration-test`, `make types`, and `make check` for applicable
  changes.
