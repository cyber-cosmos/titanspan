# HTML values

`HtmlString` represents markup that application code has already decided to
trust. It preserves the input and provides `to_html()` and `toHtml()` for
rendering integrations.

```python
from titanspan.support import EncodedHtmlString, HtmlString

trusted = HtmlString("<strong>Ready</strong>")
untrusted = EncodedHtmlString("<script>alert('input')</script>")

assert trusted.to_html() == "<strong>Ready</strong>"
assert untrusted.to_html().startswith("&lt;script&gt;")
```

Use `EncodedHtmlString` for plain text that will be inserted into an HTML text
or quoted attribute context. It uses Python's standard-library escaping,
matches Laravel's apostrophe entity spelling, and supports preserving
existing character entities with `double_encode=False`. Its output is not a
sanitizer and is not safe for JavaScript, CSS, URL, or arbitrary HTML
contexts.

Values implementing the `Htmlable` contract are treated as trusted and are
returned without a second escaping pass. Objects implementing
`DeferringDisplayableValue` are resolved only when rendered, then handled as
plain text or `Htmlable` according to the returned value. `HtmlString.__html__()`
supports template integrations that recognize Python's common HTML-safe
protocol. Never wrap user-controlled content in `HtmlString` without
appropriate context-aware escaping or sanitization.

Custom `EncodedHtmlString.encode_using()` overrides are local to the active
execution context. This keeps parallel async tasks from sharing a mutable
process-wide encoder.

See the [Laravel compatibility inventory] for per-method status and the
pinned [HtmlString implementation] and [HtmlString tests]. Titanspan's encoder
uses Python escaping and makes its context boundaries explicit.

[Laravel compatibility inventory]: ../compatibility/laravel-support
[HtmlString implementation]: https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Support/HtmlString.php
[HtmlString tests]: https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/tests/Support/SupportHtmlStringTest.php

The `DeferringDisplayableValue` protocol is available from
`titanspan.contracts` and defines both `resolve_displayable_value()` and the
Laravel-compatible `resolveDisplayableValue()` spelling.
