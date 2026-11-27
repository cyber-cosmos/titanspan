---
title: "Delivery guarantees"
description: "Understand Queue backend behavior and operational limits."
---

Queue uses Taskiq for broker transport, message consumption, acknowledgement,
and retry scheduling. The guarantee depends on the selected Taskiq broker and
its configuration.

## Backend capabilities

| Driver | Implemented behavior | Verification and limits |
| --- | --- | --- |
| `sync` | Runs a job inline in the current application. | No broker durability or redelivery. |
| `null` | Returns a `discarded` receipt without executing a job. | Intentional drop behavior. |
| `redis_stream` | Taskiq Redis Streams, JSON payloads, delayed scheduling, and Taskiq retry middleware. | Real Redis tests verify worker concurrency, process-crash redelivery after new queue activity, delayed delivery, retries, and chain continuation. |
| `rabbitmq` | Taskiq RabbitMQ adapter declares a durable queue and configures QoS. | Adapter is present; live RabbitMQ integration is not verified. Delayed scheduling is unavailable. |
| Custom Taskiq broker | Trusted factory can construct a broker through `QueueServiceProvider`. | The application owner must verify acknowledgement, redelivery, and cleanup semantics. |

Taskiq SQS integration is not included. Queue results are available only for
the Redis Streams driver. No universal queue-size, priority, dead-letter, or
administrative API is exposed.

## At-least-once and duplicate execution

Queue does not provide exactly-once processing. A worker can finish a handler
and lose acknowledgement or continuation publication. Broker redelivery can
run the handler again. Make external side effects idempotent and use
application-owned idempotency keys when required.

Redis Streams uses Taskiq acknowledgements and pending-message recovery.
Configure `idle_timeout_ms` for the minimum pending-message age before recovery.
Taskiq checks pending messages after it reads fresh queue messages. A crashed
message can remain pending while its queue has no new traffic.
`unacknowledged_lock_timeout_seconds` limits Taskiq's Redis claim lock. It does
not set the allowed handler duration. Real Redis integration verifies that a
worker killed inside a handler leaves the message pending and that later queue
activity triggers its redelivery. This does not prove recovery for every
broker failure window.

## Retry behavior

`tries` counts total attempts. `backoff` sets the delay in seconds for retry
attempts. Redis uses a Taskiq schedule source for delayed retry and delayed
dispatch. RabbitMQ currently supports only zero-delay retries through this
adapter. Queue does not retry cancellation as an ordinary handler failure.

The receipt for a queued job confirms broker publication only. Redis result
handles report bounded JSON output or sanitized failure status. Result
retention is finite and does not provide a failed-job repository, manual retry
command, or failed-job pruning.

## Payload security

Queue encodes versioned, bounded JSON envelopes. It registers trusted job
types before startup. Broker message values cannot trigger imports or
pickle-based object construction. Add only safe serializable data to job
payloads. Do not include secrets or live application resources.

Queue lifecycle events carry metadata and omit payloads and exception text.
`JobRetried` includes the one-based retry count after Taskiq accepts retry
publication. A failed observer cannot change the accepted retry operation.
Broker URLs and connection options are redacted from configuration
representations. Broker access remains an application security boundary.
