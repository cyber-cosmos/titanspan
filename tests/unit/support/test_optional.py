"""Verify null-safe access and delegation through Optional values.

The cases cover wrapped objects, mutable containers, and async calls.
"""

from __future__ import annotations

import asyncio

import pytest

from titanspan.support import Optional, optional, optional_async

INPUT_VALUE = 4
DOUBLED_VALUE = 8
ASYNC_RESULT = 5
OPTIONAL_ASYNC_RESULT = 6
NOT_INTEGER_ERROR = "Expected an integer."


@pytest.mark.unit
def test_optional_factory_wraps_values_and_skips_callbacks_for_none() -> None:
    """Wrap without callbacks and avoid invoking callbacks on ``None``.

    Returns:
        None.
    """
    calls: list[int] = []

    def record(item: int) -> int:
        """Record and return a value if the callback is invoked.

        Args:
            item: The integer to append to the call history.

        Returns:
            The unchanged integer.
        """
        calls.append(item)
        return item

    absent = optional(None)
    present = optional(INPUT_VALUE)
    transformed = optional(INPUT_VALUE, lambda item: item * 2)
    skipped = optional(None, record)

    assert isinstance(absent, Optional)
    assert absent.wrapped is None
    assert isinstance(present, Optional)
    assert present.wrapped == INPUT_VALUE
    assert transformed == DOUBLED_VALUE
    assert skipped is None
    assert calls == []


@pytest.mark.unit
def test_optional_reads_nested_mapping_and_preserves_missing_semantics() -> (
    None
):
    """Read nested mapping data and distinguish missing from null values.

    Returns:
        None.
    """
    data: dict[str, object] = {
        "profile": {"name": "Ada", "nickname": None},
    }
    value = Optional(data)

    assert value["profile.name"] == "Ada"
    assert value["profile.missing"] is None
    assert "profile.nickname" in value
    assert value.has("profile.nickname")
    assert not value.has("profile.missing")
    assert value.get("profile.missing", "fallback") == "fallback"


@pytest.mark.unit
def test_optional_mutates_only_supported_mutable_containers() -> None:
    """Update and remove values in mutable mappings and lists.

    Returns:
        None.
    """
    data: dict[str, object] = {"name": "Ada"}
    wrapped = Optional(data)

    wrapped["role"] = "admin"
    assert data == {"name": "Ada", "role": "admin"}
    del wrapped["name"]
    assert data == {"role": "admin"}

    immutable = Optional(("first", "second"))
    immutable[0] = "changed"
    del immutable[0]
    assert immutable[0] == "first"


@pytest.mark.unit
def test_optional_reads_object_attributes_and_delegates_methods() -> None:
    """Read object properties and explicitly delegate method calls.

    Returns:
        None.
    """

    class User:
        """Represent an object with property and method access.

        The public name attribute is used by the greeting method.
        """

        name = "Ada"

        def greet(self, prefix: str) -> str:
            """Build a greeting with a caller-supplied prefix.

            Args:
                prefix: The greeting prefix.

            Returns:
                A greeting containing the user's name.
            """
            return f"{prefix}, {self.name}"

    wrapped = Optional(User())

    assert wrapped.name == "Ada"
    assert wrapped["name"] is None
    assert wrapped.call("greet", "Hello") == "Hello, Ada"
    assert Optional(None).call("greet") is None


@pytest.mark.unit
@pytest.mark.anyio
async def test_optional_call_async_awaits_underlying_method() -> None:
    """Await an underlying async method using the explicit async API.

    Returns:
        None.
    """

    class AsyncWorker:
        """Represent a dependency with asynchronous work.

        The worker yields control before returning its result.
        """

        async def execute(self, value: int) -> int:
            """Return one value after yielding control to the loop.

            Args:
                value: The integer to increment.

            Returns:
                The value incremented by one.
            """
            await asyncio.sleep(0)
            return value + 1

    wrapped = Optional(AsyncWorker())

    assert await wrapped.call_async("execute", INPUT_VALUE) == ASYNC_RESULT
    assert await Optional(None).call_async("execute") is None


@pytest.mark.unit
@pytest.mark.anyio
async def test_optional_async_callback_is_awaited_and_null_is_skipped() -> None:
    """Await optional async callbacks while skipping null candidates.

    Returns:
        None.
    """
    calls: list[int] = []

    async def double(value: object) -> object:
        """Return twice the integer candidate after yielding control.

        Args:
            value: The candidate, asserted to be an integer.

        Returns:
            Twice the integer value.
        """
        assert isinstance(value, int)
        await asyncio.sleep(0)
        calls.append(value)
        return value * 2

    assert await optional_async(3, double) == OPTIONAL_ASYNC_RESULT
    assert await optional_async(None, double) is None
    assert calls == [3]


@pytest.mark.unit
def test_optional_sync_callback_rejects_awaitables() -> None:
    """Reject async callbacks in the synchronous optional helper.

    Returns:
        None.
    """

    async def callback(value: int) -> int:
        """Represent asynchronous callback work.

        Args:
            value: The integer to return.

        Returns:
            The unchanged integer.
        """
        return value

    with pytest.raises(TypeError, match="optional_async"):
        optional(3, callback)


@pytest.mark.unit
def test_optional_is_set_handles_mappings_sequences_and_objects() -> None:
    """Apply null-aware presence checks across supported value shapes.

    Returns:
        None.
    """

    class Record:
        """Expose nullable and populated attributes for access checks.

        The false-like zero value verifies that only ``None`` is unset.
        """

        present = 0
        nullable = None

    assert Optional({"value": 0, "nullable": None}).is_set("value")
    assert not Optional({"nullable": None}).is_set("nullable")
    assert Optional([0]).is_set(0)
    assert not Optional([None]).is_set(0)
    assert not Optional([0]).is_set(-1)
    assert Optional(Record()).is_set("present")
    assert not Optional(Record()).is_set("nullable")
    assert not Optional(3).is_set(0)


@pytest.mark.unit
def test_optional_calls_report_missing_and_non_callable_attributes() -> None:
    """Raise clear errors when explicit delegation cannot call a member.

    Returns:
        None.
    """

    class Record:
        """Expose an attribute that cannot be called as a method.

        The wrapper should distinguish this from a missing attribute.
        """

        value = 3

    wrapped = Optional(Record())

    with pytest.raises(AttributeError):
        wrapped.call("missing")
    with pytest.raises(TypeError, match="value"):
        wrapped.call("value")
    assert Optional(None).call("missing") is None


@pytest.mark.unit
def test_optional_mapping_mutation_and_unsupported_targets_are_safe() -> None:
    """Mutate nested mutable data and ignore immutable or invalid targets.

    Returns:
        None.
    """
    mapping: dict[str, object] = {"profile": {"name": "Ada"}}
    wrapped = Optional(mapping)
    wrapped["profile.role"] = "admin"
    assert mapping == {
        "profile": {"name": "Ada", "role": "admin"},
    }
    del wrapped["profile.name"]
    assert mapping == {"profile": {"role": "admin"}}

    sequence: list[object] = ["first", "second"]
    sequence_wrapper = Optional(sequence)
    del sequence_wrapper[0]
    sequence_wrapper[1] = "third"
    assert sequence == ["second", "third"]

    immutable = Optional(("value",))
    immutable[0] = "ignored"
    del immutable[0]
    assert immutable[0] == "value"
    assert [] not in immutable


@pytest.mark.unit
def test_optional_attributes_are_null_safe_and_hide_private_names() -> None:
    """Return null for missing public attributes and reject private access.

    Returns:
        None.
    """
    assert Optional(None).missing is None
    assert Optional(object()).missing is None
    private_name = "_private"
    with pytest.raises(AttributeError, match="_private"):
        getattr(Optional(None), private_name)


@pytest.mark.unit
@pytest.mark.anyio
async def test_optional_async_accepts_a_synchronous_callback_result() -> None:
    """Return synchronous callback values through the async helper.

    Returns:
        None.
    """

    def double(value: object) -> int:
        """Double an integer callback input.

        Args:
            value: The value supplied to the optional helper.

        Returns:
            Twice the input integer.

        Raises:
            TypeError: If the callback receives a non-integer value.
        """
        if not isinstance(value, int):
            raise TypeError(NOT_INTEGER_ERROR)
        return value * 2

    assert await optional_async(INPUT_VALUE, double) == DOUBLED_VALUE
    assert await Optional(3).call_async("__str__") == "3"
