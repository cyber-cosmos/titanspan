---
title: "Testing"
---

<span id="testing"></span>

Titanspan provides application test contexts that use the production
Foundation lifecycle, Container, HTTP middleware, and ASGI application.
Pytest remains the test runner. Starlette and HTTPX2 provide in-process ASGI
clients.

## Test an application

Use `ApplicationTest` for synchronous tests. It creates an isolated temporary
root when `base_path` is omitted and starts the real ASGI lifespan.

```python
from titanspan.testing import ApplicationTest

test_application = ApplicationTest(
    config={"app": {"name": "Test catalog"}},
)
test_application.application.router.get(
    "/health",
    lambda: {"status": "ready"},
)

with test_application:
    result = test_application.client.get("/health")
    assert result.status_code == 200
    assert result.json() == {"status": "ready"}
```

Use `AsyncApplicationTest` inside an async test. It starts Foundation
explicitly and closes the HTTPX2 client before application shutdown.

```python
from titanspan.testing import AsyncApplicationTest

test_application = AsyncApplicationTest()
test_application.application.router.get(
    "/health",
    lambda: {"status": "ready"},
)

async with test_application:
    result = await test_application.client.get("/health")
    assert result.status_code == 200
```

Both helpers compose applications through Foundation's `Application.builder()`
and discover trusted `titanspan.providers` entry points before registering
test providers and middleware. Configuration and typed Settings pass through
that builder. `replacements` register in the test application's canonical
Container before graph composition. They cannot change another Application.
Component fakes remain owned by their components.

See the [application testing specification](/framework/specifications/testing/)
for lifecycle and substitution behavior.

## Repository checks

The repository uses Pytest, Ruff, strict Pyright, and independent minimums of
95 percent statement coverage and 90 percent branch coverage. Tests include
real integration boundaries and require no paid infrastructure or live model
APIs. See the [engineering standards](/framework/development/standards/) for
TDD, docstrings, typing, and quality checks.

From a checkout, run:

```sh
uv sync --locked
make check
make integration-test
```

Performance measurements are informational. Shared runner timing is not a
stable performance gate.
