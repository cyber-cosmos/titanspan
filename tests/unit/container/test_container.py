"""Verify native binding, automatic resolution, and scope semantics.

The tests exercise the native container using observable behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import (
    AsyncIterator,  # noqa: TC003  # Dishka resolves it at runtime.
    Iterator,  # noqa: TC003  # Dishka resolves it at runtime.
)
from types import NoneType
from typing import TYPE_CHECKING, Annotated, Protocol

import anyio
import pytest

from titanspan.container import (
    BindingError,
    BindingResolutionError,
    Container,
    ContainerClosedError,
    GraphLimitError,
    Scope,
    ScopeError,
)

pytestmark = pytest.mark.unit

_EXPECTED_SCOPE_PARTICIPANTS = 2
_EXPECTED_ATTEMPTS = 3
_DEFAULT_CALL_ATTEMPTS = 3
_CLEANUP_FAILURE_MESSAGE = "cleanup failed"

if TYPE_CHECKING:

    class UnavailableCallableDependency:
        """Declare a static-only missing type for signature error tests.

        The runtime intentionally omits this name so Python annotation
        evaluation exercises the container's error translation path.
        """


class Repository:
    """Represent an automatically constructible persistence dependency.

    Keep this fixture focused on the dependency shape required by its test.
    """


class DocumentService:
    """Depend on a concrete repository without explicit registration.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, repository: Repository) -> None:
        """Retain the repository resolved by the active container graph.

        Args:
            repository: Automatically constructed persistence dependency.
        """
        self.repository = repository


class DocumentController:
    """Represent an application entry point with nested dependencies.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, service: DocumentService) -> None:
        """Retain the automatically resolved document service.

        Args:
            service: Application service for document operations.
        """
        self.service = service


class SharedService:
    """Represent an application singleton used by multiple graphs.

    Keep this fixture focused on the dependency shape required by its test.
    """


class SingletonConsumer:
    """Depend on a container-registered shared service.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, service: SharedService) -> None:
        """Retain the application-owned shared service.

        Args:
            service: The instance registered as an application singleton.
        """
        self.service = service


class FirstSharedConsumer:
    """Represent one graph root that depends on shared application state.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, service: SharedService) -> None:
        """Retain the shared service used by the first graph root.

        Args:
            service: Application-wide service dependency.
        """
        self.service = service


class SecondSharedConsumer:
    """Represent another graph root with the same shared dependency.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, service: SharedService) -> None:
        """Retain the service produced while resolving the second root.

        Args:
            service: Application-wide service dependency.
        """
        self.service = service


class _SharedConsumer(Protocol):
    """Describe the dependency exposed by both test graph roots.

    Keep this fixture focused on the dependency shape required by its test.
    """

    service: SharedService


class ScopedService:
    """Represent state that belongs to one execution scope.

    Keep this fixture focused on the dependency shape required by its test.
    """


class ScopedConsumer:
    """Depend on scoped state from another auto-discovered graph.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, service: ScopedService) -> None:
        """Retain the active scope's service dependency.

        Args:
            service: Service instance already resolved in the current scope.
        """
        self.service = service


class TaggedService:
    """Represent a service resolved through an ordered container tag.

    Keep this fixture focused on the dependency shape required by its test.
    """


class ManagedService:
    """Represent a resource that must be finalized when its scope ends.

    Keep this fixture focused on the dependency shape required by its test.
    """


class ApplicationResource:
    """Represent a long-lived resource owned by the application container.

    Keep this fixture focused on the dependency shape required by its test.
    """


class ScopedResourceConsumer:
    """Depend on an application resource from a shorter execution scope.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, resource: ApplicationResource) -> None:
        """Retain the application resource for the scope lifetime.

        Args:
            resource: Resource that remains owned by the application.
        """
        self.resource = resource


class AsyncManagedService:
    """Represent an asynchronously initialized scoped resource.

    Keep this fixture focused on the dependency shape required by its test.
    """


class AsyncFactoryService:
    """Represent a value produced by an asynchronous factory.

    Keep this fixture focused on the dependency shape required by its test.
    """


class CallDependency:
    """Represent a dependency injected into a callable.

    Keep this fixture focused on the dependency shape required by its test.
    """


class TransientFactoryValue:
    """Represent a service created by a lazy container factory.

    Keep this fixture focused on the dependency shape required by its test.
    """


class FailingFactoryService:
    """Represent a service factory that raises during backend resolution.

    Keep this fixture focused on the dependency shape required by its test.
    """


class NullValueConsumer:
    """Depend on an explicitly registered ``None`` value.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, value: NoneType) -> None:
        """Retain a nullable dependency without confusing it with absence.

        Args:
            value: Explicitly registered ``None`` value.
        """
        self.value = value


class AbstractRepository(ABC):
    """Represent an unresolved service contract for error translation.

    Keep this fixture focused on the dependency shape required by its test.
    """

    @abstractmethod
    def get(self) -> object:
        """Retrieve a value through the abstract repository contract.

        Returns:
            A generic value used only to establish the abstract contract.
        """
        ...


class ServiceWithMissingContract:
    """Depend on a contract without a registered implementation.

    Keep this fixture focused on the dependency shape required by its test.
    """

    def __init__(self, repository: AbstractRepository) -> None:
        """Retain the unavailable repository contract.

        Args:
            repository: Contract intentionally left unbound by the test.
        """
        self.repository = repository


@pytest.mark.anyio
async def test_make_resolves_an_unregistered_concrete_graph() -> None:
    """Build nested concrete dependencies without manual bindings.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        controller = await container.make_async(DocumentController)

    assert isinstance(controller, DocumentController)
    assert isinstance(controller.service, DocumentService)
    assert isinstance(controller.service.repository, Repository)


@pytest.mark.anyio
async def test_singleton_survives_automatic_graph_expansion() -> None:
    """Preserve a shared instance while adding an automatic graph.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        container.singleton(SharedService)
        consumer = await container.make_async(SingletonConsumer)
        original = await container.make_async(SharedService)
        resolved_again = await container.make_async(SharedService)

    assert consumer.service is original
    assert resolved_again is original


@pytest.mark.anyio
async def test_unrelated_singleton_is_not_eagerly_initialized() -> None:
    """Keep unrelated shared factories lazy during graph resolution.

    Verify the behavior through results visible from the container API.
    """
    creations: list[str] = []

    class UnrelatedService:
        """Represent a binding unrelated to the requested dependency graph.

        Keep this fixture focused on the dependency shape required by its test.
        """

        def __init__(self) -> None:
            """Record construction so accidental eagerness is observable.

            Keep this helper local so captured test state stays isolated.
            """
            creations.append("created")

    async with Container() as container:
        container.singleton(UnrelatedService)
        await container.make_async(Repository)

    assert creations == []


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_concurrent_graph_expansion_preserves_singleton_identity() -> (
    None
):
    """Share one singleton across concurrently composed root graphs.

    Verify the behavior through results visible from the container API.
    """
    factory_calls = 0
    both_callers_ready = anyio.Event()
    caller_count = 0
    resolved: list[SharedService] = []

    async def create_shared_service() -> SharedService:
        """Hold initialization until both graph generations request it.

        Returns:
            The application service produced by the test factory.
        """
        nonlocal factory_calls
        factory_calls += 1
        await both_callers_ready.wait()
        return SharedService()

    async def resolve[ConsumerT: _SharedConsumer](
        service: type[ConsumerT],
    ) -> None:
        """Resolve one consumer and record its shared dependency.

        Keep this helper local so captured test state stays isolated.
        """
        nonlocal caller_count
        caller_count += 1
        if caller_count == _EXPECTED_SCOPE_PARTICIPANTS:
            both_callers_ready.set()
        consumer = await container.make_async(service)
        resolved.append(consumer.service)

    async with Container() as container:
        container.singleton(SharedService, create_shared_service)
        with anyio.fail_after(2):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(resolve, FirstSharedConsumer)
                task_group.start_soon(resolve, SecondSharedConsumer)

    assert factory_calls == 1
    assert resolved[0] is resolved[1]


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_execution_scopes_isolate_concurrent_service_instances() -> None:
    """Give concurrent workflow scopes separate cached instances.

    A rendezvous keeps both scopes active together so identity is checked
    without relying on sleep-based scheduling.
    """
    resolved: list[ScopedService] = []
    arrived = 0
    rendezvous = anyio.Event()

    async def resolve_in_scope() -> None:
        """Resolve and retain one service inside an independent scope.

        Returns:
            ``None`` after both scopes have overlapped.
        """
        nonlocal arrived
        async with container.scope(Scope.WORKFLOW) as scope:
            service = await scope.make_async(ScopedService)
            assert await scope.make_async(ScopedService) is service
            consumer = await scope.make_async(ScopedConsumer)
            assert consumer.service is service
            resolved.append(service)
            arrived += 1
            if arrived == _EXPECTED_SCOPE_PARTICIPANTS:
                rendezvous.set()
            await rendezvous.wait()

    async with Container() as container:
        container.scoped(ScopedService)
        with anyio.fail_after(2):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(resolve_in_scope)
                task_group.start_soon(resolve_in_scope)

    assert len(resolved) == _EXPECTED_SCOPE_PARTICIPANTS
    assert resolved[0] is not resolved[1]


@pytest.mark.anyio
async def test_scope_context_cannot_be_reentered_after_cleanup() -> None:
    """Reject reuse of a scope after its backend child was finalized.

    A scope object owns child graphs and cached values, so reopening that same
    object could expose stale references from an earlier lifecycle.
    """
    async with Container() as container:
        scope = container.scope(Scope.WORKFLOW)
        async with scope:
            await scope.make_async(ScopedService)

        with pytest.raises(ScopeError):
            async with scope:
                pass


@pytest.mark.anyio
async def test_scope_validates_entry_and_typed_resolution() -> None:
    """Validate scope hierarchy and the concise typed resolution method.

    Reject same-level lifetimes and allow deeper scopes to resolve services.
    """
    async with Container() as container:
        with pytest.raises(ScopeError):
            async with container.scope(Scope.APPLICATION):
                pass

        async with container.scope(Scope.WORKFLOW) as workflow:
            with pytest.raises(ScopeError):
                async with container.scope(Scope.REQUEST):
                    pass
            async with container.scope(Scope.NODE) as node:
                assert node.is_active
                with pytest.raises(ScopeError):
                    async with container.scope(Scope.AGENT):
                        pass
                assert isinstance(
                    await node.get_async(ScopedService), ScopedService
                )
                first = await node.make_async(Repository)
                second = await node.make_async(Repository)
                assert first is not second

                with pytest.raises(ScopeError):
                    async with container.scope(Scope.APPLICATION):
                        pass

                async with container.scope(Scope.TOOL) as tool:
                    assert tool.is_active
                    with pytest.raises(ScopeError):
                        async with container.scope(Scope.TASK):
                            pass

        with pytest.raises(ScopeError):
            await workflow.make_async(ScopedService)

        async with container.scope(Scope.AGENT):
            with pytest.raises(ScopeError):
                async with container.scope(Scope.NODE):
                    pass


@pytest.mark.anyio
async def test_container_rejects_zero_graph_limit() -> None:
    """Reject an invalid graph bound before creating container state.

    A positive graph limit is required to bound retained resolver generations.
    """
    with pytest.raises(BindingError):
        Container(max_graph_generations=0)


@pytest.mark.anyio
async def test_conditional_bindings_keep_the_first_registration() -> None:
    """Preserve the original contract implementation on conditional binds.

    Repeated transient, singleton, and scoped registrations must not replace
    a binding that has already been selected by application bootstrap.
    """

    class FirstImplementation:
        """Represent the first concrete registration for this contract.

        Keep this fixture focused on the dependency shape required by its test.
        """

    class SecondImplementation(FirstImplementation):
        """Represent a later registration that must be ignored.

        Keep this fixture focused on the dependency shape required by its test.
        """

    async with Container() as container:
        container.bind_if(FirstImplementation)
        container.bind_if(FirstImplementation, SecondImplementation)
        container.singleton_if(SharedService)
        container.singleton_if(SharedService, TaggedService)
        container.scoped_if(ScopedService)
        container.scoped_if(ScopedService, TaggedService)

        transient = await container.make_async(FirstImplementation)
        assert isinstance(transient, FirstImplementation)
        assert not isinstance(transient, SecondImplementation)
        assert container.get_bindings()[SharedService].implementation is (
            SharedService
        )
        assert container.get_bindings()[ScopedService].implementation is (
            ScopedService
        )


@pytest.mark.anyio
async def test_alias_and_tag_names_must_be_non_empty_and_unambiguous() -> None:
    """Reject empty names and aliases that target different services.

    Registration errors must be raised before graph construction can create
    resources or freeze additional container state.
    """
    container = Container()
    with pytest.raises(BindingError):
        container.alias(Repository, "")
    container.alias(Repository, "repositories")
    with pytest.raises(BindingError):
        container.alias(DocumentService, "repositories")
    with pytest.raises(BindingError):
        container.tag(TaggedService, "")
    container.tag([TaggedService, TaggedService], "workers")
    assert len(await container.tagged_async("workers")) == 1
    await container.aclose()


@pytest.mark.anyio
async def test_instance_registration_is_external_and_resolved_immediately() -> (
    None
):
    """Retain an externally owned instance without taking cleanup ownership.

    The registered value is immediately visible to the container and remains
    the same identity in execution scopes.
    """
    instance = SharedService()
    async with Container() as container:
        container.instance(SharedService, instance)
        assert container.resolved(SharedService)
        assert container.get_bindings()[SharedService].is_instance
        assert (await container.make_async(SharedService)) is instance
        async with container.scope(Scope.REQUEST) as request:
            assert await request.make_async(SharedService) is instance


@pytest.mark.anyio
async def test_factory_binding_replaces_an_uncomposed_instance() -> None:
    """Discard an explicit instance when a factory replaces its binding.

    Registration replacement happens before graph composition, so the new
    factory must be the only source used for subsequent resolution.
    """
    original = SharedService()
    replacement = SharedService()
    factory_calls = 0

    def create_service() -> SharedService:
        """Return the replacement and expose whether stale state was used.

        Returns:
            The object selected by the replacement factory.
        """
        nonlocal factory_calls
        factory_calls += 1
        return replacement

    async with Container() as container:
        container.instance(SharedService, original)
        container.bind(SharedService, create_service)

        resolved = container.make(SharedService)

    assert resolved is replacement
    assert resolved is not original
    assert factory_calls == 1


@pytest.mark.anyio
async def test_singleton_binding_replaces_an_uncomposed_instance() -> None:
    """Use the new singleton factory after replacing an explicit instance.

    The replacement is cached according to singleton semantics, while the
    externally supplied previous instance is no longer seeded into the graph.
    """
    original = SharedService()
    replacement = SharedService()
    factory_calls = 0

    def create_service() -> SharedService:
        """Return one observable value for the new singleton binding.

        Returns:
            The replacement singleton instance.
        """
        nonlocal factory_calls
        factory_calls += 1
        return replacement

    async with Container() as container:
        container.instance(SharedService, original)
        container.singleton(SharedService, create_service)

        first = container.make(SharedService)
        second = container.make(SharedService)

    assert first is replacement
    assert second is replacement
    assert first is not original
    assert factory_calls == 1


@pytest.mark.anyio
async def test_none_instance_is_a_valid_explicit_dependency() -> None:
    """Distinguish an explicit null instance from a missing registration.

    A constructor can consume the registered value and an alias resolves to
    the same cached key without inventing a separate sentinel service.
    """
    async with Container() as container:
        container.instance(NoneType, None)
        container.alias(NoneType, "null-value")
        consumer = await container.make_async(NullValueConsumer)

        assert consumer.value is None
        assert await container.get_async("null-value") is None
        assert container.bound("null-value")
        assert container.resolved("null-value")


@pytest.mark.anyio
async def test_scoped_registration_rejects_application_scope() -> None:
    """Reject scoped cache policy when no execution lifetime exists.

    Application lifetime values must use singleton registration so their
    ownership and shutdown behavior stay explicit.
    """
    with pytest.raises(BindingError):
        Container().scoped(ScopedService, scope=Scope.APPLICATION)


@pytest.mark.anyio
async def test_callable_injection_handles_typed_parameter_kinds() -> None:
    """Resolve supported annotations while preserving Python parameter kinds.

    The callable receives positional-only defaults and dependencies together
    with keyword data accepted by its variadic keyword parameter.
    """

    def process(
        dependency: Annotated[CallDependency, "service"],
        attempts: int = _DEFAULT_CALL_ATTEMPTS,
        /,
        *values: str,
        **details: object,
    ) -> tuple[int, CallDependency, tuple[str, ...], object]:
        """Return injected and explicit arguments for verification.

        Args:
            attempts: Positional-only parameter using its default.
            dependency: Annotated service supplied by the container.
            values: Positional values accepted by the callback.
            details: Extra named values accepted by the callback.

        Returns:
            The default, dependency, positional tuple, and selected keyword.
        """
        return attempts, dependency, values, details["label"]

    async with Container() as container:
        attempts, dependency, values, label = await container.call_async(
            process,
            {"label": "ready"},
        )

    assert attempts == _DEFAULT_CALL_ATTEMPTS
    assert isinstance(dependency, CallDependency)
    assert values == ()
    assert label == "ready"


@pytest.mark.anyio
async def test_callable_injection_translates_resolution_errors() -> None:
    """Report unresolved annotations and missing service dependencies natively.

    The exception cause remains available without exposing backend exception
    types through callable injection.
    """

    def invalid_hint(value: UnavailableCallableDependency) -> None:
        """Declare a deliberately unresolved forward reference.

        Args:
            value: Annotation omitted from the active module namespace.
        """

    def primitive(timeout: int) -> None:
        """Declare a primitive parameter with no caller-supplied value.

        Args:
            timeout: Value that automatic resolution must not guess.
        """

    def missing_contract(repository: AbstractRepository) -> None:
        """Declare an abstract dependency with no registered implementation.

        Args:
            repository: Contract intentionally left unbound by this test.
        """

    async with Container() as container:
        with pytest.raises(BindingResolutionError) as signature_error:
            await container.call_async(invalid_hint)
        with pytest.raises(BindingResolutionError) as primitive_error:
            await container.call_async(primitive)
        with pytest.raises(BindingResolutionError) as dependency_error:
            await container.call_async(missing_contract)

    assert signature_error.value.__cause__ is not None
    assert primitive_error.value.__cause__ is None
    assert dependency_error.value.__cause__ is not None


@pytest.mark.anyio
async def test_missing_method_and_unknown_alias_raise_native_errors() -> None:
    """Reject dispatch keys that have not been registered by the application.

    Missing names fail before any dependency graph is composed.
    """
    async with Container() as container:
        assert not container.resolved("missing")
        assert not container.has("missing")
        assert not container.bound("missing")
        with pytest.raises(BindingError):
            await container.call_method_binding_async("missing")
        with pytest.raises(BindingError):
            await container.make_async("missing")
        with pytest.raises(BindingError):
            container.bind_method("", lambda: None)


@pytest.mark.anyio
async def test_factory_failure_is_translated_and_chained() -> None:
    """Translate implementation errors without losing the original cause.

    Application code receives a Titanspan resolution exception while the
    factory error remains available for diagnostics through exception chaining.
    """

    def failing_factory() -> FailingFactoryService:
        """Raise while constructing the test service.

        Raises:
            RuntimeError: The deliberately injected factory failure.
        """
        raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

    async with Container() as container:
        container.bind(FailingFactoryService, failing_factory)
        with pytest.raises(BindingResolutionError) as resolution_error:
            await container.make_async(FailingFactoryService)

    assert resolution_error.value.__cause__ is not None


@pytest.mark.anyio
async def test_container_rejects_shutdown_while_scopes_are_active() -> None:
    """Require active scope cleanup before application shutdown begins.

    A closed container cannot create new work, while repeated close calls are
    safe after all owned resources have already been finalized.
    """
    container = Container()
    async with container.scope(Scope.REQUEST):
        with pytest.raises(ScopeError):
            await container.aclose()

    await container.close()
    await container.aclose()
    with pytest.raises(ContainerClosedError):
        await container.make_async(Repository)


@pytest.mark.anyio
async def test_container_translates_application_resource_cleanup_failures() -> (
    None
):
    """Translate resource finalization failures at container boundaries.

    Shutdown continues after a failed resource so all graph owners get a
    cleanup attempt and the native exception retains the backend cause.
    """

    def broken_resource() -> Iterator[ManagedService]:
        """Yield a resource whose finalizer reports a cleanup failure.

        Yields:
            The resource owned by the application container.
        """
        yield ManagedService()
        raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

    def another_broken_resource() -> Iterator[AsyncManagedService]:
        """Yield a second resource to verify cleanup continues after failure.

        Yields:
            The resource owned by a separate application graph.
        """
        yield AsyncManagedService()
        raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

    container = Container()
    container.singleton(ManagedService, broken_resource)
    container.singleton(AsyncManagedService, another_broken_resource)
    await container.make_async(ManagedService)
    await container.make_async(AsyncManagedService)

    with pytest.raises(BindingResolutionError) as cleanup_error:
        await container.aclose()

    assert cleanup_error.value.__cause__ is not None


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_closed_scope_context_is_rejected_in_inherited_tasks() -> None:
    """Reject a child task that resumes after its inherited scope has closed.

    Events control task ordering so this lifecycle edge case is deterministic
    and does not depend on sleep-based scheduling.
    """
    child_started = anyio.Event()
    resume_child = anyio.Event()

    async def resolve_after_close(container: Container) -> None:
        """Wait for scope exit before attempting inherited resolution.

        Args:
            container: Container whose scope the task inherited.
        """
        child_started.set()
        await resume_child.wait()
        with pytest.raises(ScopeError):
            await container.make_async(ScopedService)

    async with Container() as container:
        with anyio.fail_after(2):
            async with anyio.create_task_group() as task_group:
                async with container.scope(Scope.WORKFLOW):
                    task_group.start_soon(
                        resolve_after_close,
                        container,
                    )
                    await child_started.wait()
                resume_child.set()


@pytest.mark.anyio
async def test_scope_translates_resource_finalization_failures() -> None:
    """Translate failures raised while an execution scope closes resources.

    Scoped backend cleanup must preserve its cause while exposing only native
    container exceptions to callers.
    """

    def broken_resource() -> Iterator[ManagedService]:
        """Yield a scope-owned resource with a failing finalizer.

        Yields:
            The resource owned by the active workflow scope.
        """
        yield ManagedService()
        raise RuntimeError(_CLEANUP_FAILURE_MESSAGE)

    async with Container() as container:
        container.scoped(
            ManagedService,
            broken_resource,
            scope=Scope.WORKFLOW,
        )
        with pytest.raises(BindingResolutionError) as cleanup_error:
            async with container.scope(Scope.WORKFLOW) as workflow:
                await workflow.make_async(ManagedService)

    assert cleanup_error.value.__cause__ is not None


@pytest.mark.anyio
async def test_scoped_generator_resource_is_finalized_on_scope_exit() -> None:
    """Finalize a real backend-managed resource when its owner exits.

    Verify the behavior through results visible from the container API.
    """
    lifecycle: list[str] = []

    def managed_service() -> Iterator[ManagedService]:
        """Yield one managed value and record its cleanup.

        Yields:
            The service instance owned by the workflow scope.
        """
        lifecycle.append("started")
        yield ManagedService()
        lifecycle.append("closed")

    async with Container() as container:
        container.scoped(
            ManagedService,
            managed_service,
            scope=Scope.WORKFLOW,
        )
        async with container.scope(Scope.WORKFLOW) as scope:
            first = await scope.make_async(ManagedService)
            second = await scope.make_async(ManagedService)
            assert first is second
            assert lifecycle == ["started"]

        assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_application_resource_outlives_scopes_that_resolve_it() -> None:
    """Keep application resource ownership outside execution scopes.

    Resolving a singleton through a request graph must not make that graph
    responsible for finalizing the application-owned value.
    """
    lifecycle: list[str] = []

    def application_resource() -> Iterator[ApplicationResource]:
        """Yield one application-owned value and record finalization.

        Yields:
            The resource retained until application shutdown.
        """
        lifecycle.append("started")
        yield ApplicationResource()
        lifecycle.append("closed")

    async with Container() as container:
        container.singleton(ApplicationResource, application_resource)
        async with container.scope(Scope.REQUEST) as first_scope:
            first = await first_scope.make_async(ScopedResourceConsumer)
        async with container.scope(Scope.REQUEST) as second_scope:
            second = await second_scope.make_async(ScopedResourceConsumer)

        assert first.resource is second.resource
        assert lifecycle == ["started"]

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_scoped_async_generator_is_finalized_on_scope_exit() -> None:
    """Finalize asynchronous generator resources on scope exit.

    Verify the behavior through results visible from the container API.
    """
    lifecycle: list[str] = []

    async def managed_service() -> AsyncIterator[AsyncManagedService]:
        """Yield and asynchronously finalize one managed service.

        Yields:
            An instance owned by the active workflow scope.
        """
        lifecycle.append("started")
        yield AsyncManagedService()
        lifecycle.append("closed")

    async with Container() as container:
        container.scoped(
            AsyncManagedService,
            managed_service,
            scope=Scope.WORKFLOW,
        )
        async with container.scope(Scope.WORKFLOW) as scope:
            first = await scope.make_async(AsyncManagedService)
            second = await scope.make_async(AsyncManagedService)
            assert first is second
            assert lifecycle == ["started"]

        assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_scope_resource_is_finalized_when_work_is_cancelled() -> None:
    """Finalize an async resource when its execution task is cancelled.

    Verify the behavior through results visible from the container API.
    """
    lifecycle: list[str] = []

    async def managed_service() -> AsyncIterator[AsyncManagedService]:
        """Yield a resource and record its asynchronous finalization.

        Yields:
            A resource owned by the active execution scope.
        """
        lifecycle.append("started")
        yield AsyncManagedService()
        lifecycle.append("closed")

    async with Container() as container:
        container.scoped(
            AsyncManagedService,
            managed_service,
            scope=Scope.WORKFLOW,
        )
        async with container.scope(Scope.WORKFLOW) as scope:
            with anyio.CancelScope() as cancellation:
                await scope.make_async(AsyncManagedService)
                cancellation.cancel()
                await anyio.Event().wait()

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_async_factory_can_create_a_singleton() -> None:
    """Await async factories and retain their singleton result.

    Verify the behavior through results visible from the container API.
    """

    async def create_service() -> AsyncFactoryService:
        """Create the service through an asynchronous factory.

        Returns:
            A new factory-owned service value.
        """
        return AsyncFactoryService()

    async with Container() as container:
        container.singleton(AsyncFactoryService, create_service)
        first = await container.make_async(AsyncFactoryService)
        second = await container.make_async(AsyncFactoryService)

    assert first is second


@pytest.mark.anyio
async def test_factory_resolves_transient_values_when_invoked() -> None:
    """Return a lazy typed callable that resolves through the container.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        container.bind(TransientFactoryValue)
        create_value = container.factory_async(TransientFactoryValue)
        first = await create_value()
        second = await create_value()

    assert isinstance(first, TransientFactoryValue)
    assert isinstance(second, TransientFactoryValue)
    assert first is not second


@pytest.mark.anyio
async def test_call_injects_dependencies_and_uses_explicit_parameters() -> None:
    """Resolve annotated services and preserve caller-supplied values.

    Verify the behavior through results visible from the container API.
    """

    def process(
        dependency: CallDependency,
        attempts: int,
    ) -> tuple[CallDependency, int]:
        """Return arguments for inspection by the test.

        Args:
            dependency: Automatically resolved service dependency.
            attempts: Explicit scalar value supplied by the caller.

        Returns:
            The resolved dependency and explicit scalar value.
        """
        return dependency, attempts

    async with Container() as container:
        dependency, attempts = await container.call_async(
            process,
            {"attempts": _EXPECTED_ATTEMPTS},
        )

    assert isinstance(dependency, CallDependency)
    assert attempts == _EXPECTED_ATTEMPTS


@pytest.mark.anyio
async def test_call_awaits_async_callbacks() -> None:
    """Await an asynchronous callback after resolving its dependencies.

    Verify the behavior through results visible from the container API.
    """

    async def process(dependency: CallDependency) -> CallDependency:
        """Return the dependency resolved for this callback.

        Args:
            dependency: Automatically resolved service dependency.

        Returns:
            The same resolved dependency.
        """
        return dependency

    async with Container() as container:
        dependency = await container.call_async(process)

    assert isinstance(dependency, CallDependency)


@pytest.mark.anyio
async def test_call_rejects_unconsumed_explicit_parameters() -> None:
    """Reject arguments that cannot be passed to a callable signature.

    Verify the behavior through results visible from the container API.
    """

    def process() -> None:
        """Represent a callable without named parameters.

        Keep this helper local so captured test state stays isolated.
        """

    async with Container() as container:
        with pytest.raises(BindingError):
            await container.call_async(process, {"unknown": True})


@pytest.mark.anyio
async def test_method_bindings_dispatch_through_callable_injection() -> None:
    """Resolve registered method callbacks with native aliases.

    Verify the behavior through results visible from the container API.
    """

    def process(dependency: CallDependency, label: str) -> str:
        """Return an observable result from injected and explicit values.

        Args:
            dependency: Automatically resolved callable dependency.
            label: Explicit value supplied to the bound callback.

        Returns:
            The label for verification after successful dependency injection.
        """
        assert isinstance(dependency, CallDependency)
        return label

    async with Container() as container:
        container.bind_method("worker.process", process)
        assert container.has_method_binding("worker.process")
        result = await container.call_method_binding_async(
            "worker.process",
            {"label": "ready"},
        )

    assert result == "ready"


@pytest.mark.anyio
async def test_unbound_abstract_dependency_raises_native_error() -> None:
    """Translate a missing backend factory into a native exception.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        with pytest.raises(BindingResolutionError) as error:
            await container.make_async(ServiceWithMissingContract)

    assert error.value.__cause__ is not None


@pytest.mark.anyio
async def test_registered_alias_resolves_tagged_singleton() -> None:
    """Resolve a service by alias and reuse it in its registered tag.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        container.singleton_if(TaggedService)
        container.alias(TaggedService, "tagged")
        container.tag(TaggedService, "workers")

        assert container.bound(TaggedService)
        assert container.has("tagged")
        assert container.is_alias("tagged")
        assert container.is_shared("tagged")
        assert container.get_alias(TaggedService) == "tagged"
        assert TaggedService in container.get_bindings()

        resolved = await container.make_async("tagged")
        tagged = await container.tagged_async("workers")

    assert isinstance(resolved, TaggedService)
    assert tagged == [resolved]


@pytest.mark.anyio
async def test_registration_freezes_after_first_graph_composition() -> None:
    """Reject live mutations that could invalidate active graph resources.

    Verify the behavior through results visible from the container API.
    """
    async with Container() as container:
        await container.make_async(Repository)
        with pytest.raises(BindingError):
            container.singleton(SharedService)


@pytest.mark.anyio
async def test_dynamic_graph_generation_limit_is_enforced() -> None:
    """Bound graph metadata retained by a long-lived application container.

    Verify the behavior through results visible from the container API.
    """
    async with Container(max_graph_generations=1) as container:
        await container.make_async(Repository)
        with pytest.raises(GraphLimitError):
            await container.make_async(DocumentService)


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_graph_limit_counts_generations_in_concurrent_scopes() -> None:
    """Bound graphs across concurrent task-local execution scopes.

    Verify the behavior through results visible from the container API.
    """
    first_scope_ready = anyio.Event()
    release_first_scope = anyio.Event()

    async def hold_first_graph() -> None:
        """Keep one dynamically composed graph alive during the check.

        Keep this helper local so captured test state stays isolated.
        """
        async with container.scope(Scope.WORKFLOW) as scope:
            await scope.make_async(ScopedService)
            first_scope_ready.set()
            await release_first_scope.wait()

    async def check_second_graph() -> None:
        """Reject another graph while the configured limit is occupied.

        Keep this helper local so captured test state stays isolated.
        """
        await first_scope_ready.wait()
        try:
            async with container.scope(Scope.WORKFLOW) as scope:
                with pytest.raises(GraphLimitError):
                    await scope.make_async(TaggedService)
        finally:
            release_first_scope.set()

    async with Container(max_graph_generations=1) as container:
        with anyio.fail_after(2):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(hold_first_graph)
                task_group.start_soon(check_second_graph)
