"""Expose Titanspan's native route registration and URL services.

FastAPI and Starlette are private matching and ASGI implementation details.
"""

from titanspan.routing.exceptions import (
    DuplicateRouteError,
    EndpointResponseError,
    InvalidRouteError,
    RouteBindingNotFoundError,
    RouteCacheError,
    RouteDiscoveryError,
    RouteNotFoundError,
    RouterFrozenError,
    RouteUrlError,
    RoutingContextError,
    RoutingError,
    StaleRouteCacheError,
    UnsupportedRouteCacheError,
)
from titanspan.routing.resource_registrar import ResourceRegistrar
from titanspan.routing.route import RouteDefinition, RouteMetadata
from titanspan.routing.route_cache import RouteCache, RouteCacheEntry
from titanspan.routing.route_collection import RouteCollection, RouteFilter
from titanspan.routing.route_group import RouteGroupBuilder
from titanspan.routing.router import Router
from titanspan.routing.service_provider import RoutingServiceProvider
from titanspan.routing.url_generator import UrlGenerator

__all__ = [
    "DuplicateRouteError",
    "EndpointResponseError",
    "InvalidRouteError",
    "ResourceRegistrar",
    "RouteBindingNotFoundError",
    "RouteCache",
    "RouteCacheEntry",
    "RouteCacheError",
    "RouteCollection",
    "RouteDefinition",
    "RouteDiscoveryError",
    "RouteFilter",
    "RouteGroupBuilder",
    "RouteMetadata",
    "RouteNotFoundError",
    "RouteUrlError",
    "Router",
    "RouterFrozenError",
    "RoutingContextError",
    "RoutingError",
    "RoutingServiceProvider",
    "StaleRouteCacheError",
    "UnsupportedRouteCacheError",
    "UrlGenerator",
]
