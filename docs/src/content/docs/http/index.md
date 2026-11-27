---
title: "HTTP"
---

<span id="http"></span>

The HTTP component connects incoming ASGI requests, native responses, and
pooled outgoing clients to the active Titanspan application. Incoming HTTP is
served through the application's FastAPI ASGI adapter. Ordinary application
services, HTTP configuration, and the outgoing client are registered in the
same native service container.

Verified capabilities include request metadata and input parsing, bounded
body reads, request-scoped services, response construction, asynchronous
streaming and Server-Sent Events, native and Starlette-backed middleware,
context-local HTTP fakes, bounded concurrent requests, and synchronous and
asynchronous outgoing clients through application-owned connection pools.
The [HTTP specification](/framework/specifications/http/) records the tested
surface and external integration requirements.

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

- [Incoming requests](/framework/http/requests/)
- [Responses](/framework/http/responses/)
- [Outgoing HTTP client](/framework/http/client/)
- [Streaming and SSE](/framework/http/streaming/)
- [Native middleware](/framework/http/middleware/)
- [Configuration and lifecycle](/framework/http/configuration/)
- [Security boundaries](/framework/http/security/)
- [Testing](/framework/http/testing/)

The current transport integrations use the versions resolved by `uv.lock`.
Starlette handles ASGI requests and response transmission. HTTPX2 owns outgoing
connection pools and network protocol behavior. Titanspan wraps those
boundaries with native contracts and errors; it does not replace their HTTP
implementations.
