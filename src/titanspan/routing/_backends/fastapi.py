"""Compile native definitions into the existing FastAPI application.

FastAPI and Starlette provide path matching, method errors, OpenAPI wiring,
and ASGI dispatch while Titanspan retains route ownership and DI.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from inspect import Parameter, Signature
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Protocol,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from urllib.parse import urlsplit
from uuid import UUID

import anyio
from fastapi import APIRouter, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.params import Param
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from starlette.routing import Match, NoMatchFound
from starlette.websockets import WebSocket

from titanspan.contracts.container import Scope
from titanspan.contracts.http import (
    HttpMiddleware,
    HttpRequest,
    ParameterizedHttpMiddleware,
    ResponseFactory,
)
from titanspan.http.request import Request
from titanspan.routing.exceptions import (
    EndpointResponseError,
    InvalidRouteError,
    RouteBindingNotFoundError,
    RouteUrlError,
)
from titanspan.routing.helpers import bind_current_route
from titanspan.routing.router import Router
from titanspan.validation import ValidationErrorBody

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, MutableMapping
    from contextlib import AbstractAsyncContextManager

    from starlette.types import Scope as ASGIScope

    from titanspan.contracts.container import ServiceContainer
    from titanspan.contracts.http import (
        HttpResponse,
        JsonValue,
    )
    from titanspan.contracts.routing import ControllerAction, RouteAction
    from titanspan.routing.route import RouteDefinition
    from titanspan.routing.url_generator import UrlGenerator

_PATH_PARAMETER = re.compile(
    r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}?]+))?(\?)?\}",
)
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
_BINDING_NOT_FOUND_ERROR = "The route parameter did not match a resource."
_MISSING_WEBSOCKET_ERROR = "WebSocket routes need one typed connection value."
_ASYNC_WEBSOCKET_ERROR = "WebSocket route handlers must be asynchronous."
_INVALID_ROUTE_DEFAULT_ERROR = (
    "A route default cannot be converted to its handler annotation."
)
_VALIDATION_RESPONSE_STATUS = 422
_VALIDATION_RESPONSE_DESCRIPTION = "Request data failed validation."
_INVALID_PARAMETERIZED_MIDDLEWARE_ERROR = (
    "Resolved middleware does not support its declared parameters."
)
_NO_CONTENT_STATUSES = frozenset({204, 205, 304})
type _ResolvedMiddleware = tuple[
    type[HttpMiddleware],
    tuple[str, ...],
]


class _ScopedServiceContainer(Protocol):
    """Describe the existing Container execution-scope boundary privately.

    The adapter uses this contract only for WebSocket connection ownership.
    """

    def scope(
        self,
        scope: Scope,
    ) -> AbstractAsyncContextManager[object]:
        """Create a task-local resource scope.

        Args:
            scope: Container lifetime selected for this connection.

        Returns:
            An asynchronous context that owns scoped dependencies.
        """
        ...


@dataclass(frozen=True, slots=True)
class _EndpointConfiguration:
    """Retain immutable route dispatch inputs created during compilation.

    One configuration is shared by every request using its route endpoint.
    """

    definition: RouteDefinition
    action: RouteAction
    target: Callable[..., object]
    container: ServiceContainer
    router: Router
    defaults: Mapping[str, object]
    omitted_path_parameters: frozenset[str]
    asgi_parameter_name: str
    middleware_types: tuple[_ResolvedMiddleware, ...]
    signature: Signature


@dataclass(frozen=True, slots=True)
class _RouteExecution:
    """Hold per-request values for one already selected route action.

    This record keeps request state separate from compiled route metadata.
    """

    configuration: _EndpointConfiguration
    call_values: Mapping[str, object]
    native_request: Request
    factory: ResponseFactory


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
        route_name = definition.route_name or f"native_route_{index}"
        variants = _path_variants(definition.path)
        if definition.protocol == "websocket":
            for variant_index, (path, omitted) in enumerate(variants):
                endpoint = _websocket_endpoint(
                    definition,
                    container,
                    router,
                    omitted_path_parameters=omitted,
                )
                backend_name = (
                    route_name
                    if variant_index == 0
                    else f"{route_name}__without_{next(iter(omitted))}"
                )
                compiled.add_api_websocket_route(
                    path,
                    endpoint,
                    name=backend_name,
                )
            continue

        route_class = _route_class(
            definition.constraints,
            definition.domain_name,
            frozenset(name for _, omitted in variants for name in omitted),
        )
        for variant_index, (path, omitted) in enumerate(variants):
            endpoint = _endpoint(
                definition,
                container,
                router,
                omitted_path_parameters=omitted,
            )
            for method_index, method in enumerate(definition.methods):
                backend_name = (
                    route_name
                    if method_index == 0
                    else f"{route_name}__{method.lower()}"
                )
                operation_id = _operation_id(
                    definition.route_name,
                    index,
                    method,
                    multiple_methods=len(definition.methods) > 1,
                )
                if variant_index:
                    optional_name = next(iter(omitted))
                    backend_name = f"{backend_name}__without_{optional_name}"
                    operation_id = f"{operation_id}.without_{optional_name}"
                compiled.add_api_route(
                    path,
                    endpoint,
                    methods=[method],
                    name=backend_name,
                    operation_id=operation_id,
                    tags=list(definition.tag_values) or None,
                    summary=definition.summary_text,
                    description=definition.description_text,
                    deprecated=definition.is_deprecated,
                    status_code=definition.response_status,
                    response_model=definition.response_model_type,
                    responses=_response_metadata(definition),
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


def _operation_id(
    route_name: str | None,
    index: int,
    method: str,
    *,
    multiple_methods: bool,
) -> str:
    """Build a deterministic unique OpenAPI operation identifier.

    Args:
        route_name: Optional native route name.
        index: Declaration index for unnamed routes.
        method: One HTTP method accepted by the operation.
        multiple_methods: Whether the native declaration has several methods.

    Returns:
        An operation identifier unique across compiled route methods.
    """
    base = route_name or f"native_route_{index}"
    return f"{base}.{method.lower()}" if multiple_methods else base


def _response_metadata(
    definition: RouteDefinition,
) -> dict[int | str, dict[str, Any]]:
    """Combine route responses with the safe native validation schema.

    Args:
        definition: Frozen route metadata selected for OpenAPI generation.

    Returns:
        Explicit response metadata plus the default safe 422 response.
    """
    responses: dict[int | str, dict[str, Any]] = {
        status: cast("dict[str, Any]", dict(metadata))
        for status, metadata in definition.response_metadata.items()
    }
    responses.setdefault(
        _VALIDATION_RESPONSE_STATUS,
        {
            "model": ValidationErrorBody,
            "description": _VALIDATION_RESPONSE_DESCRIPTION,
        },
    )
    return responses


def _endpoint(
    definition: RouteDefinition,
    container: ServiceContainer,
    router: Router,
    *,
    omitted_path_parameters: frozenset[str] = frozenset(),
) -> Callable[..., object]:
    """Create one typed FastAPI adapter for a native route definition.

    Args:
        definition: Frozen route and OpenAPI metadata.
        container: Application container that resolves endpoint dependencies.
        router: Owner of route bindings and current route metadata.
        omitted_path_parameters: Optional values absent from this path variant.

    Returns:
        A backend endpoint with typed request inputs and no service fields.
    """
    action = definition.action
    if action is None:
        raise InvalidRouteError(_MISSING_ACTION_ERROR)
    target, _ = _target_callable(action)
    route_defaults = _coerce_route_defaults(
        target,
        definition.default_values,
    )
    signature = _dispatch_signature(
        definition,
        target,
        router,
        omitted_path_parameters=omitted_path_parameters,
    )
    configuration = _EndpointConfiguration(
        definition=definition,
        action=action,
        target=target,
        container=container,
        router=router,
        defaults=route_defaults,
        omitted_path_parameters=omitted_path_parameters,
        asgi_parameter_name=next(iter(signature.parameters)),
        middleware_types=_resolved_middleware(definition, container),
        signature=signature,
    )

    async def dispatch(
        **values: object,
    ) -> object:
        """Dispatch one matched route through native scopes and services.

        Args:
            **values: Backend request and path values selected by FastAPI.

        Returns:
            A backend response created by the native ResponseFactory.
        """
        try:
            native_request, factory, call_values = await _prepare_call(
                configuration,
                values,
            )
        except RouteBindingNotFoundError:
            factory = container.make(ResponseFactory)
            return cast(
                "StarletteResponse",
                factory.json({"detail": "Not Found"}, status=404),
            )
        with bind_current_route(definition):
            return await _invoke_route(
                _RouteExecution(
                    configuration=configuration,
                    call_values=call_values,
                    native_request=native_request,
                    factory=factory,
                ),
            )

    dispatch.__name__ = definition.route_name or "titanspan_endpoint"
    dispatch.__signature__ = configuration.signature
    return dispatch


async def _prepare_call(
    configuration: _EndpointConfiguration,
    values: Mapping[str, object],
) -> tuple[Request, ResponseFactory, dict[str, object]]:
    """Build request metadata and explicit action arguments for one match.

    Args:
        configuration: Frozen route, services, defaults, and binding policy.
        values: Backend request and path values selected by FastAPI.

    Returns:
        Native request, response factory, and filtered action arguments.

    Raises:
        RouteBindingNotFoundError: If a path binding finds no resource.
    """
    definition = configuration.definition
    dispatch_values = dict(values)
    dispatch_values.pop(configuration.asgi_parameter_name)
    path_values = {
        name: dispatch_values[name]
        for name in _path_parameters(definition.path)
        if name in dispatch_values
    }
    native_request = await configuration.container.make_async(Request)
    native_request.set_attribute(_ROUTE_ATTRIBUTE, definition)
    native_request.set_attribute(
        _ROUTE_PARAMETERS_ATTRIBUTE,
        dict(path_values),
    )
    factory = configuration.container.make(ResponseFactory)
    for name, default in configuration.defaults.items():
        dispatch_values.setdefault(name, default)
    for name in configuration.omitted_path_parameters:
        dispatch_values.setdefault(name, configuration.defaults.get(name))
    dispatch_values.update(
        await _resolve_route_bindings(configuration.router, path_values),
    )
    return (
        native_request,
        factory,
        _call_parameters(configuration.target, dispatch_values),
    )


async def _invoke_route(execution: _RouteExecution) -> object:
    """Invoke one action directly or through its selected middleware chain.

    Args:
        execution: Route metadata and per-request values for this invocation.

    Returns:
        Native response or value for FastAPI response validation.
    """
    configuration = execution.configuration
    if configuration.middleware_types:
        return await _invoke_with_middleware(execution)
    result = await _invoke_action(
        configuration.action,
        configuration.container,
        execution.call_values,
    )
    definition = configuration.definition
    if definition.response_model_type is not None:
        return result
    return _normalize_response(
        result,
        execution.factory,
        status=definition.response_status,
    )


async def _invoke_with_middleware(
    execution: _RouteExecution,
) -> HttpResponse:
    """Run the endpoint and response normalization through route middleware.

    Args:
        execution: Route metadata and per-request values for this invocation.

    Returns:
        Response returned by the innermost action or outer middleware.
    """
    configuration = execution.configuration
    definition = configuration.definition

    async def invoke() -> HttpResponse:
        """Invoke the action and normalize its result for middleware.

        Returns:
            Native response produced by the endpoint and response factory.
        """
        result = await _invoke_action(
            configuration.action,
            configuration.container,
            execution.call_values,
        )
        if definition.response_model_type is not None:
            if isinstance(result, StarletteResponse):
                return cast("HttpResponse", result)
            # Pydantic accepts model classes and generic aliases through this
            # adapter boundary, while native metadata stores the value broadly.
            result = TypeAdapter(
                cast("type[object]", definition.response_model_type),
            ).validate_python(result)
            encoded = cast("JsonValue", jsonable_encoder(result))
            return execution.factory.json(
                encoded,
                status=(
                    200
                    if definition.response_status is None
                    else definition.response_status
                ),
            )
        return cast(
            "HttpResponse",
            _normalize_response(
                result,
                execution.factory,
                status=definition.response_status,
            ),
        )

    handler = invoke
    for middleware_type, middleware_parameters in reversed(
        configuration.middleware_types,
    ):
        downstream = handler

        async def apply_middleware(
            middleware_class: type[HttpMiddleware] = middleware_type,
            parameters: tuple[str, ...] = middleware_parameters,
            next_handler: Callable[[], Awaitable[HttpResponse]] = downstream,
        ) -> HttpResponse:
            """Run one resolved middleware around the remaining handler.

            Args:
                middleware_class: Class resolved by the native container.
                parameters: Immutable values from the route declaration.
                next_handler: Remaining endpoint or middleware chain.

            Returns:
                Native response produced by middleware or endpoint.
            """
            middleware = await configuration.container.make_async(
                middleware_class,
            )

            async def next_request(_: HttpRequest) -> HttpResponse:
                """Advance the same request through the downstream chain.

                Args:
                    _: Current request from the native HTTP contract.

                Returns:
                    The downstream native response.
                """
                return await next_handler()

            if parameters:
                if not isinstance(
                    middleware,
                    ParameterizedHttpMiddleware,
                ):
                    raise InvalidRouteError(
                        _INVALID_PARAMETERIZED_MIDDLEWARE_ERROR,
                    )
                return await middleware.handle_with_parameters(
                    execution.native_request,
                    next_request,
                    parameters,
                )
            return await middleware.handle(
                execution.native_request,
                next_request,
            )

        handler = apply_middleware
    return await handler()


def _websocket_endpoint(
    definition: RouteDefinition,
    container: ServiceContainer,
    router: Router,
    *,
    omitted_path_parameters: frozenset[str] = frozenset(),
) -> Callable[..., object]:
    """Create a FastAPI WebSocket endpoint with a Container connection scope.

    Args:
        definition: Frozen route metadata and WebSocket action.
        container: Canonical application service container.
        router: Owner of parameter bindings.
        omitted_path_parameters: Optional values absent from this path variant.

    Returns:
        A backend endpoint that owns the full connection lifetime.

    Raises:
        InvalidRouteError: If the handler is not an async WebSocket action.
    """
    action = definition.action
    if action is None:
        raise InvalidRouteError(_MISSING_ACTION_ERROR)
    target, _ = _target_callable(action)
    route_defaults = _coerce_route_defaults(
        target,
        definition.default_values,
    )
    if not _is_async_callable(target):
        raise InvalidRouteError(_ASYNC_WEBSOCKET_ERROR)
    connection_parameter = _websocket_parameter(target)
    signature = _dispatch_signature(
        definition,
        target,
        router,
        websocket=True,
        omitted_path_parameters=omitted_path_parameters,
    )
    asgi_parameter_name = next(iter(signature.parameters))

    async def dispatch(**values: object) -> None:
        """Run a WebSocket action until it returns or disconnects.

        Args:
            **values: WebSocket connection and typed route values.

        Side Effects:
            Owns and closes connection-scoped dependencies deterministically.
        """
        websocket = cast("WebSocket", values.pop(asgi_parameter_name))
        path_values = {
            name: values[name]
            for name in _path_parameters(definition.path)
            if name in values
        }
        try:
            bound_values = await _resolve_route_bindings(router, path_values)
        except RouteBindingNotFoundError:
            await websocket.close(code=1008)
            return
        call_values = _call_parameters(
            target,
            {
                **path_values,
                **bound_values,
                **{
                    name: route_defaults.get(name)
                    for name in omitted_path_parameters
                },
                connection_parameter: websocket,
            },
        )
        scoped_container = cast("_ScopedServiceContainer", container)
        async with scoped_container.scope(Scope.CONNECTION):
            with bind_current_route(definition):
                await _invoke_action(action, container, call_values)

    dispatch.__name__ = definition.route_name or "titanspan_websocket"
    dispatch.__signature__ = signature
    return dispatch


async def _resolve_route_bindings(
    router: Router,
    path_values: Mapping[str, object],
) -> dict[str, object]:
    """Apply registered binders to raw matched path parameter values.

    Args:
        router: Application route owner containing binding callbacks.
        path_values: Typed values produced by the backend route parser.

    Returns:
        Values replaced by any registered sync or async binding callbacks.

    Raises:
        RouteBindingNotFoundError: If a callback returns ``None``.
    """
    bound: dict[str, object] = {}
    for name, raw_value in path_values.items():
        callback = router.binding_for(name)
        if callback is None:
            continue
        value = callback(str(raw_value))
        if inspect.isawaitable(value):
            value = await value
        if value is None:
            raise RouteBindingNotFoundError(_BINDING_NOT_FOUND_ERROR)
        bound[name] = value
    return bound


def _websocket_parameter(target: Callable[..., object]) -> str:
    """Find the handler parameter that receives the Starlette connection.

    Args:
        target: Unbound controller method or callable declaration.

    Returns:
        The parameter name to populate with the live connection object.

    Raises:
        InvalidRouteError: If no unique connection parameter is declared.
    """
    parameters = inspect.signature(target).parameters
    try:
        hints = get_type_hints(target, include_extras=True)
    except (NameError, TypeError, ValueError):
        hints = {}
    candidates = [
        name
        for name, parameter in parameters.items()
        if name not in {"self", "cls"}
        and (
            name == "websocket"
            or hints.get(name, parameter.annotation) is WebSocket
        )
    ]
    if len(candidates) != 1:
        raise InvalidRouteError(_MISSING_WEBSOCKET_ERROR)
    return candidates[0]


def _is_async_callable(target: Callable[..., object]) -> bool:
    """Report whether a function or callable instance has async execution.

    Args:
        target: Callable declared by a WebSocket route.

    Returns:
        True when invoking it produces a coroutine.
    """
    return inspect.iscoroutinefunction(target) or (
        callable(target) and inspect.iscoroutinefunction(type(target).__call__)
    )


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
    router: Router,
    *,
    websocket: bool = False,
    omitted_path_parameters: frozenset[str] = frozenset(),
) -> Signature:
    """Expose protocol, path, and supported user-input parameters.

    Args:
        definition: Route path and registration metadata.
        target: Original callable inspected for input annotations.
        router: Owner of explicit binding callbacks.
        websocket: Whether the first synthetic input is a WebSocket.
        omitted_path_parameters: Optional values absent from this path variant.

    Returns:
        FastAPI signature excluding service-container dependencies.
    """
    parameters = list(inspect.signature(target).parameters.values())
    if parameters and parameters[0].name in {"self", "cls"}:
        parameters = parameters[1:]
    try:
        hints = get_type_hints(target, include_extras=True)
    except (NameError, TypeError, ValueError):
        hints = {}
    by_name = {parameter.name: parameter for parameter in parameters}
    path_names = _path_parameters(definition.path)
    visible = [
        Parameter(
            _asgi_request_parameter(definition),
            Parameter.POSITIONAL_OR_KEYWORD,
            annotation=WebSocket if websocket else StarletteRequest,
        )
    ]
    for name in path_names:
        if name in omitted_path_parameters:
            continue
        original = by_name.get(name)
        annotation = hints.get(
            name,
            original.annotation if original is not None else str,
        )
        if router.binding_for(name) is not None:
            annotation = str
        visible.append(
            Parameter(
                name,
                Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation,
            )
        )
    if not websocket:
        for original in parameters:
            if original.name in path_names or original.name in {"self", "cls"}:
                continue
            annotation = hints.get(original.name, original.annotation)
            if not _is_request_parameter(annotation) and _is_openapi_input(
                annotation,
            ):
                visible.append(
                    Parameter(
                        original.name,
                        Parameter.POSITIONAL_OR_KEYWORD,
                        default=original.default,
                        annotation=annotation,
                    )
                )
    return Signature(visible)


def _is_request_parameter(annotation: object) -> bool:
    """Identify native request types that FastAPI injects internally.

    Args:
        annotation: Resolved callable parameter annotation.

    Returns:
        True for Titanspan or Starlette request values.
    """
    return (
        annotation is Request
        or annotation is HttpRequest
        or annotation is StarletteRequest
        or annotation is WebSocket
    )


def _is_openapi_input(annotation: object) -> bool:
    """Select FastAPI-supported client inputs and exclude service classes.

    Args:
        annotation: Resolved route handler parameter annotation.

    Returns:
        True for scalar, enum, Pydantic, or explicitly marked parameters.
    """
    origin = get_origin(annotation)
    if origin is Annotated:
        arguments = get_args(annotation)
        if any(isinstance(value, Param) for value in arguments[1:]):
            return True
        return _is_openapi_input(arguments[0]) if arguments else False
    if origin is not None:
        return any(_is_openapi_input(value) for value in get_args(annotation))
    if not isinstance(annotation, type):
        return False
    if annotation in {
        bool,
        bytes,
        date,
        datetime,
        Decimal,
        float,
        int,
        str,
        time,
        timedelta,
        UUID,
    }:
        return True
    return issubclass(annotation, Enum) or any(
        base.__module__.startswith("pydantic") and base.__name__ == "BaseModel"
        for base in annotation.__mro__
    )


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
) -> tuple[_ResolvedMiddleware, ...]:
    """Resolve route middleware metadata once while startup freezes routes.

    Args:
        definition: Route whose middleware aliases must be expanded.
        container: Native container used to verify middleware contracts.

    Returns:
        Middleware classes and parameters in outer-to-inner order.

    Notes:
        The Router expands aliases; the Container applies each service lifetime.
    """
    active_router = container.make(Router)
    declarations = active_router.resolve_middleware_declarations(definition)
    resolved: list[_ResolvedMiddleware] = []
    for declaration in declarations:
        target = declaration.target
        if not isinstance(target, type):
            raise InvalidRouteError(_INVALID_PARAMETERIZED_MIDDLEWARE_ERROR)
        resolved.append((target, declaration.parameters))
    return tuple(resolved)


def _normalize_response(
    value: object,
    factory: ResponseFactory,
    *,
    status: int | None,
) -> StarletteResponse:
    """Convert supported endpoint values through the native response factory.

    Args:
        value: Value returned by an endpoint or middleware.
        factory: Application response factory resolved from the container.
        status: Optional status configured on the route.

    Returns:
        A response understood by the ASGI host.

    Raises:
        EndpointResponseError: If the endpoint returns an unsupported object.
    """
    if isinstance(value, StarletteResponse):
        return value
    if value is None:
        selected_status = 204 if status is None else status
        if selected_status in _NO_CONTENT_STATUSES:
            return cast(
                "StarletteResponse",
                factory.no_content(status=selected_status),
            )
        return cast(
            "StarletteResponse",
            factory(None, status=selected_status),
        )
    if isinstance(value, (str, bytes)):
        return cast(
            "StarletteResponse",
            factory(value, status=200 if status is None else status),
        )
    if _is_json_value(value):
        return cast(
            "StarletteResponse",
            factory.json(
                cast("JsonValue", value),
                status=200 if status is None else status,
            ),
        )
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
    optional_parameters: frozenset[str],
) -> type[APIRoute]:
    """Create a backend route class applying native constraint metadata.

    Args:
        constraints: Parameter patterns used by this route.
        domain: Optional exact host constraint.
        optional_parameters: Names omitted by a trailing optional segment.

    Returns:
        APIRoute subclass that delegates path matching before extra checks.
    """

    class ConstrainedRoute(APIRoute):
        """Apply safe native constraints after the backend path match.

        The matcher remains owned by the selected ASGI backend.
        """

        def matches(
            self,
            scope: ASGIScope,
        ) -> tuple[Match, MutableMapping[str, object]]:
            """Reject full path matches that violate declared constraints.

            Args:
                scope: ASGI request scope passed by Starlette's route matcher.

            Returns:
                Backend match result and the associated child request scope.
            """
            match, child_scope = super().matches(scope)
            if match is Match.NONE:
                return match, child_scope
            route_values = child_scope.get("path_params", {})
            for parameter, pattern in constraints.items():
                value = route_values.get(parameter)
                if value is None and parameter in optional_parameters:
                    continue
                if value is None or re.fullmatch(pattern, str(value)) is None:
                    return Match.NONE, child_scope
            if domain is not None and not _host_matches(scope, domain):
                return Match.NONE, child_scope
            return match, child_scope

    return ConstrainedRoute


def _coerce_route_defaults(
    target: Callable[..., object],
    defaults: Mapping[str, object],
) -> dict[str, object]:
    """Convert declared defaults to the handler's supported input types.

    Args:
        target: Original route handler inspected before controller dispatch.
        defaults: Route and group defaults stored in native metadata.

    Returns:
        Defaults converted through Pydantic for typed scalar and model inputs.

    Raises:
        InvalidRouteError: If a default violates its supported annotation.
    """
    try:
        hints = get_type_hints(target, include_extras=True)
    except (NameError, TypeError, ValueError):
        hints = {}
    converted: dict[str, object] = {}
    for name, value in defaults.items():
        annotation = hints.get(name)
        if annotation is None or not _is_openapi_input(annotation):
            converted[name] = value
            continue
        try:
            converted[name] = TypeAdapter(annotation).validate_python(value)
        except ValidationError as error:
            raise InvalidRouteError(_INVALID_ROUTE_DEFAULT_ERROR) from error
    return converted


def _host_matches(scope: ASGIScope, domain: str) -> bool:
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


def _path_variants(
    path: str,
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Compile an optional final segment into backend-owned path variants.

    Args:
        path: Native path template with an optional trailing parameter.

    Returns:
        Present and absent Starlette paths with omitted handler parameters.
    """
    optional_match = next(
        (
            match
            for match in _PATH_PARAMETER.finditer(path)
            if match.group(3) == "?"
        ),
        None,
    )
    backend_path = path.replace("?}", "}")
    if optional_match is None:
        return ((backend_path, frozenset()),)
    absent_path = path[: optional_match.start() - 1] or "/"
    return (
        (backend_path, frozenset()),
        (absent_path, frozenset((optional_match.group(1),))),
    )


__all__ = ["install_routes"]
