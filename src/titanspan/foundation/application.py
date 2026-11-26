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
from inspect import isawaitable
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast
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
    ApplicationExceptionHandler,
    ApplicationLifecycleCallback,
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
from titanspan.foundation.builder import ApplicationBuilder
from titanspan.foundation.exceptions import ApplicationLifecycleError
from titanspan.http import HttpServiceProvider, JsonResponse, Request
from titanspan.http._backends.asgi import create_request_boundary
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
_APP_ENVIRONMENT_KEY = "app.env"
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
    "Application shutdown requires active execution scopes, overrides, and "
    "service resolution operations to finish first."
)
_INVALID_MIDDLEWARE_RESPONSE_ERROR = (
    "Native HTTP middleware must return an ASGI-compatible response."
)
_INVALID_EXCEPTION_RESPONSE_ERROR = (
    "Native exception handlers must return a Titanspan ASGI response."
)
_DEFAULT_SERVER_ERROR = "Internal server error."
_INVALID_ENVIRONMENT_ERROR = "Application environment must not be empty."
_LIFECYCLE_REGISTRATION_ERROR = (
    "Lifecycle hooks and exception handlers must be registered before startup."
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
        request_boundary = create_request_boundary(
            scope,
            receive,
            request_id=request_id,
            configuration=server,
        )
        native_request = request_boundary.request
        async with self._application.execution_scope(Scope.REQUEST) as active:
            active.provide_instance(Request, native_request)
            active.provide_instance(HttpRequest, native_request)
            try:
                with self._log_manager.context(
                    application=self._app_name,
                    request_id=request_id,
                ):
                    await self._app(scope, request_boundary.receive, send)
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
        startup_callbacks: Sequence[ApplicationLifecycleCallback] = (),
        shutdown_callbacks: Sequence[ApplicationLifecycleCallback] = (),
        exception_handlers: (
            Mapping[type[Exception], ApplicationExceptionHandler] | None
        ) = None,
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
            startup_callbacks: Callbacks run after provider boot.
            shutdown_callbacks: Callbacks run before owned resources close.
            exception_handlers: Native request and response exception handlers.

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
        self._base_path = config_manager.base_path
        self._http_configuration = http_configuration
        self._environment = _application_environment(active_repository)
        self._router = routing_provider.router
        self._url_generator = routing_provider.url_generator
        self._started = False
        self._starting = False
        self._closed = False
        self._routes_installed = False
        self._standalone_context: (
            AbstractContextManager[ActiveApplicationContext] | None
        ) = None
        self._startup_callbacks = list(startup_callbacks)
        self._shutdown_callbacks = list(shutdown_callbacks)
        self._exception_handlers = dict(
            {} if exception_handlers is None else exception_handlers
        )

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
        asgi.add_exception_handler(Exception, self._unhandled_exception)
        for exception_type, handler in self._exception_handlers.items():
            asgi.add_exception_handler(
                exception_type,
                self._exception_handler_adapter(handler),
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
            for callback in self._shutdown_callbacks:
                self._lifecycle_stack.push_async_callback(
                    self._run_lifecycle_callback,
                    callback,
                )
            await self.container.start()
            with self._bind_context():
                await self._complete_startup()
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

    async def _complete_startup(self) -> None:
        """Boot providers and finalize application startup in order.

        Provider hooks run before application startup hooks. Cleanup callbacks
        were armed before container startup so partial startup can roll back.
        """
        for provider in self._service_providers:
            if isinstance(provider, BootableServiceProvider):
                await self.container.call_async(provider.boot)
        for callback in self._startup_callbacks:
            await self._run_lifecycle_callback(callback)
        install_routes(
            self.asgi,
            self._router,
            self.container,
            self._url_generator,
        )
        self._routes_installed = True

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
            or self.container.active_resolution_count
        ):
            raise ScopeError(_ACTIVE_APPLICATION_SCOPE_ERROR)
        # Atomically prevent direct container users from starting work after
        # the count check and before owned resources begin finalization.
        self.container.stop_accepting()
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

    @classmethod
    def builder(cls) -> ApplicationBuilder:
        """Return a typed builder that creates this application class.

        Returns:
            A builder that collects options for the canonical composition
            root.
        """
        return ApplicationBuilder(cls)

    async def run[ResultT](
        self,
        operation: Callable[..., ResultT] | Callable[..., Awaitable[ResultT]],
        parameters: Mapping[str, object] | None = None,
    ) -> ResultT:
        """Run one standalone operation inside the application lifecycle.

        Args:
            operation: Sync or async callable invoked through the native
                container.
            parameters: Explicit callable values keyed by parameter name.

        Returns:
            The operation result after application shutdown completes.

        Raises:
            Exception: If startup, operation, or cleanup fails.
        """
        async with self:
            return await self.container.call_async(operation, parameters)

    def on_startup(
        self,
        callback: ApplicationLifecycleCallback,
    ) -> None:
        """Register a synchronous or asynchronous startup callback.

        Callbacks run after provider boot and before native route installation.
        They use captured application services rather than dependency
        injection; providers own injected initialization.

        Args:
            callback: Zero-argument startup callable.

        Raises:
            ApplicationLifecycleError: If startup has begun or ended.
        """
        self._ensure_lifecycle_registration("startup callback")
        self._startup_callbacks.append(callback)

    def on_shutdown(
        self,
        callback: ApplicationLifecycleCallback,
    ) -> None:
        """Register a zero-argument cleanup callback.

        Callbacks run in reverse registration order before owned resources
        close. They must use captured references because the container has
        stopped accepting new resolutions.

        Args:
            callback: Synchronous or asynchronous cleanup callable.

        Raises:
            ApplicationLifecycleError: If startup has begun or ended.
        """
        self._ensure_lifecycle_registration("shutdown callback")
        self._shutdown_callbacks.append(callback)

    def add_exception_handler[ExceptionT: Exception](
        self,
        exception_type: type[ExceptionT],
        handler: ApplicationExceptionHandler,
    ) -> None:
        """Register a native exception renderer before startup.

        The handler receives injected services and explicit ``request`` and
        ``exception`` parameters. It must return a Titanspan ASGI response.

        Args:
            exception_type: Exception class selected by the ASGI adapter.
            handler: Sync or async callback using native HTTP contracts.

        Raises:
            ApplicationLifecycleError: If startup has begun or ended.
        """
        self._ensure_lifecycle_registration("exception handler")
        self._exception_handlers[exception_type] = handler
        self.asgi.add_exception_handler(
            exception_type,
            self._exception_handler_adapter(handler),
        )

    def report_exception(
        self,
        error: Exception,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Report one application failure through the shared logger.

        Args:
            error: Exception to report.
            context: Safe structured context that excludes request secrets.
        """
        self._logging_manager.channel().exception(
            "Application operation failed",
            context,
            exception=error,
        )

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
    def base_path(self) -> Path:
        """Return the resolved root used by application configuration.

        Returns:
            The application base directory.
        """
        return self._base_path

    @property
    def config_path(self) -> Path:
        """Return the conventional application configuration directory.

        Returns:
            The path under ``base_path`` reserved for configuration files.
        """
        return self.path("config")

    @property
    def bootstrap_path(self) -> Path:
        """Return the conventional application bootstrap directory.

        Returns:
            The path under ``base_path`` reserved for bootstrap artifacts.
        """
        return self.path("bootstrap")

    @property
    def storage_path(self) -> Path:
        """Return the conventional application storage directory.

        Returns:
            The path under ``base_path`` reserved for runtime storage.
        """
        return self.path("storage")

    @property
    def environment(self) -> str:
        """Return the configured application environment name.

        Returns:
            The non-empty ``app.env`` setting or ``production`` by default.
        """
        return self._environment

    @property
    def debug(self) -> bool:
        """Return the validated application debug setting.

        Returns:
            Whether debug mode is enabled.
        """
        return _application_metadata(self._config_repository)[1]

    @property
    def is_started(self) -> bool:
        """Report whether provider boot completed successfully.

        Returns:
            Whether this application completed startup and remains open.
        """
        return self._started and not self._closed

    def is_environment(self, *environments: str) -> bool:
        """Check whether the active environment matches a supplied name.

        Matching is case-insensitive. An empty argument list returns false.

        Args:
            *environments: Environment names to compare.

        Returns:
            Whether the configured environment matches a supplied name.

        Raises:
            ValueError: If an environment name is empty.
        """
        if any(not environment.strip() for environment in environments):
            raise ValueError(_INVALID_ENVIRONMENT_ERROR)
        selected = {environment.casefold() for environment in environments}
        return self._environment.casefold() in selected

    def path(self, *parts: str) -> Path:
        """Join path segments to the resolved application base directory.

        Args:
            *parts: Path components accepted by :meth:`Path.joinpath`.

        Returns:
            The composed path. This helper does not create directories or
            enforce filesystem containment for untrusted values.
        """
        return self._base_path.joinpath(*parts)

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

    async def _run_lifecycle_callback(
        self,
        callback: ApplicationLifecycleCallback,
    ) -> None:
        """Invoke one zero-argument lifecycle callback.

        Args:
            callback: Synchronous or asynchronous application callback.
        """
        result = callback()
        if isawaitable(result):
            await cast("Awaitable[object]", result)

    def _exception_handler_adapter(
        self,
        handler: ApplicationExceptionHandler,
    ) -> Callable[[StarletteRequest, Exception], Awaitable[StarletteResponse]]:
        """Create an ASGI handler that invokes a native callback.

        Args:
            handler: Registered renderer for the selected exception class.

        Returns:
            An async ASGI adapter that uses the native request scope.
        """

        async def render(
            request: StarletteRequest,
            error: Exception,
        ) -> StarletteResponse:
            """Resolve the native request and render one exception.

            Args:
                request: Backend request represented in the native scope.
                error: Exception selected by the ASGI handler registry.

            Returns:
                The native response accepted by the ASGI host.

            Raises:
                TypeError: If the callback returns a non-ASGI response.
            """
            _ = request
            native_request = await self.container.make_async(HttpRequest)
            response = await self.container.call_async(
                handler,
                {"request": native_request, "exception": error},
            )
            if isawaitable(response):
                response = await response
            return _require_asgi_response(response)

        return render

    async def _unhandled_exception(
        self,
        request: StarletteRequest,
        error: Exception,
    ) -> StarletteResponse:
        """Report an unhandled request failure without exposing its details.

        Args:
            request: Backend request associated with the failure.
            error: Exception raised by route or middleware execution.

        Returns:
            A generic JSON response with HTTP status 500.
        """
        _ = request
        self.report_exception(error)
        response = self.container.make(ResponseFactory).json(
            {"detail": _DEFAULT_SERVER_ERROR},
            status=500,
        )
        return _require_asgi_response(response)

    def _ensure_lifecycle_registration(self, operation: str) -> None:
        """Reject callback or handler changes after startup begins.

        Args:
            operation: Registration operation attempted by the caller.

        Raises:
            ApplicationLifecycleError: If application state is not mutable.
        """
        if self._starting or self._started or self._closed:
            raise ApplicationLifecycleError(
                operation,
                _LIFECYCLE_REGISTRATION_ERROR,
            )

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
    _base_path: Path
    _environment: str
    _service_providers: tuple[ServiceProvider, ...]
    _lifecycle_stack: AsyncExitStack
    _started: bool
    _starting: bool
    _closed: bool
    _routes_installed: bool
    _standalone_context: AbstractContextManager[ActiveApplicationContext] | None
    _startup_callbacks: list[ApplicationLifecycleCallback]
    _shutdown_callbacks: list[ApplicationLifecycleCallback]
    _exception_handlers: dict[type[Exception], ApplicationExceptionHandler]


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


def _application_environment(repository: ConfigRepository) -> str:
    """Read and validate the configured application environment.

    Args:
        repository: Application configuration selected at composition.

    Returns:
        A non-empty environment name.

    Raises:
        ConfigValueError: If the value is not a string.
        ValueError: If the value is empty or contains only whitespace.
    """
    value = repository.get(_APP_ENVIRONMENT_KEY, "production")
    if not isinstance(value, str):
        raise ConfigValueError(_APP_ENVIRONMENT_KEY, "a string", value)
    if not value.strip():
        raise ValueError(_INVALID_ENVIRONMENT_ERROR)
    return value


def _require_asgi_response(response: HttpResponse) -> StarletteResponse:
    """Validate a native response at the private ASGI adapter boundary.

    Args:
        response: Response returned by a native response contract.

    Returns:
        A response accepted by FastAPI and Starlette.

    Raises:
        TypeError: If the value is not an ASGI response.
    """
    if not isinstance(response, StarletteResponse):
        raise TypeError(_INVALID_EXCEPTION_RESPONSE_ERROR)
    return response


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
