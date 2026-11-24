# ADR 0008: Structured Concurrency

- Status: Accepted for planned concurrency APIs
- Date: 2026-11-24

## Context

Tasks need predictable ownership, bounded parallelism, cancellation
propagation, and cleanup across requests, jobs, and workflows.

## Decision

Use AnyIO as the planned async concurrency foundation. Build conventions around
task groups, capacity limiters, cancellation scopes, and bounded work queues.
Do not expose unstructured task creation as the default.

AnyIO is currently transitive through FastAPI's stack. Declare it directly
only when Titanspan exposes a concurrency API.

## Alternatives considered

- Direct asyncio primitives everywhere: rejected as the sole abstraction
  because AnyIO supports multiple async backends.
- Unbounded asyncio.gather: rejected for large or unbounded inputs.
- Process pools for all concurrency: rejected because they do not solve
  asynchronous I/O concurrency.

## Consequences

Cancellation and capacity become API behavior. CPU-bound work remains a
separate process or native-library concern.

## Risks

Backend portability can be lost if adapters leak event-loop assumptions. Test
supported backends where practical.

## References

- [AnyIO documentation](https://anyio.readthedocs.io/en/stable/)
- [Python concurrent futures](https://docs.python.org/3/library/concurrent.futures.html)
