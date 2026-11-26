---
title: "URL generation"
---

<span id="url-generation"></span>

Routing registers one application-owned URL generator that shares the
canonical route catalog. `Uri.to`, `Uri.route`, `Uri.action`, `route()`,
`url()`, named redirects, and dependency injection resolve the same
`UriUrlGenerator` contract. URI parsing and query manipulation remain
available without an active Application; route-aware helpers require one.

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
    assert route("documents.show", {"document_id": "a b"}) == (
        "/documents/a%20b"
    )
    absolute = route(
        "documents.show",
        {"document_id": 42},
        absolute=True,
    )
    assert absolute == "https://example.test/documents/42"
    assert url("/docs") == "/docs"
    assert url("/docs", absolute=True) == "https://example.test/docs"
    assert Uri.route("documents.show", {"document_id": 42}).value() == (
        "/documents/42"
    )
```

The consistent default for `route()`, `url()`, `Uri.route()`, and
`Uri.action()` is a relative URL. Pass `absolute=True` to add the configured
origin. `Uri.to()` retains its established behavior and returns an absolute
URL; it requires `routing.origin` or `app.url`. This policy aligns route
helpers while preserving `Uri.to()` callers. Applications that previously
used the default absolute behavior of `Uri.route()` can request it explicitly.

Host and forwarded headers never select the application's trusted origin.
Absolute generation rejects missing or invalid origins and requires a
domain-constrained route's host to match that origin. Relative URLs do not
need an origin.

## Parameters and matching

Path values are percent-encoded and validated against route constraints and
the built-in `str`, `int`, `float`, `uuid`, and `path` converters. Declared
defaults fill missing path values. Unused values use Support's `Arr.query`
encoder: lists use indexed bracket keys, nested mappings use bracket notation,
`None` values are omitted, and booleans use `1` or `0`. Unicode uses UTF-8
percent encoding, and repeated query keys and fragments are preserved when an
origin is added. Missing named routes and required parameters raise routing
exceptions.

After compilation, built-in named paths delegate substitution to Starlette's
`url_path_for`. Optional final path segments use native catalog substitution.
Custom Starlette converters are unsupported and fail explicitly. Both
supported forms use the same route definition as ASGI matching, so generated
paths dispatch when their parameter values satisfy its converters and
constraints.

## URI factories and action lookup

```python
with application.context():
    health = Uri.to("/health")
    document = Uri.route(
        "documents.show",
        {"document_id": 42},
        absolute=True,
    )
    action = Uri.action(
        "DocumentController.show",
        {"document_id": 42},
    )
```

`Uri.action` compares registered callable metadata without constructing a
controller. It accepts a dotted identifier or identifier sequence. If an
action is registered at distinct paths, lookup raises an ambiguity error;
use a route name to choose the intended path.

`Uri.to`, `Uri.route`, `Uri.action`, `route()`, and `url()` resolve the active
application's generator through a context-local service binding. A contract
replacement affects relative and absolute URL helpers consistently. Nested
contexts, errors, cancellation, and concurrent tasks restore the previous
binding.

## Redirects

Named redirects always generate a relative path and use the active native
`ResponseFactory`:

```python
from titanspan import redirect

with application.context():
    response = redirect().route(
        "documents.show",
        {"document_id": 42},
    )
```

`Uri.redirect()` also delegates to `ResponseFactory`. The HTTP redirect
policy rejects external and protocol-relative destinations by default.

## Signed links

`Uri.signed_route` and `Uri.temporary_signed_route` raise `RouteUrlError`.
They remain unsupported until the framework key-management service can
generate, verify, and rotate signatures. Routing does not provide separate
cryptographic or key-storage infrastructure.
