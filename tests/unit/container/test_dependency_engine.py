"""Verify private type discovery and lifecycle mapping helpers.

These tests exercise metadata adaptation without constructing application
services or exposing the dependency engine through the public API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Protocol

import pytest

# Private helper tests cover invalid metadata that cannot be represented by a
# valid public registration. Suppress only the corresponding name checks.
from titanspan.container._backends.dependency_engine import (
    EngineBinding,
    _class_annotations,  # pyright: ignore[reportPrivateUsage]
    _discover_factory_types,  # pyright: ignore[reportPrivateUsage]
    _discover_types,  # pyright: ignore[reportPrivateUsage]
    _scope_for_name,  # pyright: ignore[reportPrivateUsage]
    discover_dependency_types,
)
from titanspan.container.scope import Scope

if TYPE_CHECKING:

    class UnavailableDependency:
        """Declare a static-only name for forward-reference error tests.

        This class is intentionally absent at runtime so type-hint evaluation
        exercises the adapter's unresolved-reference handling.
        """


class Repository:
    """Represent a concrete constructor dependency for discovery tests.

    Keep this fixture focused on the dependency shape required by its test.
    """


class SearchDependency:
    """Represent another concrete dependency in a typing union.

    Keep this fixture focused on the dependency shape required by its test.
    """


class RepositoryContract(Protocol):
    """Describe the structural contract consumed by a concrete service.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def read(self) -> object:
        """Read a value through the test contract.

        Returns:
            The value exposed by a concrete repository.
        """
        ...


class ConcreteRepository:
    """Implement the contract using a discoverable concrete type.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def read(self) -> object:
        """Return a value through the repository contract.

        Returns:
            A concrete test value.
        """
        return "value"


class ContractConsumer:
    """Consume a protocol dependency selected by a binding.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, repository: RepositoryContract) -> None:
        """Retain the configured contract dependency.

        Args:
            repository: Contract selected through an explicit binding.
        """
        self.repository = repository


class FactoryProduct:
    """Represent a service constructed by an annotated factory.

    Keep this fixture focused on the dependency shape required by its test.
    """


class ConstructorGraph:
    """Declare concrete, scalar, and inherited constructor parameters.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, repository: Repository, retries: int = 3) -> None:
        """Retain the dependency used to validate type inspection.

        Args:
            repository: Automatically discoverable concrete dependency.
            retries: Primitive default that must not become a service key.
        """
        self.repository = repository
        self.retries = retries


class UnresolvedConstructor:
    """Declare a forward reference absent from the active module namespace.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, dependency: UnavailableDependency) -> None:
        """Retain a deliberately unavailable dependency annotation.

        Args:
            dependency: A type that cannot be imported during discovery.
        """


def test_class_annotation_discovery_handles_supported_typing_forms() -> None:
    """Extract service classes from Annotated and union declarations.

    Primitive and unresolved annotations are ignored without importing or
    constructing classes during discovery.
    """
    assert _class_annotations("UnresolvedType") == set()
    assert _class_annotations(Annotated[Repository, "metadata"]) == {
        Repository,
    }
    assert _class_annotations(Repository | SearchDependency) == {
        Repository,
        SearchDependency,
    }
    assert _class_annotations(object()) == set()


def test_constructor_and_factory_discovery_ignore_scalars_and_bad_hints() -> (
    None
):
    """Inspect type dependencies without executing constructors or factories.

    Unresolvable forward references fail closed and do not create guessed
    dependency registrations.
    """

    def factory(
        repository: Repository,
        retries: int,
    ) -> FactoryProduct:
        """Describe a typed factory signature without invoking it.

        Args:
            repository: Concrete service consumed by the factory.
            retries: Primitive argument that is not an injected service.

        Returns:
            The declared factory product type.
        """
        _ = repository, retries
        return FactoryProduct()

    def unresolved_factory(
        dependency: UnavailableDependency,
    ) -> FactoryProduct:
        """Declare a factory with a forward reference that cannot resolve.

        Args:
            dependency: Type intentionally omitted from this module.

        Returns:
            The factory product type.
        """
        _ = dependency
        return FactoryProduct()

    assert _discover_types(ConstructorGraph) == {
        ConstructorGraph,
        Repository,
    }
    assert _discover_types(UnresolvedConstructor) == {UnresolvedConstructor}
    assert _discover_factory_types(factory) == {Repository}
    assert _discover_factory_types(unresolved_factory) == set()


def test_dependency_closure_follows_contracts_factories_and_instances() -> None:
    """Follow explicit implementation and instance registrations safely.

    The closure contains the concrete implementation and preserves an
    externally supplied dependency as a terminal node.
    """

    def factory(repository: Repository) -> FactoryProduct:
        """Describe a factory that consumes an external service.

        Args:
            repository: Service registered as an external instance.

        Returns:
            The product produced after dependency resolution.
        """
        _ = repository
        return FactoryProduct()

    contract_binding = EngineBinding(
        RepositoryContract,
        ConcreteRepository,
        "transient",
        Scope.APPLICATION.value,
    )
    instance_binding = EngineBinding(
        Repository,
        Repository(),
        "singleton",
        Scope.APPLICATION.value,
        is_instance=True,
    )
    factory_binding = EngineBinding(
        FactoryProduct,
        factory,
        "transient",
        Scope.APPLICATION.value,
    )
    non_callable_binding = EngineBinding(
        SearchDependency,
        object(),
        "transient",
        Scope.APPLICATION.value,
    )

    assert RepositoryContract in discover_dependency_types(
        ContractConsumer,
        [contract_binding],
    )
    assert Repository in discover_dependency_types(
        FactoryProduct,
        [factory_binding, instance_binding],
    )
    assert (
        discover_dependency_types(
            SearchDependency,
            [non_callable_binding],
        )
        == frozenset()
    )


def test_scope_names_map_to_known_levels_and_reject_unknown_names() -> None:
    """Translate native lifecycle names and preserve useful mapping errors.

    All declared scope names map to a known backend level, while unknown names
    retain their lookup failure as the native mapping error's cause.
    """
    expected: dict[str, str] = {
        "application": "APP",
        "request": "REQUEST",
        "connection": "REQUEST",
        "job": "REQUEST",
        "workflow": "REQUEST",
        "node": "ACTION",
        "agent": "ACTION",
        "tool": "STEP",
        "task": "STEP",
    }
    for name, scope_name in expected.items():
        assert _scope_for_name(name).name == scope_name

    with pytest.raises(
        ValueError,
        match="Unsupported lifecycle scope",
    ) as error:
        _scope_for_name("unknown")
    assert isinstance(error.value.__cause__, KeyError)
