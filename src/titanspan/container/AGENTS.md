# Container module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns
Titanspan's dependency registration API and lifecycle integration over
Dishka.

- Keep Dishka as the graph resolver and resource finalizer. Do not implement
  a competing dependency-resolution engine.
- Keep public names domain-oriented (currently `container/container.py`), not
  vendor-oriented. State clearly that graph resolution is delegated to Dishka.
- Keep Dishka types behind `container._backends` for ordinary APIs.
  `Application.dependency` resolves native services from the active app and
  request scope, including through streamed responses. `Application.providers`
  remains an advanced interoperability boundary for explicit external route
  providers. Do not expand the raw provider surface. Remove it only with
  request-scope, cleanup, and migration coverage.
- Keep application startup and shutdown available without an ASGI host.
  Register cleanup before provider boot, roll back partial startup, and close
  external route resources before native services while logging remains live.
- Keep the synchronous-first `ServiceContainer` and async-only
  `AsyncServiceContainer` protocols canonical in
  `titanspan.contracts.container`. Ordinary resolution uses `make`/`get` for
  sync-safe graphs; `make_async`/`get_async` explicitly allow async resources.
- At application scope, keep one Dishka async graph for both `get_sync` and
  `get`, because those operations share its cache. Worker-thread sync calls
  must return through the owning AnyIO runtime, acquire Titanspan's shared
  initialization gates, then call `get_sync` in a bounded worker pool.
- Key application singleton gates by container and service. Key scoped gates
  by execution-scope owner and service. Do not serialize independent request
  or workflow scopes with one global scoped-service lock.
- Bind a started container to one event loop. Reject unsafe resolution on the
  owner loop while another task initializes the same shared value. Never
  block, create a hidden event loop, or return an awaitable from a sync method.
- Synchronous resolution before runtime startup uses separate per-key thread
  gates. Startup must reject while any public sync resolution remains active.
- Do not use a broad `RuntimeError` catch to translate expired AnyIO tokens.
  Preserve factory failures and translate only the documented token-expiry
  exception.
- A sync factory running in the managed backend worker must declare uncached
  dependencies in its signature. Reject nested container lookup that could
  deadlock while the worker waits on its owning event loop.
- Validate registration graphs before serving. Freeze production
  registrations after boot; avoid shared mutable runtime mutation.
- Contextual rules, injection metadata, extensions, callbacks, and temporary
  overrides must preserve the precedence and lifecycle documented in
  `docs/src/content/docs/specifications/container.md`. Synchronous overrides must use sync
  graph owners and cleanup; asynchronous overrides must await async resource
  finalization. Neither form may cross those lifecycle boundaries silently.
- Keep injection-source selection shared between public callable resolution
  and private graph composition; do not duplicate precedence logic.
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
