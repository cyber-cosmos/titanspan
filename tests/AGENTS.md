# Test suite instructions

Follow root `AGENTS.md` and `docs/development/standards.md`. This tree verifies
implemented Titanspan behavior; it does not make planned APIs real.

- Use Pytest and test-driven development for meaningful behavior. Add a
  focused regression test before implementation and confirm the failure is
  relevant.
- Assert public contracts and observable behavior. Mocks may isolate external
  boundaries but must not replace the behavior under test.
- Cover failure, resource cleanup, cancellation, scope isolation, concurrency,
  and validation when relevant.
- Keep tests deterministic, isolated, and free of paid services or live AI
  calls. Do not weaken assertions, skip tests, or lower coverage to mask a
  defect.
- Use `make test`, `make coverage`, `make integration-test`, and `make check`
  only where applicable; report actual results.
