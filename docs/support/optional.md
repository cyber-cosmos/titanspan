# Optional values

`Optional` wraps a Python value for null-safe reads and explicit delegation.

```python
from titanspan.support import Optional, optional

profile: dict[str, object] = {"name": "Ada"}
wrapped = Optional(profile)
assert wrapped["name"] == "Ada"
wrapped["role"] = "maintainer"

if wrapped.has("role"):
    assert wrapped.get("role") == "maintainer"

assert optional(None).get("name") is None
assert optional("Ada", str.upper) == "ADA"
```

`has` follows key-existence semantics, so a key containing `None` still
exists. `is_set` follows null-aware attribute semantics. Item mutation is
available for mutable mappings and lists; immutable wrapped values ignore
set and delete operations.

Method delegation is explicit so static analysis can see where dynamic calls
occur:

```python
result = wrapped.call("get", "name")
```

`call_async` awaits an underlying asynchronous method. `optional_async`
awaits a callback only when its candidate is not `None`; the synchronous
`optional` helper rejects async callbacks and directs callers to that API.

Attribute access is provided for convenience, but Python type checkers cannot
infer attributes on arbitrary wrapped values. Use typed wrapper protocols in
application code when static guarantees are required.

See the [Support specification](/specifications/support) for ownership and
verification boundaries.
