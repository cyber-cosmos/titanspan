---
title: "Cache configuration"
---

<span id="cache-configuration"></span>

Cache reads settings from the canonical Config repository under the cache
namespace. Each application receives a separate CacheManager.

## Configure named stores

~~~python
application = Application(
    config={
        "app": {"name": "storefront"},
        "cache": {
            "default": "memory",
            "prefix": "titanspan",
            "max_batch_size": 1000,
            "max_value_bytes": 1_000_000,
            "events": True,
            "stores": {
                "memory": {
                    "driver": "memory",
                    "options": {"max_items": 10_000},
                },
                "redis": {
                    "driver": "redis",
                    "options": {
                        "host": "127.0.0.1",
                        "port": 6379,
                        "db": 0,
                        "socket_timeout": 2,
                        "socket_connect_timeout": 2,
                        "max_connections": 50,
                    },
                    "events": False,
                },
                "disabled": {"driver": "null"},
            },
        },
    },
    service_providers=(CacheServiceProvider(),),
)
~~~

The namespace defaults to app.name, or to titanspan if the application does
not define a name. The prefix defaults to titanspan. Store names, namespace,
and prefix accept bounded ASCII letters, digits, hyphens, underscores, and
periods. Names must start with a letter or digit.

All store keys include the configured prefix and application namespace.
Cache.flush clears only that store namespace. It never flushes an entire
Redis database.

## Redis options

Install the package's redis extra to enable the Redis driver. The optional
redis-py integration is imported only when a Redis store is first used.
Accepted options are url, host, port, db, username, password, ssl,
socket_timeout, socket_connect_timeout, and max_connections. Use either url
or host and port. Credentials stay in application configuration and are not
rendered by Cache diagnostics.

Connection and socket timeouts are bounded to 60 seconds. The connection
pool has a positive configured maximum. Connection creation is lazy, and
application shutdown closes both sync and async clients.

~~~python
application = Application(
    config={
        "cache": {
            "default": "redis",
            "stores": {
                "redis": {
                    "driver": "redis",
                    "options": {
                        "url": "rediss://cache.internal:6379/0",
                        "username": "cache-user",
                        "password": read_secret("CACHE_PASSWORD"),
                        "socket_timeout": 2,
                        "socket_connect_timeout": 2,
                        "max_connections": 50,
                    },
                },
            },
        },
    },
    service_providers=(CacheServiceProvider(),),
)
~~~

Load credentials from a secret source. Do not commit credentials or put them
in examples, status output, events, or logs.

## Failover

Failover stores use an ordered list of configured child store names. The
children must be unique, non-failover stores with safe scoped clearing.

~~~python
"cache": {
    "default": "resilient",
    "stores": {
        "redis": {"driver": "redis", "options": {"url": redis_url}},
        "memory": {"driver": "memory"},
        "resilient": {
            "driver": "failover",
            "options": {"stores": ["redis", "memory"]},
        },
    },
}
~~~

Reads continue after misses and backend errors. Writes go to the first store
that accepts them. A write is not replicated. If Redis later recovers, values
written only to memory are not copied back. Failover emits a metadata-only
event. Atomic operations, tags, and locks are not available through a
failover store.

## Extend a driver

Trusted driver factories receive immutable CacheStoreConfiguration and
return a CacheStore. Register a driver with CacheServiceProvider before
resolving stores.

~~~python
from titanspan.cache import (
    CacheServiceProvider,
    CacheStoreConfiguration,
)
from titanspan.contracts.cache import CacheStore

def create_custom_store(
    configuration: CacheStoreConfiguration,
) -> CacheStore:
    """Create a trusted application cache store."""
    return MyStore(configuration.options)

provider = CacheServiceProvider(
    drivers={"custom": create_custom_store},
)
~~~

Custom drivers must implement the complete CacheStore contract and advertise
truthful CacheCapabilities. Add PrefixClearStore, TaggableCacheStore, or
LockStore support only when the backend provides those guarantees.
