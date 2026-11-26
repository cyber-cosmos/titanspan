"""Verify namespaced key parsing and parsed-value cache semantics.

Exercise key segmentation and Python-safe cache copy behavior.
"""

from __future__ import annotations

import pytest

from titanspan.support import NamespacedItemResolver

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("module::messages.welcome", ["module", "messages", "welcome"]),
        ("module::messages", ["module", "messages", None]),
        ("messages.welcome", [None, "messages", "welcome"]),
        ("messages", [None, "messages", None]),
        ("messages.errors.required", [None, "messages", "errors.required"]),
        ("", [None, "", None]),
        (".welcome", [None, "", "welcome"]),
    ],
)
def test_parse_key_splits_namespace_group_and_item(
    key: str,
    expected: list[str | None],
) -> None:
    """Parse basic and namespaced keys into three ordered segments.

    Args:
        key: The dotted key, optionally prefixed by a namespace.
        expected: The namespace, group, and optional item segments.
    """
    assert NamespacedItemResolver().parse_key(key) == expected


def test_cached_key_can_be_set_and_flushed() -> None:
    """Allow an explicit parsed value to be replaced and invalidated.

    Flushing the cache restores parsing from the updated source key.
    """
    resolver = NamespacedItemResolver()

    assert resolver.parse_key("package::group.item") == [
        "package",
        "group",
        "item",
    ]
    resolver.set_parsed_key("cached.key", ["custom"])
    assert resolver.parse_key("cached.key") == ["custom"]

    resolver.flush_parsed_keys()

    assert resolver.parse_key("cached.key") == [None, "cached", "key"]


def test_explicitly_cached_keys_skip_parsing_and_are_copied() -> None:
    """Return independent parsed lists from explicitly cached values.

    Mutating either the input or a returned result does not corrupt the cache.
    """
    resolver = NamespacedItemResolver()
    parsed = ["custom", "group", "item"]
    resolver.set_parsed_key("arbitrary.key", parsed)
    parsed[0] = "changed-input"

    first = resolver.parse_key("arbitrary.key")
    first[1] = "changed-result"

    assert resolver.parse_key("arbitrary.key") == [
        "custom",
        "group",
        "item",
    ]


def test_only_the_first_namespace_separator_splits_the_key() -> None:
    """Keep later separators inside the namespaced group segment.

    Only the first separator divides the namespace from the item name.
    """
    assert NamespacedItemResolver().parse_key(
        "package::group::ignored.item"
    ) == ["package", "group::ignored", "item"]
