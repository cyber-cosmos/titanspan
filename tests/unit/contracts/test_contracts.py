"""Verify the public contracts package exposes native typed protocols.

The tests exercise structural conformance and public symbol identity without
instantiating infrastructure implementations.
"""

from collections.abc import Mapping, Sequence
from typing import overload

import pytest

from titanspan import Application
from titanspan.config import ConfigCapabilityError
from titanspan.contracts import (
    AsyncServiceContainer,
    ConfigRepository,
    DeferredDisplayValue,
    FileMetadata,
    HtmlRenderable,
    StorageDisk,
    StorageManager,
)
from titanspan.contracts.config.repository import (
    ConfigRepository as ConfigModule,
)
from titanspan.contracts.container import (
    AsyncServiceContainer as ContainerModule,
)
from titanspan.contracts.filesystem import (
    FileMetadata as MetadataModule,
)
from titanspan.contracts.filesystem import (
    StorageDisk as StorageDiskModule,
)
from titanspan.contracts.filesystem import (
    StorageManager as StorageManagerModule,
)
from titanspan.facades import Config

pytestmark = pytest.mark.unit


class RepositoryFixture:
    """Implement the mutable configuration repository protocol.

    This lightweight test fixture models only the declared semantics.
    """

    def __init__(self) -> None:
        """Create the test repository with one nested value.

        Keep the fixture independent of production configuration code.
        """
        self.values: dict[str, object] = {"app.name": "Titanspan"}

    def has(self, key: str) -> bool:
        """Check whether a configuration key exists, including null values.

        Args:
            key: The dotted configuration key.

        Returns:
            Whether the exact key is stored.
        """
        return key in self.values

    @overload
    def get(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Retrieve one configuration path.

        Args:
            key: The dotted configuration key.
            default: Value returned when the path is missing.

        Returns:
            The stored value or fallback.
        """

    @overload
    def get(
        self,
        key: list[str] | tuple[str, ...],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several configuration paths.

        Args:
            key: The requested paths in caller-specified order.
            default: Value substituted for absent paths.

        Returns:
            A mapping keyed by requested paths.
        """

    @overload
    def get(
        self,
        key: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Retrieve paths with individual fallback values.

        Args:
            key: Paths mapped to fallback values.

        Returns:
            A mapping keyed by requested paths.
        """

    def get(
        self,
        key: str | list[str] | tuple[str, ...] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Retrieve one value or a selected set of values.

        Args:
            key: A dotted key or ordered sequence of keys.
            default: Value returned when a selected key is missing.

        Returns:
            The selected value, default, or mapping of selected values.
        """
        if isinstance(key, str):
            return self.values.get(key, default)
        if isinstance(key, Mapping):
            return self.get_many(key)
        return {item: self.values.get(item, default) for item in key}

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve multiple values using the shared repository operation.

        Args:
            keys: Ordered paths or paths mapped to fallback values.
            default: Value used when an ordered path is missing.

        Returns:
            Values keyed by their requested paths.
        """
        pairs = (
            keys.items()
            if isinstance(keys, Mapping)
            else ((key, default) for key in keys)
        )
        return {key: self.values.get(key, fallback) for key, fallback in pairs}

    def all(self) -> Mapping[str, object]:
        """Return a shallow snapshot of every configuration value.

        Returns:
            A mapping containing the repository's current entries.
        """
        return dict(self.values)

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one key or merge several values into the repository.

        Args:
            key: A dotted key or mapping of key-value pairs.
            value: The value assigned when ``key`` is a string.
        """
        if isinstance(key, str):
            self.values[key] = value
        else:
            self.values.update(key)

    def prepend(self, key: str, value: object) -> None:
        """Prepend a value to a list-valued configuration item.

        Args:
            key: The target configuration key.
            value: The value inserted at the beginning.
        """
        current = self.values.get(key, [])
        assert isinstance(current, list)
        self.values[key] = [value, *current]

    def push(self, key: str, value: object) -> None:
        """Append a value to a list-valued configuration item.

        Args:
            key: The target configuration key.
            value: The value appended at the end.
        """
        current = self.values.get(key, [])
        assert isinstance(current, list)
        self.values[key] = [*current, value]


class ResolvedService:
    """Represent a no-argument dependency for the resolver fixture.

    The test does not model a production container or scope hierarchy.
    """


class ResolverFixture:
    """Implement the async container contract for a local type fixture.

    The fixture demonstrates generic resolution and asynchronous cleanup
    without introducing a second production dependency engine.
    """

    async def get_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Construct a no-argument service by its class key.

        Args:
            service: The service class to instantiate.

        Returns:
            An instance whose type matches the requested class.
        """
        return service()

    async def close(self) -> None:
        """Complete the fixture's no-op resource lifecycle.

        The fixture owns no resources to finalize.
        """


def test_contract_exports_preserve_canonical_identity() -> None:
    """Re-export contract types without creating duplicate identities.

    This keeps imports stable for Support and future component consumers.
    """
    assert ConfigRepository is ConfigModule
    assert AsyncServiceContainer is ContainerModule
    assert HtmlRenderable.__module__ == (
        "titanspan.contracts.support.html_renderable"
    )
    assert DeferredDisplayValue.__module__ == (
        "titanspan.contracts.support.deferred_display_value"
    )
    assert FileMetadata is MetadataModule
    assert StorageDisk is StorageDiskModule
    assert StorageManager is StorageManagerModule


@pytest.mark.anyio
async def test_async_service_container_preserves_requested_service_type() -> (
    None
):
    """Resolve a generic service and close the structural container fixture.

    This test checks the contract's typing surface, not dependency graph
    semantics supplied by concrete container implementations.
    """
    container: AsyncServiceContainer = ResolverFixture()

    assert isinstance(container, AsyncServiceContainer)
    assert isinstance(
        await container.get_async(ResolvedService), ResolvedService
    )
    await container.close()


def test_config_repository_protocol_is_structural_and_mutable() -> None:
    """Describe get, has, set, collection mutation, and snapshots.

    The protocol remains a contract; this fixture demonstrates how a
    replaceable repository can satisfy the declared interface.
    """
    repository = _configuration_repository(RepositoryFixture())

    assert isinstance(repository, ConfigRepository)
    assert repository.has("app.name")
    assert repository.get("app.name") == "Titanspan"
    assert repository.get(("app.name", "missing"), "fallback") == {
        "app.name": "Titanspan",
        "missing": "fallback",
    }

    repository.set({"features": ["ai"]})
    repository.prepend("features", "web")
    repository.push("features", "data")

    assert repository.get("features") == ["web", "ai", "data"]
    assert repository.all()["app.name"] == "Titanspan"


def test_basic_config_contract_does_not_require_typed_extensions() -> None:
    """Keep optional typed access separate from the base repository API.

    The fixture implements only the canonical read/write contract. A facade
    operation requiring typed validation reports the missing capability.
    """
    application = Application()
    repository = _configuration_repository(RepositoryFixture())

    with application.context(), Config.use(repository):
        assert Config.get("app.name") == "Titanspan"
        with pytest.raises(ConfigCapabilityError):
            Config.string("app.name")


def _configuration_repository(
    repository: ConfigRepository,
) -> ConfigRepository:
    """Check a candidate against the public repository protocol.

    Args:
        repository: A possible configuration repository implementation.

    Returns:
        The same object with its public contract type.
    """
    return repository
