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


class RouteBindingNotFoundError(RoutingError, LookupError):
    """Report that an explicit path binding found no matching resource.

    The ASGI adapter translates this error to a 404 without exposing the raw
    route parameter or depending on a database exception hierarchy.
    """


class RouteDiscoveryError(RoutingError, ImportError):
    """Report a trusted route module import or registration failure.

    The original import or callback error remains available as the cause.
    """

    def __init__(
        self,
        message: str,
        *,
        source: str | None = None,
    ) -> None:
        """Attach the trusted route module or file to a discovery failure.

        Args:
            message: Stable failure description without source context.
            source: Optional configured module or conventional file identity.
        """
        if source is not None:
            message = f"{message} [{source}]."
        super().__init__(message)


class RouteCacheError(RoutingError):
    """Report an invalid, unsupported, or unreadable route cache file.

    Catch this error when a persisted inspection snapshot cannot be trusted.
    """


class StaleRouteCacheError(RouteCacheError):
    """Report cached route metadata that differs from current registration.

    Recreate the snapshot after the application route catalog changes.
    """


class UnsupportedRouteCacheError(RouteCacheError):
    """Report live route data without safe stable JSON identities.

    Closures and arbitrary objects are deliberately not serialized.
    """


class RouteUrlError(RoutingError, ValueError):
    """Report unsafe origins or invalid named-route URL parameters.

    Absolute generation requires an explicitly configured trusted origin.
    """

    def __init__(
        self,
        message: str,
        *,
        parameter: str | None = None,
    ) -> None:
        """Attach a missing path parameter name to a URL error.

        Args:
            message: Stable reason for rejecting URL generation.
            parameter: Optional path parameter that requires a value.
        """
        if parameter is not None:
            message = f"{message} {parameter!r}."
        super().__init__(message)


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
    "RouteBindingNotFoundError",
    "RouteCacheError",
    "RouteDiscoveryError",
    "RouteNotFoundError",
    "RouteUrlError",
    "RouterFrozenError",
    "RoutingContextError",
    "RoutingError",
    "StaleRouteCacheError",
    "UnsupportedRouteCacheError",
]
