"""Verify explicit context values in native execution scopes.

These tests exercise scope instance seeding through the real dependency
engine so request and job context can be injected without global bindings.
"""

import pytest

from titanspan.container import Container, Scope, ScopeError

pytestmark = pytest.mark.unit


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


def test_scope_rejects_values_after_graph_composition() -> None:
    """Reject new values after a scope graph has been composed.

    Existing graph generations cannot be safely amended in place.
    """
    container = Container()

    with container.scope(Scope.REQUEST) as request_scope:
        container.make(ExecutionMetadata)

        with pytest.raises(ScopeError, match="before resolving"):
            request_scope.provide_instance(
                MetadataConsumer,
                MetadataConsumer(ExecutionMetadata()),
            )


def test_scope_rejects_duplicate_and_inactive_instance_registration() -> None:
    """Reject duplicate values and writes after scope finalization.

    The scope owns resolution state but not caller-provided objects.
    """
    container = Container()
    request_scope = container.scope(Scope.REQUEST)
    metadata = ExecutionMetadata()

    with request_scope:
        request_scope.provide_instance(ExecutionMetadata, metadata)

        with pytest.raises(ScopeError, match="cannot replace"):
            request_scope.provide_instance(
                ExecutionMetadata,
                ExecutionMetadata(),
            )

    with pytest.raises(ScopeError, match="not active"):
        request_scope.provide_instance(
            MetadataConsumer,
            MetadataConsumer(metadata),
        )
