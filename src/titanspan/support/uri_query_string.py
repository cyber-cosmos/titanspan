"""Represent decoded query data for a Titanspan URI.

The type preserves the encoded query for string conversion and exposes
structured access through Titanspan's shared data helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from titanspan.support.arr import Arr
from titanspan.support.helpers import data_get

if TYPE_CHECKING:
    from collections.abc import Iterable

    from titanspan.support.uri import Uri


class UriQueryString:
    """Read query parameters from their owning immutable URI.

    Attributes:
        _uri: The URI whose raw query this view reads.

    Notes:
        Query values are strings, nested mappings, or lists. Scalar coercion
        is left to explicit typed accessors.
    """

    def __init__(self, uri: Uri) -> None:
        """Bind a query view to an immutable URI value.

        Args:
            uri: The URI providing the encoded query string.
        """
        self._uri = uri

    def all(
        self,
        keys: str | Iterable[str] | None = None,
    ) -> dict[str | int, object]:
        """Return all query values or a nested selection of requested keys.

        Args:
            keys: Optional dotted or bracket-compatible data paths to select.

        Returns:
            A new mapping containing the selected values.
        """
        values = self._query_mapping()
        if keys is None or keys == "":
            return values
        selected = [keys] if isinstance(keys, str) else list(keys)
        if not selected:
            return values

        result: dict[str | int, object] = {}
        for key in selected:
            Arr.set(result, key, Arr.get(values, key))
        return result

    def get(self, key: str | None = None, default: object = None) -> object:
        """Get one query value through nested dot-path access.

        Args:
            key: The optional nested key to retrieve.
            default: A value or lazy default used when the key is missing.

        Returns:
            The selected value, complete query mapping, or resolved default.
        """
        return data_get(self._query_mapping(), key, default)

    def decode(self) -> str:
        """Percent-decode the raw query without treating plus as a space.

        Returns:
            The decoded query string without a leading question mark.
        """
        return unquote(str(self), encoding="utf-8", errors="replace")

    def value(self) -> str:
        """Return the encoded query string.

        Returns:
            The raw query string without a leading question mark.
        """
        return str(self)

    def _query_mapping(self) -> dict[str | int, object]:
        """Parse the query string into nested Python data.

        Returns:
            Query keys mapped to string values, dictionaries, or lists.
        """
        # Keep URI parsing internals private while sharing this adapter's
        # nested-query interpretation with its owning value.
        return self._uri._query_data()  # pyright: ignore[reportPrivateUsage]

    def __str__(self) -> str:
        """Return the URI's encoded query component.

        Returns:
            The query string, or an empty string when absent.
        """
        return urlsplit(self._uri.value()).query


__all__ = ["UriQueryString"]
