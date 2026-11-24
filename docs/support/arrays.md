# Array utilities

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

## Names

Laravel camelCase method names are available as explicit aliases for methods
that Python can name directly:

```python
assert Arr.has_all(profile, ["user.name"])
assert Arr.hasAll(profile, ["user.name"])
```

Python keywords use legal names with a trailing underscore:

```python
remaining = Arr.except_(profile, "user.active")
converted = Arr.from_(("first", "second"))
```

`Arr.except` and `Arr.from` are not exposed as dynamic attributes. The
explicit aliases remain discoverable by IDEs and static type checkers.

## Input and output behavior

- Mappings retain their keys and insertion order where the operation
  preserves keys.
- Lists and tuples are treated as positional sequences; text and byte strings
  are not treated as sequences of array values.
- Mapping mutation requires a `MutableMapping`; positional mutation requires
  a mutable sequence.
- Mixed incomparable Python values use deterministic categories in sorting.
  This is not PHP's loose comparison behavior.
- Iterables are consumed only where the operation needs to produce a result.
  Helpers that return a complete list or mapping necessarily materialize it.

The method-level matrix links each API to the exact Laravel source file and
records parity status and tests: [Laravel Support compatibility](
/compatibility/laravel-support).
