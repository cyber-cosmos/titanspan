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

Route-specific middleware groups and aliases are not implemented. CORS,
trusted-host, trusted-proxy, authentication, and rate-limit policies should
be provided through explicit application ASGI integrations until native
components own those policies.
