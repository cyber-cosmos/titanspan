# Callable injection

Use `Container.call` to invoke application functions and methods while
resolving registered services, contextual values, or declared injection
metadata.

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

Explicit named values take precedence over contextual rules. Contextual rules
take precedence over supported `Annotated` metadata. If neither selects a
source, the container resolves a registered service or auto-resolvable
concrete class. Python defaults apply when no source is selected. Required
primitive values are not guessed. Unknown explicit names raise `BindingError`,
unless the callable accepts `**kwargs`.

`Container.call` invokes sync callbacks immediately and rejects async-only
callbacks. `Container.call_async` accepts synchronous or asynchronous
callbacks and awaits awaitable results. Synchronous callbacks execute on the
current thread. Blocking work should be moved to an explicit worker boundary
by the application.

Supported metadata includes `Inject(Implementation)`,
`FromConfig("path.to.value")`, `Named("service-alias")`, and
`Tagged("service-group")`. Configuration selection resolves the registered
`ConfigReader` contract and its optional `TypedConfigReader` capability;
tagged selection
preserves registration order.
Arbitrary union inference and custom metadata handlers are not implemented.
Configuration annotations support scalar accessors plus bare and
parameterized `dict`, `list`, and `Mapping` forms. Collection values are read
through `TypedConfigReader.array` and checked against the requested outer
type; nested generic arguments are not recursively validated.
Before synchronous resolution, the container inspects the same selected
contextual, metadata, alias, and tag sources and rejects known async-only
factories before they initialize. Opaque external provider behavior may still
be discovered only when the backend attempts synchronous resolution.
