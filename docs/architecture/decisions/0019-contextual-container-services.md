# ADR 0019: Contextual container services and temporary overrides

- Status: Accepted
- Date: 2026-11-26
- Supersedes: Pending capability statements in ADR 0014 and ADR 0015

## Context

The container already owns bindings, dependency discovery, execution scopes,
and the application service graph. Application services also need a safe way
to choose per-consumer implementations, inject configuration and tagged
services, decorate resolved values, observe public resolution, and substitute
services temporarily. Rebuilding or mutating a live graph would endanger
scoped resources and shared instance identity.

## Decision

- Add immutable consumer-specific rules through
  `Container.when(...).needs(...)`. Rules select an implementation or factory,
  a literal value, a `ConfigReader` value, a registered alias, or an ordered
  tag. Configuration injection requires its implementation to provide the
  optional `TypedConfigReader` capability. Missing and incompatible values
  use its existing accessors; no second validation engine is added.
- Support Titanspan-owned `Annotated` metadata: `Inject`, `FromConfig`,
  `Named`, and `Tagged`. A shared private selector enforces one precedence
  policy across graph construction and callable injection.
- Apply explicit call arguments first, contextual rules second, metadata
  third, and ordinary binding or automatic resolution after those sources.
  Python defaults apply when no source is selected.
- Delegate service decoration to Dishka's public provider decoration API.
  Sync and async extension functions retain native resolution-mode behavior.
  Extensions that wrap owned resources must forward cleanup through their
  wrapper.
- Add `before_resolving`, `resolving`, and `after_resolving` hooks for public
  root lookups. Hooks run in phase order, including for cached retrievals;
  nested dependencies created internally by a graph do not emit individual
  hook events. Async hooks require explicit async resolution.
- Keep registration frozen after graph composition. Do not offer arbitrary
  live rebinding or cache invalidation.
- Provide `Container.override` as a context-local graph overlay supporting
  synchronous and asynchronous entry. Sync entry composes sync graph owners;
  async entry supports async factories and finalizers. Nested overrides
  restore in LIFO order. Replacement values belong to the overlay; unaffected
  application singletons and their per-service locks are shared with the
  canonical cache. If a requested singleton depends on an overridden service,
  reject resolution rather than return or retain a singleton built from the
  original dependency. Finalize resources before restoring the prior context,
  shield async cleanup from cancellation, and prevent shutdown while an
  override remains active.
- Require overrides to begin before execution scopes. The existing scope
  hierarchy and scope ownership model remain unchanged.

## Alternatives considered

### Mutate and rebuild the live graph

Rejected because existing execution scopes may retain resources from the old
graph, and a rebuilt graph could duplicate or prematurely finalize cached
application singletons.

### Implement a parallel constructor resolver

Rejected because the backend already owns dependency construction, graph
validation, caching, and resource finalization. Native metadata is adapted to
graph sources while the backend remains the construction authority.

### Use one synchronous lifecycle for every override

Rejected because async factories and resource finalizers require explicit
awaiting. Sync-safe replacements use the supported synchronous graph backend;
async-only replacements require the asynchronous context form.

## Consequences

Applications can select dependencies per consumer and provide temporary
substitutions without mutating the application registry. Explicit arguments
remain highest priority. Ordinary dependency resolution remains synchronous
when the graph is sync-safe; async factories, extensions, callbacks, or
resource lifecycles require explicit async APIs.

The supported injection markers are intentionally limited to four native
metadata classes. Arbitrary union inference and custom marker handlers are not
implemented. Resolution callbacks observe public root requests only.
Decorators must preserve the service contract and forward cleanup for resources
they wrap. Runtime binding mutation after graph composition remains
unsupported.

## Verification

`tests/unit/container/test_contextual_injection.py` verifies consumer
isolation, metadata sources, precedence, `make_with`, async extension and
callback preflight, callback ordering, nested overrides, cancellation-safe
cleanup, shared singleton identity, and concurrent task-local overrides.
Container integration tests exercise real Dishka graph composition and
resource lifecycle. The sync override regression exercises a synchronous
resource factory, shared application identity, and exception restoration.
`tests/integration/test_framework_cohesion.py` verifies
the context-local `app()` helper and cross-component resolution.
