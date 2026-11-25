# String utilities

`titanspan.support.Str` provides stateless string operations inspired by
Laravel's `Illuminate\Support\Str`. It uses Python strings, regular
expressions, UUID parsing, URL parsing, JSON, Base64, and Unicode data from the
standard library. It adds no runtime dependencies.

```python
from titanspan.support import Str

assert Str.snake("LaravelHTTPFramework") == "laravel_http_framework"
assert Str.startsWith("Titanspan", "Titan")
assert Str.starts_with("Titanspan", "Titan")
assert Str.after("user@example.com", "@") == "example.com"
```

Both the Python `snake_case` API and the Laravel-compatible `camelCase`
aliases call the same implementation. Python reserves the name `is`, so use
`Str.is_()` for whole-string wildcard matching.

## Available operations

The tested surface includes delimiter extraction, prefix and suffix checks,
case conversion, slugs, truncation, padding, masking, literal and regular
expression replacement, callback-name parsing, keyword swapping, contextual
excerpts, Unicode slicing, JSON and UUID checks, Base64 conversion, and
whitespace utilities. It also includes secure random strings and a
Titanspan-specific password generator. The exact upstream member status is
tracked in the [Laravel compatibility inventory](../compatibility/laravel-support).

```python
assert Str.between("[section] body", "[", "]") == "section"
assert Str.slug("Crème brûlée & AI", dictionary={"&": "and"}) == (
    "creme-brulee-and-ai"
)
assert Str.limit("Laravel is a framework", 10) == "Laravel is..."
assert Str.replaceMatches(r"(\d+)", r"[\1]", "a12b") == "a[12]b"
assert Str.parseCallback("Job@handle") == ("Job", "handle")
assert Str.excerpt("This is a beautiful morning", "beautiful", {"radius": 5}) == (
    "...is a beautiful morn..."
)
assert len(Str.random(40)) == 40
assert len(Str.password(24)) == 24
```

## Secure random strings and passwords

`Str.random()` uses the system-backed `secrets` module to generate ASCII
letters and digits. Its default length is 16. The factory controls mirror the
pinned Laravel API and provide deterministic values for tests; Titanspan
stores these overrides in the active execution context, so one task's test
factory does not mutate another task's state.

`Str.password()` is an additional Titanspan utility because the pinned
Laravel `Str` API does not define password generation. It defaults to 32
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
- `Str.match_all()` returns a Python `list`; Laravel returns an Illuminate
  Collection. The Titanspan collections module may provide a canonical
  collection result in a later integration.
- `Str.position()` returns `None` when no substring is found.
- `Str.limit()` and padding use code point lengths, not terminal display
  widths.
- `Str.word_count()` counts Python Unicode word characters. Laravel's
  default behavior is more ASCII-oriented.
- `Str.ascii()` uses Unicode decomposition and a small Latin transliteration
  table. Its `language` argument is accepted for source compatibility, but
  locale-specific transliteration is not implemented.
- `Str.is_url()` checks syntax for a conservative set of common schemes. URL
  validation does not prevent server-side request forgery or make a request
  safe.
- `Str.is_ulid()` validates the canonical alphabet and 128-bit length
  boundary. Full Symfony UID compatibility remains under review.
- `Str.convert_case()` supports the standard upper, lower, title, and fold
  modes. PHP's simple case-mapping modes are not implemented.

The remaining methods in Laravel's pinned Str inventory, including
translation, Markdown conversion, inflection, UUID/ULID factories, and
several locale-specific utilities remain pending. The
compatibility inventory distinguishes implemented partial behavior from
verified parity.

## Validation

Run the focused tests with:

```bash
uv run --locked pytest tests/unit/support/test_str.py -q
```

The suite covers both method naming conventions, boundary cases, Unicode
code points, invalid regular expressions, and property-based trim behavior.
