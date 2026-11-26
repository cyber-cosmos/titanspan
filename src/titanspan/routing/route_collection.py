"""Store one authoritative set of route definitions per application.

Definitions remain mutable only until route compilation at application startup.
"""

from dataclasses import dataclass

from titanspan.contracts.routing import RouteCatalog
from titanspan.routing.exceptions import (
    DuplicateRouteError,
    InvalidRouteError,
    RouteNotFoundError,
    RouterFrozenError,
)
from titanspan.routing.route import RouteDefinition

_DUPLICATE_METHOD_PATH_ERROR = (
    "A route already handles one of these methods and paths."
)
_ROUTE_NOT_IN_COLLECTION_ERROR = (
    "The route definition is not in this collection."
)
_INCOMPLETE_ROUTE_ERROR = "Every registered route must have an endpoint action."
_FROZEN_COLLECTION_ERROR = "Routes are frozen after application startup."
_INVALID_INSPECTION_METHOD_ERROR = "A route inspection method must be valid."
_INVALID_INSPECTION_PROTOCOL_ERROR = (
    "A route inspection protocol must be HTTP or WebSocket."
)
_OPTIONAL_PATH_SUFFIX = "?}"


@dataclass(frozen=True, slots=True)
class RouteFilter:
    """Select route metadata by exact native catalog fields.

    Omitted fields do not restrict results; matching preserves registration
    order and returns the original route definition objects.
    """

    method: str | None = None
    path: str | None = None
    name: str | None = None
    protocol: str | None = None
    domain: str | None = None
    middleware: str | type[object] | None = None

    def __post_init__(self) -> None:
        """Reject invalid protocol and method selectors at construction.

        Raises:
            InvalidRouteError: If a method or protocol selector is malformed.
        """
        if self.method is not None and not self.method.isalpha():
            raise InvalidRouteError(_INVALID_INSPECTION_METHOD_ERROR)
        if self.protocol not in {None, "http", "websocket"}:
            raise InvalidRouteError(_INVALID_INSPECTION_PROTOCOL_ERROR)


class RouteCollection(RouteCatalog):
    """Own route definitions and enforce names and method/path uniqueness.

    Matching, URL generation, route inspection, and OpenAPI compilation read
    from this single collection.
    """

    def __init__(self) -> None:
        """Create an empty mutable collection for one Router instance.

        Routes are ordered by declaration for inspection; the backend receives
        a separate specificity-sorted snapshot when the app starts.
        """
        self._routes: list[RouteDefinition] = []
        self._frozen = False

    def add(self, route: RouteDefinition) -> None:
        """Add one route if its methods do not conflict with existing paths.

        Args:
            route: Route definition owned by the same Router.

        Raises:
            DuplicateRouteError: If a path and method are already registered.
            RouterFrozenError: If the collection has been compiled.
        """
        self._ensure_mutable()
        route_paths = _effective_paths(route.path)
        for existing in self._routes:
            duplicate_methods = set(existing.methods).intersection(
                route.methods,
            )
            if (
                route_paths.intersection(_effective_paths(existing.path))
                and duplicate_methods
            ):
                raise DuplicateRouteError(_DUPLICATE_METHOD_PATH_ERROR)
            if (
                route.route_name is not None
                and existing.route_name == route.route_name
            ):
                message = f"Route name {route.route_name!r} already exists."
                raise DuplicateRouteError(message)
        self._routes.append(route)

    def remove(self, route: RouteDefinition) -> None:
        """Remove one route during resource registrar configuration.

        Args:
            route: Exact route definition previously added to this collection.

        Raises:
            RouterFrozenError: If the collection has been compiled.
            InvalidRouteError: If the route is not part of this collection.
        """
        self._ensure_mutable()
        try:
            self._routes.remove(route)
        except ValueError as error:
            raise InvalidRouteError(_ROUTE_NOT_IN_COLLECTION_ERROR) from error

    def replace_path(
        self,
        route: RouteDefinition,
        path: str,
        parameter_names: dict[str, str | None],
    ) -> None:
        """Update one resource path while preserving its catalog identity.

        Args:
            route: Existing definition whose path should change.
            path: New route path.
            parameter_names: Previous path names mapped to replacements.

        Raises:
            DuplicateRouteError: If another route claims the new method path.
            InvalidRouteError: If the route is not in this collection.
            RouterFrozenError: If application route registration is closed.
        """
        self._ensure_mutable()
        if route not in self._routes:
            raise InvalidRouteError(_ROUTE_NOT_IN_COLLECTION_ERROR)
        route_paths = _effective_paths(path)
        for existing in self._routes:
            if existing is route or not route_paths.intersection(
                _effective_paths(existing.path),
            ):
                continue
            if set(existing.methods).intersection(route.methods):
                raise DuplicateRouteError(_DUPLICATE_METHOD_PATH_ERROR)
        # RouteDefinition keeps this mutation private; the canonical collection
        # validates collisions first and preserves the existing route identity.
        route._set_path(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            path,
            parameter_names,
        )

    def all(self) -> tuple[RouteDefinition, ...]:
        """Return an immutable snapshot in declaration order.

        Returns:
            Route definitions registered by this application.
        """
        return tuple(self._routes)

    def inspect(
        self,
        filters: RouteFilter | None = None,
    ) -> tuple[RouteDefinition, ...]:
        """Return matching definitions in registration order.

        Args:
            filters: Exact metadata selectors, or an empty filter.

        Returns:
            Original route definitions matching every selected field.
        """
        selected = RouteFilter() if filters is None else filters
        domain = (
            None
            if selected.domain is None
            else selected.domain.lower().rstrip(".")
        )
        method = None if selected.method is None else selected.method.upper()
        return tuple(
            route
            for route in self._routes
            if (method is None or method in route.methods)
            and (selected.path is None or selected.path == route.path)
            and (selected.name is None or selected.name == route.route_name)
            and (
                selected.protocol is None or selected.protocol == route.protocol
            )
            and (domain is None or domain == route.domain_name)
            and (
                selected.middleware is None
                or selected.middleware in route.middleware_types
            )
        )

    def named(self, name: str) -> RouteDefinition:
        """Return the route registered under one unique name.

        Args:
            name: Exact route name selected for lookup.

        Returns:
            The matching route definition.

        Raises:
            RouteNotFoundError: If no route has the requested name.
        """
        for route in self._routes:
            if route.route_name == name:
                return route
        message = f"No route is registered as {name!r}."
        raise RouteNotFoundError(message)

    def has(self, name: str) -> bool:
        """Report whether a route with this name is registered.

        Args:
            name: Route name to search for.

        Returns:
            True when a route has the given name.
        """
        return any(route.route_name == name for route in self._routes)

    def validate_name(
        self,
        name: str,
        candidate: RouteDefinition,
    ) -> None:
        """Enforce route-name uniqueness before changing a definition.

        Args:
            name: Candidate fully qualified route name.
            candidate: Route attempting to claim the name.

        Raises:
            DuplicateRouteError: If another route already uses the name.
            RouterFrozenError: If the collection has been compiled.
        """
        self._ensure_mutable()
        if any(
            route is not candidate and route.route_name == name
            for route in self._routes
        ):
            message = f"Route name {name!r} already exists."
            raise DuplicateRouteError(message)

    def freeze(self) -> None:
        """Validate complete definitions and reject later collection changes.

        Raises:
            InvalidRouteError: If a decorator did not supply its endpoint.
        """
        self._ensure_mutable()
        if any(route.action is None for route in self._routes):
            raise InvalidRouteError(_INCOMPLETE_ROUTE_ERROR)
        self._frozen = True

    @property
    def frozen(self) -> bool:
        """Return whether registration has been closed for this collection.

        Returns:
            True after application route compilation.
        """
        return self._frozen

    def _ensure_mutable(self) -> None:
        """Reject writes after the application has compiled route metadata.

        Raises:
            RouterFrozenError: If the collection is no longer mutable.
        """
        if self._frozen:
            raise RouterFrozenError(_FROZEN_COLLECTION_ERROR)


def _effective_paths(path: str) -> frozenset[str]:
    """List canonical and compiled paths for an optional route template.

    Args:
        path: Validated route path template owned by a RouteDefinition.

    Returns:
        The declared path and any backend paths emitted for optional syntax.
    """
    if not path.endswith(_OPTIONAL_PATH_SUFFIX):
        return frozenset({path})
    marker = path.rfind("/{")
    present = path[:-2] + "}"
    absent = path[:marker] or "/"
    return frozenset({path, present, absent})


__all__ = ["RouteCollection", "RouteFilter"]
