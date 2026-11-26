---
title: "Native HTTP middleware"
---

<span id="native-http-middleware"></span>

Application middleware implements the `HttpMiddleware` contract and is
registered with `Application(http_middleware=...)`. Middleware is constructed
through the native container for each request, in the declared outer-to-inner
order. Its `handle` method receives the active `HttpRequest` and a typed
continuation. It may transform the request, short-circuit with a response, or
modify the downstream response.

```python
from titanspan.contracts.http import (
    HttpMiddleware,
    HttpRequest,
    HttpResponse,
    RequestHandler,
)


class RequestIdMiddleware:
    """Add a request identifier to the final response."""

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Run downstream handling and attach the native request id."""
        result = await next_handler(request)
        result.with_header("X-Request-ID", request.request_id)
        return result
```

The example uses the current native Request implementation's `request_id`
metadata. Application middleware dependencies resolve from the same request
scope used by endpoint injection. The outer pure ASGI middleware keeps the
application, request, and logging contexts active until the final body
message has been sent.

Starlette-backed `CorsMiddleware`, `TrustedHostMiddleware`, and
`HttpsRedirectMiddleware` are public ASGI middleware. Add them to the ASGI
application before startup:

```python
from titanspan.http import CorsMiddleware, TrustedHostMiddleware

application.asgi.add_middleware(
    CorsMiddleware,
    allow_origins=["https://client.example.test"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
application.asgi.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["app.example.test", "*.app.example.test"],
)
```

Starlette owns each middleware's ASGI behavior. CORS settings should name the
origins, methods, and headers the application uses. Trusted hosts reject
requests with other host values. HTTPS redirection applies to HTTP and
WebSocket scopes.

The HTTP server configuration also enforces request body, multipart file,
field, and part-size limits. The Foundation ASGI boundary assigns and returns
the `X-Request-ID` header. Route-specific middleware registration belongs to
Routing, which owns route groups and dispatch.

Do not trust forwarded client addresses or scheme headers by default. If an
ASGI server sits behind a proxy, configure its supported proxy middleware
with an explicit trusted-proxy list. Authentication, authorization,
sessions, CSRF, and distributed rate limiting belong to their owning
components.
