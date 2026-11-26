---
title: "Native service container specification"
---

<span id="native-service-container-specification"></span>

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
| `when(...).needs(...).give(...)` | Verified | Adds consumer-specific implementation, value, configuration, alias, or tag sources before graph composition. |
| `Annotated` metadata | Verified | `Inject`, `FromConfig`, `Named`, and `Tagged` select native dependency sources. |
| `extend` | Verified | Adds ordered sync or async decorators through the backend's supported provider API. |
| Resolution callbacks | Verified | `before_resolving`, `resolving`, and `after_resolving` wrap public root lookups, including cached values. |
| `override` | Adapted | A dual sync/async context creates a task-local overlay; each mode owns matching graph cleanup. |
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
| Shared initialization | Adapted | Async graph resolutions coordinate registered and decorated shared values with per-service async locks. Concurrent sync `get_sync` calls from worker threads do not share that lock and can initialize one application singleton more than once; see the framework review. |
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
| Active application helper | Verified | `titanspan.app()` returns the active `Application`; use `.container` for its canonical service container. |

The remaining provider escape hatch belongs to `foundation.Application`,
whose `providers` parameter passes explicit interoperability registrations to
the private adapter. Ordinary registration through the native `Container`
uses Titanspan bindings and contracts. It remains available only for
third-party integration; see the [backend boundary audit](/titanspan/specifications/backend-boundaries/).

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
| `REQUEST`, `CONNECTION`, `JOB`, `WORKFLOW` | Request | One execution level; these names cannot nest within each other. |
| `NODE`, `AGENT` | Action | One execution level; these names cannot nest within each other. |
| `TOOL`, `TASK` | Step | One execution level; these names cannot nest within each other. |

The supported nesting chains are `APPLICATION` → one request-level scope →
one action-level scope → one step-level scope. A request-level scope may be
`REQUEST` for HTTP, `JOB` for background work, or `WORKFLOW` for a workflow.
For example, `REQUEST` → `NODE` → `TOOL` is supported, as is
`WORKFLOW` → `AGENT` → `TASK`. `REQUEST` → `WORKFLOW`, `NODE` → `AGENT`, and
`TOOL` → `TASK` are not supported nested combinations because each pair maps
to the same Dishka level. Use sequential sibling scopes at that level when
their lifecycles do not overlap. The backend exposes one ordered scope chain,
not separate HTTP, job, and workflow branches. Lifecycles that must overlap
as independent request and workflow scopes need separate containers or an
external owner; separate containers do not share application singletons.

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
8. Bindings, contextual rules, extensions, and callbacks are registered before
   first graph composition. Later mutation raises `BindingError`; use a
   temporary override for task-local substitution.
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
    backend cache. This does not guarantee single-flight initialization when
    concurrent worker threads call `get_sync`; async locks do not coordinate
    those calls. Scope-local sync graphs are tracked separately by execution
    mode, while tracked singleton and scoped instances preserve identity across
    newly composed roots after initialization.

## Canonical API names

Use `make` and `make_async` for service resolution, `make_with` and
`make_with_async` when constructor values must be supplied, and `get` or
`get_async` when consuming the `ServiceContainer` contract. The contract
retrieval names are intentionally retained for native Titanspan services.
Redundant `resolve` and `build` forwarding methods are not part of the public
API.

All methods use `snake_case`. Sync and async methods are distinct operations;
neither returns an awaitable conditionally.

## Contextual injection and lifecycle hooks

`Container.when(Consumer).needs(selector)` registers a rule for one or more
consumer classes. `give` selects a service implementation or typed factory;
`give_value` supplies a literal; `give_config` reads through the registered
`ConfigReader` and its optional `TypedConfigReader` capability; `give_named`
selects a registered alias; and `give_tagged`
resolves tagged services in registration order.

Constructor and callable source precedence is deterministic:

1. Explicit values supplied to `make_with`, `make_with_async`, `call`, or
   `call_async`.
2. A matching consumer-specific contextual rule.
3. A supported `Annotated` marker (`Inject`, `FromConfig`, `Named`, or
   `Tagged`).
4. An ordinary binding or automatic concrete resolution.
5. A Python parameter default when no source is selected.

Explicit values remain present when they are `None`, `False`, zero, or an
empty collection. Conflicting supported injection markers raise
`BindingError`. Contextual rules affect only their selected consumers.
`FromConfig` reads through the registered `ConfigReader`, whose implementation
must provide the optional `TypedConfigReader` capability. Missing and
incompatible values use the configuration component's existing typed
accessors. Supported annotations are `str`, `int`, `float`, `bool`, `dict`,
`list`, and `Mapping`. Both bare `dict` and `list` annotations and their
parameterized forms are supported. The selected collection annotation must
match the outer value returned by `TypedConfigReader.array`: list annotations
require a list, dict annotations require a dictionary, and Mapping
annotations require a mapping. Element and key/value types are not checked
recursively. Other annotations fail during resolution before the consumer is
constructed. The application provider registers the optional capability
when its repository implements it.

`extend` decorates a service in registration order through the backend's
supported graph pipeline. The final value is cached according to the binding
lifetime. Decorators that wrap resources must forward cleanup to resources
they own. Sync decorators work through `make`; async decorators require
`make_async` and are detected before sync resolution constructs or caches a
partial value.

`before_resolving`, `resolving`, and `after_resolving` run for each public root
lookup, including cached values. The order is before hooks, resolution,
resolving hooks, then after hooks. A failure stops later phases and propagates.
Async callbacks require explicit async resolution. Hooks do not observe each
dependency created internally by a backend graph. Recursive resolution of
the same service from a callback is rejected to avoid an uncontrolled loop.

## Temporary overrides

`Container.override` returns a context object that supports both sync and async
entry. Use synchronous entry for graphs with synchronous factories and
finalizers:

```python
with container.override({Repository: FakeRepository}):
    service = container.make(DocumentService)
```

Use asynchronous entry when a replacement requires asynchronous resource
initialization or cleanup:

```python
async with container.override({Repository: FakeRepository}):
    service = container.make(DocumentService)
```

Overrides are context-local and nest in LIFO order. Replacement values and
their resources belong to the temporary graph. Unaffected application
singletons share the canonical application cache and per-service locks,
including when first initialized concurrently from an overlay. Before an
overlay borrows an application singleton, it compares that singleton's
owner-composed dependency graph with replacements introduced by the overlay.
Resolution raises `ScopeError` if a replacement would be hidden by the
owner's cached graph, whether the singleton was already initialized or not.
Each nested overlay is checked against its immediate owner's graph as
resolution delegates outward. Replacing the singleton in the active overlay
creates a value in that overlay's graph and lets it use that overlay's
dependencies. Closing an overlay does not close borrowed application
singletons. Cleanup is shielded from cancellation before the previous context
is restored.

The synchronous context composes through the supported synchronous backend
and closes its resources immediately. Async resolution inside that context is
allowed only when its graph remains synchronous; async-only dependencies fail
before initialization with guidance to use `async with`. The asynchronous
context supports async factories and finalizers.

Enter overrides before opening execution scopes. The container rejects an
override entered inside an active scope, and rejects shutdown while an
override remains active. Bindings still freeze when a graph is first
composed; temporary overlays are the supported substitution mechanism after
that point. Arbitrary live rebinding is not supported.

## Known limits

- Runtime bindings freeze after first graph composition. Synchronous overrides
  cannot initialize async-only dependencies; use the asynchronous context for
  those resources.
- `Annotated` injection is limited to the four documented Titanspan markers.
  Arbitrary union inference and custom metadata handlers are not implemented.
- Contextual rules have no runtime removal or mutation operation.
  `ConfigReader` must be registered for `FromConfig` or `give_config`, and its
  implementation must provide `TypedConfigReader`; collection injection
  checks only the requested outer shape, not nested element or key/value
  types.
- Service extensions must preserve the selected contract and forward cleanup
  when wrapping owned resources. Ownership of arbitrary user wrappers cannot
  be inferred.
- Resolution hooks wrap public root lookups only; nested backend-created
  dependencies do not emit separate callback events.
- `Application` uses this registry as the composition root for framework
  services. Use `Application.dependency` for HTTP handlers that consume native
  services; it resolves through the active application container and request
  scope. Explicit `Application.providers` values remain an advanced
  interoperability boundary with a separate provider graph. The
  `titanspan.app()` returns the active `Application`, and its `.container`
  exposes the same service registry; ordinary Titanspan services do not need
  the provider graph.
- Synchronous and asynchronous generator resource factories have lifecycle
  tests, including cleanup when the active task is cancelled. Direct
  context-manager factory forms are not implemented.
- The scope names adapt to one backend hierarchy and do not represent
  independent request, job, and workflow branches.
- Component coverage remains subject to the repository-wide line and branch
  coverage gates; passing isolated tests alone does not prove completeness.
- Task-group tests verify sync and async operations share one application
  singleton cache and scope tests verify a scoped instance is shared across
  both modes. Cross-thread access to one Dishka graph is not declared safe or
  tested; integrations must not share a graph across worker threads unless
  they provide their own documented synchronization boundary.
- Async resolution inside a synchronous scope is supported only when the
  dependency graph is sync-safe; it delegates to synchronous resolution.
  Async-only resources require an asynchronous scope.

## Dishka delegation audit

The locked backend is Dishka 1.10.1. The adapter uses its public
`Provider.provide`, `provide_all`, `from_context`, and `decorate` operations,
`make_container` / `make_async_container`, async `get`, sync `get_sync`, child
scope contexts, and `close`. These operations remain responsible for graph
validation, dependency construction, per-graph caching, and generator resource
finalization. No backend internals are patched or imported by the native
container.

Some metadata adaptation remains native because Dishka does not implement
Titanspan's consumer-specific `when(...).needs(...).give_*` precedence or its
`FromConfig`, `Named`, and `Tagged` markers. Private synthetic dependency keys
let Dishka resolve these selected values while retaining its construction,
cache, and cleanup ownership. Reachable-type inspection is also retained to
compose only the requested closure, preflight async-only paths, and track
shared values across the dynamically generated Dishka graphs. Per-service
async locks coordinate first construction across asynchronous graph caches.
They do not protect synchronous ``get_sync`` calls from worker threads.
Dishka's own per-container lock cannot synchronize distinct graph containers.
Temporary overlays are composed with the public provider API because a
validated Dishka graph is fixed after construction. They do not reimplement
object construction or resource finalization.

No alternative dependency engine or backend is introduced. A future
consolidation of graph generations would need to preserve automatic concrete
roots, contextual source precedence, shared identity, async preflight, and
scope-owned cleanup together; deleting discovery or overlay code alone would
weaken those behaviors.

## Scope of this specification

This specification records supported behavior and pending work.
Unimplemented capabilities are not advertised as available.
