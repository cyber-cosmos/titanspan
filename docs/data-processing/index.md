# Data processing

Data processing pipelines and large dataset processing are planned. The
Collections component supports lazy iteration over ordinary Python iterables.
It does not provide dataframe operations, async streams, or distributed
processing.

The current component uses standard-library iterators and documents its
materialization boundaries in [Collections](/collections/). See the
[architecture guide](https://github.com/titanspan/titanspan/blob/main/ARCHITECTURE.md#async-first-behavior)
and [roadmap](https://github.com/titanspan/titanspan/blob/main/ROADMAP.md)
for planned data and streaming capabilities.
