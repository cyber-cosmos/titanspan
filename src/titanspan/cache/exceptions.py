"""Define failures raised by the native Cache component.

Errors avoid including cache payloads and connection credentials.
"""


class CacheError(RuntimeError):
    """Report a cache operation or configuration failure.
    """  # fmt: skip


class CacheConfigurationError(CacheError):
    """Report invalid or incomplete cache configuration.
    """  # fmt: skip


class CacheBackendError(CacheError):
    """Report a backend failure without exposing its private payload.
    """  # fmt: skip


class CacheSerializationError(CacheError):
    """Report a value that violates the configured safe format.
    """  # fmt: skip


class CacheKeyError(CacheError, ValueError):
    """Report an invalid or oversized cache key or namespace.
    """  # fmt: skip


class CacheCapabilityError(CacheError):
    """Report an operation unsupported by the selected store.
    """  # fmt: skip


class CacheLockTimeoutError(CacheError, TimeoutError):
    """Report that bounded lock acquisition exceeded its wait duration.
    """  # fmt: skip


__all__ = [
    "CacheBackendError",
    "CacheCapabilityError",
    "CacheConfigurationError",
    "CacheError",
    "CacheKeyError",
    "CacheLockTimeoutError",
    "CacheSerializationError",
]
