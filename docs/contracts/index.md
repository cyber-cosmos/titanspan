# Contracts

Titanspan contracts define framework-owned behavior at component boundaries.
They let application code depend on stable Python protocols while adapters
delegate infrastructure to mature libraries.

## Current public contracts

The package currently exports:

- `ConfigRepository`, a structural interface for mutable configuration.
- `AsyncServiceContainer`, a typed async resolution and cleanup interface.
- `InstanceRegistration`, a native contract for supplying an existing service
  instance to the active container adapter.
- Support data and presentation protocols such as `Arrayable`, `Jsonable`,
  `Renderable`, `Responsable`, and `ValidatedData`.
- Existing canonical Support protocols for HTML values and message bags.

The logging contracts remain canonically owned by
`titanspan.logging.contracts`; they are not duplicated in this package.
Contracts for unimplemented cache, database, queue, workflow, and other
components remain pending in the [Laravel compatibility inventory](
/compatibility/laravel-contracts).

These interfaces describe substitution points. Defining a protocol does not
mean a production implementation or complete framework feature exists.
The configuration component provides the native `Repository` implementation
of `ConfigRepository`; application startup registers it through the private
container adapter. `titanspan.container.Container` implements
`AsyncServiceContainer` and keeps graph-engine types out of its public API.
`ConfigRepository.get` accepts either one path or an ordered sequence of
paths. The concrete Repository also exposes `get_many` and `getMany`, strict
typed accessors, mapping behavior, and Support macros. Those additions are not
required of every structural implementation. Pydantic Settings remains the
private validation backend for Titanspan's native `Settings` type.

## Structural typing

Protocols are structural: an implementation can satisfy one without
inheriting from it. `@runtime_checkable` allows basic attribute-presence checks,
but does not verify signatures, return types, resource cleanup, cancellation,
or other behavioral guarantees. Use static checking and behavior tests for
those guarantees.

Prefer Python snake_case APIs. Separate compatibility protocols accept
Laravel's original camelCase spellings where useful; implementations do not
need to implement both spellings unless their own public API promises both.

## Guides

- [Dependency injection](./dependency-injection)
- [Implementing contracts](./implementing-contracts)
- [Testing contracts](./testing)
- [Laravel Contracts inventory](/compatibility/laravel-contracts)
