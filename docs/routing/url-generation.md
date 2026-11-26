# URL generation

Routing registers one `UrlGenerator` for each Application. The generator
shares the route catalog used for incoming dispatch and is available through
the `UriUrlGenerator` contract. URI parsing remains usable without an active
Application; route-aware URI factories require one.

## Named routes

```python
from titanspan import Application, route, url
from titanspan.support import Uri

application = Application(
    config={"app": {"url": "https://example.test"}},
)
application.router.get(
    "/documents/{document_id}",
    show_document,
).name("documents.show")

with application.context():
    assert route(
        "documents.show",
        {"document_id": "a b"},
    ) == "/documents/a%20b"
    absolute = Uri.route(
        "documents.show",
        {"document_id": 42},
    )
    assert absolute.value() == "https://example.test/documents/42"
    assert url("/docs", absolute=True) == "https://example.test/docs"
```

Path parameters are percent-encoded. Unused parameters become query values;
sequence values use repeated keys. Missing routes and required path parameters
raise native routing exceptions. Absolute URLs require `routing.origin` or
`app.url`. Host and forwarded headers are never trusted as the application
origin.

After compilation, ordinary named paths use the ASGI router's supported
`url_path_for` operation. Route forms with custom converters use the native
catalog fallback. Both paths use the same registered definition and produce
local URLs before the configured origin is applied.

## URI factories and controller actions

```python
with application.context():
    path_url = Uri.to("/health")
    document_url = Uri.route(
        "documents.show",
        {"document_id": 42},
    )
    action_url = Uri.action(
        "DocumentController.show",
        {"document_id": 42},
    )
```

`Uri.action` matches registered callable identities without constructing the
controller. If one action is registered at different paths, action lookup is
ambiguous; use a named route to select the intended path.

URI component manipulation such as `Uri.of(...).with_query(...)` does not
require an Application. `Uri.to`, `Uri.route`, and `Uri.action` resolve the
active application's URL generator through a context-local binding. Nested
contexts, exceptions, cancellation, and concurrent tasks restore the previous
binding.

## Redirects

Use the Routing redirect helper for a named route:

```python
from titanspan import redirect

with application.context():
    response = redirect().route(
        "documents.show",
        {"document_id": 42},
    )
```

`Uri.redirect()` delegates to the active native `ResponseFactory` and returns
the native `HttpResponse` contract. The HTTP redirect policy rejects
protocol-relative and external destinations by default. For a URI generated
as an absolute URL, request a relative route with `absolute=False` before
redirecting.

## Signed links

`Uri.signed_route` and `Uri.temporary_signed_route` fail with `RouteUrlError`
until Titanspan has key management that supports both signature generation
and verification. They never return an unsigned URL as a fallback.
