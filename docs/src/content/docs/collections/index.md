---
title: "Collections"
---

<span id="collections"></span>

Collections provides eager and lazy transformations for ordinary Python
iterables. The API uses Python's iteration, equality, ordering, and exception
semantics.

```python
from titanspan.collections import collect

names = (
    collect(["ada", "lin", "ada"])
    .map(str.title)
    .unique()
    .sort()
    .all()
)
```

## Installation

Collections is included in Titanspan and adds no runtime dependencies. Use
the [installation guide](/titanspan/getting-started/installation) to set up a checkout
with the locked project dependencies.

## Choose a collection

- Use `Collection` when you need a shallow snapshot and repeated access.
- Use `LazyCollection` when you want to process values as an iterator.
- Use native lists, tuples, sets, and dictionaries for direct operations that
  already express the required behavior.

Collections does not require an Application or Container. It can run in
scripts, tests, and application code without starting framework services.

## Guides

- [Eager collections](/titanspan/collections/eager/): sequence behavior, transformations, and
  selection.
- [Grouping and aggregation](/titanspan/collections/operations/): ordering, native mappings,
  callbacks, errors, and typing.
- [Lazy collections](/titanspan/collections/lazy/): iterator ownership, bounded processing, and
  materialization.
- [Behavioral specification](/titanspan/specifications/collections): complete public
  semantics and implementation limits.

Benchmarks compare representative pipelines with standard-library
implementations. They report measurements without imposing shared-runner
thresholds.
