"""Compose application services and own their execution lifecycles.

Foundation connects configuration, logging, service providers, the native
container, and the application context at one composition boundary.
"""

from __future__ import annotations

from contextlib import (
    AbstractContextManager,
    AsyncExitStack,
    asynccontextmanager,
    contextmanager,
)
from pathlib import Path
from typing import TYPE_CHECKING, Self
from uuid import uuid4

import anyio
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from titanspan._application_context import (
    ActiveApplicationContext,
    ApplicationContextError,
    active_application_context,
    bind_application_context,
)
from titanspan.config import (
    ConfigManager,
    ConfigServiceProvider,
    ConfigValueError,
    Settings,
)
from titanspan.container import Container, Scope, ScopeError
from titanspan.container._backends.fastapi import (
    create_fastapi_container,
    setup_fastapi_container,
)
from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import (
    AsyncServiceContainer,
    ServiceContainer,
)
from titanspan.contracts.foundation import (
    BootableServiceProvider,
    ServiceProvider,
)
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    ResponseFactory,
)
from titanspan.contracts.logging import LoggingManager
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.events import EventServiceProvider
from titanspan.http import HttpServiceProvider, JsonResponse, Request
from titanspan.http._backends.asgi import create_request
from titanspan.http.configuration import HttpConfiguration
from titanspan.http.exceptions import RequestBodyTooLargeError
from titanspan.http.response import validate_header
from titanspan.logging import (
    LogCustomizer,
    LoggingConfiguration,
    LoggingServiceProvider,
)
from titanspan.routing import Router, RoutingServiceProvider, UrlGenerator
from titanspan.routing._backends.fastapi import install_routes
from titanspan.support.uri import bind_uri_services

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        Awaitable,
        Callable,
        Generator,
        Mapping,
        Sequence,
    )
    from types import TracebackType

    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp, Receive, Send
    from starlette.types import Scope as ASGIScope

    from titanspan.container.container import ContainerScope
    from titanspan.contracts.http import HttpMiddleware, RequestHandler
    from titanspan.logging.logger import Logger

_REQUEST_ID_MAX_LENGTH = 128
_APP_NAME_KEY = "app.name"
_APP_DEBUG_KEY = "app.debug"
_CONFIGURATION_SOURCE_CONFLICT = (
    "Pass either config overrides or config_repository, not both."
)
_APPLICATION_CLOSED_ERROR = "A stopped application cannot be restarted."
_APPLICATION_STARTING_ERROR = "Application startup is already in progress."
_APPLICATION_CONTEXT_REENTRY_ERROR = (
    "An application async context is already active."
)
_APPLICATION_SHUTDOWN_DURING_STARTUP_ERROR = (
    "Application shutdown cannot run while startup is in progress."
)
_APPLICATION_CONTEXT_ERROR = (
    "Native HTTP dependencies require this application's active context."
)
_ACTIVE_APPLICATION_SCOPE_ERROR = (
    "Application shutdown requires all execution scopes and overrides "
    "to finish first."
)
_INVALID_MIDDLEWARE_RESPONSE_ERROR = (
    "Native HTTP middleware must return an ASGI-compatible response."
)


class _ApplicationContextMiddleware:
    """Hold app and request state through a complete ASGI response call.

    Pure ASGI middleware remains active until all messages have been sent,
    including messages produced lazily by a streaming response.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        application: Application,
        app_name: str,
        log_manager: LoggingManager,
    ) -> None:
        """Retain the native application dependencies used by each request.

        Args:
            app: Downstream ASGI application wrapped by this middleware.
            application: Composition root providing request scopes.
            app_name: Safe application identifier added to log context.
            log_manager: Native manager supplying request-local context.
        """
        self._app = app
        self._application = application
        self._app_name = app_name
        self._log_manager = log_manager

    async def __call__(
        self,
        scope: ASGIScope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Enclose HTTP request handling and all response body messages.

        Args:
            scope: ASGI connection metadata.
            receive: ASGI message receiver.
            send: ASGI message sender.

        Side Effects:
            Creates and finalizes a request scope around the full HTTP ASGI
            invocation. Other connection types pass through unchanged.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        incoming = StarletteRequest(scope, receive=receive)
        request_id = _request_id(incoming)
        server = self._application.http_configuration.server
        native_request = create_request(
            scope,
            receive,
            request_id=request_id,
            configuration=server,
        )
        async with self._application.execution_scope(Scope.REQUEST) as active:
            active.provide_instance(Request, native_request)
            active.provide_instance(HttpRequest, native_request)
            try:
                with self._log_manager.context(
                    application=self._app_name,
                    request_id=request_id,
                ):
                    await self._app(scope, receive, send)
            finally:
                with anyio.CancelScope(shield=True):
                    await native_request.aclose()

    _app: ASGIApp
    _application: Application
    _app_name: str
    _log_manager: LoggingManager


class _NativeHttpResponseAdapter:
    """Adapt a downstream response without reading or buffering its body.

    The application owns this lifecycle through shutdown.
    """

    def __init__(self, response: StarletteResponse) -> None:
        """Retain the ASGI response returned by downstream handling.

        Args:
            response: Response whose body may be produced incrementally.
        """
        self._response = response

    @property
    def status_code(self) -> int:
        """Return the downstream response status code.

        The application owns this lifecycle through shutdown.
        """
        return self._response.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        """Expose current headers for native middleware inspection.

        The application owns this lifecycle through shutdown.
        """
        return self._response.headers

    def with_header(self, name: str, value: str) -> Self:
        """Set a validated response header without consuming the body.

        Args:
            name: HTTP header token name.
            value: Single-line header value.

        Returns:
            This response adapter for fluent middleware composition.

        Raises:
            ValueError: If the name or value is malformed.
        """
        validate_header(name, value)
        self._response.headers[name] = value
        return self

    def asgi_response(self) -> StarletteResponse:
        """Return the original response to the middleware host.

        Returns:
            The original response object, retaining any streaming iterator.
        """
        return self._response

    _response: StarletteResponse


class _NativeHttpMiddlewareStack(BaseHTTPMiddleware):
    """Resolve native middleware from the request's application container.

    The application owns this lifecycle through shutdown.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        application: Application,
        middleware_types: Sequence[type[HttpMiddleware]],
    ) -> None:
        """Retain middleware classes in outer-to-inner order.

        Args:
            app: Downstream ASGI application.
            application: Composition root owning the native service graph.
            middleware_types: Classes in the configured execution order.
        """
        super().__init__(app)
        self._application = application
        self._middleware_types = tuple(middleware_types)

    async def dispatch(
        self,
        request: StarletteRequest,
        call_next: RequestResponseEndpoint,
    ) -> StarletteResponse:
        """Run native middleware around downstream route processing.

        Args:
            request: Backend request passed through the ASGI stack.
            call_next: Starlette continuation to the route application.

        Returns:
            The final response transmitted through the ASGI send channel.

        Raises:
            TypeError: If a middleware returns a non-ASGI response object.
        """
        native_request = self._application.container.make(HttpRequest)
        instances = [
            await self._application.container.make_async(middleware_type)
            for middleware_type in self._middleware_types
        ]

        async def terminal(_: HttpRequest) -> HttpResponse:
            """Run the route and adapt its response without buffering it.

            The application owns this lifecycle through shutdown.
            """
            backend_response = await call_next(request)
            return _NativeHttpResponseAdapter(backend_response)

        handler: RequestHandler = terminal
        for middleware in reversed(instances):
            downstream = handler

            async def invoke(
                value: HttpRequest,
                *,
                current: HttpMiddleware = middleware,
                next_handler: RequestHandler = downstream,
            ) -> HttpResponse:
                """Bind one middleware instance to its own continuation.

                The application owns this lifecycle through shutdown.
                """
                return await current.handle(value, next_handler)

            handler = invoke

        result = await handler(native_request)
        if isinstance(result, StarletteResponse):
            return result
        if isinstance(result, _NativeHttpResponseAdapter):
            return result.asgi_response()
        raise TypeError(_INVALID_MIDDLEWARE_RESPONSE_ERROR)

    _application: Application
    _middleware_types: tuple[type[HttpMiddleware], ...]


class Application:
    """Compose one application container and its optional ASGI adapter.

    Native providers register against ``container`` before graph resolution.
    HTTP handlers can resolve those same services with ``dependency``;
    third-party provider graphs remain an optional interoperability boundary.

    Attributes:
        asgi: FastAPI application served by an ASGI server.
        container: Canonical native service container for this application.
        settings: Validated settings resolved on access.

    Notes:
        Use ``async with application`` or call ``startup`` and ``shutdown``
        for non-ASGI work. ASGI middleware binds request context automatically.
    """

    # Keep independent framework and adapter inputs visible at composition.
    def __init__(  # noqa: PLR0913
        self,
        *,
        base_path: str | Path | None = None,
        config: Mapping[str, object] | None = None,
        config_repository: ConfigRepository | None = None,
        settings: Settings | None = None,
        service_providers: Sequence[ServiceProvider] = (),
        providers: Sequence[object] = (),
        logging: LoggingConfiguration | Mapping[str, object] | None = None,
        logging_customizers: (
            Mapping[str, LogCustomizer[Logger]] | None
        ) = None,
        http_middleware: Sequence[type[HttpMiddleware]] = (),
    ) -> None:
        """Build the native service graph and the FastAPI integration.

        Args:
            base_path: Trusted root for configuration and environment files.
            config: Final bootstrap values applied to loaded configuration.
            config_repository: Optional alternative repository implementation.
            settings: Explicit typed application settings, if available.
            service_providers: Native providers registering Titanspan services.
            providers: Advanced FastAPI dependency integration providers.
            logging: Final explicit logging configuration override.
            logging_customizers: Native logger setup hooks keyed by name.
            http_middleware: Native middleware in outer-to-inner order.

        Raises:
            ValueError: If both configuration source override forms are used.
            ConfigValueError: If application name or debug has an invalid type.
            Exception: A provider or native service construction failure.

        Side Effects:
            Loads trusted configuration and composes application-owned
            containers. Managed resources close on native or ASGI shutdown.
        """
        if config_repository is not None and config is not None:
            raise ValueError(_CONFIGURATION_SOURCE_CONFLICT)

        config_manager = ConfigManager(
            Path.cwd() if base_path is None else base_path,
            settings=settings,
        )
        repository: ConfigRepository = (
            config_repository
            if config_repository is not None
            else config_manager.load(overrides=config)
        )
        http_configuration = HttpConfiguration.from_repository(repository)
        native_container = Container()
        native_container.instance(ServiceContainer, native_container)
        native_container.instance(AsyncServiceContainer, native_container)
        config_provider = ConfigServiceProvider(repository)
        logging_provider = LoggingServiceProvider(
            logging,
            customizers=logging_customizers,
        )
        routing_provider = RoutingServiceProvider(repository)
        events_provider = EventServiceProvider(native_container, repository)
        native_providers: tuple[ServiceProvider, ...] = (
            config_provider,
            logging_provider,
            HttpServiceProvider(http_configuration),
            routing_provider,
            events_provider,
            *service_providers,
        )
        for provider in native_providers:
            provider.register(native_container)
        self._service_providers = native_providers

        active_repository = native_container.make(ConfigRepository)
        log_manager = native_container.make(LoggingManager)
        self.container = native_container
        self._config_repository = active_repository
        self._logging_manager = log_manager
        self._config_manager = config_manager
        self._http_configuration = http_configuration
        self._router = routing_provider.router
        self._url_generator = routing_provider.url_generator
        self._started = False
        self._starting = False
        self._closed = False
        self._routes_installed = False
        self._standalone_context: (
            AbstractContextManager[ActiveApplicationContext] | None
        ) = None

        integration_container = (
            create_fastapi_container([*providers, config_provider])
            if providers
            else None
        )
        self._lifecycle_stack = AsyncExitStack()
        # LIFO cleanup closes the optional route graph first, then native
        # dependencies, while keeping logging available to their finalizers.
        self._lifecycle_stack.push_async_callback(log_manager.aclose)
        self._lifecycle_stack.push_async_callback(native_container.aclose)
        if integration_container is not None:
            self._lifecycle_stack.push_async_callback(
                integration_container.close
            )

        self._fastapi_container = integration_container
        self.asgi = self._create_asgi(http_middleware)

    def _create_asgi(
        self,
        http_middleware: Sequence[type[HttpMiddleware]],
    ) -> FastAPI:
        """Compose the ASGI host around the native application.

        Args:
            http_middleware: Native middleware in outer-to-inner order.

        Returns:
            FastAPI host configured with lifecycle, scopes, and adapters.
        """
        app_name, debug = _application_metadata(self._config_repository)

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Bind application context through host shutdown.

            The application owns this lifecycle through shutdown.
            """
            with self._bind_context():
                await self.startup()
                try:
                    yield
                finally:
                    await self.shutdown()

        asgi = FastAPI(
            title=app_name,
            debug=debug,
            lifespan=lifespan,
        )
        asgi.state.titanspan_config = self._config_repository
        asgi.state.titanspan_logging = self._logging_manager
        asgi.state.titanspan_http = self._http_configuration
        asgi.add_exception_handler(
            RequestBodyTooLargeError,
            _request_too_large,
        )

        if http_middleware:
            asgi.add_middleware(
                _NativeHttpMiddlewareStack,
                application=self,
                middleware_types=http_middleware,
            )

        if self._fastapi_container is not None:
            setup_fastapi_container(
                container=self._fastapi_container,
                application=asgi,
            )
        # Keep context outside dependency middleware and response transmission
        # so stream iterators retain request-owned services.
        asgi.add_middleware(
            _ApplicationContextMiddleware,
            application=self,
            app_name=app_name,
            log_manager=self._logging_manager,
        )
        return asgi

    async def startup(self) -> None:
        """Boot application providers without requiring an ASGI host.

        Provider registration is complete before startup. Boot callbacks run
        in order with native dependency injection and the application context
        bound. A failure closes owned resources before it is re-raised.

        Raises:
            RuntimeError: If a stopped application is restarted or another
                startup call is already in progress.
            Exception: If provider boot or owned-resource cleanup fails.
        """
        if self._closed:
            raise RuntimeError(_APPLICATION_CLOSED_ERROR)
        if self._started:
            return
        if self._starting:
            raise RuntimeError(_APPLICATION_STARTING_ERROR)

        self._starting = True
        try:
            with self._bind_context():
                for provider in self._service_providers:
                    if isinstance(provider, BootableServiceProvider):
                        await self.container.call_async(provider.boot)
                install_routes(
                    self.asgi,
                    self._router,
                    self.container,
                    self._url_generator,
                )
                self._routes_installed = True
        except BaseException as startup_error:
            self._closed = True
            try:
                with anyio.CancelScope(shield=True):
                    with self._bind_context():
                        await self._lifecycle_stack.aclose()
            except BaseException as cleanup_error:
                startup_error.add_note(
                    "Application cleanup also failed with "
                    f"{type(cleanup_error).__name__}."
                )
                raise startup_error from cleanup_error
            raise
        else:
            self._started = True
        finally:
            self._starting = False

    async def shutdown(self) -> None:
        """Finalize application-owned resources without an ASGI host.

        Cleanup is idempotent and runs in reverse ownership order. The
        application context remains active while finalizers execute, and
        cancellation is shielded until registered cleanup completes.

        Raises:
            Exception: If an owned service fails during finalization.
        """
        if self._closed:
            return
        if self._starting:
            raise RuntimeError(_APPLICATION_SHUTDOWN_DURING_STARTUP_ERROR)
        if (
            self.container.active_scope_count
            or self.container.active_override_count
        ):
            raise ScopeError(_ACTIVE_APPLICATION_SCOPE_ERROR)
        self._closed = True
        with self._bind_context():
            with anyio.CancelScope(shield=True):
                await self._lifecycle_stack.aclose()

    async def __aenter__(self) -> Self:
        """Start this application and bind it for standalone work.

        Returns:
            This started application with its context active.

        Raises:
            RuntimeError: If another standalone context is already active or
                the application was previously stopped.
        """
        if self._standalone_context is not None:
            raise RuntimeError(_APPLICATION_CONTEXT_REENTRY_ERROR)
        await self.startup()
        binding = self._bind_context()
        binding.__enter__()
        self._standalone_context = binding
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Shut down services and restore the previous application context.

        Args:
            exception_type: Active exception class, if work failed.
            exception: Active exception instance, if work failed.
            traceback: Traceback associated with the active exception.
        """
        binding = self._standalone_context
        self._standalone_context = None
        try:
            await self.shutdown()
        finally:
            if binding is not None:
                binding.__exit__(exception_type, exception, traceback)

    def dependency[ServiceT](
        self,
        service: type[ServiceT],
    ) -> Callable[[], Awaitable[ServiceT]]:
        """Create a FastAPI dependency backed by the native service graph.

        Use the returned callable with FastAPI's ``Depends`` declaration.
        It resolves from the same application container and active request
        scope used by facades and ordinary application services.

        Args:
            service: Native service contract or concrete service type.

        Returns:
            An async dependency resolver preserving the requested type.

        Raises:
            ApplicationContextError: If invoked outside this application's
                active ASGI request context.
        """

        async def resolve_service() -> ServiceT:
            """Resolve one service through the active native container.

            Returns:
                The service instance selected by the active request scope.

            Raises:
                ApplicationContextError: If another application is active.
            """
            active = active_application_context()
            if (
                active is None
                or active.application is not self
                or active.container is not self.container
            ):
                raise ApplicationContextError(_APPLICATION_CONTEXT_ERROR)
            return await self.container.make_async(service)

        return resolve_service

    @property
    def config(self) -> ConfigRepository:
        """Return the configuration repository registered for this app.

        Returns:
            The exact implementation resolved through the service container.
        """
        return self._config_repository

    @property
    def logging(self) -> LoggingManager:
        """Return the logging service registered for this application.

        Returns:
            The exact logging manager resolved through the service container.
        """
        return self._logging_manager

    @property
    def settings(self) -> Settings:
        """Return settings owned by the configuration composition root.

        Returns:
            Lazily validated settings for this application.
        """
        return self._config_manager.settings

    @property
    def http_configuration(self) -> HttpConfiguration:
        """Return validated incoming and outgoing HTTP settings.

        Returns:
            The immutable defaults shared by the ASGI adapter and HTTP
            service provider.
        """
        return self._http_configuration

    @property
    def router(self) -> Router:
        """Return the Router used by facades and incoming ASGI dispatch.

        Returns:
            The same application-owned Router registered in the container.
        """
        return self._router

    def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a synchronous service through the canonical registry.

        Args:
            service: Service or contract used as the resolution key.

        Returns:
            The application-owned instance compatible with the key.
        """
        return self.container.make(service)

    async def make_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service graph that may initialize async resources.

        Args:
            service: Service or contract used as the resolution key.

        Returns:
            The instance resolved through the async lifecycle.
        """
        return await self.container.make_async(service)

    @contextmanager
    def context(self) -> Generator[None, None, None]:
        """Bind this application for synchronous or task-local facade use.

        Yields:
            Control while facades resolve services from this application.

        Notes:
            ContextVar restoration applies on exceptions and cancellation.
        """
        with self._bind_context():
            yield

    @contextmanager
    def _bind_context(
        self,
        scope: object | None = None,
    ) -> Generator[ActiveApplicationContext, None, None]:
        """Bind URI services and the canonical active application together.

        Args:
            scope: Optional execution scope visible during service resolution.

        Yields:
            The active application context for this execution.

        Notes:
            Services resolve lazily from this container. ContextVar tokens
            restore nested applications and concurrent tasks independently.
        """
        with (
            bind_application_context(
                self,
                self.container,
                scope,
            ) as active,
            bind_uri_services(
                lambda: self.container.make(UriUrlGenerator),
                lambda: self.container.make(ResponseFactory),
            ),
        ):
            yield active

    @asynccontextmanager
    async def execution_scope(
        self,
        scope: Scope,
    ) -> AsyncGenerator[ContainerScope, None]:
        """Bind this app and one async execution scope until cleanup.

        Args:
            scope: Request, job, workflow, or other native lifecycle scope.

        Yields:
            The active scope used for scope-owned dependency resolution.

        Side Effects:
            Closes resources created within the scope on exit, failure, or
            cancellation.

        Raises:
            RuntimeError: If the application is stopping or stopped.
        """
        if self._closed:
            raise RuntimeError(_APPLICATION_CLOSED_ERROR)
        async with self.container.scope(scope) as active_scope:
            with self._bind_context(active_scope):
                yield active_scope

    asgi: FastAPI
    container: Container
    _config_repository: ConfigRepository
    _logging_manager: LoggingManager
    _http_configuration: HttpConfiguration
    _router: Router
    _url_generator: UrlGenerator
    _config_manager: ConfigManager
    _service_providers: tuple[ServiceProvider, ...]
    _lifecycle_stack: AsyncExitStack
    _started: bool
    _starting: bool
    _closed: bool
    _routes_installed: bool
    _standalone_context: AbstractContextManager[ActiveApplicationContext] | None


def _application_metadata(
    repository: ConfigRepository,
) -> tuple[str, bool]:
    """Read validated metadata without requiring optional typed access.

    Args:
        repository: Effective application configuration implementation.

    Returns:
        Application title and debug flag for ASGI composition.

    Raises:
        ConfigValueError: If either supported metadata value has an invalid
            type. Rejected values are represented by type only.
    """
    name = repository.get(_APP_NAME_KEY, "Titanspan")
    if not isinstance(name, str):
        raise ConfigValueError(_APP_NAME_KEY, "a string", name)
    debug_value = repository.get(_APP_DEBUG_KEY, False)
    if type(debug_value) is not bool:
        raise ConfigValueError(_APP_DEBUG_KEY, "a boolean", debug_value)
    return name, debug_value


def _request_id(request: StarletteRequest) -> str:
    """Return a bounded request identifier or generate a safe replacement.

    Args:
        request: The active request.

    Returns:
        A printable identifier within the configured maximum length.
    """
    request_id = request.headers.get("x-request-id", "")
    if (
        not request_id
        or len(request_id) > _REQUEST_ID_MAX_LENGTH
        or not request_id.isprintable()
    ):
        return uuid4().hex
    return request_id


async def _request_too_large(
    request: StarletteRequest,
    error: Exception,
) -> StarletteResponse:
    """Return a safe client error for an oversized ASGI request.

    Args:
        request: Server request associated with the rejected body.
        error: Native size-limit exception without request payload data.

    Returns:
        A JSON 413 response without disclosing request contents.
    """
    _ = request, error
    return JsonResponse(
        {"detail": "Request body exceeds the configured size limit."},
        status=413,
    )
