"""FastAPI-backed application with an owned Dishka resource lifecycle."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

from dishka import Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from titanspan.config import Settings
from titanspan.container.container import create_container


class Application:
    """Configure an ASGI application and manage its dependency container."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        providers: Sequence[Provider] = (),
    ) -> None:
        """Build the FastAPI app and bind its Dishka container."""
        app_settings = settings or Settings()
        container = create_container(providers)

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
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
