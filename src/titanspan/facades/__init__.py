"""Expose shared facade infrastructure and service entrypoints.

The facade base resolves services through the active application container;
component facades retain explicit, statically discoverable methods.
"""

from titanspan.facades.base import Facade
from titanspan.facades.config import Config
from titanspan.facades.http import Http
from titanspan.facades.log import Log

__all__ = ["Config", "Facade", "Http", "Log"]
