"""Verify configuration, logging, providers, and container composition.

These tests exercise the application composition root rather than constructing
facades or framework services through isolated test registries.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, cast, overload

import pytest

from titanspan import Application
from titanspan._application_context import active_application_context
from titanspan.config import ConfigCapabilityError
from titanspan.contracts.config import (
    ConfigDiagnostics,
    ConfigMacroRegistry,
    ConfigReader,
    ConfigRepository,
    ConfigWriter,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.contracts.container import (
    AsyncServiceContainer,
    ServiceContainer,
)
from titanspan.contracts.logging import LoggingManager, LogWriter
from titanspan.facades import Config, Facade, Log
from titanspan.logging import LogLifecycleError
from titanspan.support import config
from titanspan.support.arr import Arr

if TYPE_CHECKING:
    from titanspan.contracts.container import ServiceRegistry
    from titanspan.contracts.foundation import (
        BootableServiceProvider,
        ServiceProvider,
    )

pytestmark = [pytest.mark.integration, pytest.mark.architecture]


class _Marker:
    """Identify a service registered by a native application provider.

    The value has no behavior because the test verifies registration identity.
    """


class _MarkerProvider:
    """Register one application-owned marker through the container.

    The test uses this provider to verify that user registrations share the
    application-owned service registry.
    """

    def __init__(self, marker: _Marker) -> None:
        """Retain the test instance that application resolution must return.

        Args:
            marker: Externally owned marker instance.
        """
        self._marker = marker

    def register(self, container: ServiceRegistry) -> None:
        """Contribute a native service instance to the application.

        Args:
            container: Application-owned service registry.
        """
        container.instance(_Marker, self._marker)


class _LoggingConsumer:
    """Consume the default logger through its canonical contract key.

    This fixture proves that regular dependency injection and the facade
    resolve the same application-owned logger.
    """

    def __init__(self, logger: LogWriter) -> None:
        """Retain the application-owned logger contract.

        Args:
            logger: Default logger resolved by the application container.
        """
        self.logger = logger

    logger: LogWriter


class _BootProvider:
    """Record provider registration and injected boot lifecycle order.

    The event list makes registration-before-boot ordering observable.
    """

    def __init__(self, events: list[str]) -> None:
        """Retain an ordered event sink for lifecycle verification.

        Args:
            events: Mutable sequence populated during registration and boot.
        """
        self._events = events

    def register(self, container: ServiceRegistry) -> None:
        """Contribute a service before provider boot begins.

        Args:
            container: Application service registry shared by providers.
        """
        container.instance(_Marker, _Marker())
        self._events.append("registered")

    async def boot(self, repository: ConfigRepository) -> None:
        """Use container injection after all providers have registered.

        Args:
            repository: Configuration contract resolved by the application.
        """
        assert repository.get("app.name") == "Booted"
        self._events.append("booted")


class _MappingConfigRepository:
    """Provide an independent mutable mapping-backed config implementation.

    The object uses the shared path helper but owns its storage and mutation
    behavior rather than wrapping the production repository.
    """

    def __init__(self, values: Mapping[str, object]) -> None:
        """Copy initial values into the alternate implementation.

        Args:
            values: Initial values held by this repository instance.
        """
        self._values = dict(values)

    def has(self, key: str) -> bool:
        """Check whether a direct or nested configuration path exists.

        Args:
            key: Configuration path to inspect.

        Returns:
            Whether the path is present in this repository.
        """
        return Arr.has(self._values, key)

    @overload
    def get(self, key: str, default: object = None) -> object:
        """Retrieve one path with an optional fallback.

        Args:
            key: Direct or dotted configuration path.
            default: Value or callback returned when absent.

        Returns:
            The stored value or resolved fallback.
        """

    @overload
    def get(
        self,
        key: list[str] | tuple[str, ...],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several paths with one fallback.

        Args:
            key: Ordered paths to retrieve.
            default: Fallback for missing paths.

        Returns:
            Values keyed by their requested paths.
        """

    @overload
    def get(self, key: Mapping[str, object]) -> Mapping[str, object]:
        """Retrieve several paths with per-path fallbacks.

        Args:
            key: Paths mapped to fallback values.

        Returns:
            Values keyed by their requested paths.
        """

    def get(
        self,
        key: str | Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Read one path or delegate a batch to the batch operation.

        Args:
            key: Path, path sequence, or per-path fallback mapping.
            default: Shared fallback for an ordered path sequence.

        Returns:
            The stored value or selected mapping of values.
        """
        if isinstance(key, str):
            return Arr.get(self._values, key, default)
        return self.get_many(key, default)

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Return several independently selected mapping values.

        Args:
            keys: Paths or paths mapped to fallback values.
            default: Shared fallback for ordered path sequences.

        Returns:
            A dictionary keyed by each requested path.
        """
        pairs = (
            keys.items()
            if isinstance(keys, Mapping)
            else ((key, default) for key in keys)
        )
        return {
            key: Arr.get(self._values, key, fallback) for key, fallback in pairs
        }

    def all(self) -> Mapping[str, object]:
        """Return a detached top-level snapshot of stored configuration.

        Returns:
            An immutable top-level mapping.
        """
        return MappingProxyType(dict(self._values))

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one path or apply a group of path assignments.

        Args:
            key: Dotted path or mapping of assignments.
            value: Value assigned when ``key`` is a path.
        """
        if isinstance(key, Mapping):
            for path, item in key.items():
                Arr.set(self._values, path, item)
        else:
            Arr.set(self._values, key, value)

    def prepend(self, key: str, value: object) -> None:
        """Insert a value before an existing list setting.

        Args:
            key: Dotted path to the list.
            value: Item inserted at index zero.
        """
        items = self.get(key, [])
        assert isinstance(items, list)
        stored_items = cast("list[object]", items)
        self.set(key, [value, *stored_items])

    def push(self, key: str, value: object) -> None:
        """Append a value after an existing list setting.

        Args:
            key: Dotted path to the list.
            value: Item appended to the list.
        """
        items = self.get(key, [])
        assert isinstance(items, list)
        stored_items = cast("list[object]", items)
        self.set(key, [*stored_items, value])


def test_application_shares_contract_services_across_public_access_paths() -> (
    None
):
    """Expose one config and logging service through the app and facades.

    The same configuration repository is visible through contract
    resolution, the application, the facade, and the support helper.
    """
    marker = _Marker()
    application = Application(
        config={
            "app": {"name": "Cohesion", "debug": False},
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        },
        service_providers=[_MarkerProvider(marker)],
    )
    repository = application.make(ConfigRepository)
    container = application.make(ServiceContainer)
    async_container = application.make(AsyncServiceContainer)
    logger = application.make(LogWriter)
    logging_consumer = application.make(_LoggingConsumer)

    assert repository is application.config
    assert container is application.container
    assert async_container is container
    assert application.make(ConfigReader) is repository
    assert application.make(ConfigWriter) is repository
    assert application.make(TypedConfigReader) is repository
    assert application.make(ScopedConfigOverrides) is repository
    assert application.make(ConfigDiagnostics) is repository
    assert application.make(ConfigMacroRegistry) is repository
    assert application.make(_Marker) is marker
    assert application.logging is application.make(LoggingManager)
    assert logger is application.make(LogWriter)
    assert logging_consumer.logger is logger

    with application.context():
        assert Config.repository() is repository
        assert config() is repository
        Config.set("app.name", "Updated")
        with Log.fake() as fake:
            Log.info("application composed")
            fake.assert_logged("info", "application composed")

    assert repository.get("app.name") == "Updated"
    assert application.logging.get_default_channel() == "memory"


@pytest.mark.concurrency
@pytest.mark.anyio
async def test_active_application_context_isolated_between_tasks() -> None:
    """Keep facades bound to each task's application during interleaving.

    An event synchronizes both tasks after context entry so the test verifies
    ContextVar isolation without timing-based sleeps.
    """
    applications = (
        Application(
            config={
                "app": {"name": "first"},
                "logging": {
                    "channels": {"memory": {"driver": "memory"}},
                    "default": "memory",
                },
            }
        ),
        Application(
            config={
                "app": {"name": "second"},
                "logging": {
                    "channels": {"memory": {"driver": "memory"}},
                    "default": "memory",
                },
            }
        ),
    )
    both_ready = asyncio.Event()
    ready_count = 0

    async def read_application(application: Application) -> str:
        """Read and log through one task-local application binding.

        Args:
            application: Application selected for this independent task.

        Returns:
            Its configured application name.
        """
        nonlocal ready_count
        with application.context():
            ready_count += 1
            if ready_count == len(applications):
                both_ready.set()
            await both_ready.wait()
            name = Config.string("app.name")
            with Log.fake() as fake:
                Log.info("task context", application=name)
                record = fake.assert_logged("info", "task context")
                assert record.context["application"] == name
            return name

    names = await asyncio.gather(
        *(read_application(application) for application in applications)
    )

    assert names == ["first", "second"]
    assert all(
        application.logging.get_default_channel() == "memory"
        for application in applications
    )


def test_nested_application_context_restores_the_previous_container() -> None:
    """Restore the outer application after a nested context exits.

    Context-local facade resolution must remain correct when applications
    are nested on one execution stack.
    """
    first = Application(config={"app": {"name": "first"}})
    second = Application(config={"app": {"name": "second"}})

    with first.context():
        assert Config.string("app.name") == "first"
        with second.context():
            assert Config.string("app.name") == "second"
        assert Config.string("app.name") == "first"


def test_facades_resolve_declared_contracts_from_the_shared_base() -> None:
    """Resolve both service facades through one typed base operation.

    Each component declares the contract used for resolution; the active
    application context remains the only production service registry.
    """
    application = Application(config={"app": {"name": "Facade"}})

    assert Config.service_contract is ConfigRepository
    assert Log.service_contract is LoggingManager

    with application.context():
        config_repository: ConfigRepository = Config.resolve_service()
        logging_manager: LoggingManager = Log.resolve_service()

    assert config_repository is application.config
    assert logging_manager is application.logging
    assert issubclass(Config, Facade)
    assert issubclass(Log, Facade)


def test_application_substitutes_an_independent_config_contract() -> None:
    """Use a distinct config implementation through app and facade APIs.

    Container resolution, the facade, and the helper all expose and mutate
    the same substituted contract instance.
    """
    repository: ConfigRepository = _MappingConfigRepository(
        {
            "app": {"name": "Alternate", "debug": False},
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        }
    )
    application = Application(config_repository=repository)

    assert application.make(ConfigRepository) is repository
    assert application.config is repository
    assert application.logging.get_default_channel() == "memory"
    with application.context():
        assert Config.repository() is repository
        assert config() is repository
        assert Config.get("app.name") == "Alternate"
        Config.set("app.name", "Updated")
        assert config("app.name") == "Updated"
        with pytest.raises(ConfigCapabilityError, match="typed retrieval"):
            Config.boolean("app.debug")


def test_explicit_logging_configuration_overrides_repository_settings() -> None:
    """Apply explicit logging bootstrap values after repository settings.

    The logging provider consumes configuration by default while preserving
    a deliberate final override supplied during application construction.
    """
    application = Application(
        config={
            "logging": {
                "default": "configured",
                "channels": {
                    "configured": {"driver": "memory"},
                },
            },
        },
        logging={
            "default": "explicit",
            "channels": {"explicit": {"driver": "memory"}},
        },
    )

    assert application.logging.get_default_channel() == "explicit"


@pytest.mark.anyio
async def test_provider_boot_runs_after_registration_with_injection() -> None:
    """Boot providers in order after registration with typed dependencies.

    The active container resolves provider boot dependencies from the same
    graph that owns configuration and logging.
    """
    events: list[str] = []
    provider: BootableServiceProvider = _BootProvider(events)
    application = Application(
        config={"app": {"name": "Booted"}},
        service_providers=[provider],
    )

    async with application.asgi.router.lifespan_context(application.asgi):
        assert events == ["registered", "booted"]

    assert events == ["registered", "booted"]


@pytest.mark.anyio
async def test_application_context_covers_the_full_asgi_lifespan() -> None:
    """Keep shared facade resolution active through startup and shutdown.

    The same context used for provider boot remains available to application
    lifecycle hooks until the host exits its ASGI lifespan.
    """
    application = Application(
        config={
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        }
    )

    async with application.asgi.router.lifespan_context(application.asgi):
        active = active_application_context()
        assert active is not None
        assert active.application is application
        assert Config.repository() is application.config
        assert Log.manager() is application.logging

    assert active_application_context() is None


@pytest.mark.anyio
async def test_provider_boot_failure_closes_services_and_restores_context() -> (
    None
):
    """Finalize application services when provider startup fails.

    The application context must unwind after the boot error, and the
    initialized logging manager must reject use after cleanup.
    """

    class FailingProvider:
        """Fail startup after all application services are prepared.

        The integration test verifies that partially initialized services
        are still finalized and the active application context is restored.
        """

        def register(self, container: ServiceRegistry) -> None:
            """Leave service registration unchanged for this failure case.

            Args:
                container: Shared registry created by the application.
            """

        async def boot(self) -> None:
            """Fail during the managed provider startup phase.

            Raises:
                RuntimeError: Always, to exercise startup cleanup.
            """
            failure = "provider startup failed"
            raise RuntimeError(failure)

    application = Application(
        config={
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        },
        service_providers=[FailingProvider()],
    )

    with pytest.raises(RuntimeError, match="provider startup failed"):
        async with application.asgi.router.lifespan_context(application.asgi):
            pytest.fail("Application boot should have failed")

    assert active_application_context() is None
    with pytest.raises(LogLifecycleError):
        application.logging.channel()


def test_service_provider_contract_is_used_for_application_registration() -> (
    None
):
    """Require native providers to satisfy the shared structural contract.

    This assignment is a static conformance check and the application test
    above exercises the provider through a real container instance.
    """
    provider: ServiceProvider = _MarkerProvider(_Marker())

    assert callable(provider.register)
