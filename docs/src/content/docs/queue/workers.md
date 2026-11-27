---
title: "Queue workers"
description: "Run bounded workers through the application lifecycle."
---

Taskiq owns broker consumption and worker scheduling. Queue supplies its
registered job handler, Container integration, per-job scope, and application
resource lifecycle.

## Run a worker

Run workers in a separate process from web request handling. Keep the same
trusted job registrations and namespace in producers and workers.

```python
from titanspan.foundation import Application
from titanspan.queue import QueueManager, QueueServiceProvider


application = Application(
    config={
        "app": {"name": "documents"},
        "queue": {
            "default_connection": "redis",
            "default_queue": "documents",
            "connections": {
                "redis": {
                    "driver": "redis_stream",
                    "options": {"url": "redis://127.0.0.1:6379/0"},
                },
            },
        },
    },
    service_providers=(
        QueueServiceProvider(jobs=(ProcessDocument,)),
    ),
)


async def run_worker() -> None:
    """Run the worker until cancellation or backend failure."""
    async with application:
        manager = application.container.make(QueueManager)
        await manager.work_async(
            connection="redis",
            queue="documents",
            concurrency=8,
            prefetch=16,
        )
```

Foundation closes broker and schedule-source resources when the application
context exits. Let cancellation propagate so Taskiq can stop consuming and
Foundation can finalize application-owned resources.

## Worker limits

`worker_concurrency` sets the default active async handler limit.
`prefetch` sets additional in-flight transport capacity where the backend
supports it. `work_async()` can override both values for one worker.
A real Redis integration test confirms concurrent jobs use separate native
`JOB`-scoped dependencies.

The worker requires the asyncio backend because the locked Taskiq receiver
uses asyncio. Async handlers execute on the active event loop. Sync handlers
use AnyIO's managed worker-thread boundary. Queue does not claim that a
timeout can stop arbitrary synchronous Python code already running in a
thread.

## Console workers

The installed Console registers these commands:

```shell
titanspan queue:work --connection redis --queue documents \
  --concurrency 8 --prefetch 16
```

```shell
titanspan queue:listen --connection redis --queue documents
```

`queue:listen` uses one concurrent job handler. Use an application Console
factory or trusted provider discovery that registers the same job classes as
the producer. Queue does not supervise operating-system worker processes;
use the deployment's process manager.

Graceful process restart coordination, memory limits, stop-when-empty, and
worker health inspection are not implemented.
