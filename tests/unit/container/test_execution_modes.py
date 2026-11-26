"""Verify synchronous and asynchronous container resolution modes.

The tests assert native public behavior over real Dishka graphs.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from inspect import iscoroutinefunction
from typing import Annotated, cast

import anyio
import pytest

from titanspan.container import (
    AsyncResolutionRequiredError,
    BindingError,
    BindingResolutionError,
    Container,
    Scope,
    ScopeError,
)
from titanspan.contracts import ServiceContainer

_MIXED_TASK_COUNT = 8
_EXPECTED_CALLBACK_COUNT = 2
_DEFAULT_CALLBACK_VALUE = 3
_EXPLICIT_CALLBACK_VALUE = 5
_SYNC_CLEANUP_FAILURE = "sync cleanup failed"
_ASYNC_CLEANUP_FAILURE = "async cleanup failed"

pytestmark = pytest.mark.unit


class SyncService:
    """Represent a service constructed without asynchronous resources.

    The empty class keeps this execution-mode test focused on container
    behavior rather than application service logic.
    """


class ScopedService:
    """Represent one value cached in an execution scope.

    Instances are compared by identity to verify scope ownership.
    """


class AsyncService:
    """Represent a value that is created by an asynchronous factory.

    The test factory records entry so synchronous failure can prove it did not
    partially initialize the dependency graph.
    """


class ConstructorDependency:
    """Represent an automatically constructed leaf dependency.

    The dependency intentionally needs no explicit container binding.
    """


class ConstructorService:
    """Represent a service with one recursively discovered dependency.

    Its constructor annotation is the only registration information used.
    """

    def __init__(self, dependency: ConstructorDependency) -> None:
        """Retain the automatically constructed dependency.

        Args:
            dependency: Concrete class resolved without an explicit binding.
        """
        self.dependency = dependency


class AsyncServiceConsumer:
    """Represent a synchronous class that depends on an async factory.

    Constructor injection remains sync-safe only when every dependency is
    already initialized or has a synchronous creation path.
    """

    def __init__(
        self,
        service: AsyncService,
        sync_service: SyncService,
    ) -> None:
        """Retain the asynchronous service and its synchronous companion.

        Args:
            service: Value produced by the explicitly async factory.
            sync_service: Value created through a synchronous binding.
        """
        self.service = service
        self.sync_service = sync_service


class ManagedSyncService:
    """Represent a generator-managed service with synchronous cleanup.

    Tests use a factory finalizer to check the selected scope owner.
    """


class ScopedServiceConsumer:
    """Retain a request-owned dependency resolved through a sync graph.

    The consumer makes sync scope sharing observable across graph roots.
    """

    def __init__(self, service: ScopedService) -> None:
        """Retain the dependency selected by the active execution scope.

        Args:
            service: Value owned by the current request scope.
        """
        self.service = service


class SingletonServiceConsumer:
    """Retain an application singleton through scoped construction.

    Tests verify that sync scope graphs borrow rather than own the instance.
    """

    def __init__(self, service: SyncService) -> None:
        """Retain the application-owned value.

        Args:
            service: Singleton resolved through its application graph.
        """
        self.service = service


@pytest.mark.anyio
async def test_make_is_a_synchronous_public_operation() -> None:
    """Expose immediate resolution for a synchronous dependency graph.

    Verify the public method is not a coroutine function so callers need not
    spread ``await`` through code that performs ordinary object construction.
    """
    async with Container() as container:
        assert not iscoroutinefunction(container.make)

        service = container.make(SyncService)

        assert isinstance(service, SyncService)


@pytest.mark.anyio
async def test_sync_resolution_discovers_nested_constructor_dependencies() -> (
    None
):
    """Resolve an unregistered constructor graph synchronously.

    This verifies recursive discovery without registering the leaf or root.
    """
    async with Container() as container:
        service: ConstructorService = container.make(ConstructorService)

    assert isinstance(service.dependency, ConstructorDependency)


@pytest.mark.anyio
async def test_sync_roots_reuse_one_graph_generation() -> None:
    """Reuse a composed application graph for repeated sync requests.

    Transient bindings still create new instances, while graph metadata stays
    bounded by the one-generation limit.
    """
    async with Container(max_graph_generations=1) as container:
        container.bind(SyncService)

        first = container.make(SyncService)
        second = container.make(SyncService)

    assert first is not second


@pytest.mark.anyio
async def test_inactive_scopes_reject_sync_and_async_resolution() -> None:
    """Reject resolution before and after a scope owns active resources.

    All public scope entry points share the same active-state invariant.
    """
    async with Container() as container:
        scope = container.scope(Scope.REQUEST)

        with pytest.raises(ScopeError):
            scope.make(SyncService)
        with pytest.raises(ScopeError):
            scope.get(SyncService)
        with pytest.raises(ScopeError):
            await scope.make_async(SyncService)
        with pytest.raises(ScopeError):
            await scope.get_async(SyncService)


@pytest.mark.anyio
async def test_scope_resolution_methods_handle_sync_safe_values() -> None:
    """Resolve sync-safe values through both explicit execution modes.

    An async scope may invoke its async method for a graph that needs no async
    initialization, while a sync scope owns the same safe capability.
    """
    async with Container() as container:
        with container.scope(Scope.REQUEST) as request:
            synchronous = request.get(SyncService)
            asynchronous = await request.make_async(SyncService)
            assert synchronous is not asynchronous

        with container.scope(Scope.REQUEST) as request:
            asynchronous = await request.get_async(SyncService)
            synchronous = request.make(SyncService)
            assert isinstance(asynchronous, SyncService)
            assert isinstance(synchronous, SyncService)


@pytest.mark.anyio
async def test_async_scope_sync_access_reuses_an_entered_graph() -> None:
    """Resolve a transient from a previously entered async child graph.

    The graph is retained per generation even though transient instances are
    constructed freshly for each access.
    """
    async with Container() as container:
        container.bind(SyncService)

        async with container.scope(Scope.REQUEST) as request:
            first = await request.make_async(SyncService)
            second = request.make(SyncService)

    assert first is not second


@pytest.mark.anyio
async def test_sync_scoped_dependencies_are_seeded_across_graph_roots() -> None:
    """Keep a scoped dependency shared by independent sync graph roots.

    The dependency is captured in scope state after the consumer graph builds.
    """
    async with Container() as container:
        container.scoped(ScopedService, scope=Scope.REQUEST)

        with container.scope(Scope.REQUEST) as request:
            consumer = request.make(ScopedServiceConsumer)
            dependency = request.make(ScopedService)

    assert consumer.service is dependency


@pytest.mark.anyio
async def test_sync_scope_primes_application_singletons() -> None:
    """Create uncached application singletons in their owning graph first.

    The request graph receives the initialized value as borrowed context.
    """
    async with Container() as container:
        container.singleton(SyncService)

        with container.scope(Scope.REQUEST) as request:
            consumer = request.make(SingletonServiceConsumer)
            singleton = request.make(SyncService)

    assert consumer.service is singleton


@pytest.mark.anyio
async def test_container_matches_the_sync_first_contract() -> None:
    """Expose typed sync and async resolution through the native protocol.

    This verifies the concrete container and dependency-independent contract
    remain structurally compatible.
    """
    async with Container() as concrete:
        container: ServiceContainer = concrete
        assert isinstance(container, ServiceContainer)
        synchronous: ConstructorService = container.make(
            ConstructorService,
        )
        asynchronous: ConstructorService = await container.make_async(
            ConstructorService,
        )

    assert isinstance(synchronous.dependency, ConstructorDependency)
    assert isinstance(asynchronous.dependency, ConstructorDependency)


@pytest.mark.anyio
async def test_resolution_methods_share_singleton_instances() -> None:
    """Keep synchronous and asynchronous access on one singleton identity.

    This protects callers from separate caches for each resolution mode.
    """
    async with Container() as container:
        container.singleton(ConstructorService)
        first = container.make(ConstructorService)
        second = container.get(ConstructorService)

        assert first is second
        assert container.make_with(ConstructorService, {}) is not first

        async_first = await container.make_async(ConstructorService)
        async_second = await container.get_async(ConstructorService)

    assert async_first is first
    assert async_second is first


@pytest.mark.anyio
async def test_sync_factory_and_tagged_resolution_are_lazy_and_ordered() -> (
    None
):
    """Resolve sync factories and tags through the sync-first API.

    Registration remains lazy, and tag members resolve in declaration order.
    """
    async with Container() as container:
        container.bind(SyncService)
        container.tag([ConstructorDependency, SyncService], "worker-services")
        create_service = container.factory(SyncService)

        first = create_service()
        second = create_service()
        tagged = container.tagged("worker-services")
        missing = container.tagged("unknown")

    assert first is not second
    assert isinstance(tagged[0], ConstructorDependency)
    assert isinstance(tagged[1], SyncService)
    assert missing == []


@pytest.mark.anyio
async def test_sync_and_async_make_with_preserve_result_types() -> None:
    """Construct typed objects with explicit dependencies in each mode.

    Explicit values override automatic constructor resolution without changing
    the result type exposed by either API.
    """
    dependency = ConstructorDependency()

    async with Container() as container:
        synchronous: ConstructorService = container.make_with(
            ConstructorService,
            {"dependency": dependency},
        )
        asynchronous: ConstructorService = await container.make_with_async(
            ConstructorService,
            {"dependency": dependency},
        )

    assert synchronous.dependency is dependency
    assert asynchronous.dependency is dependency


@pytest.mark.anyio
async def test_async_resolution_discovers_a_mixed_dependency_graph() -> None:
    """Resolve async factories recursively through the explicit async API.

    Verify that synchronous constructors can depend on async-created values.
    """
    factory_calls = 0

    async def create_service() -> AsyncService:
        """Construct the async dependency and count factory entry.

        Returns:
            The value retained by the consumer.
        """
        nonlocal factory_calls
        factory_calls += 1
        return AsyncService()

    async with Container() as container:
        container.singleton(AsyncService, create_service)
        service = await container.make_async(AsyncServiceConsumer)

    assert isinstance(service.service, AsyncService)
    assert factory_calls == 1


@pytest.mark.anyio
async def test_sync_and_async_resolution_share_singleton_identity() -> None:
    """Keep one singleton cache across both explicit resolution modes.

    Resolve the same registration synchronously and asynchronously through a
    real backend graph, then compare object identity.
    """
    async with Container() as container:
        assert not iscoroutinefunction(container.make)
        container.singleton(SyncService)

        synchronous = container.make(SyncService)
        asynchronous = await container.make_async(SyncService)

    assert synchronous is asynchronous


@pytest.mark.anyio
async def test_sync_access_reuses_an_async_initialized_singleton() -> None:
    """Allow sync access after async-only initialization has completed.

    A cached instance needs no further asynchronous work and must retain the
    one identity owned by the application graph.
    """
    factory_calls = 0

    async def create_service() -> AsyncService:
        """Initialize the service through an async-only factory.

        Returns:
            The initialized service retained by both resolution modes.
        """
        nonlocal factory_calls
        factory_calls += 1
        return AsyncService()

    async with Container() as container:
        container.singleton(AsyncService, create_service)
        asynchronous = await container.make_async(AsyncService)
        synchronous = container.make(AsyncService)

    assert synchronous is asynchronous
    assert factory_calls == 1


@pytest.mark.anyio
async def test_sync_consumer_can_inject_async_initialized_singleton() -> None:
    """Allow sync construction when an async-only dependency is cached.

    The synchronous root constructor performs no async work. Its singleton
    dependency was initialized during application startup, so reuse is safe.
    """

    async def create_service() -> AsyncService:
        """Create the dependency through its asynchronous factory.

        The assertions exercise the application-owned container lifecycle.
        """
        return AsyncService()

    async with Container() as container:
        container.singleton(AsyncService, create_service)
        initialized = await container.make_async(AsyncService)

        consumer = container.make(AsyncServiceConsumer)

    assert consumer.service is initialized


@pytest.mark.anyio
async def test_application_singletons_are_isolated_between_containers() -> None:
    """Keep singleton identity local to the owning application container.

    Separate containers must not share mutable process-global instances.
    """
    first_container = Container()
    second_container = Container()
    first_container.singleton(SyncService)
    second_container.singleton(SyncService)

    try:
        first = first_container.make(SyncService)
        second = second_container.make(SyncService)
    finally:
        await first_container.aclose()
        await second_container.aclose()

    assert first is not second


@pytest.mark.anyio
async def test_async_only_graph_fails_before_factory_initialization() -> None:
    """Reject async-only dependencies before starting their factories.

    A synchronous request must direct callers to ``make_async`` without
    creating resources or caching part of an asynchronous graph.
    """
    factory_calls = 0
    sync_factory_calls = 0

    def create_sync_service() -> SyncService:
        """Create a sync sibling whose side effect exposes partial work.

        Returns:
            A synchronous service instance.
        """
        nonlocal sync_factory_calls
        sync_factory_calls += 1
        return SyncService()

    async def create_service() -> AsyncService:
        """Create the async-only fixture and expose any premature execution.

        Returns:
            A new asynchronous service instance.
        """
        nonlocal factory_calls
        factory_calls += 1
        return AsyncService()

    async with Container() as container:
        container.singleton(SyncService, create_sync_service)
        container.singleton(AsyncService, create_service)

        assert not iscoroutinefunction(container.make)
        with pytest.raises(
            AsyncResolutionRequiredError,
            match="AsyncServiceConsumer -> AsyncService",
        ):
            container.make(AsyncServiceConsumer)

        assert factory_calls == 0
        assert sync_factory_calls == 0
        service = await container.make_async(AsyncServiceConsumer)

    assert isinstance(service.service, AsyncService)
    assert isinstance(service.sync_service, SyncService)
    assert factory_calls == 1
    assert sync_factory_calls == 1


@pytest.mark.anyio
async def test_sync_factory_failure_is_translated_with_its_cause() -> None:
    """Translate synchronous backend factory failures at the public boundary.

    Callers receive the native resolution error and can inspect its cause.
    """

    def fail_to_create() -> SyncService:
        """Raise a deterministic failure during sync service construction.

        Raises:
            RuntimeError: The simulated factory error.
        """
        raise RuntimeError(_SYNC_CLEANUP_FAILURE)

    async with Container() as container:
        container.bind(SyncService, fail_to_create)
        with pytest.raises(BindingResolutionError) as resolution_error:
            container.make(SyncService)

    assert isinstance(resolution_error.value.__cause__, Exception)


@pytest.mark.anyio
async def test_sync_scope_rejects_async_dependencies_before_entry() -> None:
    """Keep synchronous scope exit from abandoning async-only resources.

    The native scope error is raised before the registered factory runs.
    """
    factory_calls = 0

    async def create_service() -> AsyncService:
        """Create the async-only fixture and count any invocation.

        Returns:
            A new service value.
        """
        nonlocal factory_calls
        factory_calls += 1
        return AsyncService()

    async with Container() as container:
        container.singleton(AsyncService, create_service)
        with (
            container.scope(Scope.REQUEST) as request,
            pytest.raises(ScopeError),
        ):
            await request.make_async(AsyncService)

    assert factory_calls == 0


@pytest.mark.anyio
async def test_synchronous_scope_caches_and_finalizes_sync_services() -> None:
    """Support deterministic scope lifetime without an event loop adapter.

    The same synchronous scoped service is reused inside one native scope and
    a later scope receives an independent instance.
    """
    container = Container()
    container.scoped(ScopedService, scope=Scope.REQUEST)

    with container.scope(Scope.REQUEST) as first_scope:
        first = first_scope.make(ScopedService)
        assert first_scope.make(ScopedService) is first

    with container.scope(Scope.REQUEST) as second_scope:
        second = second_scope.make(ScopedService)

    assert first is not second
    await container.aclose()


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_mixed_resolution_modes_share_scoped_identity() -> None:
    """Preserve one scoped instance across sync and async calls.

    Resolve one value through each explicit mode while the same async scope is
    active; the task-local scope owns both accesses.
    """
    async with Container() as container:
        container.scoped(ScopedService, scope=Scope.REQUEST)

        async with container.scope(Scope.REQUEST) as request:
            synchronous = request.make(ScopedService)
            asynchronous = await request.make_async(ScopedService)

    assert synchronous is asynchronous


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_concurrent_mixed_modes_share_singleton_identity() -> None:
    """Keep async tasks from creating duplicate shared services.

    Task-group scheduling exercises the real backend cache without relying on
    sleeps or timing thresholds.
    """
    results: list[SyncService] = []

    async with Container() as container:
        container.singleton(SyncService)

        async def resolve_sync() -> None:
            """Resolve synchronously from one independent task.

            Append the canonical instance for later identity assertions.
            """
            results.append(container.make(SyncService))

        async def resolve_async() -> None:
            """Resolve asynchronously from one independent task.

            Append the canonical instance for later identity assertions.
            """
            results.append(await container.make_async(SyncService))

        with anyio.fail_after(2):
            async with anyio.create_task_group() as group:
                for _ in range(_MIXED_TASK_COUNT):
                    group.start_soon(resolve_sync)
                    group.start_soon(resolve_async)

    assert len(results) == _MIXED_TASK_COUNT * 2
    assert all(result is results[0] for result in results)


@pytest.mark.anyio
async def test_async_scope_closes_sync_resources_on_cancellation() -> None:
    """Finalize sync graph resources when an async scope is cancelled.

    The async lifecycle owns sync graph callbacks too, so cancellation cannot
    leave generator-backed sync resources active.
    """
    lifecycle: list[str] = []

    def create_service() -> Iterator[ManagedSyncService]:
        """Yield one service and record the close operation.

        Yields:
            A value owned by the workflow execution scope.
        """
        lifecycle.append("started")
        yield ManagedSyncService()
        lifecycle.append("closed")

    async with Container() as container:
        container.scoped(
            ManagedSyncService,
            create_service,
            scope=Scope.WORKFLOW,
        )
        with anyio.CancelScope() as cancellation:
            async with container.scope(Scope.WORKFLOW) as workflow:
                workflow.make(ManagedSyncService)
                cancellation.cancel()
                await anyio.Event().wait()

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure_type",
    [RuntimeError, BindingResolutionError],
)
async def test_sync_scope_translates_resource_cleanup_failures(
    failure_type: type[Exception],
) -> None:
    """Propagate native cleanup errors and translate other finalizer errors.

    Both cleanup paths remain visible to the caller after scope exit.
    """

    def create_service() -> Iterator[ManagedSyncService]:
        """Yield one managed service and fail during finalization.

        Yields:
            The service whose scope cleanup will report an error.
        """
        yield ManagedSyncService()
        raise failure_type(_SYNC_CLEANUP_FAILURE)

    async with Container() as container:
        container.scoped(
            ManagedSyncService,
            create_service,
            scope=Scope.REQUEST,
        )
        with (
            pytest.raises(BindingResolutionError),
            container.scope(Scope.REQUEST) as request,
        ):
            request.make(ManagedSyncService)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure_type",
    [RuntimeError, BindingResolutionError],
)
async def test_async_scope_translates_resource_cleanup_failures(
    failure_type: type[Exception],
) -> None:
    """Propagate native errors and translate async finalization failures.

    The asynchronous scope owns all child cleanup and reports it at exit.
    """

    async def create_service() -> AsyncIterator[ManagedSyncService]:
        """Yield a managed service and fail during asynchronous cleanup.

        Yields:
            The service whose scope cleanup will report an error.
        """
        yield ManagedSyncService()
        raise failure_type(_ASYNC_CLEANUP_FAILURE)

    async with Container() as container:
        container.scoped(
            ManagedSyncService,
            create_service,
            scope=Scope.REQUEST,
        )
        with pytest.raises(BindingResolutionError):
            async with container.scope(Scope.REQUEST) as request:
                await request.make_async(ManagedSyncService)


@pytest.mark.anyio
async def test_call_is_synchronous_for_sync_callbacks() -> None:
    """Inject synchronous dependencies without awaiting ordinary callables.

    Verify the direct callable result is returned synchronously from the
    container API.
    """

    def consume(service: SyncService) -> SyncService:
        """Return the injected value for identity verification.

        Args:
            service: Automatically resolved synchronous dependency.

        Returns:
            The same dependency instance received by the callback.
        """
        return service

    async with Container() as container:
        assert not iscoroutinefunction(container.call)
        result = container.call(consume)

    assert isinstance(result, SyncService)


@pytest.mark.anyio
async def test_sync_call_rejects_async_callbacks_before_invocation() -> None:
    """Require explicit async invocation for coroutine callbacks.

    The synchronous method rejects the function without creating a coroutine.
    """
    callback_calls = 0

    async def consume(service: SyncService) -> SyncService:
        """Return the injected service after async callback entry.

        Args:
            service: Automatically resolved service instance.

        Returns:
            The same instance received by this callback.
        """
        nonlocal callback_calls
        callback_calls += 1
        return service

    async with Container() as container:
        with pytest.raises(AsyncResolutionRequiredError, match="call_async"):
            container.call(cast("Callable[..., object]", consume))

        assert callback_calls == 0
        result = await container.call_async(consume)
        alias_result = await container.call_async(consume)

    assert isinstance(result, SyncService)
    assert alias_result is not result
    assert callback_calls == _EXPECTED_CALLBACK_COUNT


@pytest.mark.anyio
async def test_sync_call_validates_parameters_and_python_parameter_kinds() -> (
    None
):
    """Inject annotated dependencies and preserve callback parameter rules.

    Positional-only values, defaults, variadic arguments and keyword data keep
    normal Python calling semantics.
    """

    def positional_only(service: SyncService, /) -> SyncService:
        """Return a positional-only injected dependency.

        Args:
            service: Dependency that must be passed positionally.

        Returns:
            The same service received by the callback.
        """
        return service

    def defaulted(value: int = _DEFAULT_CALLBACK_VALUE, /) -> int:
        """Return a positional-only default value.

        Args:
            value: Default retained when no explicit value is supplied.

        Returns:
            The selected integer value.
        """
        return value

    def variadic(*values: str, **details: object) -> object:
        """Return an extra keyword value accepted by a variadic callback.

        Args:
            values: Positional values accepted by the callback.
            details: Keyword values accepted by the callback.

        Returns:
            The selected ``label`` value.
        """
        _ = values
        return details["label"]

    def annotated(service: Annotated[SyncService, "service"]) -> SyncService:
        """Return a service whose annotation includes metadata.

        Args:
            service: Concrete service selected after metadata unwrapping.

        Returns:
            The resolved service.
        """
        return service

    async with Container() as container:
        injected = container.call(positional_only)
        assert container.call(defaulted) == _DEFAULT_CALLBACK_VALUE
        assert (
            container.call(
                defaulted,
                {"value": _EXPLICIT_CALLBACK_VALUE},
            )
            == _EXPLICIT_CALLBACK_VALUE
        )
        assert container.call(variadic, {"label": "ready"}) == "ready"
        assert isinstance(container.call(annotated), SyncService)
        with pytest.raises(BindingError):
            container.call(defaulted, {"unknown": True})

    assert isinstance(injected, SyncService)


@pytest.mark.anyio
async def test_sync_call_rejects_unresolvable_and_awaitable_results() -> None:
    """Fail explicitly for unknown scalar dependencies and returned coroutines.

    Synchronous dispatch closes a coroutine result before raising so no
    unawaited coroutine escapes to application code.
    """

    async def create_async_result() -> SyncService:
        """Return a service from an async callback result.

        Returns:
            A service value that cannot be returned synchronously.
        """
        return SyncService()

    def return_coroutine() -> object:
        """Return a coroutine without annotating an async return contract.

        Returns:
            A coroutine that sync dispatch must close and reject.
        """
        return create_async_result()

    def require_scalar(timeout: int) -> int:
        """Require a primitive value that must not be guessed.

        Args:
            timeout: Missing explicit primitive argument.

        Returns:
            The supplied timeout value.
        """
        return timeout

    async with Container() as container:
        with pytest.raises(BindingResolutionError, match="timeout"):
            container.call(require_scalar)
        with pytest.raises(AsyncResolutionRequiredError, match="call_async"):
            container.call(return_coroutine)


@pytest.mark.anyio
async def test_sync_callable_injection_translates_dependency_failures() -> None:
    """Wrap async-only service resolution as a native callable error.

    The callable API explains which parameter could not be resolved.
    """

    async def create_async_service() -> AsyncService:
        """Return a service through an async-only registration.

        Returns:
            The value required by the consumer's dependency graph.
        """
        return AsyncService()

    def consume(consumer: AsyncServiceConsumer) -> object:
        """Expose an async-only dependency through a sync callback.

        Args:
            consumer: Service whose graph needs asynchronous initialization.

        Returns:
            The consumer value if synchronous injection were possible.
        """
        return consumer

    async with Container() as container:
        container.singleton(AsyncService, create_async_service)
        with pytest.raises(
            BindingResolutionError,
            match="consumer",
        ):
            container.call(consume)


@pytest.mark.anyio
async def test_sync_method_bindings_dispatch_and_fail_natively() -> None:
    """Use sync callback bindings and report missing keys natively.

    Missing keys raise a native binding error before callback execution.
    """

    def process(service: SyncService) -> SyncService:
        """Return the dependency supplied by callable injection.

        Args:
            service: Automatically resolved service dependency.

        Returns:
            The same service instance.
        """
        return service

    async with Container() as container:
        container.bind_method("worker.process", process)
        assert container.has_method_binding("worker.process")
        assert isinstance(
            container.call_method_binding("worker.process"),
            SyncService,
        )
        with pytest.raises(BindingError):
            container.call_method_binding("missing")
