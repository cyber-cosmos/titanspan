# ADR 0011: Testing and Quality Standards

- Status: Accepted
- Date: 2026-11-24

## Context

The framework's value depends on predictable lifecycle, concurrency, and
integration behavior. A passing linter cannot establish runtime correctness.

## Decision

Use Pytest, pytest-cov with an initial 90 percent coverage gate, Ruff for
linting and formatting, and strict Pyright for static analysis. Use
test-driven development for meaningful functionality. Keep performance tests
informational on shared CI runners.

## Alternatives considered

- Manual testing only: rejected because behavior would not be repeatable.
- Coverage as the sole quality measure: rejected because it does not prove
  useful assertions.
- Strict wall-clock thresholds on shared runners: rejected because runner
  variance is high.
- Blanket typing ignores: rejected because they hide boundary problems.

## Consequences

Capabilities include tests for success, failure, and cleanup where applicable.
Local make check is read-only and mirrors the core CI quality commands.

## Risks

A numerical coverage threshold can encourage shallow tests. Review behavioral
assertions and adjust the threshold only with evidence and an explicit decision.

## References

- [pytest](https://docs.pytest.org/en/stable/)
- [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/)
- [Ruff](https://docs.astral.sh/ruff/)
- [Pyright](https://microsoft.github.io/pyright/)

