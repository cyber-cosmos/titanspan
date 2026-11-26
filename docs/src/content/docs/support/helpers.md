---
title: "Shared helpers"
---

<span id="shared-helpers"></span>

Titanspan exposes reusable value, nested-data, and exception helpers from
`titanspan.support`.

```python
from titanspan.support import blank, data_get, data_set, filled

document = {"author": {"name": "Ada"}}
assert data_get(document, "author.name") == "Ada"
assert blank(" \t")
assert filled(0)
data_set(document, "author.role", "maintainer")
```

## Value helpers

- `blank(value)` considers `None`, whitespace-only strings, and empty sized
  values blank. Numeric and boolean values, including `0` and `False`, remain
  filled.
- `filled(value)` is the inverse of `blank`.
- `value(value, *args)` invokes callable values lazily with `args` and returns
  constants unchanged.
- `with_(value, callback=None)` returns the value or the callback result. The
  underscore is required because `with` is a Python keyword.
- `transform(value, callback, default=None)` transforms filled values and
  resolves a value or callback for blank values.
- `retry(times, callback, sleep_milliseconds=0, when=None)` retries a
  synchronous operation with one-based attempt numbers. `times` may be a
  total attempt count or a sequence of millisecond delays between attempts.
- `retry_async(...)` is the explicit asynchronous extension. It uses AnyIO
  for waits and propagates cancellation. Both retry helpers delegate their
  retry controller to Tenacity.
- `tap(value, callback=None)` runs a synchronous side effect and returns the
  original value. Its callback-free form returns a method forwarding proxy;
  call `.call("method", ...)` for a statically discoverable invocation.
- `tap_async(value, callback)` explicitly awaits asynchronous callbacks.

Synchronous callback helpers reject awaitable results. Use their async form
where available; Titanspan never creates an event loop inside a utility.

Retry callbacks receive the current attempt number starting at `1`. Retry
predicates run only when another attempt remains. Use retries for operations
that are safe to repeat; Titanspan cannot undo external side effects from a
failed attempt.

```python
from titanspan.support import retry

attempts: list[int] = []

def fetch(attempt: int) -> str:
    attempts.append(attempt)
    if attempt < 2:
        raise ConnectionError
    return "response"

response = retry(3, fetch, sleep_milliseconds=0)
assert response == "response"
```

The asynchronous form accepts an async callback and never blocks the event
loop:

```python
from titanspan.support import retry_async

async def fetch_async(attempt: int) -> str:
    if attempt < 2:
        raise ConnectionError
    return "response"

response = await retry_async([10, 25], fetch_async)
```

Integer delays are milliseconds. A `datetime.timedelta` or a callable
`(attempt, exception) -> delay` is also accepted. Cancellation and
process-control exceptions are propagated without retry.

## Nested data helpers

`data_get`, `data_has`, `data_set`, `data_fill`, and `data_forget` accept
mapping keys and dot-separated paths. Reads distinguish a missing key from
an explicit `None`. Wildcards select or update child values. Escaped `*`,
`{first}`, and `{last}` segments are treated literally.

```python
users = {"users": [{"name": "Ada"}, {"name": "Lin"}]}
assert data_get(users, "users.*.name") == ["Ada", "Lin"]
data_set(users, "users.*.active", True)
data_fill(users, "users.*.role", "reader")
data_forget(users, "users.*.active")
```

Mutation changes mutable mappings and lists in place. If a path starts at an
immutable scalar, use the returned root because Python cannot replace the
caller's local variable by reference. Deleting a list element shifts later
indexes, following Python list semantics.

`head` returns the first iterable item and `last` consumes an iterable while
retaining only its most recent item. Both return `None` for an empty iterable.

## Escaping and errors

`e` escapes scalar text for HTML and uses the `&#039;` apostrophe reference.
It does not treat arbitrary objects as trusted HTML. HTML wrapper support is
planned separately; escaping is not HTML sanitization.

`throw_if` and `throw_unless` accept Python exception instances, classes,
built-in class names, or exception factories. They use Python truthiness.
Their return value is the original condition when no exception is raised.

`enum_value` returns scalar-backed Python Enum values and uses the member
name when the enum value is not a scalar. For `None`, it resolves the
provided default.

See the [Support specification](/titanspan/specifications/support) for module ownership
and test evidence.
