---
title: "Number utilities"
---

<span id="number-utilities"></span>

`titanspan.support.Number` formats, parses, and summarizes numeric values.
Locale data and numeric formatting use Babel; number-to-words conversion
uses `num2words`.

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
`False` according to the parser contract. Integer results use
Python's arbitrary-precision `int` and do not overflow at a 32- or 64-bit
boundary.

`NumberParseType` exposes `INT32` as `0`, `INT64` as `1`, and `DOUBLE` as
`2`. Python integer modes both return `int`.

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

```python
Number.use_locale("en")
assert Number.default_locale() == "en"

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

| Method | Purpose |
|---|---|
| `format`, `parse`, `parse_int`, `parse_float` | Locale-aware formatting and parsing. |
| `spell`, `ordinal`, `spell_ordinal` | Convert numbers to words or ordinal forms. |
| `percentage`, `currency`, `file_size` | Format common numeric quantities. |
| `abbreviate`, `for_humans` | Present large values with magnitude labels. |
| `clamp`, `pairs`, `trim` | Bound, partition, or normalize values. |
| `with_locale`, `with_currency` | Scope locale or currency defaults. |
| `use_locale`, `use_currency` | Set context-local defaults. |
| `default_locale`, `default_currency` | Read the active defaults. |

Python reserves the keyword `in`, so the currency argument is named `in_`.
`with_locale_async(locale, callback)` and
`with_currency_async(currency, callback)` are explicit asynchronous
counterparts for awaitable callbacks.

## Locale and security notes

Babel's CLDR data and `num2words` language support can change the displayed
symbols, separators, spacing, and word forms when locale data is updated.
Do not use
formatted currency strings as arithmetic values; retain `Decimal` or integer
minor units for monetary calculations.

The formatter rejects booleans even though `bool` is an `int` subclass in
Python. The class accepts integers and floats; it does not silently coerce
arbitrary strings or custom numeric objects.

## Validation

The focused unit suite exercises public methods, boundaries, locale and
currency scope restoration, task isolation, and missing optional
dependencies. Integration tests use the actual Babel and `num2words`
packages. Run them with:

```bash
uv run --locked pytest tests/unit/support/test_number.py -q
uv run --locked pytest tests/integration/support/test_number_integration.py -q
```
