"""Expose Titanspan's native route registration and URL services.

FastAPI and Starlette are private matching and ASGI implementation details.
"""

from titanspan.routing.exceptions import (
    DuplicateRouteError,
    EndpointResponseError,
    InvalidRouteError,
    RouteNotFoundError,
    RouterFrozenError,
    RouteUrlError,
    RoutingContextError,
    RoutingError,
)
from titanspan.routing.resource_registrar import ResourceRegistrar
from titanspan.routing.route import RouteDefinition, RouteMetadata
from titanspan.routing.route_collection import RouteCollection
from titanspan.routing.route_group import RouteGroupBuilder
from titanspan.routing.router import Router
from titanspan.routing.service_provider import RoutingServiceProvider
from titanspan.routing.url_generator import UrlGenerator

__all__ = [
    "DuplicateRouteError",
    "EndpointResponseError",
    "InvalidRouteError",
    "ResourceRegistrar",
    "RouteCollection",
    "RouteDefinition",
    "RouteGroupBuilder",
    "RouteMetadata",
    "RouteNotFoundError",
    "RouteUrlError",
    "Router",
    "RouterFrozenError",
    "RoutingContextError",
    "RoutingError",
    "RoutingServiceProvider",
    "UrlGenerator",
]
