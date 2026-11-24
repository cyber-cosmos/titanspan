# Fluent data objects

`Fluent` stores mutable attributes and provides nested reads, fluent writes,
condition callbacks, macros, Python mapping operations, and JSON output.

```python
from titanspan.support import Fluent

user: Fluent[str, object] = Fluent({"profile": {"name": "Ada"}})
user.set("profile.role", "maintainer")
assert user.get("profile.name") == "Ada"
assert user.profile == {"name": "Ada", "role": "maintainer"}
```

Initialize from a mapping, an iterable of values, an iterable of key/value
pairs, or a model exposing `model_dump()` or `to_dict()`. Value-only
iterables receive integer keys. A sequence of two-item tuples is interpreted
as key/value pairs.

Use `dynamic_call(name, *values)` for Laravel-style dynamic setters. It stores
`True` when no value is supplied and the first argument otherwise. Python
cannot distinguish a property read from a call such as `user.enabled()` in
the same way PHP's magic methods do, so `dynamic_call` keeps this operation
explicit and typed.

Dynamic property reads return `None` for missing values. Use `get` with a
default for nested paths and `value` for direct keys. `has` includes keys
whose stored value is `None`; `key in fluent` follows Laravel's `isset`
behavior and is false for such keys. The Python item getter returns `None`
for missing keys, and deleting a missing key is a no-op.

Both snake_case methods and Laravel's camelCase names are available where
applicable. CamelCase compatibility methods have narrow Ruff naming
exceptions; internal names remain idiomatic Python.

`to_json` uses Python's standard `json` module. The supported options map
Laravel's pretty-print and unescaped-Unicode bits to Python's JSON encoder.
Other PHP JSON flags are not interpreted.

The `collect` method from Laravel's `InteractsWithData` trait depends on the
not-yet-implemented Titanspan Collections component and is not exposed here.
See the [compatibility inventory](/compatibility/laravel-support) for the
current method status.
