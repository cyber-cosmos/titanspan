"""Expose native application construction and lifecycle primitives.

Foundation owns composition, provider boot, and application shutdown.
"""

from titanspan.foundation.application import Application
from titanspan.foundation.builder import ApplicationBuilder
from titanspan.foundation.exceptions import (
    ApplicationLifecycleError,
    ProviderDiscoveryError,
)
from titanspan.foundation.helpers import app

__all__ = [
    "Application",
    "ApplicationBuilder",
    "ApplicationLifecycleError",
    "ProviderDiscoveryError",
    "app",
]
