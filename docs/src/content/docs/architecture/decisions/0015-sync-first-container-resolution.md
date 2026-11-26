---
title: "ADR 0015: Synchronous-first container resolution"
---

<span id="adr-0015-synchronous-first-container-resolution"></span>

- Status: Accepted
- Date: 2026-11-25
- Supersedes: Resolution-mode details in ADR 0014
- Application composition and facade integration are updated by ADR 0018.

> Status update: At acceptance, `Application` still used a separate native
> service graph. ADR 0018 subsequently made `Container` the composition root
> for framework services and added the context-local `app()` helper.
> Contextual sources, callbacks, extensions, and temporary overrides are
> described in ADR 0019. Explicit FastAPI dependency injection still uses its native bridge;
> the separate raw provider graph is reserved for explicit interoperability.

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

The web `Application` owns the native container as the composition root for
Titanspan services. A context-local module-level `app()` helper provides
access to it while an application context is active.

## Decision

- Make `Container.make`, `get`, `make_with`, and `call` synchronous when the
  requested graph is sync-safe.
- Provide explicit `make_async`, `get_async`, `make_with_async`, and
  `call_async` operations.
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
  Config and Log now resolve declared contracts through the shared typed
  facade base and active application container; their explicit `use`
  contexts remain temporary execution-local overrides.

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

The native container is the composition root for framework services. FastAPI
route injection uses a bridge into that container. External provider
integrations may supply async factories that Titanspan cannot inspect
statically. At this boundary, sync backend failures become native
`BindingResolutionError` exceptions. The message recommends async resolution
instead of claiming preflight identified an async-only graph. The active
container helper is `titanspan.app()`. It requires an application context.

Contextual bindings, injection metadata, extensions, callbacks, and temporary
overrides were added after this decision. Their precedence, ownership, and
cleanup rules are in [ADR 0019](/titanspan/architecture/decisions/0019-contextual-container-services/).

## Verification

`test_execution_modes.py` covers sync and async resolution, mixed graphs, cache
identity, transient and scoped behavior, preflight errors, callbacks, cleanup,
and task-group access. Container integration tests verify real Dishka graph
construction, resource cleanup, scope ownership, and configuration contract
resolution. The backend version and mode behavior are in the container
specification.
