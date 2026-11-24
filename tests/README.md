# Test organization

- `unit/` checks one public behavior at a time.
- `integration/` checks framework behavior across library boundaries.
- `feature/` is for user-visible flows spanning multiple modules.
- `performance/` is for repeatable performance tests, not shared-runner gates.
- `stress/` checks repeated or high-volume behavior.
- `fixtures/` holds shared fixtures only when more than one test needs them.

Shared pytest configuration belongs in `conftest.py`. Keep one-off fixtures
near the tests that use them.
