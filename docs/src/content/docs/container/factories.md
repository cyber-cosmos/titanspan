---
title: "Lazy service resolvers"
---

<span id="lazy-service-resolvers"></span>

Use `Container.factory` for sync-safe graphs and `factory_async` when the
service may require asynchronous initialization. Neither method resolves the
service until its returned callable is invoked.

```python
from titanspan.container import Container


class Exporter:
    """Represent a service that produces application exports.

    The example keeps the class intentionally small so the factory
    lifecycle is the focus.
    """


class AsyncExporter:
    """Represent an export service with asynchronous initialization.

    The class has no additional runtime behavior in this example.
    """


async def run() -> None:
    """Resolve a transient exporter through the synchronous factory.
    """
    async with Container() as container:
        container.bind(Exporter)
        create_exporter = container.factory(Exporter)

        async def create_async_exporter() -> AsyncExporter:
            """Create an exporter through an asynchronous factory.

            Returns:
                A new exporter value.
            """
            return AsyncExporter()

        container.bind(AsyncExporter, create_async_exporter)
        create_exporter_async = container.factory_async(AsyncExporter)
        exporter = create_exporter()
        async_exporter = await create_exporter_async()
        assert isinstance(exporter, Exporter)
        assert isinstance(async_exporter, AsyncExporter)
```

The returned callable follows the service's registered lifetime. Transient
bindings produce a new value for each call. Singleton and scoped bindings
reuse values within their owning lifecycle.
