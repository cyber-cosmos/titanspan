"""Expose Titanspan application lifecycle primitives.

The initial implementation coordinates FastAPI startup and Dishka cleanup.
"""

from titanspan.foundation.application import Application
from titanspan.foundation.helpers import app

__all__ = ["Application", "app"]
