"""Provide Titanspan's native synchronous-first service container.

Titanspan owns registration, aliases, lifetime metadata, and active execution
scope handling. Sync-safe graphs resolve immediately; explicit async methods
support asynchronous initialization and resource lifecycles. The private
dependency adapter composes validated graphs and finalizes resources.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable as AwaitableABC
from collections.abc import Coroutine as CoroutineABC
from contextlib import AsyncExitStack, ExitStack
from contextvars import ContextVar, Token
from dataclasses import dataclass
from inspect import (
    Parameter,
    Signature,
    isabstract,
    isasyncgenfunction,
    isawaitable,
    iscoroutine,
    iscoroutinefunction,
    signature,
    unwrap,
)
from threading import RLock
from typing import (
    TYPE_CHECKING,
    Annotated,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from titanspan.container._backends.dependency_engine import (
    DependencyGraph,
    EngineBinding,
    GraphRequest,
    SyncDependencyGraph,
    asynchronous_dependency_path,
    create_dependency_graph,
    create_sync_dependency_graph,
    discover_dependency_types,
)
from titanspan.container.binding import Binding, Lifetime, ServiceFactory
from titanspan.container.decorators import binding_declaration
from titanspan.container.exceptions import (
    AsyncResolutionRequiredError,
    BindingError,
    BindingResolutionError,
    ContainerClosedError,
    GraphLimitError,
    ScopeError,
)
from titanspan.container.scope import Scope
from titanspan.contracts import ServiceContainer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping
    from types import TracebackType

_NESTED_SCOPE_ERROR = (
    "Nested scopes must advance the configured lifecycle hierarchy."
)
_APPLICATION_SCOPE_ERROR = "The application scope is owned by the container."
_INACTIVE_SCOPE_ERROR = "The requested execution scope is not active."
_REENTERED_SCOPE_ERROR = "An execution scope context can only be entered once."
_SCOPED_BINDING_ERROR = "Scoped bindings require an execution scope."
_EMPTY_ALIAS_ERROR = "Service aliases must not be empty."
_EMPTY_TAG_ERROR = "Service tags must not be empty."
_INHERITED_SCOPE_ERROR = "An inherited execution scope has closed."
_ACTIVE_SCOPE_ERROR = "Execution scopes must close before the container."
_CLOSED_CONTAINER_ERROR = "The service container is closed."
_SCOPE_FINALIZATION_ERROR = "Execution scope resource finalization failed."
_FROZEN_BINDINGS_ERROR = "Bindings are immutable after graph composition."
_GRAPH_LIMIT_ERROR = "The configured graph generation limit has been reached."
_INVALID_GRAPH_LIMIT_ERROR = "The graph generation bound must be positive."
_EMPTY_METHOD_BINDING_ERROR = "Method binding names must not be empty."
_MISSING_METHOD_BINDING_ERROR = "No callable is registered for this method."
_CALL_SIGNATURE_ERROR = "Unable to inspect the callable signature."
_CALL_PARAMETER_ERROR = "The callable received unknown explicit parameters."
_CALL_ANNOTATION_ERROR = "A required callable parameter is not resolvable."
_ASYNC_RESOLUTION_ERROR = (
    "Synchronous resolution requires an asynchronous dependency path."
)
_SYNC_ASYNC_CALLBACK_ERROR = (
    "Use call_async for asynchronous callbacks or dependencies."
)
_SYNC_AWAITABLE_RESULT_ERROR = (
    "The callable returned an awaitable; use call_async."
)
_APPLICATION_GRAPH_ERROR = (
    "The application graph must support async resolution."
)
_APPLICATION_DEPENDENCY_GRAPH_ERROR = (
    "Application dependencies require an async graph."
)
_ASYNC_GRAPH_ERROR = "Async scopes require an async backend graph."
_APPLICATION_RESOURCE_GRAPH_ERROR = (
    "Application resource graphs must be asynchronous."
)
_APPLICATION_DEPENDENCY_MODE_ERROR = (
    "Application dependencies require an async graph."
)
_ASYNC_SCOPE_SYNC_ERROR = (
    "Use async resolution for a dependency not yet entered in this scope."
)
_SYNC_SCOPE_ASYNC_ERROR = (
    "Async-only dependencies require an asynchronous execution scope."
)
_PRIMITIVE_TYPES = (str, int, float, bool, bytes, object)
_DEFAULT_MAX_GRAPH_GENERATIONS = 128


@dataclass(frozen=True, slots=True)
class _ScopeCallbacks:
    """Carry lifecycle accounting callbacks into execution scopes.

    Attributes:
        ensure_open: Rejects scope entry after container shutdown.
        entered: Counts a successfully activated scope.
        exited: Releases active scope and graph counts after cleanup.
        generation_created: Counts a scope-owned graph generation.
    """

    ensure_open: Callable[[], None]
    entered: Callable[[], None]
    exited: Callable[[int], None]
    generation_created: Callable[[], None]


class _Generation:
    """Hold one validated graph for a discovered concrete entry point.

    Attributes:
        identifier: Stable identity used by active scope frames.
        root: Type that caused this graph to be composed.
        graph: Private adapter for the selected sync or async mode.
    """

    def __init__(
        self,
        identifier: int,
        root: type[object],
        graph: DependencyGraph | SyncDependencyGraph,
    ) -> None:
        """Store one graph generation without exposing its backend.

        Args:
            identifier: Unique generation number within the container.
            root: Concrete type requested when the graph was created.
            graph: Private dependency graph adapter.
        """
        self.identifier = identifier
        self.root = root
        self.graph = graph


class ContainerScope:
    """Represent one task-local scope with explicit sync and async entry.

    Synchronous entry uses a synchronous backend child and synchronous
    finalizers. Asynchronous entry uses the owning async graph and preserves
    async resource cleanup. A frame can be entered only once.
    """

    def __init__(
        self,
        container: Container,
        scope: Scope,
        scope_context: ContextVar[tuple[ContainerScope, ...]],
        callbacks: _ScopeCallbacks,
    ) -> None:
        """Create an inactive execution scope.

        Args:
            container: Application container that owns backend graphs.
            scope: Lifecycle name to enter.
            scope_context: Execution-local stack owned by the container.
            callbacks: Lifecycle accounting functions owned by the container.
        """
        self._container = container
        self.scope = scope
        self._scope_context = scope_context
        self._callbacks = callbacks
        self._parent: ContainerScope | None = None
        self._token: Token[tuple[ContainerScope, ...]] | None = None
        self._exit_stack = AsyncExitStack()
        self._sync_exit_stack = ExitStack()
        self._graphs: dict[int, DependencyGraph] = {}
        self._sync_graphs: dict[int, SyncDependencyGraph] = {}
        self._generations: dict[tuple[type[object], bool], _Generation] = {}
        self._instances: dict[type[object], object] = {}
        self._lock = asyncio.Lock()
        self._active = False
        self._entered = False
        self._synchronous = False

    def __enter__(self) -> ContainerScope:
        """Activate a scope whose resources support synchronous cleanup.

        Returns:
            This active scope.

        Raises:
            ContainerClosedError: If the owning container is closed.
            ScopeError: If lifecycle ordering is invalid.
        """
        self._activate(synchronous=True)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the active context and finalize synchronous resources.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Active traceback, if any.
        """
        self._deactivate()
        try:
            self._sync_exit_stack.__exit__(
                exception_type,
                exception,
                traceback,
            )
        except BindingResolutionError:
            raise
        except Exception as error:
            raise BindingResolutionError(_SCOPE_FINALIZATION_ERROR) from error
        finally:
            self._callbacks.exited(len(self._generations))

    async def __aenter__(self) -> ContainerScope:
        """Activate the scope in the current asynchronous context.

        Returns:
            This scope, which provides resolution methods.

        Raises:
            ContainerClosedError: If the owning container is closed.
            ScopeError: If nested scopes do not advance the scope hierarchy.
        """
        self._activate(synchronous=False)
        return self

    def _activate(self, *, synchronous: bool) -> None:
        """Validate and install this scope in the execution-local stack.

        Args:
            synchronous: Whether the caller selected sync scope management.

        Raises:
            ContainerClosedError: If the owning container is closed.
            ScopeError: If lifecycle ordering or reentry is invalid.
        """
        self._callbacks.ensure_open()
        parents = self._scope_context.get()
        if parents:
            self._parent = parents[-1]
            if _scope_level(self.scope) <= _scope_level(self._parent.scope):
                raise ScopeError(_NESTED_SCOPE_ERROR)
        elif self.scope is Scope.APPLICATION:
            raise ScopeError(_APPLICATION_SCOPE_ERROR)
        if self._entered:
            raise ScopeError(_REENTERED_SCOPE_ERROR)

        self._entered = True
        self._active = True
        self._synchronous = synchronous
        self._token = self._scope_context.set(
            (*parents, self),
        )
        self._callbacks.entered()

    def _deactivate(self) -> None:
        """Restore the prior execution-local scope stack exactly once.

        Resetting the token prevents a closed scope from remaining visible
        to later work in this execution context.
        """
        self._active = False
        if self._token is not None:
            self._scope_context.reset(self._token)

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore context and finalize resources created in this scope.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Active traceback, if any.

        Side Effects:
            Closes every backend child entered by this frame in reverse order.
        """
        self._deactivate()
        try:
            await self._exit_stack.__aexit__(
                exception_type,
                exception,
                traceback,
            )
        except BindingResolutionError:
            raise
        except Exception as error:
            raise BindingResolutionError(_SCOPE_FINALIZATION_ERROR) from error
        finally:
            self._callbacks.exited(len(self._generations))

    def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service within this active execution scope.

        Args:
            service: Registered or automatically constructible service type.

        Returns:
            The resolved service instance.

        Raises:
            ScopeError: If this scope is inactive or inherited after exit.
        """
        if not self._active:
            raise ScopeError(_INACTIVE_SCOPE_ERROR)
        return self._container.make(service)

    async def make_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service through its explicit async operation.

        Args:
            service: Registered or automatically constructible service type.

        Returns:
            The service instance resolved within this scope.
        """
        if not self._active:
            raise ScopeError(_INACTIVE_SCOPE_ERROR)
        return await self._container.make_async(service)

    def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service using the concise synchronous method name.

        Args:
            service: Service key requested within the active scope.

        Returns:
            The resolved service instance.
        """
        return self.make(service)

    async def get_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service using the explicit asynchronous method name.

        Args:
            service: Service key requested within the active scope.

        Returns:
            The resolved service instance.
        """
        return await self.make_async(service)

    @property
    def is_active(self) -> bool:
        """Return whether this frame still owns an open execution scope.

        Returns:
            ``True`` between successful entry and completed cleanup.
        """
        return self._active

    @property
    def is_synchronous(self) -> bool:
        """Report whether synchronous scope cleanup owns this frame.

        Returns:
            ``True`` when the frame was entered with a ``with`` statement.
        """
        return self._synchronous

    def entered_async_graph(
        self,
        identifier: int,
    ) -> DependencyGraph | None:
        """Return an already entered backend child without exposing storage.

        Args:
            identifier: Graph generation whose child may be active.

        Returns:
            The child graph for this frame, if one has been entered.
        """
        return self._graphs.get(identifier)

    def find_instance(
        self, service: type[object]
    ) -> tuple[bool, object | None]:
        """Look up a tracked scoped value without conflating ``None``.

        Args:
            service: Service type stored in this frame.

        Returns:
            A pair containing a membership flag and the stored value.
        """
        return service in self._instances, self._instances.get(service)

    def instance_snapshot(self) -> Mapping[type[object], object]:
        """Return a shallow snapshot for seeding a new graph generation.

        Returns:
            Scoped service identities observed through this container API.
        """
        return dict(self._instances)

    def remember_instance(
        self,
        service: type[object],
        instance: object,
    ) -> None:
        """Retain a resolved value for later graphs in this scope.

        Args:
            service: Canonical service type.
            instance: Resolved object whose identity must be preserved.
        """
        self._instances[service] = instance

    def generation_for(
        self,
        service: type[object],
        *,
        asynchronous: bool,
    ) -> _Generation | None:
        """Return a mode-specific graph generation for a service root.

        Args:
            service: Root type previously composed in this frame.
            asynchronous: Whether the graph supports async resolution.

        Returns:
            The frame-owned generation, if present.
        """
        return self._generations.get((service, asynchronous))

    def own_generation(
        self,
        service: type[object],
        generation: _Generation,
    ) -> None:
        """Attach a graph generation to this frame's cleanup lifecycle.

        Args:
            service: Root type served by the graph.
            generation: Generation whose lifetime ends with this scope.

        Side Effects:
            Registers graph cleanup before child scope cleanup is added.
        """
        is_async_graph = isinstance(generation.graph, DependencyGraph)
        self._generations[(service, is_async_graph)] = generation
        self._callbacks.generation_created()
        if isinstance(generation.graph, SyncDependencyGraph):
            if self._synchronous:
                self._sync_exit_stack.callback(generation.graph.close)
            else:
                self._exit_stack.callback(generation.graph.close)
            return
        if self._synchronous:
            raise ScopeError(_SYNC_SCOPE_ASYNC_ERROR)
        self._exit_stack.push_async_callback(generation.graph.close)

    async def graph_for(
        self,
        generation: _Generation,
        parent_graph: DependencyGraph,
    ) -> DependencyGraph:
        """Return this frame's child graph for one generation.

        Args:
            generation: Graph generation being used by the resolution.
            parent_graph: Parent-scope graph for this generation.

        Returns:
            A child graph whose cache and resources belong to this frame.
        """
        async with self._lock:
            graph = self._graphs.get(generation.identifier)
            if graph is None:
                graph = await self._exit_stack.enter_async_context(
                    parent_graph.scope(self.scope.value),
                )
                self._graphs[generation.identifier] = graph
            return graph

    def graph_for_sync(
        self,
        generation: _Generation,
    ) -> SyncDependencyGraph:
        """Return a synchronous backend child owned by this scope frame.

        Args:
            generation: Graph generation used for dependency discovery.

        Returns:
            A synchronous backend view entered for this scope.
        """
        if not self._active:
            raise ScopeError(_ASYNC_SCOPE_SYNC_ERROR)
        graph = self._sync_graphs.get(generation.identifier)
        if graph is not None:
            return graph
        root_graph = generation.graph
        if not isinstance(root_graph, SyncDependencyGraph):
            raise ScopeError(_ASYNC_SCOPE_SYNC_ERROR)
        if self._synchronous:
            graph = self._sync_exit_stack.enter_context(
                root_graph.scope(self.scope.value),
            )
        else:
            graph = self._exit_stack.enter_context(
                root_graph.scope(self.scope.value),
            )
        self._sync_graphs[generation.identifier] = graph
        return graph


class Container(ServiceContainer):
    """Register services and resolve sync-safe graphs synchronously.

    Bindings are mutable until the first graph is requested. Concrete
    unregistered classes are discovered recursively by the private graph
    adapter. Sync resolution uses the async backend's documented sync getter,
    preserving its application cache. Async factories use the explicitly
    asynchronous methods. Each discovered root has a bounded graph generation.

    Attributes:
        providers: Optional advanced interoperability registrations. Ordinary
            application code should use Titanspan-owned binding methods.

    Notes:
        Execution scopes map onto a finite hierarchy. Request, connection,
        job, and workflow share a level; node and agent share the next; tool
        and task share the last. Equivalent-level scopes cannot be nested.
    """

    def __init__(
        self,
        *,
        providers: Iterable[object] = (),
        max_graph_generations: int = _DEFAULT_MAX_GRAPH_GENERATIONS,
    ) -> None:
        """Create an application-owned service registry.

        Args:
            providers: Optional advanced provider objects used by integration
                adapters. Native applications should register through methods
                such as ``bind`` and ``singleton``.
            max_graph_generations: Maximum graph roots retained at once.

        Raises:
            BindingError: If the graph generation bound is not positive.
        """
        if max_graph_generations <= 0:
            raise BindingError(_INVALID_GRAPH_LIMIT_ERROR)
        self.providers = tuple(providers)
        self.max_graph_generations = max_graph_generations
        self._bindings: dict[type[object], Binding[object]] = {}
        self._dependency_types_by_root: dict[
            type[object], frozenset[type[object]]
        ] = {}
        self._aliases: dict[str, type[object]] = {}
        self._tags: dict[str, list[type[object]]] = {}
        self._method_bindings: dict[str, Callable[..., object]] = {}
        self._shared_instances: dict[type[object], object] = {}
        self._shared_resolution_locks: dict[type[object], asyncio.Lock] = {}
        self._generations: list[DependencyGraph] = []
        self._generation_by_type: dict[type[object], _Generation] = {}
        self._next_generation_id = 0
        self._active_scopes: ContextVar[tuple[ContainerScope, ...]] = (
            ContextVar(f"titanspan_container_scopes_{id(self)}", default=())
        )
        self._generation_lock = RLock()
        self._closed = False
        self._frozen = False
        self._active_scope_count = 0
        self._scope_generation_count = 0
        self._scope_callbacks = _ScopeCallbacks(
            ensure_open=self._ensure_open,
            entered=self._scope_entered,
            exited=self._scope_exited,
            generation_created=self._scope_generation_created,
        )

    @property
    def active_scope_count(self) -> int:
        """Return the number of execution scopes that have not finalized.

        Returns:
            The container-wide active scope count.

        Notes:
            This supports same-event-loop lifecycle coordination. It does not
            establish cross-thread synchronization.
        """
        return self._active_scope_count

    async def __aenter__(self) -> Container:
        """Return this container for deterministic asynchronous ownership.

        Returns:
            The open container.

        Raises:
            ContainerClosedError: If this instance has already been closed.
        """
        self._ensure_open()
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close all graph generations after the owning context exits.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception, if any.
            traceback: Active traceback, if any.
        """
        await self.aclose()

    def bind[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register a transient implementation or factory.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory. The service
                type is used when this argument is omitted.

        Notes:
            A later registration replaces the prior registration before graph
            composition. Registration freezes when the first graph is built.
        """
        self._register(
            service,
            service if implementation is None else implementation,
            Lifetime.TRANSIENT,
            Scope.APPLICATION,
        )

    def bind_if[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register a transient implementation only when no binding exists.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
        """
        if service not in self._bindings:
            self.bind(service, implementation)

    def singleton[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register one application-owned instance per service type.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.

        Notes:
            The instance belongs to this container, not the Python process.
        """
        self._register(
            service,
            service if implementation is None else implementation,
            Lifetime.SINGLETON,
            Scope.APPLICATION,
        )

    def singleton_if[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register an application singleton only when no binding exists.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
        """
        if service not in self._bindings:
            self.singleton(service, implementation)

    def scoped[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
        *,
        scope: Scope = Scope.REQUEST,
    ) -> None:
        """Register a service cached within an active execution scope.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
            scope: Lifecycle scope that owns the cached instance.
        """
        if scope is Scope.APPLICATION:
            raise BindingError(_SCOPED_BINDING_ERROR)
        self._register(
            service,
            service if implementation is None else implementation,
            Lifetime.SCOPED,
            scope,
        )

    def scoped_if[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
        *,
        scope: Scope = Scope.REQUEST,
    ) -> None:
        """Register a scoped service only when no binding exists.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
            scope: Lifecycle scope that owns the cached instance.
        """
        if service not in self._bindings:
            self.scoped(service, implementation, scope=scope)

    def instance[ServiceT](
        self,
        service: type[ServiceT],
        value: ServiceT,
    ) -> None:
        """Register an externally owned instance under a service contract.

        Args:
            service: Public service key.
            value: Existing instance. The container does not own its cleanup.
        """
        self._ensure_mutable()
        self._dependency_types_by_root.clear()
        self._bindings[service] = Binding(
            service=service,
            implementation=None,
            lifetime=Lifetime.SINGLETON,
            scope=Scope.APPLICATION,
            instance=value,
            instance_binding=True,
        )
        self._shared_instances[service] = value

    def alias[ServiceT](
        self,
        service: type[ServiceT],
        name: str,
    ) -> None:
        """Register a string name for a canonical service type.

        Args:
            service: Canonical dependency key.
            name: Name accepted by ``make`` and ``get``.

        Raises:
            BindingError: If the name is empty or already targets another key.
        """
        self._ensure_mutable()
        if not name:
            raise BindingError(_EMPTY_ALIAS_ERROR)
        current = self._aliases.get(name)
        if current is not None and current is not service:
            message = f"The alias {name!r} is already registered."
            raise BindingError(message)
        self._aliases[name] = service

    def tag(
        self,
        services: type[object] | Iterable[type[object]],
        name: str,
    ) -> None:
        """Associate one or more service keys with an ordered tag.

        Args:
            services: Service type or iterable of service types.
            name: Tag used by ``tagged`` to resolve the services.
        """
        self._ensure_mutable()
        if not name:
            raise BindingError(_EMPTY_TAG_ERROR)
        values = (services,) if isinstance(services, type) else tuple(services)
        tagged = self._tags.setdefault(name, [])
        for service in values:
            if service not in tagged:
                tagged.append(service)

    def tagged(self, name: str) -> list[object]:
        """Resolve sync-safe tagged services in registration order.

        Args:
            name: Tag previously registered with ``tag``.

        Returns:
            Resolved values. Unknown tags return an empty list.
        """
        return [self.make(service) for service in self._tags.get(name, [])]

    async def tagged_async(self, name: str) -> list[object]:
        """Resolve tagged services through async-capable graphs.

        Args:
            name: Tag previously registered with ``tag``.

        Returns:
            Resolved values in registration order.
        """
        return [
            await self.make_async(service)
            for service in self._tags.get(name, [])
        ]

    def factory[ServiceT](
        self,
        service: type[ServiceT],
    ) -> Callable[[], ServiceT]:
        """Return a lazy synchronous resolver for a service type.

        Args:
            service: Service resolved each time the returned callable is used.

        Returns:
            A callable that delegates to synchronous container resolution.

        Notes:
            Transient bindings produce fresh values; cached lifetimes keep
            their normal application or execution-scope semantics.
        """

        def resolve() -> ServiceT:
            """Resolve the configured service when invoked.

            Returns:
                The service value from the active container context.
            """
            return self.make(service)

        return resolve

    def factory_async[ServiceT](
        self,
        service: type[ServiceT],
    ) -> Callable[[], Awaitable[ServiceT]]:
        """Return a lazy asynchronous resolver for a service type.

        Args:
            service: Service resolved each time the returned callable is used.

        Returns:
            A coroutine factory using the async resolution path.
        """

        async def resolve() -> ServiceT:
            """Resolve the configured service when invoked.

            Returns:
                The service value from the active container context.
            """
            return await self.make_async(service)

        return resolve

    async def call_async[**P, ReturnT](
        self,
        callback: Callable[P, ReturnT] | Callable[P, Awaitable[ReturnT]],
        parameters: Mapping[str, object] | None = None,
    ) -> ReturnT:
        """Invoke a callable after resolving its annotated dependencies.

        Args:
            callback: Synchronous or asynchronous application callable.
            parameters: Explicit values keyed by callable parameter name.

        Returns:
            The callback result, awaiting it when it is awaitable.

        Raises:
            BindingError: If explicit values name unsupported parameters.
            BindingResolutionError: If a required parameter cannot be resolved.

        Notes:
            Synchronous callbacks run on the calling thread. Blocking work
            should be offloaded by the application explicitly.
        """
        call_signature, annotations = self._call_signature(
            cast("Callable[..., object]", callback)
        )
        arguments, keywords = await self._resolve_call_arguments_async(
            call_signature,
            annotations,
            {} if parameters is None else dict(parameters),
        )
        callable_callback = cast(
            "Callable[..., ReturnT] | Callable[..., Awaitable[ReturnT]]",
            callback,
        )
        result = callable_callback(*arguments, **keywords)
        if isawaitable(result):
            return await cast("Awaitable[ReturnT]", result)
        return cast("ReturnT", result)

    @staticmethod
    def _call_signature(
        callback: Callable[..., object],
    ) -> tuple[Signature, Mapping[str, object]]:
        """Read a callback signature and resolve its annotations.

        Args:
            callback: Function, bound method, or callable instance.

        Returns:
            The inspectable signature and evaluated type hints.

        Raises:
            BindingResolutionError: If Python cannot inspect the callback.
        """
        try:
            callback_signature = signature(callback)
            annotations = get_type_hints(
                callback,
                include_extras=True,
            )
        except (NameError, TypeError, ValueError) as error:
            raise BindingResolutionError(_CALL_SIGNATURE_ERROR) from error
        return callback_signature, annotations

    def call[**P, ReturnT](
        self,
        callback: Callable[P, ReturnT],
        parameters: Mapping[str, object] | None = None,
    ) -> ReturnT:
        """Invoke a synchronous callable with resolved dependencies.

        Args:
            callback: Synchronous application callable.
            parameters: Explicit values keyed by callable parameter name.

        Returns:
            The direct result returned by the callable.

        Raises:
            AsyncResolutionRequiredError: If resolution or callback execution
                requires asynchronous work.
            BindingError: If explicit values name unsupported parameters.
            BindingResolutionError: If a required parameter cannot be resolved.
        """
        callable_callback = cast("Callable[..., object]", callback)
        call_signature, annotations = self._call_signature(callable_callback)
        return_hint = annotations.get(
            "return",
            call_signature.return_annotation,
        )
        if _is_async_callable(callable_callback) or _is_awaitable_hint(
            return_hint,
        ):
            raise AsyncResolutionRequiredError(_SYNC_ASYNC_CALLBACK_ERROR)
        arguments, keywords = self._resolve_call_arguments_sync(
            call_signature,
            annotations,
            {} if parameters is None else dict(parameters),
        )
        result = callable_callback(*arguments, **keywords)
        if isawaitable(result):
            if iscoroutine(result):
                result.close()
            raise AsyncResolutionRequiredError(_SYNC_AWAITABLE_RESULT_ERROR)
        return cast("ReturnT", result)

    def _resolve_call_arguments_sync(
        self,
        callback_signature: Signature,
        annotations: Mapping[str, object],
        explicit: dict[str, object],
    ) -> tuple[list[object], dict[str, object]]:
        """Resolve synchronous callback arguments and validate overrides.

        Args:
            callback_signature: Parameters accepted by the callable.
            annotations: Resolved callback parameter annotations.
            explicit: Caller-supplied values keyed by parameter name.

        Returns:
            Positional and keyword arguments ready for invocation.
        """
        positional: list[object] = []
        keywords: dict[str, object] = {}
        accepts_keywords = any(
            parameter.kind is Parameter.VAR_KEYWORD
            for parameter in callback_signature.parameters.values()
        )
        named_parameters = {
            name
            for name, parameter in callback_signature.parameters.items()
            if parameter.kind
            not in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}
        }
        unknown = set(explicit).difference(named_parameters)
        if unknown and not accepts_keywords:
            names = ", ".join(sorted(unknown))
            message = f"{_CALL_PARAMETER_ERROR} {names}."
            raise BindingError(message)
        keywords.update(
            (name, value) for name, value in explicit.items() if name in unknown
        )

        for name, parameter in callback_signature.parameters.items():
            if parameter.kind in {
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            }:
                continue
            if name in explicit:
                value = explicit[name]
            elif parameter.default is not Parameter.empty:
                if parameter.kind is Parameter.POSITIONAL_ONLY:
                    positional.append(parameter.default)
                continue
            else:
                value = self._resolve_call_parameter_sync(
                    name,
                    annotations.get(name, parameter.annotation),
                )
            if parameter.kind is Parameter.POSITIONAL_ONLY:
                positional.append(value)
            else:
                keywords[name] = value
        return positional, keywords

    def _resolve_call_parameter_sync(
        self,
        name: str,
        annotation: object,
    ) -> object:
        """Resolve one annotated callback service without guessing scalars.

        Args:
            name: Parameter name used in actionable resolution errors.
            annotation: Evaluated or declared Python type annotation.

        Returns:
            A resolved service instance.
        """
        if get_origin(annotation) is Annotated:
            arguments = get_args(annotation)
            annotation = arguments[0] if arguments else annotation
        if not isinstance(annotation, type) or annotation in _PRIMITIVE_TYPES:
            message = f"{_CALL_ANNOTATION_ERROR} Parameter {name!r}."
            raise BindingResolutionError(message)
        try:
            return self.make(cast("type[object]", annotation))
        except BindingResolutionError as error:
            message = f"Unable to resolve callable parameter {name!r}."
            raise BindingResolutionError(message) from error

    async def _resolve_call_arguments_async(
        self,
        callback_signature: Signature,
        annotations: Mapping[str, object],
        explicit: dict[str, object],
    ) -> tuple[list[object], dict[str, object]]:
        """Resolve a callable's required arguments and validate overrides.

        Args:
            callback_signature: Parameters accepted by the callable.
            annotations: Resolved callback parameter annotations.
            explicit: Caller-supplied values keyed by parameter name.

        Returns:
            Positional and keyword arguments ready for invocation.

        Raises:
            BindingError: If explicit values cannot be consumed.
            BindingResolutionError: If a required dependency is unavailable.
        """
        signature_parameters = callback_signature.parameters
        accepts_keywords = any(
            parameter.kind is Parameter.VAR_KEYWORD
            for parameter in signature_parameters.values()
        )
        named_parameters = {
            name
            for name, parameter in signature_parameters.items()
            if parameter.kind
            not in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}
        }
        unknown = set(explicit).difference(named_parameters)
        if unknown and not accepts_keywords:
            names = ", ".join(sorted(unknown))
            message = f"{_CALL_PARAMETER_ERROR} {names}."
            raise BindingError(message)

        positional: list[object] = []
        keywords = {
            name: value for name, value in explicit.items() if name in unknown
        }
        for name, parameter in signature_parameters.items():
            if parameter.kind in {
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
            }:
                continue
            if name in explicit:
                value = explicit[name]
            elif parameter.default is not Parameter.empty:
                if parameter.kind is Parameter.POSITIONAL_ONLY:
                    positional.append(parameter.default)
                continue
            else:
                value = await self._resolve_call_parameter_async(
                    name,
                    annotations.get(name, parameter.annotation),
                )
            if parameter.kind is Parameter.POSITIONAL_ONLY:
                positional.append(value)
            else:
                keywords[name] = value
        return positional, keywords

    async def _resolve_call_parameter_async(
        self,
        name: str,
        annotation: object,
    ) -> object:
        """Resolve one annotated service parameter without guessing scalars.

        Args:
            name: Parameter name used in actionable resolution errors.
            annotation: Evaluated or declared Python type annotation.

        Returns:
            A resolved service instance.

        Raises:
            BindingResolutionError: If the annotation is missing or unsupported.
        """
        if get_origin(annotation) is Annotated:
            arguments = get_args(annotation)
            annotation = arguments[0] if arguments else annotation
        if not isinstance(annotation, type) or annotation in _PRIMITIVE_TYPES:
            message = f"{_CALL_ANNOTATION_ERROR} Parameter {name!r}."
            raise BindingResolutionError(message)
        try:
            service = cast("type[object]", annotation)
            return await self.make_async(service)
        except BindingResolutionError as error:
            message = f"Unable to resolve callable parameter {name!r}."
            raise BindingResolutionError(message) from error

    def bind_method(
        self,
        method: str,
        callback: Callable[..., object],
    ) -> None:
        """Register a callable for later method-key dispatch.

        Args:
            method: Stable application-defined method binding key.
            callback: Callable invoked through dependency-aware ``call``.

        Raises:
            BindingError: If the key is empty or registration is frozen.
        """
        self._ensure_mutable()
        if not method:
            raise BindingError(_EMPTY_METHOD_BINDING_ERROR)
        self._method_bindings[method] = callback

    def has_method_binding(self, method: str) -> bool:
        """Check whether a callable is registered for a method key.

        Args:
            method: Application-defined binding key.

        Returns:
            ``True`` if the key has a registered callback.
        """
        return method in self._method_bindings

    def call_method_binding(
        self,
        method: str,
        parameters: Mapping[str, object] | None = None,
    ) -> object:
        """Invoke a registered method callback with dependency injection.

        Args:
            method: Application-defined binding key.
            parameters: Optional caller-supplied parameter values.

        Returns:
            The synchronous or asynchronous callback result.

        Raises:
            BindingError: If the method key has no registered callback.
        """
        try:
            callback = self._method_bindings[method]
        except KeyError as error:
            raise BindingError(_MISSING_METHOD_BINDING_ERROR) from error
        result: object = self.call(callback, parameters)
        return result

    async def call_method_binding_async(
        self,
        method: str,
        parameters: Mapping[str, object] | None = None,
    ) -> object:
        """Invoke a registered callback through asynchronous injection.

        Args:
            method: Application-defined binding key.
            parameters: Optional caller-supplied parameter values.

        Returns:
            The callback result after asynchronous dependency resolution.
        """
        try:
            callback = self._method_bindings[method]
        except KeyError as error:
            raise BindingError(_MISSING_METHOD_BINDING_ERROR) from error
        return await self.call_async(callback, parameters)

    @overload
    def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Synchronously resolve a class-keyed service.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The immediate service instance with its declared type.
        """

    @overload
    def make(self, service: str) -> object:
        """Synchronously resolve a named service.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    def make(
        self,
        service: type[object] | str,
    ) -> object:
        """Synchronously resolve a graph that requires no async resources.

        Args:
            service: Service type or registered string alias.

        Returns:
            The resolved service instance.

        Raises:
            BindingError: If a string alias is unknown.
            AsyncResolutionRequiredError: If a factory requires awaiting.
            BindingResolutionError: If graph construction or resolution fails.
            ContainerClosedError: If the container has begun shutdown.
            ScopeError: If an inherited execution scope has already closed.
        """
        return self._make_sync(service)

    @overload
    async def make_async[ServiceT](
        self,
        service: type[ServiceT],
    ) -> ServiceT:
        """Asynchronously resolve a class-keyed service.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The resolved instance with its declared service type.
        """

    @overload
    async def make_async(self, service: str) -> object:
        """Asynchronously resolve a named service.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    async def make_async(
        self,
        service: type[object] | str,
    ) -> object:
        """Resolve a service through its explicitly asynchronous operation.

        Args:
            service: Service type or registered string alias.

        Returns:
            The resolved service instance.

        Raises:
            BindingError: If a string alias is unknown.
            BindingResolutionError: If graph construction or resolution fails.
            ContainerClosedError: If the container has begun shutdown.
            ScopeError: If an inherited execution scope has already closed.
        """
        self._ensure_open()
        key = self._resolve_key(service)
        frames = self._active_scopes.get()
        if frames and frames[-1].is_synchronous:
            path = self._async_path(key)
            if path is not None:
                raise ScopeError(_SYNC_SCOPE_ASYNC_ERROR)
            return self._make_sync(key)
        is_cached, cached = self._cached_value(key, frames)
        if is_cached:
            return cached
        async with AsyncExitStack() as lock_stack:
            for lock in self._shared_locks_for(key, frames):
                await lock_stack.enter_async_context(lock)
            if frames:
                await self._prime_application_dependencies(key)
            return await self._resolve_locked(key, frames)

    def make_with[ServiceT](
        self,
        service: type[ServiceT],
        parameters: Mapping[str, object],
    ) -> ServiceT:
        """Construct a service with explicit constructor values.

        Args:
            service: Concrete class to construct.
            parameters: Explicit constructor values keyed by parameter name.

        Returns:
            A newly constructed instance of ``service``.

        Notes:
            This operation bypasses the root service's cached binding while
            resolving omitted constructor dependencies through the container.
        """
        return cast("ServiceT", self.call(service, parameters))

    async def make_with_async[ServiceT](
        self,
        service: type[ServiceT],
        parameters: Mapping[str, object],
    ) -> ServiceT:
        """Construct a service with explicit values and async dependencies.

        Args:
            service: Concrete class to construct.
            parameters: Explicit constructor values keyed by parameter name.

        Returns:
            A newly constructed instance of ``service``.
        """
        return cast(
            "ServiceT",
            await self.call_async(service, parameters),
        )

    def _make_sync(self, service: type[object] | str) -> object:
        """Resolve one service synchronously through the shared graph cache.

        Args:
            service: Native service type or registered string alias.

        Returns:
            The resolved service instance.

        Raises:
            AsyncResolutionRequiredError: If the dependency path is async-only.
            BindingResolutionError: If synchronous backend resolution fails.
            ScopeError: If the active scope cannot use sync resolution.
        """
        self._ensure_open()
        key = self._resolve_key(service)
        frames = self._active_scopes.get()
        is_cached, cached = self._cached_value(key, frames)
        if is_cached:
            return cached
        path = self._async_path(key)
        if path is not None:
            dependency_path = " -> ".join(path)
            message = (
                f"{_ASYNC_RESOLUTION_ERROR} Dependency path: "
                f"{dependency_path}. Use make_async()."
            )
            raise AsyncResolutionRequiredError(message)

        if frames and not frames[-1].is_synchronous:
            generation = frames[-1].generation_for(
                key,
                asynchronous=True,
            )
            graph = (
                None
                if generation is None
                else self._entered_async_graph(generation, frames)
            )
            if generation is not None and graph is not None:
                return self._resolve_from_graph_sync(
                    key,
                    graph,
                    generation,
                    frames,
                )

        if frames:
            self._prime_application_dependencies_sync(key)
        generation = self._generation_for_sync(key, frames)
        if frames:
            frame = frames[-1]
            graph = frame.graph_for_sync(generation)
            resolve = graph.get
        else:
            graph = generation.graph
            if not isinstance(graph, DependencyGraph):
                raise BindingResolutionError(_APPLICATION_GRAPH_ERROR)
            resolve = graph.get_sync
        try:
            result = resolve(key)
        except Exception as error:
            raise self._translate_sync_error(key) from error
        self._remember(key, result, frames)
        self._remember_shared_dependencies_sync(
            key,
            generation,
            graph,
            frames,
        )
        return result

    def _async_path(self, service: type[object]) -> tuple[str, ...] | None:
        """Return a known async-only dependency chain without executing it.

        Args:
            service: Root type requested by synchronous resolution.

        Returns:
            A dependency path or ``None`` if its native graph is sync-safe.
        """
        bindings = tuple(
            self._engine_binding(binding) for binding in self._bindings.values()
        )
        return asynchronous_dependency_path(service, bindings)

    @staticmethod
    def _entered_async_graph(
        generation: _Generation,
        frames: tuple[ContainerScope, ...],
    ) -> DependencyGraph | None:
        """Return the deepest already-entered async graph for sync access.

        Args:
            generation: Existing graph generation.
            frames: Active async scope frames.

        Returns:
            The deepest entered graph, or ``None`` if one has not been entered.
        """
        graph = generation.graph
        for frame in frames:
            current = frame.entered_async_graph(generation.identifier)
            if current is None:
                return None
            graph = current
        if not isinstance(graph, DependencyGraph):
            return None
        return graph

    def _translate_sync_error(
        self,
        service: type[object],
    ) -> BindingResolutionError:
        """Translate an unclassified backend sync failure to a native error.

        Args:
            service: Requested native service key.

        Returns:
            An actionable native error preserving the backend cause.
        """
        message = (
            f"Unable to resolve {service.__qualname__} synchronously. "
            "If its integration provider requires async resolution, "
            "use make_async()."
        )
        return BindingResolutionError(message)

    async def _resolve_locked(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
    ) -> object:
        """Resolve after acquiring locks for shared graph dependencies.

        Args:
            service: Canonical service type.
            frames: Active execution-scope stack.

        Returns:
            The resolved service instance.
        """
        is_cached, cached = self._cached_value(service, frames)
        if is_cached:
            return cached
        generation = await self._generation_for(service, frames)
        graph = await self._graph_in_scope(generation, frames)
        result = await self._resolve_from_graph(service, graph)
        self._remember(service, result, frames)
        await self._remember_shared_dependencies(
            service,
            generation,
            graph,
            frames,
        )
        return result

    def _shared_locks_for(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
    ) -> tuple[asyncio.Lock, ...]:
        """Return ordered locks for shared bindings in a dependency closure.

        Args:
            service: Requested root whose annotated graph is inspected.
            frames: Active scopes used to identify already cached dependencies.

        Returns:
            One stable lock for each explicitly shared service dependency.
        """
        dependencies = self._dependency_types_for(service)
        shared = sorted(
            (
                dependency
                for dependency in dependencies
                if (policy := self._binding_policy(dependency)) is not None
                and policy[0] is not Lifetime.TRANSIENT
                and not self._cached_value(dependency, frames)[0]
            ),
            key=lambda dependency: (
                dependency.__module__,
                dependency.__qualname__,
            ),
        )
        return tuple(
            self._shared_resolution_locks.setdefault(
                dependency,
                asyncio.Lock(),
            )
            for dependency in shared
        )

    def _dependency_types_for(
        self,
        service: type[object],
    ) -> frozenset[type[object]]:
        """Return the cached constructor type closure for one graph root.

        Args:
            service: Native root whose constructor dependencies are inspected.

        Returns:
            Discovered service keys, including registered implementation
            dependencies.
        """
        dependencies = self._dependency_types_by_root.get(service)
        if dependencies is None:
            bindings = tuple(
                self._engine_binding(binding)
                for binding in self._bindings.values()
            )
            dependencies = discover_dependency_types(service, bindings)
            self._dependency_types_by_root[service] = dependencies
        return dependencies

    async def _prime_application_dependencies(
        self,
        root: type[object],
    ) -> None:
        """Resolve uncached application singletons before entering a scope.

        Args:
            root: Requested scoped root whose dependency graph is inspected.

        Notes:
            A request-owned backend graph must not become the cleanup owner of
            application resources. Resolve singleton dependencies through an
            application-owned graph first, then seed them into the request
            graph as external instances.
        """
        dependencies = sorted(
            self._dependency_types_for(root),
            key=lambda dependency: (
                dependency.__module__,
                dependency.__qualname__,
            ),
        )
        for dependency in dependencies:
            policy = self._binding_policy(dependency)
            if (
                policy is None
                or policy[0] is not Lifetime.SINGLETON
                or dependency in self._shared_instances
            ):
                continue
            generation = await self._generation_for(dependency, ())
            graph = generation.graph
            if not isinstance(graph, DependencyGraph):
                raise BindingResolutionError(
                    _APPLICATION_DEPENDENCY_GRAPH_ERROR
                )
            value = await self._resolve_from_graph(dependency, graph)
            self._remember(dependency, value, ())
            await self._remember_shared_dependencies(
                dependency,
                generation,
                graph,
                (),
            )

    def _prime_application_dependencies_sync(
        self,
        root: type[object],
    ) -> None:
        """Resolve sync-safe app singletons before entering a sync scope.

        Args:
            root: Scoped root whose dependency closure is being prepared.

        Raises:
            AsyncResolutionRequiredError: If an app singleton is async-only.
            BindingResolutionError: If synchronous singleton creation fails.
        """
        dependencies = sorted(
            self._dependency_types_for(root),
            key=lambda dependency: (
                dependency.__module__,
                dependency.__qualname__,
            ),
        )
        for dependency in dependencies:
            policy = self._binding_policy(dependency)
            if (
                policy is None
                or policy[0] is not Lifetime.SINGLETON
                or dependency in self._shared_instances
            ):
                continue
            generation = self._generation_for_sync(dependency, ())
            graph = generation.graph
            if not isinstance(graph, DependencyGraph):
                raise BindingResolutionError(
                    _APPLICATION_DEPENDENCY_GRAPH_ERROR
                )
            try:
                value = graph.get_sync(dependency)
            except Exception as error:
                raise self._translate_sync_error(dependency) from error
            self._remember(dependency, value, ())
            self._remember_shared_dependencies_sync(
                dependency,
                generation,
                graph,
                (),
            )

    def _cached_value(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
    ) -> tuple[bool, object | None]:
        """Find a value already retained by an active or application scope.

        Args:
            service: Canonical service key.
            frames: Active scope stack for the current task.

        Returns:
            A membership flag and cached value, preserving explicit ``None``.

        Raises:
            ScopeError: If an inherited execution frame has already closed.
        """
        for frame in frames:
            if not frame.is_active:
                raise ScopeError(_INHERITED_SCOPE_ERROR)
            is_cached, cached = frame.find_instance(service)
            if is_cached:
                return True, cached
        if service in self._shared_instances:
            return True, self._shared_instances[service]
        return False, None

    async def _graph_in_scope(
        self,
        generation: _Generation,
        frames: tuple[ContainerScope, ...],
    ) -> DependencyGraph:
        """Enter backend child scopes for the active task context.

        Args:
            generation: Graph generation selected for the service.
            frames: Active nested execution scopes.

        Returns:
            The deepest backend graph corresponding to the active scopes.
        """
        graph = generation.graph
        if not isinstance(graph, DependencyGraph):
            raise BindingResolutionError(_ASYNC_GRAPH_ERROR)
        for frame in frames:
            graph = await frame.graph_for(generation, graph)
        return graph

    @staticmethod
    async def _resolve_from_graph(
        service: type[object],
        graph: DependencyGraph,
    ) -> object:
        """Resolve a dependency and translate backend errors at the boundary.

        Args:
            service: Canonical service type.
            graph: Active private graph view.

        Returns:
            The resolved service instance.

        Raises:
            BindingResolutionError: If graph resolution fails.
        """
        try:
            return await graph.get(service)
        except Exception as error:
            message = f"Unable to resolve service {service.__qualname__}."
            raise BindingResolutionError(message) from error

    async def _remember_shared_dependencies(
        self,
        root: type[object],
        generation: _Generation,
        graph: DependencyGraph,
        frames: tuple[ContainerScope, ...],
    ) -> None:
        """Retain configured shared dependencies from the resolved graph.

        Args:
            root: Requested root service.
            generation: Graph containing inspected constructor types.
            graph: Active scoped graph used for resolution.
            frames: Current execution scope stack.

        Raises:
            BindingResolutionError: If a configured shared dependency fails.
        """
        try:
            for dependency in generation.graph.known_types:
                if dependency == root:
                    continue
                policy = self._binding_policy(dependency)
                if policy is None or policy[0] is Lifetime.TRANSIENT:
                    continue
                value = await graph.get(dependency)
                self._remember(dependency, value, frames)
        except Exception as error:
            message = f"Unable to retain dependencies for {root.__qualname__}."
            raise BindingResolutionError(message) from error

    def _resolve_from_graph_sync(
        self,
        service: type[object],
        graph: DependencyGraph,
        generation: _Generation,
        frames: tuple[ContainerScope, ...],
    ) -> object:
        """Resolve synchronously from a child of an active async scope.

        Args:
            service: Canonical service key.
            graph: Already entered async backend scope.
            generation: Graph metadata for shared dependency tracking.
            frames: Current task-local scope stack.

        Returns:
            The resolved instance, preserving the shared async graph cache.
        """
        try:
            result = graph.get_sync(service)
        except Exception as error:
            raise self._translate_sync_error(service) from error
        self._remember(service, result, frames)
        self._remember_shared_dependencies_sync(
            service,
            generation,
            graph,
            frames,
        )
        return result

    def _remember_shared_dependencies_sync(
        self,
        root: type[object],
        generation: _Generation,
        graph: DependencyGraph | SyncDependencyGraph,
        frames: tuple[ContainerScope, ...],
    ) -> None:
        """Track non-transient dependencies constructed by a sync graph.

        Args:
            root: Requested root service.
            generation: Graph containing inspected constructor types.
            graph: Sync-capable backend graph view.
            frames: Current execution-scope stack.

        Raises:
            BindingResolutionError: If a shared dependency cannot be retained.
        """
        try:
            for dependency in generation.graph.known_types:
                if dependency == root:
                    continue
                policy = self._binding_policy(dependency)
                if policy is None or policy[0] is Lifetime.TRANSIENT:
                    continue
                value = (
                    graph.get(dependency)
                    if isinstance(graph, SyncDependencyGraph)
                    else graph.get_sync(dependency)
                )
                self._remember(dependency, value, frames)
        except Exception as error:
            message = f"Unable to retain dependencies for {root.__qualname__}."
            raise BindingResolutionError(message) from error

    @overload
    def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Synchronously retrieve a class-keyed service.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The resolved instance with its declared service type.
        """

    @overload
    def get(self, service: str) -> object:
        """Synchronously retrieve a named service.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    def get(self, service: type[object] | str) -> object:
        """Resolve a sync-safe service using the concise method name.

        Args:
            service: Service type or registered string alias.

        Returns:
            The resolved service instance.
        """
        return self.make(service)

    @overload
    async def get_async[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Asynchronously retrieve a class-keyed service.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The resolved instance with its declared service type.
        """

    @overload
    async def get_async(self, service: str) -> object:
        """Asynchronously retrieve a named service.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    async def get_async(self, service: type[object] | str) -> object:
        """Resolve a service using the explicit async method name.

        Args:
            service: Service type or registered string alias.

        Returns:
            The resolved service instance.
        """
        return await self.make_async(service)

    def bound(self, service: type[object] | str) -> bool:
        """Return whether the service has an explicit registration.

        Args:
            service: Service type or registered string alias.

        Returns:
            ``True`` only for an explicit binding or resolvable alias.
        """
        if isinstance(service, str):
            service = self._aliases.get(service, service)
        return isinstance(service, type) and service in self._bindings

    def has(self, service: type[object] | str) -> bool:
        """Return whether a key is registered or is a concrete class.

        Args:
            service: Service type or alias to inspect.

        Returns:
            ``True`` for an explicit binding, alias, or non-abstract class.

        Notes:
            The check is structural only and never constructs an instance.
        """
        if isinstance(service, str):
            key = self._aliases.get(service)
            return key is not None and self.has(key)
        return service in self._bindings or not isabstract(service)

    def resolved(self, service: type[object] | str) -> bool:
        """Return whether this API has already observed a cached instance.

        Args:
            service: Service type or registered alias.

        Returns:
            ``True`` for a tracked singleton or active scoped instance.
        """
        if isinstance(service, str):
            service = self._aliases.get(service, service)
        if not isinstance(service, type):
            return False
        return service in self._shared_instances or any(
            frame.find_instance(service)[0]
            for frame in self._active_scopes.get()
        )

    def is_shared(self, service: type[object] | str) -> bool:
        """Return whether the explicit binding uses a cached lifetime.

        Args:
            service: Service type or registered alias.

        Returns:
            ``True`` for registered or declared cached lifetimes.
        """
        key = self._resolve_key(service)
        policy = self._binding_policy(key)
        return policy is not None and policy[0] is not Lifetime.TRANSIENT

    def is_alias(self, name: str) -> bool:
        """Return whether a string name is registered as an alias.

        Args:
            name: Name to inspect.

        Returns:
            ``True`` if the alias resolves to a service key.
        """
        return name in self._aliases

    def get_alias(self, service: type[object] | str) -> str | None:
        """Return the registered name for a service, if one exists.

        Args:
            service: Service type or alias.

        Returns:
            The first alias registered for the canonical service key.
        """
        key = self._resolve_key(service)
        return next(
            (name for name, target in self._aliases.items() if target is key),
            None,
        )

    def get_bindings(self) -> Mapping[type[object], Binding[object]]:
        """Return a read-only snapshot of explicit binding metadata.

        Returns:
            A fresh mapping that cannot mutate the internal registry.
        """
        return dict(self._bindings)

    def scope(self, scope: Scope) -> ContainerScope:
        """Create a task-local execution scope context manager.

        Args:
            scope: Execution lifecycle owned by the returned context manager.

        Returns:
            An inactive context manager that resolves within the scope.
        """
        return ContainerScope(
            self,
            scope,
            self._active_scopes,
            self._scope_callbacks,
        )

    def _scope_entered(self) -> None:
        """Track an active frame so shutdown cannot race its cleanup.

        Scope contexts invoke this callback after setting their execution-local
        context.
        """
        self._active_scope_count += 1

    def _scope_exited(self, generation_count: int) -> None:
        """Release scope and graph counts after resource finalization.

        Args:
            generation_count: Number of scope-owned graphs closed by the frame.

        Scope contexts invoke this callback from a ``finally`` block.
        """
        self._active_scope_count -= 1
        self._scope_generation_count -= generation_count

    def _scope_generation_created(self) -> None:
        """Count a scope-owned graph under the container-wide graph bound.

        Graph construction invokes this callback while holding the shared
        generation lock, so independent tasks cannot exceed the cap.
        """
        self._scope_generation_count += 1

    async def aclose(self) -> None:
        """Finalize graph resources in reverse generation order.

        Raises:
            ScopeError: If an execution scope is still active.

        Notes:
            Later graph generations may borrow cached instances from earlier
            generations, so they close first.
        """
        if self._closed:
            return
        if self._active_scope_count:
            raise ScopeError(_ACTIVE_SCOPE_ERROR)
        self._closed = True
        failures: list[Exception] = []
        for graph in reversed(self._generations):
            try:
                await graph.close()
            except Exception as error:
                failures.append(error)
        if failures:
            details = "; ".join(type(error).__name__ for error in failures)
            message = f"Container resource finalization failed: {details}."
            raise BindingResolutionError(message) from failures[0]

    async def close(self) -> None:
        """Finalize resources through the native async lifecycle contract.

        This method matches the consumer-facing service-container protocols
        and is an alias for ``aclose``.
        """
        await self.aclose()

    def _register[ServiceT](
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT],
        lifetime: Lifetime,
        scope: Scope,
    ) -> None:
        """Replace a registration before the registry becomes immutable.

        Args:
            service: Public dependency key.
            implementation: Class or factory selected for resolution.
            lifetime: Cache behavior applied to the implementation.
            scope: Scope owning a cached value.
        """
        self._ensure_mutable()
        self._dependency_types_by_root.clear()
        self._shared_instances.pop(service, None)
        self._bindings[service] = Binding(
            service=service,
            implementation=implementation,
            lifetime=lifetime,
            scope=scope,
        )

    def _binding_policy(
        self,
        service: type[object],
    ) -> tuple[Lifetime, Scope] | None:
        """Return explicit or class-declared cache metadata.

        Args:
            service: Canonical type whose lifetime is being inspected.

        Returns:
            The cache lifetime and owning scope, if either was declared.

        Notes:
            An explicit container binding overrides class decorator metadata.
        """
        binding = self._bindings.get(service)
        if binding is not None:
            return binding.lifetime, binding.scope
        declaration = binding_declaration(service)
        if declaration is None:
            return None
        return declaration.lifetime, declaration.scope

    def _resolve_key(self, service: type[object] | str) -> type[object]:
        """Normalize a type or string alias to its canonical type key.

        Args:
            service: Requested type or alias.

        Returns:
            Canonical service type.

        Raises:
            BindingError: If a string has no registered target.
        """
        if isinstance(service, str):
            try:
                return self._aliases[service]
            except KeyError as error:
                message = f"No service alias named {service!r} is registered."
                raise BindingError(message) from error
        return service

    async def _generation_for(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
    ) -> _Generation:
        """Compose or reuse the graph selected for async resolution.

        Args:
            service: Requested service type.
            frames: Active execution frames.

        Returns:
            The existing or newly composed graph generation.
        """
        return self._generation_for_mode(
            service,
            frames,
            asynchronous=True,
        )

    def _generation_for_sync(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
    ) -> _Generation:
        """Compose one cached backend graph for a newly requested root.

        Args:
            service: Concrete type requested for the first time.
            frames: Active scope frames that can own or reuse this graph.

        Returns:
            The cached graph generation that contains this root.
        """
        return self._generation_for_mode(
            service,
            frames,
            asynchronous=False,
        )

    def _generation_for_mode(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
        *,
        asynchronous: bool,
    ) -> _Generation:
        """Compose one graph for the requested execution mode.

        Args:
            service: Concrete type requested for the first time.
            frames: Active scope frames that can own or reuse this graph.
            asynchronous: Whether the graph must support async factories.

        Returns:
            The cached graph generation containing this root.

        Raises:
            GraphLimitError: If retaining the generation would exceed the cap.
            BindingResolutionError: If backend graph validation fails.
        """
        # The application graph uses Dishka's async container for both public
        # modes so get_sync and get share one backend cache. Scope-local sync
        # graphs are separate because Dishka cannot synchronously enter an
        # async child scope; outer-scope instances are supplied as context.
        with self._generation_lock:
            existing = self._find_generation(
                service,
                frames,
                asynchronous=asynchronous,
            )
            if existing is not None:
                return existing
            self._ensure_open()
            if self._graph_limit_reached():
                raise GraphLimitError(_GRAPH_LIMIT_ERROR)
            self._frozen = True
            generation = self._compose_generation(
                service,
                frames,
                asynchronous=asynchronous,
            )
            self._store_generation(service, frames, generation)
            return generation

    def _find_generation(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
        *,
        asynchronous: bool,
    ) -> _Generation | None:
        """Find the closest reusable generation for one service.

        Args:
            service: Canonical root key.
            frames: Active scope stack.
            asynchronous: Whether an async scope graph is requested.

        Returns:
            The root generation or matching scope generation, if composed.
        """
        if not frames:
            # Application roots always use the async graph adapter, whose
            # public sync resolver shares the same cache with async access.
            return self._generation_by_type.get(service)
        for frame in reversed(frames):
            existing = frame.generation_for(
                service,
                asynchronous=asynchronous,
            )
            if existing is not None:
                return existing
        return None

    def _graph_limit_reached(self) -> bool:
        """Check the bounded number of active and retained graph generations.

        Returns:
            Whether another graph would exceed the configured limit.
        """
        active_graph_count = (
            len(self._generations) + self._scope_generation_count
        )
        return active_graph_count >= self.max_graph_generations

    def _compose_generation(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
        *,
        asynchronous: bool,
    ) -> _Generation:
        """Build a backend graph and assign it a native generation identity.

        Args:
            service: Concrete dependency requested by the caller.
            frames: Active scope frames whose values seed the graph.
            asynchronous: Whether the graph supports asynchronous resources.

        Returns:
            A native generation wrapping the private graph adapter.

        Raises:
            BindingResolutionError: If graph composition or validation fails.
        """
        bindings = tuple(
            self._engine_binding(item) for item in self._bindings.values()
        )
        instances = dict(self._shared_instances)
        for frame in frames:
            instances.update(frame.instance_snapshot())
        scopes = self._instance_scopes(instances)
        request = GraphRequest(
            service=service,
            auto_resolve=service not in self._bindings,
        )
        resolution_scope = (
            frames[-1].scope.value if frames else Scope.APPLICATION.value
        )
        try:
            graph_factory = (
                create_dependency_graph
                if asynchronous or not frames
                else create_sync_dependency_graph
            )
            graph = graph_factory(
                providers=self.providers,
                bindings=bindings,
                request=request,
                resolution_scope=resolution_scope,
                instances=instances,
                instance_scopes=scopes,
            )
        except Exception as error:
            message = f"Unable to compose a graph for {service.__qualname__}."
            raise BindingResolutionError(message) from error
        generation = _Generation(
            self._next_generation_id,
            service,
            graph,
        )
        self._next_generation_id += 1
        return generation

    def _store_generation(
        self,
        service: type[object],
        frames: tuple[ContainerScope, ...],
        generation: _Generation,
    ) -> None:
        """Attach a generation to its application or execution lifecycle.

        Args:
            service: Root key represented by the generation.
            frames: Active scope stack.
            generation: Backend graph that must be closed with its owner.

        Raises:
            BindingResolutionError: If an application graph is not async.
        """
        if frames:
            frames[-1].own_generation(service, generation)
            return
        if not isinstance(generation.graph, DependencyGraph):
            raise BindingResolutionError(_APPLICATION_GRAPH_ERROR)
        self._generations.append(generation.graph)
        self._generation_by_type[service] = generation

    def _instance_scopes(
        self,
        instances: Mapping[type[object], object],
    ) -> dict[type[object], str]:
        """Describe ownership scopes for cached values passed to a new graph.

        Args:
            instances: Application and active-scope values already resolved.

        Returns:
            Backend-neutral scope names for every registered cached value.
        """
        scopes = {
            binding.service: binding.scope.value
            for binding in self._bindings.values()
        }
        for service in instances:
            if service in scopes:
                continue
            declaration = binding_declaration(service)
            if declaration is not None:
                scopes[service] = declaration.scope.value
        return scopes

    @staticmethod
    def _engine_binding(binding: Binding[object]) -> EngineBinding:
        """Translate native binding metadata to the private graph adapter.

        Args:
            binding: Native binding declaration.

        Returns:
            Private adapter metadata without backend implementation types.
        """
        implementation = (
            binding.instance
            if binding.instance_binding
            else binding.implementation
        )
        if implementation is None:
            implementation = binding.service
        return EngineBinding(
            service=binding.service,
            implementation=cast("object", implementation),
            lifetime=binding.lifetime.value,
            scope=binding.scope.value,
            is_instance=binding.instance_binding,
        )

    def _remember(
        self,
        service: type[object],
        instance: object,
        frames: tuple[ContainerScope, ...],
    ) -> None:
        """Track shared identities for subsequent graph generations.

        Args:
            service: Resolved service key.
            instance: Instance returned by the backend.
            frames: Currently active nested scope frames.

        Notes:
            Only values explicitly requested through this API are tracked.
            Backend-owned nested values remain scoped to their graph generation.
        """
        policy = self._binding_policy(service)
        if policy is None or policy[0] is Lifetime.TRANSIENT:
            return
        lifetime, scope = policy
        if lifetime is Lifetime.SINGLETON:
            self._shared_instances[service] = instance
            return
        level = _scope_level(scope)
        for frame in reversed(frames):
            if _scope_level(frame.scope) == level:
                frame.remember_instance(service, instance)
                return

    def _ensure_open(self) -> None:
        """Reject operations after the container starts finalization.

        Raises:
            ContainerClosedError: If this instance is already closed.
        """
        if self._closed:
            raise ContainerClosedError(_CLOSED_CONTAINER_ERROR)

    def _ensure_mutable(self) -> None:
        """Reject registrations after graph composition has started.

        Raises:
            BindingError: If the registry has been frozen.
            ContainerClosedError: If the container is closed.
        """
        self._ensure_open()
        if self._frozen:
            raise BindingError(_FROZEN_BINDINGS_ERROR)


def _scope_level(scope: Scope) -> int:
    """Return the lifecycle depth used to validate nested scope entry.

    Args:
        scope: Native lifecycle scope.

    Returns:
        Zero for application scope and increasing values for execution scopes.
    """
    if scope is Scope.APPLICATION:
        return 0
    if scope in {
        Scope.REQUEST,
        Scope.CONNECTION,
        Scope.JOB,
        Scope.WORKFLOW,
    }:
        return 1
    if scope in {Scope.NODE, Scope.AGENT}:
        return 2
    return 3


def _is_async_callable(callback: Callable[..., object]) -> bool:
    """Identify coroutine and async-generator callables without invoking them.

    Args:
        callback: Function, bound method, or callable instance.

    Returns:
        Whether calling the callback requires an async execution context.
    """
    unwrapped = unwrap(callback)
    if iscoroutinefunction(unwrapped) or isasyncgenfunction(unwrapped):
        return True
    return callable(unwrapped) and (
        iscoroutinefunction(type(unwrapped).__call__)
        or isasyncgenfunction(type(unwrapped).__call__)
    )


def _is_awaitable_hint(annotation: object) -> bool:
    """Check whether a return annotation describes an async result.

    Args:
        annotation: Resolved or deferred callable return annotation.

    Returns:
        Whether its top-level generic origin is awaitable.
    """
    return get_origin(annotation) in {AwaitableABC, CoroutineABC}


__all__ = ["Container", "ContainerScope", "Scope"]
