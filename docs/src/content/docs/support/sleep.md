---
title: "Sleep"
---

<span id="sleep"></span>

`Sleep` builds a duration and executes it explicitly. It uses standard
library time values for durations, `time.sleep` for synchronous waits, and
AnyIO for asynchronous waits.

## Build a duration

Every numeric duration needs a unit. Builders can add several units:

```python
from titanspan.support import Sleep

duration = (
    Sleep.for_(1)
    .second()
    .and_(250)
    .milliseconds()
)

async def wait_for_duration() -> None:
    """Wait without blocking the event loop.

    Returns:
        None.
    """
    await duration.sleep_async()
```

`for_`, `and_`, and `while_` use trailing underscores because those names
conflict with Python keywords. Singular and plural unit methods are available.

`Sleep.sleep(seconds)` and `Sleep.usleep(microseconds)` create completed
duration builders. `Sleep.until(timestamp, now=...)` accepts a Python
`datetime` or a numeric Unix timestamp. The optional `now` argument supports
deterministic tests.

## Execute synchronously or asynchronously

The builder does not sleep when it is created, discarded, or garbage
collected. Choose the execution method for the current context:

```python
Sleep.for_(10).milliseconds().sleep_sync()

async def wait_asynchronously() -> None:
    """Wait asynchronously for a short duration.

    Returns:
        None.
    """
    await Sleep.for_(100).milliseconds().sleep_async()
```

`sleep_async` waits through AnyIO, so it yields to other tasks and propagates
cancellation. `then` runs a synchronous callback after `sleep_sync`; use
`then_async` for an asynchronous callback. A synchronous callback that returns
an awaitable is rejected instead of leaving un-awaited work behind.

The `when` and `unless` conditions accept booleans or synchronous callbacks
that receive the builder. `when_async` and `unless_async` explicitly await
asynchronous conditions. `while_` accepts a synchronous zero-argument
predicate; `while_async` accepts a predicate that may be asynchronous.
Repetition applies to real waits. Fake sleeps record one operation and skip
the repetition callback.

## Fake waits in tests

Fake state is scoped to the current `ContextVar` context. Calling `fake`
starts a fresh sequence and callback list:

```python
from datetime import timedelta

from titanspan.support import Sleep

async def use_fake_sleep() -> None:
    """Record a fake sleep and verify its duration.

    Returns:
        None.
    """
    Sleep.fake()
    await Sleep.for_(3).seconds().sleep_async()

    Sleep.assert_slept_times(1)
    Sleep.assert_slept(timedelta(seconds=3))
```

`when_faking_sleep` registers callbacks that receive each recorded
`timedelta`. `assert_sequence` compares an ordered list of durations or Sleep
builders; `None` skips a comparison. `assert_never_slept` verifies an empty
sequence, and `assert_insomniac` accepts only zero-duration entries.

## Python adaptations

- A duration value is an immutable `datetime.timedelta`. Assign a new
  `timedelta` to `Sleep.duration` to replace it.
- Waiting is explicit. Python object finalization does not trigger a blocking
  sleep.
- Async waits and callback variants use explicit `_async` method names.
- Fake state uses context-local storage instead of process-global static
  state, which isolates separate requests and tests.
- Durations are limited to the range Python's `datetime.timedelta` can
  represent. Fractional amounts truncate at microsecond precision.

## Tests

Titanspan's deterministic unit tests are in
`tests/unit/support/test_sleep.py`; AnyIO scheduling and cancellation tests
are in `tests/integration/support/test_sleep_async.py`.
