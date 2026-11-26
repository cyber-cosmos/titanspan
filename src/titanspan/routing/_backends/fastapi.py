"""Compile native definitions into the existing FastAPI application.

FastAPI and Starlette provide path matching, method errors, OpenAPI wiring,
and ASGI dispatch while Titanspan retains route ownership and DI.
"""

from __future__ import annotations

import inspect
import re
from inspect import Parameter, Signature
from typing import TYPE_CHECKING, cast, get_type_hints
from urllib.parse import urlsplit

import anyio
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from starlette.routing import Match, NoMatchFound

from titanspan.contracts.http import ResponseFactory
from titanspan.http.request import Request
from titanspan.routing.exceptions import (
    EndpointResponseError,
    InvalidRouteError,
    RouteUrlError,
)
from titanspan.routing.router import Router

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, MutableMapping

    from starlette.types import Scope

    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.http import (
        HttpMiddleware,
        HttpRequest,
        HttpResponse,
        JsonValue,
    )
    from titanspan.contracts.routing import ControllerAction, RouteAction
    from titanspan.routing.route import RouteDefinition
    from titanspan.routing.url_generator import UrlGenerator

_PATH_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[^{}]+)?\}")
_INVALID_CONTROLLER_ACTION = (
    "Controller actions must name a public callable method."
)
_MISSING_ACTION_ERROR = "Every compiled route must have an endpoint action."
_INVALID_ENDPOINT_RESULT = (
    "Route handlers must return a native response, JSON value, text, bytes, "
    "or None."
)
_ROUTE_ATTRIBUTE = "titanspan.route"
_ROUTE_PARAMETERS_ATTRIBUTE = "titanspan.route_parameters"
_ROUTE_REVERSAL_ERROR = "The registered route could not be reversed."


def install_routes(
    application: FastAPI,
    router: Router,
    container: ServiceContainer,
    url_generator: UrlGenerator,
) -> None:
    """Freeze and compile native routes into the application's ASGI host.

    Args:
        application: Existing FastAPI application composed by Foundation.
        router: Native route owner and metadata source.
        container: Canonical service container used by endpoint dispatch.
        url_generator: Application URL generator sharing the route catalog.

    Side Effects:
        Adds FastAPI operations and route metadata to the application once.

    Raises:
        InvalidRouteError: If a controller action or middleware is invalid.
    """
    compiled = APIRouter()
    for index, definition in enumerate(router.freeze()):
        endpoint = _endpoint(definition, container)
        route_class = _route_class(
            definition.constraints,
            definition.domain_name,
        )
        compiled.add_api_route(
            definition.path,
            endpoint,
            methods=list(definition.methods),
            name=definition.route_name or f"native_route_{index}",
            tags=list(definition.tag_values) or None,
            summary=definition.summary_text,
            description=definition.description_text,
            deprecated=definition.is_deprecated,
            status_code=definition.response_status,
            response_model=None,
            route_class_override=route_class,
        )
    application.include_router(compiled)

    def reverse_path(
        name: str,
        values: Mapping[str, str],
    ) -> str:
        """Reverse one installed named route through Starlette's router.

        Args:
            name: Name assigned to the native route definition.
            values: String path values already validated by URL generation.

        Returns:
            Starlette's encoded local URL path.

        Raises:
            RouteUrlError: If the compiled route cannot be reversed.
        """
        try:
            return str(application.url_path_for(name, **values))
        except NoMatchFound as error:
            raise RouteUrlError(_ROUTE_REVERSAL_ERROR) from error

    url_generator.configure_path_reverser(reverse_path)


def _endpoint(
    definition: RouteDefinition,
    container: ServiceContainer,
) -> Callable[..., object]:
    """Create one typed FastAPI adapter for a native route definition.

    Args:
        definition: Frozen route and OpenAPI metadata.
        container: Application container that resolves endpoint dependencies.

    Returns:
        A backend endpoint whose visible parameters contain path values only.
    """
    action = definition.action
    if action is None:
        raise InvalidRouteError(_MISSING_ACTION_ERROR)
    target, _ = _target_callable(action)
    signature = _dispatch_signature(definition, target)
    asgi_parameter_name = next(iter(signature.parameters))
    middleware_types = _resolved_middleware(definition, container)

    async def dispatch(
        **values: object,
    ) -> StarletteResponse:
        """Dispatch one matched route through native scopes and services.

        Args:
            **values: Backend request and path values selected by FastAPI.

        Returns:
            A backend response created by the native ResponseFactory.
        """
        values.pop(asgi_parameter_name)
        path_values = values
        native_request = await container.make_async(Request)
        native_request.set_attribute(_ROUTE_ATTRIBUTE, definition)
        native_request.set_attribute(
            _ROUTE_PARAMETERS_ATTRIBUTE,
            dict(path_values),
        )
        values = _call_parameters(target, path_values)
        factory = container.make(ResponseFactory)

        async def invoke() -> HttpResponse:
            """Resolve and invoke the endpoint without another service graph.

            Returns:
                The endpoint result after native dependency injection.
            """
            result = await _invoke_action(action, container, values)
            return cast("HttpResponse", _normalize_response(result, factory))

        handler = invoke
        for middleware_type in reversed(middleware_types):
            downstream = handler

            async def apply_middleware(
                middleware_class: type[HttpMiddleware] = middleware_type,
                next_handler: Callable[
                    [], Awaitable[HttpResponse]
                ] = downstream,
            ) -> HttpResponse:
                """Run one route middleware around its downstream handler.

                Args:
                    middleware_class: Class resolved by the native container.
                    next_handler: Remaining endpoint or middleware chain.

                Returns:
                    Native response produced by middleware or endpoint.
                """
                middleware = await container.make_async(middleware_class)

                async def next_request(
                    _: HttpRequest,
                ) -> HttpResponse:
                    """Advance the same request through the remaining chain.

                    Args:
                        _: Current request accepted by the middleware contract.

                    Returns:
                        The downstream native response.
                    """
                    return await next_handler()

                return await middleware.handle(native_request, next_request)

            handler = apply_middleware

        result = await handler()
        return cast("StarletteResponse", result)

    dispatch.__name__ = definition.route_name or "titanspan_endpoint"
    dispatch.__signature__ = signature
    return dispatch


async def _invoke_action(
    action: RouteAction,
    container: ServiceContainer,
    parameters: Mapping[str, object],
) -> object:
    """Resolve controller ownership and call an endpoint with native DI.

    Args:
        action: Callable or controller action from the native definition.
        container: Canonical application service container.
        parameters: Explicit values extracted from the matched path.

    Returns:
        The endpoint result, awaiting async handlers and offloading sync ones.
    """
    callback, _ = await _resolve_callback(action, container)
    if inspect.iscoroutinefunction(callback) or (
        callable(callback)
        and inspect.iscoroutinefunction(type(callback).__call__)
    ):
        return await container.call_async(callback, parameters)
    return await anyio.to_thread.run_sync(
        container.call,
        callback,
        parameters,
    )


async def _resolve_callback(
    action: RouteAction,
    container: ServiceContainer,
) -> tuple[Callable[..., object], type[object] | None]:
    """Resolve a class-based controller only when a request is dispatched.

    Args:
        action: Endpoint declaration from the frozen route metadata.
        container: Canonical application service container.

    Returns:
        Bound callable plus its controller type, when applicable.

    Raises:
        InvalidRouteError: If a controller method is private or absent.
    """
    controller: type[object] | None = None
    method_name: str | None = None
    if isinstance(action, tuple):
        controller, method_name = cast("ControllerAction", action)
    elif isinstance(action, type):
        controller = action
        method_name = "__call__"
    elif inspect.ismethod(action) and isinstance(action.__self__, type):
        controller = cast("type[object]", action.__self__)
        method_name = action.__name__
    if controller is None or method_name is None:
        return cast("Callable[..., object]", action), None
    private_method = method_name.startswith("_") and method_name != "__call__"
    if private_method or not callable(getattr(controller, method_name, None)):
        raise InvalidRouteError(_INVALID_CONTROLLER_ACTION)
    instance = await container.make_async(controller)
    callback = getattr(instance, method_name)
    if not callable(callback):
        raise InvalidRouteError(_INVALID_CONTROLLER_ACTION)
    return callback, controller


def _target_callable(
    action: RouteAction,
) -> tuple[Callable[..., object], type[object] | None]:
    """Find the declaration signature without constructing a controller.

    Args:
        action: Function, controller class, or controller/method pair.

    Returns:
        A callable for annotation inspection and its controller owner.

    Raises:
        InvalidRouteError: If the action cannot be inspected safely.
    """
    controller: type[object] | None = None
    if isinstance(action, tuple):
        controller, name = cast("ControllerAction", action)
        callback = getattr(controller, name, None)
    elif isinstance(action, type):
        controller = action
        callback = cast("Callable[..., object]", action.__call__)
    elif inspect.ismethod(action) and isinstance(action.__self__, type):
        controller = cast("type[object]", action.__self__)
        callback = getattr(controller, action.__name__, None)
    else:
        callback = action
    if not callable(callback):
        raise InvalidRouteError(_INVALID_CONTROLLER_ACTION)
    return cast("Callable[..., object]", callback), controller


def _dispatch_signature(
    definition: RouteDefinition,
    target: Callable[..., object],
) -> Signature:
    """Expose only the Starlette request and declared path parameters.

    Args:
        definition: Route path whose placeholders are public HTTP inputs.
        target: Original endpoint signature used for path type annotations.

    Returns:
        A synthetic signature that excludes service-container dependencies.
    """
    parameters = list(inspect.signature(target).parameters.values())
    if parameters and parameters[0].name in {"self", "cls"}:
        parameters = parameters[1:]
    try:
        hints = get_type_hints(target, include_extras=True)
    except (NameError, TypeError, ValueError):
        hints = {}
    by_name = {parameter.name: parameter for parameter in parameters}
    visible = [
        Parameter(
            _asgi_request_parameter(definition),
            Parameter.POSITIONAL_OR_KEYWORD,
            annotation=StarletteRequest,
        )
    ]
    for name in _path_parameters(definition.path):
        original = by_name.get(name)
        annotation = hints.get(name, original.annotation if original else str)
        visible.append(
            Parameter(
                name,
                Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation,
            )
        )
    return Signature(visible)


def _asgi_request_parameter(definition: RouteDefinition) -> str:
    """Choose an internal parameter name that cannot collide with a route.

    Args:
        definition: Native route whose parameters are exposed to FastAPI.

    Returns:
        Unique synthetic name used for the backend-only request object.
    """
    name = "_titanspan_asgi_request"
    while name in _path_parameters(definition.path):
        name += "_"
    return name


def _call_parameters(
    callback: Callable[..., object],
    path_values: Mapping[str, object],
) -> dict[str, object]:
    """Keep only explicit path values accepted by an endpoint.

    Args:
        callback: Bound callable invoked by the native container.
        path_values: Values produced by backend path parsing.

    Returns:
        Values keyed by parameters accepted by the handler.
    """
    parameters = inspect.signature(callback).parameters
    if any(
        parameter.kind is Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return dict(path_values)
    return {
        name: value for name, value in path_values.items() if name in parameters
    }


def _resolved_middleware(
    definition: RouteDefinition,
    container: ServiceContainer,
) -> tuple[type[HttpMiddleware], ...]:
    """Resolve route middleware metadata once while startup freezes routes.

    Args:
        definition: Route whose middleware aliases must be expanded.
        container: Native container used to verify middleware contracts.

    Returns:
        Middleware classes in outer-to-inner order.

    Notes:
        The router owns alias expansion; instances remain request scoped.
    """
    active_router = container.make(Router)
    return active_router.resolve_middleware(definition)


def _normalize_response(
    value: object,
    factory: ResponseFactory,
) -> StarletteResponse:
    """Convert supported endpoint values through the native response factory.

    Args:
        value: Value returned by an endpoint or middleware.
        factory: Application response factory resolved from the container.

    Returns:
        A response understood by the ASGI host.

    Raises:
        EndpointResponseError: If the endpoint returns an unsupported object.
    """
    if isinstance(value, StarletteResponse):
        return value
    if value is None:
        return cast("StarletteResponse", factory.no_content())
    if isinstance(value, (str, bytes)):
        return cast("StarletteResponse", factory(value))
    if _is_json_value(value):
        return cast("StarletteResponse", factory.json(cast("JsonValue", value)))
    raise EndpointResponseError(_INVALID_ENDPOINT_RESULT)


def _is_json_value(value: object) -> bool:
    """Check JSON values recursively without exposing arbitrary object state.

    Args:
        value: Endpoint result to validate for JSON serialization.

    Returns:
        True for standard JSON scalars, lists, and string-key mappings.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, list):
        values = cast("list[object]", value)
        return all(_is_json_value(item) for item in values)
    if isinstance(value, dict):
        values = cast("dict[object, object]", value)
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in values.items()
        )
    return False


def _route_class(
    constraints: Mapping[str, str],
    domain: str | None,
) -> type[APIRoute]:
    """Create a backend route class applying native constraint metadata.

    Args:
        constraints: Parameter patterns used by this route.
        domain: Optional exact host constraint.

    Returns:
        APIRoute subclass that delegates path matching before extra checks.
    """

    class ConstrainedRoute(APIRoute):
        """Apply safe native constraints after the backend path match.

        The matcher remains owned by the selected ASGI backend.
        """

        def matches(
            self,
            scope: Scope,
        ) -> tuple[Match, MutableMapping[str, object]]:
            """Reject full path matches that violate declared constraints.

            Args:
                scope: ASGI request scope passed by Starlette's route matcher.

            Returns:
                Backend match result and the associated child request scope.
            """
            match, child_scope = super().matches(scope)
            if match is not Match.FULL:
                return match, child_scope
            route_values = child_scope.get("path_params", {})
            for parameter, pattern in constraints.items():
                value = route_values.get(parameter)
                if value is None or re.fullmatch(pattern, str(value)) is None:
                    return Match.NONE, child_scope
            if domain is not None and not _host_matches(scope, domain):
                return Match.NONE, child_scope
            return match, child_scope

    return ConstrainedRoute


def _host_matches(scope: Scope, domain: str) -> bool:
    """Compare the request Host value against one exact configured domain.

    Args:
        scope: ASGI request scope containing untrusted headers.
        domain: Normalized domain configured by the application.

    Returns:
        True only when the Host header hostname matches exactly.
    """
    for name, value in scope.get("headers", []):
        if name.lower() == b"host":
            parsed = urlsplit(f"//{value.decode('latin-1')}")
            return parsed.hostname is not None and (
                parsed.hostname.lower().rstrip(".") == domain
            )
    return False


def _path_parameters(path: str) -> tuple[str, ...]:
    """Extract ordered path parameter names for synthetic signatures.

    Args:
        path: Native path template.

    Returns:
        Parameter names in route order.
    """
    return tuple(match.group(1) for match in _PATH_PARAMETER.finditer(path))


__all__ = ["install_routes"]
