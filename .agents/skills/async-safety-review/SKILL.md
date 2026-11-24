---
name: async-safety-review
description: Review asynchronous Python changes for task ownership, cancellation, bounds, blocking calls, and cleanup.
---

# Async safety review

## When to use

Use for async APIs, background tasks, workers, streaming, database access,
shutdown, or changes that process concurrent or unbounded work.

## References

- Root and nearest scoped `AGENTS.md`
- `ARCHITECTURE.md`, especially async, database, and lifecycle sections
- ADR 0002 and ADR 0008
- Official AnyIO and relevant dependency documentation

## Procedure

1. Trace each task from creation to completion and identify its owner.
2. Trace cancellation and timeout propagation through nested calls.
3. Check for blocking I/O or CPU work on the event loop.
4. Check that concurrency, queue depth, buffers, batches, and memory are
   bounded and that streams apply backpressure.
5. Check mutable state and SQLAlchemy async session isolation.
6. Check retry idempotency, partial failures, and cleanup after cancellation
   and shutdown.
7. Recommend deterministic tests for each discovered boundary.

## Failure modes

- Assuming async/await alone provides scalability.
- Unbounded `gather`, task-per-row fanout, or whole-dataset materialization.
- Detached tasks, lost cancellation, missing timeouts, or hidden synchronous
  I/O.
- Shared async sessions or resources used after shutdown.
- Retrying non-idempotent side effects without protection.

## Validation

Run targeted tests for timeout, cancellation, concurrent scope isolation,
failure cleanup, and backpressure as applicable. Run `make check` for code
changes. Benchmarks must follow `benchmarks/AGENTS.md`.

## Completion criteria

Task ownership, concurrency bounds, cancellation, resource lifetime, and
failure semantics are explicit or concrete gaps are reported with file paths.
