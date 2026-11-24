"""Expose Titanspan application lifecycle primitives.

The initial implementation coordinates FastAPI startup and Dishka cleanup.
"""

from titanspan.foundation.application import Application

__all__ = ["Application"]
