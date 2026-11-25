# Execution scopes

Create an isolated cache for an execution lifecycle:

```python
from titanspan.container import Container, Scope


def run_sync_scope(container: Container) -> None:
    """Resolve sync-safe resources inside a synchronous execution scope.

    Args:
        container: Registry that owns the scoped binding.
    """
    with container.scope(Scope.REQUEST) as request:
        store = request.make(WorkflowStore)
        assert request.make(WorkflowStore) is store


async def run_workflow(container: Container) -> None:
    """Resolve workflow-owned resources inside an async execution scope.

    Args:
        container: Registry that owns the scoped binding.
    """
    async with container.scope(Scope.WORKFLOW) as workflow:
        store = await workflow.make_async(WorkflowStore)
        assert await workflow.make_async(WorkflowStore) is store
```

The application container owns application singletons. A synchronous scope
accepts sync-only graphs and closes them on normal exit or exceptions. An async
scope supports async resources and also closes sync-only graphs requested
inside it. A synchronous scope rejects async-only dependencies rather than
abandoning resources that need asynchronous finalization. Explicitly supplied
instances remain externally owned.

When a scoped graph depends on an uncached application singleton, the
application container resolves that singleton through an application-owned
graph first. Generator-backed singleton resources therefore remain available
across multiple request or workflow scopes and close with the application.
Create a fresh scope context object for each lifecycle; re-entering a closed
scope object raises `ScopeError` because its backend children have already
been finalized.

The current adapter uses an ordered backend scope chain:

| Titanspan names | Lifecycle level |
| --- | --- |
| `REQUEST`, `CONNECTION`, `JOB`, `WORKFLOW` | Request level |
| `NODE`, `AGENT` | Action level |
| `TOOL`, `TASK` | Step level |

Names in the same row share one backend level and cannot be nested within one
another. A nested scope must advance to a deeper level. This is an explicit
adaptation, not a claim that unrelated lifecycles have independent hierarchies.
Each concurrent workflow entered from the application context receives an
isolated child scope. Tasks spawned inside one scope inherit that context; use
a deeper task scope when concurrent work requires separate scoped instances.
The execution-mode tests verify mixed sync and async access to one scoped value
and task-group access to one application singleton. Cross-thread access is not
covered by that guarantee.
