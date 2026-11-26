---
title: "Responses"
---

<span id="responses"></span>

Use `ResponseFactory` through `response()` or construct a native response
directly. The factory supports text, JSON, HTML, redirects, bodyless
responses, file downloads, byte/text streams, and Server-Sent Events.

```python
from titanspan.http import response


async def health() -> object:
    """Return a small JSON health response."""
    return response().json({"status": "ready"})
```

`Response` and specialized responses use mutable fluent header methods:
`with_header` changes the response and returns the same object. Header names
and values are validated against response splitting. `with_cookie` accepts a
`CookieOptions` value; defaults set `Secure`, `HttpOnly`, and `SameSite=Lax`.
`without_cookie` expires one cookie. `cache_control` constructs an explicit
private/public cache policy.

Redirects accept local paths by default. Absolute external HTTP(S) locations
require `allow_external=True`; non-HTTP and protocol-relative destinations
remain invalid. File downloads require a trusted application-selected path.
The supplied filename is reduced to a basename and never selects the source
path.

Responses with status 204, 205, or 304 do not send a body. Use `no_content`
for those statuses. Responses to `HEAD` send headers without body bytes while
preserving the selected response metadata. JSON serialization accepts the
supported JSON value model and rejects arbitrary application objects.
