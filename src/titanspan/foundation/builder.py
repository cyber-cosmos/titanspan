"""Build one native Application from explicit bootstrap configuration.

The builder only collects inputs. Application remains the sole composition
root and owns every registered service and lifecycle resource.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint, entry_points
from inspect import isclass
from typing import TYPE_CHECKING, Self, cast

from titanspan.contracts.foundation import ServiceProvider
from titanspan.foundation.exceptions import ProviderDiscoveryError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from titanspan.config import Settings
    from titanspan.contracts.foundation.lifecycle import (
        ApplicationExceptionHandler,
        ApplicationLifecycleCallback,
    )
    from titanspan.contracts.http import HttpMiddleware
    from titanspan.foundation.application import Application
    from titanspan.logging import LogCustomizer, LoggingConfiguration
    from titanspan.logging.logger import Logger

_DEFAULT_PROVIDER_GROUP = "titanspan.providers"
_INVALID_PROVIDER_ERROR = "entry point did not provide a ServiceProvider"


class ApplicationBuilder:
    """Collect trusted application options before creating an Application.

    Provider entry points are loaded only when requested. The builder never
    scans application modules or constructs a second service registry.
    """

    def __init__(self, application_type: type[Application]) -> None:
        """Create a builder for the selected application class.

        Args:
            application_type: Application implementation constructed by
                :meth:`build`.
        """
        self._application_type = application_type
        self._base_path: str | Path | None = None
        self._config: dict[str, object] | None = None
        self._settings: Settings | None = None
        self._providers: list[ServiceProvider] = []
        self._external_providers: list[object] = []
        self._middleware: list[type[HttpMiddleware]] = []
        self._logging: LoggingConfiguration | Mapping[str, object] | None = None
        self._logging_customizers: dict[str, LogCustomizer[Logger]] = {}
        self._startup_callbacks: list[ApplicationLifecycleCallback] = []
        self._shutdown_callbacks: list[ApplicationLifecycleCallback] = []
        self._exception_handlers: dict[
            type[Exception], ApplicationExceptionHandler
        ] = {}
        self._discovered_entries: set[tuple[str, str]] = set()

    def with_base_path(self, path: str | Path) -> Self:
        """Set the trusted root used by configuration and path helpers.

        Args:
            path: Application root directory.

        Returns:
            This builder for chained configuration.
        """
        self._base_path = path
        return self

    def with_config(self, values: Mapping[str, object]) -> Self:
        """Set final configuration overrides for the built Application.

        A later call replaces the previous override mapping. This mirrors
        explicit application construction and avoids hidden merge rules.

        Args:
            values: Values applied after trusted configuration sources.

        Returns:
            This builder for chained configuration.
        """
        self._config = dict(values)
        return self

    def with_settings(self, settings: Settings) -> Self:
        """Set the typed settings object used during bootstrap.

        Args:
            settings: Validated Titanspan settings for this application.

        Returns:
            This builder for chained configuration.
        """
        self._settings = settings
        return self

    def with_service_provider(self, provider: ServiceProvider) -> Self:
        """Register one native provider after framework providers.

        Args:
            provider: Provider that contributes native services.

        Returns:
            This builder for chained configuration.
        """
        self._providers.append(provider)
        return self

    def discover_providers(
        self,
        *,
        group: str = _DEFAULT_PROVIDER_GROUP,
    ) -> Self:
        """Load installed providers from one explicitly selected group.

        Installed distributions are trusted application code. Entry points
        are ordered by name and value before they are loaded.

        Args:
            group: Python entry-point group to inspect.

        Returns:
            This builder with discovered providers appended.

        Raises:
            ProviderDiscoveryError: If an entry point fails to load or does
                not provide a provider instance or zero-argument class.
        """
        entries = sorted(
            entry_points(group=group),
            key=lambda item: (item.name, item.value),
        )
        for entry in entries:
            identity = (group, entry.value)
            if identity in self._discovered_entries:
                continue
            self._providers.append(_load_provider(entry))
            self._discovered_entries.add(identity)
        return self

    def with_fastapi_provider(self, provider: object) -> Self:
        """Add one explicit third-party FastAPI interoperability provider.

        Args:
            provider: Backend provider accepted by the private adapter.

        Returns:
            This builder for chained configuration.
        """
        self._external_providers.append(provider)
        return self

    def with_http_middleware(
        self,
        *middleware: type[HttpMiddleware],
    ) -> Self:
        """Append ordered application-wide native HTTP middleware.

        Args:
            *middleware: Middleware classes in outer-to-inner order.

        Returns:
            This builder for chained configuration.
        """
        self._middleware.extend(middleware)
        return self

    def with_logging(
        self,
        configuration: LoggingConfiguration | Mapping[str, object],
    ) -> Self:
        """Set an explicit logging configuration override.

        Args:
            configuration: Native logging settings or a validated mapping.

        Returns:
            This builder for chained configuration.
        """
        self._logging = configuration
        return self

    def with_logging_customizer(
        self,
        name: str,
        customizer: LogCustomizer[Logger],
    ) -> Self:
        """Register a native logger customizer by its configured name.

        Args:
            name: Customizer name referenced by a channel configuration.
            customizer: Callback that configures one native logger.

        Returns:
            This builder for chained configuration.
        """
        self._logging_customizers[name] = customizer
        return self

    def on_startup(
        self,
        callback: ApplicationLifecycleCallback,
    ) -> Self:
        """Append a callback that runs after provider boot.

        Args:
            callback: Zero-argument synchronous or asynchronous callback.

        Returns:
            This builder for chained configuration.
        """
        self._startup_callbacks.append(callback)
        return self

    def on_shutdown(
        self,
        callback: ApplicationLifecycleCallback,
    ) -> Self:
        """Append a callback that runs before resource cleanup.

        Shutdown callbacks run in reverse registration order.

        Args:
            callback: Zero-argument synchronous or asynchronous callback.

        Returns:
            This builder for chained configuration.
        """
        self._shutdown_callbacks.append(callback)
        return self

    def with_exception_handler(
        self,
        exception_type: type[Exception],
        handler: ApplicationExceptionHandler,
    ) -> Self:
        """Register a native exception renderer for the built application.

        Args:
            exception_type: Exception class selected by the ASGI adapter.
            handler: Callable using native request and response contracts.

        Returns:
            This builder for chained configuration.
        """
        self._exception_handlers[exception_type] = handler
        return self

    def build(self) -> Application:
        """Construct the application through its canonical composition root.

        Returns:
            A fully configured, not-yet-started application.
        """
        return self._application_type(
            base_path=self._base_path,
            config=self._config,
            settings=self._settings,
            service_providers=tuple(self._providers),
            providers=tuple(self._external_providers),
            logging=self._logging,
            logging_customizers=self._logging_customizers,
            http_middleware=tuple(self._middleware),
            startup_callbacks=tuple(self._startup_callbacks),
            shutdown_callbacks=tuple(self._shutdown_callbacks),
            exception_handlers=self._exception_handlers,
        )

    _application_type: type[Application]
    _base_path: str | Path | None
    _config: dict[str, object] | None
    _settings: Settings | None
    _providers: list[ServiceProvider]
    _external_providers: list[object]
    _middleware: list[type[HttpMiddleware]]
    _logging: LoggingConfiguration | Mapping[str, object] | None
    _logging_customizers: dict[str, LogCustomizer[Logger]]
    _startup_callbacks: list[ApplicationLifecycleCallback]
    _shutdown_callbacks: list[ApplicationLifecycleCallback]
    _exception_handlers: dict[type[Exception], ApplicationExceptionHandler]
    _discovered_entries: set[tuple[str, str]]


def _load_provider(entry: EntryPoint) -> ServiceProvider:
    """Load and validate one explicitly selected provider entry point.

    Args:
        entry: Installed provider entry point.

    Returns:
        A zero-argument provider instance.

    Raises:
        ProviderDiscoveryError: If loading, construction, or validation
            fails.
    """
    try:
        candidate = entry.load()
        provider = (
            cast("Callable[[], object]", candidate)()
            if isclass(candidate)
            else candidate
        )
    except Exception as error:
        raise ProviderDiscoveryError(
            entry.name,
            type(error).__name__,
        ) from error
    if not isinstance(provider, ServiceProvider):
        raise ProviderDiscoveryError(entry.name, _INVALID_PROVIDER_ERROR)
    return provider


__all__ = ["ApplicationBuilder"]
