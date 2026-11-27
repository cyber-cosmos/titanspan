"""Verify configuration, logging, providers, and container composition.

These tests exercise the application composition root rather than constructing
facades or framework services through isolated test registries.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from http import HTTPStatus
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, Self, cast, overload

import httpx2
import pytest
from dishka import Provider
from fastapi.testclient import TestClient

from titanspan import Application, app
from titanspan._application_context import (
    ApplicationContextError,
    active_application_context,
)
from titanspan.config import (
    ConfigCapabilityError,
    ConfigValueError,
    Repository,
)
from titanspan.container import (
    BindingResolutionError,
    FromConfig,
    Scope,
    ScopeError,
)
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
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.filesystem import StorageManager
from titanspan.contracts.hashing import Hasher

# Exception dispatch resolves these postponed annotations through Container.
from titanspan.contracts.http import (
    DEFAULT_COOKIE_OPTIONS,
    CookieOptions,
    HttpRequest,
    HttpResponse,
    ResponseFactory,
)
from titanspan.contracts.logging import LoggingManager, LogWriter
from titanspan.contracts.validation import ValidationService
from titanspan.facades import Config, Event, Facade, Log
from titanspan.filesystem import FilesystemServiceProvider
from titanspan.foundation.exceptions import ApplicationLifecycleError
from titanspan.logging import LogLifecycleError
from titanspan.support import config
from titanspan.support.arr import Arr

_PROVIDER_FAILURE_MESSAGE = "provider startup failed"
_RESOURCE_CLEANUP_FAILURE_MESSAGE = "resource cleanup failed"
_PRIVATE_ROUTE_FAILURE = "private exception detail"
_PRIVATE_EXCEPTION_DETAIL = "credential=foundation-secret-value"
_UNPROCESSABLE_ENTITY = 422
_INTERNAL_SERVER_ERROR = 500
_EXPECTED_COOKIE_COUNT = 3


class _BuilderHeaderMiddleware:
    """Add a response marker through the native middleware contract.

    The marker proves builder middleware participates in real ASGI dispatch.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Add one safe response header after downstream execution.

        Args:
            request: Request scoped to the active application.
            next_handler: Native middleware continuation.

        Returns:
            The downstream response with a builder marker header.
        """
        response = await next_handler(request)
        return response.with_header("X-Builder", "enabled")


class _CookieResponseMiddleware:
    """Exercise native cookie operations on a downstream response.

    The middleware uses contract methods rather than backend response types.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Set and expire cookies without merging their headers.

        Args:
            request: Active request supplied by Foundation.
            next_handler: Native continuation for the endpoint.

        Returns:
            The same response with independent cookie headers.
        """
        response = await next_handler(request)
        return (
            response.with_cookie("session", "opaque")
            .with_cookie(
                "preference",
                "compact",
                options=CookieOptions(secure=False),
            )
            .without_cookie("retired")
        )


class _NonAsgiResponse:
    """Satisfy the native response contract without an ASGI implementation.

    Foundation must reject this value at its explicit interoperability edge.
    """

    @property
    def status_code(self) -> int:
        """Return the contract-required status value.

        Returns:
            An ordinary success status for the test response.
        """
        return 200

    @property
    def headers(self) -> Mapping[str, str]:
        """Return empty response metadata.

        Returns:
            No response headers.
        """
        return {}

    def with_header(self, name: str, value: str) -> Self:
        """Retain the fluent contract without producing an ASGI response.

        Args:
            name: Header name supplied by the caller.
            value: Header value supplied by the caller.

        Returns:
            This response object.
        """
        _ = name, value
        return self

    def with_cookie(
        self,
        name: str,
        value: str,
        *,
        options: CookieOptions = DEFAULT_COOKIE_OPTIONS,
    ) -> Self:
        """Retain cookie mutation in the non-ASGI response fixture.

        Args:
            name: Cookie name.
            value: Cookie value.
            options: Cookie attributes.

        Returns:
            This response fixture.
        """
        _ = name, value, options
        return self

    def without_cookie(
        self,
        name: str,
        *,
        options: CookieOptions = DEFAULT_COOKIE_OPTIONS,
    ) -> Self:
        """Retain cookie removal in the non-ASGI response fixture.

        Args:
            name: Cookie name.
            options: Cookie attributes.

        Returns:
            This response fixture.
        """
        _ = name, options
        return self


if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.container import ServiceRegistry
    from titanspan.contracts.foundation import (
        BootableServiceProvider,
        ServiceProvider,
    )
    from titanspan.contracts.http import RequestHandler

pytestmark = [pytest.mark.integration, pytest.mark.architecture]


class _ConfiguredIntegerConsumer:
    """Consume an integer selected from application configuration.

    Attributes:
        limit: Typed value injected by the application container.
    """

    def __init__(
        self,
        limit: Annotated[int, FromConfig("testing.limit")],
    ) -> None:
        """Retain the configured integer.

        Args:
            limit: A value validated by the typed configuration capability.
        """
        self.limit = limit

    limit: int


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


def test_application_registers_supported_component_providers_by_default(
    tmp_path: Path,
) -> None:
    """Resolve supported component contracts from the native application.

    Built-in services must use the application container without requiring
    callers to repeat each component provider during construction.
    """
    application = Application(base_path=tmp_path)

    storage = application.make(StorageManager)
    hasher = application.make(Hasher)
    validator = application.make(ValidationService)

    assert callable(storage.disk)
    assert callable(hasher.make)
    assert callable(validator.validate)
    assert application.make(StorageManager) is storage
    assert application.make(Hasher) is hasher
    assert application.make(ValidationService) is validator


def test_application_rejects_duplicate_builtin_provider_overrides() -> None:
    """Reject competing registrations for one application service.

    One explicit Filesystem provider replaces the default provider. Multiple
    instances would create ambiguous manager ownership and fail predictably.
    """
    with pytest.raises(ValueError, match="at most one provider"):
        Application(
            service_providers=(
                FilesystemServiceProvider(),
                FilesystemServiceProvider(),
            ),
        )


def test_framework_exception_reporting_uses_safe_substituted_logging() -> None:
    """Keep framework error reports in the canonical logging override.

    Default diagnostics retain the exception class but omit exception text,
    chained causes, and tracebacks that can contain secrets.
    """
    application = Application(config={"app": {"debug": False}})
    cause = ValueError(_PRIVATE_EXCEPTION_DETAIL)
    error = RuntimeError(_PRIVATE_EXCEPTION_DETAIL)
    error.__cause__ = cause

    with application.context(), Log.fake() as fake:
        assert application.logging is Log.manager()
        application.report_exception(
            error,
            context={"component": "test"},
        )
        record = fake.assert_logged(
            "error",
            "Application operation failed",
        )

    assert record.context["exception_type"] == "RuntimeError"
    assert record.context["component"] == "test"
    assert record.exception is None
    assert _PRIVATE_EXCEPTION_DETAIL not in repr(record)


def test_application_exception_details_require_explicit_opt_in() -> None:
    """Capture full exception details only under an explicit policy.

    Application debug mode or the reporting argument can enable traceback
    records for trusted development environments.
    """
    application = Application(config={"app": {"debug": False}})
    error = RuntimeError(_PRIVATE_EXCEPTION_DETAIL)

    with application.context(), Log.fake() as fake:
        application.report_exception(error, include_details=True)
        record = fake.assert_logged("error", "Application operation failed")

    assert record.exception is not None
    assert _PRIVATE_EXCEPTION_DETAIL in record.exception["message"]


@pytest.mark.anyio
async def test_application_reports_after_shutdown_without_leaking_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Use the logging emergency path after application resources close.

    The post-shutdown report remains useful and omits arbitrary exception
    text after the normal logging graph is unavailable.
    """
    application = Application(config={"app": {"debug": False}})
    await application.startup()
    await application.shutdown()

    application.report_exception(RuntimeError(_PRIVATE_EXCEPTION_DETAIL))

    output = capsys.readouterr().err
    assert "TITANSPAN EMERGENCY" in output
    assert "Application operation failed" in output
    assert "RuntimeError" in output
    assert _PRIVATE_EXCEPTION_DETAIL not in output


@pytest.mark.anyio
async def test_asgi_exception_logging_uses_request_context() -> None:
    """Report request failures through the active logger substitution.

    The real ASGI middleware supplies the request identifier to the same
    application-owned fake selected before request execution.
    """
    application = Application(config={"app": {"debug": False}})

    @application.router.get("/failure")
    async def fail() -> None:
        """Raise a private failure that must not enter public diagnostics.

        Foundation handles the exception after route dispatch.
        """
        Log.info("route started")
        raise RuntimeError(_PRIVATE_EXCEPTION_DETAIL)

    async def dispatch_with_fake() -> int:
        """Send one request while the fake owns the active context.

        The ASGI request uses the real application and logging middleware.
        """
        with Log.fake() as fake:
            transport = httpx2.ASGITransport(
                app=application.asgi,
                raise_app_exceptions=False,
            )
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                response = await client.get("/failure")

            record = fake.assert_logged(
                "error",
                "Application operation failed",
            )
            request_record = fake.assert_logged("info", "route started")
            assert record.context["exception_type"] == "RuntimeError"
            assert isinstance(record.context["request_id"], str)
            assert (
                request_record.context["request_id"]
                == record.context["request_id"]
            )
            assert record.exception is None
            assert _PRIVATE_EXCEPTION_DETAIL not in repr(record)
            return response.status_code

    assert await application.run(dispatch_with_fake) == _INTERNAL_SERVER_ERROR


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


def test_app_helper_resolves_only_the_active_application() -> None:
    """Return the nested active application without global fallback state.

    Application lookup must respect nested ContextVar bindings and fail
    actionably when no application context is active.
    """
    first = Application()
    second = Application()

    with first.context():
        assert app() is first
        with second.context():
            assert app() is second
        assert app() is first

    with pytest.raises(ApplicationContextError, match="active application"):
        app()


def test_facades_resolve_declared_contracts_from_the_shared_base() -> None:
    """Resolve both service facades through one typed base operation.

    Each component declares the contract used for resolution; the active
    application context remains the only production service registry.
    """
    application = Application(config={"app": {"name": "Facade"}})

    assert Config.service_contract is ConfigRepository
    assert Log.service_contract is LoggingManager
    assert Event.service_contract is EventDispatcher

    with application.context():
        config_repository: ConfigRepository = Config.resolve_service()
        logging_manager: LoggingManager = Log.resolve_service()
        event_dispatcher: EventDispatcher = Event.resolve_service()

    assert config_repository is application.config
    assert logging_manager is application.logging
    assert event_dispatcher is application.make(EventDispatcher)
    assert issubclass(Config, Facade)
    assert issubclass(Log, Facade)


def test_config_facade_replacement_is_visible_to_container_and_helpers() -> (
    None
):
    """Route facade substitutions through the application container.

    The facade, direct resolution, and Support helper must observe one
    replacement instance inside the same application context.
    """
    application = Application(config={"app": {"name": "Original"}})
    replacement = Repository({"app": {"name": "Replacement"}})

    with application.context(), Config.use(replacement):
        assert application.make(ConfigRepository) is replacement
        assert Config.repository() is replacement
        assert config() is replacement
        assert Config.string("app.name") == "Replacement"


def test_log_fake_replaces_the_container_visible_logger() -> None:
    """Keep logger injection and facade calls on one fake manager.

    A fake must replace the application contract so injected services and
    facade calls resolve the same logger during the fake scope.
    """
    application = Application(
        config={
            "logging": {
                "default": "memory",
                "channels": {"memory": {"driver": "memory"}},
            },
        }
    )

    with application.context(), Log.fake() as fake:
        injected_logger = application.make(LogWriter)

        assert injected_logger is Log.channel()
        injected_logger.info("shared fake service")
        fake.assert_logged("info", "shared fake service")


@pytest.mark.anyio
async def test_application_injects_only_present_typed_configuration() -> None:
    """Use the application repository's typed accessors for injection.

    Missing and incompatible values fail before an application service can
    observe them, while both resolution and cleanup use native providers.
    """
    configurations: tuple[Mapping[str, object], ...] = (
        {},
        {"testing": {"limit": "many"}},
    )
    for values in configurations:
        application = Application(config=values)
        async with application:
            with pytest.raises(BindingResolutionError) as error:
                application.make(_ConfiguredIntegerConsumer)

            cause = error.value.__cause__
            while cause is not None and not isinstance(
                cause,
                ConfigValueError,
            ):
                cause = cause.__cause__
            assert isinstance(cause, ConfigValueError)


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
async def test_shutdown_rejects_active_overrides_without_losing_cleanup() -> (
    None
):
    """Leave application resources available until overrides have exited.

    A rejected shutdown must remain retryable after the temporary graph
    finalizes and restores the application container context.
    """
    events: list[str] = []
    application = Application(
        service_providers=[_LifecycleProvider(events)],
    )
    await application.startup()
    resource = application.make(_LifecycleResource)

    async with application.container.override({_Marker: _Marker()}):
        with pytest.raises(ScopeError, match="overrides"):
            await application.shutdown()
        assert not resource.closed

    await application.shutdown()

    assert resource.closed
    assert events.count("resource-closed") == 1


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
@pytest.mark.feature
async def test_application_callbacks_and_run_share_native_lifecycle() -> None:
    """Run standalone work between injected startup and shutdown callbacks.

    Callback dependencies resolve through the same application container as
    the operation and run in deterministic ownership order.
    """
    events: list[str] = []
    application = Application()

    async def start() -> None:
        """Record startup after application providers have booted.

        The event sequence verifies provider and callback ordering.
        """
        events.append("started")

    def stop() -> None:
        """Record shutdown before application resources are finalized.

        The event sequence verifies callback ownership order.
        """
        events.append("stopped")

    def stop_first() -> None:
        """Record reverse-order cleanup after the second callback.

        The event sequence verifies last-in, first-out behavior.
        """
        events.append("stopped-first")

    def operation(repository: ConfigRepository) -> str:
        """Return configured state from the active application.

        Args:
            repository: Application-owned configuration repository.

        Returns:
            Configured application name.
        """
        events.append("operation")
        value = repository.get("app.name")
        assert isinstance(value, str)
        return value

    application.on_startup(start)
    application.on_shutdown(stop)
    application.on_shutdown(stop_first)
    result = await application.run(operation)

    assert result == "Titanspan"
    assert events == [
        "started",
        "operation",
        "stopped-first",
        "stopped",
    ]
    assert active_application_context() is None
    assert not application.is_started


@pytest.mark.anyio
@pytest.mark.regression
async def test_application_startup_callback_failure_runs_cleanup_hooks() -> (
    None
):
    """Run registered cleanup after an application hook fails.

    Startup rollback must restore the active context and finalize the
    container even when a callback raises before route installation.
    """
    events: list[str] = []
    application = Application()

    def fail_startup() -> None:
        """Raise a stable error after recording startup entry.

        The failure exercises application startup rollback.
        """
        events.append("startup")
        raise RuntimeError(_PROVIDER_FAILURE_MESSAGE)

    async def cleanup() -> None:
        """Record shielded cleanup after partial startup.

        The callback must run even when startup raises.
        """
        events.append("cleanup")

    application.on_startup(fail_startup)
    application.on_shutdown(cleanup)

    with pytest.raises(RuntimeError, match=_PROVIDER_FAILURE_MESSAGE):
        await application.startup()

    assert events == ["startup", "cleanup"]
    assert active_application_context() is None
    assert not application.is_started


@pytest.mark.anyio
async def test_application_rejects_lifecycle_registration_after_startup() -> (
    None
):
    """Freeze application callbacks when startup begins.

    A serving application cannot mutate its registered lifecycle policy.
    """
    application = Application()
    await application.startup()

    def late_callback() -> None:
        """Represent a lifecycle callback added after startup.

        Startup freezes the callback registry before serving work.
        """

    with pytest.raises(ApplicationLifecycleError, match="before startup"):
        application.on_startup(late_callback)

    await application.shutdown()


@pytest.mark.feature
def test_application_exception_handlers_use_native_contracts() -> None:
    """Resolve exception rendering through native request and response APIs.

    The request context remains active when the registered handler receives
    an application exception.
    """

    def fail() -> None:
        """Raise an application exception for the adapter boundary.

        Raises:
            ValueError: A deterministic route failure.
        """
        raise ValueError(_PRIVATE_ROUTE_FAILURE)

    async def render_error(
        request: HttpRequest,
        exception: ValueError,
        factory: ResponseFactory,
    ) -> HttpResponse:
        """Render only a safe, structured exception classification.

        Args:
            request: Active native request associated with the exception.
            exception: Exception selected by the native handler registry.
            factory: Application-owned response factory.

        Returns:
            A response without private exception details.
        """
        assert request.method == "GET"
        _ = exception
        return factory.json({"detail": "Invalid operation"}, status=422)

    application = (
        Application.builder()
        .with_fastapi_provider(Provider())
        .with_http_middleware(_BuilderHeaderMiddleware)
        .with_exception_handler(ValueError, render_error)
        .build()
    )
    application.add_exception_handler(ValueError, render_error)
    application.router.get("/fail", fail)

    with TestClient(
        application.asgi,
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/fail")

    assert response.status_code == _UNPROCESSABLE_ENTITY
    assert response.headers["X-Builder"] == "enabled"
    assert response.json() == {"detail": "Invalid operation"}
    assert _PRIVATE_ROUTE_FAILURE not in response.text


@pytest.mark.feature
def test_native_middleware_preserves_multiple_cookie_headers() -> None:
    """Expose cookie mutation through the native downstream response.

    Each cookie remains a separate Set-Cookie field on the ASGI response.
    """
    application = (
        Application.builder()
        .with_fastapi_provider(Provider())
        .with_http_middleware(_CookieResponseMiddleware)
        .build()
    )

    def index() -> dict[str, str]:
        """Return a small native response for middleware mutation.

        The response keeps the cookie test independent of route behavior.
        """
        return {"status": "ok"}

    application.router.get("/cookies", index)

    with TestClient(application.asgi) as client:
        response = client.get("/cookies")

    cookies = response.headers.get_list("set-cookie")
    assert response.status_code == HTTPStatus.OK
    assert len(cookies) == _EXPECTED_COOKIE_COUNT
    assert any(value.startswith("session=opaque;") for value in cookies)
    assert any(value.startswith("preference=compact;") for value in cookies)
    assert any(value.startswith("retired=") for value in cookies)


@pytest.mark.feature
def test_application_rejects_non_asgi_exception_responses() -> None:
    """Reject response contract values unsupported by the ASGI host.

    A structural HTTP response is not sufficient at the transport boundary;
    the framework adapter must receive a response the host can transmit.
    """
    application = Application()

    def fail() -> None:
        """Raise an error handled by the invalid response callback.

        Raises:
            ValueError: A deterministic renderer invocation signal.
        """
        raise ValueError(_PRIVATE_ROUTE_FAILURE)

    def render_error(
        request: HttpRequest,
        exception: ValueError,
    ) -> HttpResponse:
        """Return a contract implementation without ASGI transport support.

        Args:
            request: Active native request.
            exception: Exception selected for rendering.

        Returns:
            A structural response rejected by the Foundation adapter.
        """
        _ = request, exception
        return _NonAsgiResponse()

    application.add_exception_handler(ValueError, render_error)
    application.router.get("/fail", fail)

    with (
        TestClient(application.asgi) as client,
        pytest.raises(
            TypeError,
            match="ASGI response",
        ),
    ):
        client.get("/fail")


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

    async def stop() -> None:
        """Record rollback callback execution in the active app context.

        The callback verifies that partial startup cleanup keeps its owning
        application context active.
        """
        active = active_application_context()
        assert active is not None
        assert active.application is application
        events.append("application-shutdown")

    application.on_shutdown(stop)

    with pytest.raises(RuntimeError, match=_PROVIDER_FAILURE_MESSAGE):
        await application.startup()

    assert "application-context-active-during-close" in events
    assert events.index("application-shutdown") < events.index(
        "resource-closed"
    )
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
