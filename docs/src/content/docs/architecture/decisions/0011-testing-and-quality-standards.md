---
title: "ADR 0011: Testing and Quality Standards"
---

<span id="adr-0011-testing-and-quality-standards"></span>

- Status: Accepted
- Date: 2026-11-24

## Context

The framework's value depends on predictable lifecycle, concurrency, and
integration behavior. A passing linter cannot establish runtime correctness.

## Decision

Use Pytest and Red-Green-Refactor for meaningful behavior changes. Require
real unit and integration tests for implemented contracts and dependency
boundaries. Enforce at least 95 percent statement coverage and 90 percent
branch coverage independently for first-party runtime code. Ruff enforces
strict linting and formatting; a repository AST checker additionally enforces
80-column lines and physically multi-line docstrings. Pyright checks runtime
code, tests, examples, benchmarks, and development scripts in strict mode.
Yamllint enforces two-space YAML indentation. Import Linter enforces the
implemented core dependency direction. Keep performance tests informational
on shared CI runners.

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
Contributors must not disable checks or lower thresholds to make a change
pass. Significant policy edits require focused justification and independent
maintainer review.

## Risks

A numerical coverage threshold can encourage shallow tests. Review behavioral
assertions and retain direct integration coverage for critical behavior.
More coverage does not substitute for useful assertions.

## References

- [pytest](https://docs.pytest.org/en/stable/)
- [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/)
- [Ruff](https://docs.astral.sh/ruff/)
- [Pyright](https://microsoft.github.io/pyright/)
