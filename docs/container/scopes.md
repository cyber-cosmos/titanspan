# Execution scopes

Create an isolated cache for an execution lifecycle:

```python
from titanspan.container import Container, Scope


async def run_workflow(container: Container) -> None:
    """Resolve workflow-owned resources inside one execution scope.
    """
    async with container.scope(Scope.WORKFLOW) as workflow:
        store = await workflow.make(WorkflowStore)
        assert await workflow.make(WorkflowStore) is store
```

The application container owns application singletons. A scope owns resources
constructed in its backend child and closes them when its async context exits,
including when an exception propagates. Explicitly supplied instances remain
externally owned.

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
