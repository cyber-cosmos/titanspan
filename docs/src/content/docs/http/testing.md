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

For application-level outgoing-client tests, register an alternate native
`HttpClient` implementation with a service provider before the application
composes its graph. This uses the same contract and container as production.
The HTTP component does not yet provide `Http.fake`, URL-pattern matching,
request recording assertions, or a global no-network guard.

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
