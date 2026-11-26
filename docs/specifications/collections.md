# Collections specification

`titanspan.collections` provides typed eager and lazy APIs over ordinary
Python iterables. It delegates iteration, ordering, aggregation, and nested
mapping access to Python and Support.

Collections are value-oriented. They work without an Application, a
Container, or optional AI, database, queue, and web packages. The component
adds no runtime dependencies.

## Public API

```python
from titanspan.collections import Collection, LazyCollection, collect, lazy
```

`collect(values)` creates an eager `Collection[T]`. `lazy(values)` creates a
`LazyCollection[T]` without consuming its source. Transformations preserve
their source type or use the callback's result type.

## Eager sequence behavior

`Collection` stores a shallow snapshot of input iteration order. Construction
consumes an input iterable once. Mapping inputs iterate over their keys; pass
`mapping.values()` or `mapping.items()` when those values are required.

The collection implements iteration, length, membership, integer indexing,
negative indexing, slicing, and reversed iteration. Integer lookup follows
tuple behavior. Slicing returns a new `Collection`.

Operations do not mutate the stored sequence. `all()` returns a new list;
other transformations return new collections or native dictionaries. Items
remain shared references, so callers can still mutate item objects.

Equality uses Python element equality between two `Collection` instances. A
collection does not compare equal to a list or tuple. Hashing always raises
`TypeError`, including when all items are hashable.

`first()`, `last()`, and `get(index)` return a value or raise `IndexError` when
the requested value is absent. An explicit default is returned as-is,
including `None`, `False`, zero, or an empty value. `sole()` returns the only
matching item and raises `ValueError` for zero or multiple matches.

`count()` returns the number of items. `is_empty()` and `is_not_empty()` test
the sequence without changing it. `contains()` uses Python equality.
`search()` returns the first zero-based index or `None`, so index zero remains
distinct from no match. `every()` follows `all()` semantics and returns
`True` for empty input. `some()` follows `any()` and returns `False` for empty
input.

## Transformations and selection

`map()` changes the item type according to its callback. `filter()` and
`reject()` preserve item types and use Python truthiness. `flat_map()` maps
each item to an iterable and concatenates the returned iterables. It treats a
returned string as an iterable of characters. `flatten()` delegates nested
mapping and sequence traversal to `Support.Arr.flatten()`.

`pluck()` accepts a direct or dotted mapping path and uses `Support.Arr.get()`.
A missing field produces `None`, matching the existing Support contract. Use
`map()` for callback-based extraction. `each()` calls a synchronous callback
in source order and returns the same collection. Support's `Tappable` powers
`tap()`. `pipe()` returns the callback result.

`take()` and `skip()` accept non-negative counts. `slice()` and `__getitem__`
use Python slice semantics, including negative endpoints and steps. `chunk()`
requires a positive size and includes a final shorter chunk. `partition()`
returns matching items followed by the remaining items. `reverse()`,
`enumerate()`, and `zip()` preserve source order. `zip()` truncates at the
shortest input.

`unique()` keeps the first equal item. It supports unhashable values by using
equality comparisons when hashing is unavailable. `difference()`,
`intersection()`, and `union()` implement ordered set behavior: outputs contain
no duplicates and retain first-seen order. `concat()` appends input iterables
and preserves duplicates. A `merge()` alias is omitted because sequence
concatenation uses `concat()` and mapping merge behavior belongs to `dict`.

## Ordering, grouping, and aggregation

`sort()` uses Python's stable ordering. `sort_by()` accepts a callback or a
direct or dotted mapping path. Python raises `TypeError` when selected values
cannot be compared.

`group_by()`, `key_by()`, and `count_by()` accept callbacks that return
hashable keys. `group_by()` returns `dict[K, Collection[T]]`. `key_by()` returns
`dict[K, T]`, and later duplicate keys replace earlier values. `count_by()`
returns native dictionary counts. Mapping paths can be read inside a callback
with `Support.Arr.get()`.

`reduce()` requires an initial value and applies its callback from left to
right. `sum()` delegates to Python's built-in operation and is typed for
`int`, `float`, and `complex` values. `min()` and `max()` use Python ordering
and raise `ValueError` for empty input. `average()` returns a float through
`statistics.fmean()`. `median()` delegates to `statistics.median()` and may
retain the full input. Average and median raise `statistics.StatisticsError`
for empty input. Native operation and callback exceptions propagate.

## Lazy behavior

`LazyCollection` stores an iterator factory and does not cache results. A
source that implements `Iterator` is one-shot. Other iterables are requested
again through their `__iter__` method for each traversal. `is_replayable`
reports this distinction. Derived pipelines preserve the source's
replayability; each replay calls pipeline callbacks again.

`map()`, `filter()`, `reject()`, `flat_map()`, `take()`, `skip()`,
`take_while()`, `skip_while()`, `chunk()`, `enumerate()`, `zip()`, and
`concat()` compose iterator operations. Pipeline construction does not call
the source or callbacks. `take(n)` consumes at most `n` source items when the
pipeline is iterated. `chunk(n)` stores at most `n` items per emitted eager
chunk. Python's `take_while()` consumes the first item that fails its
predicate.

`collect()` explicitly materializes the remaining items into a `Collection`.
`first()`, `last()`, `count()`, `reduce()`, `sum()`, `average()`, `min()`,
`max()`, and `median()` are terminal operations. `first()`, `count()`,
`reduce()`, `sum()`, `average()`, `min()`, and `max()` can process values
incrementally. `last()` keeps one candidate while traversing the full source.
`median()` materializes values for Python's calculation. Infinite sources need
a finite operation such as `take()` before materialization or a full traversal.

Calling `first()` on a one-shot source consumes the returned item. The next
traversal begins at the following item. Calling `collect()` or `count()` on a
one-shot source exhausts it. Repeated traversal never silently rebuilds or
caches that source.

## Errors and memory

Callbacks run synchronously and their exceptions propagate. `each()` rejects
awaitable callbacks through the shared Support tap helper. Invalid counts and
chunk sizes raise `ValueError`. Empty lazy `first()` and `last()` calls raise
`IndexError` unless the caller supplies a default.

Eager construction and transformations use memory proportional to their
output. Lazy mapping, filtering, taking, skipping, zipping, and concatenation
remain incremental. Sorting, grouping, set operations, and median retain data
proportional to their input. The component does not provide lazy uniqueness,
sorting, global grouping, asynchronous iteration, dataframe operations, or
parallel execution.

The classes do not create threads, processes, tasks, event loops, or
background work. They do not claim that arbitrary source iterators are
thread-safe. Async stream processing belongs to Concurrency and Streaming.
Collections do not register services or change Application, Container,
Foundation, or Support contracts.

## Evidence

Behavior is covered by `tests/unit/collections/`. Support interoperability
uses real `Fluent` and Support callbacks in `tests/integration/collections/`.
`assert_type()` examples verify transformation pipelines. Informational
comparisons and peak-memory measurements live in
`benchmarks/test_collections.py`.
