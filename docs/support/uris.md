# URI utilities

`Uri` provides an immutable interface over Python's `urllib.parse`. It
exposes URI components, fluent component changes, nested query data, and
Starlette redirect responses.

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
expose League URI objects. `path_segments()` returns an immutable tuple
because Titanspan's canonical Collections module is not implemented yet.

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

## Route URL generation

`Uri.to`, `Uri.route`, `Uri.signed_route`, `Uri.temporary_signed_route`, and
`Uri.action` delegate URL generation to a caller-provided
`UriUrlGenerator` protocol. Install a factory in the current execution
context with `set_url_generator_resolver()`:

```python
Uri.set_url_generator_resolver(lambda: application_url_generator)
profile_url = Uri.route("profiles.show", {"profile": "ada"})
```

The protocol is an integration seam; Titanspan does not yet provide a
framework URL generator. These factories raise `RuntimeError` if no resolver
is active. The resolver is held in a `ContextVar`, so separate async contexts
do not share a mutable process-global generator.

## Web interoperability

`redirect()` returns Starlette's `RedirectResponse`, and `to_stringable()`
returns Titanspan's fluent `Stringable`. `to_html()` returns the raw URI
string. That value is not escaped for an HTML attribute or validated as a
safe redirect destination.
Escape it for the destination context and apply an application allowlist when
URI input is untrusted.

`value()` and `to_string()` preserve user information in the URI string.
`repr(uri)` omits credentials to reduce accidental disclosure in diagnostics,
but callers should avoid logging `value()` when it may contain secrets.

## Python behavior and boundaries

- Component parsing and composition use `urllib.parse`.
- `get_uri()` returns the standard-library `SplitResult`.
- `path_segments()` returns `tuple[str, ...]`.
- Parsed query values remain strings; nested values use Python lists and
  mappings.
- Route methods require an injected URL generator; a routing integration is
  not implemented yet.
- `redirect()` returns Starlette's redirect response.
- URI parsing does not validate an address for SSRF or open redirect safety.

See the [Support specification](/specifications/support) for component
ownership and test evidence.

## Tests

```bash
uv run --locked pytest tests/unit/support/test_uri.py -q
```
