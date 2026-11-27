---
title: "HTML values"
---

<span id="html-values"></span>

`HtmlString` represents markup that application code has already decided to
trust. It preserves the input and provides `to_html()` for rendering
integrations.

```python
from titanspan.support import EncodedHtmlString, HtmlString

trusted = HtmlString("<strong>Ready</strong>")
untrusted = EncodedHtmlString("<script>alert('input')</script>")

assert trusted.to_html() == "<strong>Ready</strong>"
assert untrusted.to_html().startswith("&lt;script&gt;")
```

Use `EncodedHtmlString` for plain text that will be inserted into an HTML text
or quoted attribute context. It uses Python's standard-library escaping and
supports preserving existing character entities with `double_encode=False`.
Its output is not a sanitizer and is not safe for JavaScript, CSS, URL, or
arbitrary HTML contexts.

Values implementing the `HtmlRenderable` contract are treated as trusted and are
returned without a second escaping pass. Objects implementing
`DeferredDisplayValue` are resolved only when rendered, then handled as
plain text or `HtmlRenderable` according to the returned value. `HtmlString.__html__()`
supports template integrations that recognize Python's common HTML-safe
protocol. Never wrap user-controlled content in `HtmlString` without
appropriate context-aware escaping or sanitization.

Custom `EncodedHtmlString.encode_using()` overrides are local to the active
execution context. This keeps parallel async tasks from sharing a mutable
process-wide encoder.

See the [Support specification](/framework/specifications/support) for contract
ownership and test organization.

The `DeferredDisplayValue` protocol is available from
`titanspan.contracts` and defines `resolve_display_value()`.
