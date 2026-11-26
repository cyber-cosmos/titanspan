"""Declare the application configuration repository registration.

The private container adapter translates this native registration into its
dependency graph while preserving the repository's contract identity.
"""

from titanspan.contracts.config import (
    ConfigDiagnostics,
    ConfigMacroRegistry,
    ConfigReader,
    ConfigRepository,
    ConfigWriter,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.contracts.container import ServiceRegistry


class ConfigServiceProvider:
    """Bind an application-owned repository under its native contract.

    The repository is already constructed by application bootstrap. The
    container adapter reuses that instance for graph resolution.

    Attributes:
        repository_instance: Repository owned by the current application.
    """

    def __init__(self, repository: ConfigRepository) -> None:
        """Retain the repository selected during application construction.

        Args:
            repository: Application-specific contract implementation.
        """
        self.repository_instance = repository

    def register(self, container: ServiceRegistry) -> None:
        """Register this repository with the native application container.

        Args:
            container: Application registry shared by all components.
        """
        # Each key points at the same object. Optional services are exposed
        # only when the selected implementation supports that capability.
        container.instance(ConfigRepository, self.repository_instance)
        container.instance(ConfigReader, self.repository_instance)
        container.instance(ConfigWriter, self.repository_instance)
        if isinstance(self.repository_instance, TypedConfigReader):
            container.instance(TypedConfigReader, self.repository_instance)
        if isinstance(self.repository_instance, ScopedConfigOverrides):
            container.instance(ScopedConfigOverrides, self.repository_instance)
        if isinstance(self.repository_instance, ConfigDiagnostics):
            container.instance(ConfigDiagnostics, self.repository_instance)
        if isinstance(self.repository_instance, ConfigMacroRegistry):
            container.instance(ConfigMacroRegistry, self.repository_instance)

    @property
    def service(self) -> type[object]:
        """Expose the repository contract as a container registration key.

        Returns:
            The canonical configuration repository contract.
        """
        return ConfigRepository

    @property
    def value(self) -> object:
        """Expose the initialized repository through a native registration.

        Returns:
            The repository instance owned by application bootstrap.
        """
        return self.repository_instance


__all__ = ["ConfigServiceProvider"]
