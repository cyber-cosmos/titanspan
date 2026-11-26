"""Verify shared dependency identity across concurrent ASGI workers.

The tests use real application scopes, native registration, and the pinned
dependency backend. Synchronization barriers expose initialization races.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from threading import Barrier, Event, Lock

import anyio
import httpx2
import pytest
from anyio import RunFinishedError
from fastapi.testclient import TestClient

from titanspan import Application, app
from titanspan.container import (
    AsyncResolutionRequiredError,
    BindingResolutionError,
    Container,
    ContainerClosedError,
    Scope,
    ScopeError,
)
from titanspan.contracts.container import ServiceRegistry

_REQUEST_COUNT = 20
_MIXED_CALL_COUNT = 2
_WAIT_SECONDS = 10.0
_FACTORY_TIMEOUT_MESSAGE = "Test did not release singleton construction."
_INITIAL_FAILURE_MESSAGE = "first attempt failed"


class ColdSingleton:
    """Identify the instance created by one singleton factory invocation.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, identifier: int) -> None:
        """Retain the factory invocation number for response assertions.

        Args:
            identifier: One-based number assigned to the factory invocation.
        """
        self.identifier = identifier


class ColdSingletonProvider:
    """Register a singleton factory with deterministic contention gates.

    The fixture coordinates initialization and cleanup.
    """

    def __init__(self, *, expected_resolutions: int = _REQUEST_COUNT) -> None:
        """Create synchronization state observed by requests and the factory.

        It initializes state owned by this test fixture.
        """
        self.expected_resolutions = expected_resolutions
        self.release_factory = Event()
        self.factory_entered = Event()
        self.resolution_started = Event()
        self._lock = Lock()
        self._factory_calls = 0
        self._finalizations = 0
        self._resolution_calls = 0

    @property
    def factory_calls(self) -> int:
        """Return the number of factory entries under concurrent access.

        The lock protects this value from concurrent updates.
        """
        with self._lock:
            return self._factory_calls

    @property
    def finalizations(self) -> int:
        """Return the number of singleton resource finalizers that ran.

        The lock protects this value from concurrent updates.
        """
        with self._lock:
            return self._finalizations

    def register(self, container: ServiceRegistry) -> None:
        """Register the cold singleton in the native application container.

        Args:
            container: Canonical service registry owned by the application.
        """
        container.singleton(ColdSingleton, self.create)

    def observe_resolution(self, service: type[object]) -> None:
        """Count each public request before singleton initialization begins.

        Args:
            service: Canonical service key passed by the container callback.
        """
        _ = service
        with self._lock:
            self._resolution_calls += 1
            if self._resolution_calls == self.expected_resolutions:
                self.resolution_started.set()

    def create(self) -> Generator[ColdSingleton, None, None]:
        """Block construction until every request reaches the cold lookup.

        Yields:
            The instance assigned to this factory entry.

        Raises:
            TimeoutError: If the test fails to release the controlled gate.
        """
        with self._lock:
            self._factory_calls += 1
            identifier = self._factory_calls
        self.factory_entered.set()
        if not self.release_factory.wait(timeout=_WAIT_SECONDS):
            message = _FACTORY_TIMEOUT_MESSAGE
            raise TimeoutError(message)
        try:
            yield ColdSingleton(identifier)
        finally:
            with self._lock:
                self._finalizations += 1


class AsyncColdSingleton:
    """Identify the instance created by an asynchronous singleton factory.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, identifier: int) -> None:
        """Retain the asynchronous factory invocation number.

        Args:
            identifier: One-based number assigned to the factory invocation.
        """
        self.identifier = identifier


class AsyncColdSingletonProvider:
    """Register an async resource factory with observable contention.

    The fixture coordinates initialization and cleanup.
    """

    def __init__(self) -> None:
        """Create thread-safe state for the ASGI test coordinator.

        It initializes state owned by this test fixture.
        """
        self.release_factory = Event()
        self.factory_entered = Event()
        self.resolution_started = Event()
        self._lock = Lock()
        self._factory_calls = 0
        self._finalizations = 0
        self._resolution_calls = 0

    @property
    def factory_calls(self) -> int:
        """Return the number of async factory entries.

        The lock protects this value from concurrent updates.
        """
        with self._lock:
            return self._factory_calls

    @property
    def finalizations(self) -> int:
        """Return the number of completed async resource finalizers.

        The lock protects this value from concurrent updates.
        """
        with self._lock:
            return self._finalizations

    def register(self, container: ServiceRegistry) -> None:
        """Register the app-owned async resource.

        Args:
            container: Canonical service registry owned by the application.
        """
        container.singleton(AsyncColdSingleton, self.create)

    def observe_resolution(self) -> None:
        """Signal when every request has reached asynchronous resolution.

        It signals the coordinator when expected callers arrive.
        """
        with self._lock:
            self._resolution_calls += 1
            if self._resolution_calls == _REQUEST_COUNT:
                self.resolution_started.set()

    async def create(
        self,
    ) -> AsyncGenerator[AsyncColdSingleton, None]:
        """Wait for the test coordinator, then yield one managed resource.

        Yields:
            The shared asynchronous singleton.

        Raises:
            TimeoutError: If the test does not release the factory gate.
        """
        with self._lock:
            self._factory_calls += 1
            identifier = self._factory_calls
        self.factory_entered.set()
        released = await anyio.to_thread.run_sync(
            self.release_factory.wait,
            _WAIT_SECONDS,
        )
        if not released:
            message = _FACTORY_TIMEOUT_MESSAGE
            raise TimeoutError(message)
        try:
            yield AsyncColdSingleton(identifier)
        finally:
            with self._lock:
                self._finalizations += 1


class RequestScopedValue:
    """Identify one service instance owned by an HTTP request scope.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, identifier: int) -> None:
        """Retain the unique identifier assigned by the provider.

        Args:
            identifier: Monotonic provider-local request identifier.
        """
        self.identifier = identifier


class RequestScopedValueProvider:
    """Register values whose identity is limited to one request.

    The fixture coordinates initialization and cleanup.
    """

    def __init__(self) -> None:
        """Create a thread-safe request value counter.

        It initializes state owned by this test fixture.
        """
        self._lock = Lock()
        self._created = 0

    def register(self, container: ServiceRegistry) -> None:
        """Bind the service to the native request scope.

        Args:
            container: Canonical service registry owned by the application.
        """
        container.scoped(RequestScopedValue, self.create)

    def create(self) -> RequestScopedValue:
        """Create one value for the current request execution.

        Returns:
            A request-scoped value with a unique provider-local identifier.
        """
        with self._lock:
            self._created += 1
            identifier = self._created
        return RequestScopedValue(identifier)


class SharedDependency:
    """Represent one singleton required by independent root services.

    The fixture gives the real container a concrete service type.
    """


class FirstRoot:
    """Retain the shared dependency through one automatic root graph.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: SharedDependency) -> None:
        """Store the dependency resolved by the backend graph.

        Args:
            dependency: Application singleton shared with other root graphs.
        """
        self.dependency = dependency


class SecondRoot:
    """Retain the shared dependency through another automatic root graph.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: SharedDependency) -> None:
        """Store the dependency resolved by the backend graph.

        Args:
            dependency: Application singleton shared with other root graphs.
        """
        self.dependency = dependency


class AsyncRoot:
    """Retain a shared sync dependency during async singleton creation.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: SharedDependency) -> None:
        """Store the shared dependency resolved before async factory work.

        Args:
            dependency: Application singleton shared with sync scopes.
        """
        self.dependency = dependency


class AsyncRootConsumer:
    """Require the async singleton currently under construction.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: AsyncRoot) -> None:
        """Store the async singleton required by a nested graph.

        Args:
            dependency: Application singleton under active initialization.
        """
        self.dependency = dependency


class DynamicFactoryRoot:
    """Identify a root used to test undeclared nested factory lookups.

    The fixture gives the real container a concrete service type.
    """


class DeepDependency:
    """Represent a leaf service in a nested automatic dependency graph.

    The fixture gives the real container a concrete service type.
    """


class MiddleDependency:
    """Retain a leaf service during nested constructor resolution.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: DeepDependency) -> None:
        """Store the resolved leaf dependency.

        Args:
            dependency: Automatically resolved concrete leaf service.
        """
        self.dependency = dependency


class DeepRoot:
    """Retain the middle service for a nested resolution regression.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, dependency: MiddleDependency) -> None:
        """Store the recursively resolved middle dependency.

        Args:
            dependency: Service that itself requires another dependency.
        """
        self.dependency = dependency


class ApplicationValue:
    """Identify a value owned by one Application container.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, name: str) -> None:
        """Retain the application-specific label.

        Args:
            name: Label used to distinguish independent applications.
        """
        self.name = name


class ApplicationValueProvider:
    """Register a distinct value in each application container.

    The fixture coordinates initialization and cleanup.
    """

    def __init__(self, name: str) -> None:
        """Store the value label for the owning application.

        Args:
            name: Application-specific test label.
        """
        self.name = name

    def register(self, container: ServiceRegistry) -> None:
        """Add one application-owned instance to the native registry.

        Args:
            container: The registry belonging to one Application.
        """
        container.instance(ApplicationValue, ApplicationValue(self.name))


class GatedScopedValue:
    """Identify one value created by a request-scoped factory.

    The fixture gives the real container a concrete service type.
    """

    def __init__(self, identifier: int) -> None:
        """Store the identifier assigned by the shared test provider.

        Args:
            identifier: Monotonic factory invocation number.
        """
        self.identifier = identifier


class GatedScopedValueProvider:
    """Hold scoped factories until independent scopes reach initialization.

    The fixture coordinates initialization and cleanup.
    """

    def __init__(self, expected_arrivals: int) -> None:
        """Create a loop-local barrier initialized by the first factory call.

        Args:
            expected_arrivals: Number of distinct scopes that must enter.
        """
        self.expected_arrivals = expected_arrivals
        self._all_started: anyio.Event | None = None
        self._arrivals = 0
        self._lock = Lock()

    def register(self, container: ServiceRegistry) -> None:
        """Register the gated service in the request lifecycle.

        Args:
            container: Native service registry under test.
        """
        container.scoped(
            GatedScopedValue,
            self.create,
            scope=Scope.REQUEST,
        )

    async def create(self) -> GatedScopedValue:
        """Wait for all independent request scopes before returning a value.

        Returns:
            A unique value owned by the current request scope.
        """
        with self._lock:
            if self._all_started is None:
                self._all_started = anyio.Event()
            self._arrivals += 1
            identifier = self._arrivals
            all_started = self._all_started
            if self._arrivals == self.expected_arrivals:
                all_started.set()
        await all_started.wait()
        return GatedScopedValue(identifier)


class AsyncSingletonHarness:
    """Coordinate gated async factory tests without timing assumptions.

    The harness owns synchronization state for each test.
    """

    def __init__(self, container: Container) -> None:
        """Register one instrumented async singleton on a native container.

        Args:
            container: Real service container used by the integration case.
        """
        self.container = container
        self.factory_started = anyio.Event()
        self.release_factory = anyio.Event()
        self.second_resolution = anyio.Event()
        self._callback_calls = 0
        self.factory_calls = 0
        self.abandoned_initializations = 0
        self.finalizations = 0
        container.singleton(ColdSingleton, self.create)
        container.before_resolving(ColdSingleton, self.observe)

    def observe(self, service: type[object]) -> None:
        """Signal when a second caller reaches the public resolution hook.

        Args:
            service: Native service key passed by the callback registry.
        """
        _ = service
        self._callback_calls += 1
        if self._callback_calls == _MIXED_CALL_COUNT:
            self.second_resolution.set()

    async def create(self) -> AsyncGenerator[ColdSingleton, None]:
        """Gate the first initializer and expose cleanup ownership.

        Yields:
            The singleton created by the successful factory attempt.
        """
        self.factory_calls += 1
        identifier = self.factory_calls
        if identifier == 1:
            self.factory_started.set()
        try:
            if identifier == 1:
                await self.release_factory.wait()
            resource = ColdSingleton(identifier)
            try:
                yield resource
            finally:
                self.finalizations += 1
        except BaseException:
            if identifier == 1:
                self.abandoned_initializations += 1
            raise


@pytest.mark.integration
@pytest.mark.concurrency
def test_twenty_sync_asgi_requests_share_one_cold_singleton() -> None:
    """Initialize one app singleton across twenty worker-thread requests.

    The route barrier releases every request together. The factory remains
    blocked until all public container lookups have started.
    """
    provider = ColdSingletonProvider()
    application = Application(service_providers=(provider,))
    request_barrier = Barrier(_REQUEST_COUNT)

    def endpoint() -> dict[str, object]:
        """Resolve the service directly from a synchronous worker endpoint.

        Returns:
            The singleton identifier and active application identity.
        """
        request_barrier.wait(timeout=_WAIT_SECONDS)
        provider.observe_resolution(ColdSingleton)
        service = app().make(ColdSingleton)
        return {
            "identifier": service.identifier,
            "application_matches": app() is application,
        }

    application.router.get("/singleton", endpoint)

    with (
        TestClient(application.asgi) as client,
        ThreadPoolExecutor(max_workers=_REQUEST_COUNT) as executor,
    ):
        futures = [
            executor.submit(client.get, "/singleton")
            for _ in range(_REQUEST_COUNT)
        ]
        assert provider.factory_entered.wait(timeout=_WAIT_SECONDS)
        assert provider.resolution_started.wait(timeout=_WAIT_SECONDS)
        provider.release_factory.set()
        responses = [future.result(timeout=_WAIT_SECONDS) for future in futures]

    assert all(response.status_code == HTTPStatus.OK for response in responses)
    assert {response.json()["identifier"] for response in responses} == {1}
    assert all(response.json()["application_matches"] for response in responses)
    assert provider.factory_calls == 1
    assert provider.finalizations == 1


@pytest.mark.integration
@pytest.mark.concurrency
def test_twenty_async_asgi_requests_share_one_cold_singleton() -> None:
    """Serialize cold async singleton creation across twenty ASGI requests.

    The async factory waits in a managed worker while all request tasks reach
    resolution. Every request must receive one value and one owner.
    """
    provider = AsyncColdSingletonProvider()
    application = Application(service_providers=(provider,))

    async def endpoint() -> dict[str, int]:
        """Resolve the app singleton through the explicit async API.

        Returns:
            The invocation identifier for the shared instance.
        """
        provider.observe_resolution()
        service = await app().make_async(AsyncColdSingleton)
        return {"identifier": service.identifier}

    application.router.get("/async-singleton", endpoint)

    with (
        TestClient(application.asgi) as client,
        ThreadPoolExecutor(max_workers=_REQUEST_COUNT) as executor,
    ):
        futures = [
            executor.submit(client.get, "/async-singleton")
            for _ in range(_REQUEST_COUNT)
        ]
        assert provider.factory_entered.wait(timeout=_WAIT_SECONDS)
        assert provider.resolution_started.wait(timeout=_WAIT_SECONDS)
        provider.release_factory.set()
        responses = [future.result(timeout=_WAIT_SECONDS) for future in futures]

    assert all(response.status_code == HTTPStatus.OK for response in responses)
    assert {response.json()["identifier"] for response in responses} == {1}
    assert provider.factory_calls == 1
    assert provider.finalizations == 1


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_mixed_asgi_endpoints_share_one_cold_singleton() -> None:
    """Share one cold singleton between concurrent sync and async routes.

    The factory stays gated until both native endpoint paths request it.
    """
    provider = ColdSingletonProvider(expected_resolutions=_MIXED_CALL_COUNT)
    application = Application(service_providers=(provider,))

    def sync_endpoint() -> dict[str, int]:
        """Resolve the shared service from an AnyIO worker endpoint.

        Returns:
            The invocation identifier for the shared singleton.
        """
        provider.observe_resolution(ColdSingleton)
        service = app().make(ColdSingleton)
        return {"identifier": service.identifier}

    async def async_endpoint() -> dict[str, int]:
        """Resolve the shared service through async route execution.

        Returns:
            The invocation identifier for the shared singleton.
        """
        factory_started = await anyio.to_thread.run_sync(
            provider.factory_entered.wait,
            _WAIT_SECONDS,
        )
        assert factory_started
        provider.observe_resolution(ColdSingleton)
        service = await app().make_async(ColdSingleton)
        return {"identifier": service.identifier}

    application.router.get("/sync-singleton", sync_endpoint)
    application.router.get("/async-singleton", async_endpoint)

    await application.startup()
    responses: dict[str, httpx2.Response] = {}
    try:
        transport = httpx2.ASGITransport(app=application.asgi)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:

            async def request_sync() -> None:
                """Send one request to the synchronous endpoint.

                It stores the completed response for assertions.
                """
                responses["sync"] = await client.get("/sync-singleton")

            async def request_async() -> None:
                """Send one request to the asynchronous endpoint.

                It stores the completed response for assertions.
                """
                responses["async"] = await client.get("/async-singleton")

            async with anyio.create_task_group() as task_group:
                task_group.start_soon(request_sync)
                task_group.start_soon(request_async)
                try:
                    factory_started = await anyio.to_thread.run_sync(
                        provider.factory_entered.wait,
                        _WAIT_SECONDS,
                    )
                    assert factory_started
                    both_resolving = await anyio.to_thread.run_sync(
                        provider.resolution_started.wait,
                        _WAIT_SECONDS,
                    )
                    assert both_resolving
                finally:
                    provider.release_factory.set()
    finally:
        provider.release_factory.set()
        await application.shutdown()

    assert all(
        response.status_code == HTTPStatus.OK for response in responses.values()
    )
    assert {
        response.json()["identifier"] for response in responses.values()
    } == {1}
    assert provider.factory_calls == 1
    assert provider.finalizations == 1


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_sync_and_async_resolution_share_cold_singleton_identity() -> (
    None
):
    """Share one cold singleton when worker and async calls contend.

    The worker starts construction first and blocks in the factory. Async
    resolution then waits on the same per-service lock before the gate opens.
    """
    provider = ColdSingletonProvider(
        expected_resolutions=_MIXED_CALL_COUNT,
    )
    container = Container()
    provider.register(container)
    results: list[ColdSingleton] = []
    await container.start()

    async def resolve_sync() -> None:
        """Resolve from an AnyIO worker using the synchronous API.

        It keeps this test's resolution path explicit and observable.
        """
        provider.observe_resolution(ColdSingleton)
        results.append(
            await anyio.to_thread.run_sync(
                container.make,
                ColdSingleton,
            )
        )

    async def resolve_async() -> None:
        """Resolve through the event-loop async API.

        It keeps this test's resolution path explicit and observable.
        """
        provider.observe_resolution(ColdSingleton)
        results.append(await container.make_async(ColdSingleton))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_sync)
        assert await anyio.to_thread.run_sync(
            provider.factory_entered.wait,
            _WAIT_SECONDS,
        )
        task_group.start_soon(resolve_async)
        assert await anyio.to_thread.run_sync(
            provider.resolution_started.wait,
            _WAIT_SECONDS,
        )
        provider.release_factory.set()

    await container.aclose()
    assert provider.factory_calls == 1
    assert provider.finalizations == 1
    assert len(results) == _MIXED_CALL_COUNT
    assert results[0] is results[1]


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_sync_lookup_reuses_primed_singleton_while_async_root_runs() -> (
    None
):
    """Return a primed singleton while its async consumer is still running.

    The sync and async paths must observe one application-owned value.
    """
    container = Container()
    factory_started = anyio.Event()
    release_factory = anyio.Event()

    async def create_root(dependency: SharedDependency) -> AsyncRoot:
        """Hold the shared dependency gate during async initialization.

        Args:
            dependency: Service already constructed by the backend graph.

        Returns:
            A root value after the test releases its gate.
        """
        factory_started.set()
        await release_factory.wait()
        return AsyncRoot(dependency)

    container.singleton(SharedDependency)
    container.singleton(AsyncRoot, create_root)
    await container.start()
    roots: list[AsyncRoot] = []
    synchronous: SharedDependency | None = None

    async def resolve_root() -> None:
        """Retain the root after its factory gate is released.

        This task observes the same dependency as the sync caller.
        """
        roots.append(await container.make_async(AsyncRoot))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_root)
        await factory_started.wait()
        synchronous = container.make(SharedDependency)
        release_factory.set()

    assert len(roots) == 1
    assert synchronous is not None
    assert roots[0].dependency is synchronous
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_nested_async_lookup_reenters_owned_shared_gates() -> None:
    """Reuse an initialized dependency from its owning resolution task.

    Same-task lookups can reenter a gate while child tasks must acquire it.
    """
    container = Container()
    nested_values: list[SharedDependency] = []

    async def create_root(dependency: SharedDependency) -> AsyncRoot:
        """Resolve the dependency again from its root factory.

        Args:
            dependency: Shared instance supplied by the backend graph.

        Returns:
            An async root after verifying nested identity.
        """
        nested_values.append(await container.make_async(SharedDependency))
        return AsyncRoot(dependency)

    container.singleton(SharedDependency)
    container.singleton(AsyncRoot, create_root)
    await container.start()

    root = await container.make_async(AsyncRoot)

    assert nested_values == [root.dependency]
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_nested_factory_cannot_duplicate_initializing_singleton() -> None:
    """Reject nested construction through another root graph.

    The successful dependency remains application-owned after root failure.
    """
    container = Container()
    root_factory_calls = 0
    injected_dependencies: list[SharedDependency] = []

    async def create_root(dependency: SharedDependency) -> AsyncRoot:
        """Try a second root that requires this unfinished singleton.

        Args:
            dependency: Shared service created before the root factory.

        Returns:
            The root after the test-only nested lookup.
        """
        nonlocal root_factory_calls
        root_factory_calls += 1
        injected_dependencies.append(dependency)
        await container.make_async(AsyncRootConsumer)
        return AsyncRoot(dependency)

    container.singleton(SharedDependency)
    container.singleton(AsyncRoot, create_root)
    await container.start()

    with pytest.raises(
        BindingResolutionError,
        match="still initializing",
    ):
        await container.make_async(AsyncRoot)

    assert root_factory_calls == 1
    assert len(injected_dependencies) == 1
    assert (
        await container.make_async(SharedDependency)
        is (injected_dependencies[0])
    )
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_worker_resolution_avoids_default_limiter_starvation() -> None:
    """Resolve sync graphs when request workers use all default tokens.

    It exercises this behavior through the real container.
    """
    container = Container()
    default_limiter = anyio.to_thread.current_default_thread_limiter()
    original_limit = default_limiter.total_tokens
    default_limiter.total_tokens = 1
    worker_finished = Event()

    def resolve_from_worker() -> DeepDependency:
        """Resolve one service and signal completion after accounting ends.

        It keeps this test's resolution path explicit and observable.
        """
        try:
            return container.make(DeepDependency)
        finally:
            worker_finished.set()

    try:
        await container.start()
        try:
            with anyio.fail_after(2.0):
                value = await anyio.to_thread.run_sync(
                    resolve_from_worker,
                    abandon_on_cancel=True,
                )
        except TimeoutError:
            # If a regression blocks on the occupied default limiter, release
            # and join its worker before failing so no test thread is leaked.
            default_limiter.total_tokens = original_limit
            assert await anyio.to_thread.run_sync(
                worker_finished.wait,
                _WAIT_SECONDS,
            )
            raise
        assert isinstance(value, DeepDependency)
        assert worker_finished.is_set()
    finally:
        default_limiter.total_tokens = original_limit
        await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_start_rejects_an_active_pre_runtime_lookup() -> None:
    """Keep sync and async initialization gates from overlapping at startup.

    It exercises this behavior through the real container.
    """
    container = Container()
    lookup_started = Event()
    release_lookup = Event()

    def pause_before_resolution(service: type[object]) -> None:
        """Hold a sync lookup before its backend graph is selected.

        It keeps this test's resolution path explicit and observable.
        """
        _ = service
        lookup_started.set()
        if not release_lookup.wait(timeout=_WAIT_SECONDS):
            message = _FACTORY_TIMEOUT_MESSAGE
            raise TimeoutError(message)

    container.singleton(
        ColdSingleton,
        lambda: ColdSingleton(1),
    )
    container.before_resolving(ColdSingleton, pause_before_resolution)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(container.make, ColdSingleton)
        assert await anyio.to_thread.run_sync(
            lookup_started.wait,
            _WAIT_SECONDS,
        )
        with pytest.raises(ScopeError, match="synchronous resolution"):
            await container.start()
        release_lookup.set()
        synchronous = await anyio.to_thread.run_sync(
            future.result,
            _WAIT_SECONDS,
        )

    await container.start()
    asynchronous = await container.make_async(ColdSingleton)
    assert asynchronous is synchronous
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_async_lookup_in_sync_scope_waits_for_shared_initialization() -> (
    None
):
    """Wait for a concurrent singleton without racing a sync scope graph.

    It exercises this behavior through the real container.
    """
    container = Container()
    root_started = anyio.Event()
    release_root = anyio.Event()
    dependency_lookup_started = anyio.Event()
    results: list[SharedDependency] = []

    async def create_root(
        dependency: SharedDependency,
    ) -> AsyncRoot:
        """Hold the root graph while its sync singleton is already created.

        Args:
            dependency: Shared dependency retained by the root value.

        Returns:
            The root after the test releases its initialization gate.
        """
        root_started.set()
        await release_root.wait()
        return AsyncRoot(dependency)

    def observe_dependency(service: type[object]) -> None:
        """Signal when the sync-scope lookup reaches resolution callbacks.

        It keeps this test's resolution path explicit and observable.
        """
        _ = service
        dependency_lookup_started.set()

    container.singleton(SharedDependency)
    container.singleton(AsyncRoot, create_root)
    container.before_resolving(SharedDependency, observe_dependency)
    await container.start()

    async def resolve_application_value() -> None:
        """Initialize an async root which depends on the shared value.

        It keeps this test's resolution path explicit and observable.
        """
        await container.make_async(AsyncRoot)

    async def resolve_scoped_value() -> None:
        """Wait in a synchronous scope, then reuse the owner instance.

        It keeps this test's resolution path explicit and observable.
        """
        with container.scope(Scope.REQUEST):
            results.append(await container.make_async(SharedDependency))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_application_value)
        await root_started.wait()
        task_group.start_soon(resolve_scoped_value)
        await dependency_lookup_started.wait()
        release_root.set()

    assert len(results) == 1
    root = await container.make_async(AsyncRoot)
    assert root.dependency is results[0]
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
def test_request_scope_is_shared_within_and_isolated_between_requests() -> None:
    """Reuse a request value within a scope and isolate concurrent requests.

    It exercises this behavior through the real container.
    """
    application = Application(
        service_providers=(RequestScopedValueProvider(),),
    )

    async def endpoint() -> dict[str, list[int]]:
        """Resolve the scoped value concurrently through the active app.

        Returns:
            The two request-local identifiers for identity assertions.
        """
        values: list[RequestScopedValue] = []

        async def resolve() -> None:
            """Append the service resolved from this request scope.

            It keeps this test's resolution path explicit and observable.
            """
            values.append(await app().make_async(RequestScopedValue))

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(resolve)
            task_group.start_soon(resolve)
        return {"identifiers": [value.identifier for value in values]}

    application.router.get("/request-scope", endpoint)

    with (
        TestClient(application.asgi) as client,
        ThreadPoolExecutor(max_workers=_MIXED_CALL_COUNT) as executor,
    ):
        futures = [
            executor.submit(client.get, "/request-scope")
            for _ in range(_MIXED_CALL_COUNT)
        ]
        responses = [future.result(timeout=_WAIT_SECONDS) for future in futures]

    identifiers = [response.json()["identifiers"] for response in responses]
    assert all(response.status_code == HTTPStatus.OK for response in responses)
    assert all(len(set(values)) == 1 for values in identifiers)
    assert len({values[0] for values in identifiers}) == _MIXED_CALL_COUNT


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_scoped_factories_initialize_concurrently_per_scope() -> None:
    """Avoid a container-wide lock for independent scoped instances.

    It exercises this behavior through the real container.
    """
    container = Container()
    provider = GatedScopedValueProvider(_MIXED_CALL_COUNT)
    provider.register(container)
    results: list[GatedScopedValue] = []

    async def resolve_one_scope() -> None:
        """Resolve one service within an independent request lifecycle.

        It keeps this test's resolution path explicit and observable.
        """
        async with container.scope(Scope.REQUEST):
            results.append(await container.make_async(GatedScopedValue))

    try:
        with anyio.fail_after(2.0):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(resolve_one_scope)
                task_group.start_soon(resolve_one_scope)
    finally:
        await container.aclose()

    assert len(results) == _MIXED_CALL_COUNT
    assert {value.identifier for value in results} == {1, 2}


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_transitive_singleton_is_shared_across_root_graphs() -> None:
    """Keep a singleton dependency shared across distinct root requests.

    It exercises this behavior through the real container.
    """
    container = Container()
    container.singleton(SharedDependency)
    await container.start()
    results: list[FirstRoot | SecondRoot] = []

    async def resolve_first() -> None:
        """Resolve one concrete root and its singleton dependency.

        It keeps this test's resolution path explicit and observable.
        """
        results.append(await container.make_async(FirstRoot))

    async def resolve_second() -> None:
        """Resolve another concrete root through a different graph.

        It keeps this test's resolution path explicit and observable.
        """
        results.append(await container.make_async(SecondRoot))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_first)
        task_group.start_soon(resolve_second)

    assert len(results) == _MIXED_CALL_COUNT
    first = next(item for item in results if isinstance(item, FirstRoot))
    second = next(item for item in results if isinstance(item, SecondRoot))
    assert first.dependency is second.dependency
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_child_task_does_not_inherit_lock_ownership() -> None:
    """Share cached dependencies when a factory starts a child consumer.

    It exercises this behavior through the real container.
    """
    container = Container()
    child_tasks: list[asyncio.Task[SecondRoot]] = []
    dependency_factory_calls = 0

    def create_dependency() -> SharedDependency:
        """Count singleton graph construction across root generations.

        It keeps this test's resolution path explicit and observable.
        """
        nonlocal dependency_factory_calls
        dependency_factory_calls += 1
        return SharedDependency()

    async def create_parent(
        dependency: SharedDependency,
    ) -> FirstRoot:
        """Start a competing graph while this singleton is initializing.

        Args:
            dependency: Singleton required by the parent graph.

        Returns:
            The parent root that owns shared initialization first.
        """
        child_tasks.append(
            asyncio.create_task(container.make_async(SecondRoot)),
        )
        await anyio.lowlevel.checkpoint()
        return FirstRoot(dependency)

    container.singleton(SharedDependency, create_dependency)
    container.singleton(FirstRoot, create_parent)
    await container.start()

    parent = await container.make_async(FirstRoot)
    with anyio.fail_after(_WAIT_SECONDS):
        child = await child_tasks[0]

    assert dependency_factory_calls == 1
    assert parent.dependency is child.dependency
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_nested_dependency_resolution_completes_without_deadlock() -> (
    None
):
    """Resolve a deep concrete graph within a bounded completion deadline.

    It exercises this behavior through the real container.
    """
    container = Container()
    await container.start()

    with anyio.fail_after(_WAIT_SECONDS):
        root = await container.make_async(DeepRoot)

    assert isinstance(root.dependency.dependency, DeepDependency)
    await container.aclose()


@pytest.mark.integration
def test_application_containers_keep_singletons_isolated() -> None:
    """Keep instances registered by two applications independent.

    It exercises this behavior through the real container.
    """
    first = Application(
        service_providers=(ApplicationValueProvider("first"),),
    )
    second = Application(
        service_providers=(ApplicationValueProvider("second"),),
    )

    with first.context():
        first_value = app().make(ApplicationValue)
    with second.context():
        second_value = app().make(ApplicationValue)

    assert first_value.name == "first"
    assert second_value.name == "second"
    assert first_value is not second_value


@pytest.mark.integration
def test_sync_override_reuses_parent_singleton_and_owns_resources() -> None:
    """Preserve parent identity and finalize sync override resources once.

    A transient root borrows an application singleton from its owner graph.
    """
    container = Container()
    container.singleton(SharedDependency)
    parent_dependency = container.make(SharedDependency)
    finalizations = 0

    def create_resource() -> Generator[ColdSingleton, None, None]:
        """Yield a sync resource owned by the temporary graph.

        Yields:
            A test resource finalized when the override context exits.
        """
        nonlocal finalizations
        try:
            yield ColdSingleton(1)
        finally:
            finalizations += 1

    with container.override(
        {ColdSingleton: create_resource},
    ) as overridden:
        root = overridden.make(FirstRoot)
        resource = overridden.make(ColdSingleton)
        assert root.dependency is parent_dependency
        assert overridden.make(SharedDependency) is parent_dependency
        assert resource.identifier == 1
        assert finalizations == 0

    assert finalizations == 1
    assert container.make(SharedDependency) is parent_dependency


@pytest.mark.integration
@pytest.mark.anyio
async def test_failed_singleton_initialization_can_retry() -> None:
    """Release the shared gate after failure and permit a successful retry.

    It exercises this behavior through the real container.
    """
    container = Container()
    calls = 0

    def create() -> ColdSingleton:
        """Fail once, then return a value through the real backend graph.

        It keeps this test's resolution path explicit and observable.
        """
        nonlocal calls
        calls += 1
        if calls == 1:
            message = _INITIAL_FAILURE_MESSAGE
            raise ValueError(message)
        return ColdSingleton(calls)

    container.singleton(ColdSingleton, create)
    await container.start()

    with pytest.raises(BindingResolutionError):
        await container.make_async(ColdSingleton)

    resolved = await container.make_async(ColdSingleton)
    assert resolved.identifier == _MIXED_CALL_COUNT
    assert calls == _MIXED_CALL_COUNT
    await container.aclose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_sync_worker_rejects_async_only_service_before_factory_runs() -> (
    None
):
    """Reject sync lookup before any async factory side effect occurs.

    It exercises this behavior through the real container.
    """
    container = Container()
    calls = 0

    async def create() -> ColdSingleton:
        """Record an invalid sync path if the preflight fails.

        It keeps this test's resolution path explicit and observable.
        """
        nonlocal calls
        calls += 1
        return ColdSingleton(calls)

    container.singleton(ColdSingleton, create)
    await container.start()

    with pytest.raises(AsyncResolutionRequiredError, match="make_async"):
        await anyio.to_thread.run_sync(container.make, ColdSingleton)

    assert calls == 0
    assert container.active_resolution_count == 0
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_factory_runtime_error_is_not_reported_as_closed_loop() -> None:
    """Preserve factory failures while translating expired loop tokens.

    It exercises this behavior through the real container.
    """
    container = Container()

    def create() -> ColdSingleton:
        """Raise from the service factory after worker bridging begins.

        It keeps this test's resolution path explicit and observable.
        """
        raise RuntimeError(_INITIAL_FAILURE_MESSAGE)

    container.singleton(ColdSingleton, create)
    await container.start()

    with pytest.raises(BindingResolutionError) as captured:
        await anyio.to_thread.run_sync(container.make, ColdSingleton)

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == _INITIAL_FAILURE_MESSAGE
    assert "event loop is no longer active" not in str(captured.value)
    await container.aclose()


@pytest.mark.integration
def test_container_rejects_resolution_after_its_runtime_stops() -> None:
    """Reject stale loop tokens from callers and worker threads.

    The container must not migrate after its owning runtime has stopped.
    """
    container = Container()
    anyio.run(container.start)

    with pytest.raises(BindingResolutionError, match="no longer active"):
        container.make(DeepDependency)

    async def resolve_from_another_loop() -> None:
        """Reject a new event loop on the original owner thread.

        The runtime token must match even when the thread identity does.
        """
        with pytest.raises(BindingResolutionError, match="different active"):
            container.make(DeepDependency)

    anyio.run(resolve_from_another_loop)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(container.make, DeepDependency)
        with pytest.raises(BindingResolutionError, match="no longer active"):
            future.result(timeout=_WAIT_SECONDS)
        worker_error = future.exception()
        assert isinstance(worker_error, BindingResolutionError)
        assert isinstance(worker_error.__cause__, RunFinishedError)

    anyio.run(container.aclose)


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_sync_factory_rejects_undeclared_nested_resolution() -> None:
    """Fail instead of deadlocking on a nested worker-to-loop bridge.

    It exercises this behavior through the real container.
    """
    container = Container()

    def create_root() -> DynamicFactoryRoot:
        """Request an undeclared dependency from a managed worker factory.

        It keeps this test's resolution path explicit and observable.
        """
        container.make(SharedDependency)
        return DynamicFactoryRoot()

    container.singleton(SharedDependency)
    container.singleton(DynamicFactoryRoot, create_root)
    await container.start()

    with pytest.raises(
        BindingResolutionError,
        match="Declare dependencies in the factory signature",
    ):
        await anyio.to_thread.run_sync(
            container.make,
            DynamicFactoryRoot,
        )

    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_shutdown_rejects_active_async_singleton_resolution() -> None:
    """Keep the graph open until an in-flight singleton completes.

    It exercises this behavior through the real container.
    """
    container = Container()
    harness = AsyncSingletonHarness(container)
    results: list[ColdSingleton] = []
    await container.start()

    async def resolve() -> None:
        """Resolve the gated resource through the active graph.

        It keeps this test's resolution path explicit and observable.
        """
        results.append(await container.make_async(ColdSingleton))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve)
        await harness.factory_started.wait()
        with pytest.raises(ScopeError, match="resolution"):
            await container.aclose()
        with pytest.raises(ScopeError, match="resolution"):
            container.stop_accepting()
        assert container.active_resolution_count == 1
        harness.release_factory.set()

    assert len(results) == 1
    await container.aclose()
    assert harness.finalizations == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_container_shutdown_closes_resolution_admission() -> None:
    """Reject new resolutions after shutdown starts accepting no work.

    It exercises this behavior through the real container.
    """
    container = Container()
    await container.start()

    with (
        container.scope(Scope.REQUEST),
        pytest.raises(ScopeError, match="Execution scopes"),
    ):
        container.stop_accepting()

    with container.override({DeepDependency: DeepDependency()}) as override:
        assert isinstance(override.make(DeepDependency), DeepDependency)
        with pytest.raises(ScopeError, match="Execution scopes"):
            container.stop_accepting()

    container.stop_accepting()

    with pytest.raises(ContainerClosedError):
        container.make(DeepDependency)

    await container.aclose()
    with pytest.raises(ContainerClosedError):
        container.stop_accepting()
    await container.aclose()


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_application_shutdown_rejects_in_flight_resolution() -> None:
    """Leave the application usable after shutdown meets active resolution.

    It exercises this behavior through the real container.
    """
    provider = AsyncColdSingletonProvider()
    application = Application(service_providers=(provider,))
    results: list[AsyncColdSingleton] = []
    await application.startup()

    async def resolve() -> None:
        """Resolve the app-owned resource before shutdown can proceed.

        It keeps this test's resolution path explicit and observable.
        """
        results.append(await application.make_async(AsyncColdSingleton))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve)
        assert await anyio.to_thread.run_sync(
            provider.factory_entered.wait,
            _WAIT_SECONDS,
        )
        with pytest.raises(ScopeError, match="resolution operations"):
            await application.shutdown()
        provider.release_factory.set()

    assert len(results) == 1
    assert await application.make_async(AsyncColdSingleton) is results[0]
    await application.shutdown()
    assert provider.finalizations == 1
    with pytest.raises(ContainerClosedError):
        application.container.make(AsyncColdSingleton)


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_cancelled_waiter_leaves_singleton_owner_unchanged() -> None:
    """Cancel one waiter without cancelling the current initializer.

    It exercises this behavior through the real container.
    """
    container = Container()
    harness = AsyncSingletonHarness(container)
    waiter_finished = anyio.Event()
    waiter_scope: list[anyio.CancelScope] = []
    owner_result: list[ColdSingleton] = []
    await container.start()

    async def resolve_owner() -> None:
        """Retain the value produced by the first initializer.

        It keeps this test's resolution path explicit and observable.
        """
        owner_result.append(await container.make_async(ColdSingleton))

    async def resolve_waiter() -> None:
        """Run the second lookup inside its own cancellation scope.

        It keeps this test's resolution path explicit and observable.
        """
        with anyio.CancelScope() as cancel_scope:
            waiter_scope.append(cancel_scope)
            await container.make_async(ColdSingleton)
        waiter_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_owner)
        await harness.factory_started.wait()
        task_group.start_soon(resolve_waiter)
        await harness.second_resolution.wait()
        waiter_scope[0].cancel()
        await waiter_finished.wait()
        harness.release_factory.set()

    assert harness.factory_calls == 1
    assert len(owner_result) == 1
    await container.aclose()
    assert harness.finalizations == 1


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_cancelled_initializer_releases_gate_for_waiting_resolution() -> (
    None
):
    """Retry shared initialization after its owner is cancelled.

    It exercises this behavior through the real container.
    """
    container = Container()
    harness = AsyncSingletonHarness(container)
    owner_finished = anyio.Event()
    waiter_finished = anyio.Event()
    owner_scope: list[anyio.CancelScope] = []
    waiter_result: list[ColdSingleton] = []
    await container.start()

    async def resolve_owner() -> None:
        """Run the first lookup in a separately cancellable task scope.

        It keeps this test's resolution path explicit and observable.
        """
        with anyio.CancelScope() as cancel_scope:
            owner_scope.append(cancel_scope)
            await container.make_async(ColdSingleton)
        owner_finished.set()

    async def resolve_waiter() -> None:
        """Resolve after the cancelled initializer releases its gate.

        It keeps this test's resolution path explicit and observable.
        """
        waiter_result.append(await container.make_async(ColdSingleton))
        waiter_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(resolve_owner)
        await harness.factory_started.wait()
        task_group.start_soon(resolve_waiter)
        await harness.second_resolution.wait()
        owner_scope[0].cancel()
        await owner_finished.wait()
        await waiter_finished.wait()

    assert harness.factory_calls == _MIXED_CALL_COUNT
    assert harness.abandoned_initializations == 1
    assert len(waiter_result) == 1
    assert waiter_result[0].identifier == _MIXED_CALL_COUNT
    await container.aclose()
    assert harness.finalizations == 1


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.anyio
async def test_container_shutdown_finishes_cancelled_resource_cleanup() -> None:
    """Finalize an async singleton even when shutdown is cancelled.

    It exercises this behavior through the real container.
    """
    container = Container()
    finalizer_started = anyio.Event()
    release_finalizer = anyio.Event()
    close_scope: list[anyio.CancelScope] = []
    finalizations = 0

    async def create() -> AsyncGenerator[AsyncColdSingleton, None]:
        """Yield one resource whose asynchronous finalizer is controlled.

        It keeps this test's resolution path explicit and observable.
        """
        nonlocal finalizations
        try:
            yield AsyncColdSingleton(1)
        finally:
            finalizer_started.set()
            await release_finalizer.wait()
            finalizations += 1

    async def close() -> None:
        """Close the graph inside a task scope that can be cancelled.

        It keeps this test's resolution path explicit and observable.
        """
        with anyio.CancelScope() as cancel_scope:
            close_scope.append(cancel_scope)
            await container.aclose()

    container.singleton(AsyncColdSingleton, create)
    await container.start()
    await container.make_async(AsyncColdSingleton)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(close)
        await finalizer_started.wait()
        close_scope[0].cancel()
        release_finalizer.set()

    assert finalizations == 1
    with pytest.raises(ContainerClosedError):
        container.make(AsyncColdSingleton)
