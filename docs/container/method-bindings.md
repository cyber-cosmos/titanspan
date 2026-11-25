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
    """Register and invoke a method callback."""
    async with Container() as container:
        container.bind_method("jobs.process", process_job)
        return await container.call_method_binding(
            "jobs.process",
            {"job_id": "job-123"},
        )
```

The container also exposes the camelCase aliases `bindMethod`,
`hasMethodBinding`, and `callMethodBinding`. Registrations follow the same
freeze rule as service bindings and must be added before the first graph is
composed.
