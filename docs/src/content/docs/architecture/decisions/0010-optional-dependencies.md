---
title: "ADR 0010: Optional Dependencies (Superseded)"
---

<span id="adr-0010-optional-dependencies"></span>

- Status: Superseded by [ADR 0025](../0025-batteries-included-components/)
- Date: 2026-11-24

## Context

Long-term scope includes databases, AI models, queues, Redis, mail, storage,
and observability. Most applications will not use every integration.

## Historical decision

Keep the core dependencies limited to the initial application lifecycle,
dependency injection, typed settings, and CLI. This decision was superseded
when Titanspan adopted mandatory dependencies for implemented native
components and reserved extras for external integrations.

## Alternatives considered

- Install every preferred technology by default: rejected because it increases
  install size and couples unrelated applications to unneeded services.
- Publish extras before integrations exist: rejected because installability
  alone is not supported functionality.
- Use undeclared optional libraries: rejected because it causes runtime errors.

## Consequences

Each integration defines its extra and version bounds with its tests. CI should
test the core install and selected extras independently.

## Risks

Optional combinations multiply quickly. Keep a small supported matrix and use
Dependabot and vulnerability auditing.

## References

- [PEP 621 optional dependencies](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dependencies-optional-dependencies)
- [uv dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/)
