---
title: "Cache backends"
---

<span id="cache-backends"></span>

Inspect CacheRepository.capabilities before relying on optional backend
operations. CacheCapabilities reports atomic behavior, tags, scoped clearing,
lock guarantees, and store-scoped lock clearing. Lock clearing is an
administrative operation. Redis uses SCAN and bounded deletes, which can be
partial and are not atomic with concurrent acquisition.

| Store | Expiry | Atomic add / counter / pull | Tags | Locks | Scoped lock clear |
| --- | --- | --- | --- | --- | --- |
| Memory | Bounded process-local TTL | Yes / yes / yes | Yes; local clear | Local lease | Yes |
| Redis | Server TTL | Yes / yes / yes | Yes; SCAN | Owner lease | Yes; SCAN |
| Null | Values discarded | No / no / no | No | No | No |
| Failover | Child store TTL | No / no / no | No | No | No |
| Custom | Driver-defined | Declare accurately | Optional | Optional | Optional |

## Memory

Memory is suitable for local applications and deterministic tests. The
backend uses cachetools' bounded TLRU collection for expiry and eviction.
Titanspan synchronizes its documented non-thread-safe collection. Stores
belong to one application manager and are not shared across processes.

cachetools is an MIT-licensed runtime dependency. It supplies the bounded
expiry/eviction collection; Titanspan owns the cache API, serialization,
namespace, lifecycle, and capability contract.

## Redis

Redis is an optional integration over redis-py. Synchronous methods use the
regular Redis client. Async methods use redis.asyncio and await I/O directly.
Both client variants share the same configured namespace. Redis provides
server-side atomic add, counter updates, pull, and owner-checked lock
release. Namespace clearing and tag invalidation use SCAN followed by
bounded deletes; these operations are not atomic snapshots.

redis-py is MIT-licensed and supports the Python versions required by
Titanspan. Titanspan lazily creates clients, bounds connection pools and
timeouts, and closes both clients with the owning application. Redis data
must be reachable only by trusted application services. The adapter stores
bounded JSON bytes, not arbitrary Python objects.

## Null and failover

Null explicitly disables caching and advertises no atomic capabilities.
Reads always miss, writes are discarded, and status reports the null driver.

Failover reads child stores by priority, continuing on misses and backend
errors. Writes go to the first accepting child. Removal and clear attempt all
children and report partial failures. Failover does not replicate data and
does not route atomic counters, add, pull, tags, or locks.

## Evaluated alternatives

The filesystem backend is not included. The evaluated filesystem cache
dependencies do not provide the full combination of bounded expiry,
cross-process atomic add and counters, atomic pull, owner-checked leases, and
safe namespace clearing required by the portable contract.

Memcached is deferred because it would add another optional protocol adapter
without improving the required local and Redis use cases. Database and
DynamoDB stores depend on future Titanspan persistence integrations.

Cashews was evaluated as an MIT-licensed async cache framework supporting
Python 3.10 and later. It provides memory, Redis, disk cache, tags, and
distributed lock operations. Its async-only public API does not meet
Titanspan's explicit sync and async parity requirement. Its Redis backend
uses pickle by default and clears through a database-wide operation. The
memory backend owns a periodic cleanup task. These behaviors need more
adaptation for safe serialization, application ownership, and namespace-safe
clearing than a thin adapter should own. Titanspan delegates Redis client
behavior to redis-py and bounded local expiry to cachetools.

See the [dependency evaluation and behavior matrix](/titanspan/specifications/cache/)
for the full component inventory.
