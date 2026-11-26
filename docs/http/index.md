# HTTP

The HTTP component connects incoming ASGI requests, native responses, and
pooled outgoing clients to the active Titanspan application. Incoming HTTP is
served through the application's FastAPI ASGI adapter. Ordinary application
services, HTTP configuration, and the outgoing client are registered in the
same native service container.

The component is implemented incrementally. Verified capabilities include
request metadata and input parsing, bounded body reads, request-scoped
services, response construction, asynchronous streaming and Server-Sent
Events, ordered native middleware, and synchronous/asynchronous outgoing
requests through application-owned connection pools. The exact current
surface and pending work are listed in the [HTTP specification](../specifications/http.md).

## Application setup

```python
from titanspan.foundation import Application

application = Application(
    config={
        "app": {"name": "Documents"},
        "http": {"client": {"timeout": 20.0}},
    },
)

application.asgi.add_api_route("/health", health, methods=["GET"])
```

Use `application.asgi` as the ASGI application. Its lifespan delegates to
native application startup and shutdown. Standalone workers and commands can
use `async with application` without starting an HTTP server.

## Guides

- [Incoming requests](./requests.md)
- [Responses](./responses.md)
- [Outgoing HTTP client](./client.md)
- [Streaming and SSE](./streaming.md)
- [Native middleware](./middleware.md)
- [Configuration and lifecycle](./configuration.md)
- [Security boundaries](./security.md)
- [Testing](./testing.md)

The current transport integrations use the versions resolved by `uv.lock`.
Starlette handles ASGI requests and response transmission. HTTPX2 owns outgoing
connection pools and network protocol behavior. Titanspan wraps those
boundaries with native contracts and errors; it does not replace their HTTP
implementations.
