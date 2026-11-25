"""Provide the optional native web integration with the dependency engine.

Import this adapter only when the application opts into web integration.
"""

from collections.abc import Sequence

from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from titanspan.container._backends.providers import adapt_providers


def create_fastapi_container(providers: Sequence[object]) -> AsyncContainer:
    """Compose provider registrations with request context support.

    Args:
        providers: Explicit provider objects supplied by an application.

    Returns:
        An asynchronous container for the web integration adapter.

    Notes:
        This is an internal interoperability seam. Ordinary application code
        should register Titanspan-owned bindings through ``Container``.
    """
    backend_providers = adapt_providers(providers)
    return make_async_container(*backend_providers, FastapiProvider())


def setup_fastapi_container(
    container: AsyncContainer,
    application: FastAPI,
) -> None:
    """Attach the private dependency graph to the ASGI application.

    Args:
        container: Graph created for the application's integration providers.
        application: ASGI application receiving dependency middleware.
    """
    setup_dishka(container=container, app=application)
