"""Build the Dishka container used by the FastAPI application lifecycle.

Titanspan owns the integration point while Dishka owns dependency resolution
and resource finalization.
"""

from collections.abc import Sequence

from dishka import AsyncContainer, Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider


def create_container(providers: Sequence[Provider]) -> AsyncContainer:
    """Create the framework container with FastAPI context bindings.

    Args:
        providers: Dishka providers registered by the application.

    Returns:
        An asynchronous Dishka container with FastAPI request integration.

    Dishka owns dependency graph resolution and resource finalization.
    """
    # FastAPIProvider supplies request context without replacing Dishka's
    # graph validation or resolution behavior.
    return make_async_container(*providers, FastapiProvider())
