---
title: "String utilities"
---

<span id="string-utilities"></span>

`titanspan.support.Str` provides stateless string operations using Python
strings, regular expressions, UUID and URL parsing, JSON, Base64, and Unicode
data from the standard library. It adds no runtime dependencies.

```python
from titanspan.support import Str

assert Str.snake("TitanspanHTTPFramework") == "titanspan_http_framework"
assert Str.starts_with("Titanspan", "Titan")
assert Str.after("user@example.com", "@") == "example.com"
```

Public methods use snake_case. Python reserves the name `is`, so use
`Str.is_()` for whole-string wildcard matching.

## Available operations

The tested surface includes delimiter extraction, prefix and suffix checks,
case conversion, slugs, truncation, padding, masking, literal and regular
expression replacement, callback-name parsing, keyword swapping, contextual
excerpts, Unicode slicing, JSON and UUID checks, Base64 conversion, and
whitespace utilities. It also includes secure random strings and a password
generator.

```python
assert Str.between("[section] body", "[", "]") == "section"
assert Str.slug("Crème brûlée & AI", dictionary={"&": "and"}) == (
    "creme-brulee-and-ai"
)
assert Str.limit("Titanspan is a framework", 10) == "Titanspan ..."
assert Str.replace_matches(r"(\d+)", r"[\1]", "a12b") == "a[12]b"
assert Str.parse_callback("Job@handle") == ("Job", "handle")
assert Str.excerpt("This is a beautiful morning", "beautiful", {"radius": 5}) == (
    "...is a beautiful morn..."
)
assert len(Str.random(40)) == 40
assert len(Str.password(24)) == 24
```

## Secure random strings and passwords

`Str.random()` uses the system-backed `secrets` module to generate ASCII
letters and digits. Its default length is 16. The factory controls provide
deterministic values for tests; Titanspan stores overrides in the active
execution context, so one task's test
factory does not mutate another task's state.

`Str.password()` defaults to 32
characters and includes at least one uppercase or lowercase letter, digit,
and printable ASCII punctuation character. Callers may disable categories,
but the requested length must be large enough to include one character from
each enabled category.

```python
password = Str.password(
    24,
    letters=True,
    numbers=True,
    symbols=False,
)
```

Password output is plaintext secret material. Store only an appropriate
one-way password hash when persisting it, and do not place generated values in
logs or telemetry.

## Python behavior

- String indexes count Unicode code points. They do not count display cells
  or grapheme clusters such as emoji plus skin-tone modifiers.
- Regular expressions use Python's `re` syntax and raise `re.error` for an
  invalid expression. PCRE-specific constructs are not translated.
- `Str.match_all()` returns a Python `list`. Collection types are owned by
  `titanspan.collections`.
- `Str.position()` returns `None` when no substring is found.
- `Str.limit()` and padding use code point lengths, not terminal display
  widths.
- `Str.word_count()` counts Python Unicode word characters.
- `Str.ascii()` uses Unicode decomposition and a small Latin transliteration
  table. Locale-specific transliteration is not implemented.
- `Str.is_url()` checks syntax for a conservative set of common schemes. URL
  validation does not prevent server-side request forgery or make a request
  safe.
- `Str.is_ulid()` validates the canonical alphabet and 128-bit length
  boundary.
- `Str.convert_case()` supports upper, lower, title, and case-fold modes.

Translation, Markdown conversion, inflection, and locale-specific
transliteration are not part of the current `Str` implementation.

## Validation

Run the focused tests with:

```bash
uv run --locked pytest tests/unit/support/test_str.py -q
```

The suite covers the native API, boundary cases, Unicode
code points, invalid regular expressions, and property-based trim behavior.
