# Fluent strings

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
    .toString()
)

assert result == "hello-world-framework"
```

Use either Laravel-compatible camelCase names or Python snake_case names:

```python
from titanspan.support import Stringable

name = Stringable("path/to/report.csv")
assert name.afterLast("/").beforeLast(".").to_string() == "report"
assert name.after_last("/").before_last(".").toString() == "report"
```

The current implemented surface includes delimiter and case transformations,
matching and predicates, literal and regular-expression replacement, padding,
truncation, word operations, Base64 conversion, and read-only or mutable
integer offsets. See the [method-level compatibility inventory] for the
verified methods and test evidence.

## Conditional operations

Predicate-specific methods such as `when_contains()`, `when_is_uuid()`, and
`when_starts_with()` delegate callback selection to `Conditionable`. Both
snake_case and Laravel camelCase spellings are available. A callback receives
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

Python strings index Unicode code points, while PHP string offsets operate on
bytes. Titanspan follows Python indexing, including negative indexes and
slices. Integer assignment and deletion mutate the current wrapper to preserve
the useful part of Laravel's `ArrayAccess` behavior; chainable transformations
return new wrappers.

Methods that return Laravel collections remain unavailable until the
canonical `titanspan.collections` implementation exists. Date, URI, Markdown,
encryption, and dynamic property behavior also remain outside this implemented
surface. `Macroable` supports explicit registration and `call_macro`; registered
macros are not exposed through dynamic attribute lookup, so static type checkers
can continue to validate normal method calls.

## Reference

The compatibility baseline is Laravel `v13.44.1`, commit
`8a8c4a84852869e13190d89f9da873cd9a70f14c`. Titanspan's tests and API design are
informed by the pinned upstream [Stringable implementation] and
[Stringable tests]. Titanspan is an independent project and is not affiliated
with Laravel.

[method-level compatibility inventory]: ../compatibility/laravel-support
[Stringable implementation]: https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Support/Stringable.php
[Stringable tests]: https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/tests/Support/SupportStringableTest.php
