# Callable injection

Use `Container.call` to invoke application functions and methods while
resolving required class-typed parameters from the active container.

```python
from titanspan.container import Container


class DocumentStore:
    """Represent the storage dependency used by a task.
    """


def process_document(store: DocumentStore, retries: int) -> int:
    """Return the configured retry count after dependency resolution.

    Args:
        store: Automatically resolved document store.
        retries: Explicit retry count supplied by the caller.

    Returns:
        The retry count used by this operation.
    """
    return retries


async def run() -> int:
    """Resolve the task dependency and invoke the sync function.

    Returns:
        The operation's retry count.
    """
    async with Container() as container:
        return container.call(
            process_document,
            {"retries": 2},
        )


async def run_async() -> int:
    """Invoke an async callback through explicit async injection.

    Returns:
        The operation's retry count.
    """
    async with Container() as container:
        return await container.call_async(
            process_document,
            {"retries": 2},
        )
```

Explicit named values take precedence over annotation resolution. Python
defaults are used when a value is omitted. A required parameter without an
explicit value must have a class annotation that the container can resolve.
The container does not guess primitive values such as strings, numbers, or
booleans. Unknown explicit names raise `BindingError`, unless the callable
accepts `**kwargs`.

`Container.call` invokes sync callbacks immediately and rejects async-only
callbacks. `Container.call_async` accepts synchronous or asynchronous
callbacks and awaits awaitable results. Synchronous callbacks execute on the
current thread. Blocking work should be moved to an explicit worker boundary
by the application.

Only the annotation's base type is currently used for `Annotated` values.
Custom injection attributes, configuration values, tagged collections,
primitive contextual bindings, and arbitrary union resolution remain
unimplemented.
