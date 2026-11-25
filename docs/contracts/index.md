# Contracts

Titanspan contracts define framework-owned behavior at component boundaries.
They let components depend on stable Python protocols while private adapters
delegate infrastructure to mature libraries.

## Current public contracts

The package currently exports:

- `ConfigRepository`, a structural interface for mutable configuration.
- `ServiceContainer`, a typed sync-first resolution and cleanup interface.
- `AsyncServiceContainer`, an async-only resolution and cleanup interface for
  consumers that inherently require asynchronous resolution.
- `InstanceRegistration`, a native contract for supplying an existing service
  instance to the active container adapter.
- Support display and message protocols for HTML values and message bags.
- Logging protocols for drivers, formatters, processors, async delivery, and
  logger customization, plus the shared `DeliveryStatus` enum.

Contracts for unimplemented cache, database, queue, workflow, and other
components remain pending. The [native Contracts specification](
/specifications/contracts) records established boundaries and deferred work.

These interfaces describe substitution points. Defining a protocol does not
mean a production implementation or complete framework feature exists.
Generic conversion, HTTP response, and validation protocols remain unpublished
until their owning components establish a real behavioral boundary.
The configuration component provides the native `Repository` implementation
of `ConfigRepository`. Application startup registers it through the
application-owned `titanspan.container.Container`. Framework service
resolution, provider registration, facades, configuration, and logging share
that native application container. The ASGI route integration remains a
separate private graph adapter.
Domain packages own each protocol: `config`, `container`, `logging`, and
`support`. `titanspan.contracts` re-exports the same objects for convenience;
component packages may also expose those objects without creating new
identities. `ConfigRepository.get` accepts one path or an ordered sequence of
paths. The concrete `Repository` also exposes `get_many`, strict typed
accessors, mapping behavior, and Support macros. Those additions are not
required of every structural implementation. Pydantic Settings supplies
validation for Titanspan's typed `Settings` declaration through a private
adapter; inherited backend methods are not part of the documented API.

## Structural typing

Protocols are structural: an implementation can satisfy one without
inheriting from it. `@runtime_checkable` allows basic attribute-presence checks,
but does not verify signatures, return types, resource cleanup, cancellation,
or other behavioral guarantees. Use static checking and behavior tests for
those guarantees.

Use one canonical Python `snake_case` spelling for each operation. Do not
define compatibility protocols or duplicate method names solely to imitate an
external framework's API.

## Guides

- [Dependency injection](./dependency-injection)
- [Implementing contracts](./implementing-contracts)
- [Testing contracts](./testing)
- [Native Contracts specification](/specifications/contracts)
