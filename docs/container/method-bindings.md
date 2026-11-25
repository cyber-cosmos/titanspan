# Method bindings

Register application callbacks under a stable key and invoke them through the
same dependency-aware callable path.

```python
from titanspan.container import Container


def process_job(job_id: str) -> str:
    """Return the supplied job identifier.

    Args:
        job_id: Identifier supplied by the dispatcher.

    Returns:
        The identifier that was processed.
    """
    return job_id


async def run() -> str:
    """Register and invoke a sync callback in an async app lifecycle.

    The callback itself is synchronous, so dependency injection can
    execute it without introducing an asynchronous result.

    Returns:
        The processed job identifier.
    """
    async with Container() as container:
        container.bind_method("jobs.process", process_job)
        return container.call_method_binding(
            "jobs.process",
            {"job_id": "job-123"},
        )


async def run_async_callback() -> str:
    """Invoke a callback that performs asynchronous work.

    The container awaits the callback and any asynchronous dependencies.

    Returns:
        The processed job identifier.
    """
    async def process_async(job_id: str) -> str:
        """Return the supplied identifier through an async callback.

        Args:
            job_id: Identifier supplied by the dispatcher.

        Returns:
            The identifier that was processed.
        """
        return job_id

    async with Container() as container:
        container.bind_method("jobs.process", process_async)
        return await container.call_method_binding_async(
            "jobs.process",
            {"job_id": "job-123"},
        )
```

The container also exposes the camelCase aliases `bindMethod`,
`hasMethodBinding`, `callMethodBinding`, and `callMethodBindingAsync`.
Registrations follow the same freeze rule as service bindings and must be
added before the first graph is composed.
