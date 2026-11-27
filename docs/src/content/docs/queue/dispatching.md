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

## Unsupported dispatch policies

After-commit dispatch requires the canonical Database transaction lifecycle.
After-response dispatch is not implemented. Bulk publication and conditional
dispatch helpers are not implemented. Use explicit application logic until
their owning contracts are available; do not infer transaction or publication
atomicity from a pending builder.
