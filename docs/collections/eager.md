# Eager collections

`Collection` stores a shallow, ordered snapshot. Use `collect()` to create
one:

```python
from dataclasses import dataclass

from titanspan.collections import collect

@dataclass(frozen=True)
class User:
    """Represent a user in the eager pipeline example.

    Attributes:
        active: Whether the user is active.
        name: The user's display name.
    """

    active: bool
    name: str

users = [User(active=True, name="Ada"), User(active=False, name="Lin")]

active_names = (
    collect(users)
    .filter(lambda user: user.active)
    .map(lambda user: user.name)
    .unique()
    .sort()
)
```

The collection implements iteration, `len()`, membership, integer and
negative indexing, slicing, and reverse iteration. A mapping is iterated as
keys. Pass `mapping.values()` or `mapping.items()` to select other data.

## Transform and select

`map()` uses its callback's return type. `filter()` keeps truthy callback
results; `reject()` keeps false-like results. `flat_map()` concatenates the
iterables returned by its callback. `flatten()` uses Support's nested array
semantics.

Use `pluck()` for a mapping path or `map()` for callback-based extraction:

```python
from titanspan.collections import collect

profiles = collect([
    {"user": {"name": "Ada"}},
    {"user": {"name": "Lin"}},
])

names = profiles.pluck("user.name")
upper_names = profiles.map(
    lambda profile: profile["user"]["name"].upper()
)
```

`take()`, `skip()`, `slice()`, `chunk()`, `partition()`, `reverse()`,
`enumerate()`, and `zip()` return new values. `chunk(size)` requires a
positive size and includes a shorter final chunk. `zip()` stops at the
shortest input.

## Searching and callbacks

`contains()` and `search()` use Python equality. `search()` returns the first
index or `None`. `every()` and `some()` use Python truthiness and follow the
empty-input behavior of `all()` and `any()`.

`each()` calls a synchronous side-effect callback for every item and returns
the same collection. It propagates callback errors and rejects awaitable
results. `tap()` uses Support's `Tappable` mixin. `pipe()` returns the value
from its callback.

Transformations create new collection containers. They do not copy nested
objects, so mutable items remain shared references. See the
[behavioral specification](/specifications/collections) for empty values,
defaults, equality, and errors.
