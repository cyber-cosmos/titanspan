# Resource management

Container-owned generator factories are finalized by the dependency engine
when the graph or execution scope that owns them closes. Synchronous
generators and asynchronous generators are supported.

```python
from collections.abc import AsyncIterator

from titanspan.container import Container, Scope


class WorkflowClient:
    """Represent a client owned by one workflow execution.

    Keep transport shutdown explicit so the factory can finalize the client.
    """

    def __init__(self) -> None:
        """Create an open client resource.

        A production implementation would retain its transport here.
        """
        self.closed = False

    async def close(self) -> None:
        """Release the client transport.

        Mark this fixture closed where a production client would release its
        owned connection.
        """
        self.closed = True


async def workflow_client() -> AsyncIterator[WorkflowClient]:
    """Yield a workflow client and release it when its owner exits.

    Yields:
        The client owned by the active workflow scope.
    """
    client = WorkflowClient()
    try:
        yield client
    finally:
        await client.close()


async def run() -> None:
    """Close a workflow-owned client deterministically."""
    async with Container() as container:
        container.scoped(
            WorkflowClient,
            workflow_client,
            scope=Scope.WORKFLOW,
        )
        async with container.scope(Scope.WORKFLOW) as workflow:
            await workflow.make_async(WorkflowClient)
```

Application singletons are resolved through application-owned graph
generations even when first requested from an execution scope. This keeps
generator-backed singleton values open until `Container.aclose()`.

Values passed to `Container.instance` are externally owned. The container does
not finalize them. A scope context object is one-shot: use
`container.scope(...)` again to create a new execution lifecycle.

Scope cleanup runs on normal return, raised exceptions, and task cancellation.
If cleanup itself fails, the container translates the failure to
`BindingResolutionError` while retaining the original exception as its cause.
