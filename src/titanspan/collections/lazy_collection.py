"""Provide lazy collection pipelines over Python iterables.

Pipelines retain their source behavior and never cache traversed values.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Iterable, Iterator
from itertools import chain, dropwhile, islice, takewhile
from statistics import fmean
from statistics import median as statistics_median
from typing import TYPE_CHECKING, SupportsFloat, cast, overload

from titanspan.collections.collection import Collection

if TYPE_CHECKING:
    from titanspan.collections._internal import (
        SupportsOrdering as _SupportsOrdering,
    )

_MISSING = object()
_TAKE_COUNT_ERROR = "take count must be non-negative"
_SKIP_COUNT_ERROR = "skip count must be non-negative"
_CHUNK_SIZE_ERROR = "chunk size must be positive"
_EMPTY_FIRST_ERROR = "first item requested from an empty source"
_EMPTY_LAST_ERROR = "last item requested from an empty source"


class _FactoryIterable[T]:
    """Expose an iterator factory as a private iterable source.

    Attributes:
        factory: A function that creates the next pipeline iterator.
        replayable: Whether each traversal can request a fresh source.
    """

    def __init__(
        self,
        factory: Callable[[], Iterator[T]],
        replayable: bool,
    ) -> None:
        """Store a source factory and its replayability metadata.

        Args:
            factory: A function that creates an iterator on traversal.
            replayable: Whether repeated traversals request fresh sources.
        """
        self.factory = factory
        self.replayable = replayable

    def __iter__(self) -> Iterator[T]:
        """Create the iterator for one traversal.

        Returns:
            The iterator returned by the stored factory.
        """
        return self.factory()


def _from_factory[T](
    factory: Callable[[], Iterator[T]],
    replayable: bool,
) -> LazyCollection[T]:
    """Build a pipeline from a deferred iterator factory.

    Args:
        factory: A function that creates one output iterator.
        replayable: Whether repeated traversals create fresh iterators.

    Returns:
        A lazy collection backed by the supplied factory.
    """
    return LazyCollection(_FactoryIterable(factory, replayable))


def _is_replayable_source(source: Iterable[object]) -> bool:
    """Return whether an iterable can provide a fresh source traversal.

    Args:
        source: The iterable appended to or zipped with a pipeline.

    Returns:
        Whether each traversal can request a new underlying iterator.
    """
    if isinstance(source, LazyCollection):
        return source.is_replayable
    return not isinstance(source, Iterator)


class LazyCollection[T]:
    """Compose iterator operations without caching source values.

    A replayable iterable creates a new iterator for each traversal. A source
    that already implements ``Iterator`` remains one-shot.

    Attributes:
        _factory: A function that creates the next pipeline iterator.
        _replayable: Whether repeated traversal requests fresh source iterators.
    """

    def __init__(self, values: Iterable[T]) -> None:
        """Store an iterable without consuming its values.

        Args:
            values: A replayable iterable or a one-shot iterator.
        """
        if isinstance(values, _FactoryIterable):
            self._factory = lambda: iter(values)
            self._replayable = values.replayable
        elif isinstance(values, LazyCollection):
            self._factory = lambda: iter(values)
            self._replayable = values.is_replayable
        elif isinstance(values, Iterator):
            self._factory = lambda: values
            self._replayable = False
        else:
            self._factory = lambda: iter(values)
            self._replayable = True

    def __iter__(self) -> Iterator[T]:
        """Create an iterator for the next traversal.

        Returns:
            The next source or pipeline iterator.
        """
        return self._factory()

    @property
    def is_replayable(self) -> bool:
        """Report whether the source can provide fresh iterators.

        Returns:
            Whether repeated traversals request a new source iterator.
        """
        return self._replayable

    def map[U](self, callback: Callable[[T], U]) -> LazyCollection[U]:
        """Transform values as the pipeline is traversed.

        Args:
            callback: A function that returns each replacement value.

        Returns:
            A lazy collection parameterized by callback results.
        """
        return _from_factory(
            lambda: (callback(item) for item in self),
            self._replayable,
        )

    def filter(
        self,
        predicate: Callable[[T], object],
    ) -> LazyCollection[T]:
        """Keep values whose predicate result is truthy.

        Args:
            predicate: A function that decides whether to keep each value.

        Returns:
            A lazy collection containing matching values.
        """
        return _from_factory(
            lambda: (item for item in self if bool(predicate(item))),
            self._replayable,
        )

    def reject(
        self,
        predicate: Callable[[T], object],
    ) -> LazyCollection[T]:
        """Keep values whose predicate result is false-like.

        Args:
            predicate: A function that decides whether to reject each value.

        Returns:
            A lazy collection containing non-matching values.
        """
        return _from_factory(
            lambda: (item for item in self if not bool(predicate(item))),
            self._replayable,
        )

    def flat_map[U](
        self,
        callback: Callable[[T], Iterable[U]],
    ) -> LazyCollection[U]:
        """Map values to iterables and stream their items in order.

        Args:
            callback: A function that returns values for each input.

        Returns:
            A lazy collection over each returned iterable in order.
        """
        return _from_factory(
            lambda: chain.from_iterable(callback(item) for item in self),
            self._replayable,
        )

    def take(self, count: int) -> LazyCollection[T]:
        """Limit traversal to a finite number of leading values.

        Args:
            count: The maximum number of values to yield.

        Returns:
            A lazy collection that yields at most ``count`` values.

        Raises:
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_TAKE_COUNT_ERROR)
        return _from_factory(
            lambda: islice(self, count),
            self._replayable,
        )

    def skip(self, count: int) -> LazyCollection[T]:
        """Skip a finite number of leading values.

        Args:
            count: The number of values to discard.

        Returns:
            A lazy collection over the remaining values.

        Raises:
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_SKIP_COUNT_ERROR)
        return _from_factory(
            lambda: islice(self, count, None),
            self._replayable,
        )

    def take_while(
        self,
        predicate: Callable[[T], object],
    ) -> LazyCollection[T]:
        """Yield leading values while the predicate remains truthy.

        Args:
            predicate: A function that decides whether to continue.

        Returns:
            A lazy collection ending at the first failed predicate.
        """
        return _from_factory(
            lambda: takewhile(lambda item: bool(predicate(item)), self),
            self._replayable,
        )

    def skip_while(
        self,
        predicate: Callable[[T], object],
    ) -> LazyCollection[T]:
        """Skip leading values while the predicate remains truthy.

        Args:
            predicate: A function that decides whether to keep skipping.

        Returns:
            A lazy collection beginning at the first failed predicate.
        """
        return _from_factory(
            lambda: dropwhile(lambda item: bool(predicate(item)), self),
            self._replayable,
        )

    def chunk(self, size: int) -> LazyCollection[Collection[T]]:
        """Yield eager chunks while retaining at most ``size`` values.

        Args:
            size: The positive maximum number of values per chunk.

        Returns:
            A lazy collection of eager collections.

        Raises:
            ValueError: If ``size`` is not positive.
        """
        if size <= 0:
            raise ValueError(_CHUNK_SIZE_ERROR)

        def chunks() -> Iterator[Collection[T]]:
            """Create chunks on demand from one source traversal.

            Yields:
                Eager chunks containing at most ``size`` values.
            """
            source = iter(self)
            while values := tuple(islice(source, size)):
                yield Collection(values)

        return _from_factory(chunks, self._replayable)

    def enumerate(
        self,
        start: int = 0,
    ) -> LazyCollection[tuple[int, T]]:
        """Pair each value with its position during traversal.

        Args:
            start: The first integer index.

        Returns:
            A lazy collection of index and value pairs.
        """
        return _from_factory(
            lambda: builtins.enumerate(self, start),
            self._replayable,
        )

    @overload
    def zip[U](
        self,
        other: Iterable[U],
        /,
    ) -> LazyCollection[tuple[T, U]]:
        """Describe a lazy two-input zip.

        Args:
            other: The second iterable.

        Returns:
            A lazy collection of pairs.
        """

    @overload
    def zip[U, V](
        self,
        other: Iterable[U],
        second: Iterable[V],
        /,
    ) -> LazyCollection[tuple[T, U, V]]:
        """Describe a lazy three-input zip.

        Args:
            other: The second iterable.
            second: The third iterable.

        Returns:
            A lazy collection of triples.
        """

    @overload
    def zip(
        self,
        other: Iterable[object],
        second: Iterable[object],
        third: Iterable[object],
        /,
        *more: Iterable[object],
    ) -> LazyCollection[tuple[object, ...]]:
        """Describe a lazy zip with four or more sources.

        Args:
            other: The second iterable.
            second: The third iterable.
            third: The fourth iterable.
            *more: Additional iterables.

        Returns:
            A lazy collection of tuples.
        """

    def zip(
        self,
        other: Iterable[object],
        /,
        *more: Iterable[object],
    ) -> LazyCollection[tuple[object, ...]]:
        """Zip values with one or more iterables until one source ends.

        Args:
            other: The second iterable.
            *more: Additional iterables to zip.

        Returns:
            A lazy collection of tuples, truncated at the shortest source.
        """
        sources = (other, *more)
        replayable = self._replayable and all(
            _is_replayable_source(source) for source in sources
        )
        return _from_factory(
            lambda: builtins.zip(self, *sources, strict=False),
            replayable,
        )

    def concat(self, *others: Iterable[T]) -> LazyCollection[T]:
        """Append iterables without materializing or removing duplicates.

        Args:
            *others: Sources to visit after this collection.

        Returns:
            A lazy collection that yields each source in order.
        """
        replayable = self._replayable and all(
            _is_replayable_source(source) for source in others
        )
        return _from_factory(
            lambda: chain(self, *others),
            replayable,
        )

    def collect(self) -> Collection[T]:
        """Materialize the remaining values into an eager collection.

        Returns:
            An eager collection containing the traversal values.
        """
        return Collection(self)

    @overload
    def first(self) -> T:
        """Describe first-value access without a default.

        Returns:
            The first value.

        Raises:
            IndexError: If the source is empty.
        """

    @overload
    def first[Default](self, default: Default, /) -> T | Default:
        """Describe first-value access with an explicit default.

        Args:
            default: The value returned when the source is empty.

        Returns:
            The first value or the supplied default.
        """

    def first(self, default: object = _MISSING) -> object:
        """Consume and return the next value or an explicit fallback.

        Args:
            default: The value returned when the source is empty.

        Returns:
            The first value or the supplied default.

        Raises:
            IndexError: If empty and no default was supplied.
        """
        value = next(iter(self), _MISSING)
        if value is not _MISSING:
            return value
        if default is _MISSING:
            raise IndexError(_EMPTY_FIRST_ERROR)
        return default

    @overload
    def last(self) -> T:
        """Describe last-value access without a default.

        Returns:
            The last value.

        Raises:
            IndexError: If the source is empty.
        """

    @overload
    def last[Default](self, default: Default, /) -> T | Default:
        """Describe last-value access with an explicit default.

        Args:
            default: The value returned when the source is empty.

        Returns:
            The last value or the supplied default.
        """

    def last(self, default: object = _MISSING) -> object:
        """Consume the source and return its last value.

        Args:
            default: The value returned when the source is empty.

        Returns:
            The final value or the supplied default.

        Raises:
            IndexError: If empty and no default was supplied.
        """
        source = iter(self)
        last_value = next(source, _MISSING)
        if last_value is _MISSING:
            if default is _MISSING:
                raise IndexError(_EMPTY_LAST_ERROR)
            return default
        result = cast("T", last_value)
        for value in source:
            result = value
        return result

    def count(self) -> int:
        """Consume the source and count its remaining values.

        Returns:
            The number of values in this traversal.
        """
        return builtins.sum(1 for _ in self)

    def reduce[Result](
        self,
        callback: Callable[[Result, T], Result],
        initial: Result,
    ) -> Result:
        """Reduce values from left to right using an explicit initial value.

        Args:
            callback: A function combining the accumulator and next value.
            initial: The accumulator value before traversal.

        Returns:
            The final accumulator.
        """
        result = initial
        for item in self:
            result = callback(result, item)
        return result

    @overload
    def sum(self: LazyCollection[int], start: int = 0) -> int:
        """Describe integer addition.

        Args:
            start: The initial integer value.

        Returns:
            The integer total.
        """

    @overload
    def sum(self: LazyCollection[float], start: float = 0.0) -> float:
        """Describe floating-point addition.

        Args:
            start: The initial floating-point value.

        Returns:
            The floating-point total.
        """

    @overload
    def sum(self: LazyCollection[complex], start: complex = 0j) -> complex:
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
        values = cast("Iterable[int | float | complex]", self)
        return builtins.sum(values, start)

    def average(self) -> float:
        """Consume values and calculate their floating-point mean.

        Returns:
            The mean computed by ``statistics.fmean``.

        Raises:
            statistics.StatisticsError: If the source is empty.
            TypeError: If a value cannot be converted to a float.
        """
        return fmean(cast("Iterable[SupportsFloat]", self))

    def min(self, *, key: Callable[[T], object] | None = None) -> T:
        """Consume the source and return its smallest value.

        Args:
            key: An optional function that returns ordering values.

        Returns:
            The smallest source value.

        Raises:
            ValueError: If the source is empty.
            TypeError: If Python cannot compare selected values.
        """
        if key is None:
            values = cast("Iterable[_SupportsOrdering]", self)
            return cast("T", builtins.min(values))
        ordering_key = cast("Callable[[T], _SupportsOrdering]", key)
        return builtins.min(self, key=ordering_key)

    def max(self, *, key: Callable[[T], object] | None = None) -> T:
        """Consume the source and return its largest value.

        Args:
            key: An optional function that returns ordering values.

        Returns:
            The largest source value.

        Raises:
            ValueError: If the source is empty.
            TypeError: If Python cannot compare selected values.
        """
        if key is None:
            values = cast("Iterable[_SupportsOrdering]", self)
            return cast("T", builtins.max(values))
        ordering_key = cast("Callable[[T], _SupportsOrdering]", key)
        return builtins.max(self, key=ordering_key)

    def median(self) -> T | float:
        """Materialize the source and calculate its statistical median.

        Returns:
            The median calculated by ``statistics.median``.

        Raises:
            statistics.StatisticsError: If the source is empty.
            TypeError: If values cannot be ordered or averaged.
        """
        numbers = cast("Iterable[int | float]", self)
        return cast("T | float", statistics_median(numbers))


def lazy[T](values: Iterable[T]) -> LazyCollection[T]:
    """Create a lazy collection without consuming the input.

    Args:
        values: A replayable iterable or a one-shot iterator.

    Returns:
        A lazy collection that preserves the input's traversal behavior.
    """
    return LazyCollection(values)
