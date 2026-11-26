---
title: "Fluent strings"
---

<span id="fluent-strings"></span>

`Stringable` wraps a Python string with chainable transformations backed by
`titanspan.support.Str`. Transformations return a new wrapper. Predicates,
positions, callback parsing, and other extraction methods keep their native
Python return types.

```python
from titanspan.support import Str

result = (
    Str.of("  Hello World  ")
    .trim()
    .lower()
    .replace(" ", "-")
    .append("-framework")
    .to_string()
)

assert result == "hello-world-framework"
```

Use the native snake_case API:

```python
from titanspan.support import Stringable

name = Stringable("path/to/report.csv")
assert name.after_last("/").before_last(".").to_string() == "report"
```

The current implemented surface includes delimiter and case transformations,
matching and predicates, literal and regular-expression replacement, padding,
truncation, word operations, Base64 conversion, and read-only or mutable
integer offsets. The [Support specification](/titanspan/specifications/support) links
this module to its test evidence.

## Conditional operations

Predicate-specific methods such as `when_contains()`, `when_is_uuid()`, and
`when_starts_with()` delegate callback selection to `Conditionable`. A callback receives
the `Stringable` instance and the predicate result; a default callback handles
the false case. Synchronous methods reject awaitable callback results. Use the
explicit async methods on `Conditionable` when callbacks need to be awaited.

```python
from titanspan.support import Stringable

value = Stringable("report.csv").when_ends_with(
    ".csv",
    lambda current, _matched: current.append(".ready"),
)

assert value.to_string() == "report.csv.ready"
```

## Python behavior

Python strings index Unicode code points. Titanspan follows Python indexing,
including negative indexes and slices. Integer assignment and deletion mutate
the current wrapper; chainable transformations return new wrappers.

Collection-returning operations are not part of the current `Stringable` API.
Date, URI, Markdown, encryption, and dynamic property behavior also remain
outside this implemented surface. `Macroable` supports explicit registration
and `call_macro`; registered macros are not exposed through dynamic attribute
lookup, so static type checkers can continue to validate normal method calls.

See the [Support specification](/titanspan/specifications/support) for module ownership
and verification boundaries.
