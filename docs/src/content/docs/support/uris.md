---
title: "URI utilities"
---

<span id="uri-utilities"></span>

`Uri` provides an immutable interface over Python's `urllib.parse`. It
exposes URI components, fluent component changes, nested query data, and
application-aware route factories. Parsing and ordinary URI manipulation do
not require an active application.

## Construct and inspect

```python
from titanspan.support import Uri

uri = Uri.of(
    "https://docs.example.test/guide/start?lang=en#overview"
)

assert uri.origin() == "https://docs.example.test"
assert uri.path() == "guide/start"
assert uri.path_segments() == ("guide", "start")
assert uri.query().get("lang") == "en"
assert uri.fragment() == "overview"
```

`Uri` accepts a string, Titanspan `Stringable`, or `urllib.parse.SplitResult`.
`get_uri()` returns that standard-library parsed representation. It does not
expose third-party URI objects. `path_segments()` returns a native tuple that
preserves ordered path segments without coupling URI parsing to Collections.

Values are immutable: component methods return a new `Uri` and leave the
original unchanged.

```python
changed = (
    uri.with_scheme("http")
    .with_host("api.example.test")
    .with_path("v2/guide")
    .with_query({"lang": "si", "page": 2})
    .with_fragment("install")
)
```

Component changes return new `Uri` values; the original remains unchanged.

## Query data

`query()` returns a `UriQueryString` view. It supports `all`, `get`, `decode`,
and `value`.

```python
uri = Uri.of(
    "https://example.test/?filter[name]=Ada&tags[]=async&tags[]=agents"
)

assert uri.query().get("filter.name") == "Ada"
assert uri.query().all() == {
    "filter": {"name": "Ada"},
    "tags": ["async", "agents"],
}

updated = uri.with_query({"filter.role": "researcher"})
updated = updated.push_onto_query("tags", "workflows")
```

Query keys support bracket notation when parsed. Repeated scalar keys become
Python lists. Contiguous numeric indexes starting at zero become lists inside
nested bracket values; sparse indexes remain integer-keyed dictionaries, and
root numeric keys remain integer-keyed mappings. Query values remain strings
after parsing.

The decoder uses RFC 3986 behavior: percent escapes are decoded and `+`
remains a literal plus. `decode()` decodes the query component while keeping
the URI path and fragment as-is. Empty query and fragment delimiters are
preserved until the corresponding component is changed or removed.

`with_query()` merges keys by default. Dotted keys are interpreted as nested
paths by Titanspan's `Arr` helpers, while dots parsed from a URI remain literal
keys. Use `replace_query()` to replace the full query mapping, and
`with_query_if_missing()` to keep existing paths. `push_onto_query()` appends
values and removes duplicate list values in first-seen order.

## Application URLs

`Uri.to`, `Uri.route`, `Uri.signed_route`, `Uri.temporary_signed_route`, and
`Uri.action` resolve the active application's registered `UriUrlGenerator`
contract. Foundation binds the resolver together with the application
ContextVar, so nested and concurrent application contexts restore correctly.
Application developers do not install a separate resolver.

```python
from titanspan import Application
from titanspan.support import Uri

application = Application(
    config={"app": {"url": "https://docs.example.test"}},
)
application.router.get(
    "/profiles/{profile}",
    show_profile,
).name("profiles.show")

with application.context():
    profile_url = Uri.route("profiles.show", {"profile": "ada"})
    relative_url = Uri.route(
        "profiles.show",
        {"profile": "ada"},
        absolute=False,
    )
```

The same route catalog powers `Uri.route`, `Uri.action`, the Routing helpers,
and named redirects. Named route path values are percent-encoded; remaining
values become query parameters. Lists use repeated query keys. After startup,
ordinary named paths use the supported ASGI router path-reversal operation.
Absolute URLs require an explicit trusted `routing.origin` or `app.url`; the
request Host and forwarded headers are never used as an origin.

Action lookup accepts a dotted callable identity such as
`"ProfileController.show"`. It fails if no registered route matches or if
the action appears at distinct paths. Prefer a route name when several paths
intentionally share an action.

Signed URLs are unavailable until Titanspan has an application key-management
contract that supports both signing and verification. `Uri.signed_route` and
`Uri.temporary_signed_route` raise `RouteUrlError` instead of returning an
unsigned URL.

## Web interoperability

`Uri.redirect()` resolves the active native `ResponseFactory`. It accepts
local destinations and passes them through the HTTP component's redirect
validation. Protocol-relative and external destinations remain rejected by
default. Use the native Routing `redirect()` helper for named-route redirects;
it generates a relative URL from the same application route catalog.

`to_stringable()` returns Titanspan's fluent `Stringable`. `to_html()` returns
the raw URI string and does not escape it for an HTML attribute. URI parsing
does not validate a destination for SSRF or other network access.

`value()` and `to_string()` preserve user information in the URI string.
`repr(uri)` omits credentials to reduce accidental disclosure in diagnostics,
but callers should avoid logging `value()` when it may contain secrets.

## Python behavior and boundaries

- Component parsing and composition use `urllib.parse`.
- `get_uri()` returns the standard-library `SplitResult`.
- `path_segments()` returns `tuple[str, ...]`.
- Parsed query values remain strings; nested values use Python lists and
  mappings.
- Route factories and redirects require an active Titanspan Application;
  ordinary parsing and component changes do not.
- `UriUrlGenerator` is canonically defined in `contracts.routing` and
  re-exported from Support as the same object.
- `redirect()` returns the native `HttpResponse` contract after validation by
  the application-owned `ResponseFactory`.
- URI parsing does not validate an address for SSRF or open redirect safety.

See the [Support specification](/titanspan/specifications/support/) for component
ownership and test evidence.

## Tests

```bash
uv run --locked pytest tests/unit/support/test_uri.py -q
```
