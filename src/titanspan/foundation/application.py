"""Provide the initial ASGI application composition root.

Titanspan coordinates FastAPI and Dishka lifecycles while leaving their
underlying application and dependency APIs available to callers.
"""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

from dishka import Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from titanspan.config import Settings
from titanspan.container.container import create_container


class Application:
    """Compose a FastAPI application and own its Dishka container lifecycle.

    Use ``asgi`` to access native FastAPI routers, middleware, state, and
    server integration. Dishka remains responsible for dependency graph
    resolution and resource finalization.

    Attributes:
        asgi: The configured FastAPI application served by an ASGI server.

    Notes:
        Create registrations before serving traffic. The application does not
        mutate the container after construction and is safe to share as an
        ASGI application when its application-scoped services are safe to use
        concurrently.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        providers: Sequence[Provider] = (),
    ) -> None:
        """Build the ASGI app and bind the registered dependency providers.

        Args:
            settings: Validated application settings, or environment-backed
                defaults when omitted.
            providers: Dishka providers that own application dependencies.

        Side Effects:
            Creates a Dishka container and configures FastAPI integration.
            The container is closed when the ASGI lifespan exits.
        """
        app_settings = settings or Settings()
        container = create_container(providers)

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
            """Own the container until the host exits the ASGI lifespan.

            Dishka finalizes yielded resources from ``close``. A ``finally``
            block keeps that cleanup attached to both normal shutdown and
            exceptions raised while the host is serving the application.
            """
            try:
                yield
            finally:
                await container.close()

        self.asgi = FastAPI(
            title=app_settings.app_name,
            debug=app_settings.debug,
            lifespan=lifespan,
        )
        setup_dishka(container=container, app=self.asgi)

    asgi: FastAPI
