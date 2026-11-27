"""Expose shared facade infrastructure and service entrypoints.

The facade base resolves services through the active application container;
component facades retain explicit, statically discoverable methods.
"""

from titanspan.facades.base import Facade
from titanspan.facades.bus import Bus
from titanspan.facades.cache import Cache
from titanspan.facades.config import Config
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.facades.hash import Hash
from titanspan.facades.http import Http
from titanspan.facades.log import Log
from titanspan.facades.queue import Queue
from titanspan.facades.route import Route
from titanspan.facades.storage import Storage
from titanspan.facades.validation import Validation

__all__ = [
    "DB",
    "Bus",
    "Cache",
    "Config",
    "Event",
    "Facade",
    "Hash",
    "Http",
    "Log",
    "Queue",
    "Route",
    "Storage",
    "Validation",
]
