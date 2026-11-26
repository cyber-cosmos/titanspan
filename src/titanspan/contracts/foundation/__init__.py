"""Expose dependency-independent application lifecycle contracts.

The package exports service provider protocols without importing concrete
application or infrastructure implementations.
"""

from titanspan.contracts.foundation.lifecycle import (
    ApplicationExceptionHandler,
    ApplicationLifecycleCallback,
)
from titanspan.contracts.foundation.service_provider import (
    BootableServiceProvider,
    ServiceProvider,
)

__all__ = [
    "ApplicationExceptionHandler",
    "ApplicationLifecycleCallback",
    "BootableServiceProvider",
    "ServiceProvider",
]
