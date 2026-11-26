---
title: "Grouping and aggregation"
---

<span id="grouping-and-aggregation"></span>

Collection callbacks use ordinary Python functions. Type parameters follow
callback return types, so transformations remain discoverable to static
checkers.

## Order and group values

`sort()` uses Python's stable ordering. `sort_by()` accepts a callback or a
direct or dotted mapping path. The selected values must be mutually
comparable.

`group_by()`, `key_by()`, and `count_by()` accept callbacks that return
hashable values:

```python
from dataclasses import dataclass

from titanspan.collections import collect

@dataclass(frozen=True)
class User:
    """Represent a user with a department and key fields.

    Attributes:
        active: Whether the user is active.
        department: The group assigned to the user.
        identifier: The user's unique identifier.
    """

    active: bool
    department: str
    identifier: int

@dataclass(frozen=True)
class Event:
    """Represent a named event with a unique identifier.

    Attributes:
        identifier: The event's unique identifier.
        name: The event label.
    """

    identifier: int
    name: str

users = [
    User(active=True, department="research", identifier=1),
    User(active=False, department="platform", identifier=2),
]
events = [Event(identifier=1, name="created")]

grouped = collect(users).group_by(lambda user: user.department)
latest_by_id = collect(events).key_by(lambda event: event.identifier)
counts = collect(users).count_by(lambda user: user.active)
```

`group_by()` returns an insertion-ordered `dict` whose values are
`Collection` instances. `key_by()` follows normal dictionary assignment, so
later duplicate keys replace earlier values. `count_by()` returns native
integer counts. Use `Arr.get()` inside a callback when a mapping path is
needed.

## Aggregation

`reduce()` requires an initial accumulator. `sum()` supports `int`, `float`,
and `complex` values. `average()` returns a float. `median()` returns the
middle value or averages the two middle values. `min()` and `max()` accept an
optional ordering callback.

Empty `min()` and `max()` calls raise `ValueError`. Empty `average()` and
`median()` calls raise `statistics.StatisticsError`. `sum()` returns zero on
empty input. Other Python and callback exceptions propagate.

## Mapping interoperability

`collect(mapping)` iterates over mapping keys, following Python's mapping
iteration behavior. Pass `mapping.values()` or `mapping.items()` when you
need values or key-value pairs. `group_by()`, `key_by()`, and `count_by()`
return native dictionaries. Collections does not wrap mapping results in a
separate keyed collection.

`pluck(path)` uses Support's `Arr.get()` for nested mapping access. Missing
paths produce `None`, as they do in `Arr`. Use `map()` for an extraction
callback or for fields on objects such as `Fluent`.

## Typing and errors

```python
from dataclasses import dataclass

from titanspan.collections import Collection, collect

@dataclass(frozen=True)
class User:
    """Represent a user in a typed collection pipeline.

    Attributes:
        department: The group assigned to the user.
        name: The user's display name.
    """

    department: str
    name: str

users = [User(department="research", name="Ada")]

names: Collection[str] = collect(users).map(lambda user: user.name)
groups: dict[str, Collection[User]] = collect(users).group_by(
    lambda user: user.department
)
```

Grouping keys must be hashable. Python raises `TypeError` when a callback
returns an unhashable value. Python also raises `TypeError` when sort keys
cannot be compared. Callbacks are never caught or rewritten.

Collections follow Python iteration and equality conventions. They do not
coerce values or silently replace false-like values with defaults. See the
[behavioral specification](/titanspan/specifications/collections) for full details.
