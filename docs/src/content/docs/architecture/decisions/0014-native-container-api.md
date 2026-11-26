---
title: "ADR 0014: Native service container API"
---

<span id="adr-0014-native-service-container-api"></span>

- Status: Accepted for container graph behavior; application composition
  integration is superseded by ADR 0018
- Date: 2026-11-25

> Status update: The native container now composes framework services in
> `Application`. Explicit FastAPI dependency injection retains an interoperability bridge; see
> ADR 0018. Contextual injection, service extensions, resolution callbacks,
> and sync/async task-local overrides were subsequently implemented with the
> constraints recorded in ADR 0019.

## Context

Applications need a Titanspan-owned registration and resolution surface while
the framework continues to use a mature graph resolver for construction and
resource cleanup. The first application integration exposed backend provider
types directly and required every class to be registered before startup.

The new API also needs to resolve concrete typed graphs discovered after the
container is created. The selected resolver validates a graph at composition
time and does not document in-place graph mutation. Replacing a live graph
could invalidate singleton and scoped resources.

## Decision

- Add `titanspan.container.Container`, native binding and lifetime metadata,
  typed aliases, tags, declarative class lifetime decorators, and owned
  execution scopes.
- Keep all direct resolver imports in `container._backends`.
- Discover constructor type dependencies without creating service instances;
  pass the resulting class set to the resolver for graph construction.
- Compose and cache one graph for each newly requested root. Do not rebuild a
  graph for repeated resolutions of the same root.
- Keep application graph generations on the container. Keep graph generations
  discovered inside an execution scope on that scope and close them when the
  scope exits.
- Seed tracked shared values into later generations through public context
  registration APIs. Close newer generations before earlier generations so
  borrowed values outlive their consumers.
- Track only the requested root's dependency closure for lazy shared-value
  capture. Use per-service async locks to preserve shared identity across
  concurrent graph generations.
- Resolve uncached application singletons through an application-owned graph
  before creating a shorter-lived graph that depends on them. This keeps
  generator-backed singleton cleanup attached to application shutdown.
- Treat each scope context object as one-shot because it owns closed backend
  child graphs and cannot safely reopen those resources.
- Freeze registration after first graph composition. Contextual injection and
  temporary sync/async overrides are implemented in ADR 0019; arbitrary live
  rebinding remains unsupported.
- Bound retained generations with a configurable default limit of 128.
- Map semantic execution scope names onto the existing ordered backend scope
  levels. Document equivalent-level and nesting limitations instead of
  claiming independent scope trees.
- Preserve the existing web application integration during this milestone.
  The native container is not yet the application's single composition root.

## Consequences

Applications can use a typed native API and resolve unregistered concrete
constructor graphs. Graph composition still validates the whole provider
graph. Dynamic root graphs are retained for the owning application or scope,
and the explicit limit prevents unbounded root metadata growth.

At the time this decision was accepted, contextual bindings, primitive
injection, custom metadata, extensions, resolution callbacks, and overrides
were pending. The current implementation and its verified limits are recorded
in `docs/src/content/docs/specifications/container.md` and ADR 0019. Safe live rebinding remains
unsupported because registrations freeze after graph composition.

## Verification required for future changes

Any change to dynamic graph ownership must retain regression tests for
application singleton identity, overlapping execution scopes, generator
resource cleanup, concurrent discovery, and cleanup after cancellation. A
future application integration must use one lifecycle owner for HTTP, direct
resolution, configuration, and logging services.

The synchronous-first execution model and explicit async alternatives were
adopted after this decision. See [ADR 0015](/titanspan/architecture/decisions/0015-sync-first-container-resolution/)
for the resolution-mode contract and mixed-mode cache guarantees.
