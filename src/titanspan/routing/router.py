"""Register native application routes and their shared metadata.

The matching backend compiles this Router once, after application providers
have completed registration and before the ASGI host accepts requests.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, cast, overload

# Runtime resolution inspects this callback's annotation during DI.
from titanspan.contracts.http import ResponseFactory  # noqa: TC001
from titanspan.routing.exceptions import (
    DuplicateRouteError,
    InvalidRouteError,
    RouterFrozenError,
)
from titanspan.routing.resource_registrar import (
    ResourceOptions,
    ResourceRegistrar,
)
from titanspan.routing.route import RouteDefinition, RouteMetadata
from titanspan.routing.route_collection import RouteCollection, RouteFilter
from titanspan.routing.route_group import RouteGroup, RouteGroupBuilder

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from titanspan.contracts.http import HttpMiddleware
    from titanspan.contracts.routing import (
        ControllerAction,
        RouteAction,
        RouteBindingCallback,
        RouteEndpoint,
    )

_ANY_METHODS = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
)
_INVALID_ALIAS_ERROR = "Middleware aliases must be non-empty names."
_MIDDLEWARE_GROUP_CYCLE_ERROR = "Middleware groups cannot include themselves."
_DUPLICATE_MIDDLEWARE_GROUP_ERROR = "Middleware group is already registered."
_MISSING_MIDDLEWARE_ALIAS_ERROR = "Unknown route middleware alias."
_FROZEN_ROUTER_ERROR = "Routes are frozen after application startup."
_INVALID_BINDING_NAME_ERROR = "Route binding names must be identifiers."
_DUPLICATE_BINDING_ERROR = "A route parameter binding is already registered."
_INVALID_CONTROLLER_MIDDLEWARE_ERROR = (
    "Controller route_middleware must contain aliases or middleware classes."
)


class Router:
    """Own route declarations, groups, aliases, and one route collection.

    Starlette and FastAPI provide matching and OpenAPI infrastructure through
    a private adapter; dispatch and service resolution remain native.
    """

    def __init__(self, routes: RouteCollection | None = None) -> None:
        """Create a Router isolated from every other application.

        Args:
            routes: Optional route catalog used by a composition root.
        """
        self._routes = RouteCollection() if routes is None else routes
        self._groups: ContextVar[tuple[RouteGroup, ...]] = ContextVar(
            f"titanspan_route_groups_{id(self)}",
            default=(),
        )
        self._middleware_aliases: dict[str, type[HttpMiddleware]] = {}
        self._middleware_groups: dict[
            str,
            tuple[str | type[HttpMiddleware], ...],
        ] = {}
        self._bindings: dict[str, RouteBindingCallback] = {}
        self._frozen = False

    @property
    def routes(self) -> RouteCollection:
        """Return the canonical route collection owned by this Router.

        Returns:
            The collection shared with URL generation and route inspection.
        """
        return self._routes

    @property
    def frozen(self) -> bool:
        """Report whether route registration is closed.

        Returns:
            True after this Router is compiled into the ASGI host.
        """
        return self._frozen

    @overload
    def route(
        self,
        path: str,
        action: RouteAction,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> RouteDefinition:
        """Register an endpoint directly for one or more methods.

        The returned definition supports registration-time metadata.
        """

    @overload
    def route(
        self,
        path: str,
        action: None = None,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator that registers an endpoint after definition.

        The overload avoids a dynamic value-or-decorator return type.
        """

    def route(
        self,
        path: str,
        action: RouteAction | None = None,
        *,
        methods: Sequence[str] = ("GET",),
        name: str | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register one route or return a decorator for that registration.

        Args:
            path: Absolute path template.
            action: Callable, controller class, or controller/method pair.
            methods: Explicit HTTP method sequence.
            name: Optional name used by URL generation.

        Returns:
            A route definition, or a decorator when action is omitted.
        """
        definition = self._register(path, action, methods)
        if name is not None:
            definition.name(name)
        if action is not None:
            return definition

        def decorate(endpoint: RouteEndpoint) -> RouteEndpoint:
            """Attach a later-declared endpoint without wrapping it.

            Args:
                endpoint: Function retained with its original identity.

            Returns:
                The same endpoint object supplied by the application.
            """
            definition.set_action(endpoint)
            return endpoint

        return decorate

    @overload
    def get(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a GET route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def get(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a GET route.

        Direct registration returns its mutable route definition.
        """

    def get(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a GET route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("GET",))

    @overload
    def post(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a POST route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def post(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a POST route.

        Direct registration returns its mutable route definition.
        """

    def post(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a POST route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("POST",))

    @overload
    def put(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a PUT route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def put(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a PUT route.

        Direct registration returns its mutable route definition.
        """

    def put(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a PUT route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("PUT",))

    @overload
    def patch(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a PATCH route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def patch(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a PATCH route.

        Direct registration returns its mutable route definition.
        """

    def patch(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a PATCH route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("PATCH",))

    @overload
    def delete(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a DELETE route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def delete(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a DELETE route.

        Direct registration returns its mutable route definition.
        """

    def delete(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a DELETE route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("DELETE",))

    @overload
    def head(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a HEAD route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def head(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register a HEAD route.

        Direct registration returns its mutable route definition.
        """

    def head(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a HEAD route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("HEAD",))

    @overload
    def options(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return an OPTIONS route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def options(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register an OPTIONS route.

        Direct registration returns its mutable route definition.
        """

    def options(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register an OPTIONS route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or decorator.
        """
        return self.route(path, action, methods=("OPTIONS",))

    @overload
    def match(
        self,
        methods: Sequence[str],
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register an endpoint directly for an explicit method sequence.

        The returned route definition supports metadata configuration.
        """

    @overload
    def match(
        self,
        methods: Sequence[str],
        path: str,
        action: None = None,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator for an explicit method sequence.

        The decorated callable is registered without wrapping it.
        """

    def match(
        self,
        methods: Sequence[str],
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register an endpoint for an explicit set of methods.

        Args:
            methods: HTTP methods accepted by this route.
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            A route definition or endpoint decorator.
        """
        return self.route(path, action, methods=methods)

    @overload
    def connect(
        self,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a CONNECT route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def connect(
        self,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register a CONNECT route directly.

        Direct registration returns the mutable route definition.
        """

    def connect(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a CONNECT route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            The fluent route definition.
        """
        return self.match(("CONNECT",), path, action)

    @overload
    def trace(
        self,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a TRACE route decorator.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def trace(
        self,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register a TRACE route directly.

        Direct registration returns the mutable route definition.
        """

    def trace(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a TRACE route directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            The fluent route definition.
        """
        return self.match(("TRACE",), path, action)

    @overload
    def websocket(
        self,
        path: str,
    ) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator that registers a WebSocket endpoint.

        The decorated callable is registered without wrapping it.
        """

    @overload
    def websocket(
        self,
        path: str,
        action: RouteAction,
    ) -> RouteDefinition:
        """Register one WebSocket endpoint directly.

        Direct registration returns the mutable route definition.
        """

    def websocket(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register a WebSocket handler or return its decorator.

        Args:
            path: Absolute WebSocket path template.
            action: Optional callable or controller action.

        Returns:
            The route definition or a decorator preserving endpoint identity.
        """
        definition = self._register(
            path,
            action,
            ("WEBSOCKET",),
            protocol="websocket",
        )
        if action is not None:
            return definition

        def decorate(endpoint: RouteEndpoint) -> RouteEndpoint:
            """Attach the decorated endpoint to its definition.

            Args:
                endpoint: Callable retaining its original identity.

            Returns:
                The original endpoint supplied by the application.
            """
            definition.set_action(endpoint)
            return endpoint

        return decorate

    def bind(self, parameter: str, callback: RouteBindingCallback) -> None:
        """Register a synchronous or asynchronous path binding callback.

        Args:
            parameter: Path parameter name selected for binding.
            callback: Resolver receiving the raw path value.

        Raises:
            InvalidRouteError: If the name or callback is invalid.
            DuplicateRouteError: If another callback owns the name.
            RouterFrozenError: If routes are already compiled.
        """
        self._ensure_mutable()
        if not parameter.isidentifier() or not callable(callback):
            raise InvalidRouteError(_INVALID_BINDING_NAME_ERROR)
        existing = self._bindings.get(parameter)
        if existing is not None and existing is not callback:
            raise DuplicateRouteError(_DUPLICATE_BINDING_ERROR)
        self._bindings[parameter] = callback

    def binding_for(self, parameter: str) -> RouteBindingCallback | None:
        """Return the callback registered for one path parameter.

        Args:
            parameter: Native route parameter name.

        Returns:
            The callback or ``None`` when no binding exists.
        """
        return self._bindings.get(parameter)

    @overload
    def any(self, path: str) -> Callable[[RouteEndpoint], RouteEndpoint]:
        """Return a decorator for the supported common HTTP methods.

        The supported method set excludes CONNECT and TRACE.
        """

    @overload
    def any(self, path: str, action: RouteAction) -> RouteDefinition:
        """Register one endpoint for the supported common HTTP methods.

        Direct registration returns the mutable route definition.
        """

    def any(
        self,
        path: str,
        action: RouteAction | None = None,
    ) -> RouteDefinition | Callable[[RouteEndpoint], RouteEndpoint]:
        """Register common HTTP methods directly or as a decorator.

        Args:
            path: Absolute path template.
            action: Optional callable or controller action.

        Returns:
            The fluent route definition.

        Notes:
            This deliberately excludes CONNECT and TRACE.
        """
        return self.match(_ANY_METHODS, path, action)

    def redirect(
        self,
        path: str,
        location: str,
        *,
        status: int = 303,
    ) -> RouteDefinition:
        """Register a route that returns a validated relative redirect.

        Args:
            path: Incoming absolute route path.
            location: Relative redirect destination.
            status: Redirect status accepted by ResponseFactory.

        Returns:
            The fluent route definition.
        """

        def redirect_action(
            factory: ResponseFactory,
        ) -> object:
            """Build a redirect with the active application's response service.

            Args:
                factory: Native response factory resolved by the container.

            Returns:
                The response produced by the native factory.
            """
            return factory.redirect(location, status=status)

        return self._register(path, redirect_action, ("GET",))

    def fallback(self, action: RouteAction) -> RouteDefinition:
        """Register a catch-all handler after more specific routes.

        Args:
            action: Callable or controller action for unmatched paths.

        Returns:
            The fallback definition, matched for the common HTTP methods.
        """
        return self.match(_ANY_METHODS, "/{path:path}", action)

    def resource(
        self,
        name: str,
        controller: type[object],
        *,
        parameter: str | None = None,
    ) -> ResourceRegistrar:
        """Register the standard resource-controller action set.

        Args:
            name: Relative resource path, which may contain a parent path.
            controller: Controller resolved through the application container.
            parameter: Optional item identifier replacing the singularized
                resource name.

        Returns:
            A registrar for keeping or excluding actions before startup.
        """
        self._ensure_mutable()
        return ResourceRegistrar(
            self,
            name,
            controller,
            ResourceOptions(
                api_only=False,
                parameter=parameter,
                singleton=False,
                group=self._active_group(),
            ),
        )

    def api_resource(
        self,
        name: str,
        controller: type[object],
        *,
        parameter: str | None = None,
    ) -> ResourceRegistrar:
        """Register API resource actions without create and edit endpoints.

        Args:
            name: Relative resource path, which may contain a parent path.
            controller: Controller resolved through the application container.
            parameter: Optional item identifier replacing the singularized
                resource name.

        Returns:
            A registrar for keeping or excluding actions before startup.
        """
        self._ensure_mutable()
        return ResourceRegistrar(
            self,
            name,
            controller,
            ResourceOptions(
                api_only=True,
                parameter=parameter,
                singleton=False,
                group=self._active_group(),
            ),
        )

    def singleton(
        self,
        name: str,
        controller: type[object],
    ) -> ResourceRegistrar:
        """Register a resource with one address and no item identifier.

        Args:
            name: Relative singleton resource name or nested name.
            controller: Controller resolved through the application container.

        Returns:
            A registrar that can include creation actions or filter routes.
        """
        self._ensure_mutable()
        return ResourceRegistrar(
            self,
            name,
            controller,
            ResourceOptions(
                api_only=False,
                parameter=None,
                singleton=True,
                group=self._active_group(),
            ),
        )

    def api_singleton(
        self,
        name: str,
        controller: type[object],
    ) -> ResourceRegistrar:
        """Register API actions for one addressable resource instance.

        Args:
            name: Relative singleton resource name or nested name.
            controller: Controller resolved through the application container.

        Returns:
            A registrar that can include creation actions or filter routes.
        """
        self._ensure_mutable()
        return ResourceRegistrar(
            self,
            name,
            controller,
            ResourceOptions(
                api_only=True,
                parameter=None,
                singleton=True,
                group=self._active_group(),
            ),
        )

    def register_resource_route(
        self,
        path: str,
        action: RouteAction,
        methods: Sequence[str],
        group: RouteGroup,
    ) -> RouteDefinition:
        """Add one resource action using its captured registration group.

        The registrar may rebuild resource paths after its original group
        context exits, so this entry point reapplies that immutable metadata.

        Args:
            path: Resource action path relative to its captured group.
            action: Controller action retained by the route definition.
            methods: HTTP methods accepted by this action.
            group: Immutable group captured when the resource was declared.

        Returns:
            The resource action stored in the canonical route catalog.
        """
        return self._register(
            path,
            action,
            methods,
            group_override=group,
        )

    def prefix(self, value: str = "") -> RouteGroupBuilder:
        """Create a fluent group builder with one path prefix.

        Args:
            value: Absolute path prefix inherited by child routes.

        Returns:
            A builder that must be entered with its group context manager.
        """
        self._ensure_mutable()
        return RouteGroupBuilder(self, value)

    @contextmanager
    def group_context(self, group: RouteGroup) -> Generator[None, None, None]:
        """Push group metadata for this registration context only.

        Args:
            group: Immutable attributes declared by a group builder.

        Yields:
            Control while child route declarations inherit the group.

        Notes:
            ContextVar tokens restore nested state after errors and task exit.
        """
        self._ensure_mutable()
        stack = self._groups.get()
        merged = stack[-1].merged(group) if stack else group
        token: Token[tuple[RouteGroup, ...]] = self._groups.set(
            (*stack, merged)
        )
        try:
            yield
        finally:
            self._groups.reset(token)

    def alias_middleware(
        self,
        alias: str,
        middleware: type[HttpMiddleware],
    ) -> None:
        """Associate a route middleware name with a native middleware class.

        Args:
            alias: Stable application name used by route metadata.
            middleware: Middleware type resolved through the application
                container for each request.

        Raises:
            InvalidRouteError: If the alias is empty.
            DuplicateRouteError: If the alias already names another class.
        """
        self._ensure_mutable()
        if not alias:
            raise InvalidRouteError(_INVALID_ALIAS_ERROR)
        existing = self._middleware_aliases.get(alias)
        if existing is not None and existing is not middleware:
            message = f"Middleware alias {alias!r} already exists."
            raise DuplicateRouteError(message)
        self._middleware_aliases[alias] = middleware

    def middleware_group(
        self,
        name: str,
        middleware: Sequence[str | type[HttpMiddleware]],
    ) -> None:
        """Register an ordered reusable route middleware group.

        Args:
            name: Group name referenced in route metadata.
            middleware: Middleware aliases and classes in execution order.

        Raises:
            InvalidRouteError: If the group name is empty.
            DuplicateRouteError: If a prior group has this name.
        """
        self._ensure_mutable()
        if not name:
            raise InvalidRouteError(_INVALID_ALIAS_ERROR)
        if name in self._middleware_groups:
            raise DuplicateRouteError(_DUPLICATE_MIDDLEWARE_GROUP_ERROR)
        self._middleware_groups[name] = tuple(middleware)

    def has(self, name: str) -> bool:
        """Report whether the route collection contains a name.

        Args:
            name: Exact route name.

        Returns:
            True when the application has registered this route.
        """
        return self._routes.has(name)

    def named(self, name: str) -> RouteDefinition:
        """Return one route definition by its stable name.

        Args:
            name: Exact route name.

        Returns:
            The matching native route definition.
        """
        return self._routes.named(name)

    def inspect(
        self,
        filters: RouteFilter | None = None,
    ) -> tuple[RouteDefinition, ...]:
        """Inspect matching route metadata through the canonical catalog.

        Args:
            filters: Exact method, path, name, protocol, domain, or middleware
                selectors.

        Returns:
            Original route definitions in stable declaration order.
        """
        return self._routes.inspect(filters)

    def resolve_middleware(
        self,
        route: RouteDefinition,
    ) -> tuple[type[HttpMiddleware], ...]:
        """Expand aliases and groups into ordered middleware classes.

        Args:
            route: Route whose middleware will be prepared for dispatch.

        Returns:
            Middleware classes after exclusions and stable deduplication.

        Raises:
            InvalidRouteError: If an alias or group is unknown or recursive.
        """
        expanded: list[type[HttpMiddleware]] = []
        excluded = set(route.excluded_middleware)
        for declaration in route.middleware_types:
            self._expand_middleware(
                declaration,
                expanded,
                excluded,
                frozenset(),
            )
        return tuple(expanded)

    def _expand_middleware(
        self,
        item: str | type[HttpMiddleware],
        expanded: list[type[HttpMiddleware]],
        excluded: set[str | type[HttpMiddleware]],
        active_groups: frozenset[str],
    ) -> None:
        """Expand aliases and groups with deduplication and cycle checks.

        Args:
            item: Middleware alias, class, or group name.
            expanded: Output list shared by one route resolution.
            excluded: Explicit route-local exclusions.
            active_groups: Middleware groups on this recursion path.

        Raises:
            InvalidRouteError: If an alias is unknown or a group is recursive.
        """
        if item in excluded:
            return
        if isinstance(item, type):
            if item not in expanded:
                expanded.append(item)
            return
        group = self._middleware_groups.get(item)
        if group is not None:
            if item in active_groups:
                raise InvalidRouteError(_MIDDLEWARE_GROUP_CYCLE_ERROR)
            next_groups = active_groups | {item}
            for child in group:
                self._expand_middleware(
                    child,
                    expanded,
                    excluded,
                    next_groups,
                )
            return
        middleware_type = self._middleware_aliases.get(item)
        if middleware_type is None:
            raise InvalidRouteError(_MISSING_MIDDLEWARE_ALIAS_ERROR)
        if middleware_type not in excluded and middleware_type not in expanded:
            expanded.append(middleware_type)

    def freeze(self) -> tuple[RouteDefinition, ...]:
        """Freeze route registration and return a specificity-sorted snapshot.

        Returns:
            Routes ordered to test static and constrained paths before general
            dynamic paths, with catch-all routes last.

        Raises:
            InvalidRouteError: If any declaration lacks a valid action.
        """
        if not self._frozen:
            self._routes.freeze()
            self._frozen = True
        return tuple(sorted(self._routes.all(), key=_route_priority))

    def _register(
        self,
        path: str,
        action: RouteAction | None,
        methods: Sequence[str],
        *,
        group_override: RouteGroup | None = None,
        protocol: str = "http",
    ) -> RouteDefinition:
        """Create a route using the active nested group metadata.

        Args:
            path: Route-local absolute path.
            action: Endpoint action or None for decorator registration.
            methods: HTTP methods handled by the new route.
            group_override: Captured registration group for resources.
            protocol: HTTP or WebSocket dispatch protocol.

        Returns:
            The route definition stored in the canonical collection.
        """
        self._ensure_mutable()
        group = (
            self._active_group() if group_override is None else group_override
        )
        full_path = _join_prefix(group.prefix, path)
        constraints = dict(group.constraints)
        defaults = dict(group.defaults)
        definition = RouteDefinition(
            full_path,
            methods,
            action,
            RouteMetadata(
                name_prefix=group.name_prefix,
                middleware=group.middleware,
                constraints=constraints,
                defaults=defaults,
                domain=group.domain_name,
                protocol=protocol,
            ),
            ensure_mutable=self._ensure_mutable,
            validate_name=self._routes.validate_name,
        )
        definition.middleware(_controller_middleware(action))
        self._routes.add(definition)
        return definition

    def _active_group(self) -> RouteGroup:
        """Return current immutable group metadata or an empty group.

        Returns:
            The route attributes inherited by new registrations.
        """
        stack = self._groups.get()
        return stack[-1] if stack else RouteGroup()

    def _ensure_mutable(self) -> None:
        """Reject registrations and group changes after route compilation.

        Raises:
            RouterFrozenError: If the app has already compiled its routes.
        """
        if self._frozen:
            raise RouterFrozenError(_FROZEN_ROUTER_ERROR)


def _controller_middleware(
    action: RouteAction | None,
) -> tuple[str | type[HttpMiddleware], ...]:
    """Read optional class-level middleware from a controller declaration.

    Args:
        action: Route action that may identify a controller class.

    Returns:
        Controller middleware declarations in their declared order.

    Raises:
        InvalidRouteError: If ``route_middleware`` has an invalid value.
    """
    controller: type[object] | None = None
    if isinstance(action, type):
        controller = action
    elif isinstance(action, tuple):
        controller = cast("ControllerAction", action)[0]
    if controller is None:
        return ()
    declarations = getattr(controller, "route_middleware", ())
    values: tuple[object, ...]
    if isinstance(declarations, (str, type)):
        values = (declarations,)
    elif isinstance(declarations, Sequence):
        values = tuple(cast("Sequence[object]", declarations))
    else:
        raise InvalidRouteError(_INVALID_CONTROLLER_MIDDLEWARE_ERROR)
    if any(
        not isinstance(value, str) and not isinstance(value, type)
        for value in values
    ):
        raise InvalidRouteError(_INVALID_CONTROLLER_MIDDLEWARE_ERROR)
    return cast(
        "tuple[str | type[HttpMiddleware], ...]",
        values,
    )


def _join_prefix(prefix: str, path: str) -> str:
    """Combine a group prefix and route path without duplicate slashes.

    Args:
        prefix: Inherited absolute route prefix.
        path: Route-local absolute path.

    Returns:
        One canonical absolute path template.
    """
    if not prefix:
        return path
    return f"{prefix}/{path.lstrip('/')}"


def _route_priority(
    route: RouteDefinition,
) -> tuple[int, int, int, int, int]:
    """Return a sort key that prioritizes specific paths and constraints.

    Args:
        route: Candidate route definition.

    Returns:
        A stable key with static segments ahead of dynamic and catch-all paths.
    """
    path = route.path
    catch_all = path.endswith(":path}")
    dynamic_count = path.count("{")
    static_segments = sum(
        not segment.startswith("{")
        for segment in path.strip("/").split("/")
        if segment
    )
    return (
        int(catch_all),
        dynamic_count,
        -len(route.constraints),
        -static_segments,
        -len(path),
    )


__all__ = ["Router"]
