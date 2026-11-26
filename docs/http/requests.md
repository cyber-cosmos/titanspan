# Incoming requests

The request object is created by the application ASGI middleware and belongs
to one request scope. Inject the shared `HttpRequest` contract in framework
services or use the concrete `Request` helper in a handler.

```python
from typing import Annotated

from fastapi import Depends

from titanspan.contracts.http import HttpRequest
from titanspan.http import Response

resolve_request = application.dependency(HttpRequest)


async def show_page(
    request: Annotated[HttpRequest, Depends(resolve_request)],
) -> Response:
    """Return a page number selected by query input."""
    page = request.query("page", "1")
    return Response(f"page={page}")
```

Method, URL, path, host, scheme, headers, cookies, and query metadata are
synchronous and do not consume the body. `query_values` preserves repeated
query parameters. `accepts`, `expects_json`, `is_method`, `is_secure`, and
`bearer_token` provide common metadata checks.

Reading JSON, form values, or merged input may consume and cache the body, so
these operations are asynchronous. The merge order is query values followed
by body values; body fields win when the same key appears in both sources.
`input`, `all`, `only`, and `except_` expose merged input. `json` and `form`
allow callers to select an explicit parser.

Typed accessors validate values and do not apply Python's bool-as-int rule.
Query and form values are text and may be parsed by `integer`, `float`, and
`boolean`; already parsed JSON values are validated by type. `False`, zero,
empty strings, empty collections, explicit null, and missing values remain
distinct. A malformed value raises `RequestInputError` without including its
content in the diagnostic.

Use `body` to buffer a request within the configured size cap. Use `stream`
for incremental processing. Streaming is single-use unless the body was
already buffered; a buffered body can be replayed as one chunk. Form parsing
uses explicit file, field, and part-size limits. Uploaded files expose a safe
display basename, bounded reads, and chunk iteration. The request scope owns
temporary upload resources and closes them after response transmission.
