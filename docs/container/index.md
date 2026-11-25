# Service container

Titanspan's container registers application services, resolves typed
dependencies asynchronously, isolates execution scopes, and finalizes
resources created by managed factories.

```python
from titanspan.container import Container


class Repository:
    """Provide persistence operations for document services.
    """


class DocumentService:
    """Coordinate document operations using a repository.
    """

    def __init__(self, repository: Repository) -> None:
        """Retain the repository dependency.

        Args:
            repository: Automatically constructed concrete dependency.
        """
        self.repository = repository


async def run() -> None:
    """Resolve one application service and close owned resources.
    """
    async with Container() as container:
        service = await container.make(DocumentService)
        assert isinstance(service.repository, Repository)
```

## Registration

Register concrete classes, interface implementations, factories, instances,
and lifetimes before the first graph is composed:

```python
container.bind(Repository, SqlRepository)
container.singleton(ApplicationRegistry)
container.scoped(RequestSession)
```

Registrations freeze at first resolution. This keeps shared graph and resource
ownership stable during application execution.

Classes may also declare application or execution lifetimes with the native
decorators described in [class declarations](decorators.md).

## Resolution scopes

Use `async with container.scope(Scope.WORKFLOW)` to isolate cached resources
for one execution. See [execution scopes](scopes.md) for lifetime mapping and
nested-scope limits.

## Callable injection and factories

Use `Container.call` to inject class-typed callback parameters. See
[callable injection](injection.md), [method bindings](method-bindings.md),
and [lazy factories](factories.md) for current APIs and limits.

See [resource management](resource-management.md) for factory ownership,
scope cleanup, cancellation, and shutdown behavior.

## Compatibility status

The native method inventory, implemented operations, and pending work are
listed in [the container specification](../specifications/container.md).
The API is incremental; the inventory does not claim full parity with its
reference component.
