# Support

The Support module contains shared utilities that other Titanspan modules
can use without importing database, queue, AI, or web infrastructure.

The current implementation includes:

- `Arr` helpers for Python mappings, sequences, and iterables.
- Shared value, nested-data, escaping, and exception helpers.
- `Fluent` for typed, mutable attribute data and nested path access.
- `Optional` for null-safe access and explicit method delegation.
- `Env` and `env` for normalized process environment access, scoped adapters,
  and explicit dotenv file updates.
- `Str` for tested string transformations and validators.
- `Stringable` for explicit chainable transformations over `Str`.
- `Number` for locale-aware formatting, parsing, spelling, and summaries;
  Babel and `num2words` are available through the optional `numbers` extra.
- `HtmlString` and `EncodedHtmlString` for trusted markup and escaped text.
- `MessageBag` for keyed messages, wildcard reads, formatting, and JSON output.
- `Benchmark`, `Lottery`, `Sleep`, and `Timebox` for measured execution,
  probabilistic callbacks, explicit waiting, and minimum-duration operations.
- `Uri` and `UriQueryString` for immutable URL components and nested query
  data, with Starlette redirect interoperability.
- `Macroable` for explicit, typed macro registration and invocation.
- `Conditionable` for synchronous and asynchronous conditional callbacks.
- `Tappable` for callback observation while preserving instance identity.

These APIs follow Laravel Support's developer experience where Python has a
clear equivalent. Titanspan does not emulate PHP arrays, traits, or magic
method dispatch. See the [compatibility inventory](
/compatibility/laravel-support) for the pinned source baseline, method-level
status, and documented differences.

## Imports

```python
from titanspan.support import Arr, Conditionable, Macroable
```

Value helpers are available from the same package:

```python
from titanspan.support import blank, data_get, env, optional, tap

profile = {"user": {"name": "Ada"}}
assert data_get(profile, "user.name") == "Ada"
assert blank("  ")
assert optional(None).get("name") is None
debug = env("TITANSPAN_DEBUG", False)
```

The module has no optional AI, database, queue, or infrastructure
dependencies. URI redirects reuse the Starlette version already installed
through the web foundation; URI parsing and encoding otherwise use the Python
standard library and Titanspan's `Arr` helpers.

## Compatibility status

Support is under active development. Arr methods are implemented and have
initial unit coverage, but their complete Laravel behavioural parity has not
been verified. Macroable has tested explicit invocation equivalents for
Laravel's dynamic calls. Conditionable supports direct callback forms;
Laravel's higher-order proxy forms remain planned.

See [arrays](./arrays), [environment utilities](./environment),
[Fluent](./fluent), [helpers](./helpers),
[message bags](./message-bag),
[optional values](./optional), [strings](./strings), and [extensions](./extensions)
for the implemented surface. See [URI utilities](./uris) and
[fluent strings](./stringable) for the implemented `Stringable` methods and
their Python behavior, [HTML values](./html) for context-aware rendering
guidance, [timing utilities](./timing) for `Benchmark`, `Lottery`, and
`Timebox`, and [Sleep](./sleep) for explicit synchronous and asynchronous
waiting. See [Number utilities](./numbers) for numeric formatting, locale
scopes, optional dependencies, and Python-specific behavior.
