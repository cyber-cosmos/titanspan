"""Verify configuration, logging, providers, and container composition.

These tests exercise the application composition root rather than constructing
facades or framework services through isolated test registries.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, cast, overload

import pytest

from titanspan import Application
from titanspan._application_context import (
    ApplicationContextError,
    active_application_context,
)
from titanspan.config import ConfigCapabilityError
from titanspan.container import Scope, ScopeError
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

_PROVIDER_FAILURE_MESSAGE = "provider startup failed"
_RESOURCE_CLEANUP_FAILURE_MESSAGE = "resource cleanup failed"

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


class _LifecycleResource:
    """Track a container-owned resource across application lifecycle hooks.

    Attributes:
        closed: Whether the native container finalized the resource.
    """

    def __init__(self, events: list[str]) -> None:
        """Retain a test-owned event sink for resource finalization.

        Args:
            events: Ordered lifecycle observations shared by the test.
        """
        self.closed = False
        self._events = events

    def close(self) -> None:
        """Record finalization and preserve its observable order.

        The event list makes resource shutdown relative to logging cleanup
        testable.
        """
        if active_application_context() is not None:
            self._events.append("application-context-active-during-close")
        self.closed = True
        self._events.append("resource-closed")

    closed: bool
    _events: list[str]


class _LifecycleProvider:
    """Register and initialize a resource through the native application.

    Attributes:
        events: Ordered observations of registration and cleanup.
    """

    def __init__(
        self,
        events: list[str],
        *,
        fail_during_boot: bool = False,
        fail_during_cleanup: bool = False,
    ) -> None:
        """Configure successful or failing application startup.

        Args:
            events: Ordered observations populated by hooks and resources.
            fail_during_boot: Whether startup raises after resolving a resource.
            fail_during_cleanup: Whether finalization raises after recording.
        """
        self.events = events
        self._fail_during_boot = fail_during_boot
        self._fail_during_cleanup = fail_during_cleanup

    def register(self, container: ServiceRegistry) -> None:
        """Register the lifecycle resource before application startup.

        Args:
            container: Canonical registry owned by the application.
        """
        container.singleton(_LifecycleResource, self._resource)
        self.events.append("registered")

    async def _resource(self) -> AsyncIterator[_LifecycleResource]:
        """Yield a managed resource and record deterministic cleanup.

        Yields:
            The resource owned by the application's container.
        """
        resource = _LifecycleResource(self.events)
        self.events.append("resource-created")
        try:
            yield resource
        finally:
            resource.close()
            if self._fail_during_cleanup:
                raise RuntimeError(_RESOURCE_CLEANUP_FAILURE_MESSAGE)

    async def boot(self, resource: _LifecycleResource) -> None:
        """Use the registered resource during native application startup.

        Args:
            resource: Application-owned service resolved by injection.

        Raises:
            RuntimeError: When configured to exercise startup rollback.
        """
        assert not resource.closed
        self.events.append("booted")
        if self._fail_during_boot:
            failure_message = _PROVIDER_FAILURE_MESSAGE
            raise RuntimeError(failure_message)

    events: list[str]
    _fail_during_boot: bool
    _fail_during_cleanup: bool


class _BlockingBootProvider:
    """Hold provider startup until the owning lifecycle releases it.

    The two events give integration tests a deterministic startup barrier for
    checking that shutdown cannot race with partially initialized services.
    """

    def __init__(
        self,
        startup_entered: asyncio.Event,
        finish_startup: asyncio.Event,
    ) -> None:
        """Retain synchronization points for startup coordination.

        Args:
            startup_entered: Event set after boot begins.
            finish_startup: Event that releases the suspended boot operation.
        """
        self._startup_entered = startup_entered
        self._finish_startup = finish_startup

    def register(self, container: ServiceRegistry) -> None:
        """Satisfy the provider lifecycle without adding test services.

        Args:
            container: Canonical application service registry.
        """

    async def boot(self) -> None:
        """Signal entry and wait for the test to allow startup completion.

        Side Effects:
            Suspends until the paired release event is set.
        """
        self._startup_entered.set()
        await self._finish_startup.wait()

    _startup_entered: asyncio.Event
    _finish_startup: asyncio.Event


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
async def test_application_lifecycle_runs_without_an_asgi_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start and stop application services independently of HTTP hosting.

    Provider boot uses the canonical container and its resource is finalized
    by the same native shutdown operation used by the ASGI adapter.

    Args:
        monkeypatch: Wraps real logger cleanup to observe ownership ordering.
    """
    events: list[str] = []
    application = Application(
        service_providers=[_LifecycleProvider(events)],
    )
    close_logging_sync = application.logging.close

    def observe_logging_cleanup() -> None:
        """Record logging finalization before delegating to the manager.

        The test compares the manager's real cleanup with native resource
        finalization through one ordered event sequence.
        """
        events.append("logging-closed")
        close_logging_sync()

    monkeypatch.setattr(
        application.logging,
        "close",
        observe_logging_cleanup,
    )

    await application.startup()

    resource = application.make(_LifecycleResource)
    assert events == ["registered", "resource-created", "booted"]
    assert not resource.closed
    with application.context():
        active = active_application_context()
        assert active is not None
        assert active.application is application

    await application.shutdown()

    assert resource.closed
    assert events[-2:] == ["resource-closed", "logging-closed"]
    assert active_application_context() is None


@pytest.mark.anyio
async def test_application_startup_and_shutdown_are_idempotent() -> None:
    """Keep repeated lifecycle calls safe and reject a stopped restart.

    Standalone workers may share startup hooks with host integrations, so
    repeated calls must not duplicate initialization or finalization.
    """
    events: list[str] = []
    application = Application(
        service_providers=[_LifecycleProvider(events)],
    )

    await application.startup()
    await application.startup()
    await application.shutdown()
    await application.shutdown()

    assert events.count("booted") == 1
    assert events.count("resource-closed") == 1
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        await application.startup()


@pytest.mark.anyio
async def test_shutdown_is_rejected_while_provider_startup_is_active() -> None:
    """Prevent teardown from racing with provider initialization.

    Events provide a deterministic barrier so shutdown is attempted only
    after startup has entered the provider's asynchronous boot operation.
    """
    startup_entered = asyncio.Event()
    finish_startup = asyncio.Event()
    provider = _BlockingBootProvider(startup_entered, finish_startup)
    application = Application(service_providers=[provider])
    startup_task = asyncio.create_task(application.startup())

    await startup_entered.wait()
    with pytest.raises(RuntimeError, match="startup is in progress"):
        await application.shutdown()

    finish_startup.set()
    await startup_task
    await application.shutdown()


@pytest.mark.anyio
async def test_async_context_reentry_is_rejected() -> None:
    """Reject overlapping standalone context ownership for one app.

    The application context is task-local, but a single lifecycle owner must
    still have unambiguous responsibility for finalization.
    """
    application = Application()

    async with application:
        with pytest.raises(RuntimeError, match="already active"):
            await application.__aenter__()


@pytest.mark.anyio
async def test_native_dependency_rejects_resolution_without_app_context() -> (
    None
):
    """Require native HTTP dependency resolution to use its owning app.

    This prevents an ASGI dependency callable from silently resolving a
    service through another application's active container.
    """
    application = Application()
    dependency = application.dependency(_Marker)

    with pytest.raises(ApplicationContextError, match="active context"):
        await dependency()

    await application.shutdown()


@pytest.mark.anyio
async def test_closed_application_rejects_new_execution_scopes() -> None:
    """Prevent new scoped resources after application shutdown.

    Closed containers cannot safely create resources whose owner has already
    finalized its application lifecycle.
    """
    application = Application()
    await application.shutdown()

    with pytest.raises(RuntimeError, match="cannot be restarted"):
        async with application.execution_scope(Scope.REQUEST):
            pytest.fail("a closed application opened an execution scope")


@pytest.mark.anyio
async def test_shutdown_rejects_active_scopes_without_losing_cleanup() -> None:
    """Keep lifecycle callbacks available until execution scopes have exited.

    A rejected shutdown must leave the application usable so the owner can
    finish active work and retry finalization afterward.
    """
    events: list[str] = []
    application = Application(
        service_providers=[_LifecycleProvider(events)],
    )
    await application.startup()

    async with application.execution_scope(Scope.REQUEST):
        with pytest.raises(ScopeError, match="execution scopes"):
            await application.shutdown()
        assert application.container.active_scope_count == 1
        assert not application.make(_LifecycleResource).closed

    await application.shutdown()

    assert events[-1] == "resource-closed"


@pytest.mark.anyio
async def test_application_async_context_manages_native_lifecycle() -> None:
    """Keep the active application context through standalone work.

    The async context manager offers command and worker entry points a
    structured startup, active-context, and shutdown boundary.
    """
    events: list[str] = []
    application = Application(
        service_providers=[_LifecycleProvider(events)],
    )

    async with application as active_application:
        assert active_application is application
        active = active_application_context()
        assert active is not None
        assert active.application is application
        assert not application.make(_LifecycleResource).closed

    assert events[-1] == "resource-closed"
    assert active_application_context() is None


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
    events: list[str] = []
    application = Application(
        config={
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        },
        service_providers=[
            _LifecycleProvider(events, fail_during_boot=True),
        ],
    )

    with pytest.raises(RuntimeError, match=_PROVIDER_FAILURE_MESSAGE):
        await application.startup()

    assert "application-context-active-during-close" in events
    assert events[-1] == "resource-closed"
    assert active_application_context() is None
    with pytest.raises(LogLifecycleError):
        application.logging.channel()


@pytest.mark.anyio
async def test_startup_failure_remains_primary_on_cleanup_failure() -> None:
    """Preserve the boot error while reporting a failed finalizer.

    Startup rollback must continue closing the other owned resources and
    attach cleanup failure details without replacing the original cause.
    """
    events: list[str] = []
    application = Application(
        service_providers=[
            _LifecycleProvider(
                events,
                fail_during_boot=True,
                fail_during_cleanup=True,
            ),
        ],
    )

    with pytest.raises(
        RuntimeError,
        match=_PROVIDER_FAILURE_MESSAGE,
    ) as startup_error:
        await application.startup()

    assert startup_error.value.__cause__ is not None
    assert any(
        "Application cleanup also failed" in note
        for note in startup_error.value.__notes__
    )
    assert events[-1] == "resource-closed"
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
