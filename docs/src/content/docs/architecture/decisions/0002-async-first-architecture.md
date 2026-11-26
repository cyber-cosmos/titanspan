---
title: "ADR 0002: Async-First Architecture"
---

<span id="adr-0002-async-first-architecture"></span>

- Status: Accepted
- Date: 2026-11-24

## Context

Expected workloads include network services, AI providers, queues, streaming,
and large dataset processing. These systems need explicit I/O concurrency,
cancellation, and resource ownership.

## Decision

Use asynchronous APIs for I/O when the underlying library supports them. Use
structured task lifetimes and bounded fan-out. Keep CPU-bound work separate
from asynchronous I/O, and expose synchronous APIs only where they are an
intentional fit.

## Alternatives considered

- Synchronous-first APIs: rejected for expected I/O-heavy workloads.
- Unstructured task creation: rejected because ownership and cancellation
  become unclear.
- Wrapping all code in async: rejected because it obscures CPU work and
  intentionally synchronous libraries.

## Consequences

APIs must model cancellation and cleanup. Async tests and native library
interop need first-class treatment. Async I/O is not CPU parallelism.

## Risks

Async ecosystems and event-loop integration differ. Prefer AnyIO at future
framework-owned concurrency boundaries.

## References

- [AnyIO documentation](https://anyio.readthedocs.io/en/stable/)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
