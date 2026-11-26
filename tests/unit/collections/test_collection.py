"""Verify eager Collections with native Python value semantics.

The tests cover the public sequence contract, transformations, and failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import StatisticsError
from typing import TYPE_CHECKING, assert_type

import pytest
from hypothesis import given
from hypothesis import strategies as st

from titanspan.collections import Collection, collect

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from collections.abc import Iterable


_EXPECTED_SEQUENCE_LENGTH = 4
_EXPECTED_LAST_VALUE = 4
_MISSING_INDEX = 7
_EXPECTED_ITEM_COUNT = 3
_EXPECTED_SINGLETON_VALUE = 8
_EXPECTED_MATCH_VALUE = 2
_EXPECTED_SUM = 6
_EXPECTED_AVERAGE = 2.0
_EXPECTED_MAXIMUM = 3
_EXPECTED_MEDIAN = 2.5


@dataclass(frozen=True, slots=True)
class Record:
    """Represent a typed record used by collection pipelines.

    Attributes:
        name: The record's display name.
        active: Whether the record is eligible for selection.
        group: The group assigned to the record.
    """

    name: str
    active: bool
    group: str


def test_construction_copies_iteration_and_mapping_keys() -> None:
    """Snapshot source order while preserving ordinary mapping iteration.

    Returns:
        None.
    """
    source = [1, 2]
    items = collect(source)
    source.append(3)

    assert items.all() == [1, 2]
    assert collect({"a": 1, "b": 2}).all() == ["a", "b"]
    assert collect({"a": 1}.items()).all() == [("a", 1)]


def test_sequence_protocol_uses_python_indexing_and_equality() -> None:
    """Expose indexing, slicing, iteration, and length without mutation.

    Returns:
        None.
    """
    values = collect([None, False, 0, ""])

    assert len(values) == _EXPECTED_SEQUENCE_LENGTH
    assert list(values) == [None, False, 0, ""]
    assert values[0] is None
    assert values[-1] == ""
    assert values[1:3] == collect([False, 0])
    assert values == collect([None, False, 0, ""])
    assert values != [None, False, 0, ""]
    assert list(reversed(values)) == ["", 0, False, None]
    assert repr(values).startswith("Collection(")
    with pytest.raises(TypeError, match="unhashable"):
        hash(values)


def test_get_and_endpoints_distinguish_missing_from_explicit_defaults() -> None:
    """Return explicit false-like defaults and raise for missing values.

    Returns:
        None.
    """
    values = collect([None, 4])

    assert values.get(0) is None
    assert values.get(_MISSING_INDEX, None) is None
    assert values.get(_MISSING_INDEX, False) is False
    assert values.first() is None
    assert values.first(False) is None
    assert values.last() == _EXPECTED_LAST_VALUE
    assert values.last(None) == _EXPECTED_LAST_VALUE
    with pytest.raises(IndexError):
        collect([]).get(0)
    with pytest.raises(IndexError):
        collect([]).first()
    with pytest.raises(IndexError):
        collect([]).last()
    assert collect([]).first(None) is None
    assert collect([]).last(False) is False


def test_sole_count_and_empty_predicates_follow_python_truth_rules() -> None:
    """Count items and distinguish empty values from absent items.

    Returns:
        None.
    """
    values = collect([None, False, 0])

    assert values.count() == _EXPECTED_ITEM_COUNT
    assert values.is_empty() is False
    assert values.is_not_empty() is True
    assert collect([]).is_empty() is True
    assert collect([]).is_not_empty() is False
    assert collect([_EXPECTED_SINGLETON_VALUE]).sole() == (
        _EXPECTED_SINGLETON_VALUE
    )
    assert (
        collect([1, 2, 3]).sole(lambda item: item == _EXPECTED_MATCH_VALUE)
        == _EXPECTED_MATCH_VALUE
    )
    empty_items: Collection[int] = collect([])
    with pytest.raises(ValueError, match="no item matched"):
        empty_items.sole()
    with pytest.raises(ValueError, match="multiple items matched"):
        collect([1, 1]).sole()


def test_map_filter_reject_and_flat_map_preserve_output_types() -> None:
    """Preserve source types or replace them with callback result types.

    Returns:
        None.
    """
    records = collect(
        [
            Record("Ada", True, "research"),
            Record("Lin", False, "platform"),
        ]
    )
    names: Collection[str] = (
        records.filter(lambda record: record.active)
        .map(lambda record: record.name)
        .unique()
    )
    assert_type(names, Collection[str])
    assert names.all() == ["Ada"]
    assert records.reject(lambda record: record.active).all() == [
        Record("Lin", False, "platform")
    ]
    assert collect([1, 2]).flat_map(lambda item: [item, -item]).all() == [
        1,
        -1,
        2,
        -2,
    ]


def test_flatten_and_pluck_delegate_nested_data_access() -> None:
    """Flatten nested Support data and extract dotted paths or callbacks.

    Returns:
        None.
    """
    values = collect(
        [
            {"profile": {"name": "Ada"}},
            {"profile": {"name": None}},
            {"profile": {}},
        ]
    )

    assert values.pluck("profile.name").all() == ["Ada", None, None]
    assert values.map(lambda item: item["profile"].get("name")).all() == [
        "Ada",
        None,
        None,
    ]
    assert collect([[1, [2]], {"a": 3}, "word"]).flatten().all() == [
        1,
        2,
        3,
        "word",
    ]
    assert collect([[1, [2]]]).flatten(depth=1).all() == [1, [2]]
    with pytest.raises(ValueError, match="flatten depth"):
        collect([[1]]).flatten(depth=-1)


def test_each_tap_and_pipe_keep_their_documented_return_values() -> None:
    """Reuse Support tapping and preserve explicit callback results.

    Returns:
        None.
    """
    values = collect([1, 2])
    visited: list[int] = []

    result = values.each(visited.append)
    tapped = values.tap(lambda collection: visited.append(collection.count()))

    assert result is values
    assert tapped is values
    assert visited == [1, 2, 2]
    expected_count = 2
    assert values.pipe(lambda collection: collection.count()) == expected_count


def test_each_rejects_awaitables_and_propagates_callback_errors() -> None:
    """Reject discarded awaitables and preserve callback exceptions.

    Returns:
        None.
    """

    async def callback(value: int) -> None:
        """Provide an invalid async callback for the sync each operation.

        Args:
            value: The current item.

        Returns:
            None.
        """
        del value

    def fail(value: int) -> None:
        """Raise the original user exception for one item.

        Args:
            value: The current item.

        Returns:
            None.
        """
        raise LookupError(str(value))

    with pytest.raises(TypeError):
        collect([1]).each(callback)
    with pytest.raises(LookupError, match="1"):
        collect([1]).each(fail)


def test_take_skip_slice_chunk_and_partition_preserve_order() -> None:
    """Select and group ordered items with explicit chunk boundaries.

    Returns:
        None.
    """
    values = collect([0, 1, 2, 3, 4])

    assert values.take(2).all() == [0, 1]
    assert values.skip(2).all() == [2, 3, 4]
    assert values.slice(-3, None, 2).all() == [2, 4]
    assert [chunk.all() for chunk in values.chunk(2)] == [
        [0, 1],
        [2, 3],
        [4],
    ]
    accepted, rejected = values.partition(lambda value: value % 2 == 0)
    assert accepted.all() == [0, 2, 4]
    assert rejected.all() == [1, 3]
    with pytest.raises(ValueError, match="take count"):
        values.take(-1)
    with pytest.raises(ValueError, match="skip count"):
        values.skip(-1)
    with pytest.raises(ValueError, match="chunk size"):
        values.chunk(0)


def test_enumerate_zip_contains_predicates_and_search_are_ordered() -> None:
    """Follow Python tuple order, equality, and empty predicate behavior.

    Returns:
        None.
    """
    values = collect([None, 0, False])

    assert values.enumerate(4).all() == [(4, None), (5, 0), (6, False)]
    assert values.zip(["a"]).all() == [(None, "a")]
    assert None in values
    assert [] not in values
    assert values.contains(False)
    assert values.search(None) == 0
    assert values.search("missing") is None
    empty_values: Collection[object] = collect([])
    assert empty_values.every(bool) is True
    assert empty_values.some(bool) is False
    assert values.every(lambda value: value != "missing")


def test_unique_and_ordered_set_operations_support_unhashable_items() -> None:
    """Apply ordered set behavior with equality for lists and dictionaries.

    Returns:
        None.
    """
    values = collect([[1], [1], {"name": "Ada"}, [2]])

    assert values.unique().all() == [[1], {"name": "Ada"}, [2]]
    assert values.difference([[1]]).all() == [{"name": "Ada"}, [2]]
    assert values.intersection([[1], [2]]).all() == [[1], [2]]
    assert collect([2, 2, 1]).intersection().all() == [2, 1]
    assert values.union([[2], [3]]).all() == [
        [1],
        {"name": "Ada"},
        [2],
        [3],
    ]
    assert collect([1, 1, 2]).concat([2, 3]).all() == [1, 1, 2, 2, 3]


def test_sort_group_key_count_and_aggregations_use_python_operations() -> None:
    """Preserve stable sorting and return native ordered dictionaries.

    Returns:
        None.
    """
    records = collect(
        [
            Record("A", True, "red"),
            Record("B", False, "blue"),
            Record("C", True, "red"),
        ]
    )

    assert records.sort_by(lambda record: record.group).all() == [
        records[1],
        records[0],
        records[2],
    ]
    assert records.min(key=lambda record: record.name) == records[0]
    assert records.max(key=lambda record: record.name) == records[2]
    by_name = collect([{"name": "A"}, {"name": "C"}])
    assert by_name.sort_by("name", reverse=True).first() == {"name": "C"}
    grouped = records.group_by(lambda record: record.group)
    assert_type(grouped, dict[str, Collection[Record]])
    assert {key: group.count() for key, group in grouped.items()} == {
        "red": 2,
        "blue": 1,
    }
    keyed = records.key_by(lambda record: record.group)
    assert_type(keyed, dict[str, Record])
    assert keyed["red"] == records[2]
    counts = records.count_by(lambda record: record.active)
    assert_type(counts, dict[bool, int])
    assert counts == {True: 2, False: 1}
    assert collect([3, 1, 2]).sort().all() == [1, 2, 3]
    assert collect([3, 1, 2]).reduce(lambda total, item: total + item, 0) == (
        _EXPECTED_SUM
    )
    integer_sum = collect([1, 2, 3]).sum()
    assert_type(integer_sum, int)
    assert integer_sum == _EXPECTED_SUM
    assert collect([1, 2, 3]).average() == _EXPECTED_AVERAGE
    assert collect([1, 2, 3]).min() == 1
    assert collect([1, 2, 3]).max() == _EXPECTED_MAXIMUM
    assert collect([1, 2, 3, 4]).median() == _EXPECTED_MEDIAN


def test_aggregation_empty_and_incompatible_inputs_raise_native_errors() -> (
    None
):
    """Propagate standard sorting and aggregation failures.

    Returns:
        None.
    """
    empty: Collection[int] = collect([])

    assert empty.sum() == 0
    with pytest.raises(ValueError, match="iterable argument is empty"):
        empty.min()
    with pytest.raises(ValueError, match="iterable argument is empty"):
        empty.max()
    with pytest.raises(StatisticsError):
        empty.average()
    with pytest.raises(StatisticsError):
        empty.median()
    with pytest.raises(TypeError):
        collect([1, "two"]).sort()


def test_string_field_grouping_missing_keys_and_duplicate_key_replacement() -> (
    None
):
    """Use Support field access and keep native dictionary replacement.

    Returns:
        None.
    """
    values = collect(
        [
            {"group": "a", "value": 1},
            {"group": "a", "value": 2},
            {"value": 3},
        ]
    )

    assert values.group_by(lambda item: item.get("group"))[None].all() == [
        {"value": 3}
    ]
    assert values.key_by(lambda item: item.get("group"))["a"] == {
        "group": "a",
        "value": 2,
    }
    assert values.key_by(lambda item: item.get("group"))[None] == {"value": 3}
    assert values.count_by(lambda item: item.get("group")) == {
        "a": 2,
        None: 1,
    }


def test_collection_shares_items_but_does_not_mutate_its_sequence() -> None:
    """Copy containers while preserving identity of mutable item references.

    Returns:
        None.
    """
    item = {"value": 1}
    values = collect([item])
    mapped = values.map(lambda value: value["value"])
    item["value"] = 2

    assert values[0] is item
    expected_value = 2
    assert values[0]["value"] == expected_value
    assert mapped.all() == [1]
    assert values.all() == [item]


@given(st.lists(st.integers()))
def test_reverse_is_an_involution_for_arbitrary_integer_sequences(
    values: list[int],
) -> None:
    """Return the original order after reversing a collection twice.

    Args:
        values: An arbitrary finite integer sequence.

    Returns:
        None.
    """
    collection = collect(values)

    assert collection.reverse().reverse() == collection
    assert collection.all() == values


@given(st.lists(st.integers()))
def test_unique_is_idempotent_and_stable(values: list[int]) -> None:
    """Keep first-seen values and preserve the original order.

    Args:
        values: An arbitrary finite integer sequence.

    Returns:
        None.
    """
    unique_values = collect(values).unique()

    assert unique_values.unique() == unique_values
    assert unique_values.all() == list(dict.fromkeys(values))


def test_public_callbacks_accept_native_iterables() -> None:
    """Consume each callback iterable without wrapping Python's behavior.

    Returns:
        None.
    """

    def values() -> Iterable[int]:
        """Produce a one-shot iterable for construction.

        Returns:
            A generator of integer values.
        """
        yield 1
        yield 2

    assert collect(values()).all() == [1, 2]
