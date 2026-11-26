"""Define native errors raised while registering and dispatching routes.

Messages identify routing metadata without exposing internal services.
"""


class RoutingError(RuntimeError):
    """Represent a failure in native route registration or dispatch.

    Applications can catch this base class for routing-specific handling.
    """


class InvalidRouteError(RoutingError, ValueError):
    """Report an invalid path, action, or route constraint.

    The rejected route value is omitted from messages when it may be sensitive.
    """


class DuplicateRouteError(InvalidRouteError):
    """Report conflicting methods or duplicate names in one application.

    Route names and method/path pairs are unique within a route collection.
    """


class RouteNotFoundError(RoutingError, LookupError):
    """Report a route lookup or URL-generation failure.

    The message identifies the requested route name or missing parameter.
    """


class RouteUrlError(RoutingError, ValueError):
    """Report unsafe origins or invalid named-route URL parameters.

    Absolute generation requires an explicitly configured trusted origin.
    """


class RoutingContextError(RoutingError):
    """Report route helper use outside an active app or request scope.

    Bind an Application context before using route-aware helpers.
    """


class RouterFrozenError(RoutingError):
    """Report route mutation after application startup has compiled routes.

    Register routes during application composition, before serving requests.
    """


class EndpointResponseError(RoutingError, TypeError):
    """Report endpoint values that cannot be normalized to an HTTP response.

    Return a native HTTP response or a supported JSON, text, or byte value.
    """


__all__ = [
    "DuplicateRouteError",
    "EndpointResponseError",
    "InvalidRouteError",
    "RouteNotFoundError",
    "RouteUrlError",
    "RouterFrozenError",
    "RoutingContextError",
    "RoutingError",
]
