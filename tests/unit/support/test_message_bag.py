"""Verify typed message storage and formatting behavior.

The cases cover message uniqueness, wildcard access, formatting, and
serialization against Titanspan's Python mapping conventions.
"""

from __future__ import annotations

import json

import pytest

from titanspan.contracts import MessageBagProtocol, MessageProvider
from titanspan.support import MessageBag

MESSAGE_COUNT = 2
DEFAULT_FORMAT = ":message"


@pytest.mark.unit
def test_message_bag_normalizes_messages_and_exposes_keys() -> None:
    """Normalize constructor inputs while preserving message order.

    Returns:
        None.
    """
    bag = MessageBag(
        {
            "email": ["invalid", "invalid", "required"],
            "name": "missing",
        },
    )

    assert bag.keys() == ["email", "name"]
    assert bag.get_messages() == {
        "email": ["invalid", "required"],
        "name": ["missing"],
    }
    assert bag.get_message_bag() is bag
    assert bag.get_message_bag() is bag


@pytest.mark.unit
def test_message_bag_add_merge_and_forget_are_chainable() -> None:
    """Add unique messages, merge providers, and remove named entries.

    Returns:
        None.
    """
    bag = MessageBag({"email": ["invalid"]})
    other = MessageBag({"email": ["invalid", "required"], "name": "bad"})

    assert bag.add("email", "invalid") is bag
    assert bag.add_if(False, "email", "ignored") is bag
    assert bag.add_if(True, "email", "required") is bag
    assert bag.merge(other) is bag
    assert bag.forget("name") is bag
    assert bag.get("email") == [
        "invalid",
        "required",
        "invalid",
        "required",
    ]
    assert bag.get("name") == []
    bag.merge({"external": ["one", "two"]})
    assert bag.get("external") == ["one", "two"]


@pytest.mark.unit
def test_message_bag_reads_wildcards_and_applies_format_placeholders() -> None:
    """Select wildcard keys and substitute message and field placeholders.

    Returns:
        None.
    """
    bag = MessageBag(
        {
            "users.0.email": ["invalid", "required"],
            "users.1.email": ["missing"],
            "name": ["required"],
        },
    )

    assert bag.get("users.*.email") == {
        "users.0.email": ["invalid", "required"],
        "users.1.email": ["missing"],
    }
    assert bag.get("name", "[ :key ] :message") == [
        "[ name ] required",
    ]
    assert bag.first("users.0.email") == "invalid"
    assert bag.first("users.*.email") == "invalid"
    assert bag.first("unknown") == ""
    assert bag.all("(:key) :message") == [
        "(users.0.email) invalid",
        "(users.0.email) required",
        "(users.1.email) missing",
        "(name) required",
    ]
    assert bag.unique("(:key) :message") == bag.all("(:key) :message")


@pytest.mark.unit
def test_message_bag_presence_methods_match_all_and_any_semantics() -> None:
    """Check all-key and any-key queries including empty messages.

    Returns:
        None.
    """
    bag = MessageBag({"email": ["invalid"], "empty": [""]})
    empty = MessageBag()

    assert bag.has("email")
    assert bag.has(["email", "empty"]) is False
    assert not bag.has("email", "empty")
    assert bag.has_any(["missing", "email"])
    assert bag.has_any("missing", "email")
    assert bag.has_any(["missing", "email"])
    assert bag.missing(["missing", "unknown"])
    assert not bag.missing("email")
    assert not bag.missing("missing", "email")
    assert bag.has(None)
    assert bag.has_any(None)
    assert not empty.has(None)
    assert empty.is_empty()
    assert empty.is_empty()
    assert not empty.is_not_empty()
    assert bag.is_not_empty()
    assert bag.is_not_empty()
    assert bag.any()
    assert bag.count() == MESSAGE_COUNT
    assert MessageBag({"one": "same", "two": "same"}).unique() == [
        "same",
    ]


@pytest.mark.unit
def test_message_bag_format_configuration_and_json_serialization() -> None:
    """Serialize raw messages and maintain a configurable default format.

    Returns:
        None.
    """
    bag = MessageBag({"name": "required"})

    assert bag.get_format() == DEFAULT_FORMAT
    assert bag.get_format() == DEFAULT_FORMAT
    assert bag.set_format("Error: :message") is bag
    assert bag.set_format("Error: :message") is bag
    assert bag.first("name") == "Error: required"
    assert bag.get_messages() == {"name": ["required"]}
    assert json.loads(bag.to_json()) == bag.get_messages()
    assert json.loads(bag.to_pretty_json()) == bag.get_messages()
    assert str(bag) == bag.to_json()
    assert len(bag) == bag.count()


@pytest.mark.unit
def test_message_bag_rejects_invalid_message_values() -> None:
    """Reject non-string fields and malformed provider objects clearly.

    Returns:
        None.
    """
    with pytest.raises(TypeError):
        MessageBag({"email": 3})


@pytest.mark.unit
def test_message_bag_empty_wildcards_and_invalid_mapping_data() -> None:
    """Cover empty query results and reject invalid keys and message items.

    Returns:
        None.
    """
    empty = MessageBag()
    assert not empty.has_any("email")
    assert MessageBag({"field": ["bad"]}).first("other.*") == ""
    assert MessageBag({"field": []}).first("field.*") == ""

    with pytest.raises(TypeError, match="strings or integers"):
        MessageBag({True: "bad"})

    with pytest.raises(TypeError, match="Messages must be strings"):
        MessageBag({"field": [1]})

    with pytest.raises(TypeError, match="mapping or iterable"):
        MessageBag(3)


@pytest.mark.unit
def test_message_bag_adapts_numeric_array_keys_and_null_queries() -> None:
    """Preserve integer keys supplied by Python mappings.

    Returns:
        None.
    """
    bag = MessageBag([["foo", "bar"], ["baz"]])

    assert bag.keys() == [0, 1]
    assert bag.get(0) == ["foo", "bar"]
    assert bag.get_messages() == {0: ["foo", "bar"], 1: ["baz"]}
    assert bag.has_any(None)
    assert bag.has(None)


@pytest.mark.unit
def test_message_bag_merges_framework_message_providers() -> None:
    """Merge through the canonical contracts without concrete bag coupling.

    Returns:
        None.
    """

    class Provider:
        """Expose a message bag through the structural provider contract.

        The wrapper has no dependency on the concrete merge implementation.
        """

        def __init__(self, bag: MessageBag) -> None:
            """Store the source bag for provider resolution.

            Args:
                bag: The source message data.
            """
            self.bag = bag

        def get_message_bag(self) -> MessageBag:
            """Return the provider's source message bag.

            Returns:
                The stored message bag.
            """
            return self.bag

    source = MessageBag({"email": ["invalid"]})
    provider = Provider(source)
    target = MessageBag({"email": ["required"]})

    assert isinstance(source, MessageBagProtocol)
    assert isinstance(provider, MessageProvider)
    assert target.merge(provider) is target
    assert target.get("email") == ["required", "invalid"]
