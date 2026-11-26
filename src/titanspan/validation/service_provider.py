"""Register the application-owned Validation service.

The service reads defaults from the canonical configuration repository.
"""

from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.validation import ValidationService
from titanspan.validation.configuration import ValidationConfiguration
from titanspan.validation.validator import Validator


class ValidationServiceProvider:
    """Register one typed validator using application configuration.

    Applications may include this provider in their service-provider list.
    Foundation default registration and exception rendering are coordinated
    separately with their owning component.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind Validation to the canonical ConfigRepository dependency.

        Args:
            container: Application-owned service registry.
        """

        def create_validator(repository: ConfigRepository) -> Validator:
            """Create validation defaults from the active repository.

            Args:
                repository: Config service selected by the active application.

            Returns:
                A stateless adapter with immutable application defaults.
            """
            return Validator(
                ValidationConfiguration.from_repository(repository),
            )

        container.singleton(ValidationService, create_validator)


__all__ = ["ValidationServiceProvider"]
