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

Multipart attachments are replayable byte values. Combine `attach` or
`with_files` with `post`, `put`, `patch`, or `request`; HTTPX2 encodes the
multipart request body.

```python
response = await (
    Http.attach(
        "document",
        document_bytes,
        filename="report.pdf",
        content_type="application/pdf",
    )
    .post_async("https://files.example.test/documents", {"name": "report"})
)
```

`ClientResponse.cookies` returns an immutable snapshot. The application
client does not reuse response cookies in later requests; pass request cookies
explicitly through `with_cookies`.

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

Use `Http.pool` for bounded asynchronous operations. Named mappings return a
mapping with the same keys; sequences return a tuple in input order. Each
`HttpPoolRequest` accepts an async callback and optional timeout. Fail-fast
mode cancels remaining callbacks, closes received responses, and raises the
first error. Set `fail_fast=False` to collect errors beside successful
responses. The caller must close every successful returned response.

```python
from titanspan.http import HttpPoolRequest

results = await Http.pool(max_concurrency=4).run(
    {
        "profile": HttpPoolRequest(
            lambda: Http.get_async("https://api.example.test/profile"),
            timeout=3,
        ),
        "settings": HttpPoolRequest(
            lambda: Http.get_async("https://api.example.test/settings"),
            timeout=3,
        ),
    },
    fail_fast=False,
)
```

For testing, `Http.fake` provides context-local HTTPX2 mock transports,
recorded requests, and send assertions. See the
[HTTP testing guide](/framework/http/testing/).
