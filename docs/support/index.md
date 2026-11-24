# Support

The Support module contains shared utilities that other Titanspan modules
can use without importing database, queue, AI, or web infrastructure.

The current implementation includes:

- `Arr` helpers for Python mappings, sequences, and iterables.
- Shared value, nested-data, escaping, and exception helpers.
- `Fluent` for typed, mutable attribute data and nested path access.
- `Optional` for null-safe access and explicit method delegation.
- `Str` for tested string transformations and validators.
- `Stringable` for explicit chainable transformations over `Str`.
- `HtmlString` and `EncodedHtmlString` for trusted markup and escaped text.
- `MessageBag` for keyed messages, wildcard reads, formatting, and JSON output.
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
from titanspan.support import blank, data_get, optional, tap

profile = {"user": {"name": "Ada"}}
assert data_get(profile, "user.name") == "Ada"
assert blank("  ")
assert optional(None).get("name") is None
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

See [arrays](./arrays), [Fluent](./fluent), [helpers](./helpers),
[message bags](./message-bag),
[optional values](./optional), [strings](./strings), and [extensions](./extensions)
for the implemented surface. See [URI utilities](./uris) and
[fluent strings](./stringable) for the implemented `Stringable` methods and
their Python behavior, and [HTML values](./html) for context-aware rendering
guidance.
