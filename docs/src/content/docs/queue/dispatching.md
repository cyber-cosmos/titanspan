---
title: "Dispatch jobs"
description: "Publish jobs with explicit connection, queue, and delay choices."
---

Queue and Bus share one dispatcher. Use the Queue facade, the Bus facade, or
inject the `QueueDispatcher` contract. All three resolve the same
application-owned manager.

## Dispatch immediately

Use `dispatch_async()` for an explicit asynchronous operation:

```python
from titanspan.facades.queue import Queue


async def process_later(document_id: int) -> str:
    """Publish one registered job and return its identifier."""
    receipt = await Queue.dispatch_async(
        ProcessDocument(document_id),
        connection="redis",
        queue="documents",
    )
    return receipt.job_id
```

The receipt reports the job ID, selected connection and queue, state, and
optional chain or batch metadata. A queued receipt confirms publication was
accepted by the adapter. It does not report job completion.

## Configure a pending dispatch

`dispatch()` creates a single-use builder. Call `dispatch_async()` or
`dispatch_sync()` explicitly to perform the operation:

```python
pending = Queue.dispatch(ProcessDocument(42))
pending.on_connection("redis").on_queue("documents")
pending.delay(30)
receipt = await pending.dispatch_async()
```

The builder never publishes during destruction or garbage collection. Do not
reuse a builder after dispatch. Call `dispatch_async()` directly when no
intermediate configuration is needed.

Relative delays use seconds. Absolute delays require a timezone-aware
`datetime`. Delay support depends on the selected backend. The synchronous
connection rejects delayed work.

## Run inline

The `sync` connection executes the handler before returning. The explicit
`dispatch_sync()` operation is synchronous and rejects an active async runtime,
request scope, or non-sync connection. It does not create an event loop.

`dispatch_async()` with the `sync` connection also executes inline but through
the async Container path. Do not dispatch inline from an incompatible active
request scope. Select a broker-backed connection for request handlers that
must publish work without entering a nested `JOB` scope.

The `null` connection intentionally discards the job and returns a
`discarded` receipt. It is useful only when that behavior is explicitly
configured.

## Read retained results

Redis Streams stores a bounded JSON result after Taskiq completes an attempt.
Use `Queue.result_for()` with the queued receipt from the same application:

```python
receipt = await Queue.dispatch_async(
    ProcessDocument(42),
    connection="redis",
    queue="documents",
)
result = await Queue.result_for(receipt).wait_async(timeout=30)

if result.state == "succeeded" and result.has_value:
    print(result.value)
```

`wait_async()` uses cancellable polling. Taskiq result records expire after
`result_ttl_seconds`, which defaults to one day. Results contain JSON values
only. Unsupported values are omitted without turning completed work into a
retry. Failed results expose status and execution time, not exception text.
The `sync`, `null`, RabbitMQ, and custom connections do not provide result
handles through this API.

## Bulk and deferred dispatch

`dispatch_many_async()` accepts up to 1,000 jobs and returns receipts in input
order. It validates registrations and destinations before publication. It then
publishes each job through the same single-job dispatch path.

```python
receipts = await Queue.dispatch_many_async(
    [ProcessDocument(42), ProcessDocument(43)],
    connection="redis",
    queue="documents",
)
```

Taskiq's public broker API has no atomic bulk operation. A payload, handler,
broker failure, or cancellation can leave earlier jobs accepted. A broker
failure can also leave the current job's outcome uncertain. Use idempotent
jobs when retrying after an incomplete bulk dispatch.

After-commit dispatch requires the canonical Database transaction lifecycle.
After-response dispatch is not implemented. Do not infer transaction or
publication atomicity from a pending builder.

## Conditional dispatch

Use `dispatch_if()` or `dispatch_unless()` to create a pending operation. The
builder still requires an explicit dispatch call. Use the `_async` variants
to perform an enabled dispatch immediately:

```python
receipt = await Queue.dispatch_unless_async(
    document_already_processed,
    ProcessDocument(42),
)
```

A false condition returns `None` without validating the job or resolving its
connection. An enabled condition uses the ordinary Queue dispatch path.
