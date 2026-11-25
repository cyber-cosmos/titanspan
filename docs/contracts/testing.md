# Testing contracts

Test contract behavior through real or representative implementations.
A protocol declaration alone cannot prove ordering, error behavior, type
relationships, isolation, cancellation, or cleanup.

## Current tests

`tests/unit/contracts/test_contracts.py` checks exported identity, generic
typing surfaces, structural recognition, and the documented configuration
repository shape. `tests/integration/test_contract_resolution.py` registers a
real implementation under the `ConfigRepository` protocol key in the actual
dependency graph.

The integration test verifies the contract as a dependency key. The container
execution-mode tests verify that the native Container implements the
sync-first contract. They do not claim that the private dependency engine
implements a Titanspan protocol or that the in-memory test adapter is a
production configuration repository.

Run focused tests with:

```bash
uv run --locked pytest tests/unit/contracts -q
uv run --locked pytest tests/integration/test_contract_resolution.py -q
```

## Reusable conformance tests

Add a reusable behavioral suite when more than one production implementation
of a contract exists or is planned with concrete semantics. A useful suite
asserts observable behavior against each implementation; it does not merely
check that attributes exist. Include failure and lifecycle cases when the
contract owns errors or resources.

Do not create empty conformance fixtures for cache, queue, filesystem, or
workflow protocols before their contracts and implementations are established.
