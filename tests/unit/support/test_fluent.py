"""Verify the Laravel-inspired Fluent object behavior.

The cases cover mapping access, fluent APIs, serialization, and aliases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from titanspan.support import Fluent

EXPECTED_JSON = '{"name":"Ada","active":true}'
EXPECTED_AGE = 37
EXPECTED_COUNT = 2

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.unit
def test_fluent_constructs_from_mappings_and_iterables() -> None:
    """Copy mapping entries and positional iterable values into attributes.

    Returns:
        None.
    """
    source = {"name": "Ada", "age": EXPECTED_AGE}
    fluent: Fluent[str, object] = Fluent(source)
    pairs: Iterator[tuple[str, object]] = iter(
        [("name", "Lin"), ("active", True)],
    )
    from_pairs: Fluent[str, object] = Fluent(pairs)

    source["age"] = 38

    assert fluent.to_array() == {"name": "Ada", "age": EXPECTED_AGE}
    assert from_pairs.toArray() == {"name": "Lin", "active": True}
    assert Fluent[str, object].make({"active": True}).active is True


@pytest.mark.unit
def test_fluent_supports_dot_get_set_and_lazy_defaults() -> None:
    """Read and write nested data while preserving fluent identity.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent(
        {"user": {"name": "Ada", "nickname": None}},
    )

    assert fluent.get("user.name") == "Ada"
    assert fluent.get("user.missing", lambda: "fallback") == "fallback"
    assert fluent.get("user.nickname", "fallback") is None
    assert fluent.set("user.role", "admin") is fluent
    assert fluent.user == {"name": "Ada", "nickname": None, "role": "admin"}


@pytest.mark.unit
def test_fluent_value_and_all_preserve_direct_and_nested_access() -> None:
    """Read direct keys and select nested attribute paths into a new mapping.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent(
        {"user": {"name": "Ada", "active": True}, "theme": "dark"},
    )

    assert fluent.value("theme") == "dark"
    assert fluent.value("unknown", lambda: "fallback") == "fallback"
    assert fluent.all() == fluent.to_array()
    assert fluent.all(["user.name", "theme"]) == {
        "user": {"name": "Ada"},
        "theme": "dark",
    }
    assert fluent.all(iter(())) == fluent.to_array()
    assert fluent.scope("user").to_array() == {
        "name": "Ada",
        "active": True,
    }


@pytest.mark.unit
def test_fluent_dynamic_attributes_and_calls_are_explicitly_adapted() -> None:
    """Read and assign dynamic attributes and use an explicit setter call.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent()

    fluent.name = "Ada"
    fluent.dynamic_call("developer")
    fluent.dynamic_call("age", 37)

    assert fluent.name == "Ada"
    assert fluent.developer is True
    assert fluent.age == EXPECTED_AGE
    assert fluent.missing is None
    assert fluent.dynamic_call("active") is fluent
    assert fluent.active is True
    assert fluent.dynamic_call("role", "admin") is fluent
    assert fluent.role == "admin"

    fluent.set("value", "stored-key")
    assert fluent.get("value") == "stored-key"
    assert callable(fluent.value)
    assert fluent.is_set("name")
    assert not fluent.is_set("missing")
    del fluent.name
    assert fluent.name is None


@pytest.mark.unit
def test_fluent_mapping_protocol_mutates_items_and_tracks_null_keys() -> None:
    """Support key lookup, assignment, deletion, membership, and iteration.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent({"name": "Ada", "nullable": None})

    assert "nullable" not in fluent
    assert fluent.has("nullable")
    assert fluent["nullable"] is None
    fluent["role"] = "admin"
    assert fluent["role"] == "admin"
    del fluent["name"]
    assert "name" not in fluent
    assert list(fluent) == ["nullable", "role"]
    assert len(fluent) == EXPECTED_COUNT


@pytest.mark.unit
def test_fluent_serializes_with_python_and_laravel_method_names() -> None:
    """Serialize the same attribute data through explicit naming aliases.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent({"name": "Ada", "active": True})

    expected = json.loads(EXPECTED_JSON)

    assert fluent.to_json() == EXPECTED_JSON
    assert fluent.toJson() == EXPECTED_JSON
    assert fluent.json_serialize() == expected
    assert fluent.jsonSerialize() == expected
    assert json.loads(fluent.toPrettyJson()) == expected
    assert "\n" in fluent.to_pretty_json()
    assert fluent.toArray() == fluent.getAttributes()


@pytest.mark.unit
def test_fluent_empty_checks_and_iterator_aliases() -> None:
    """Expose emptiness checks and the Laravel-compatible iterator alias.

    Returns:
        None.
    """
    empty: Fluent[str, object] = Fluent()
    populated: Fluent[str, object] = Fluent({"name": "Ada"})

    assert empty.is_empty()
    assert empty.isEmpty()
    assert not empty.is_not_empty()
    assert populated.is_not_empty()
    assert populated.isNotEmpty()
    assert list(populated.getIterator()) == list(populated.attributes.items())


@pytest.mark.unit
def test_fluent_dynamic_call_invokes_registered_macros() -> None:
    """Route explicit dynamic calls through the shared macro registry.

    Returns:
        None.
    """

    def macro_value(fluent: Fluent[str, object], key: str) -> object:
        """Read an attribute through the Fluent public API.

        Args:
            fluent: The instance receiving the macro call.
            key: The attribute path to retrieve.

        Returns:
            The selected value.
        """
        return fluent.get(key)

    Fluent.macro("read_value_for_test", macro_value)
    try:
        fluent: Fluent[str, object] = Fluent({"name": "Ada"})
        assert fluent.dynamic_call("read_value_for_test", "name") == "Ada"
    finally:
        Fluent.flush_macros()


@pytest.mark.unit
def test_fluent_handles_integer_keys_and_non_string_dynamic_keys() -> None:
    """Support integer mapping keys and dynamic attribute storage.

    Returns:
        None.
    """
    fluent: Fluent[int, object] = Fluent({1: "one"})

    assert fluent.get(1) == "one"
    assert fluent.set(2, "two") is fluent
    assert fluent.get(2) == "two"
    assert fluent.all([]) == {1: "one", 2: "two"}
    assert fluent.all(1, 2) == {1: "one", 2: "two"}


@pytest.mark.unit
def test_fluent_coerces_values_objects_and_pair_iterables() -> None:
    """Convert scalar, positional, and model-like inputs to attributes.

    Returns:
        None.
    """

    class Model:
        """Expose fields through the supported public conversion API.

        This exercises conversion through a model-style method without
        making the Support module depend on Pydantic.
        """

        def model_dump(self) -> dict[str, object]:
            """Return the model fields used to construct Fluent.

            Returns:
                The model field mapping.
            """
            return {"name": "Ada"}

    assert Fluent("value").to_array() == {0: "value"}
    assert Fluent([1, 2]).to_array() == {0: 1, 1: 2}
    assert Fluent([("name", "Lin")]).to_array() == {"name": "Lin"}
    assert Fluent([["name", "Lin"]]).to_array() == {
        0: ["name", "Lin"],
    }
    assert Fluent(Model()).to_array() == {"name": "Ada"}


@pytest.mark.unit
def test_fluent_dynamic_attribute_collisions_and_errors_are_explicit() -> None:
    """Keep stored method names addressable and guard invalid attributes.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent({"get": "stored"})

    assert callable(fluent.get)
    assert fluent.value("get") == "stored"
    assert fluent.get("get") == "stored"
    private_name = "_private"
    with pytest.raises(AttributeError, match="_private"):
        getattr(fluent, private_name)
    with pytest.raises(AttributeError, match="missing"):
        del fluent.missing


@pytest.mark.unit
def test_fluent_mapping_membership_handles_unhashable_keys() -> None:
    """Return false for unhashable lookup keys without mutating data.

    Returns:
        None.
    """
    fluent: Fluent[str, object] = Fluent({"name": "Ada"})

    assert [] not in fluent
    assert fluent.to_array() == {"name": "Ada"}
