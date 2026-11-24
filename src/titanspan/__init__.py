"""Titanspan: an async-first Python framework for intelligent systems."""

from importlib.metadata import version

from titanspan.foundation.application import Application

__version__ = version("titanspan")

__all__ = ["Application", "__version__"]
