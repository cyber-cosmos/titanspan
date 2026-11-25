# ADR 0015: Synchronous-first container resolution

- Status: Accepted
- Date: 2026-11-25
- Supersedes: Resolution-mode details in ADR 0014

## Context

Titanspan is async-first, but object construction, registration, introspection,
and in-memory graph resolution do not inherently require asynchronous
execution. Requiring `await` for every dependency lookup would spread async
syntax through code that performs no asynchronous work. Conversely, blocking
or creating an event loop inside a synchronous API would hide lifecycle and
cancellation behavior.

The locked dependency engine is Dishka `1.10.1`. Its supported public API
provides `AsyncContainer.get_sync` for sync-safe dependencies and
`make_container` for synchronous graphs and cleanup. `AsyncContainer.get_sync`
and `AsyncContainer.get` use the same graph cache. Synchronous access bypasses
the async method's lock, so the framework must not imply cross-thread safety.

The web `Application` still owns its established ASGI graph and does not yet
expose the native `Container` as its single composition root. There is no
module-level `app()` helper in this milestone.

## Decision

- Make `Container.make`, `get`, `resolve`, `build`, `make_with`, and `call`
  synchronous when the requested graph is sync-safe.
- Provide explicit `make_async`, `get_async`, `resolve_async`, `build_async`,
  `make_with_async`, and `call_async` operations. Provide compatibility
  camelCase aliases for the named resolution operations.
- Never dynamically return an instance or awaitable from one method. Never
  start an event loop, block an active loop, or move arbitrary constructors to
  unmanaged threads.
- Keep one asynchronous backend graph for each application root. Dispatch
  synchronous requests through Dishka's documented `get_sync` and async
  requests through `get`, preserving cache identity for that root.
- Inspect native constructor and factory metadata before sync resolution. If
  the known graph contains an async-only factory or resource, raise
  `AsyncResolutionRequiredError` with a dependency path before invoking it.
- Use the backend's sync graph API for a new sync-only graph in a scope. A sync
  scope owns these graphs through an `ExitStack`; an async scope owns any sync
  graph callbacks through its `AsyncExitStack`. Async-only dependencies require
  async scope entry and async resolution.
- Track singleton and scoped instances observed through the native API and
  seed later mode-specific graphs from the owning application or scope. This
  preserves identities across graph generations without introducing a second
  backend singleton cache.
- Document only async-task concurrency that is verified by tests. Do not
  promise that one Dishka graph is safe to resolve concurrently from multiple
  operating-system threads.
- Keep shutdown asynchronous because application graphs may own async
  resources, even when ordinary service construction is synchronous.
- Keep facade operations synchronous when their own operation is in-memory.
  The current `Config` and `Log` facades use explicit execution-local bindings;
  they do not resolve their manager services through the native container.

## Consequences

Applications can call synchronous resolution from ordinary functions and can
use explicit async APIs for async factories, context managers, callbacks, and
other asynchronous work. A sync request against an async-only native graph
fails without invoking its async factory. Sync scopes can finalize sync
resources without requiring an event loop; async scopes still own async
cleanup.

Root-level sync and async calls share one backend cache. Scope-local sync and
async graphs are distinct because the backend exposes different scope-entry
APIs. Tracked values are copied into new graph contexts to preserve singleton
and scoped identities. Task-group tests verify mixed-mode application
singleton access and mixed-mode scoped access; cross-thread resolution remains
unsupported and unverified.

The native container is still not the ASGI `Application`'s composition root,
and `app()` is not available as a container helper. Async factories supplied
through external provider integrations may not be statically inspectable; a
sync backend failure at that boundary is reported as a native
`BindingResolutionError` with an async-resolution recommendation, rather than
misclassified as a verified async-only graph.

## Verification

`tests/unit/container/test_execution_modes.py` covers sync and async
zero-configuration resolution, mixed graphs, cache identity, transient and
scoped behavior, async-only preflight, callback behavior, cancellation cleanup,
and task-group mixed-mode access. Existing container integration tests exercise
real Dishka graph construction, resource cleanup, scope ownership, and
configuration contract resolution. The backend version and mode-specific
behavior are recorded in `docs/specifications/container.md`.
