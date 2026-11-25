# Lazy service factories

Use `Container.factory` to create an async resolver without resolving the
service immediately.

```python
from titanspan.container import Container


class Exporter:
    """Represent a service that produces application exports.
    """


async def run() -> None:
    """Resolve a transient exporter when the lazy factory is called.
    """
    async with Container() as container:
        container.bind(Exporter)
        create_exporter = container.factory(Exporter)
        exporter = await create_exporter()
        assert isinstance(exporter, Exporter)
```

The returned callable follows the service's registered lifetime. Transient
bindings produce a new value for each call. Singleton and scoped bindings
reuse values within their owning lifecycle.
