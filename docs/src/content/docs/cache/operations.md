---
title: "Cache operations"
---

<span id="cache-operations"></span>

The CacheRepository contract defines portable operations. A repository view
selects one named store and can add memoization or tag grouping.

## Expiration and values

Pass TTL as seconds using an integer or finite float, a datetime.timedelta,
or a timezone-aware absolute datetime. None means no expiration. Positive
durations round up to the nearest millisecond. Zero and negative durations
expire immediately. TTLs above ten years, infinity, NaN, and naive datetimes
raise ValueError.

The JSON serializer accepts None, booleans, integers, finite floats, strings,
lists, and string-keyed dictionaries. It rejects custom objects, recursive
containers, non-finite values, and payloads above max_value_bytes. Decoding
never constructs Python classes or executes serialized data.

~~~python
from datetime import UTC, datetime, timedelta

Cache.put("short", "value", ttl=timedelta(minutes=5))
Cache.put(
    "expires-at-midnight",
    {"ready": True},
    ttl=datetime(2027, 1, 1, tzinfo=UTC),
)
Cache.forever("release", "2026.11")
~~~

Each key must be non-empty text, at most 512 UTF-8 bytes, without control
characters. Bulk operations are bounded by max_batch_size. Bulk writes are
not transactional.

## Atomic operations

Memory and Redis provide atomic add-if-absent, integer increment and
decrement, and pull. Redis uses server commands and a small compare-and-delete
script; memory guards each operation with one process-local lock.

~~~python
if Cache.add("tasks:refresh", {"started": True}, ttl=30):
    Cache.increment("tasks:started")

latest = Cache.pull("tasks:refresh")
Cache.flush("memory")
~~~

Failover and Null stores do not claim atomic guarantees. Unsupported
operations raise CacheCapabilityError. Cache.has checks whether a key exists;
it does not infer presence from truthiness. Cache.pull atomically retrieves
and removes a key on memory and Redis.

## Named stores, tags, and memoization

Select a store through Cache.store(name). Tags are supported by memory and
Redis stores. Tag names are sorted and deduplicated; the group identity is
independent of argument order. Each group accepts up to 16 names of at most
128 safe ASCII characters.

~~~python
Cache.store("redis").put("user:42", {"name": "Ada"}, ttl=300)
Cache.tags("users", "profiles").put("user:42", {"name": "Ada"})
Cache.tags("profiles", "users").flush()

memo = Cache.memo("redis")
first = await memo.get_async("user:42")
second = await memo.get_async("user:42")
~~~

Tag flush deletes the group's keys without enumerating application keys.
Redis scans and deletes in bounded batches. Invalidation is not atomic with
concurrent writes. Tags have no separate persistent index to grow without
bound.

Memo repositories retain successful reads in the current ContextVar scope.
Values are isolated by application, fake substitution, and backend
generation. A mutation clears the active memo view. The memo map is bounded
to 1,000 entries and clears when it reaches that limit. Use it within one
request or another existing execution scope; it does not define a new
scope-management system.

## Remember and refresh

remember computes only after a miss and stores the result using the supplied
TTL. remember_async accepts synchronous or asynchronous callbacks. The
backend lock coordinates concurrent factory calls when the selected backend
supports locks. The callback runs once per lock lease while the lease remains
valid. A slow callback can outlive its lease and overlap a later callback.

~~~python
result = await Cache.remember_async(
    "recommendations:42",
    ttl=60,
    callback=load_recommendations,
)
~~~

flexible_async accepts fresh and stale age thresholds in seconds. stale is
the maximum total age, not an extra duration. Fresh values return
immediately. During the stale window, the call returns the old value and
coordinates refresh with a backend lock when available.

~~~python
async with anyio.create_task_group() as tasks:
    summary = await Cache.flexible_async(
        "dashboard:summary",
        fresh=60,
        stale=300,
        callback=load_summary,
        task_group=tasks,
    )
~~~

Deferred refresh work belongs to the caller's AnyIO task group. Without a
task_group, Cache returns a stale value without starting background work.
When the value is older than stale, Cache recalculates in the current call.
If refresh fails during the stale window, the old value remains available.

## Locks

Memory locks coordinate only tasks and threads in one process. Redis locks
use an atomic owner-token lease shared by clients that access the same Redis
server and namespace. Lease expiry can permit another owner while earlier
work is still running. A lease alone cannot guarantee exclusive work after
expiry.

~~~python
with Cache.lock("report:daily", ttl=30).block(5):
    generate_report()

async with Cache.lock("report:daily", ttl=30).block_async(5):
    await generate_report_async()
~~~

Locks support non-blocking acquisition, bounded waits, owner inspection,
owner-checked release, context managers, callback execution, and owner-token
transfer. force_release is an administrative operation that releases any
current owner. It can disrupt active work and should be restricted by
application policy. Lock operations are never routed through a failover
store. Cache.flush_locks() clears leases only under the selected application's
store prefix. Redis scans and deletes in bounded batches, so clearing is not
atomic and can partially complete after a connection failure. This operation
can invalidate a live owner's lease and admit overlapping work.

~~~python
await Cache.flush_locks_async("redis")
~~~

## Events and maintenance

CacheEvent contains only action, store name, and success status. Actions
include hit, miss, write, removal, clear, failure, lock lifecycle, and
failover. Events never contain cache keys or values. Disable events for the
whole component or for an individual store.

Cache.status and Cache.status_async report driver names, capabilities, and
supported aggregate statistics. They omit credentials, connection strings,
keys, and cached values.

Register cache commands through the existing CommandRegistrar contract by
calling register_cache_commands(registrar). This adds cache:clear,
cache:forget, and cache:status without changing Console's command engine.
The clear command targets only the default application's namespace.
