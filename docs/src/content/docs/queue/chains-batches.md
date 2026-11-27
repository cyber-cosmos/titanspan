---
title: "Chains and batches"
description: "Coordinate ordered jobs and inspect local batch results."
---

Bus builds ordered chains and bounded batches on the canonical Queue
dispatcher. Builders require an explicit dispatch call.

## Dispatch a chain

```python
from titanspan.facades.bus import Bus


async def process_document(document_id: int) -> None:
    """Run three jobs in order on one configured queue."""
    await (
        Bus.chain(
            [
                DownloadDocument(document_id),
                ProcessDocument(document_id),
                GenerateReport(document_id),
            ]
        )
        .on_connection("redis")
        .on_queue("documents")
        .dispatch_async()
    )
```

With a synchronous connection, jobs run in sequence before the call returns.
With Redis Streams, Queue stores bounded, versioned continuation data and
publishes the next member after the current handler succeeds.

For sync-only application work, call `dispatch_sync()` from a synchronous
command handler or another sync-safe application context. It validates every
member before execution and gives each member a separate job scope. It rejects
async handlers, async middleware, timeouts, and non-sync connections. Use
`dispatch_async()` from async application code.

Each job's `connection` and `queue` class attributes override the chain-wide
defaults. Use `prepend()` or `append()` to change the pending chain before
dispatch. A chain builder accepts one dispatch attempt.

The completion and continuation publication are separate broker operations.
A worker failure between them can cause duplicate execution or interrupt the
chain. Make side effects idempotent. Chains are not a durable workflow engine.

## Dispatch a batch

```python
batch = await (
    Bus.batch(
        [
            ProcessDocument(10),
            ProcessDocument(11),
        ]
    )
    .name("Import documents")
    .allow_failures()
    .dispatch_async()
)
```

The current batch repository is process-local. The `sync` connection executes
members sequentially and records totals. `Queue.fake()` records batch members
without opening a broker. Distributed batches reject before publication
because no persistent batch repository is registered.

`BatchHandle` exposes `id`, `name`, `total_jobs`, `pending_jobs`,
`processed_jobs`, `failed_jobs`, and `state`. The manager retains at most
`queue.batch_history_limit` snapshots. It evicts the oldest non-running
snapshot first. It rejects new dispatch before execution when active batches
fill the limit. Accessing an evicted handle raises `QueueError`. All status
disappears when its owning application manager closes. Completion callbacks,
cancellation, dynamic additions, and batch retries are not implemented.

Database-backed batch persistence remains deferred until the native Database
contracts provide suitable atomic operations.
