"""Declare the application configuration repository registration.

The private container adapter translates this native registration into its
dependency graph while preserving the repository's contract identity.
"""

from titanspan.contracts.config_repository import ConfigRepository


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
