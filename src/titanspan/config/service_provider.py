"""Register one application configuration repository with Dishka.

The provider exposes the native contract key and leaves graph resolution and
resource lifecycle handling to the existing container implementation.
"""

from dishka import (
    Provider,
    Scope,
    provide,  # pyright: ignore[reportUnknownVariableType]
)

from titanspan.contracts.config_repository import ConfigRepository


class ConfigServiceProvider(Provider):
    """Bind an application-owned repository under its native contract.

    The repository is already constructed by application bootstrap. Returning
    that same instance ensures facade, container, and FastAPI metadata agree.

    Attributes:
        repository_instance: Repository owned by the current application.
    """

    def __init__(self, repository: ConfigRepository) -> None:
        """Retain the repository selected during application construction.

        Args:
            repository: Application-specific contract implementation.
        """
        super().__init__()
        self.repository_instance = repository

    @provide(scope=Scope.APP, provides=ConfigRepository)
    def repository(self) -> ConfigRepository:
        """Provide the already initialized configuration service.

        Returns:
            The repository bound to the current application.
        """
        return self.repository_instance


__all__ = ["ConfigServiceProvider"]
