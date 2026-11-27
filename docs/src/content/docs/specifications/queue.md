---
title: "Queue behavioral specification"
---

<span id="queue-behavioral-specification"></span>

This specification records verified Queue and Bus behavior. It separates
available behavior from backend-dependent and deferred capabilities.

## Architecture

Foundation registers `QueueServiceProvider` through the default-provider
policy. One application-owned `QueueManager` implements the canonical
`QueueDispatcher` and `BusDispatcher` contracts. Queue and Bus facades resolve
that same manager through the active Application Container.

The manager owns a trusted job catalog, lazy broker instances, retry
configuration, application-local batches, execution-local fakes, and job
context metadata. It does not own a second Container, worker runtime, or
application lifecycle.

Taskiq owns broker calls, message consumption, acknowledgement, and retry
middleware execution. Titanspan owns the public job contract, JSON envelope,
trusted type registry, dispatch policy, Container integration, and native
Console registration.

## Capability status

| Capability | Status | Evidence or boundary |
| --- | --- | --- |
| Typed dataclass and Pydantic job payloads | Implemented and verified | Codec unit tests and real Application integration. |
| Trusted job registration | Implemented and verified | Provider registration freezes the catalog at boot. |
| Bounded, versioned JSON envelopes | Implemented and verified | Security tests reject unknown types, coercion, oversized messages, and excessive JSON nesting. |
| Container-injected sync and async handlers | Implemented and verified | Application integration tests use real Container graphs. |
| Per-attempt `JOB` scope | Implemented and verified | Concurrent jobs receive separate scoped services; cancellation finalizes resources. |
| Sync and async job middleware | Implemented and verified | Pipeline executes middleware in the active job scope. |
| Sync inline connection | Implemented and verified | Synchronous and asynchronous entry points execute registered jobs inline. |
| Null connection | Implemented | Dispatch returns `discarded`; no job executes. |
| Redis Streams transport | Implemented and verified | Real Redis integration covers publication, consumption, retries, chains, and synchronous handlers. |
| Redis delayed dispatch | Implemented and verified | A real Taskiq worker verifies the Redis schedule source honors requested availability time. |
| RabbitMQ transport | Implemented; live integration pending | Taskiq adapter is optional; no live service evidence. |
| Custom Taskiq driver factory | Implemented | Application-supplied trusted factory. Custom backend guarantees remain application-owned. |
| Single-use pending dispatch | Implemented and verified | Dispatch requires explicit call; reuse fails. |
| Job retry and backoff | Implemented; backend-dependent | Taskiq retry middleware; non-zero delay needs a schedule source. |
| Dispatch receipts | Implemented and verified | Receipts distinguish queued, executed, and discarded state. |
| Queue and Bus fakes | Implemented and verified | Fakes intercept facades and direct manager access without broker creation. |
| Ordered job chains | Implemented and verified | Inline order and Redis continuation integration are tested. Durable atomic continuation is unavailable. |
| Chain-wide destinations and per-job overrides | Implemented and verified | Inline and real Redis workers verify each job's declared queue. |
| Batches | Partial | Inline and fake status are process-local. Distributed batches reject before publication. |
| Queue Console commands | Partial | `queue:work`, `queue:listen`, `make:job`, and `make:job-middleware` are registered. |
| Queue lifecycle events | Partial | Metadata events cover dispatch, processing, success, failure, and worker boundaries. Event errors do not change a completed side effect. |
| Queue result persistence | Unsupported | No Taskiq result backend is configured. |
| Failed-job persistence and administration | Deferred | Requires a native persistence contract and owner. |
| Unique jobs and distributed overlap controls | Deferred | Cache lease behavior is not a verified Queue guarantee. |
| Transaction-aware dispatch | Deferred | Requires the canonical Database transaction lifecycle. |
| Queued event listeners | Deferred | Events does not serialize or schedule arbitrary listener callbacks. |
| SQS transport | Unsupported | No supported Taskiq SQS package is integrated. |
| Exactly-once execution | Unsupported | Broker acknowledgement and handler side effects cannot provide this guarantee. |

## Dispatch and execution

`Queue.dispatch()` and `Bus.dispatch()` create a pending builder. The caller
must call `dispatch_async()` or `dispatch_sync()`. Builders do not publish on
destruction. Direct `dispatch_async()` publishes through an async backend or
runs an inline job using the async Container path.

`dispatch_sync()` only accepts the `sync` connection. It rejects active
asyncio task execution and incompatible scoped execution. Synchronous job
handlers run through a managed worker thread when a Taskiq worker executes
them. Arbitrary synchronous code cannot be forcibly stopped after it starts.

Each attempt creates a `JOB` scope under the active Application. Job-scoped
resources close after success, exception, or cancellation. The Application
owns broker and schedule-source cleanup.

## Message format

Each message contains a format version, job ID, registered job name, payload
schema version, connection, queue, dispatch timestamp, optional correlation
and orchestration IDs, typed JSON payload, and bounded chain continuation.
Pydantic validates envelope fields and job payloads. The receiver only looks
up registered types. The receiver does not import message-selected modules.

Queue does not provide automatic schema migration. Producers and workers must
use compatible registered job declarations during deployment.

## Retry and acknowledgement

Taskiq owns attempt labels, retry scheduling, broker acknowledgement, and
message redelivery. Titanspan maps job `tries` and `backoff` to Taskiq's
retry middleware. `tries` counts total attempts. Redis delayed retry uses the
configured schedule source. Other adapters may reject non-zero retry delays.

Redis integration currently verifies a failing handler followed by a
successful retry. It does not verify process crash recovery, visibility-timeout
expiry, or every possible broker/network ambiguity. Consumers must expect
duplicate execution. Queue provides no exactly-once guarantee.

## Chain and batch semantics

Inline chains execute jobs sequentially. Redis chains encode a bounded
continuation in the message and publish the next job only after the current
handler succeeds. Handler success and continuation publication are separate
operations. A crash between them can leave a chain incomplete or cause a
retry to repeat effects.

Batches execute only through the `sync` connection or a Queue fake. Their
status is application-local. A distributed batch request raises before
publishing jobs. Persistent batch state, atomic counters, callbacks, and
recovery remain pending Database repository integration.

## Event behavior

Queue emits metadata-only event types for dispatching, dispatched, processing,
processed, and failed stages. Job payloads and exception messages are omitted.
Observer exceptions are logged by type and suppressed after the associated
operation. Cancellation from asynchronous event dispatch propagates.

Worker startup and shutdown currently emit `QueueEvent` metadata. Queue does
not yet emit dedicated release, retry, or durable batch lifecycle events.

## Integration limitations

- Job class registration is explicit. Queue does not import arbitrary job
  modules by convention.
- Delayed delivery and non-zero retry backoff require a configured schedule
  source. Redis supplies one; RabbitMQ does not.
- Redis process-crash recovery and RabbitMQ behavior require additional live
  backend tests.
- Database-backed failed jobs, batches, and transaction callbacks require
  Database-owned persistence and transaction contracts.
- Results, failed-job replay, queue administration, and process supervision
  are not implemented.
- Uniqueness and distributed overlap protection remain deferred until their
  coordination guarantees are verified.
- Queued event listeners require explicit, versioned event serialization and
  trusted listener registration.
- Queue cannot stop arbitrary synchronous Python code already running in a
  worker thread.
