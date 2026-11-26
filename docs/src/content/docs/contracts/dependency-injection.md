---
title: "Dependency injection contracts"
---

<span id="dependency-injection-contracts"></span>

`ServiceContainer` describes synchronous-first resolution for sync-safe graphs
and explicit async resolution for graphs that require it. Its generic methods
preserve the requested service type for static callers.

```python
from titanspan.contracts import ServiceContainer


class MyService:
    """Represent a service used by this typing example.

    The example class has no runtime behavior.
    """


def load_sync_service(
    container: ServiceContainer,
) -> MyService:
    """Resolve an application service from the active scope.

    Args:
        container: The container owned by the current execution scope.

    Returns:
        The resolved service.
    """
    return container.get(MyService)


async def load_async_service(container: ServiceContainer) -> MyService:
    """Resolve a service whose graph may include asynchronous resources.

    Args:
        container: The container owned by the current execution scope.

    Returns:
        The asynchronously initialized service.
    """
    return await container.get_async(MyService)
```

Replace `MyService` with an application class. Consumers must keep each
container within its application or execution lifecycle and close it after
use. Implementations own resource finalization and cancellation behavior.

The native `Container` implements `ServiceContainer` and is the composition
root for framework-owned services in `Application`. Native Router handlers
resolve from that container and its active request scope. External FastAPI
handlers can use `Application.dependency` to resolve from the same container.
Explicit external route providers remain behind a separate private adapter.
`titanspan.app()` returns the active `Application` and requires an application
context; its `.container` property exposes the native service container.

Do not build another resolver, infer dependency graphs, or promise scopes that
the selected adapter cannot enforce. Any adapter should be introduced with
focused tests for resolution, scope isolation, failure propagation, and
resource cleanup.
