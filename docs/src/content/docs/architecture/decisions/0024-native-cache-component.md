---
title: "ADR 0024: Native Cache component and backend ownership"
---

<span id="adr-0024-native-cache-component"></span>

- Status: Accepted
- Date: 2026-11-27

## Context

Cache is shared application infrastructure. It needs one safe API across
in-process and optional distributed stores, with explicit ownership,
capabilities, serialization, and asynchronous behavior. Backends should
provide storage mechanics without becoming the application-facing API.

## Decision

- Bind one `CacheManager` and default `CacheRepository` per application.
- Register the Cache provider as a Foundation built-in while allowing one
  application provider to supply trusted custom drivers.
- Delegate bounded local expiry and eviction to cachetools. Guard its
  non-thread-safe collection with a store-owned lock.
- Use optional redis-py synchronous and asynchronous clients for Redis.
  Namespace every key, use bounded connection pools, and close both clients
  through application resource ownership.
- Serialize values as bounded JSON built from safe Python primitives. Do not
  reconstruct arbitrary Python classes or accept pickle from cache data.
- Express backend guarantees through capabilities and optional structural
  contracts. Reject atomic, tag, lock, or clear operations unsupported by a
  selected backend.
- Scope data and lock clearing to one application store prefix. Redis scans
  and deletes in batches; clearing is not an atomic snapshot.
- Require caller-owned AnyIO task groups for deferred stale-value refresh.
  Cache does not create unmanaged refresh tasks.

Cashews was evaluated but is not selected as the Cache adapter. Its async-only
public API does not provide Titanspan's synchronous surface. Its Redis store
uses pickle by default and its default clear operation can flush a whole
database. Adapting those policies would add ownership and serialization
layers instead of keeping the backend boundary thin.

## Consequences

Applications use Titanspan contracts, repositories, the Cache facade,
configuration, events, commands, and fakes. Memory stores coordinate only
within one process. Redis leases use atomic owner tokens, but expiry can
permit overlapping work. Redis tag and namespace clearing are bounded scans
and are not atomic with concurrent writes.

The optional Redis dependency stays outside the base installation. Filesystem
and Memcached adapters are excluded until an established dependency meets the
required expiration, atomicity, locking, and namespace guarantees. Database
and DynamoDB adapters remain future integrations.

## Verification

Unit and property tests cover serialization, expiration, backend capabilities,
fake substitution, failover behavior, lock ownership, and concurrent access.
Application integration tests verify provider registration, service
identity, Events, Console, and resource cleanup. Redis integration tests use
an isolated local `redis-server` when available.
