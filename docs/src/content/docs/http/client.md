---
title: "Outgoing HTTP client"
---

<span id="outgoing-http-client"></span>

`Http` resolves the pooled client registered by the active application.
Pending request configuration is immutable: each fluent operation returns a
new builder, so headers, cookies, authentication, and query values do not
leak into unrelated requests.

```python
from titanspan.facades import Http


async def load_document(url: str, token: str) -> object:
    """Fetch one JSON document with a request-local bearer token."""
    result = await (
        Http.accept_json()
        .with_token(token)
        .timeout(10)
        .get_async(url)
    )
    result.throw()
    return result.json()
```

`get`, `post`, `put`, `patch`, `delete`, `head`, `options`, and `request`
perform synchronous network I/O and must be called outside an async runtime.
Their explicit `_async` counterparts use the asynchronous connection pool.
Calling a synchronous request from an active event loop raises
`SynchronousHttpInAsyncContextError`; Titanspan does not create or block an
event loop for the caller.

Builders support a base URL, headers, bearer and basic authentication,
Accept values, JSON or form bodies, query parameters, cookies, request
timeouts, retry policy, and redirect control. Request and response data use
Titanspan-owned types. Unsupported arbitrary values are rejected instead of
being serialized from object attributes.

Ordinary requests buffer their response. For large bodies, use `stream` or
`stream_async` as a context manager and iterate bytes inside the context.
The response context releases the connection after complete or partial
consumption, exceptions, or cancellation.

HTTP error statuses are returned as values. Inspect `successful`, `failed`,
`client_error`, `server_error`, and common exact-status predicates. Call
`throw` or `throw_if` when the application wants `HttpStatusError`.

Retries are bounded and disabled for unsafe methods unless an idempotency
key is present. Retry delays are capped; cancellation is not intercepted.
The application owns separate synchronous and asynchronous pools. Pool sizes,
TLS verification, timeouts, redirects, HTTP/2 negotiation, and base URL come
from `http.client` configuration. Per-request options override those defaults.

The current public client does not yet include an HTTP fake transport API,
multipart outgoing upload builder, or bounded concurrent request pool. Use
an explicitly configured local test server or an injected `HttpClient`
implementation in tests until those facilities are implemented.
