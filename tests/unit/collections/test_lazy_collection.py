"""Verify lazy iteration, bounded consumption, and source ownership.

Lazy tests use real generators and finite prefixes of unbounded iterators.
"""

from __future__ import annotations

from itertools import count
from statistics import StatisticsError
from typing import TYPE_CHECKING, assert_type

import pytest
from hypothesis import given
from hypothesis import strategies as st

from titanspan.collections import Collection, LazyCollection, lazy

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from collections.abc import Iterator


_EXPECTED_MAXIMUM = 3
_EXPECTED_ITEM_COUNT = 3
_EXPECTED_SUM = 6
_EXPECTED_AVERAGE = 2.0
_EXPECTED_MEDIAN = 2
_EXPECTED_PREFIX_SUM = 10
_TAKE_WHILE_BOUNDARY = 7
_SKIP_WHILE_BOUNDARY = 4


def test_pipeline_construction_does_not_consume_source_or_callbacks() -> None:
    """Defer source access and callback calls until a traversal begins.

    Returns:
        None.
    """
    visited: list[int] = []

    def source() -> Iterator[int]:
        """Yield values while recording actual source consumption.

        Returns:
            An iterator of integer values.
        """
        for value in range(3):
            visited.append(value)
            yield value

    values = (
        lazy(source())
        .map(lambda value: value * 2)
        .filter(lambda value: value > 0)
    )

    assert visited == []
    assert values.collect().all() == [2, 4]
    assert visited == [0, 1, 2]


def test_replayable_sources_rebuild_pipelines_without_caching_items() -> None:
    """Re-run a replayable iterable and callbacks on each traversal.

    Returns:
        None.
    """
    calls: list[int] = []
    values = lazy([1, 2, 3]).map(lambda value: calls.append(value) or value * 2)

    assert values.is_replayable is True
    assert values.collect().all() == [2, 4, 6]
    assert values.collect().all() == [2, 4, 6]
    assert calls == [1, 2, 3, 1, 2, 3]


def test_one_shot_sources_resume_after_partial_consumption() -> None:
    """Do not cache or silently restart a consumed iterator.

    Returns:
        None.
    """
    values = lazy(iter([1, 2, 3]))

    assert values.is_replayable is False
    assert values.take(1).collect().all() == [1]
    assert values.collect().all() == [2, 3]
    assert values.collect().all() == []


def test_wrapping_a_lazy_source_preserves_one_shot_ownership() -> None:
    """Keep replayability when one LazyCollection wraps another.

    Returns:
        None.
    """
    source = lazy(iter([1, 2]))
    wrapped = lazy(source)

    assert wrapped.is_replayable is False
    assert wrapped.collect().all() == [1, 2]


def test_take_consumes_no_more_than_its_requested_boundary() -> None:
    """Stop source iteration exactly at the requested finite prefix.

    Returns:
        None.
    """
    consumed: list[int] = []

    def source() -> Iterator[int]:
        """Record each value consumed from an infinite source.

        Returns:
            An unbounded iterator of integers.
        """
        value = 0
        while True:
            consumed.append(value)
            yield value
            value += 1

    values = lazy(source()).take(3)

    assert consumed == []
    assert values.collect().all() == [0, 1, 2]
    assert consumed == [0, 1, 2]
    assert lazy(count()).take(0).collect().all() == []
    with pytest.raises(ValueError, match="take count"):
        lazy(count()).take(-1)


def test_skip_take_while_and_skip_while_compose_lazily() -> None:
    """Use iterator operations for streaming boundaries and predicates.

    Returns:
        None.
    """
    values = (
        lazy(range(10))
        .skip(2)
        .take_while(lambda value: value < _TAKE_WHILE_BOUNDARY)
        .skip_while(lambda value: value < _SKIP_WHILE_BOUNDARY)
        .take(2)
    )

    assert values.collect().all() == [4, 5]
    assert lazy([1, 2, 3]).reject(
        lambda value: value % 2 == 0
    ).collect().all() == [
        1,
        3,
    ]
    with pytest.raises(ValueError, match="skip count"):
        lazy(range(3)).skip(-1)


def test_flat_map_chunk_enumerate_and_zip_preserve_item_types() -> None:
    """Compose nested iterables and bounded eager chunks.

    Returns:
        None.
    """
    batches = (
        lazy([1, 2, 3]).flat_map(lambda value: [value, value * 10]).chunk(3)
    )

    assert_type(batches, LazyCollection[Collection[int]])
    assert [batch.all() for batch in batches] == [[1, 10, 2], [20, 3, 30]]
    assert lazy(["a", "b"]).enumerate(1).collect().all() == [
        (1, "a"),
        (2, "b"),
    ]
    pairs = lazy([1, 2]).zip(["a", "b"])
    assert_type(pairs, LazyCollection[tuple[int, str]])
    assert lazy(count()).take(4).zip(["a", "b"]).collect().all() == [
        (0, "a"),
        (1, "b"),
    ]
    with pytest.raises(ValueError, match="chunk size"):
        lazy([1]).chunk(0)


def test_concat_keeps_duplicates_and_one_shot_replayability() -> None:
    """Append sources in order without caching one-shot inputs.

    Returns:
        None.
    """
    values = lazy([1, 1]).concat([2], iter([3]))

    assert values.is_replayable is False
    assert values.collect().all() == [1, 1, 2, 3]
    assert values.collect().all() == [1, 1, 2]


def test_zip_and_concat_preserve_nested_one_shot_sources() -> None:
    """Carry source replayability through nested lazy pipelines.

    Returns:
        None.
    """
    zip_source = lazy(iter([3, 4])).map(lambda value: value)
    zipped = lazy([1, 2]).zip(zip_source)
    concat_source = lazy(iter([2, 3])).map(lambda value: value)
    concatenated = lazy([1]).concat(concat_source)

    assert zipped.is_replayable is False
    assert list(zipped) == [(1, 3), (2, 4)]
    assert list(zipped) == []
    assert concatenated.is_replayable is False
    assert list(concatenated) == [1, 2, 3]
    assert list(concatenated) == [1]


def test_lazy_terminal_operations_consume_sources_explicitly() -> None:
    """Materialize and aggregate with documented traversal costs.

    Returns:
        None.
    """
    assert isinstance(lazy([1, 2]).collect(), Collection)
    assert lazy([1, 2, 3]).first() == 1
    assert lazy([1, 2, 3]).last() == _EXPECTED_MAXIMUM
    assert lazy([1, 2, 3]).count() == _EXPECTED_ITEM_COUNT
    assert (
        lazy([1, 2, 3]).reduce(
            lambda total, value: total + value,
            0,
        )
        == _EXPECTED_SUM
    )
    assert lazy([1, 2, 3]).sum() == _EXPECTED_SUM
    assert lazy([1, 2, 3]).average() == _EXPECTED_AVERAGE
    assert lazy([1, 2, 3]).min() == 1
    assert lazy([1, 2, 3]).max() == _EXPECTED_MAXIMUM
    ranked = [("second", 2), ("first", 1)]
    assert lazy(ranked).min(key=lambda value: value[1]) == ("first", 1)
    assert lazy(ranked).max(key=lambda value: value[1]) == ("second", 2)
    assert lazy(count()).take(5).sum() == _EXPECTED_PREFIX_SUM
    assert lazy([3, 1, 2]).median() == _EXPECTED_MEDIAN


def test_terminal_defaults_and_empty_aggregations_are_explicit() -> None:
    """Distinguish empty terminals from explicit false-like defaults.

    Returns:
        None.
    """
    empty: LazyCollection[int] = lazy([])

    assert empty.first(False) is False
    assert empty.last(None) is None
    assert empty.sum() == 0
    with pytest.raises(IndexError):
        empty.first()
    with pytest.raises(IndexError):
        empty.last()
    with pytest.raises(ValueError, match="iterable argument is empty"):
        empty.min()
    with pytest.raises(ValueError, match="iterable argument is empty"):
        empty.max()
    with pytest.raises(StatisticsError):
        empty.average()


def test_terminal_first_and_count_do_not_restore_one_shot_values() -> None:
    """Consume only the requested first item and exhaust full traversals.

    Returns:
        None.
    """
    values = lazy(iter([1, 2, 3]))

    assert values.first() == 1
    assert values.collect().all() == [2, 3]
    assert values.count() == 0


@given(st.lists(st.integers()))
def test_lazy_collection_matches_native_iterator_composition(
    values: list[int],
) -> None:
    """Match built-in filter and map results for finite replayable inputs.

    Args:
        values: An arbitrary finite integer sequence.

    Returns:
        None.
    """
    expected = [value * 2 for value in values if value % 2 == 0]
    actual = (
        lazy(values)
        .filter(lambda value: value % 2 == 0)
        .map(lambda value: value * 2)
    )

    assert actual.collect().all() == expected
