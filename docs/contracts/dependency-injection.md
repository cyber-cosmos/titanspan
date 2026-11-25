# Dependency injection contracts

`AsyncServiceContainer` describes a narrow consumer-facing capability:
resolve an instance by its class key and close the owned scope. The generic
method preserves the requested concrete service type for static callers.

```python
from titanspan.contracts import AsyncServiceContainer


class MyService:
    """Represent a service used by this typing example.

    The example class has no runtime behavior.
    """


async def load_service(
    container: AsyncServiceContainer,
) -> object:
    """Resolve an application service from the active scope.

    Args:
        container: The container owned by the current execution scope.

    Returns:
        The resolved service.
    """
    return await container.get(MyService)
```

Replace `MyService` with an application class. Consumers must keep each
container within its application or execution lifecycle and close it after
use. Implementations own resource finalization and cancellation behavior.

The current `Application` composes Dishka directly. Dishka's overloaded
resolution API does not structurally satisfy this narrower protocol, and
Titanspan does not yet provide an adapter. The integration test verifies that
a Titanspan contract can be used as a Dishka dependency key; it does not claim
that Dishka implements `AsyncServiceContainer`.

Do not build another resolver, infer dependency graphs, or promise scopes that
the selected adapter cannot enforce. Any adapter should be introduced with
focused tests for resolution, scope isolation, failure propagation, and
resource cleanup.
