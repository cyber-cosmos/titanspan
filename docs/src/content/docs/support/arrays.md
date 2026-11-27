---
title: "Array utilities"
---

<span id="array-utilities"></span>

`Arr` provides static helpers for nested data, keyed transformations,
selection, sorting, query encoding, and conditional CSS values.

```python
from titanspan.support import Arr

profile: dict[str, object] = {
    "user": {"name": "Ada", "active": True},
}

assert Arr.get(profile, "user.name") == "Ada"
assert Arr.has(profile, "user.active")
Arr.set(profile, "user.role", "admin")
assert Arr.get(profile, "user.role") == "admin"
```

Python's `None` is a valid stored value. `Arr.get` distinguishes a missing
path from a present path whose value is `None`; defaults are used only for
missing paths. Mutable helpers such as `set`, `forget`, `pull`, and `push`
mutate the supplied mutable object and return values according to their
individual contracts.

## Python naming

Public operations use snake_case. Python keywords use legal names with a
trailing underscore:

```python
assert Arr.has_all(profile, ["user.name"])
```

Python keywords use legal names with a trailing underscore:

```python
remaining = Arr.except_(profile, "user.active")
converted = Arr.from_(("first", "second"))
```

`except` and `from` are Python keywords, so their APIs are named `except_` and
`from_` and remain discoverable by IDEs and static type checkers.

## Input and output behavior

- Mappings retain their keys and insertion order where the operation
  preserves keys.
- Lists and tuples are treated as positional sequences; text and byte strings
  are not treated as sequences of array values.
- Mapping mutation requires a `MutableMapping`; positional mutation requires
  a mutable sequence.
- Mixed incomparable Python values use deterministic categories in sorting.
- Iterables are consumed only where the operation needs to produce a result.
  Helpers that return a complete list or mapping necessarily materialize it.

The [Support specification](/framework/specifications/support) records module
ownership, implementation boundaries, and test evidence.
