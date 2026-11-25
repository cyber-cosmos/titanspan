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

Use `dynamic_call(name, *values)` for explicit dynamic setters. It stores
`True` when no value is supplied and the first argument otherwise. Python
cannot distinguish a property read from a call such as `user.enabled()` using
ordinary attribute syntax, so `dynamic_call` keeps this operation explicit.

Dynamic property reads return `None` for missing values. Use `get` with a
default for nested paths and `value` for direct keys. `has` includes keys
whose stored value is `None`; `key in fluent` checks key presence. The Python
item getter returns `None` for missing keys, and deleting a missing key is a
no-op.

`to_json` uses Python's standard `json` module and its documented Titanspan
options.

Collection conversion is not provided until the canonical
`titanspan.collections` component owns that behavior. See the
[Support specification](/specifications/support) for current boundaries.
