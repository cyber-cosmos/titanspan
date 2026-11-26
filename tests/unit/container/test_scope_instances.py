"""Verify explicit context values in native execution scopes.

These tests exercise scope instance seeding through the real dependency
engine so request and job context can be injected without global bindings.
"""

import pytest

from titanspan.container import Container, Scope


class ExecutionMetadata:
    """Represent immutable metadata supplied by one execution boundary.

    The assertions exercise the application-owned container lifecycle.
    """


class MetadataConsumer:
    """Receive scope-owned execution metadata through constructor injection.

    The assertions exercise the application-owned container lifecycle.
    """

    def __init__(self, metadata: ExecutionMetadata) -> None:
        """Retain the metadata resolved from the active container scope.

        Args:
            metadata: Context value registered by the scope owner.
        """
        self.metadata = metadata

    metadata: ExecutionMetadata


def test_scope_instance_is_injected_into_sync_dependency_graph() -> None:
    """Resolve a seeded instance from a real synchronous scope graph.

    The assertions exercise the application-owned container lifecycle.
    """
    container = Container()
    metadata = ExecutionMetadata()

    with container.scope(Scope.REQUEST) as request_scope:
        request_scope.provide_instance(ExecutionMetadata, metadata)
        consumer = container.make(MetadataConsumer)

    assert consumer.metadata is metadata


@pytest.mark.anyio
async def test_scope_instance_is_injected_into_async_dependency_graph() -> None:
    """Resolve a seeded instance from a real asynchronous scope graph.

    The assertions exercise the application-owned container lifecycle.
    """
    container = Container()
    metadata = ExecutionMetadata()

    async with container.scope(Scope.REQUEST) as request_scope:
        request_scope.provide_instance(ExecutionMetadata, metadata)
        consumer = await container.make_async(MetadataConsumer)

    assert consumer.metadata is metadata
