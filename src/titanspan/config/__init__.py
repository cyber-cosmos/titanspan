"""Expose validated environment-backed application configuration.

The initial package API exports ``Settings`` and delegates parsing to
Pydantic Settings.
"""

from titanspan.config.settings import Settings

__all__ = ["Settings"]
