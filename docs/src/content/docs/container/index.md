---
title: "Service container"
---

<span id="service-container"></span>

Titanspan's container registers application services, resolves synchronous
dependency graphs immediately, isolates execution scopes, and finalizes
resources created by managed factories. Explicit async methods resolve graphs
that require asynchronous initialization or cleanup.

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


def synchronous_example(container: Container) -> DocumentService:
    """Resolve a graph containing only synchronous dependencies.

    Args:
        container: The application-owned registry.

    Returns:
        A fully constructed document service.
    """
    return container.make(DocumentService)


async def run() -> None:
    """Close resources owned by the application container.
    """
    async with Container() as container:
        service = container.make(DocumentService)
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
decorators described in [class declarations](/framework/container/decorators/).

Select a dependency for one consumer with
[contextual bindings](/framework/container/contextual-bindings/). `Annotated` metadata supports
implementation, configuration, alias, and tagged-service selection.
[Extensions and callbacks](/framework/container/lifecycle-hooks/) add ordered service decoration
and root-resolution hooks. [Temporary overrides](/framework/container/overrides/) provide
isolated substitutions for tests and individual executions.

## Resolution scopes

Use `async with container.scope(Scope.WORKFLOW)` to isolate cached resources
for one execution. See [execution scopes](/framework/container/scopes/) for lifetime mapping and
nested-scope limits.

## Callable injection and factories

Use `Container.call` for synchronous callbacks and `call_async` for callbacks
or dependencies that require asynchronous execution. See
[callable injection](/framework/container/injection/), [method bindings](/framework/container/method-bindings/),
and [lazy factories](/framework/container/factories/) for current APIs and limits.

See [resource management](/framework/container/resource-management/) for factory ownership,
scope cleanup, cancellation, and shutdown behavior.

## HTTP dependency integration

Resolve native application services in FastAPI handlers with the dependency
bridge. It uses the same container as providers and facades, and request
resources remain alive until streaming responses finish.

```python
from typing import Annotated

from fastapi import Depends

from titanspan.contracts.config import ConfigRepository


async def endpoint(
    config: Annotated[
        ConfigRepository,
        Depends(application.dependency(ConfigRepository)),
    ],
) -> dict[str, object]:
    """Return a value from the application-owned configuration service.

    Args:
        config: Configuration repository resolved by the active request.

    Returns:
        A JSON-compatible response value.
    """
    return {"name": config.get("app.name")}
```

The raw `Application.providers` input remains an advanced interoperability
boundary for external provider graphs. Ordinary Titanspan services do not
need that separate graph.

## Implementation status

The native operation inventory, implemented behavior, and pending work are
listed in [the container specification](/framework/specifications/container/).
