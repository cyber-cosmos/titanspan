# Native service container specification

This document is the implementation inventory for the current container
milestone. It distinguishes verified behavior from APIs that still require
implementation. The compatibility reference is pinned in the existing
compatibility inventory; this file records Titanspan-owned behavior and
decisions.

## Reference baseline

The behavior audit is pinned to release `13.44.1`, commit
`8a8c4a84852869e13190d89f9da873cd9a70f14c`. This inventory describes
operations using Titanspan terminology and records implementation status
without copying upstream implementation code.

## Implemented behavior

The public API is defined in `src/titanspan/container/`. The private adapter
composes validated graphs and delegates construction, caching within a graph,
and generator cleanup to the selected dependency engine.

| Native operation | Status | Behavior and evidence |
| --- | --- | --- |
| `Container()` | Verified | Creates an application-owned registry. |
| `bind` | Verified | Registers a transient class or typed factory. |
| `bind_if` / `bindIf` | Verified | Registers only when the key is absent. |
| `singleton` | Verified | Caches one application-owned instance. |
| `singleton_if` / `singletonIf` | Verified | Conditionally registers a singleton. |
| `scoped` | Verified | Caches in the selected active execution scope. |
| `scoped_if` / `scopedIf` | Verified | Conditionally registers a scoped value. |
| `@singleton` | Verified | Declares application-owned lifetime metadata on a class. |
| `@scoped(scope)` | Verified | Declares execution-scope metadata on a class. |
| `instance` | Verified | Registers an externally owned value. |
| `make` / `get` | Verified | Resolves typed keys and named aliases. |
| `bound` | Verified | Checks explicit registration without resolution. |
| `has` | Adapted | Checks explicit keys, aliases, and non-abstract classes; it does not
  prove that a concrete graph can be constructed. |
| `resolved` | Adapted | Reports only cached values observed through this API. |
| `is_shared` / `isShared` | Verified | Reports registered or class-declared cached lifetimes. |
| `is_alias` / `isAlias` | Verified | Checks a registered string alias. |
| `alias` | Verified | Maps a string key to one canonical type; alias chains are not used. |
| `get_alias` / `getAlias` | Verified | Returns the first registered alias. |
| `get_bindings` / `getBindings` | Verified | Returns a shallow registry snapshot. |
| `tag` | Verified | Stores service keys in insertion order without instantiating them. |
| `tagged` | Verified | Resolves tagged services in registration order. |
| `scope` | Adapted | Enters an isolated task-local backend scope and finalizes it on exit. Scope context objects are one-shot. |
| `close` / `aclose` | Verified | Closes owned graph generations in reverse creation order. |
| Async context manager | Verified | Closes the container after the owning context exits. |
| Automatic concrete resolution | Verified | Inspects annotations and composes a validated graph for an unknown root. |
| Graph expansion | Adapted | A new root gets a cached graph. Resolved application and active-scope
  values are seeded into later graphs using public backend APIs. |
| Generator resource cleanup | Verified | Real synchronous generator resources close when the owning scope exits. |
| Async generator resource cleanup | Verified | Real asynchronous generator resources close when the owning scope exits. |
| Shared initialization | Verified | Concurrent graph roots coordinate registered and decorated shared values with per-service locks. |
| Application resource ownership | Verified | Application singletons in a scoped graph are initialized through application-owned generations and remain open until container shutdown. |
| Callable injection | Verified | `call` resolves required annotated service arguments and consumes explicit named values. |
| Method callback registration | Verified | `bind_method` and its camelCase alias dispatch through callable injection. |
| Lazy resolver factory | Verified | `factory` returns an async callable that delegates to normal lifetime rules. |
| Unrelated service laziness | Verified | Only the requested graph's shared dependencies are retained. |
| Registration after first graph | Adapted | Rejected. The registry freezes on first graph composition to avoid unsafe
  live reconfiguration. |
| Graph generation bound | Verified | `max_graph_generations` limits retained global and active-scope graphs. |
| Backend provider interop | Advanced | `providers` accepts explicit integration objects. It is an escape hatch,
  not the ordinary registration API. |

Focused evidence is in `tests/unit/container/test_container.py` and
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

## Public operation inventory

The following reference operations are individually accounted for. A pending
entry is not an advertised Titanspan capability.

| Reference operation | Native operation | Status |
| --- | --- | --- |
| `when` | Contextual binding builder | Pending |
| `whenHasAttribute` | Attribute-sensitive contextual binding | Pending |
| `bound` | `bound` | Verified |
| `has` | `has` | Adapted |
| `resolved` | `resolved` | Adapted |
| `isShared` | `is_shared`, `isShared` | Verified |
| `isAlias` | `is_alias`, `isAlias` | Verified |
| `bind` | `bind` | Verified |
| `hasMethodBinding` | `has_method_binding`, `hasMethodBinding` | Verified |
| `bindMethod` | `bind_method`, `bindMethod` | Verified |
| `callMethodBinding` | `call_method_binding`, `callMethodBinding` | Verified |
| `addContextualBinding` | Contextual registration | Pending |
| `bindIf` | `bind_if`, `bindIf` | Verified |
| `singleton` | `singleton` | Verified |
| `singletonIf` | `singleton_if`, `singletonIf` | Verified |
| `scoped` | `scoped` | Verified |
| `scopedIf` | `scoped_if`, `scopedIf` | Verified |
| `extend` | Service extension | Pending |
| `instance` | `instance` | Verified |
| `tag` | `tag` | Verified |
| `tagged` | `tagged` | Verified |
| `alias` | `alias` | Verified |
| `rebinding` | Rebinding callback | Pending |
| `refresh` | Refresh dependent service | Pending |
| `wrap` | Callable wrapper | Pending |
| `call` | `call` | Verified |
| `factory` | `factory` | Verified |
| `makeWith` | `make_with` | Pending |
| `make` | `make` | Verified |
| `get` | `get` | Verified |
| `build` | Direct construction operation | Pending |
| `resolveFromAttribute` | Native injection attributes | Pending |
| `beforeResolving` | Resolution callbacks | Pending |
| `resolving` | Resolution callbacks | Pending |
| `afterResolving` | Resolution callbacks | Pending |
| `afterResolvingAttribute` | Attribute callbacks | Pending |
| `fireAfterResolvingAttributeCallbacks` | Attribute callbacks | Pending |
| `currentlyResolving` | Resolution diagnostic context | Pending |
| `getBindings` | `get_bindings`, `getBindings` | Verified |
| `getAlias` | `get_alias`, `getAlias` | Verified |
| `forgetExtenders` | Extension reset | Pending |
| `forgetInstance` | Instance reset | Pending |
| `forgetInstances` | Instance reset | Pending |
| `forgetScopedInstances` | Scope reset | Pending |
| `resolveEnvironmentUsing` | Environment selector | Pending |
| `currentEnvironmentIs` | Environment selector | Pending |
| `flush` | Container reset | Pending |
| `offsetExists` | Mapping membership | Not applicable |
| `offsetGet` | Mapping retrieval | Not applicable |
| `offsetSet` | Mapping mutation | Not applicable |
| `offsetUnset` | Mapping deletion | Not applicable |
| Dynamic property access | Python object attributes | Not applicable |

## Known limits for this milestone

- Runtime bindings freeze after first graph composition; live rebinding,
  contextual changes, and override stacks are not implemented.
- `make_with`, primitive contextual bindings, configuration injection, and
  custom injection attributes are not implemented. `call` accepts explicit
  named values and resolves only class-typed service parameters.
- The native `Application` composition root still uses the existing explicit
  web integration provider boundary. It does not yet expose this registry as
  its single application container.
- Synchronous and asynchronous generator resource factories have lifecycle
  tests, including cleanup when the active task is cancelled. Direct
  context-manager factory forms are not implemented.
- The scope names adapt to one backend hierarchy and do not represent
  independent request, job, and workflow branches.
- Container-level tests verify the native adapter behavior. They do not yet
  establish the full upstream API surface or the requested coverage target.

## Compatibility provenance

The exact reference pin is recorded above. Every operation in the public API
audit is classified here or in the method inventory. Pending operations are
not advertised as available, and this specification does not claim complete
one-to-one compatibility.
