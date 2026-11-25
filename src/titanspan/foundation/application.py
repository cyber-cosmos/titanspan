"""Provide the initial ASGI application composition root.

Titanspan coordinates FastAPI and Dishka lifecycles while leaving their
underlying application and dependency APIs available to callers.
"""

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from uuid import uuid4

from dishka import Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from titanspan.config import (
    ConfigManager,
    ConfigServiceProvider,
    Repository,
    Settings,
)
from titanspan.container.container import create_container
from titanspan.facades import Config, Log
from titanspan.logging import (
    LogCustomizer,
    LoggingConfiguration,
    LogManager,
)

_REQUEST_ID_MAX_LENGTH = 128


class Application:
    """Compose a FastAPI application and own its Dishka container lifecycle.

    Use ``asgi`` to access native FastAPI routers, middleware, state, and
    server integration. Dishka remains responsible for dependency graph
    resolution and resource finalization.

    Attributes:
        asgi: The configured FastAPI application served by an ASGI server.
        settings: Validated application settings, resolved on access.
        logging: The application-owned native logging manager.

    Notes:
        Create registrations before serving traffic. The application does not
        mutate the container after construction and is safe to share as an
        ASGI application when its application-scoped services are safe to use
        concurrently.
    """

    def __init__(
        self,
        *,
        base_path: str | Path | None = None,
        config: Mapping[str, object] | None = None,
        settings: Settings | None = None,
        providers: Sequence[Provider] = (),
        logging: LoggingConfiguration | Mapping[str, object] | None = None,
        logging_customizers: Mapping[str, LogCustomizer] | None = None,
    ) -> None:
        """Build the ASGI app and bind the registered dependency providers.

        Args:
            base_path: Trusted application root for config and dotenv files.
                The current working directory is used when omitted.
            config: Explicit final bootstrap configuration overrides.
            settings: Validated application settings, or environment-backed
                values when omitted.
            providers: Dishka providers that own application dependencies.
            logging: Optional native logging configuration.
            logging_customizers: Native channel setup hooks keyed by name.

        Side Effects:
            Loads trusted configuration files, creates a Dishka container,
            and configures FastAPI integration. Logging resources and the
            container close when ASGI lifespan exits.
        """
        config_manager = ConfigManager(
            Path.cwd() if base_path is None else base_path,
            settings=settings,
        )
        self._config_manager = config_manager
        config_repository = config_manager.load(overrides=config)
        app_name = config_repository.string("app.name", "Titanspan")
        debug = config_repository.boolean("app.debug", False)
        application_providers = [
            *providers,
            ConfigServiceProvider(config_repository),
        ]
        container = create_container(application_providers)
        log_manager = LogManager(
            logging,
            customizers=logging_customizers,
        )
        self.config = config_repository
        self.logging = log_manager

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Own the container until the host exits the ASGI lifespan.

            Dishka finalizes yielded resources from ``close``. A ``finally``
            block keeps that cleanup attached to both normal shutdown and
            exceptions raised while the host is serving the application.
            """
            async with AsyncExitStack() as resources:
                # Logging closes first while application resources are valid.
                resources.push_async_callback(container.close)
                resources.push_async_callback(log_manager.aclose)
                yield

        self.asgi = FastAPI(
            title=app_name,
            debug=debug,
            lifespan=lifespan,
        )
        self.asgi.state.titanspan_config = config_repository
        self.asgi.state.titanspan_logging = log_manager

        @self.asgi.middleware("http")
        async def bind_request_log_context(
            request: Request,
            call_next: RequestResponseEndpoint,
        ) -> Response:
            """Bind app and request metadata around the HTTP execution scope.

            Args:
                request: The active request whose identifier is captured.
                call_next: The next middleware or endpoint handler.

            Returns:
                The response produced by the remaining application stack.
            """
            request_id = _request_id(request)
            with (
                Config.use(config_repository),
                Log.use(log_manager),
                log_manager.context(
                    application=app_name,
                    request_id=request_id,
                ),
            ):
                return await call_next(request)

        setup_dishka(container=container, app=self.asgi)

    @property
    def settings(self) -> Settings:
        """Return the validated settings owned by this application.

        Settings are resolved lazily so a valid configuration cache does not
        read current environment values during ordinary application startup.

        Returns:
            The settings instance used during configuration composition.
        """
        return self._config_manager.settings

    asgi: FastAPI
    config: Repository
    logging: LogManager
    _config_manager: ConfigManager


def _request_id(request: Request) -> str:
    """Return a bounded client request ID or generate a safe replacement.

    Args:
        request: The active HTTP request.

    Returns:
        A printable request identifier no longer than the configured bound.
    """
    request_id = request.headers.get("x-request-id", "")
    if (
        not request_id
        or len(request_id) > _REQUEST_ID_MAX_LENGTH
        or not request_id.isprintable()
    ):
        return uuid4().hex
    return request_id
