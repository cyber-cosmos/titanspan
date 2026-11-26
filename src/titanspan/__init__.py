"""Expose application construction and selected native framework services.

Component implementations and configuration remain available from their
owning packages.
"""

from importlib.metadata import version

from titanspan.filesystem import FilesystemServiceProvider
from titanspan.foundation import Application, ApplicationBuilder, app
from titanspan.routing.helpers import Redirector, redirect, route, url

__version__ = version("titanspan")

__all__ = [
    "Application",
    "ApplicationBuilder",
    "FilesystemServiceProvider",
    "Redirector",
    "__version__",
    "app",
    "redirect",
    "route",
    "url",
]
