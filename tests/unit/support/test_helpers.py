"""Verify shared helper behavior and public utility contracts.

The tests focus on value handling, nested data, safe escaping, and mutation
semantics that are common across framework modules.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.support import (
    EncodedHtmlString,
    HigherOrderTapProxy,
    HtmlString,
    blank,
    data_fill,
    data_forget,
    data_get,
    data_has,
    data_set,
    e,
    enum_value,
    filled,
    head,
    last,
    tap,
    tap_async,
    throw_if,
    throw_unless,
    transform,
    value,
    with_,
)

EXPECTED_SEVEN = 7
EXPECTED_EIGHT = 8
EXPECTED_FOUR = 4

if TYPE_CHECKING:
    from collections.abc import Callable


class Role(Enum):
    """Provide a unit enum for enum conversion tests.

    The backed value verifies scalar conversion behavior.
    """

    ADMIN = "admin"


class DeferredText:
    """Resolve plain text when an HTML helper renders the value.

    The fixture follows both supported method spellings so static and runtime
    protocol checks exercise the same contract.
    """

    def resolve_displayable_value(self) -> str:
        """Return untrusted display text for context-aware escaping.

        Returns:
            Plain text that must be escaped as HTML.
        """
        return "<strong>deferred</strong>"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (None, True),
        ("", True),
        (" \t\n", True),
        ([], True),
        ({}, True),
        (0, False),
        (False, False),
        ("0", False),
        ([None], False),
    ],
)
def test_blank_uses_explicit_empty_value_rules(
    candidate: object,
    expected: bool,
) -> None:
    """Classify blank values without applying Python truthiness.

    Args:
        candidate: The value to classify.
        expected: The expected blank classification.

    Returns:
        None.
    """
    assert blank(candidate) is expected
    assert filled(candidate) is (not expected)


@pytest.mark.unit
def test_value_invokes_callable_defaults_with_arguments() -> None:
    """Resolve a callable value lazily with its supplied arguments.

    Returns:
        None.
    """

    def add(left: int, right: int) -> int:
        """Return the sum used to verify callable arguments.

        Args:
            left: The first addend.
            right: The second addend.

        Returns:
            The sum of both addends.
        """
        return left + right

    assert value("present", 3) == "present"
    assert value(add, 2, 5) == EXPECTED_SEVEN
    assert data_get({"items": {"first": "Ada"}}, "items.{first}") == "Ada"
    assert data_get({"items": {}}, "items.{first}", "fallback") == "fallback"


@pytest.mark.unit
def test_with_and_tap_preserve_the_original_value() -> None:
    """Pass values through callbacks while preserving tap identity.

    Returns:
        None.
    """
    value_to_keep = {"count": 0}
    observed: list[object] = []

    assert with_(EXPECTED_FOUR, lambda item: item * 2) == EXPECTED_EIGHT
    assert with_(EXPECTED_FOUR) == EXPECTED_FOUR
    assert tap(value_to_keep, observed.append) is value_to_keep
    assert observed == [value_to_keep]
    assert tap(value_to_keep) is not value_to_keep


@pytest.mark.unit
def test_transform_uses_callback_only_for_filled_values() -> None:
    """Transform filled values and resolve defaults for blank values.

    Returns:
        None.
    """
    assert transform("name", str.upper, "fallback") == "NAME"
    assert transform("  ", str.upper, lambda item: f"blank:{item!r}") == (
        "blank:'  '"
    )


@pytest.mark.unit
def test_data_access_supports_dot_paths_wildcards_and_lazy_defaults() -> None:
    """Read nested mapping and sequence values using dotted paths.

    Returns:
        None.
    """
    source: dict[str, object] = {
        "users": [
            {"name": "Ada", "role": "admin"},
            {"name": "Lin", "role": "editor"},
        ],
        "nullable": None,
    }
    default_calls = 0

    def fallback() -> str:
        """Count missing-path fallback calls.

        Returns:
            The fallback value.
        """
        nonlocal default_calls
        default_calls += 1
        return "missing"

    assert data_get(source, "users.0.name") == "Ada"
    assert data_get(source, "users.*.name") == ["Ada", "Lin"]
    assert data_get(source, "users.*.role") == ["admin", "editor"]
    assert data_get(source, "nullable", fallback) is None
    assert data_get(source, "unknown", fallback) == "missing"
    assert default_calls == 1
    assert data_has(source, "nullable")
    assert not data_has(source, "unknown")


@pytest.mark.unit
def test_data_access_supports_escaped_wildcards_and_object_attributes() -> None:
    """Resolve escaped special path segments and public object attributes.

    Returns:
        None.
    """

    class Record:
        """Expose attributes for object traversal tests.

        The nested mapping exercises mixed object and mapping traversal.
        """

        def __init__(self) -> None:
            """Initialize a public nested attribute for traversal.

            Returns:
                None.
            """
            self.profile = {"name": "Ada"}

    record = Record()
    data: dict[str, object] = {"*": "literal", "record": record}

    assert data_get(data, r"\*") == "literal"
    assert data_get(data, "record.profile.name") == "Ada"
    assert data_has(data, "record.profile.name")
    assert data_get(["first", "last"], "{first}") == "first"
    assert data_get(["first", "last"], "{last}") == "last"


@pytest.mark.unit
def test_data_set_fill_and_forget_mutate_nested_data() -> None:
    """Mutate nested mapping and sequence values, including wildcards.

    Returns:
        None.
    """
    data: dict[str, object] = {
        "users": [{"name": "Ada"}, {"name": "Lin", "role": "editor"}],
    }

    assert data_set(data, "users.*.active", True) is data
    assert data == {
        "users": [
            {"name": "Ada", "active": True},
            {"name": "Lin", "role": "editor", "active": True},
        ],
    }
    data_fill(data, "users.*.role", "reader")
    assert data_get(data, "users.*.role") == ["reader", "editor"]
    data_forget(data, "users.*.active")
    assert data_get(data, "users.*.active", "absent") == [
        "absent",
        "absent",
    ]


@pytest.mark.unit
def test_data_fill_does_not_replace_explicit_none() -> None:
    """Treat a present None value as filled data for mapping paths.

    Returns:
        None.
    """
    data: dict[str, object] = {"value": None}

    data_fill(data, "value", "replacement")

    assert data == {"value": None}

    values: list[object] = [None]
    data_fill(values, 0, "replacement")

    assert values == [None]


@pytest.mark.unit
def test_data_set_can_create_sequence_roots_and_object_attributes() -> None:
    """Create a list root for numeric paths and update object attributes.

    Returns:
        None.
    """

    class Record:
        """Provide writable attributes for path mutation.

        The profile starts empty so data_set must create its nested mapping.
        """

        def __init__(self) -> None:
            """Initialize the record without profile data.

            Returns:
                None.
            """
            self.profile: object = None

    root = data_set(None, "0.name", "Ada")
    assert root == [{"name": "Ada"}]

    record = Record()
    assert data_set(record, "profile.name", "Lin") is record
    assert record.profile == {"name": "Lin"}


@pytest.mark.unit
def test_head_and_last_handle_empty_and_nonempty_iterables() -> None:
    """Return endpoints from iterables and None for empty inputs.

    Returns:
        None.
    """
    assert head(["first", "last"]) == "first"
    assert last(("first", "last")) == "last"
    assert head([]) is None
    assert last(iter(())) is None


@pytest.mark.unit
def test_data_forget_removes_list_items_and_object_attributes() -> None:
    """Delete sequence elements and object attributes through data paths.

    Returns:
        None.
    """

    class Record:
        """Expose a deletable attribute for path mutation tests.

        The attribute is public and mutable for the tested lifecycle.
        """

        def __init__(self) -> None:
            """Initialize the attribute under test.

            Returns:
                None.
            """
            self.value = "remove"

    values: list[object] = ["remove", "keep"]
    data_forget(values, 0)
    assert values == ["keep"]

    record = Record()
    data_forget(record, "value")
    assert not hasattr(record, "value")


@pytest.mark.unit
@pytest.mark.anyio
async def test_tap_proxy_and_async_tap_preserve_values() -> None:
    """Forward a method through a proxy and await explicit async callbacks.

    Returns:
        None.
    """
    values: list[str] = []
    proxy = tap(values)
    assert proxy.call("append", "observed") is values
    assert values == ["observed"]

    async def append_async(target: list[str]) -> None:
        """Append a value through an asynchronous tap callback.

        Args:
            target: The list receiving the appended marker.

        Returns:
            None.
        """
        await asyncio.sleep(0)
        target.append("async")

    assert await tap_async(values, append_async) is values
    assert values == ["observed", "async"]


@pytest.mark.unit
def test_synchronous_tap_rejects_and_closes_async_callbacks() -> None:
    """Reject coroutine callbacks instead of leaving them unawaited.

    Returns:
        None.
    """

    async def callback(candidate: int) -> None:
        """Represent an async callback passed to a synchronous helper.

        Args:
            candidate: The value accepted by the callback.

        Returns:
            None.
        """
        del candidate

    with pytest.raises(TypeError, match="explicit async helper"):
        tap(1, callback)


@pytest.mark.unit
def test_enum_value_uses_values_names_and_lazy_defaults() -> None:
    """Convert enums to scalar values and preserve other values.

    Returns:
        None.
    """
    assert enum_value(Role.ADMIN) == "admin"
    assert enum_value(Enum("Status", {"READY": 1}).READY) == 1
    assert enum_value(None, lambda: "fallback") == "fallback"
    assert enum_value("ready") == "ready"


@pytest.mark.unit
def test_html_escaping_handles_quotes_unicode_and_existing_entities() -> None:
    """Escape text for HTML and optionally preserve existing entities.

    Returns:
        None.
    """
    assert e('<script title="x">雪</script>') == (
        "&lt;script title=&quot;x&quot;&gt;雪&lt;/script&gt;"
    )
    assert e("&amp;", double_encode=False) == "&amp;"
    assert e("'", double_encode=False) == "&#039;"
    assert e(None) == ""
    assert e(False) == ""
    assert e(True) == "1"


@pytest.mark.unit
def test_html_helper_resolves_deferred_and_trusted_values() -> None:
    """Escape deferred text and preserve explicitly trusted HTML.

    Returns:
        None.
    """
    assert e(DeferredText()) == "&lt;strong&gt;deferred&lt;/strong&gt;"
    assert e(HtmlString("<strong>trusted</strong>")) == (
        "<strong>trusted</strong>"
    )


@pytest.mark.unit
def test_html_helper_uses_the_active_encoded_html_encoder() -> None:
    """Apply the active encoder override to the HTML helper.

    Returns:
        None.
    """
    EncodedHtmlString.encode_using(
        lambda text, double_encode: f"{text}:{double_encode}"
    )
    try:
        assert e("value", double_encode=False) == "value:False"
    finally:
        EncodedHtmlString.flush_state()


@pytest.mark.unit
def test_throw_helpers_return_or_raise_the_original_condition() -> None:
    """Raise only for matching conditions and preserve false-path values.

    Returns:
        None.
    """
    assert throw_if(False) is False
    assert throw_unless("ready") == "ready"

    with pytest.raises(ValueError, match="named error"):
        throw_if(True, "ValueError", "named error")

    with pytest.raises(ValueError, match="invalid"):
        throw_if(True, ValueError, "invalid")

    with pytest.raises(RuntimeError, match="denied"):
        throw_unless(False, "denied")


@pytest.mark.unit
def test_blank_and_transform_cover_bytes_and_default_paths() -> None:
    """Classify byte containers and resolve omitted transform defaults.

    Returns:
        None.
    """
    assert blank(b"")
    assert blank(bytearray())
    assert not blank(b"data")
    assert transform("filled", str.upper) == "FILLED"
    assert transform(" ", str.upper) is None


@pytest.mark.unit
def test_data_get_handles_null_paths_wildcard_misses_and_flattening() -> None:
    """Handle null path segments and nested wildcard result flattening.

    Returns:
        None.
    """
    source: dict[str, object] = {
        "groups": [
            {"values": [1, 2]},
            {"values": [3]},
        ],
        "literal": {"{first}": "first", "{last}": "last"},
    }

    assert data_get(source, None) is source
    assert data_get(source, ["groups", None]) == source["groups"]
    assert data_get(source, "groups.*.values.*") == [1, 2, 3]
    assert data_get(source, "groups.*.missing", "absent") == [
        "absent",
        "absent",
    ]
    assert data_get(source, "literal.\\{first}") == "first"
    assert data_get(source, "literal.\\{last}") == "last"
    assert data_get({"value": 5}, "value.*", "absent") == "absent"


@pytest.mark.unit
def test_data_has_and_mutation_handle_empty_or_unwritable_paths() -> None:
    """Preserve roots and report false for unsupported path operations.

    Returns:
        None.
    """
    original = {"value": 1}
    assert not data_has(original, None)
    assert not data_has(original, [])
    assert not data_has(original, [None])
    assert data_set(original, [], 2) is original
    assert data_set(5, "value", 2) == {"value": 2}
    assert data_set(5, "value", 2) != original
    assert data_set(5, "*", 2) == []
    assert data_forget(original, None) is original
    scalar = EXPECTED_FOUR + 1
    assert data_forget(scalar, "value") == scalar


@pytest.mark.unit
def test_data_mutation_handles_missing_list_and_readonly_attributes() -> None:
    """Ignore invalid deletion paths and replace immutable object roots.

    Returns:
        None.
    """

    class ReadOnlyRecord:
        """Expose a fixed property for rejected assignment behavior.

        The object has no instance dictionary, so failed assignment cannot
        silently create an unrelated replacement attribute.
        """

        __slots__ = ()

        @property
        def name(self) -> str:
            """Return the fixed name used by the mutation test.

            Returns:
                The fixed name.
            """
            return "Ada"

    values: list[object] = [None]
    data_forget(values, -1)
    data_forget(values, "missing")
    data_forget(values, "*.value")
    assert values == [None]

    readonly = ReadOnlyRecord()
    replacement = data_set(readonly, "name", "Lin")
    assert replacement == {"name": "Lin"}
    assert readonly.name == "Ada"


@pytest.mark.unit
def test_enum_and_html_helpers_handle_non_scalar_enum_values() -> None:
    """Use enum names for complex values and escape enum-backed booleans.

    Returns:
        None.
    """

    class ComplexRole(Enum):
        """Define enum values used by conversion tests.

        Include tuple and boolean payloads to cover non-scalar fallback
        behavior and HTML-safe boolean conversion.
        """

        PAYLOAD = ("admin",)
        ENABLED = True
        DISABLED = False

    assert enum_value(ComplexRole.PAYLOAD) == "PAYLOAD"
    assert e(ComplexRole.ENABLED) == "1"
    assert e(ComplexRole.DISABLED) == ""
    assert e("&lt;", double_encode=False) == "&lt;"


@pytest.mark.unit
def test_throw_helpers_accept_factories_and_instances() -> None:
    """Construct requested exceptions and reject invalid factory results.

    Returns:
        None.
    """
    original = LookupError("stored")

    with pytest.raises(LookupError) as raised:
        throw_if(True, original)
    assert raised.value is original

    def factory(message: object) -> ValueError:
        """Build the requested exception from an opaque message.

        Args:
            message: The value passed through the helper boundary.

        Returns:
            A value error containing the supplied message.
        """
        return ValueError(message)

    with pytest.raises(ValueError, match="factory message"):
        throw_unless(
            False,
            factory,
            "factory message",
        )

    with pytest.raises(RuntimeError, match="UnknownError"):
        throw_if(True, "UnknownError")

    invalid_factory = cast(
        "Callable[..., Exception]",
        lambda: "not an exception",
    )
    with pytest.raises(TypeError, match="must produce an Exception"):
        throw_if(True, invalid_factory)


@pytest.mark.unit
def test_tap_proxy_forwards_methods_and_rejects_invalid_targets() -> None:
    """Forward public methods and reject missing or private proxy methods.

    Returns:
        None.
    """
    values: list[str] = []
    proxy = HigherOrderTapProxy(values)

    assert proxy.append("first") is values
    assert values == ["first"]
    with pytest.raises(TypeError, match="missing"):
        proxy.call("missing")
    private_name = "_private"
    with pytest.raises(AttributeError, match="_private"):
        getattr(proxy, private_name)


@pytest.mark.unit
@pytest.mark.anyio
async def test_tap_async_accepts_a_synchronous_callback() -> None:
    """Allow ordinary synchronous callbacks through the async helper.

    Returns:
        None.
    """
    values: list[int] = []
    candidate = [1]

    result = await tap_async(candidate, lambda value: values.extend(value))

    assert result is candidate
    assert values == [1]
