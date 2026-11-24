# Timing and execution utilities

Titanspan provides `Benchmark`, `Lottery`, and `Timebox` for measuring
callables, choosing deterministic or probability-based outcomes, and
enforcing a minimum operation duration. Benchmarking and random draws use
the standard library. The asynchronous timebox uses the framework's AnyIO
dependency for backend-neutral cancellation-aware waiting.

## Benchmark

`Benchmark.measure` accepts one callable, a mapping of named callbacks, or
an iterable of callbacks. It returns an average duration in milliseconds;
mapping keys and iterable order are preserved. Garbage collection runs
before each sample, outside the measured interval.

```python
from titanspan.support import Benchmark

elapsed_ms = Benchmark.measure(lambda: sum(range(1_000)))
measurements = Benchmark.measure(
    {
        "builtin": lambda: sum(range(1_000)),
        "loop": lambda: sum(value for value in range(1_000)),
    },
    iterations=5,
)
```

Use `value` when both the operation result and elapsed duration are needed:

```python
value, elapsed_ms = Benchmark.value(lambda: sum(range(1_000)))
```

`measure_async` and `value_async` explicitly await asynchronous operations.
They run callbacks sequentially and do not start background tasks.

```python
async def load_record() -> str:
    """Load one record from an async application service."""
    return "record"

elapsed_ms = await Benchmark.measure_async(load_record, iterations=3)
```

`Benchmark.dd` writes the measurement to standard output and raises
`SystemExit`, following the dump-and-stop intent of Laravel's method. Use it
only in interactive debugging code.

These measurements are diagnostic observations. They do not replace
reproducible benchmarks, workload controls, or comparisons against native
library baselines.

## Lottery

`Lottery.odds(chances, out_of=None)` creates a lottery. Without `out_of`,
`chances` is a probability from zero through one. With a denominator, it is
the expected number of wins out of the positive integer opportunity count.
`winner` and `loser` callbacks receive arguments passed to the callable
lottery; `choose(times)` performs independent draws.

```python
from titanspan.support import Lottery

result = (
    Lottery.odds(1, 10)
    .winner(lambda: "sampled")
    .loser(lambda: "skipped")
    .choose()
)
```

The default source uses `secrets` for unpredictable draws. Tests and local
deterministic runs can set outcomes with `Lottery.fix` or
`Lottery.forceResultWithSequence`. `Lottery.alwaysWin` and
`Lottery.alwaysLose` can set an outcome for the active execution context;
when passed a callback, the override is restored after that callback even
if it raises.

Result factories are stored in a `ContextVar`, so unrelated execution
contexts do not share mutable process-global test state. A context inherited
by child tasks also inherits its factory. `choose_async` awaits async
callbacks explicitly. Synchronous methods reject awaitable callback results.

For a sparse sequence mapping, the default random fallback advances beyond
the missing index. A caller-supplied `when_missing` callback leaves the
cursor on that missing index, matching Laravel's callback-controlled
fallback behavior.

## Timebox

`Timebox.call` runs a synchronous callback and waits for the remainder of a
minimum duration in microseconds. It does not interrupt callbacks that run
longer than the requested duration and is not a deadline or general timing
attack defense.

```python
from titanspan.support import Timebox

result = Timebox().call(lambda _box: "complete", 10_000)
```

`return_early` allows a callback to skip the remaining wait;
`dont_return_early` restores the minimum wait. The Laravel-compatible
`returnEarly`, `dontReturnEarly`, and `earlyReturn` spellings are available.

Use `call_async` in asynchronous execution paths. It awaits the remaining
duration with [AnyIO sleep](https://anyio.readthedocs.io/en/stable/api.html#anyio.sleep)
without blocking the current task's event loop. Cancellation propagates
immediately and does not wait for the minimum duration.

```python
async def work(_box: Timebox) -> str:
    """Run an asynchronous operation inside a timebox."""
    return "complete"

result = await Timebox().call_async(work, 10_000)
```

Durations and iteration counts must be integer values; booleans and
fractional values are rejected. Durations may be zero or positive, while
iteration counts must be positive.

## Compatibility and tests

The class and method mapping, behavior differences, pinned Laravel source,
and test evidence are recorded in the [compatibility inventory](/compatibility/laravel-support).
Focused tests are in `tests/unit/support/test_benchmark.py`,
`test_lottery.py`, and `test_timebox.py`.
