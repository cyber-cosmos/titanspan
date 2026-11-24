"""Verify internal nested-query container invariants.

The public URI tests cover parsing and mutation. These focused tests exercise
the lower-level indexed-list cases that the query parser normally normalizes
into dictionaries before converting contiguous keys back into Python lists.
"""

from __future__ import annotations

from typing import cast

import pytest

from titanspan.support.uri import (
    _ensure_child,  # pyright: ignore[reportPrivateUsage]
    _store_query_value,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.unit
def test_ensure_child_reuses_replaces_and_appends_indexed_values() -> None:
    """Keep child-container updates attached to their owning list.

    Returns:
        None.
    """
    existing: list[object] = [{"name": "Ada"}]
    assert _ensure_child(existing, 0, "") is existing[0]

    replaced: list[object] = ["scalar"]
    replacement = _ensure_child(replaced, 0, "")
    assert replacement == []
    assert replaced == [[]]

    appended: list[object] = []
    child = _ensure_child(appended, 0, "name")
    assert child == {}
    assert appended == [{}]

    nested: list[object] = []
    nested_child = _ensure_child(nested, "", "")
    assert nested_child == []
    assert nested == [[]]


@pytest.mark.unit
def test_ensure_child_rejects_sparse_list_indexes() -> None:
    """Fail rather than return an unattached child for a sparse index.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="indexes must be contiguous"):
        _ensure_child([], 2, "name")

    invalid_container = cast(
        "dict[str | int, object] | list[object]",
        object(),
    )
    with pytest.raises(ValueError, match="indexes must be contiguous"):
        _ensure_child(invalid_container, 0, "name")


@pytest.mark.unit
def test_store_query_value_appends_and_replaces_list_indexes() -> None:
    """Preserve append and explicit index replacement behavior.

    Returns:
        None.
    """
    values: list[object] = []

    _store_query_value(values, "", "first")
    _store_query_value(values, 0, "replacement")
    _store_query_value(values, 1, "second")

    assert values == ["replacement", "second"]


@pytest.mark.unit
def test_store_query_value_rejects_sparse_list_indexes() -> None:
    """Reject list writes that would silently discard a query value.

    Returns:
        None.
    """
    values: list[object] = []

    with pytest.raises(ValueError, match="indexes must be contiguous"):
        _store_query_value(values, 2, "missing-prefix")

    invalid_container = cast(
        "dict[str | int, object] | list[object]",
        object(),
    )
    with pytest.raises(ValueError, match="indexes must be contiguous"):
        _store_query_value(invalid_container, "key", "value")
