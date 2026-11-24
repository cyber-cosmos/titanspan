# ADR 0009: Contract-Driven Adapters

- Status: Accepted
- Date: 2026-11-24

## Context

Planned modules span databases, queues, caches, AI providers, storage, and
telemetry. The framework needs cohesive APIs without locking every application
to one backend.

## Decision

Define small typed protocols or interfaces at real substitution and lifecycle
boundaries. Keep library-specific adapters at module edges and compose them
through providers. Preserve access to native library objects.

Add a contract when it enables replacement, lifecycle ownership, a test seam,
or stable public behavior. Do not wrap a single function without a real need.

## Alternatives considered

- Use backend libraries with no conventions: rejected for framework lifecycle
  and testing needs.
- Wrap every library type in a duplicate: rejected because it obscures native
  capabilities.
- Inheritance-heavy base classes: rejected in favor of composition and
  structural typing.

## Consequences

Contracts stay small and behavior-focused. Fakes can test application behavior
without a live service.

## Risks

Over-generalized protocols can hide backend features. Keep native escape
hatches and review contracts alongside concrete adapters.

## References

- [Python Protocols](https://docs.python.org/3/library/typing.html#typing.Protocol)
- [PEP 544](https://peps.python.org/pep-0544/)

