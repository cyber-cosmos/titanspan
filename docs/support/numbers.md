# Number utilities

`titanspan.support.Number` formats, parses, and summarizes numeric values
using Laravel's `Illuminate\Support\Number` as its API reference. The
implementation delegates locale data and numeric formatting to Babel and
number-to-words conversion to `num2words`.

## Installation

Number helpers are available in the base package. Locale-sensitive
formatting and parsing require the optional `numbers` extra:

```bash
uv add "titanspan[numbers]"
```

The package can be imported without the extra. An operation that needs an
optional library raises `MissingNumberDependencyError` with installation
guidance when that library is absent.

## Formatting and parsing

```python
from titanspan.support import Number, NumberParseType

assert Number.format(1234.5) == "1,234.5"
assert Number.format(1234.5, locale="de") == "1.234,5"
assert Number.percentage(12.5, precision=1) == "12.5%"
assert Number.currency(10, "EUR", locale="de") == "10,00 €"

assert Number.parse("1.234,5", locale="de") == 1234.5
assert Number.parse("1.234,5", NumberParseType.INT64, "de") == 1234
assert Number.parse_int("invalid", locale="en") is False
```

`percentage` formats the supplied value on the same scale; `12.5` becomes
`12.5%`. Parsing uses Babel's locale data. Invalid numeric text returns
`False`, matching Laravel's parse-failure convention. Integer results use
Python's arbitrary-precision `int` and do not overflow at a 32- or 64-bit
boundary.

`NumberParseType` exposes ICU-compatible integer values: `INT32` is `0`,
`INT64` is `1`, and `DOUBLE` is `2`. Python integer modes both return `int`.

## Spelling and summaries

```python
assert Number.spell(42) == "forty-two"
assert Number.ordinal(3) == "3rd"
assert Number.spell_ordinal(3) == "third"
assert Number.file_size(1024) == "1 KB"
assert Number.abbreviate(1_250_000, precision=2) == "1.25M"
assert Number.for_humans(1_250_000, precision=2) == "1.25 million"
```

Word forms and language coverage follow the installed `num2words` release.
File sizes use binary 1024-byte units. Human summaries use the locale
formatting rules supplied by Babel and Titanspan's documented magnitude
suffixes.

## Bounds and normalization

```python
assert Number.clamp(12, 0, 10) == 10
assert Number.trim(12.0) == 12
assert Number.pairs(25, 10) == [(0, 9), (10, 19), (20, 25)]
```

`pairs(to, by, start=0, offset=1)` builds consecutive inclusive ranges.
The method rejects a zero step and a floating-point step that cannot advance
its current value. `trim` converts integral finite floats to integers while
preserving non-finite float values.

## Locale and currency scopes

Both Laravel camelCase names and Python snake_case names are available and
share one implementation:

```python
Number.use_locale("en")
assert Number.defaultLocale() == Number.default_locale() == "en"

localized = Number.with_locale(
    "de",
    lambda: Number.currency(10, "EUR"),
)
assert localized == "10,00 €"
```

`with_locale` and `with_currency` restore the prior value after success or
failure. Titanspan stores defaults in `ContextVar` values so concurrent
async tasks do not overwrite each other's temporary settings. The explicit
`with_locale_async` and `with_currency_async` variants await asynchronous
callbacks. Synchronous scopes reject awaitable callback results instead of
creating or managing an event loop.

## Public methods

| Laravel method | Python method | Python signature | Purpose |
|---|---|---|---|
| `format` | `format` | `format(number, precision=None, max_precision=None, locale=None)` | Locale-aware decimal formatting |
| `parse` | `parse` | `parse(string, type=NumberParseType.DOUBLE, locale=None)` | Parse a localized decimal |
| `parseInt` | `parse_int` | `parse_int(string, locale=None)` | Parse an integer result |
| `parseFloat` | `parse_float` | `parse_float(string, locale=None)` | Parse a floating-point result |
| `spell` | `spell` | `spell(number, locale=None, after=None, until=None)` | Convert a number to words |
| `ordinal` | `ordinal` | `ordinal(number, locale=None)` | Format ordinal digits |
| `spellOrdinal` | `spell_ordinal` | `spell_ordinal(number, locale=None)` | Spell an ordinal |
| `percentage` | `percentage` | `percentage(number, precision=0, max_precision=None, locale=None)` | Format a percent value |
| `currency` | `currency` | `currency(number, in_="", locale=None, precision=None)` | Format a currency value |
| `fileSize` | `file_size` | `file_size(bytes, precision=0, max_precision=None)` | Format bytes using binary units |
| `abbreviate` | `abbreviate` | `abbreviate(number, precision=0, max_precision=None)` | Format with short magnitude suffixes |
| `forHumans` | `for_humans` | `for_humans(number, precision=0, max_precision=None, abbreviate=False)` | Format with named magnitudes |
| `clamp` | `clamp` | `clamp(number, min, max)` | Bound a numeric value |
| `pairs` | `pairs` | `pairs(to, by, start=0, offset=1)` | Split an inclusive range into pairs |
| `trim` | `trim` | `trim(number)` | Normalize integral float values |
| `withLocale` | `with_locale` | `with_locale(locale, callback)` | Scope the active locale |
| `withCurrency` | `with_currency` | `with_currency(currency, callback)` | Scope the active currency |
| `useLocale` | `use_locale` | `use_locale(locale)` | Set the current context locale |
| `useCurrency` | `use_currency` | `use_currency(currency)` | Set the current context currency |
| `defaultLocale` | `default_locale` | `default_locale()` | Read the active locale default |
| `defaultCurrency` | `default_currency` | `default_currency()` | Read the active currency default |

Every camelCase method is explicitly exposed for compatibility and is an
alias of its snake_case counterpart. The full method-level status and
behavioral differences are recorded in the
[Laravel Support compatibility inventory](../compatibility/laravel-support).

Python reserves the keyword `in`, so the currency argument is named `in_`.
`with_locale_async(locale, callback)` and
`with_currency_async(currency, callback)` are Titanspan async extensions; they
are not listed as Laravel methods.

## Locale and security notes

Babel's CLDR data can differ from PHP's Intl/ICU data, and the displayed
currency symbols, separators, and spacing can change when locale data is
updated. Spellings depend on `num2words` language support. Do not use
formatted currency strings as arithmetic values; retain `Decimal` or integer
minor units for monetary calculations.

The formatter rejects booleans even though `bool` is an `int` subclass in
Python. The class accepts integers and floats; it does not silently coerce
arbitrary strings or custom numeric objects.

## Validation

The focused unit suite exercises each public method, aliases, boundaries,
locale and currency scope restoration, task isolation, and missing optional
dependencies. Integration tests use the actual Babel and `num2words`
packages. Run them with:

```bash
uv run --locked pytest tests/unit/support/test_number.py -q
uv run --locked pytest tests/integration/support/test_number_integration.py -q
```
