"""Expose shared configuration contracts owned by Titanspan.

Configuration services import their canonical protocol from this package.
"""

from titanspan.contracts.config.capabilities import (
    ConfigDiagnostics,
    ConfigMacroRegistry,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.contracts.config.repository import (
    ConfigArray,
    ConfigKeySequence,
    ConfigReader,
    ConfigRepository,
    ConfigWriter,
)

__all__ = [
    "ConfigArray",
    "ConfigDiagnostics",
    "ConfigKeySequence",
    "ConfigMacroRegistry",
    "ConfigReader",
    "ConfigRepository",
    "ConfigWriter",
    "ScopedConfigOverrides",
    "TypedConfigReader",
]
