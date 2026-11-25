"""Verify declarative lifetime metadata on service classes.

These declarations must affect backend graph lifetimes without replacing
the decorated Python classes.
"""

import pytest

from titanspan.container import (
    BindingError,
    Container,
    Scope,
    scoped,
    singleton,
)


@singleton
class DeclaredSingleton:
    """Represent a class with application-owned lifetime metadata.

    Instances should be reused by one container and isolated from others.
    """


@scoped(Scope.NODE)
class DeclaredNodeService:
    """Represent a class whose instance belongs to one node scope.

    Independent node scopes must receive independent service instances.
    """


class SingletonConsumer:
    """Depend on a declared singleton through ordinary type injection.

    This root also verifies shared identity across separately composed graphs.
    """

    def __init__(self, service: DeclaredSingleton) -> None:
        """Store the dependency resolved for this consumer.

        Args:
            service: Application-owned service provided by the container.
        """
        self.service = service


@pytest.mark.anyio
async def test_singleton_decorator_preserves_class_and_identity() -> None:
    """Resolve decorated services once per owning container.

    Separate containers must not share application-owned instances.
    """
    async with Container() as first_container:
        first = await first_container.make(DeclaredSingleton)
        second = await first_container.make(DeclaredSingleton)
        assert first is second

    async with Container() as second_container:
        third = await second_container.make(DeclaredSingleton)
        assert third is not first


@pytest.mark.anyio
async def test_singleton_declaration_survives_graph_expansion() -> None:
    """Reuse declared singletons across independently composed roots.

    Resolving another root must not reset the decorated service cache.
    """
    async with Container() as container:
        consumer = await container.make(SingletonConsumer)
        service = await container.make(DeclaredSingleton)
        assert consumer.service is service


@pytest.mark.anyio
async def test_scoped_decorator_uses_declared_execution_scope() -> None:
    """Cache a decorated dependency only inside its declared scope.

    Repeated resolution within a node reuses the instance; a new node does not.
    """
    async with Container() as container, container.scope(Scope.WORKFLOW):
        async with container.scope(Scope.NODE) as node:
            first = await node.make(DeclaredNodeService)
            second = await node.make(DeclaredNodeService)
            assert first is second

        async with container.scope(Scope.NODE) as next_node:
            third = await next_node.make(DeclaredNodeService)
            assert third is not first


def test_scoped_decorator_rejects_application_lifetime() -> None:
    """Require singleton metadata for application-owned declarations.

    The API should not permit two decorator spellings for one lifetime.
    """
    with pytest.raises(BindingError, match="Use singleton"):
        scoped(Scope.APPLICATION)


def test_conflicting_class_declarations_fail_explicitly() -> None:
    """Reject contradictory lifetime metadata on one class.

    Silent precedence would make cache behavior depend on decorator order.
    """
    with pytest.raises(BindingError, match="conflicting lifetimes"):
        scoped(Scope.NODE)(DeclaredSingleton)


@pytest.mark.anyio
async def test_explicit_binding_overrides_class_declaration() -> None:
    """Allow an application registry to override class-level metadata.

    An explicit transient registration must not inherit singleton caching.
    """
    async with Container() as container:
        container.bind(DeclaredSingleton)
        assert not container.is_shared(DeclaredSingleton)
        first = await container.make(DeclaredSingleton)
        second = await container.make(DeclaredSingleton)
        assert first is not second
