"""Verify native contracts can be keys in the Dishka dependency graph.

The integration exercises real service resolution while the application
service remains typed only against a Titanspan-owned protocol.
"""

from collections.abc import Mapping
from typing import overload

import pytest

# Dishka's decorator typing exposes an unknown decorator in strict mode.
from dishka import (
    Provider,
    Scope,
    provide,  # pyright: ignore[reportUnknownVariableType]
)

from titanspan.config import ConfigServiceProvider, Repository
from titanspan.container import Container
from titanspan.container._backends.fastapi import create_fastapi_container
from titanspan.contracts import ConfigRepository

pytestmark = pytest.mark.integration


class ConfigRepositoryAdapter:
    """Provide a test implementation of the native config contract.

    The adapter owns only in-memory values and requires no optional backend.
    """

    def __init__(self) -> None:
        """Initialize application values for the integration case.

        Store the application name used by the resolver assertion.
        """
        self.values: dict[str, object] = {"app.name": "Titanspan"}

    def has(self, key: str) -> bool:
        """Check whether a configuration path is present.

        Args:
            key: A dotted path in the configuration values.

        Returns:
            Whether the path exists, including for a stored ``None``.
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
            key: A dotted path in the configuration values.
            default: Value returned for a missing path.

        Returns:
            The configured value or fallback.
        """

    @overload
    def get(
        self,
        key: list[str] | tuple[str, ...],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several paths in one operation.

        Args:
            key: The requested paths in caller-specified order.
            default: Value substituted for missing paths.

        Returns:
            A mapping from requested paths to values.
        """

    def get(
        self,
        key: str | list[str] | tuple[str, ...],
        default: object = None,
    ) -> object:
        """Retrieve one path or a set of paths.

        Args:
            key: A dotted path or sequence of dotted paths.
            default: Value substituted for absent paths.

        Returns:
            A configured value or mapping of selected values.
        """
        if isinstance(key, str):
            return self.values.get(key, default)
        return {item: self.values.get(item, default) for item in key}

    def all(self) -> Mapping[str, object]:
        """Return a shallow, read-only-typed snapshot of stored values.

        Returns:
            A mapping containing each currently stored path.
        """
        return dict(self.values)

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one path or merge multiple path values.

        Args:
            key: A dotted path or mapping of paths to values.
            value: Value assigned when ``key`` is a string.
        """
        if isinstance(key, str):
            self.values[key] = value
        else:
            self.values.update(key)

    def prepend(self, key: str, value: object) -> None:
        """Insert a value before existing list entries.

        Args:
            key: The configuration path to update.
            value: The value inserted at the beginning.
        """
        existing = self.values.get(key, [])
        assert isinstance(existing, list)
        self.values[key] = [value, *existing]

    def push(self, key: str, value: object) -> None:
        """Append a value after existing list entries.

        Args:
            key: The configuration path to update.
            value: The value appended at the end.
        """
        existing = self.values.get(key, [])
        assert isinstance(existing, list)
        self.values[key] = [*existing, value]


class ConfigRepositoryProvider(Provider):
    """Bind an adapter under the native configuration protocol key.

    Dishka owns dependency graph resolution; this provider only declares the
    implementation selected for the application scope.
    """

    @provide(scope=Scope.APP, provides=ConfigRepository)
    def repository(self) -> ConfigRepositoryAdapter:
        """Create the service registered for the protocol key.

        Returns:
            A concrete in-memory implementation of the config contract.
        """
        return ConfigRepositoryAdapter()


@pytest.mark.anyio
async def test_native_contract_is_a_real_dependency_resolution_key() -> None:
    """Resolve a ConfigRepository without importing its implementation.

    The test verifies protocol-based registration, value retrieval, and
    container cleanup through the real Dishka dependency graph.
    """
    container = create_fastapi_container([ConfigRepositoryProvider()])

    try:
        repository = await container.get(ConfigRepository)
        assert isinstance(repository, ConfigRepository)
        assert repository.get("app.name") == "Titanspan"
    finally:
        await container.close()


@pytest.mark.anyio
async def test_native_container_adapts_config_registration() -> None:
    """Resolve a native config registration through the container facade.

    Exercise container and config components together to verify registration
    adaptation across the real dependency integration boundary.
    """
    repository = Repository({"app": {"name": "Titanspan"}})
    async with Container(providers=(ConfigServiceProvider(repository),)) as (
        container
    ):
        resolved = await container.make_async(ConfigRepository)

    assert resolved is repository
    assert resolved.get("app.name") == "Titanspan"
