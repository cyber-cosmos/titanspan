---
title: "Queue and Bus"
description: "Dispatch typed jobs through application-owned queue services."
---

Queue provides typed jobs, explicit dispatch, worker execution, retry
configuration, job middleware, chains, local batches, and test fakes. Bus
provides chain and batch builders over the same application-owned dispatcher.

Foundation registers Queue by default. The `QueueDispatcher` contract, the
`BusDispatcher` contract, both facades, and injected services resolve the same
`QueueManager` instance. The manager creates broker connections only after
dispatch or worker startup. Foundation closes connections during application
shutdown.

Taskiq owns message transport, consumption, acknowledgement, scheduling, and
retry execution. Titanspan validates and serializes job declarations, resolves
handlers through the Container, and creates one `JOB` execution scope per
attempt.

## Define a job

Use a dataclass or Pydantic model for serializable job data. Inject application
services into `handle()` instead of storing them on the job.

```python
from dataclasses import dataclass

from titanspan.queue import Job


@dataclass
class ProcessDocument(Job):
    """Process one document through an injected application service."""

    document_id: int
    tries = 3
    backoff = (5, 20)

    async def handle(self, processor: DocumentProcessor) -> None:
        """Process the selected document.

        Args:
            processor: Application service resolved by the Container.
        """
        await processor.process(self.document_id)
```

Register trusted job classes with `QueueServiceProvider` before startup. See
[Jobs](/titanspan/queue/jobs/) for payload and handler rules.

## Dispatch a job

Use `dispatch_async()` when the selected connection can perform I/O:

```python
from titanspan.facades.queue import Queue


async def submit(document_id: int) -> None:
    """Publish one document-processing job."""
    receipt = await Queue.dispatch_async(
        ProcessDocument(document_id),
        connection="redis",
        queue="documents",
    )
    assert receipt.state == "queued"
```

`Queue.dispatch()` builds a single-use pending operation. It does not publish
when the builder is created or discarded. See
[Dispatching](/titanspan/queue/dispatching/) for synchronous execution,
delays, and application scope rules.

## Choose a connection

The `sync` connection runs jobs inline. The `null` connection records a
discarded receipt. Redis Streams uses the optional `queue-redis` extra. The
RabbitMQ adapter uses the optional `queue-rabbitmq` extra. See
[Configuration](/titanspan/queue/configuration/) and
[Delivery guarantees](/titanspan/queue/delivery/).

## Queue guides

- [Configuration](/titanspan/queue/configuration/): connections, namespaces,
  queues, and worker limits.
- [Jobs](/titanspan/queue/jobs/): declarations, payloads, attempts, and scope.
- [Dispatching](/titanspan/queue/dispatching/): explicit publication and
  synchronous execution boundaries.
- [Workers](/titanspan/queue/workers/): Taskiq worker startup and cleanup.
- [Middleware](/titanspan/queue/middleware/): typed sync and async middleware.
- [Chains and batches](/titanspan/queue/chains-batches/): ordered continuation
  and application-local batch status.
- [Testing](/titanspan/queue/testing/): application fakes and assertions.
- [Console commands](/titanspan/queue/commands/): available worker and
  generation commands.
- [Queue specification](/titanspan/specifications/queue/): verified behavior
  and current limitations.
