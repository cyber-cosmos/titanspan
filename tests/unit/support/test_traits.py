"""Verify shared macro and conditional execution contracts.

Tests exercise observable registration, binding, callback, and async
behaviour without relying on a concrete framework service.
"""

import asyncio
from collections.abc import Callable
from typing import Self, cast

import pytest

from titanspan.support import Conditionable, Macroable


class MacroTarget(Macroable):
    """Provide an isolated macro registry and instance state.

    Attributes:
        prefix: Text included by instance-bound macro callbacks.
    """

    def __init__(self) -> None:
        """Initialize state used to validate instance callback binding.

        The class deliberately adds no custom macro dispatch magic; callers
        use the explicit typed invocation methods inherited from Macroable.
        """
        self.prefix = "Titanspan"


class ChildMacroTarget(MacroTarget):
    """Provide a child class for checking registry isolation.

    The child inherits existing registrations at class creation time and
    can subsequently change them without mutating its parent's registry.
    """


class ConditionalValue(Conditionable):
    """Provide a simple mutable value for conditional callback tests.

    Attributes:
        values: Ordered items recorded by callback execution.
    """

    def __init__(self) -> None:
        """Initialize the list used by conditional callback operations.

        The mutable state makes callback selection and fluent return values
        observable in a deterministic way.
        """
        self.values: list[object] = []

    def append(self, value: object) -> Self:
        """Append one value and preserve fluent chaining.

        Args:
            value: The value to append.

        Returns:
            This instance for subsequent conditional operations.
        """
        self.values.append(value)
        return self


@pytest.mark.unit
def test_macro_registry_supports_static_and_instance_calls() -> None:
    """Resolve macros explicitly and bind registered functions to objects.

    Returns:
        None.
    """

    def greet(name: str = "Guest") -> str:
        """Return a greeting for the selected name.

        Args:
            name: The person to greet.

        Returns:
            A plain-text greeting.
        """
        return f"Hello, {name}"

    def add_prefix(self: MacroTarget, value: str) -> str:
        """Combine instance state with one supplied value.

        Args:
            self: The object receiving the macro call.
            value: The suffix to append.

        Returns:
            The instance prefix followed by the suffix.
        """
        return f"{self.prefix} {value}"

    MacroTarget.flush_macros()
    MacroTarget.macro("greet", greet)
    MacroTarget.macro("add_prefix", add_prefix)

    assert MacroTarget.has_macro("greet")
    assert MacroTarget.hasMacro("greet")
    assert MacroTarget.invoke_macro("greet") == "Hello, Guest"
    assert MacroTarget.invoke_macro("greet", "Ada") == "Hello, Ada"
    assert MacroTarget().call_macro("add_prefix", "beyond limits") == (
        "Titanspan beyond limits"
    )


@pytest.mark.unit
def test_macro_mixin_replacement_and_subclass_registry_are_isolated() -> None:
    """Mix in callable factories while keeping child mutations isolated.

    Returns:
        None.
    """

    class Mixin:
        """Provide macro factories for registry mixin tests.

        The protected factory validates Laravel-style inclusion of
        protected mixin methods.
        """

        def salute(self) -> Callable[[str], str]:
            """Create a macro that salutes a named person.

            Returns:
                A callback that formats the requested salutation.
            """

            def callback(name: str) -> str:
                """Format one salute.

                Args:
                    name: The person to salute.

                Returns:
                    A formatted salutation.
                """
                return f"Greetings, {name}"

            return callback

        def _hidden(self) -> Callable[[], str]:
            """Create a protected macro to mirror mixin discovery rules.

            Returns:
                A callback returning the protected factory result.
            """
            return lambda: "protected"

    MacroTarget.flush_macros()
    MacroTarget.macro("salute", lambda: "existing")
    MacroTarget.mixin(Mixin(), replace=False)
    assert MacroTarget.invoke_macro("salute") == "existing"
    assert MacroTarget.invoke_macro("_hidden") == "protected"

    MacroTarget.mixin(Mixin())
    assert MacroTarget.invoke_macro("salute", "Ada") == "Greetings, Ada"
    assert ChildMacroTarget.has_macro("salute")
    ChildMacroTarget.macro("salute", lambda: "child")
    assert ChildMacroTarget.invoke_macro("salute") == "child"
    assert MacroTarget.invoke_macro("salute", "Ada") == "Greetings, Ada"


@pytest.mark.unit
def test_macro_lookup_and_registration_fail_explicitly() -> None:
    """Reject unknown macros and invalid registrations with clear errors.

    Returns:
        None.
    """
    MacroTarget.flush_macros()

    with pytest.raises(LookupError, match="unknown macro"):
        MacroTarget.invoke_macro("missing")

    with pytest.raises(ValueError, match="name must not be empty"):
        MacroTarget.macro("", lambda: None)

    with pytest.raises(TypeError, match="must be callable"):
        MacroTarget.macro(
            "invalid",
            cast("Callable[..., object]", object()),
        )

    class InvalidMixin:
        """Provide a malformed callback factory for validation coverage.

        The factory returns an ordinary object rather than a callable.
        """

        def broken(self) -> object:
            """Return a non-callable value from a mixin factory.

            Returns:
                An object that cannot be registered as a macro.
            """
            return object()

    with pytest.raises(TypeError, match="must return a callable"):
        MacroTarget.mixin(InvalidMixin())

    with pytest.raises(LookupError, match="unknown macro"):
        MacroTarget().call_macro("missing")

    MacroTarget.macro("present", lambda: "value")
    assert MacroTarget.has_macro("absent") is False
    Macroable.macro("root_only", lambda: "root")
    assert ChildMacroTarget.invoke_macro("root_only") == "root"
    Macroable.flush_macros()


@pytest.mark.unit
def test_when_and_unless_choose_callbacks_and_preserve_fluent_values() -> None:
    """Select conditional callbacks and retain self for None results.

    Returns:
        None.
    """
    value = ConditionalValue()
    assert value.when(True) is value
    assert value.unless(False) is value
    assert (
        value.when(
            True,
            lambda _current, _condition: None,
        )
        is value
    )
    when_result = value.when(
        lambda current: current.append("condition") is current,
        lambda current, condition: current.append(condition),
    )
    assert when_result is value
    assert value.values == ["condition", True]

    value.unless(
        False,
        lambda current, condition: current.append(condition),
    )
    value.unless(
        True,
        lambda current, _condition: current.append("wrong"),
        lambda current, condition: current.append(condition),
    )
    assert value.values[-2:] == [False, True]

    alternate = value.when(
        False,
        lambda _current, _condition: "wrong",
        lambda _current, _condition: "fallback",
    )
    assert alternate == "fallback"


@pytest.mark.unit
def test_sync_conditionable_rejects_async_callbacks_explicitly() -> None:
    """Direct async users to the explicit awaitable conditional methods.

    Returns:
        None.
    """

    async def callback(
        current: ConditionalValue,
        _: object,
    ) -> ConditionalValue:
        """Return a coroutine for the synchronous API to reject.

        Args:
            current: The conditionable target.
            _: The resolved condition value.

        Returns:
            The target after appending the marker.
        """
        return current.append("async")

    with pytest.raises(TypeError, match="use when_async"):
        ConditionalValue().when(True, callback)


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_conditionable_awaits_conditions_and_callbacks() -> None:
    """Await async condition and callback operations without hiding them.

    Returns:
        None.
    """

    async def condition(current: ConditionalValue) -> bool:
        """Resolve the asynchronous condition used by this test.

        Args:
            current: The conditionable target.

        Returns:
            Whether the target is initially empty.
        """
        return not current.values

    async def callback(
        current: ConditionalValue,
        result: object,
    ) -> ConditionalValue:
        """Append the resolved condition and return the target.

        Args:
            current: The conditionable target.
            result: The resolved condition value.

        Returns:
            The target after appending the condition result.
        """
        return current.append(result)

    value = ConditionalValue()
    result = await value.when_async(condition, callback)

    assert result is value
    assert value.values == [True]


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_conditionable_sync_callbacks_and_defaults() -> None:
    """Handle direct values, sync callbacks, defaults, and None results.

    Returns:
        None.
    """
    value = ConditionalValue()
    result = await value.when_async(
        True,
        lambda current, condition: current.append(condition),
    )
    assert result is value

    no_branch = await value.when_async(False)
    assert no_branch is value

    default = await value.when_async(
        False,
        lambda _current, _condition: "wrong",
        lambda current, condition: current.append(condition),
    )
    assert default is value

    unless = await value.unless_async(
        False,
        lambda current, condition: current.append(condition),
    )
    assert unless is value

    no_unless_branch = await value.unless_async(True)
    assert no_unless_branch is value

    none_result = await value.unless_async(
        True,
        default=lambda _current, _condition: None,
    )
    assert none_result is value
    assert value.values == [True, False, False]


@pytest.mark.unit
def test_sync_conditionable_rejects_async_conditions() -> None:
    """Reject async conditions without leaving coroutines unawaited.

    Returns:
        None.
    """

    async def condition(_: ConditionalValue) -> bool:
        """Return an awaitable condition for misuse detection.

        Args:
            _: The target, unused because this condition is fixed.

        Returns:
            The condition result.
        """
        return True

    with pytest.raises(TypeError, match="use when_async"):
        ConditionalValue().when(condition)


@pytest.mark.unit
@pytest.mark.anyio
async def test_sync_conditionable_rejects_non_coroutine_awaitables() -> None:
    """Reject resolved Futures returned through synchronous methods.

    Returns:
        None.
    """
    condition = asyncio.get_running_loop().create_future()
    condition.set_result(True)
    callback_result = asyncio.get_running_loop().create_future()
    callback_result.set_result("done")

    with pytest.raises(TypeError, match="use when_async"):
        ConditionalValue().when(condition)
    with pytest.raises(TypeError, match="use when_async"):
        ConditionalValue().when(
            True,
            lambda _current, _condition: callback_result,
        )
