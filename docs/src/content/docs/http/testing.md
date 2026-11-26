---
title: "Testing HTTP behavior"
---

<span id="testing-http-behavior"></span>

Use unit tests for native request, response, configuration, upload, builder,
and status behavior. Use real integration tests when verifying ASGI request
scope handling, middleware, connection pools, streaming, and cleanup.

`fastapi.testclient.TestClient` exercises the in-process ASGI application.
The repository's client integration tests use a loopback HTTP server and the
real locked outgoing transport. No external API or paid service is needed.

Use `Http.fake` for deterministic application-level client tests. The fake
uses HTTPX2 mock transports and applies to both facade calls and injected
`HttpClient` calls in the current context. An unmatched request raises
`UnexpectedHttpRequestError`; it never falls through to the real network.

```python
from titanspan.facades import Http


async def fetch_document() -> None:
    """Verify one request with a context-local fake response."""
    with Http.fake(
        {
            "https://example.test/*": Http.fake_response(
                {"status": "ready"},
            ),
        }
    ):
        response = await Http.get_async("https://example.test/health")
        assert response.json() == {"status": "ready"}
        Http.assert_sent(
            Http.request_pattern(
                method="GET",
                url="https://example.test/health",
            )
        )
        await response.aclose()
```

Map values may be one response reused for every match or a non-empty response
sequence consumed in order. Request matchers support URL globs, methods,
headers, and exact bodies. `Http.sent_requests`, `assert_sent`,
`assert_not_sent`, and `assert_sent_count` inspect captured requests. Nested
fake contexts restore their parent, and task contexts do not share the active
fake selection.

Always enter the application lifecycle when testing application-owned pools:

```python
async with application:
    result = await Http.get_async("http://127.0.0.1:8000/health")
    assert result.successful()
    await result.aclose()
```

When adding tests, cover success and invalid input, explicit timeouts, error
translation, streaming cleanup, cancellation, request isolation, and
application shutdown. Do not mock HTTPX2 in tests intended to verify transport
integration.
