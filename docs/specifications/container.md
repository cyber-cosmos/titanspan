# Native service container specification

This document records Titanspan's native service-container behavior, current
implementation status, and architectural limits. It is the behavioral
specification for the public API.

## Resolution backend

The private resolution adapter is verified against Dishka `1.10.1`, the exact
version in `uv.lock`. That release publicly exposes `AsyncContainer.get_sync`
and `make_container`; Titanspan uses the former for sync-safe application
graphs and the latter for sync-only scoped graphs. Backend-specific types stay
inside `container._backends`.

## Implemented behavior

The public API is defined in `src/titanspan/container/`. The private adapter
composes validated graphs and delegates construction, caching within a graph,
and generator cleanup to the selected dependency engine.

| Native operation | Status | Behavior and evidence |
| --- | --- | --- |
| `Container()` | Verified | Creates an application-owned registry. |
| `bind` | Verified | Registers a transient class or typed factory. |
| `bind_if` | Verified | Registers only when the key is absent. |
| `singleton` | Verified | Caches one application-owned instance. |
| `singleton_if` | Verified | Conditionally registers a singleton. |
| `scoped` | Verified | Caches in the selected active execution scope. |
| `scoped_if` | Verified | Conditionally registers a scoped value. |
| `@singleton` | Verified | Declares application-owned lifetime metadata on a class. |
| `@scoped(scope)` | Verified | Declares execution-scope metadata on a class. |
| `instance` | Verified | Registers an externally owned value. |
| `make` / `get` | Verified | Synchronously resolves sync-safe graphs; an initialized cached service remains accessible. |
| `make_async` / `get_async` | Verified | Explicitly resolves graphs with async factories or resources. |
| `make_with` / `make_with_async` | Verified | Constructs a root with explicit values and resolves remaining dependencies through `call` or `call_async`. |
| `bound` | Verified | Checks explicit registration without resolution. |
| `has` | Adapted | Checks explicit keys, aliases, and non-abstract classes; it does not
  prove that a concrete graph can be constructed. |
| `resolved` | Adapted | Reports only cached values observed through this API. |
| `is_shared` | Verified | Reports registered or class-declared cached lifetimes. |
| `is_alias` | Verified | Checks a registered string alias. |
| `alias` | Verified | Maps a string key to one canonical type; alias chains are not used. |
| `get_alias` | Verified | Returns the first registered alias. |
| `get_bindings` | Verified | Returns a shallow registry snapshot. |
| `tag` | Verified | Stores service keys in insertion order without instantiating them. |
| `tagged` / `tagged_async` | Verified | Resolves tagged services in registration order using the selected mode. |
| `scope` | Adapted | Supports `with` for sync-only graphs and `async with` for async lifecycles. Scope context objects are one-shot. |
| `close` / `aclose` | Verified | Closes owned graph generations in reverse creation order. |
| Async context manager | Verified | Closes the container after the owning context exits. |
| Automatic concrete resolution | Verified | Inspects annotations and composes a validated graph for an unknown root. |
| Graph expansion | Adapted | A new root gets a cached graph. Resolved application and active-scope
  values are seeded into later graphs using public backend APIs. |
| Generator resource cleanup | Verified | Real synchronous generator resources close when the owning scope exits. |
| Async generator resource cleanup | Verified | Real asynchronous generator resources close when the owning scope exits. |
| Shared initialization | Verified | Concurrent graph roots coordinate registered and decorated shared values with per-service locks. |
| Application resource ownership | Verified | Application singletons in a scoped graph are initialized through application-owned generations and remain open until container shutdown. |
| Callable injection | Verified | `call` invokes sync callbacks immediately; `call_async` awaits async callbacks and dependencies. |
| Method callback registration | Verified | `bind_method` dispatches through callable injection. |
| Lazy resolver factory | Verified | `factory` returns a sync resolver; `factory_async` returns an async resolver. |
| Shared root graph cache | Verified | Application-level sync and async operations use the same Dishka async graph and its shared cache. |
| Async-only preflight | Verified | Sync resolution identifies native async factories from annotations before invocation and reports the dependency path. |
| Sync scope graph | Adapted | Scope-local sync graphs are created through Dishka's supported sync container and closed by their owning sync or async scope. |
| Unrelated service laziness | Verified | Only the requested graph's shared dependencies are retained. |
| Registration after first graph | Adapted | Rejected. The registry freezes on first graph composition to avoid unsafe
  live reconfiguration. |
| Graph generation bound | Verified | `max_graph_generations` limits retained global and active-scope graphs. |
| Backend provider interop | Advanced | `providers` accepts explicit integration objects. It is an escape hatch,
  not the ordinary registration API. |

The remaining provider escape hatch belongs to `foundation.Application`,
whose `providers` parameter passes non-native registration values to the
private adapter. Ordinary registration through the native `Container` uses
Titanspan bindings and contracts. Replacing this input is deferred until that
container becomes the application composition root; see the
[backend boundary audit](./backend-boundaries).

Focused evidence is in `tests/unit/container/test_container.py`,
`tests/unit/container/test_execution_modes.py`, and
`tests/unit/container/test_decorators.py`. Existing
FastAPI lifecycle and request-scope evidence remains in
`tests/integration/test_container_lifecycle.py` and
`tests/integration/test_contract_resolution.py`.

## Scope mapping

| Scope names | Backend level | Constraint |
| --- | --- | --- |
| `APPLICATION` | Application | Owned by the container; cannot be entered as a child. |
| `REQUEST`, `CONNECTION`, `JOB`, `WORKFLOW` | Request | These names are equivalent at this level and cannot nest within each other. |
| `NODE`, `AGENT` | Action | These names are equivalent at this level and require an outer execution scope. |
| `TOOL`, `TASK` | Step | These names are equivalent at this level and require a deeper active scope. |

The current backend exposes one ordered scope chain. Titanspan therefore maps
semantic lifetimes onto that chain rather than claiming independent sibling
scope trees. Use separate application containers for lifecycles that must not
share any application-owned state.

Sync scopes use Dishka's synchronous container graph for sync-only services.
Async scopes use the asynchronous graph for async operations. A sync graph
created inside an async scope registers its synchronous close callback with
that scope's async exit stack. This ensures cancellation and exceptions still
close the sync resource before the scope completes.

## Resolution and mutation rules

1. String keys resolve through the registered alias table.
2. A tracked active-scope instance is returned before graph access.
3. A tracked application singleton is returned before graph access.
4. Explicit bindings are included in every composed graph.
5. An unregistered concrete root and its annotated concrete constructor
   dependencies are discovered without constructing objects during inspection.
6. Abstract classes and protocols require explicit bindings.
7. Unannotated required constructor parameters are not guessed; graph
   validation reports a resolution failure.
8. Registration is allowed until the first graph is composed. Later mutation
   raises `BindingError`.
9. The graph limit applies to global graphs plus graphs owned by active scopes.
   A graph that exceeds the configured bound raises `GraphLimitError`.
10. Externally supplied instances registered with `instance` are not closed by
    the container.
11. Application singletons needed by an execution scope are resolved through
    an application-owned graph before the scoped graph is built. This keeps
    generator resources alive until application shutdown.
12. An individual `ContainerScope` context object can be entered only once.
    Create a fresh scope context for each independent lifecycle.
13. Synchronous resolution preflights the known native constructor/factory
    graph. If an async factory is required, it raises
    `AsyncResolutionRequiredError` with a dependency path and recommends
    `make_async`; it does not invoke the async factory.
14. At application scope, `make` uses the async backend graph's documented
    `get_sync`, and `make_async` uses `get`. Both operations share the same
    backend cache. Scope-local sync graphs are tracked separately by execution
    mode, while tracked singleton and scoped instances preserve identity across
    newly composed roots.

## Canonical API names

Use `make` and `make_async` for service resolution, `make_with` and
`make_with_async` when constructor values must be supplied, and `get` or
`get_async` when consuming the `ServiceContainer` contract. The contract
retrieval names are intentionally retained for native Titanspan services.
Redundant `resolve` and `build` forwarding methods are not part of the public
API.

All methods use `snake_case`. Sync and async methods are distinct operations;
neither returns an awaitable conditionally.

## Planned capabilities

Contextual binding, attribute-based injection, service extensions, rebinding,
resolution callbacks, and temporary override stacks are not implemented.
They remain outside the advertised API until their registration and lifecycle
semantics are specified and tested.

## Known limits for this milestone

- Runtime bindings freeze after first graph composition; live rebinding,
  contextual changes, and override stacks are not implemented.
- `make_with`, primitive contextual bindings, configuration injection, and
  custom injection attributes are not implemented. `call` accepts explicit
  named values and resolves only class-typed service parameters.
- `Application` uses this registry as the composition root for framework
  services. FastAPI route dependencies still use the explicit private web
  integration provider boundary and a separate request graph. The raw
  `Application.providers` input remains a transitional interoperability
  surface. No module-level `app()` helper is available.
- Synchronous and asynchronous generator resource factories have lifecycle
  tests, including cleanup when the active task is cancelled. Direct
  context-manager factory forms are not implemented.
- The scope names adapt to one backend hierarchy and do not represent
  independent request, job, and workflow branches.
- Container-level tests verify the native adapter behavior. They do not yet
  establish every planned capability or the requested coverage target.
- Task-group tests verify sync and async operations share one application
  singleton cache and scope tests verify a scoped instance is shared across
  both modes. Cross-thread access to one Dishka graph is not declared safe or
  tested; integrations must not share a graph across worker threads unless
  they provide their own documented synchronization boundary.
- Async resolution inside a synchronous scope is supported only when the
  dependency graph is sync-safe; it delegates to synchronous resolution.
  Async-only resources require an asynchronous scope.

## Scope of this specification

This specification records supported behavior and pending work.
Unimplemented capabilities are not advertised as available.
