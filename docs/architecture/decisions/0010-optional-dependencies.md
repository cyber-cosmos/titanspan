# ADR 0010: Optional Dependencies

- Status: Accepted
- Date: 2026-11-24

## Context

Long-term scope includes databases, AI models, queues, Redis, mail, storage,
and observability. Most applications will not use every integration.

## Decision

Keep the core dependencies limited to the initial application lifecycle,
dependency injection, typed settings, and CLI. Add integration extras only
when the related APIs are implemented, tested, documented, and installable. Do
not publish empty extras or imply planned modules work.

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

