---
title: "Lazy collections"
---

<span id="lazy-collections"></span>

`LazyCollection` composes iterator operations without caching values. Use
`lazy()` when a pipeline can process items one at a time:

```python
from titanspan.collections import lazy

documents = ["first", "", "second"]

def is_valid(document: str) -> bool:
    """Keep non-empty document text.

    Args:
        document: The source document.

    Returns:
        Whether the document contains text.
    """
    return bool(document)

def transform(document: str) -> str:
    """Normalize one document for the example pipeline.

    Args:
        document: The source document.

    Returns:
        The upper-case document text.
    """
    return document.upper()

batches = (
    lazy(documents)
    .filter(is_valid)
    .map(transform)
    .chunk(100)
)

for batch in batches:
    print(batch.all())
```

The pipeline does not call the source or callbacks until iteration starts.
`map()`, `filter()`, `reject()`, `flat_map()`, `take()`, `skip()`,
`take_while()`, `skip_while()`, `chunk()`, `enumerate()`, `zip()`, and
`concat()` preserve lazy traversal.

## Replayable and one-shot sources

A source that implements `Iterator` is one-shot. Other iterables are requested
again for each traversal. The `is_replayable` property reports this
distinction. Derived pipelines preserve the source's replayability.

Each traversal of a replayable source calls its pipeline callbacks again.
One-shot iterators resume after partial consumption. Collections never cache
an iterator to make a one-shot source replayable.

`take(n)` uses Python's iterator slicing and consumes no more than `n` values
from its source. Use it to bound work on an infinite iterator:

```python
from itertools import count

from titanspan.collections import lazy

prefix = lazy(count()).take(3).collect()
assert prefix.all() == [0, 1, 2]
```

`chunk(n)` buffers at most `n` values for each emitted eager chunk. Other
streaming operations retain only iterator state. `take_while()` consumes the
first value that fails its predicate because Python's `itertools.takewhile`
must inspect that value.

## Materialize and aggregate

`collect()` creates an eager snapshot from the remaining values. `first()`,
`last()`, `count()`, `reduce()`, `sum()`, `average()`, `min()`, `max()`, and
`median()` are terminal operations. They consume one-shot sources. `last()`
retains one value while traversing the source. `median()` materializes the
input for Python's statistics implementation.

Do not call `collect()`, `count()`, or a terminal operation requiring a full
traversal on an unbounded source. Add a finite `take()` first. Errors from the
source and callbacks propagate.

## Memory and limits

Lazy mapping, filtering, taking, skipping, zipping, and concatenation are
incremental. Sorting, global grouping, uniqueness, and asynchronous iteration
are not provided. `Collection` provides eager ordering and grouping. Future
async stream and large-scale processing APIs belong to other components.

The component does not start threads, tasks, processes, or event loops. It
does not claim that user iterators are thread-safe. Benchmarks under
`benchmarks/test_collections.py` compare eager and lazy paths with standard
Python implementations and report memory measurements without fixed targets.
