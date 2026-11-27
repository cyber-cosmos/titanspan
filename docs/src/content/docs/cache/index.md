---
title: "Cache"
---

<span id="cache"></span>

Cache provides application-owned named stores through one native repository.
The memory store is ready by default. Redis adds persistent shared storage
when its optional integration is installed.

## Use Cache

~~~python
from titanspan.facades.cache import Cache
from titanspan.foundation import Application

application = Application(
    config={
        "app": {"name": "storefront"},
        "cache": {"default": "memory"},
    },
)

async def get_catalog() -> dict[str, object]:
    """Return a shared catalog summary."""
    return await Cache.remember_async(
        "catalog:summary",
        ttl=300,
        callback=lambda: {"items": 42},
    )
~~~

Foundation registers one CacheServiceProvider and binds its CacheManager and
CacheRepository in the application Container. The Cache facade and injected
repository resolve the same application-owned services. Stores open lazily
and close during application shutdown. Supply a CacheServiceProvider when
registering trusted custom drivers.

Use CacheRepository for constructor injection:

~~~python
from titanspan.contracts.cache import CacheRepository

class CatalogService:
    """Read cached catalog values."""

    def __init__(self, cache: CacheRepository) -> None:
        """Retain the repository resolved by the application Container."""
        self._cache = cache
~~~

## Read and write values

Methods are synchronous for local work and expose explicit async variants
for backend I/O. Never call a synchronous Redis method on an event loop.

~~~python
value = Cache.get("profile:42", default={"active": False})
Cache.put("profile:42", {"active": True}, ttl=60)
Cache.forever("catalog:version", 3)
Cache.add("jobs:daily", 1, ttl=3600)

found = Cache.has("profile:42")
absent = Cache.missing("profile:43")
values = Cache.many(["profile:42", "profile:43"], default=None)

async def update_profile() -> None:
    """Write and read through the asynchronous Redis or memory API."""
    await Cache.put_async("profile:42", {"active": True}, ttl=60)
    cached = await Cache.get_async("profile:42")
    assert cached == {"active": True}
~~~

Cache recognizes missing values separately from cached None, False, zero,
empty strings, lists, and mappings. A default callable runs only after a
miss. Async retrieval accepts synchronous or asynchronous default callables.

See [Configuration](/framework/cache/configuration/) for store selection and
[Operations](/framework/cache/operations/) for expiration, locks, and
invalidation.

## Application caching and Config

Cache stores application data. Config's internal snapshot cache retains
configuration parsing results and has a separate owner and lifecycle.
Clearing a Cache store never clears Config snapshots.

The [Cache specification](/framework/specifications/cache/) defines
contracts, guarantees, error behavior, and current integration boundaries.
