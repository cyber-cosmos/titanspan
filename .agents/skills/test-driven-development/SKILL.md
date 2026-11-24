---
name: test-driven-development
description: Develop or fix Titanspan behavior with a focused failing regression test before implementation.
---

# Test-driven development

## When to use

Use for meaningful runtime behavior, regressions, public APIs, configuration,
resource lifecycles, or concurrency changes.

## References

- Root and `tests/AGENTS.md`
- `docs/development/standards.md`
- Existing tests for the affected module
- `pyproject.toml` for markers and coverage rules

## Procedure

1. Inspect existing behavior and test conventions.
2. Write the narrowest test that expresses the requested contract or defect.
3. Run that test and confirm it fails for the intended reason.
4. Implement the smallest change that makes it pass.
5. Add cases for meaningful failure, cleanup, concurrency, or boundary
   conditions.
6. Refactor only while the focused tests remain green.
7. Run the full relevant suite and `make check`.

## Failure modes

- Writing tests that only assert a mock was called.
- Testing private implementation details instead of observable behavior.
- Marking a failing test skipped or weakening it to avoid a defect.
- Creating flaky timing assertions or tests that need commercial services.
- Claiming the test-first sequence happened when it did not.

## Validation

Use `uv run --locked pytest path/to/test_file.py -q` for focused tests,
`make test` for the test suite, and `make check` for the read-only quality
gate. Use integration or stress targets where relevant.

## Completion criteria

The new or changed contract has deterministic regression coverage, the
relevant checks pass, and failures/skipped checks are reported honestly.
