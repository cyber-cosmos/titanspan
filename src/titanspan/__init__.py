"""Expose the small supported Titanspan package API.

The public root exports application construction and installed distribution
metadata; planned framework modules remain unavailable as supported APIs.
"""

from importlib.metadata import version

from titanspan.foundation import Application, ApplicationBuilder, app
from titanspan.routing.helpers import Redirector, redirect, route, url

__version__ = version("titanspan")

__all__ = [
    "Application",
    "ApplicationBuilder",
    "Redirector",
    "__version__",
    "app",
    "redirect",
    "route",
    "url",
]
