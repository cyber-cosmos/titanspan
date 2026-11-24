# ADR 0001: Modular Monolith

- Status: Accepted
- Date: 2026-11-24

## Context

Titanspan will bring web, AI workflows, concurrency, persistence, and production
infrastructure into one developer experience. Separate services would add
deployment and coordination costs before stable module contracts exist.

## Decision

Start as one Python distribution with explicit module boundaries. Keep module
dependencies directional, integrate optional infrastructure through contracts
and providers, and extract a separate distribution only when a real deployment
or release boundary requires it.

## Alternatives considered

- Independently released packages: rejected because contracts are not stable.
- One unstructured package: rejected because dependency direction would be
  difficult to maintain.

## Consequences

One install and one version simplify onboarding. Boundaries still need tests
and review. Module ownership and import direction must remain explicit.

## Risks

Convenience imports could bypass contracts. Add automated import checks when
the module graph grows.

## References

- [Python packaging user guide](https://packaging.python.org/en/latest/)
- [Laravel service container](https://laravel.com/docs/12.x/container)
