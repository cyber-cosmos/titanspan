"""Expose Titanspan's native Cache configuration and manager.
"""  # fmt: skip

from titanspan.cache.configuration import (
    CacheConfiguration,
    CacheStoreConfiguration,
)
from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheCapabilityError,
    CacheConfigurationError,
    CacheError,
    CacheKeyError,
    CacheLockTimeoutError,
    CacheSerializationError,
)
from titanspan.cache.lock import Lock
from titanspan.cache.manager import CacheDriverFactory, CacheFake, CacheManager
from titanspan.cache.repository import MemoRepository, Repository
from titanspan.cache.service_provider import CacheServiceProvider
from titanspan.contracts.cache import (
    CacheCapabilities,
    CacheLock,
    CacheRepository,
    CacheStore,
    CacheTTL,
    LockClearStore,
    PrefixClearStore,
    TaggableCacheStore,
)

__all__ = [
    "CacheBackendError",
    "CacheCapabilities",
    "CacheCapabilityError",
    "CacheConfiguration",
    "CacheConfigurationError",
    "CacheDriverFactory",
    "CacheError",
    "CacheFake",
    "CacheKeyError",
    "CacheLock",
    "CacheLockTimeoutError",
    "CacheManager",
    "CacheRepository",
    "CacheSerializationError",
    "CacheServiceProvider",
    "CacheStore",
    "CacheStoreConfiguration",
    "CacheTTL",
    "Lock",
    "LockClearStore",
    "MemoRepository",
    "PrefixClearStore",
    "Repository",
    "TaggableCacheStore",
]
