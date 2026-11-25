# Configuration repository

`titanspan.config.Repository` implements the canonical
`titanspan.contracts.ConfigRepository` protocol. The same instance is bound
through the application container and the active `Config` facade.

## Reads

```python
from titanspan.config import Repository

repository = Repository({"app": {"name": "Titanspan", "debug": False}})
name = repository.get("app.name", "Fallback")
values = repository.get_many({"app.name": "Fallback", "queue.workers": 4})
```

`get()` accepts one dotted path, an ordered sequence of paths, or a mapping
from paths to defaults. `get_many()` and the Laravel-compatible `getMany()`
are also available. Defaults may be values or zero-argument callbacks.

An existing literal key such as `{"app.name": "literal"}` takes priority
over traversing `{"app": {"name": "nested"}}`. Presence checks distinguish
missing keys from explicitly stored `None`, `False`, zero, and empty
containers. Nested traversal delegates to Support's `Arr` implementation.

## Strict typed reads

The `string`, `integer`, `float`, `boolean`, and `array` accessors validate
the stored value without coercion. Integer checks reject booleans; float
checks reject integers. `array()` accepts a mapping or list. Type failures
raise `ConfigValueError` with the key and type names but never the rejected
value.

`collection()` remains unavailable until Titanspan's canonical Collections
component exists. The repository does not provide a substitute collection
type.

## Writes and mapping syntax

```python
repository.set("app.debug", True)
repository.set({"app.name": "Titanspan", "queue.workers": 4})
repository.prepend("app.middleware", "auth")
repository.push("app.middleware", "logging")

assert repository["app.debug"] is True
assert "app.name" in repository
```

Batch `set()` validates keys and applies the change to a structural copy
before replacing the root, so a failed batch does not partially apply.
`prepend()` and `push()` use lists; a missing setting starts as an empty
list. Existing incompatible values raise `TypeError`.

`all()` returns a read-only top-level mapping containing copied built-in
containers. Custom leaf objects retain identity. Python `__getitem__` raises
`KeyError` for absent paths. `del repository[key]` follows Laravel's
`offsetUnset` behavior and writes explicit `None`; it does not remove the
path.

## Macros

Repository macros use the shared Support `Macroable` registry. Register with
`Repository.macro()` or `Repository.mixin()`, inspect with `has_macro()` or
`hasMacro()`, and clean up with `flush_macros()` or `flushMacros()`. Dynamic
attribute lookup is intentionally absent; use `repository.call_macro()` for
typed, explicit invocation. Macro registration is class-level and shared
between repository instances.
