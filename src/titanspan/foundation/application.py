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
from fastapi import FastAPI, Request

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
from titanspan.contracts.logging import LoggingManager
from titanspan.logging import (
    LogCustomizer,
    LoggingConfiguration,
    LoggingServiceProvider,
)

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

    from starlette.types import ASGIApp, Receive, Send
    from starlette.types import Scope as ASGIScope

    from titanspan.container.container import ContainerScope
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
    "Application shutdown requires all execution scopes to finish first."
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

        request = Request(scope, receive=receive)
        request_id = _request_id(request)
        async with self._application.execution_scope(Scope.REQUEST):
            with self._log_manager.context(
                application=self._app_name,
                request_id=request_id,
            ):
                await self._app(scope, receive, send)

    _app: ASGIApp
    _application: Application
    _app_name: str
    _log_manager: LoggingManager


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
        native_container = Container()
        native_container.instance(ServiceContainer, native_container)
        native_container.instance(AsyncServiceContainer, native_container)
        config_provider = ConfigServiceProvider(repository)
        logging_provider = LoggingServiceProvider(
            logging,
            customizers=logging_customizers,
        )
        native_providers: tuple[ServiceProvider, ...] = (
            config_provider,
            logging_provider,
            *service_providers,
        )
        for provider in native_providers:
            provider.register(native_container)
        self._service_providers = native_providers

        active_repository = native_container.make(ConfigRepository)
        app_name, debug = _application_metadata(active_repository)
        log_manager = native_container.make(LoggingManager)
        self.container = native_container
        self._config_repository = active_repository
        self._logging_manager = log_manager
        self._config_manager = config_manager
        self._started = False
        self._starting = False
        self._closed = False
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

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Delegate HTTP hosting to the native application lifecycle.

            The application context remains bound through host startup,
            serving, and shutdown. Native startup rolls back on failure.
            """
            with bind_application_context(self, native_container):
                await self.startup()
                try:
                    yield
                finally:
                    await self.shutdown()

        self.asgi = FastAPI(
            title=app_name,
            debug=debug,
            lifespan=lifespan,
        )
        self.asgi.state.titanspan_config = active_repository
        self.asgi.state.titanspan_logging = log_manager

        if integration_container is not None:
            setup_fastapi_container(
                container=integration_container,
                application=self.asgi,
            )
        # Add this after the optional route adapter so it is the outermost
        # user middleware and remains active while every response chunk sends.
        self.asgi.add_middleware(
            _ApplicationContextMiddleware,
            application=self,
            app_name=app_name,
            log_manager=log_manager,
        )

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
            with bind_application_context(self, self.container):
                for provider in self._service_providers:
                    if isinstance(provider, BootableServiceProvider):
                        await self.container.call_async(provider.boot)
        except BaseException as startup_error:
            self._closed = True
            try:
                with anyio.CancelScope(shield=True):
                    with bind_application_context(
                        self,
                        self.container,
                    ):
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
        if self.container.active_scope_count:
            raise ScopeError(_ACTIVE_APPLICATION_SCOPE_ERROR)
        self._closed = True
        with bind_application_context(self, self.container):
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
        binding = bind_application_context(self, self.container)
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
        with bind_application_context(self, self.container):
            yield

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
            with bind_application_context(
                self,
                self.container,
                active_scope,
            ):
                yield active_scope

    asgi: FastAPI
    container: Container
    _config_repository: ConfigRepository
    _logging_manager: LoggingManager
    _config_manager: ConfigManager
    _service_providers: tuple[ServiceProvider, ...]
    _lifecycle_stack: AsyncExitStack
    _started: bool
    _starting: bool
    _closed: bool
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


def _request_id(request: Request) -> str:
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
