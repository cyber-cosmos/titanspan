---
title: "Cache component specification"
---

<span id="cache-component-specification"></span>

Cache owns an expressive application API over established local and Redis
storage libraries. Backends implement a byte-oriented CacheStore contract.
The Repository adds safe serialization, key validation, expiration
normalization, events, and higher-level operations.

## Capability inventory

| Capability area | Status | Titanspan behavior |
| --- | --- | --- |
| Manager, repository, store, facade, provider | Implemented | One manager per application and canonical Container identity |
| Retrieval and fallback | Implemented | Missing sentinel at backend boundary; lazy sync and async defaults |
| Writes and indefinite values | Implemented | JSON values with seconds, timedelta, aware datetime, or no TTL |
| Atomic add, counters, pull | Implemented | Memory and Redis only; failover and null reject the capability |
| Bulk retrieval and writes | Implemented | Bounded batches; not transactional |
| Namespaces and safe clearing | Implemented | App prefix on all data keys; no database-wide flush |
| Remember and stampede protection | Implemented | Sync and async factories; lease coordination where supported |
| Stale refresh | Implemented with boundary | Async-only; caller-owned task group required for deferred refresh |
| Tags | Implemented with boundary | Memory and Redis; canonical hashed groups; invalidation can race writes |
| Memoized repository | Implemented | ContextVar execution scope, app/fake/generation isolation, bounded entries |
| Lock contracts and leases | Implemented | Memory local lease; Redis owner-token lease; expiry limits exclusivity |
| Store-scoped lock clearing | Implemented with boundary | Memory clears its owned store; Redis scans and batch-deletes its prefix; operation is not atomic |
| Null backend | Implemented | Explicit no-storage behavior |
| Failover | Implemented with boundary | Ordered portable reads/writes; no replication or atomic coordination |
| Redis backend | Implemented as optional integration | Sync and async clients, bounded pools, lazy ownership, safe close |
| Custom backend | Implemented | Trusted provider factory and explicit capability contracts |
| Filesystem and Memcached | Excluded | No selected dependency offers required semantics without a new adapter |
| Database and DynamoDB | Deferred | Depend on future persistence components |
| Cache warming metadata | Excluded | No public warmth tuple or separate freshness state |
| Per-key tags administration | Excluded | Only scoped group invalidation is exposed |
| Cross-store lock flush | Excluded | Lock clearing cannot target an independent failover chain safely |
| Decorator key generation | Excluded | Callers choose explicit keys; no implicit function argument encoding |

## Contracts and application ownership

CacheStore performs byte-oriented get, set, add, pull, delete, clear,
increment, touch, lock, lifecycle, and async equivalents. CacheRepository
defines portable public operations. CacheCapabilities state which operations
are truly atomic, whether tags and scoped clear exist, and whether locks
coordinate across processes. PrefixClearStore, TaggableCacheStore, and
LockStore express optional backend guarantees.

Foundation registers CacheServiceProvider as a built-in while allowing one
explicit provider to supply custom drivers. The provider binds CacheManager
and CacheRepository through the existing application Container. It reads
ConfigRepository and Events contracts. The manager constructs stores on
first use and closes all created stores during application shutdown.

The Cache facade, injected CacheRepository, and direct CacheManager views
resolve repositories from that same manager. No process-global production
registry exists.

## Public behavior

Cache exposes sync and async forms for I/O-capable operations: get, put,
forever, add, has, missing, many, put_many, pull, forget, flush, increment,
decrement, remember, remember_forever, touch, status, and named store
selection. Cache.flexible_async and lock's explicit sync/async methods cover
coordinated refresh and leases.

Cached None, False, zero, empty values, and missing keys remain distinct.
Defaults resolve only after misses. Pull is atomic on memory and Redis.
Bulk writes and deletes are bounded but are not transactions. Unsupported
capabilities raise CacheCapabilityError instead of using a read/write
emulation.

TTL accepts seconds, timedelta, timezone-aware absolute datetime, or None.
Positive values round upward to milliseconds. Zero and negative values
expire immediately. Invalid, non-finite, naive, or over-ten-year values
raise ValueError.

Keys are non-empty UTF-8 text up to 512 bytes and cannot contain control
characters. Bulk operations default to at most 1,000 keys. Configuration may
select a lower or higher positive bound.

## Serialization and security

Only None, booleans, integers, finite floats, strings, lists, and mappings
with string keys can be stored. JSON serialization is bounded by a default
one-megabyte value limit, 64 nesting levels, and 100,000 visited nodes. The
decoder never imports classes or executes object reconstruction hooks.

Configuration names use validated ASCII characters. All data and lock keys
include an application namespace and configured prefix. Redis clear scans
only the exact store namespace and deletes bounded batches. It never issues
FLUSHDB or FLUSHALL. Diagnostics and CacheEvent do not include keys,
payloads, passwords, or connection URLs.

Redis connection and socket timeouts are bounded at 60 seconds. Its client
pool maximum is configurable and positive. Backend errors become safe native
CacheBackendError exceptions; cancellation propagates through async
operations.

## Expiration, storage, and dependencies

The memory adapter uses cachetools' TLRU collection for bounded expiration
and eviction, protected by Titanspan's RLock. This adapter is process-local.
cachetools is the MIT-licensed base dependency.

The optional Redis adapter uses redis-py's regular and redis.asyncio clients.
It uses JSON bytes, SET NX for atomic add and lock acquisition, Redis integer
commands for counters, and owner comparison for release. Pull uses a small
server script. Redis client resources are created lazily and closed by their
CacheManager. redis-py is MIT-licensed and its supported Python versions
include all current Titanspan versions.

Cashews was selected for evaluation but not added. It provides async caching,
multiple backends, cache decorators, TTLs, tags, transactions, and locking.
Its async-only entry points do not provide the synchronous API required by
Titanspan. Its documented Redis serializer defaults to pickle and requires
additional policy to safely handle untrusted data. It also combines global
setup and backend clear behavior with library-owned lifecycle choices that do
not directly match Titanspan's per-application manager and strict namespace
clearing. This implementation uses the smaller cachetools expiry collection
and redis-py clients behind Titanspan's contracts.

Filesystem and Memcached drivers are not provided. The selected foundations
do not establish all required atomic operations, leases, expiry, and safe
clear behavior as one verified adapter. Database and DynamoDB are deferred
until their owning persistence components can define lifecycle and
configuration integration.

## Locks, flexible values, and memoization

Lock handles use random owner tokens and explicit positive leases. Memory
locks coordinate only within one store process. Redis uses atomic acquisition
and owner-checked release, but a lease can expire while its holder is still
working. Applications must tolerate overlap or use downstream fencing.
force_release is an explicitly administrative, owner-agnostic operation.
Failover stores reject locks to prevent split ownership.

flexible_async treats fresh as the age through which the value is fresh and
stale as its maximum total age. Within fresh, it returns the cached value.
Between fresh and stale, it returns stale and schedules refresh only in a
caller-owned AnyIO TaskGroup. Without a supplied group, no background refresh
is started. Backend locks coordinate the refresh when available. At or past
the stale bound, a synchronous-in-the-call async recomputation occurs.
Refresh failures retain the old value only while it remains within the stale
bound.

MemoRepository caches successful reads in a ContextVar scope. Its values are
separated by application, fake identity, backend, and mutation generation.
Mutations invalidate the active execution memo. The map is bounded to 1,000
entries. Job and workflow memo integration waits for those components.

## Failover and consistency

Reads traverse child stores in priority order until a value is found or all
stores miss. A store failure causes the next child to be tried. Writes target
the first child that accepts them; they are not copied to later children.
If every child fails, the operation raises CacheBackendError. Removal and
clear attempt every configured child and raise on any partial backend
failure. Failover events identify the wrapper store and do not expose child
errors or payloads.

Failover cannot offer atomic add, counters, pull, tags, or locking because
independent stores do not share atomic state. It is a cache availability
policy, not a replication protocol.

## Events, console, and testing

CacheEvent provides action, configured store name, and success. Events cover
hits, misses, writes, removals, clearing, failures, lock lifecycle, and
failover. Per-component and per-store settings disable event dispatch.

register_cache_commands adds cache:clear, cache:forget, and cache:status
through CommandRegistrar. The clear command uses the default repository and
therefore preserves namespace isolation.

Cache.fake provides nested sync and async context managers backed by an
isolated memory store. Existing facade, injected repository, and manager
repository views resolve the fake in the current ContextVar. The production
store is not touched while a store is faked. Assertions cover key presence,
missing keys, and operation records.

## Deferred integrations

Database and DynamoDB drivers wait for their owning persistence components.
File and Memcached drivers remain excluded until an established adapter meets
the required expiration, atomicity, lease, and namespace guarantees.

Function decorator key generation and separate cache warmth metadata are not
part of the current public API. Applications select explicit keys and can
inspect ordinary cached values directly.
