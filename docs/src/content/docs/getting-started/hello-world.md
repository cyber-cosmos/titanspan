---
title: "Hello World"
---

<span id="hello-world"></span>

The example composes a native application configuration, service provider,
contract-based service, and logger. The greeting implementation receives its
configuration repository and logger through automatic constructor injection.
This example uses FastAPI's explicit routing interoperability API. The
native Routing component provides Titanspan-owned route registration and
dispatch.

Run it from the repository root:

```sh
uv sync --locked
uv run uvicorn --app-dir examples/hello-world app:app --reload
```

Visit <http://127.0.0.1:8000/>. The endpoint returns a configured greeting
and request identifier. Send an `x-request-id` header to observe the value
bound to that request's logging context:

```sh
curl -H 'x-request-id: example-123' http://127.0.0.1:8000/
```

Uvicorn enters the ASGI lifespan on startup and exits it on shutdown. Titanspan
boots registered providers and finalizes its container and logging resources
when that lifespan ends. The same lifecycle supports commands, workers, and
workflows without an HTTP server:

```python
async with application:
    greeter = application.make(Greeter)
    print(greeter.greet("worker"))
```

The example keeps its explicit FastAPI route and dependency bridge. See the
[native Routing guide](/titanspan/routing/) for application-owned routes.
