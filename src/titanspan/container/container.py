"""Provide the native asynchronous service container.

Titanspan owns registration, aliases, lifetime metadata, and active execution
scope handling. The private dependency adapter composes validated graphs and
finalizes resources.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from contextvars import ContextVar, Token
from dataclasses import dataclass
from inspect import Parameter, Signature, isabstract, isawaitable, signature
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
    create_dependency_graph,
    discover_dependency_types,
)
from titanspan.container.binding import Binding, Lifetime, ServiceFactory
from titanspan.container.decorators import binding_declaration
from titanspan.container.exceptions import (
    BindingError,
    BindingResolutionError,
    ContainerClosedError,
    GraphLimitError,
    ScopeError,
)
from titanspan.container.scope import Scope
from titanspan.contracts import AsyncServiceContainer

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
        graph: Private adapter that owns graph resolution and cleanup.
    """

    def __init__(
        self,
        identifier: int,
        root: type[object],
        graph: DependencyGraph,
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
    """Represent one task-local execution scope.

    Use this object as an asynchronous context manager. It lazily enters the
    matching backend scope for each graph generation used inside its lifetime.
    Concurrent tasks may inherit the active scope context; callers should give
    independently owned work its own scope when it needs isolated instances.
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
        self._graphs: dict[int, DependencyGraph] = {}
        self._generations: dict[type[object], _Generation] = {}
        self._instances: dict[type[object], object] = {}
        self._lock = asyncio.Lock()
        self._active = False
        self._entered = False

    async def __aenter__(self) -> ContainerScope:
        """Activate the scope in the current asynchronous context.

        Returns:
            This scope, which provides resolution methods.

        Raises:
            ContainerClosedError: If the owning container is closed.
            ScopeError: If nested scopes do not advance the scope hierarchy.
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
        self._token = self._scope_context.set(
            (*parents, self),
        )
        self._callbacks.entered()
        return self

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
        self._active = False
        try:
            if self._token is not None:
                self._scope_context.reset(self._token)
        finally:
            try:
                try:
                    await self._exit_stack.__aexit__(
                        exception_type,
                        exception,
                        traceback,
                    )
                except BindingResolutionError:
                    raise
                except Exception as error:
                    raise BindingResolutionError(
                        _SCOPE_FINALIZATION_ERROR
                    ) from error
            finally:
                self._callbacks.exited(len(self._generations))

    async def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
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
        return await self._container.make(service)

    async def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service using the contract's concise method name.

        Args:
            service: Registered or automatically constructible service type.

        Returns:
            The service instance resolved within this scope.
        """
        return await self.make(service)

    @property
    def is_active(self) -> bool:
        """Return whether this frame still owns an open execution scope.

        Returns:
            ``True`` between successful entry and completed cleanup.
        """
        return self._active

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

    def generation_for(self, service: type[object]) -> _Generation | None:
        """Return this frame's graph generation for a service root.

        Args:
            service: Root type previously composed in this frame.

        Returns:
            The frame-owned generation, if present.
        """
        return self._generations.get(service)

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
        self._generations[service] = generation
        self._callbacks.generation_created()
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


class Container(AsyncServiceContainer):
    """Register and resolve application services asynchronously.

    Bindings are mutable until the first graph is requested. Concrete
    unregistered classes are discovered recursively by the private graph
    adapter. Each newly discovered root creates one cached graph generation;
    later resolutions reuse that generation. Existing application instances
    are supplied to later generations so adding a graph does not invalidate
    values previously resolved through this API.

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
        self._generations: list[_Generation] = []
        self._generation_by_type: dict[type[object], _Generation] = {}
        self._next_generation_id = 0
        self._active_scopes: ContextVar[tuple[ContainerScope, ...]] = (
            ContextVar(f"titanspan_container_scopes_{id(self)}", default=())
        )
        self._generation_lock = asyncio.Lock()
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

    async def tagged(self, name: str) -> list[object]:
        """Resolve tagged services in their registration order.

        Args:
            name: Tag previously registered with ``tag``.

        Returns:
            Resolved service values. An unknown tag returns an empty list.
        """
        return [
            await self.make(service) for service in self._tags.get(name, [])
        ]

    def factory[ServiceT](
        self,
        service: type[ServiceT],
    ) -> Callable[[], Awaitable[ServiceT]]:
        """Return a lazy asynchronous resolver for a service type.

        Args:
            service: Service resolved each time the returned callable is used.

        Returns:
            A coroutine factory that delegates to the active container.

        Notes:
            Transient bindings produce fresh values; cached lifetimes keep
            their normal application or execution-scope semantics.
        """

        async def resolve() -> ServiceT:
            """Resolve the configured service when invoked.

            Returns:
                The service value from the active container context.
            """
            return await self.make(service)

        return resolve

    async def call[**P, ReturnT](
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
        arguments, keywords = await self._resolve_call_arguments(
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

    async def _resolve_call_arguments(
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
                value = await self._resolve_call_parameter(
                    name,
                    annotations.get(name, parameter.annotation),
                )
            if parameter.kind is Parameter.POSITIONAL_ONLY:
                positional.append(value)
            else:
                keywords[name] = value
        return positional, keywords

    async def _resolve_call_parameter(
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
            return await self.make(service)
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

    async def call_method_binding(
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
        result: object = await self.call(callback, parameters)
        return result

    @overload
    async def make[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a class-keyed service while preserving its static type.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The resolved instance with its declared service type.
        """

    @overload
    async def make(self, service: str) -> object:
        """Resolve a named service with a dynamic return type.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    async def make(
        self,
        service: type[object] | str,
    ) -> object:
        """Resolve a service through a cached, validated graph generation.

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
        is_cached, cached = self._cached_value(key, frames)
        if is_cached:
            return cached
        async with AsyncExitStack() as lock_stack:
            for lock in self._shared_locks_for(key, frames):
                await lock_stack.enter_async_context(lock)
            if frames:
                await self._prime_application_dependencies(key)
            return await self._resolve_locked(key, frames)

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
            value = await self._resolve_from_graph(dependency, graph)
            self._remember(dependency, value, ())
            await self._remember_shared_dependencies(
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

    @overload
    async def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a class-keyed service through the shared contract.

        Args:
            service: Service key whose class determines the result type.

        Returns:
            The resolved instance with its declared service type.
        """

    @overload
    async def get(self, service: str) -> object:
        """Resolve a named service through the shared contract.

        Args:
            service: Registered alias for a service contract.

        Returns:
            The service instance associated with that alias.
        """

    async def get(self, service: type[object] | str) -> object:
        """Resolve a service using the concise contract method name.

        Args:
            service: Service type or registered string alias.

        Returns:
            The resolved service instance.
        """
        return await self.make(service)

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
        for generation in reversed(self._generations):
            try:
                await generation.graph.close()
            except Exception as error:
                failures.append(error)
        if failures:
            details = "; ".join(type(error).__name__ for error in failures)
            message = f"Container resource finalization failed: {details}."
            raise BindingResolutionError(message) from failures[0]

    async def close(self) -> None:
        """Finalize resources through the shared async container contract.

        This explicit method matches ``AsyncServiceContainer`` and is an alias
        for ``aclose``.
        """
        await self.aclose()

    def bindMethod(  # noqa: N802
        self,
        method: str,
        callback: Callable[..., object],
    ) -> None:
        """Register a method callback with compatibility casing.

        Args:
            method: Application-defined binding key.
            callback: Callable invoked through dependency-aware dispatch.
        """
        self.bind_method(method, callback)

    def hasMethodBinding(self, method: str) -> bool:  # noqa: N802
        """Check a method callback using compatibility casing.

        Args:
            method: Application-defined binding key.

        Returns:
            ``True`` if the key has a registered callback.
        """
        return self.has_method_binding(method)

    async def callMethodBinding(  # noqa: N802
        self,
        method: str,
        parameters: Mapping[str, object] | None = None,
    ) -> object:
        """Invoke a method callback using compatibility casing.

        Args:
            method: Application-defined binding key.
            parameters: Optional explicit parameter values.

        Returns:
            The callback result after dependency resolution.
        """
        return await self.call_method_binding(method, parameters)

    def bindIf[ServiceT](  # noqa: N802
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register only when no binding exists, using compatibility casing.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
        """
        self.bind_if(service, implementation)

    def singletonIf[ServiceT](  # noqa: N802
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
    ) -> None:
        """Register an application singleton only when absent.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
        """
        self.singleton_if(service, implementation)

    def scopedIf[ServiceT](  # noqa: N802
        self,
        service: type[ServiceT],
        implementation: type[ServiceT] | ServiceFactory[ServiceT] | None = None,
        *,
        scope: Scope = Scope.REQUEST,
    ) -> None:
        """Register a scoped service only when absent.

        Args:
            service: Public service contract or concrete service type.
            implementation: Constructible class or typed factory.
            scope: Lifecycle scope that owns the cached instance.
        """
        self.scoped_if(service, implementation, scope=scope)

    def isShared(self, service: type[object] | str) -> bool:  # noqa: N802
        """Return whether a service uses an application or scoped cache.

        Args:
            service: Service type or registered alias.

        Returns:
            ``True`` for singleton and scoped bindings.
        """
        return self.is_shared(service)

    def isAlias(self, name: str) -> bool:  # noqa: N802
        """Check alias registration with compatibility method casing.

        Args:
            name: Name to inspect.

        Returns:
            ``True`` if the name targets a registered service.
        """
        return self.is_alias(name)

    def getAlias(  # noqa: N802
        self,
        service: type[object] | str,
    ) -> str | None:
        """Return a service alias with compatibility method casing.

        Args:
            service: Service type or registered alias.

        Returns:
            The first alias registered for the canonical service.
        """
        return self.get_alias(service)

    def getBindings(  # noqa: N802
        self,
    ) -> Mapping[type[object], Binding[object]]:
        """Return the binding snapshot with compatibility method casing.

        Returns:
            A fresh mapping of explicit binding metadata.
        """
        return self.get_bindings()

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
        """Compose one cached backend graph for a newly requested root.

        Args:
            service: Concrete type requested for the first time.
            frames: Active scope frames that can own or reuse this graph.

        Returns:
            The cached graph generation that contains this root.
        """
        async with self._generation_lock:
            existing = None
            if frames:
                for frame in reversed(frames):
                    existing = frame.generation_for(service)
                    if existing is not None:
                        break
            else:
                existing = self._generation_by_type.get(service)
            if existing is not None:
                return existing
            self._ensure_open()
            active_graph_count = (
                len(self._generations) + self._scope_generation_count
            )
            if active_graph_count >= self.max_graph_generations:
                raise GraphLimitError(_GRAPH_LIMIT_ERROR)
            self._frozen = True
            bindings = tuple(
                self._engine_binding(item) for item in self._bindings.values()
            )
            instances = dict(self._shared_instances)
            for frame in frames:
                instances.update(frame.instance_snapshot())
            scopes = self._instance_scopes(instances)
            auto_resolve = None if service in self._bindings else service
            try:
                graph = create_dependency_graph(
                    providers=self.providers,
                    bindings=bindings,
                    request=GraphRequest(
                        service=service,
                        auto_resolve=auto_resolve is not None,
                    ),
                    resolution_scope=(
                        frames[-1].scope.value
                        if frames
                        else Scope.APPLICATION.value
                    ),
                    instances=instances,
                    instance_scopes=scopes,
                )
            except Exception as error:
                message = (
                    f"Unable to compose a graph for {service.__qualname__}."
                )
                raise BindingResolutionError(message) from error
            generation = _Generation(
                self._next_generation_id,
                service,
                graph,
            )
            self._next_generation_id += 1
            if frames:
                frames[-1].own_generation(service, generation)
            else:
                self._generations.append(generation)
                self._generation_by_type[service] = generation
            return generation

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


__all__ = ["Container", "ContainerScope", "Scope"]
