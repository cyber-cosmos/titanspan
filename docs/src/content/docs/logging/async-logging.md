---
title: "Async logging"
---

<span id="async-logging"></span>

The synchronous logger is suitable for ordinary application code. The
explicit `Logger.log_async(...)` and `Log.log_async(...)` methods offload
synchronous sink work through AnyIO's worker pool. A native `AsyncLogDriver`
can instead receive the record directly through its asynchronous method.

For channels that must keep synchronous log calls off a slow sink, set
`background=True`. This creates one owned worker and a bounded queue per
channel:

```python
configuration = {
    "channels": {
        "application": {
            "driver": "daily",
            "path": "storage/logs/application.log",
            "background": True,
            "queue_capacity": 2_000,
            "overflow_policy": "drop_newest",
        },
    },
}
```

Supported overflow policies are:

| Policy | Synchronous call | Async call |
| --- | --- | --- |
| `drop_newest` | Return `dropped`. | Return `dropped`. |
| `drop_oldest` | Replace the oldest pending record when possible. | Same non-blocking policy. |
| `raise` | Raise `LogQueueFullError`. | Raise `LogQueueFullError`. |
| `emergency` | Send the sanitized record to the emergency stream. | Same fallback. |
| `await` | Raise immediately rather than block the caller. | Wait up to `queue_wait_timeout`, then raise. |

Queue acceptance produces a `queued` status, not a claim that the final sink
has delivered the record. Background sink failures are retained as bounded
type-only diagnostics and reported through the independent emergency writer.
`flush`, `flush_async`, `close`, and `aclose` drain accepted work and finalize
owned resources. `Application` closes logging during shutdown before closing
the dependency container.

The queue is in-process and does not provide durable or distributed delivery.
No exactly-once delivery guarantee is made. Keep the queue bounded and choose
an overflow policy appropriate to the information loss and latency budget of
the application.
