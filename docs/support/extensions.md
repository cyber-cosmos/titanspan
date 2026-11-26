# Conditional callbacks and macros

## Conditionable

Use `Conditionable` as a mixin when an object should support conditional
fluent callbacks:

```python
from __future__ import annotations

from titanspan.support import Conditionable


class QueryOptions(Conditionable):
    """Store a small set of fluent query options.

    Attributes:
        enabled: Whether the options are enabled.
    """

    def __init__(self) -> None:
        """Create options in the disabled state.

        The state is intentionally local to this object.
        """
        self.enabled = False

    def enable(self) -> QueryOptions:
        """Enable the options and return this object for chaining.

        Returns:
            This object after updating its state.
        """
        self.enabled = True
        return self


options = QueryOptions().when(
    True,
    lambda current, _condition: current.enable(),
)
assert isinstance(options, QueryOptions)
assert options.enabled
```

`when` and `unless` accept a value or a synchronous callback that receives
the target. The selected callback receives the target and resolved value.
When it returns `None`, the original target is returned for fluent use.

Use `when_async` or `unless_async` for callbacks or condition functions that
return awaitables. The synchronous methods reject awaitables instead of
silently leaving coroutines unawaited. Cancellation propagates from awaited
callbacks.

`when()` requires an explicit condition. The callback API keeps condition
handling visible to type checkers and readers.

## Macroable

`Macroable` uses an explicit invocation API because Python static type checkers
cannot discover dynamically added attributes:

```python
from titanspan.support import Macroable


class TextTools(Macroable):
    """Expose named text helpers through a class-scoped registry.

    Macro registrations belong to this class and its subclasses.
    """


def greet(name: str = "Guest") -> str:
    """Return a greeting for one person.

    Args:
        name: The person to greet.

    Returns:
        A plain-text greeting.
    """
    return f"Hello, {name}"


TextTools.macro("greet", greet)
assert TextTools.invoke_macro("greet", "Ada") == "Hello, Ada"
```

`call_macro` binds plain Python functions to an object. `invoke_macro` calls
the registered callback without an object. Mixin factories may return
closures that retain their normal Python closure binding. Macro registries
are isolated per class, inherited through the class hierarchy, and guarded
during updates with a thread lock.

Macro invocation is explicit through `call_macro()` or `invoke_macro()`.
Declare static wrappers for macros that form part of a stable public API so
type checkers can discover their signatures.

## Tappable

`Tappable` delegates to the shared `tap` helper. A callback observes or
mutates the value, and the original object is returned. Omitting the callback
returns an explicit proxy that invokes one named method through `call`:

```python
from titanspan.support import Stringable

name = Stringable("TITANSPAN")
observed: list[str] = []
assert name.tap(lambda current: observed.append(current.value())) is name
assert observed == ["TITANSPAN"]
assert name.tap().call("lower") is name
```

The synchronous API rejects callbacks that return awaitables. Use the shared
`tap_async` helper when an asynchronous callback is required.
