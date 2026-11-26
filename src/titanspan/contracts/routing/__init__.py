"""Expose dependency-independent routing contracts and handler types.

Concrete route definitions and matching adapters remain in the routing
component.
"""

from titanspan.contracts.routing.catalog import RouteCatalog, RouteInfo
from titanspan.contracts.routing.types import (
    ControllerAction,
    RouteAction,
    RouteBindingCallback,
    RouteEndpoint,
)
from titanspan.contracts.routing.url_generator import UriUrlGenerator

__all__ = [
    "ControllerAction",
    "RouteAction",
    "RouteBindingCallback",
    "RouteCatalog",
    "RouteEndpoint",
    "RouteInfo",
    "UriUrlGenerator",
]
