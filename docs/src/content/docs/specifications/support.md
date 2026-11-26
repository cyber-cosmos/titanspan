---
title: "Support component specification"
---

<span id="support-component-specification"></span>

Titanspan Support provides reusable Python utilities with one public spelling
per operation. Public APIs use `snake_case`; Python special methods are used
where they express native object behavior. This specification records
implemented ownership and known boundaries. It is not a promise that every
future utility has been implemented.

## Public module ownership

| Area | Owner | Behavioral evidence |
| --- | --- | --- |
| Nested lists and mappings | `support.Arr` | `tests/unit/support/test_arr.py` |
| String transformations | `support.Str` | `tests/unit/support/test_str.py` |
| Fluent string values | `support.Stringable` | `tests/unit/support/test_stringable.py` |
| Mutable attribute mappings | `support.Fluent` | `tests/unit/support/test_fluent.py` |
| Optional value access | `support.Optional` | `tests/unit/support/test_optional.py` |
| Message storage and formatting | `support.MessageBag` | `tests/unit/support/test_message_bag.py` |
| Trusted and encoded HTML | `HtmlString`, `EncodedHtmlString` | `tests/unit/support/test_html_strings.py` |
| URI values and query views | `Uri`, `UriQueryString` | `tests/unit/support/test_uri.py` |
| Numeric formatting | `support.Number` | `tests/unit/support/test_number.py` |
| UUID and ULID binary conversion | `support.BinaryCodec` | `tests/unit/support/test_binary_codec.py` |
| Time and execution helpers | `Sleep`, `Timebox`, `Lottery`, `Benchmark` | Corresponding `tests/unit/support/test_*.py` files |
| Environment and data helpers | `Env` and module functions | `tests/unit/support/test_env.py`, `test_helpers.py` |
| Reusable behavior mixins | `Macroable`, `Conditionable`, `Tappable`, and forwarding helpers | Corresponding `tests/unit/support/test_*.py` files |

## Naming and behavior

- Public functions and methods use one canonical `snake_case` spelling.
- Do not add compatibility-only aliases, wrappers, or protocol declarations.
- Preserve Python collection behavior unless a Titanspan specification
  explicitly documents a domain-specific operation.
- Separate synchronous computation from explicit asynchronous waiting or
  lifecycle operations. Never hide event-loop creation or blocking I/O.
- Use `None` and missing-value sentinels according to each API's documented
  contract; do not substitute truthiness for key-existence checks.
- Runtime macros are explicit extensions. Ordinary declared APIs remain
  statically typed and discoverable.
- HTML contracts distinguish trusted markup from ordinary text. Escaping is
  not sanitization for URLs, CSS, or JavaScript contexts.
- URI parsing does not establish that a destination is safe to fetch.
- URI route factories resolve `UriUrlGenerator` only inside the active
  Application context. Support re-exports the same contract object defined in
  `contracts.routing`; the application provider binds its canonical generator.
- Named URI routes and actions are relative by default. Pass `absolute=True`
  to use the configured trusted origin. Remaining route query values use
  `Arr.query`, the shared RFC 3986 encoder.
- URI redirects use the registered `ResponseFactory`. Parsing remains
  independent of app state, while `Uri.redirect()` requires active app
  context and inherits native external and protocol-relative redirect checks.

## Optional capabilities

Number spelling and locale-aware behavior depend on the `numbers` extra.
Importing `titanspan.support` must not eagerly load optional infrastructure.
Optional integrations must fail with the native Support exception that
identifies the missing capability.

## Verification

The unit suites above establish local behavior. Integration tests under
`tests/integration/support/` verify boundaries with real dependencies.
Cross-component ownership is recorded in `ARCHITECTURE.md`; do not duplicate
collections, configuration, container, lifecycle, or facade implementations
inside Support.
