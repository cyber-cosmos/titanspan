"""Register native logging services through the application container.

The provider resolves logging settings from the selected configuration
repository and owns the manager factory lifecycle for one application.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from titanspan.contracts.foundation import ApplicationPaths  # noqa: TC001
from titanspan.contracts.logging import LoggingManager, LogWriter
from titanspan.logging.configuration import LoggingConfiguration
from titanspan.logging.exceptions import LogConfigurationError
from titanspan.logging.manager import LogManager

if TYPE_CHECKING:
    from titanspan.contracts.container import ServiceRegistry
    from titanspan.contracts.logging import LogCustomizer
    from titanspan.logging.logger import Logger

# The container resolves this factory's postponed annotation at runtime.
from titanspan.contracts.config import ConfigRepository  # noqa: TC001


class LoggingServiceProvider:
    """Bind one config-driven manager and default logger service.

    The manager factory resolves the canonical configuration contract, so
    applications may substitute a different repository before service graph
    composition. An explicit logging argument has final precedence.
    """

    def __init__(
        self,
        configuration: LoggingConfiguration
        | Mapping[str, object]
        | None = None,
        *,
        customizers: Mapping[str, LogCustomizer[Logger]] | None = None,
    ) -> None:
        """Retain optional bootstrap logging settings and native hooks.

        Args:
            configuration: Explicit final logging configuration, if supplied.
            customizers: Channel customizers keyed by configured name.
        """
        self._configuration = configuration
        self._customizers = dict(customizers or {})

    def register(self, container: ServiceRegistry) -> None:
        """Register logging factories without resolving their dependencies.

        Args:
            container: Shared service registry owned by the application.
        """

        def make_manager(
            repository: ConfigRepository,
            paths: ApplicationPaths,
        ) -> LogManager:
            """Create a manager from explicit or repository settings.

            Args:
                repository: Final repository resolved by the container.
                paths: Effective application root for relative destinations.

            Returns:
                One native, application-owned logging manager.

            Raises:
                LogConfigurationError: If the configured value is not a
                    native logging model or mapping.
            """
            configuration: object = self._configuration
            if self._configuration is None:
                configuration = repository.get("logging")
            if configuration is not None and not isinstance(
                configuration,
                (LoggingConfiguration, Mapping),
            ):
                message = "The [logging] configuration must be a mapping."
                raise LogConfigurationError(message)
            normalized = (
                cast("Mapping[str, object]", configuration)
                if isinstance(configuration, Mapping)
                else configuration
            )
            application_configuration = LoggingConfiguration.from_value(
                normalized,
                base_path=paths.base_path,
            )
            return LogManager(
                application_configuration,
                customizers=self._customizers,
            )

        def make_default_logger(manager: LoggingManager) -> LogWriter:
            """Resolve the manager's cached default channel.

            Args:
                manager: Native manager resolved by the same application.

            Returns:
                The default channel's native logger interface.
            """
            return manager.channel()

        container.singleton(LoggingManager, make_manager)
        container.bind(LogWriter, make_default_logger)


__all__ = ["LoggingServiceProvider"]
