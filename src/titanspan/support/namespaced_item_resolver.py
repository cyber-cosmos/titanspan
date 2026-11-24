"""Resolve dotted and namespaced keys into their component segments.

Keep key parsing and cache lifecycle independent from configuration and
translation loading.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

type _ItemSegment = str | None


class NamespacedItemResolver:
    """Parse and cache namespace, group, and item key segments.

    Use dotted keys for an unnamespaced group and item, or ``namespace::``
    before a dotted key for namespaced groups. Parsed values are cached per
    resolver instance.

    Attributes:
        _parsed: Immutable cached segment sequences keyed by original input.

    Notes:
        Public parsing returns fresh lists to preserve PHP array value
        semantics without exposing the resolver's cached values to mutation.
    """

    def __init__(self) -> None:
        """Initialize an empty per-instance parsed-key cache.

        Each resolver owns a cache so values cannot leak across unrelated
        application or execution contexts.
        """
        self._parsed: dict[str, tuple[_ItemSegment, ...]] = {}

    def parse_key(self, key: str) -> list[_ItemSegment]:
        """Parse a key into its namespace, group, and optional item.

        Args:
            key: A dotted item key with an optional ``namespace::`` prefix.

        Returns:
            A three-element list containing the namespace, group, and item.
            Unnamespaced keys use ``None`` for the namespace; group-only keys
            use ``None`` for the item.

        Notes:
            Results are cached by the original key. Each call returns a fresh
            list so caller mutation does not alter later results.
        """
        cached = self._parsed.get(key)
        if cached is not None:
            return list(cached)

        if "::" in key:
            parsed = self._parse_namespaced_segments(key)
        else:
            parsed = self._parse_basic_segments(key.split("."))
        self._parsed[key] = tuple(parsed)
        return list(parsed)

    def set_parsed_key(
        self,
        key: str,
        parsed: Sequence[_ItemSegment],
    ) -> None:
        """Seed or replace a cached key with pre-parsed segments.

        Args:
            key: The original key used for later cache lookup.
            parsed: The parsed values to retain for that key.

        Notes:
            The supplied sequence is copied into an immutable tuple so later
            mutation by the caller cannot change the cache.
        """
        self._parsed[key] = tuple(parsed)

    def flush_parsed_keys(self) -> None:
        """Remove every cached key parsed by this resolver instance.

        Notes:
            Subsequent calls parse keys again and populate the cache anew.
        """
        self._parsed.clear()

    def _parse_basic_segments(self, segments: list[str]) -> list[_ItemSegment]:
        """Parse dotted segments without a namespace prefix.

        Args:
            segments: The group and optional dotted item segments.

        Returns:
            A three-element list with a ``None`` namespace.
        """
        group = segments[0]
        item = ".".join(segments[1:]) if len(segments) > 1 else None
        return [None, group, item]

    def _parse_namespaced_segments(
        self,
        key: str,
    ) -> list[_ItemSegment]:
        """Parse a namespaced key into namespace, group, and item segments.

        Args:
            key: A key containing the ``::`` namespace separator.

        Returns:
            The namespace followed by the group's name and optional item.

        Notes:
            The upstream implementation keeps only the first two pieces
            produced by splitting on ``::``; additional pieces are ignored.
        """
        pieces = key.split("::")
        namespace, item = pieces[0], pieces[1]
        basic = self._parse_basic_segments(item.split("."))
        return [namespace, basic[1], basic[2]]

    # Keep the original Illuminate method names as explicit aliases.
    parseKey = parse_key
    setParsedKey = set_parsed_key
    flushParsedKeys = flush_parsed_keys


__all__ = ["NamespacedItemResolver"]
