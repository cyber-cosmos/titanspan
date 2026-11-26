"""Compose application services and own their execution lifecycles.

Foundation connects configuration, logging, service providers, the native
container, and the application context at one composition boundary.
"""

from __future__ import annotations

from contextlib import (
    AsyncExitStack,
    asynccontextmanager,
    contextmanager,
)
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from titanspan._application_context import bind_application_context
from titanspan.config import (
    ConfigManager,
    ConfigServiceProvider,
    ConfigValueError,
    Settings,
)
from titanspan.container import Container, Scope
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
    from collections.abc import AsyncGenerator, Generator, Mapping, Sequence

    from starlette.middleware.base import RequestResponseEndpoint

    from titanspan.container.container import ContainerScope
    from titanspan.logging.logger import Logger

_REQUEST_ID_MAX_LENGTH = 128
_APP_NAME_KEY = "app.name"
_APP_DEBUG_KEY = "app.debug"
_CONFIGURATION_SOURCE_CONFLICT = (
    "Pass either config overrides or config_repository, not both."
)


class Application:
    """Compose one application container and its optional ASGI adapter.

    Native providers register against ``container`` before graph resolution.
    FastAPI route injection remains an explicitly separate interoperability
    boundary while ordinary application services resolve through Titanspan.

    Attributes:
        asgi: FastAPI application served by an ASGI server.
        container: Canonical native service container for this application.
        settings: Validated settings resolved on access.

    Notes:
        Bind ``context`` around non-ASGI application work before using
        component facades. ASGI middleware binds a request scope automatically.
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
            Loads trusted configuration files and composes application-owned
            containers. Logging and container resources close at ASGI shutdown.
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
        log_manager = native_container.make(LoggingManager)
        app_name, debug = _application_metadata(active_repository)
        self.container = native_container
        self._config_repository = active_repository
        self._logging_manager = log_manager
        self._config_manager = config_manager

        integration_container = create_fastapi_container(
            [*providers, config_provider]
        )

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Boot application providers and finalize services in reverse.

            Registration is complete before startup, so boot dependencies
            resolve from the same graph as facades and application services.
            ExitStack runs every registered cleanup if boot fails or is
            cancelled.
            """
            with bind_application_context(self, native_container):
                async with AsyncExitStack() as resources:
                    resources.push_async_callback(integration_container.close)
                    resources.push_async_callback(native_container.aclose)
                    resources.push_async_callback(log_manager.aclose)
                    for provider in self._service_providers:
                        if isinstance(provider, BootableServiceProvider):
                            await native_container.call_async(provider.boot)
                    yield

        self.asgi = FastAPI(
            title=app_name,
            debug=debug,
            lifespan=lifespan,
        )
        self.asgi.state.titanspan_config = active_repository
        self.asgi.state.titanspan_logging = log_manager

        @self.asgi.middleware("http")
        async def bind_request_context(
            request: Request,
            call_next: RequestResponseEndpoint,
        ) -> Response:
            """Bind application services and request metadata per request.

            Args:
                request: Active request whose safe identifier is captured.
                call_next: Remaining ASGI middleware and endpoint stack.

            Returns:
                Response produced by the downstream application.
            """
            request_id = _request_id(request)
            async with self.execution_scope(Scope.REQUEST):
                with log_manager.context(
                    application=app_name,
                    request_id=request_id,
                ):
                    return await call_next(request)

        setup_fastapi_container(
            container=integration_container,
            application=self.asgi,
        )

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
        """
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
