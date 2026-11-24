"""Titanspan container integration for the FastAPI application lifecycle."""

from collections.abc import Sequence

from dishka import AsyncContainer, Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider


def create_container(providers: Sequence[Provider]) -> AsyncContainer:
    """Create the framework container with FastAPI context bindings.

    Dishka owns dependency graph resolution and resource finalization.
    """
    return make_async_container(*providers, FastapiProvider())
