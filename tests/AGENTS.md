# Test suite instructions

Follow root `AGENTS.md` and `docs/development/standards.md`. This tree verifies
implemented Titanspan behavior; it does not make planned APIs real.

- Use Pytest and test-driven development for meaningful behavior. Add a
  focused regression test before implementation and confirm the failure is
  relevant.
- Every test, fixture, class, and test module must have a physically
  multi-line Google-style docstring and complete annotations. Use comments to
  explain tricky setup, synchronization, and assertions rather than narrate
  ordinary test code.
- Assert public contracts and observable behavior. Mocks may isolate external
  boundaries but must not replace the behavior under test.
- Write genuine integration tests for implemented library boundaries. A
  mocked method call alone does not establish integration behavior.
- Cover failure, resource cleanup, cancellation, scope isolation, concurrency,
  and validation when relevant.
- Keep tests deterministic, isolated, and free of paid services or live AI
  calls. Do not weaken assertions, skip tests, or lower coverage to mask a
  defect.
- Meet the independent 95% line and 90% branch coverage thresholds. Use
  `make unit-test`, `make integration-test`, `make coverage`, and `make check`
  as applicable; report actual results.
