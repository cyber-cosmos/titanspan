---
title: "Queue middleware"
description: "Wrap job attempts with typed, dependency-injected middleware."
---

Job middleware wraps one handler attempt through the existing Pipeline. The
Container resolves each middleware inside the active `JOB` scope. Provider
middleware wraps job-specific middleware in declaration order.

Register application-wide middleware with `QueueServiceProvider`:

```python
QueueServiceProvider(
    jobs=(ProcessDocument,),
    middleware=(RecordApplicationMetrics,),
)
```

The provider middleware list is immutable after startup. Job-specific
middleware follows it. Repeated declarations run each time they appear.
The Container creates fresh middleware instances for each job attempt.

## Asynchronous middleware

Implement the `JobMiddleware` contract and declare its type on a job:

```python
from dataclasses import dataclass

from titanspan.contracts.queue import JobContext, JobNext
from titanspan.queue import Job


class RecordAttempt:
    """Record each attempt through an injected service."""

    async def handle(
        self,
        context: JobContext,
        next_handler: JobNext,
        recorder: AttemptRecorder,
    ) -> object:
        """Wrap one attempt and continue in declaration order.

        Args:
            context: Metadata for this execution attempt.
            next_handler: Continuation for later middleware or the handler.
            recorder: Application service resolved by the Container.
        """
        await recorder.started(context.job_id, context.attempt)
        return await next_handler()


@dataclass
class ProcessDocument(Job):
    """Process one document after recording its attempt."""

    document_id: int
    middleware = (RecordAttempt,)

    async def handle(self, processor: DocumentProcessor) -> None:
        """Process the document through an injected service.

        Args:
            processor: Application-owned document processor.
        """
        await processor.process(self.document_id)
```

Middleware can short-circuit by returning a value without calling
`next_handler()`. Queue does not interpret that value as a failure.

## Synchronous middleware

The `sync` connection accepts synchronous middleware implementing
`SyncJobMiddleware`. Async middleware requires async job execution. Queue
raises a native capability error when middleware and execution modes do not
match. Do not block on async work inside synchronous middleware.

## Current boundaries

Queue provides custom middleware registration through job declarations. It
does not include built-in overlap locks, rate limiting, exception throttling,
maintenance mode, or uniqueness policies. These require additional policy
and coordination contracts. Do not treat process-local middleware state as a
distributed lock.
