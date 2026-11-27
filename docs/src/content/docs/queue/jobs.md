---
title: "Queue jobs"
description: "Declare serializable job data and inject services at execution."
---

A job declaration contains serializable data and a public `handle()` method.
The application Container supplies handler dependencies when a worker runs
the job.

## Declare a typed job

Use a dataclass or Pydantic model. Keep services, sessions, open files, request
objects, and live connections out of the payload.

```python
from dataclasses import dataclass

from titanspan.contracts.queue import JobContext
from titanspan.queue import Job


@dataclass
class ProcessDocument(Job):
    """Process one document using a scoped application service."""

    document_id: int
    job_name = "documents.process"
    schema_version = 1
    tries = 3
    backoff = (10, 30, 60)

    async def handle(
        self,
        processor: DocumentProcessor,
        context: JobContext,
    ) -> None:
        """Process the document during one job attempt.

        Args:
            processor: Service resolved by the application Container.
            context: Immutable metadata for the current attempt.
        """
        await processor.process(
            self.document_id,
            attempt=context.attempt,
        )
```

Constructor fields are message data. Do not add constructor parameters for
Container services. The handler supports synchronous or asynchronous Python
methods. Titanspan runs synchronous handlers in a managed worker thread during
async worker execution.

## Register trusted job types

Register every job class before application startup:

```python
from titanspan.foundation import Application
from titanspan.queue import QueueServiceProvider


application = Application(
    config={"app": {"name": "documents"}},
    service_providers=(
        QueueServiceProvider(jobs=(ProcessDocument,)),
    ),
)
```

The provider freezes the job catalog during boot. Use the same stable `job_name`
and payload schema across all producers and workers. Increase
`schema_version` when payload fields change. Automatic schema migrations are
not implemented; deploy compatible workers and producers together.

## Attempts and timeouts

Set `tries` to the total number of attempts. A configured `default_tries`
applies when the class leaves `tries` unset. `backoff` accepts a non-negative
number or a sequence of delays in seconds. The last sequence value repeats
for later attempts.

Non-zero delayed retry backoff requires a backend schedule source. Redis
Streams configures a Taskiq-backed Redis schedule source. RabbitMQ currently
has no schedule source, so delayed retries are not supported there.

Set `timeout` to limit an asynchronous handler. Synchronous handler timeouts
are rejected because Python cannot safely stop arbitrary running thread code.
Cancellation propagates to async job scopes and their owned resources.

## Job execution context

Each handler attempt receives a fresh native `JOB` scope. Application
singletons remain application-owned. Job-scoped dependencies are finalized
after the attempt, including failure and cancellation.

`JobContext` exposes the job ID, registered name, connection, queue, attempt,
maximum attempts, dispatch time, and optional chain and batch identifiers.
Do not treat a job ID as a business idempotency key. Broker redelivery can
execute a handler more than once.
