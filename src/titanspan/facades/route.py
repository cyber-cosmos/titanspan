"""Provide a typed entrypoint to the active application's Router.

Every operation resolves the same route registry used by ASGI dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from titanspan.facades.base import Facade
from titanspan.routing.helpers import current_route, current_route_name
from titanspan.routing.router import Router

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.http import HttpMiddleware
    from titanspan.contracts.routing import (
        RouteAction,
        RouteBindingCallback,
        RouteEndpoint,
    )
    from titanspan.routing.resource_registrar import ResourceRegistrar
    from titanspan.routing.route import RouteDefinition
    from titanspan.routing.route_collection import RouteFilter
    from titanspan.routing.route_group import RouteGroupBuilder


class Route(Facade[Router]):
    """Resolve the application's native route registrar.

    The facade keeps explicit methods for discoverability and never creates a
    global Router.
    """

    service_contract = Router

    @classmethod
    def resolve_from_container(cls, container: ServiceContainer) -> Router:
        """Resolve the application-owned Router through the active registry.

        Args:
            container: Active native service container.

        Returns:
            The Router used to compile incoming ASGI routes.
        """
        return container.make(Router)

    @classmethod
    @overload
    def route(
        cls,
        path: str,
        action: RouteAction,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> RouteDefinition:
        """Register a route action directly through the active Router.

        The overload preserves the endpoint's declared callable type.
        """

    @classmethod
    @overload
    def route(
        cls,
        path: str,
        action: None = None,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator that registers one route action.

        The original function object remains unchanged.
        """

    @classmethod
    def route(
        cls,
        path: str,
        action: RouteAction | None = None,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a native route or return its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.
            methods: Explicit HTTP method sequence.
            name: Optional route name for URL generation.

        Returns:
            Route definition, or decorator when action is omitted.
        """
        return cls.router().route(
            path,
            action,
            methods=methods,
            name=name,
        )

    @classmethod
    def router(cls) -> Router:
        """Return the active application's canonical Router service.

        Returns:
            The object used by Foundation for ASGI route compilation.
        """
        return cls.resolve_service()

    @classmethod
    @overload
    def get(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a GET decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def get(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a GET endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def get(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a GET route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("GET",))

    @classmethod
    @overload
    def post(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a POST decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def post(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a POST endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def post(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a POST route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("POST",))

    @classmethod
    @overload
    def put(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a PUT decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def put(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a PUT endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def put(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a PUT route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("PUT",))

    @classmethod
    @overload
    def patch(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a PATCH decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def patch(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a PATCH endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def patch(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a PATCH route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("PATCH",))

    @classmethod
    @overload
    def delete(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a DELETE decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def delete(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a DELETE endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def delete(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a DELETE route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("DELETE",))

    @classmethod
    @overload
    def head(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a HEAD decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def head(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register a HEAD endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def head(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a HEAD route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("HEAD",))

    @classmethod
    @overload
    def options(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return an OPTIONS decorator when no endpoint is supplied.

        The decorator preserves the declared callable identity.
        """

    @classmethod
    @overload
    def options(cls, path: str, action: RouteAction) -> RouteDefinition:
        """Register an OPTIONS endpoint and return its route definition.

        The return type exposes fluent route metadata methods.
        """

    @classmethod
    def options(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register an OPTIONS route or create its endpoint decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Route definition or endpoint decorator.
        """
        return cls.router().route(path, action, methods=("OPTIONS",))

    @classmethod
    @overload
    def match(
        cls,
        methods: Sequence[str],
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register an endpoint for an explicit method sequence.

        The returned route definition supports metadata configuration.
        """

    @classmethod
    @overload
    def match(
        cls,
        methods: Sequence[str],
        path: str,
        action: None = None,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator for an explicit method sequence.

        The decorated callable is registered without wrapping it.
        """

    @classmethod
    def match(
        cls,
        methods: Sequence[str],
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a route for an explicit method sequence.

        Args:
            methods: HTTP methods accepted by the route.
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            Fluent route definition.
        """
        return cls.router().match(methods, path, action)

    @classmethod
    @overload
    def connect(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a CONNECT endpoint decorator.

        The endpoint retains its original callable identity.
        """

    @classmethod
    @overload
    def connect(
        cls,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register one CONNECT endpoint.

        Direct registration returns the mutable route definition.
        """

    @classmethod
    def connect(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register CONNECT directly or return a decorator.

        Args:
            path: Absolute route path.
            action: Optional callable or controller action.

        Returns:
            A route definition or endpoint decorator.
        """
        if action is None:
            return cls.router().connect(path)
        return cls.router().connect(path, action)

    @classmethod
    @overload
    def trace(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a TRACE endpoint decorator.

        The endpoint retains its original callable identity.
        """

    @classmethod
    @overload
    def trace(
        cls,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register one TRACE endpoint.

        Direct registration returns the mutable route definition.
        """

    @classmethod
    def trace(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register TRACE directly or return a decorator.

        Args:
            path: Absolute route path.
            action: Optional callable or controller action.

        Returns:
            A route definition or endpoint decorator.
        """
        if action is None:
            return cls.router().trace(path)
        return cls.router().trace(path, action)

    @classmethod
    @overload
    def websocket(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a WebSocket endpoint decorator.

        The endpoint retains its original callable identity.
        """

    @classmethod
    @overload
    def websocket(
        cls,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register one WebSocket endpoint.

        Direct registration returns the mutable route definition.
        """

    @classmethod
    def websocket(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a WebSocket handler directly or as a decorator.

        Args:
            path: Absolute WebSocket route path.
            action: Optional async callable or controller action.

        Returns:
            A route definition or endpoint decorator.
        """
        if action is None:
            return cls.router().websocket(path)
        return cls.router().websocket(path, action)

    @classmethod
    def bind(
        cls,
        parameter: str,
        callback: RouteBindingCallback,
    ) -> None:
        """Register a path parameter binding callback.

        Args:
            parameter: Native route parameter name.
            callback: Synchronous or asynchronous value resolver.
        """
        cls.router().bind(parameter, callback)

    @classmethod
    @overload
    def any(
        cls,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator for common HTTP methods.

        The supported method set excludes CONNECT and TRACE.
        """

    @classmethod
    @overload
    def any(
        cls,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register common HTTP methods for one endpoint.

        Direct registration returns the mutable route definition.
        """

    @classmethod
    def any(
        cls,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register common HTTP methods directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or endpoint decorator.
        """
        if action is None:
            return cls.router().any(path)
        return cls.router().any(path, action)

    @classmethod
    def redirect(
        cls,
        path: str,
        location: str,
        *,
        status: int = 303,
    ) -> RouteDefinition:
        """Register a route that returns a validated local redirect.

        Args:
            path: Incoming absolute route path.
            location: Relative destination.
            status: HTTP redirect status.

        Returns:
            Fluent route definition.
        """
        return cls.router().redirect(path, location, status=status)

    @classmethod
    def fallback(cls, action: RouteAction) -> RouteDefinition:
        """Register the last-resort handler for unmatched request paths.

        Args:
            action: Callable or controller action.

        Returns:
            The catch-all route definition.
        """
        return cls.router().fallback(action)

    @classmethod
    def prefix(cls, value: str = "") -> RouteGroupBuilder:
        """Create a builder for nested route registration attributes.

        Args:
            value: Optional absolute path prefix.

        Returns:
            Fluent route group builder.
        """
        return cls.router().prefix(value)

    @classmethod
    def resource(
        cls,
        name: str,
        controller: type[object],
        *,
        parameter: str | None = None,
    ) -> ResourceRegistrar:
        """Register conventional resource controller routes.

        Args:
            name: Relative resource URI.
            controller: Controller type resolved for each request.
            parameter: Optional item parameter name.

        Returns:
            Resource action filter.
        """
        return cls.router().resource(
            name,
            controller,
            parameter=parameter,
        )

    @classmethod
    def api_resource(
        cls,
        name: str,
        controller: type[object],
        *,
        parameter: str | None = None,
    ) -> ResourceRegistrar:
        """Register resource routes without HTML-oriented actions.

        Args:
            name: Relative resource URI.
            controller: Controller type resolved for each request.
            parameter: Optional item parameter name.

        Returns:
            Resource action filter.
        """
        return cls.router().api_resource(
            name,
            controller,
            parameter=parameter,
        )

    @classmethod
    def singleton(
        cls,
        name: str,
        controller: type[object],
    ) -> ResourceRegistrar:
        """Register a singleton resource controller.

        Args:
            name: Relative resource name or nested path.
            controller: Controller type resolved for each request.

        Returns:
            A registrar for singleton inclusion and exclusion.
        """
        return cls.router().singleton(name, controller)

    @classmethod
    def api_singleton(
        cls,
        name: str,
        controller: type[object],
    ) -> ResourceRegistrar:
        """Register an API singleton resource controller.

        Args:
            name: Relative resource name or nested path.
            controller: Controller type resolved for each request.

        Returns:
            A registrar for singleton inclusion and exclusion.
        """
        return cls.router().api_singleton(name, controller)

    @classmethod
    def inspect(
        cls,
        filters: RouteFilter | None = None,
    ) -> tuple[RouteDefinition, ...]:
        """Return matching route definitions in registration order.

        Args:
            filters: Exact metadata selectors, or an empty selector.

        Returns:
            Original route definitions from the canonical application catalog.
        """
        return cls.router().inspect(filters)

    @classmethod
    def alias_middleware(
        cls,
        alias: str,
        middleware: type[HttpMiddleware],
    ) -> None:
        """Register one route middleware alias on the active Router.

        Args:
            alias: Stable middleware name.
            middleware: Native middleware class.
        """
        cls.router().alias_middleware(alias, middleware)

    @classmethod
    def middleware_group(
        cls,
        name: str,
        middleware: Sequence[str | type[HttpMiddleware]],
    ) -> None:
        """Register an ordered route middleware group.

        Args:
            name: Stable group name.
            middleware: Aliases and classes expanded in order.
        """
        cls.router().middleware_group(name, middleware)

    @classmethod
    def has(cls, name: str) -> bool:
        """Check whether the application registered a named route.

        Args:
            name: Exact route name.

        Returns:
            True when the name exists in the canonical route catalog.
        """
        return cls.router().has(name)

    @classmethod
    def current(cls) -> RouteDefinition | None:
        """Return the route matched by the active request.

        Returns:
            The matched route definition, or None before route dispatch.
        """
        return current_route()

    @classmethod
    def current_route_name(cls) -> str | None:
        """Return the current request's route name when assigned.

        Returns:
            Matched route name, or None for an unnamed route.
        """
        return current_route_name()


__all__ = ["Route"]
