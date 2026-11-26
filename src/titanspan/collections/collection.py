"""Provide an eager, ordered collection over Python iterables.

Transformations copy the sequence while retaining references to its items.
Nested-data access and side-effect tapping reuse Titanspan Support.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Hashable, Iterable, Iterator
from itertools import chain
from math import inf
from statistics import fmean
from statistics import median as statistics_median
from typing import TYPE_CHECKING, Self, SupportsFloat, cast, overload

from titanspan.support.arr import Arr
from titanspan.support.helpers import tap as support_tap
from titanspan.support.tappable import Tappable

if TYPE_CHECKING:
    from titanspan.collections._internal import (
        SupportsOrdering as _SupportsOrdering,
    )

_MISSING = object()
_EMPTY_FIRST_ERROR = "first item requested from an empty collection"
_EMPTY_LAST_ERROR = "last item requested from an empty collection"
_NO_SOLE_ITEM_ERROR = "no item matched the sole-item request"
_MANY_SOLE_ITEMS_ERROR = "multiple items matched the sole-item request"
_FLATTEN_DEPTH_ERROR = "flatten depth must be non-negative"
_TAKE_COUNT_ERROR = "take count must be non-negative"
_SKIP_COUNT_ERROR = "skip count must be non-negative"
_CHUNK_SIZE_ERROR = "chunk size must be positive"
_UNHASHABLE_ERROR = "unhashable type: 'Collection'"


class _EqualitySet:
    """Index values for stable equality operations, including unhashables.

    Hashable items use a native set. Unhashable items retain list equality
    semantics without forcing every ordinary lookup into a linear scan.
    """

    def __init__(self, values: Iterable[object] = ()) -> None:
        """Build a membership index from the provided values.

        Args:
            values: Values to add in their source order.
        """
        self._hashable: set[object] = set()
        self._unhashable: list[object] = []
        self._all: list[object] = []
        for value in values:
            self.add(value)

    def __contains__(self, value: object, /) -> bool:
        """Check membership with normal equality for every value shape.

        Args:
            value: The candidate to find.

        Returns:
            Whether an equal value exists.
        """
        try:
            hash(value)
        except TypeError:
            candidates = self._all
        else:
            if value in self._hashable:
                return True
            candidates = self._unhashable
        return any(value == candidate for candidate in candidates)

    def add(self, value: object) -> None:
        """Add one value to the membership index.

        Args:
            value: The value to index.
        """
        try:
            hash(value)
        except TypeError:
            self._unhashable.append(value)
        else:
            self._hashable.add(value)
        self._all.append(value)


class Collection[T](Tappable):
    """Store an ordered, shallow snapshot of iterable values.

    Transformations return new ``Collection`` instances. Their items remain
    shared references, so callers can still mutate item objects.

    Attributes:
        _items: The immutable tuple that stores item order.
    """

    def __init__(self, values: Iterable[T] = ()) -> None:
        """Copy source iteration into an ordered tuple.

        Args:
            values: The iterable to consume once.
        """
        self._items = tuple(values)

    def __iter__(self) -> Iterator[T]:
        """Iterate over the stored values in source order.

        Returns:
            An iterator over the collection's items.
        """
        return iter(self._items)

    def __reversed__(self) -> Iterator[T]:
        """Iterate over stored values in reverse order.

        Returns:
            A reverse iterator over the collection's items.
        """
        return reversed(self._items)

    def __len__(self) -> int:
        """Return the number of stored values.

        Returns:
            The collection size.
        """
        return len(self._items)

    def __contains__(self, value: object, /) -> bool:
        """Check whether an equal value occurs in this collection.

        Args:
            value: The candidate value.

        Returns:
            Whether Python equality finds a matching item.
        """
        return value in self._items

    @overload
    def __getitem__(self, index: int, /) -> T:
        """Describe integer indexing.

        Args:
            index: A zero-based or negative index.

        Returns:
            The selected item.
        """

    @overload
    def __getitem__(self, index: slice, /) -> Collection[T]:
        """Describe slice indexing.

        Args:
            index: A Python slice.

        Returns:
            A new collection containing selected items.
        """

    def __getitem__(self, index: int | slice, /) -> T | Collection[T]:
        """Return one item or a new sliced collection.

        Args:
            index: An integer or Python slice.

        Returns:
            The selected item or a shallow collection copy.
        """
        if isinstance(index, slice):
            return Collection(self._items[index])
        return self._items[index]

    def __eq__(self, other: object, /) -> bool:
        """Compare another collection using tuple value equality.

        Args:
            other: The value to compare.

        Returns:
            Whether another collection contains equal items in order.
        """
        if not isinstance(other, Collection):
            return False
        return self._items == tuple(cast("Iterable[object]", other))

    def __hash__(self) -> int:
        """Reject hashing to preserve equality over mutable item values.

        Returns:
            This method never returns.

        Raises:
            TypeError: Collections are always unhashable.
        """
        raise TypeError(_UNHASHABLE_ERROR) from None

    def __repr__(self) -> str:
        """Return a representation that shows the stored values.

        Returns:
            A constructor-like string representation.
        """
        return f"{type(self).__name__}({self._items!r})"

    @overload
    def get(self, index: int, /) -> T:
        """Describe indexed access without a default.

        Args:
            index: A zero-based or negative index.

        Returns:
            The selected item.

        Raises:
            IndexError: If the index is absent.
        """

    @overload
    def get[Default](self, index: int, default: Default, /) -> T | Default:
        """Describe indexed access with an explicit default.

        Args:
            index: A zero-based or negative index.
            default: The value returned when the index is absent.

        Returns:
            The selected item or the supplied default.
        """

    def get(
        self,
        index: int,
        default: object = _MISSING,
        /,
    ) -> object:
        """Return an indexed item or an explicit fallback.

        Args:
            index: A zero-based or negative index.
            default: A fallback value, including false-like values.

        Returns:
            The selected item or the supplied default.

        Raises:
            IndexError: If the index is absent and no default was supplied.
        """
        try:
            return self._items[index]
        except IndexError:
            if default is _MISSING:
                raise
            return default

    @overload
    def first(self) -> T:
        """Describe first-item access without a default.

        Returns:
            The first item.

        Raises:
            IndexError: If the collection is empty.
        """

    @overload
    def first[Default](self, default: Default, /) -> T | Default:
        """Describe first-item access with a default.

        Args:
            default: The value returned when the collection is empty.

        Returns:
            The first item or the supplied default.
        """

    def first(self, default: object = _MISSING) -> object:
        """Return the first item or an explicit fallback.

        Args:
            default: A fallback value, including ``None``.

        Returns:
            The first item or the supplied default.

        Raises:
            IndexError: If empty and no default was supplied.
        """
        if self._items:
            return self._items[0]
        if default is _MISSING:
            raise IndexError(_EMPTY_FIRST_ERROR)
        return default

    @overload
    def last(self) -> T:
        """Describe last-item access without a default.

        Returns:
            The last item.

        Raises:
            IndexError: If the collection is empty.
        """

    @overload
    def last[Default](self, default: Default, /) -> T | Default:
        """Describe last-item access with a default.

        Args:
            default: The value returned when the collection is empty.

        Returns:
            The last item or the supplied default.
        """

    def last(self, default: object = _MISSING) -> object:
        """Return the last item or an explicit fallback.

        Args:
            default: A fallback value, including ``None``.

        Returns:
            The last item or the supplied default.

        Raises:
            IndexError: If empty and no default was supplied.
        """
        if self._items:
            return self._items[-1]
        if default is _MISSING:
            raise IndexError(_EMPTY_LAST_ERROR)
        return default

    def all(self) -> list[T]:
        """Return a new list containing the stored item references.

        Returns:
            A shallow list copy in source order.
        """
        return list(self._items)

    def count(self) -> int:
        """Return the number of stored items.

        Returns:
            The collection size.
        """
        return len(self._items)

    def is_empty(self) -> bool:
        """Check whether the collection contains no items.

        Returns:
            Whether the collection is empty.
        """
        return not self._items

    def is_not_empty(self) -> bool:
        """Check whether the collection contains at least one item.

        Returns:
            Whether the collection is non-empty.
        """
        return bool(self._items)

    def sole(
        self,
        predicate: Callable[[T], object] | None = None,
    ) -> T:
        """Return the only item, optionally selected by a predicate.

        Args:
            predicate: An optional value filter.

        Returns:
            The only matching item.

        Raises:
            ValueError: If zero or more than one item matches.
        """
        matches = (
            item
            for item in self._items
            if predicate is None or bool(predicate(item))
        )
        selected = next(matches, _MISSING)
        if selected is _MISSING:
            raise ValueError(_NO_SOLE_ITEM_ERROR)
        if next(matches, _MISSING) is not _MISSING:
            raise ValueError(_MANY_SOLE_ITEMS_ERROR)
        return cast("T", selected)

    def map[U](self, callback: Callable[[T], U]) -> Collection[U]:
        """Transform each item and preserve iteration order.

        Args:
            callback: A function that returns the replacement item.

        Returns:
            A collection parameterized by the callback result type.
        """
        return Collection(callback(item) for item in self._items)

    def filter(
        self,
        predicate: Callable[[T], object],
    ) -> Collection[T]:
        """Keep items whose predicate result is truthy.

        Args:
            predicate: A function that decides whether to retain each item.

        Returns:
            A new collection containing matching items.
        """
        return Collection(item for item in self._items if bool(predicate(item)))

    def reject(
        self,
        predicate: Callable[[T], object],
    ) -> Collection[T]:
        """Keep items whose predicate result is false-like.

        Args:
            predicate: A function that decides whether to reject each item.

        Returns:
            A new collection containing non-matching items.
        """
        return Collection(
            item for item in self._items if not bool(predicate(item))
        )

    def flat_map[U](
        self,
        callback: Callable[[T], Iterable[U]],
    ) -> Collection[U]:
        """Map each item to an iterable and concatenate its values.

        Args:
            callback: A function that returns values to append.

        Returns:
            A new collection containing each returned iterable in order.
        """
        return Collection(
            chain.from_iterable(callback(item) for item in self._items)
        )

    def flatten(self, depth: int | None = None) -> Collection[object]:
        """Flatten nested mappings and sequences through Support.Arr.

        Args:
            depth: Maximum levels to expand, or ``None`` for full flattening.

        Returns:
            A collection containing depth-first leaf values.

        Raises:
            ValueError: If ``depth`` is negative.
        """
        if depth is not None and depth < 0:
            raise ValueError(_FLATTEN_DEPTH_ERROR)
        resolved_depth = inf if depth is None else depth
        return Collection(Arr.flatten(self._items, resolved_depth))

    def pluck(
        self,
        key: str,
    ) -> Collection[object]:
        """Extract values by direct or dotted mapping path.

        Args:
            key: A direct or dotted field path.

        Returns:
            A new collection of extracted values.
        """
        return Collection(Arr.get(item, key) for item in self._items)

    def each(self, callback: Callable[[T], object]) -> Self:
        """Run a synchronous side effect for each item.

        Args:
            callback: A callback invoked once per item in source order.

        Returns:
            This collection for fluent use.

        Raises:
            AsyncCallbackUsageError: If a callback returns an awaitable.
        """
        for item in self._items:
            support_tap(item, callback)
        return self

    def pipe[R](self, callback: Callable[[Self], R]) -> R:
        """Pass this collection to a callback and return its result.

        Args:
            callback: A function that receives this collection.

        Returns:
            The callback result.
        """
        return callback(self)

    def take(self, count: int) -> Collection[T]:
        """Return the first ``count`` items.

        Args:
            count: A non-negative number of items.

        Returns:
            A new collection containing the leading items.

        Raises:
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_TAKE_COUNT_ERROR)
        return Collection(self._items[:count])

    def skip(self, count: int) -> Collection[T]:
        """Return items after the first ``count`` values.

        Args:
            count: A non-negative number of leading items to skip.

        Returns:
            A new collection containing the remaining items.

        Raises:
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_SKIP_COUNT_ERROR)
        return Collection(self._items[count:])

    def slice(
        self,
        start: int | None = None,
        stop: int | None = None,
        step: int | None = None,
    ) -> Collection[T]:
        """Select items with native Python slice semantics.

        Args:
            start: The inclusive starting index.
            stop: The exclusive stopping index.
            step: The interval between selected indexes.

        Returns:
            A new collection containing the selected items.

        Raises:
            ValueError: If ``step`` is zero.
        """
        return Collection(self._items[slice(start, stop, step)])

    def chunk(self, size: int) -> Collection[Collection[T]]:
        """Split items into ordered, fixed-size collections.

        Args:
            size: A positive maximum chunk size.

        Returns:
            A collection of chunks, including a final shorter chunk.

        Raises:
            ValueError: If ``size`` is not positive.
        """
        if size <= 0:
            raise ValueError(_CHUNK_SIZE_ERROR)
        return Collection(
            Collection(self._items[start : start + size])
            for start in range(0, len(self._items), size)
        )

    def partition(
        self,
        predicate: Callable[[T], object],
    ) -> tuple[Collection[T], Collection[T]]:
        """Split items into matching and remaining collections.

        Args:
            predicate: A function that selects matching items.

        Returns:
            Matching items, followed by non-matching items.
        """
        passed: list[T] = []
        failed: list[T] = []
        for item in self._items:
            (passed if bool(predicate(item)) else failed).append(item)
        return Collection(passed), Collection(failed)

    def reverse(self) -> Collection[T]:
        """Return a new collection with reversed item order.

        Returns:
            A collection containing items in reverse order.
        """
        return Collection(reversed(self._items))

    def enumerate(self, start: int = 0) -> Collection[tuple[int, T]]:
        """Pair each item with its index.

        Args:
            start: The first index value.

        Returns:
            A collection of index and item pairs.
        """
        return Collection(builtins.enumerate(self._items, start))

    @overload
    def zip[U](
        self,
        other: Iterable[U],
        /,
    ) -> Collection[tuple[T, U]]:
        """Describe a two-input zip.

        Args:
            other: The second iterable.

        Returns:
            Pairs from the two inputs.
        """

    @overload
    def zip[U, V](
        self,
        other: Iterable[U],
        second: Iterable[V],
        /,
    ) -> Collection[tuple[T, U, V]]:
        """Describe a three-input zip.

        Args:
            other: The second iterable.
            second: The third iterable.

        Returns:
            Triples from the three inputs.
        """

    @overload
    def zip(
        self,
        other: Iterable[object],
        second: Iterable[object],
        third: Iterable[object],
        /,
        *more: Iterable[object],
    ) -> Collection[tuple[object, ...]]:
        """Describe zipping four or more inputs.

        Args:
            other: The second iterable.
            second: The third iterable.
            third: The fourth iterable.
            *more: Additional iterables.

        Returns:
            Tuples truncated at the shortest input.
        """

    def zip(
        self,
        other: Iterable[object],
        *more: Iterable[object],
    ) -> Collection[tuple[object, ...]]:
        """Zip this collection with one or more iterables.

        Args:
            other: The second iterable.
            *more: Additional iterables.

        Returns:
            Tuples truncated at the shortest input.
        """
        return Collection(builtins.zip(self._items, other, *more, strict=False))

    def contains(self, value: object) -> bool:
        """Check whether an equal item exists.

        Args:
            value: The candidate item.

        Returns:
            Whether Python equality finds a match.
        """
        return value in self._items

    def every(self, predicate: Callable[[T], object]) -> bool:
        """Check whether every item passes a predicate.

        Args:
            predicate: A function whose result uses Python truthiness.

        Returns:
            Whether every item passes, including ``True`` for empty input.
        """
        return builtins.all(bool(predicate(item)) for item in self._items)

    def some(self, predicate: Callable[[T], object]) -> bool:
        """Check whether any item passes a predicate.

        Args:
            predicate: A function whose result uses Python truthiness.

        Returns:
            Whether at least one item passes.
        """
        return builtins.any(bool(predicate(item)) for item in self._items)

    def search(self, value: object) -> int | None:
        """Return the first matching zero-based index.

        Args:
            value: The value to find.

        Returns:
            The first index, or ``None`` when no item matches.
        """
        for index, item in builtins.enumerate(self._items):
            if item == value:
                return index
        return None

    def unique(self) -> Collection[T]:
        """Keep the first item from each equality group.

        Returns:
            A stable collection without equal duplicates.
        """
        seen = _EqualitySet()
        result: list[T] = []
        for item in self._items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return Collection(result)

    def sort(self, *, reverse: bool = False) -> Collection[T]:
        """Return a stable Python-sorted collection.

        Args:
            reverse: Whether to sort in descending order.

        Returns:
            A new collection in sorted order.

        Raises:
            TypeError: If Python cannot compare selected items.
        """
        values = cast("Iterable[_SupportsOrdering]", self._items)
        ordered = builtins.sorted(values, reverse=reverse)
        return Collection(cast("Iterable[T]", ordered))

    @overload
    def sort_by(
        self,
        key: Callable[[T], object],
        /,
        *,
        reverse: bool = False,
    ) -> Collection[T]:
        """Describe callback-based sorting.

        Args:
            key: A callback that returns an ordering value.
            reverse: Whether to sort in descending order.

        Returns:
            A stable collection ordered by callback results.
        """

    @overload
    def sort_by(
        self,
        key: str,
        /,
        *,
        reverse: bool = False,
    ) -> Collection[T]:
        """Describe field-path sorting.

        Args:
            key: A direct or dotted field path.
            reverse: Whether to sort in descending order.

        Returns:
            A stable collection ordered by selected fields.
        """

    def sort_by(
        self,
        key: str | Callable[[T], object],
        /,
        *,
        reverse: bool = False,
    ) -> Collection[T]:
        """Sort values by a callback or a Support field path.

        Args:
            key: A callback or direct/dotted field path.
            reverse: Whether to sort in descending order.

        Returns:
            A stable collection ordered by selected values.

        Raises:
            TypeError: If Python cannot compare selected values.
        """
        if callable(key):
            ordering_key = cast("Callable[[T], _SupportsOrdering]", key)
        else:

            def selector(item: T) -> object:
                """Read an item through its direct or dotted path.

                Args:
                    item: The item to inspect.

                Returns:
                    The value returned by Support.Arr.
                """
                return Arr.get(item, key)

            ordering_key = cast("Callable[[T], _SupportsOrdering]", selector)
        return Collection(
            builtins.sorted(self._items, key=ordering_key, reverse=reverse)
        )

    def group_by[K: Hashable](
        self,
        key: Callable[[T], K],
    ) -> dict[K, Collection[T]]:
        """Group values by a hashable callback result.

        Args:
            key: A callback that returns a hashable group key.

        Returns:
            An insertion-ordered mapping of keys to groups.

        Raises:
            TypeError: If a selected key is unhashable.
        """
        groups: dict[K, list[T]] = {}
        for item in self._items:
            selected = key(item)
            groups.setdefault(selected, []).append(item)
        return {
            selected: Collection(items) for selected, items in groups.items()
        }

    def key_by[K: Hashable](
        self,
        key: Callable[[T], K],
    ) -> dict[K, T]:
        """Index items by a hashable callback result.

        Later duplicate keys replace earlier items, following ``dict``
        assignment behavior.

        Args:
            key: A callback that returns a dictionary key.

        Returns:
            An insertion-ordered dictionary of selected items.

        Raises:
            TypeError: If a selected key is unhashable.
        """
        result: dict[K, T] = {}
        for item in self._items:
            selected = key(item)
            result[selected] = item
        return result

    def count_by[K: Hashable](
        self,
        key: Callable[[T], K],
    ) -> dict[K, int]:
        """Count items by a hashable callback result.

        Args:
            key: A callback that returns a dictionary key.

        Returns:
            An insertion-ordered mapping of keys to counts.

        Raises:
            TypeError: If a selected key is unhashable.
        """
        counts: dict[K, int] = {}
        for item in self._items:
            selected = key(item)
            counts[selected] = counts.get(selected, 0) + 1
        return counts

    def reduce[Result](
        self,
        callback: Callable[[Result, T], Result],
        initial: Result,
    ) -> Result:
        """Reduce items from left to right with a required initial value.

        Args:
            callback: A function combining the accumulator and next item.
            initial: The value used before the first item.

        Returns:
            The final accumulator.
        """
        result = initial
        for item in self._items:
            result = callback(result, item)
        return result

    @overload
    def sum(self: Collection[int], start: int = 0) -> int:
        """Describe integer addition.

        Args:
            start: The initial integer value.

        Returns:
            The integer total.
        """

    @overload
    def sum(self: Collection[float], start: float = 0.0) -> float:
        """Describe floating-point addition.

        Args:
            start: The initial floating-point value.

        Returns:
            The floating-point total.
        """

    @overload
    def sum(self: Collection[complex], start: complex = 0j) -> complex:
        """Describe complex addition.

        Args:
            start: The initial complex value.

        Returns:
            The complex total.
        """

    def sum(
        self,
        start: int | float | complex = 0,
    ) -> int | float | complex:
        """Delegate addition to Python's built-in ``sum``.

        Args:
            start: The initial value, defaulting to zero.

        Returns:
            The result produced by the built-in operation.

        Raises:
            TypeError: If the values do not support addition.
        """
        values = cast("Iterable[int | float | complex]", self._items)
        return builtins.sum(values, start)

    def average(self) -> float:
        """Return the arithmetic mean as a float.

        Returns:
            The mean computed by ``statistics.fmean``.

        Raises:
            statistics.StatisticsError: If the collection is empty.
            TypeError: If an item cannot be converted to a float.
        """
        return fmean(cast("Iterable[SupportsFloat]", self._items))

    def min(
        self,
        *,
        key: Callable[[T], object] | None = None,
    ) -> T:
        """Return the smallest item using Python ordering.

        Args:
            key: An optional ordering callback.

        Returns:
            The smallest item.

        Raises:
            ValueError: If the collection is empty.
            TypeError: If selected items cannot be compared.
        """
        if key is None:
            values = cast("Iterable[_SupportsOrdering]", self._items)
            return cast("T", builtins.min(values))
        ordering_key = cast("Callable[[T], _SupportsOrdering]", key)
        return builtins.min(self._items, key=ordering_key)

    def max(
        self,
        *,
        key: Callable[[T], object] | None = None,
    ) -> T:
        """Return the largest item using Python ordering.

        Args:
            key: An optional ordering callback.

        Returns:
            The largest item.

        Raises:
            ValueError: If the collection is empty.
            TypeError: If selected items cannot be compared.
        """
        if key is None:
            values = cast("Iterable[_SupportsOrdering]", self._items)
            return cast("T", builtins.max(values))
        ordering_key = cast("Callable[[T], _SupportsOrdering]", key)
        return builtins.max(self._items, key=ordering_key)

    def median(self) -> T | float:
        """Return the middle item or average the two middle items.

        Returns:
            The median calculated by ``statistics.median``.

        Raises:
            statistics.StatisticsError: If the collection is empty.
            TypeError: If values cannot be ordered or averaged.
        """
        numbers = cast("Iterable[int | float]", self._items)
        return cast("T | float", statistics_median(numbers))

    def concat(self, *others: Iterable[T]) -> Collection[T]:
        """Append values from other iterables without removing duplicates.

        Args:
            *others: Additional iterables to append in argument order.

        Returns:
            A new collection with all values in order.
        """
        return Collection(chain(self._items, *others))

    def difference(self, *others: Iterable[T]) -> Collection[T]:
        """Return unique items absent from all other iterables.

        Args:
            *others: Iterables whose values are excluded.

        Returns:
            A stable ordered-set difference.
        """
        excluded = _EqualitySet(chain.from_iterable(others))
        selected = _EqualitySet()
        result: list[T] = []
        for item in self._items:
            if item not in excluded and item not in selected:
                selected.add(item)
                result.append(item)
        return Collection(result)

    def intersection(self, *others: Iterable[T]) -> Collection[T]:
        """Return unique items present in every other iterable.

        Args:
            *others: Iterables used for membership checks.

        Returns:
            A stable ordered-set intersection.
        """
        if not others:
            return self.unique()
        common = _EqualitySet(chain.from_iterable(others))
        selected = _EqualitySet()
        result: list[T] = []
        for item in self._items:
            if item in common and item not in selected:
                selected.add(item)
                result.append(item)
        return Collection(result)

    def union(self, *others: Iterable[T]) -> Collection[T]:
        """Return unique values in first-seen order.

        Args:
            *others: Iterables appended before duplicate removal.

        Returns:
            A stable ordered-set union.
        """
        return self.concat(*others).unique()


def collect[T](values: Iterable[T]) -> Collection[T]:
    """Create an eager collection from an iterable.

    Args:
        values: The iterable to snapshot.

    Returns:
        A collection preserving source iteration order.
    """
    return Collection(values)
