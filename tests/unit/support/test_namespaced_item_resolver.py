"""Verify namespaced key parsing and parsed-value cache semantics.

Exercise upstream segment rules and Python-safe cache copy behavior.
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


def test_camel_case_aliases_share_the_python_implementations() -> None:
    """Preserve source-compatible method names for the public API.

    Both spellings use the same parsing and cache behavior.
    """
    resolver = NamespacedItemResolver()

    assert resolver.parseKey("package::group.item") == [
        "package",
        "group",
        "item",
    ]
    resolver.setParsedKey("cached.key", ["custom"])
    assert resolver.parse_key("cached.key") == ["custom"]

    resolver.flushParsedKeys()

    assert resolver.parseKey("cached.key") == [None, "cached", "key"]


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


def test_namespaced_separator_uses_the_first_two_segments() -> None:
    """Match upstream behavior when more than one namespace separator exists.

    The upstream destructuring keeps its first namespace and item segments.
    """
    assert NamespacedItemResolver().parse_key(
        "package::group::ignored.item"
    ) == ["package", "group", None]
