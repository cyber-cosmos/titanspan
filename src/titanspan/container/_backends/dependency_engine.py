"""Adapt the dependency engine to the native container lifecycle.

This module owns all direct dependency-engine imports. The adapter exposes
typed sync and async resolution plus scope context managers to its caller.
"""

from __future__ import annotations

from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Coroutine,
    Hashable,
)
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
    contextmanager,
)
from dataclasses import dataclass
from inspect import (
    Parameter,
    Signature,
    isabstract,
    isasyncgenfunction,
    iscoroutinefunction,
    signature,
    unwrap,
)
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Protocol,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    make_async_container,
    make_container,
)
from dishka import (
    Container as SyncContainer,
)
from dishka.integrations.fastapi import FastapiProvider

from titanspan.container._backends.providers import adapt_providers
from titanspan.container._internal.injection import (
    read_config_value,
    select_dependency_source,
    split_annotation,
)
from titanspan.container.binding import BindingDeclaration, Lifetime
from titanspan.container.contextual_binding import (
    ContextualBinding,
    ContextualKind,
)
from titanspan.container.decorators import binding_declaration
from titanspan.container.exceptions import BindingError
from titanspan.contracts.config import ConfigReader

_SCALAR_DEFAULT_TYPES: tuple[object, ...] = (
    str,
    int,
    float,
    bool,
    bytes,
)
_SCALAR_TYPES: frozenset[type[object]] = frozenset(
    {str, int, float, bool, bytes, object, type(None)},
)

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Generator,
        Mapping,
        Sequence,
    )


class EngineBinding:
    """Describe a native binding when composing an engine graph.

    Attributes:
        service: The type used as the dependency key.
        implementation: A class or factory used to create the service.
        lifetime: The native caching policy for this binding.
        scope: The native lifecycle scope for cached instances.
        is_instance: Whether the implementation is an external instance.
    """

    def __init__(
        self,
        service: type[object],
        implementation: type[object] | Callable[..., object] | object,
        lifetime: str,
        scope: str,
        *,
        is_instance: bool = False,
    ) -> None:
        """Store a binding without exposing engine types to callers.

        Args:
            service: Native dependency key.
            implementation: Factory, class, or existing instance.
            lifetime: One of ``transient``, ``singleton`` or ``scoped``.
            scope: Native scope name used to select the engine lifecycle.
            is_instance: Mark a value whose lifecycle is externally owned.
        """
        self.service = service
        self.implementation = implementation
        self.lifetime = lifetime
        self.scope = scope
        self.is_instance = is_instance


@dataclass(frozen=True, slots=True)
class AsyncInspectionContext:
    """Hold optional registrations used while inspecting async graph paths.

    Attributes:
        contextual_bindings: Consumer-specific dependency source rules.
        aliases: String names mapped to canonical service keys.
        tags: Ordered service groups selected by injection metadata.
        cached_services: Services initialized in an active lifecycle.
    """

    contextual_bindings: Sequence[ContextualBinding] = ()
    aliases: Mapping[str, type[object]] | None = None
    tags: Mapping[str, Sequence[type[object]]] | None = None
    cached_services: frozenset[type[object]] = frozenset()


_EMPTY_ASYNC_INSPECTION_CONTEXT = AsyncInspectionContext()


@dataclass(frozen=True, slots=True)
class GraphRequest:
    """Describe one requested root and its automatic-discovery policy.

    Attributes:
        service: Native root requested from the composed graph.
        auto_resolve: Whether an unregistered concrete root is added directly.
    """

    service: type[object]
    auto_resolve: bool


@dataclass(frozen=True, slots=True)
class _ComposedGraph:
    """Carry backend providers and resolved discovery metadata together.

    Attributes:
        providers: Validated provider objects passed to the backend factory.
        known_types: Discovered classes whose shared values need tracking.
        context: Existing and contextual values supplied to the graph.
    """

    providers: tuple[Provider, ...]
    known_types: frozenset[type[object]]
    context: Mapping[type[object], object]


@dataclass(frozen=True, slots=True)
class GraphConfiguration:
    """Collect native registrations for one backend graph generation.

    Attributes:
        providers: Explicit interoperability providers.
        bindings: Native service registrations.
        request: Root service whose dependencies are composed.
        resolution_scope: Default scope for discovered concrete classes.
        instances: Application and active-scope values supplied as context.
        instance_scopes: Lifecycle owner for each supplied instance.
        contextual_bindings: Consumer-specific source rules.
        extensions: Ordered decorators applied to canonical service keys.
        aliases: Registered names mapped to canonical service keys.
        tags: Ordered service keys grouped by tag.
    """

    providers: Sequence[object]
    bindings: Sequence[EngineBinding]
    request: GraphRequest
    resolution_scope: str
    instances: Mapping[type[object], object]
    instance_scopes: Mapping[type[object], str]
    contextual_bindings: Sequence[ContextualBinding]
    extensions: Mapping[type[object], Sequence[Callable[..., object]]]
    aliases: Mapping[str, type[object]]
    tags: Mapping[str, Sequence[type[object]]]


@dataclass(slots=True)
class _ProviderBuild:
    """Carry mutable composition state while assembling one backend graph.

    Attributes:
        configuration: Immutable request and native binding description.
        provider_values: Adapted interoperability providers in stable order.
        native_provider: Provider containing Titanspan graph factories.
        bindings_by_service: Explicit service definitions by canonical key.
        contextual_by_key: Consumer and dependency rules for constructors.
        known_types: Reachable types discovered from the requested root.
        active_bindings: Explicit bindings reachable from the request.
        explicit_keys: Canonical service keys covered by active bindings.
        automatic_types: Concrete classes supplied without explicit bindings.
        contextual_values: Instance context passed to the backend factory.
        declared_types: Reachable classes with declarative lifetime metadata.
        wrapped_automatic: Auto-discovered services with special factories.
    """

    configuration: GraphConfiguration
    provider_values: list[Provider]
    native_provider: Provider
    bindings_by_service: dict[type[object], EngineBinding]
    contextual_by_key: dict[
        tuple[type[object], Hashable],
        ContextualBinding,
    ]
    known_types: set[type[object]]
    active_bindings: tuple[EngineBinding, ...]
    explicit_keys: set[type[object]]
    automatic_types: set[type[object]]
    contextual_values: dict[type[object], object]
    declared_types: dict[type[object], BindingDeclaration]
    wrapped_automatic: set[type[object]]


@dataclass(frozen=True, slots=True)
class _InjectionEnvironment:
    """Bundle dependencies needed to adapt one native injection source.

    Attributes:
        contextual: Consumer-specific rules selected for this graph.
        aliases: Registered names mapped to canonical service types.
        tags: Ordered service keys grouped by tag.
        provider: Provider receiving the generated factories.
        context: Existing and literal instances passed to the backend.
        scope: Lifecycle that owns the injected values.
    """

    contextual: Mapping[
        tuple[type[object], Hashable],
        ContextualBinding,
    ]
    aliases: Mapping[str, type[object]]
    tags: Mapping[str, Sequence[type[object]]]
    provider: Provider
    context: dict[type[object], object]
    scope: Scope


@dataclass(frozen=True, slots=True)
class _SelectedInjection:
    """Describe one constructor argument redirected to a private graph key.

    Attributes:
        service: Constructed class receiving the argument.
        parameter_name: Constructor parameter that receives the value.
        kind: Native source category.
        value: Selected implementation, configuration, alias, tag, or value.
        synthetic: Private service key used by the composed graph.
    """

    service: type[object]
    parameter_name: str
    kind: ContextualKind
    value: object
    synthetic: type[object]
    annotation: object


class _FactoryMetadata(Protocol):
    """Describe metadata assigned to factories inspected by the backend.

    The protocol avoids dynamic attribute assignment on callable objects.
    """

    __signature__: Signature
    __annotations__: dict[str, object]


class DependencyGraph:
    """Resolve services through one composed backend graph.

    The adapter keeps the backend container private while preserving its
    validated graph and deterministic resource finalization behavior.
    """

    def __init__(
        self,
        container: AsyncContainer,
        known_types: frozenset[type[object]],
        context: Mapping[type[object], object],
    ) -> None:
        """Wrap an initialized dependency graph.

        Args:
            container: Backend graph created by the supported public API.
            known_types: Constructor types inspected for this graph.
            context: Existing application or execution-scope instances.
        """
        self._container = container
        self.known_types = known_types
        self._context = dict(context)

    async def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve one service and preserve its caller-visible type.

        Args:
            service: Native type used as the dependency key.

        Returns:
            The resolved service instance.
        """
        return await self._container.get(service)

    def get_sync[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a synchronous dependency using the shared backend cache.

        Args:
            service: Native type used as the dependency key.

        Returns:
            The resolved service instance.

        Raises:
            Exception: If the dependency graph requires an async factory.
        """
        return self._container.get_sync(service)

    @asynccontextmanager
    async def scope(self, name: str) -> AsyncGenerator[DependencyGraph, None]:
        """Enter one backend scope and finalize it when the context exits.

        Args:
            name: Supported native scope name.

        Yields:
            A graph view that resolves within the entered scope.

        Raises:
            ValueError: If the requested scope has no backend equivalent.
        """
        scope = _scope_for_name(name)
        async with self._container(
            scope=scope,
            context=dict(self._context),
        ) as scoped_container:
            yield DependencyGraph(
                scoped_container,
                self.known_types,
                self._context,
            )

    async def close(self) -> None:
        """Finalize all resources owned by this graph.

        The operation delegates cleanup and failure propagation to the
        backend container.
        """
        await self._container.close()


class SyncDependencyGraph:
    """Resolve a synchronous scope through the private graph boundary.

    The application container remains the canonical owner of shared values;
    those instances are passed into synchronous scopes as backend context.
    """

    def __init__(
        self,
        container: SyncContainer,
        known_types: frozenset[type[object]],
        context: Mapping[type[object], object],
    ) -> None:
        """Wrap a backend graph with synchronous ownership semantics.

        Args:
            container: Backend graph created by its public factory.
            known_types: Constructor types inspected for this graph.
            context: Application or parent-scope instances supplied as context.
        """
        self._container = container
        self.known_types = known_types
        self._context = dict(context)

    def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve one service without creating or blocking an event loop.

        Args:
            service: Native type used as the dependency key.

        Returns:
            The resolved service instance.
        """
        return self._container.get(service)

    @contextmanager
    def scope(self, name: str) -> Generator[SyncDependencyGraph, None, None]:
        """Enter and deterministically close one synchronous backend scope.

        Args:
            name: Supported native lifecycle scope.

        Yields:
            A graph view that resolves within the entered scope.
        """
        with self._container(
            scope=_scope_for_name(name),
            context=dict(self._context),
        ) as scoped_container:
            yield SyncDependencyGraph(
                scoped_container,
                self.known_types,
                self._context,
            )

    def close(self) -> None:
        """Finalize all resources owned by this synchronous graph.

        The backend closes its entered child scopes in reverse order.
        """
        self._container.close()


def create_dependency_graph(
    configuration: GraphConfiguration,
) -> DependencyGraph:
    """Compose a validated graph using only supported backend APIs.

    Args:
        configuration: Native registrations and lifecycle values required for
            this graph generation.

    Returns:
        A private adapter around a validated asynchronous graph.

    Raises:
        Exception: Backend graph validation errors are preserved as causes by
            the native container boundary.
    """
    composition = _compose_providers(configuration)

    container = make_async_container(
        *composition.providers,
        context=dict(composition.context),
    )
    return DependencyGraph(
        container,
        composition.known_types,
        composition.context,
    )


def create_sync_dependency_graph(
    configuration: GraphConfiguration,
) -> SyncDependencyGraph:
    """Compose a backend graph for synchronous scope entry and cleanup.

    Args:
        configuration: Native registrations and lifecycle values required for
            this graph generation.

    Returns:
        A private synchronous graph adapter.
    """
    composition = _compose_providers(configuration)
    container = make_container(
        *composition.providers,
        context=dict(composition.context),
    )
    return SyncDependencyGraph(
        container,
        composition.known_types,
        composition.context,
    )


def _compose_providers(
    configuration: GraphConfiguration,
) -> _ComposedGraph:
    """Build backend providers from the canonical graph description.

    Args:
        configuration: Canonical service registrations and lifecycle data.

    Returns:
        Backend providers, tracked types, and graph context for both modes.
    """
    state = _provider_build(configuration)
    _register_explicit_bindings(state)
    _register_automatic_injections(state)
    state.automatic_types.difference_update(state.declared_types)
    state.automatic_types.difference_update(state.wrapped_automatic)
    for service, declaration in state.declared_types.items():
        state.native_provider.provide(
            service,
            scope=_scope_for_name(declaration.scope.value),
            cache=declaration.lifetime is not Lifetime.TRANSIENT,
        )

    providers_for_graph = [*state.provider_values, state.native_provider]
    _append_automatic_provider(state, providers_for_graph)
    _register_extensions(
        configuration.extensions,
        state.known_types,
        state.bindings_by_service,
        state.native_provider,
        configuration.resolution_scope,
    )
    _append_instance_provider(state, providers_for_graph)
    providers_for_graph.append(FastapiProvider())
    return _ComposedGraph(
        providers=tuple(providers_for_graph),
        known_types=frozenset(state.known_types),
        context=state.contextual_values,
    )


def _provider_build(configuration: GraphConfiguration) -> _ProviderBuild:
    """Discover the reachable services and initialize graph composition.

    Args:
        configuration: Root request and immutable native registration data.

    Returns:
        Mutable build state used by the focused provider registration helpers.
    """
    bindings_by_service = {
        binding.service: binding for binding in configuration.bindings
    }
    contextual_by_key = {
        (consumer, binding.dependency): binding
        for binding in configuration.contextual_bindings
        for consumer in binding.consumers
    }
    consumers_by_implementation = _implementation_consumers(
        configuration.bindings,
    )
    known_types = _discover_graph_types(
        configuration.request.service,
        bindings_by_service,
        consumers_by_implementation,
        contextual_by_key,
        configuration.aliases,
        configuration.tags,
    )
    active_bindings = tuple(
        binding
        for binding in configuration.bindings
        if binding.service in known_types
    )
    explicit_keys = {binding.service for binding in active_bindings}
    automatic_types = {
        service
        for service in known_types
        if not isabstract(service)
        and not getattr(service, "_is_protocol", False)
    }
    automatic_types.difference_update(explicit_keys)
    return _ProviderBuild(
        configuration=configuration,
        provider_values=list(adapt_providers(configuration.providers)),
        native_provider=Provider(scope=Scope.APP),
        bindings_by_service=bindings_by_service,
        contextual_by_key=contextual_by_key,
        known_types=known_types,
        active_bindings=active_bindings,
        explicit_keys=explicit_keys,
        automatic_types=automatic_types,
        contextual_values=dict(configuration.instances),
        declared_types={},
        wrapped_automatic=set(),
    )


def _implementation_consumers(
    bindings: Sequence[EngineBinding],
) -> dict[type[object], list[type[object]]]:
    """Index explicit service consumers by their selected implementation.

    Args:
        bindings: Native registrations included in graph composition.

    Returns:
        Ordered contract keys associated with each concrete implementation.
    """
    consumers: dict[type[object], list[type[object]]] = {}
    for binding in bindings:
        implementation = binding.implementation
        if binding.is_instance or not isinstance(implementation, type):
            continue
        consumers.setdefault(implementation, []).append(binding.service)
    return consumers


def _register_explicit_bindings(state: _ProviderBuild) -> None:
    """Register reachable explicit factories and externally owned values.

    Args:
        state: Graph composition state with the active root closure.
    """
    for binding in state.active_bindings:
        scope = _scope_for_name(binding.scope)
        if binding.is_instance:
            state.native_provider.from_context(
                binding.service,
                scope=scope,
                override=True,
            )
            continue
        implementation = cast(
            "type[object] | Callable[..., object]",
            binding.implementation,
        )
        if isinstance(implementation, type):
            environment = _injection_environment(state, scope)
            injected = _constructor_injections(
                implementation,
                (binding.service, implementation),
                environment,
            )
            if injected is not None:
                factory, injected_types = injected
                state.known_types.update(injected_types)
                state.native_provider.provide(
                    factory,
                    provides=binding.service,
                    scope=scope,
                    cache=binding.lifetime != Lifetime.TRANSIENT.value,
                    recursive=False,
                )
                continue
        state.native_provider.provide(
            implementation,
            provides=binding.service,
            scope=scope,
            cache=binding.lifetime != Lifetime.TRANSIENT.value,
            # Titanspan registers this discovered closure explicitly. Backend
            # recursion would preempt consumer-specific and context providers.
            recursive=False,
        )


def _register_automatic_injections(state: _ProviderBuild) -> None:
    """Register decorators and metadata for unbound reachable classes.

    Args:
        state: Graph composition state mutated with native factories.
    """
    for service in state.known_types - state.explicit_keys:
        declaration = binding_declaration(service)
        if declaration is not None:
            state.declared_types[service] = declaration
        scope_name = (
            declaration.scope.value
            if declaration is not None
            else state.configuration.resolution_scope
        )
        scope = _scope_for_name(scope_name)
        environment = _injection_environment(state, scope)
        injected = _constructor_injections(
            service,
            (service,),
            environment,
        )
        if injected is None:
            continue
        factory, injected_types = injected
        state.known_types.update(injected_types)
        state.native_provider.provide(
            factory,
            provides=service,
            scope=scope,
            cache=(
                declaration.lifetime is not Lifetime.TRANSIENT
                if declaration is not None
                else False
            ),
            recursive=False,
        )
        state.wrapped_automatic.add(service)


def _injection_environment(
    state: _ProviderBuild,
    scope: Scope,
) -> _InjectionEnvironment:
    """Bind the immutable injection metadata to one lifecycle scope.

    Args:
        state: Graph metadata and provider used during registration.
        scope: Scope that owns the selected constructor values.

    Returns:
        The backend-neutral context required by injection adaptation.
    """
    configuration = state.configuration
    return _InjectionEnvironment(
        contextual=state.contextual_by_key,
        aliases=configuration.aliases,
        tags=configuration.tags,
        provider=state.native_provider,
        context=state.contextual_values,
        scope=scope,
    )


def _append_automatic_provider(
    state: _ProviderBuild,
    providers: list[Provider],
) -> None:
    """Register concrete discovered classes not covered by explicit factories.

    Args:
        state: Current build state after injection registration.
        providers: Provider list being assembled for the backend.
    """
    if not state.automatic_types:
        return
    scope = _scope_for_name(state.configuration.resolution_scope)
    provider = Provider(scope=scope)
    provider.provide_all(
        *sorted(
            state.automatic_types,
            key=lambda value: (value.__module__, value.__qualname__),
        ),
        scope=scope,
        cache=False,
    )
    providers.append(provider)


def _append_instance_provider(
    state: _ProviderBuild,
    providers: list[Provider],
) -> None:
    """Register inherited and pre-existing values at their owning scopes.

    Args:
        state: Graph context containing instance ownership metadata.
        providers: Provider list being assembled for the backend.
    """
    configuration = state.configuration
    instance_bindings = {
        binding.service
        for binding in configuration.bindings
        if binding.is_instance
    }
    provider = Provider(scope=Scope.APP)
    for service in configuration.instances:
        if service in instance_bindings:
            continue
        provider.from_context(
            service,
            scope=_scope_for_name(configuration.instance_scopes[service]),
            override=True,
        )
    if configuration.instances:
        providers.append(provider)


def _register_extensions(
    extensions: Mapping[type[object], Sequence[Callable[..., object]]],
    known_types: set[type[object]],
    bindings: Mapping[type[object], EngineBinding],
    provider: Provider,
    resolution_scope: str,
) -> None:
    """Add selected service decorators to the native graph provider.

    Args:
        extensions: Ordered decorators grouped by canonical service key.
        known_types: Reachable services in this graph.
        bindings: Explicit native registrations indexed by service key.
        provider: Dependency provider that owns the service factories.
        resolution_scope: Default lifetime for auto-discovered services.

    Notes:
        The backend caches the final decorated value at the service lifetime.
        Extensions that wrap closeable objects must forward cleanup ownership.
    """
    for service, decorators in extensions.items():
        if service not in known_types:
            continue
        binding = bindings.get(service)
        declaration = binding_declaration(service)
        scope_name = binding.scope if binding is not None else None
        if declaration is not None and scope_name is None:
            scope_name = declaration.scope.value
        scope = _scope_for_name(
            scope_name if scope_name is not None else resolution_scope
        )
        for decorator in decorators:
            provider.decorate(decorator, provides=service, scope=scope)


def _discover_graph_types(
    root: type[object],
    bindings: Mapping[type[object], EngineBinding],
    consumers_by_implementation: Mapping[type[object], Sequence[type[object]]],
    contextual: Mapping[
        tuple[type[object], Hashable],
        ContextualBinding,
    ],
    aliases: Mapping[str, type[object]],
    tags: Mapping[str, Sequence[type[object]]],
) -> set[type[object]]:
    """Discover only dependencies reachable from one requested service.

    Args:
        root: The service requested by the caller.
        bindings: Explicit service registrations indexed by service key.
        consumers_by_implementation: Contract keys using each implementation.
        contextual: Consumer-specific dependency source rules.
        aliases: Registered names mapped to service keys.
        tags: Ordered services available under each tag name.

    Returns:
        Reachable constructor types, including explicitly selected targets.
    """
    known_types: set[type[object]] = set()
    pending = [root]
    while pending:
        service = pending.pop()
        if service in known_types:
            continue
        known_types.add(service)
        binding = bindings.get(service)
        if binding is not None and binding.is_instance:
            continue
        implementation = (
            binding.implementation if binding is not None else service
        )
        if isinstance(implementation, type):
            target = implementation
            pending.extend(_discover_types(target))
            consumers = (
                service,
                target,
                *consumers_by_implementation.get(target, ()),
            )
        elif callable(implementation):
            pending.extend(_discover_factory_types(implementation))
            continue
        else:
            continue
        for name, annotation, _ in _constructor_parameters(target):
            source = select_dependency_source(
                consumers,
                name,
                annotation,
                contextual,
            )
            if source is not None:
                pending.extend(
                    _selected_dependency_types(source, aliases, tags),
                )
    return known_types


def _selected_dependency_types(
    source: tuple[ContextualKind, object],
    aliases: Mapping[str, type[object]],
    tags: Mapping[str, Sequence[type[object]]],
) -> tuple[type[object], ...]:
    """Return graph types required by one contextual source declaration.

    Args:
        source: Source category and selected value.
        aliases: Registered aliases available to injection metadata.
        tags: Ordered service groups available to injection metadata.

    Returns:
        Concrete service classes that must be included in graph discovery.
    """
    kind, value = source
    if kind is ContextualKind.IMPLEMENTATION:
        if isinstance(value, type):
            return (cast("type[object]", value),)
        if callable(value):
            return tuple(_discover_factory_types(value))
    elif kind is ContextualKind.CONFIG:
        return (ConfigReader,)
    elif kind is ContextualKind.NAMED:
        target = aliases.get(cast("str", value))
        return () if target is None else (target,)
    elif kind is ContextualKind.TAGGED:
        return tuple(tags.get(cast("str", value), ()))
    return ()


def discover_dependency_types(
    root: type[object],
    bindings: Sequence[EngineBinding],
    contextual_bindings: Sequence[ContextualBinding] = (),
    aliases: Mapping[str, type[object]] | None = None,
    tags: Mapping[str, Sequence[type[object]]] | None = None,
) -> frozenset[type[object]]:
    """Return the reachable type closure used for shared initialization.

    Args:
        root: Native service type requested by the caller.
        bindings: Explicit service-to-implementation registrations.
        contextual_bindings: Consumer-specific dependency source rules.
        aliases: Registered names mapped to service types.
        tags: Ordered service groups used by injection sources.

    Returns:
        Types in the constructor graph, including registered implementations.

    Notes:
        This inspects annotations only. The dependency engine remains
        responsible for graph validation, service construction, and caching.
    """
    bindings_by_service = {binding.service: binding for binding in bindings}
    contextual_by_key = {
        (consumer, binding.dependency): binding
        for binding in contextual_bindings
        for consumer in binding.consumers
    }
    discovered = _discover_graph_types(
        root,
        bindings_by_service,
        _implementation_consumers(bindings),
        contextual_by_key,
        {} if aliases is None else aliases,
        {} if tags is None else tags,
    )
    root_binding = bindings_by_service.get(root)
    if root_binding is not None and root_binding.is_instance:
        return frozenset(discovered)
    discovered.discard(root)
    return frozenset(discovered)


def asynchronous_dependency_path(
    root: type[object],
    bindings: Sequence[EngineBinding],
    extensions: Mapping[type[object], Sequence[Callable[..., object]]],
    context: AsyncInspectionContext = _EMPTY_ASYNC_INSPECTION_CONTEXT,
) -> tuple[str, ...] | None:
    """Find the first dependency path that requires asynchronous creation.

    Args:
        root: Service requested by synchronous resolution.
        bindings: Native service-to-implementation registrations.
        extensions: Service decorators that may require asynchronous work.
        context: Optional registrations and initialized cache identities.

    Returns:
        A readable service path ending at an async factory, or ``None`` when
        all inspectable factories are synchronous.
    """
    inspector = _AsyncDependencyInspector(
        bindings,
        extensions,
        context,
    )
    return inspector.find_path(root)


class _AsyncDependencyInspector:
    """Inspect native graph metadata for async-only dependency paths.

    This preflight mirrors the source-selection rules used during backend
    composition without constructing application services.
    """

    def __init__(
        self,
        bindings: Sequence[EngineBinding],
        extensions: Mapping[type[object], Sequence[Callable[..., object]]],
        context: AsyncInspectionContext,
    ) -> None:
        """Index graph metadata for deterministic path traversal.

        Args:
            bindings: Native registrations included in graph composition.
            extensions: Service decorators that may require async execution.
            context: Optional registrations and initialized cache identities.
        """
        self.bindings = {binding.service: binding for binding in bindings}
        self.extensions = extensions
        self.contextual = {
            (consumer, binding.dependency): binding
            for binding in context.contextual_bindings
            for consumer in binding.consumers
        }
        self.consumers = _implementation_consumers(bindings)
        self.aliases: Mapping[str, type[object]] = (
            {} if context.aliases is None else context.aliases
        )
        self.tags: Mapping[str, Sequence[type[object]]] = (
            {} if context.tags is None else context.tags
        )
        self.cached_services = context.cached_services

    def find_path(
        self,
        root: type[object],
    ) -> tuple[str, ...] | None:
        """Return the first async path reachable from a service root.

        Args:
            root: Service requested by synchronous resolution.

        Returns:
            A readable path to async work, or ``None`` if the graph is
            inspectably synchronous.
        """
        return self._visit(root, (), frozenset())

    def _visit(
        self,
        service: type[object],
        path: tuple[str, ...],
        visited: frozenset[type[object]],
    ) -> tuple[str, ...] | None:
        """Inspect one service and its selected dependency branches.

        Args:
            service: Service key currently being inspected.
            path: Human-readable dependency chain accumulated so far.
            visited: Services already visited on this branch.

        Returns:
            The first async path found, or ``None`` when this branch is safe.
        """
        if service in visited or service in self.cached_services:
            return None
        binding = self.bindings.get(service)
        if binding is not None and binding.is_instance:
            return None
        implementation = (
            binding.implementation if binding is not None else service
        )
        current_path = (*path, service.__qualname__)
        if _has_async_extension(service, self.extensions):
            return (*current_path, "async service extension")
        branch = visited | {service}
        if not isinstance(implementation, type):
            return self._visit_factory(implementation, current_path, branch)
        return self._visit_class(
            service,
            implementation,
            current_path,
            branch,
        )

    def _visit_class(
        self,
        service: type[object],
        implementation: type[object],
        path: tuple[str, ...],
        visited: frozenset[type[object]],
    ) -> tuple[str, ...] | None:
        """Inspect constructor parameters using composed source precedence.

        Args:
            service: Contract key requested by the dependency graph.
            implementation: Concrete constructor currently selected.
            path: Human-readable path ending at this implementation.
            visited: Services already visited on this branch.

        Returns:
            The first async dependency path, or ``None`` when safe.
        """
        consumers = (
            service,
            implementation,
            *self.consumers.get(implementation, ()),
        )
        for name, annotation, _parameter in _constructor_parameters(
            implementation,
        ):
            result = self._visit_parameter(
                consumers,
                name,
                annotation,
                path,
                visited,
            )
            if result is not None:
                return result
        return None

    def _visit_parameter(
        self,
        consumers: Sequence[type[object]],
        name: str,
        annotation: object,
        path: tuple[str, ...],
        visited: frozenset[type[object]],
    ) -> tuple[str, ...] | None:
        """Resolve one parameter's selected source without constructing it.

        Args:
            consumers: Contract and implementation identities for the owner.
            name: Constructor parameter name.
            annotation: Resolved Python annotation and optional metadata.
            path: Human-readable path ending at the owning service.
            visited: Services already visited on this branch.

        Returns:
            The first async dependency path, or ``None`` when safe.
        """
        source = select_dependency_source(
            consumers,
            name,
            annotation,
            self.contextual,
        )
        if source is None:
            dependencies = _class_annotations(annotation) - _SCALAR_TYPES
            return self._visit_dependencies(dependencies, path, visited)
        if (
            source[0] is ContextualKind.IMPLEMENTATION
            and callable(source[1])
            and not isinstance(source[1], type)
        ):
            return self._visit_factory(
                source[1],
                (*path, name),
                visited,
            )
        dependencies = _selected_dependency_types(
            source,
            self.aliases,
            self.tags,
        )
        return self._visit_dependencies(dependencies, path, visited)

    def _visit_dependencies(
        self,
        dependencies: Sequence[type[object]] | set[type[object]],
        path: tuple[str, ...],
        visited: frozenset[type[object]],
    ) -> tuple[str, ...] | None:
        """Visit selected service types in a deterministic order.

        Args:
            dependencies: Service keys referenced by one constructor value.
            path: Human-readable dependency chain accumulated so far.
            visited: Services already visited on this branch.

        Returns:
            The first async dependency path, or ``None`` when safe.
        """
        ordered = sorted(
            dependencies,
            key=lambda value: (value.__module__, value.__qualname__),
        )
        for dependency in ordered:
            if isabstract(dependency) and dependency not in self.bindings:
                continue
            result = self._visit(dependency, path, visited)
            if result is not None:
                return result
        return None

    def _visit_factory(
        self,
        factory: object,
        path: tuple[str, ...],
        visited: frozenset[type[object]],
    ) -> tuple[str, ...] | None:
        """Inspect a selected factory and its annotated dependencies.

        Args:
            factory: Callable selected by a binding or injection rule.
            path: Human-readable service path leading to this factory.
            visited: Services already visited on this branch.

        Returns:
            The path to async work, or ``None`` for sync-safe factories.
        """
        if not callable(factory):
            return None
        dependencies, async_factory = _implementation_dependencies(factory)
        if async_factory is not None:
            return (*path, async_factory)
        name = getattr(factory, "__qualname__", None)
        factory_name = name if isinstance(name, str) else "factory"
        return self._visit_dependencies(
            dependencies,
            (*path, factory_name),
            visited,
        )


def _implementation_dependencies(
    implementation: object,
) -> tuple[set[type[object]], str | None]:
    """Inspect one binding implementation for dependencies and async work.

    Args:
        implementation: Concrete class, factory, or explicitly supplied value.

    Returns:
        Discovered constructor dependencies and an async factory marker.
    """
    if isinstance(implementation, type):
        return _direct_constructor_types(implementation), None
    if not callable(implementation):
        return set(), None
    if _is_async_factory(implementation):
        factory_name = getattr(
            implementation,
            "__qualname__",
            type(implementation).__qualname__,
        )
        return set(), f"async factory {factory_name}"
    return _discover_factory_types(implementation), None


def _has_async_extension(
    service: type[object],
    extensions: Mapping[type[object], Sequence[Callable[..., object]]],
) -> bool:
    """Identify whether a service decorator makes its path async-only.

    Args:
        service: Current service key in dependency traversal.
        path: Readable dependency path accumulated so far.
        extensions: Registered extension factories by service key.

    Returns:
        Whether a registered extension requires asynchronous execution.
    """
    return any(
        _is_async_factory(extension)
        for extension in extensions.get(service, ())
    )


def _direct_constructor_types(service: type[object]) -> set[type[object]]:
    """Return immediate class dependencies declared by one constructor.

    Args:
        service: Class whose constructor signature is inspected.

    Returns:
        Directly annotated dependency types, excluding the instance parameter.
    """
    try:
        parameters = signature(service).parameters
        annotations = get_type_hints(
            service.__init__,
            include_extras=True,
        )
    except (AttributeError, NameError, TypeError, ValueError):
        return set()
    dependencies: set[type[object]] = set()
    scalar_types = {str, int, float, bool, bytes, object}
    for name, parameter in parameters.items():
        if name in {"self", "cls"}:
            continue
        annotation = annotations.get(name, parameter.annotation)
        dependencies.update(_class_annotations(annotation) - scalar_types)
    return dependencies


def _is_async_factory(factory: Callable[..., object]) -> bool:
    """Detect async factories without invoking them.

    Args:
        factory: Registered factory or callable object.

    Returns:
        Whether the factory call or annotated result requires awaiting.
    """
    unwrapped = unwrap(factory)
    if iscoroutinefunction(unwrapped) or isasyncgenfunction(unwrapped):
        return True
    if callable(unwrapped) and (
        iscoroutinefunction(type(unwrapped).__call__)
        or isasyncgenfunction(type(unwrapped).__call__)
    ):
        return True
    try:
        annotation = get_type_hints(factory, include_extras=True).get(
            "return",
        )
    except (NameError, TypeError, ValueError):
        return False
    origin = get_origin(annotation)
    return origin in {
        AbstractAsyncContextManager,
        AsyncGenerator,
        AsyncIterator,
        Awaitable,
        Coroutine,
    }


def _discover_types(root: type[object]) -> set[type[object]]:
    """Inspect constructor annotations for a concrete dependency closure.

    Args:
        root: Concrete class whose graph is being composed.

    Returns:
        Concrete annotated classes that can be registered with the backend.

    Notes:
        This phase only discovers type declarations. Object construction,
        dependency validation, caching, and resource cleanup remain delegated.
    """
    pending = [root]
    known_types: set[type[object]] = set()
    inspected: set[type[object]] = set()
    scalar_types = {str, int, float, bool, bytes, object}
    while pending:
        current = pending.pop()
        if current in inspected:
            continue
        inspected.add(current)
        known_types.add(current)
        try:
            constructor = current.__init__
            parameters = signature(current).parameters
            annotations = get_type_hints(
                constructor,
                include_extras=True,
            )
        except (AttributeError, NameError, TypeError, ValueError):
            continue
        for name, parameter in parameters.items():
            annotation = annotations.get(name, parameter.annotation)
            for dependency in _class_annotations(annotation):
                if dependency in scalar_types:
                    continue
                known_types.add(dependency)
                if not isabstract(dependency) and not getattr(
                    dependency,
                    "_is_protocol",
                    False,
                ):
                    pending.append(dependency)
    return known_types


def _discover_factory_types(
    factory: Callable[..., object],
) -> set[type[object]]:
    """Inspect a factory's annotated inputs without executing the factory.

    Args:
        factory: Synchronous or asynchronous factory function.

    Returns:
        Class-valued parameter dependencies declared by the factory.
    """
    try:
        parameters = signature(factory).parameters
        annotations = get_type_hints(factory, include_extras=True)
    except (NameError, TypeError, ValueError):
        return set()
    dependencies: set[type[object]] = set()
    scalar_types = {str, int, float, bool, bytes, object}
    for name, parameter in parameters.items():
        annotation = annotations.get(name, parameter.annotation)
        for dependency in _class_annotations(annotation):
            if dependency not in scalar_types:
                dependencies.add(dependency)
    return dependencies


def _constructor_parameters(
    service: type[object],
) -> tuple[tuple[str, object, Parameter], ...]:
    """Return resolved constructor parameters with ``Annotated`` metadata.

    Args:
        service: Class whose constructor is inspected without instantiation.

    Returns:
        Ordered parameter names, evaluated annotations, and signature items.

    Raises:
        BindingError: If Python cannot resolve the constructor annotations.
    """
    if service.__init__ is object.__init__:
        return ()
    try:
        constructor = service.__init__
        parameters = signature(service).parameters
        annotations = get_type_hints(constructor, include_extras=True)
    except (AttributeError, NameError, TypeError, ValueError) as error:
        message = f"Unable to inspect dependencies for {service.__qualname__}."
        raise BindingError(message) from error
    return tuple(
        (
            name,
            annotations.get(name, parameter.annotation),
            parameter,
        )
        for name, parameter in parameters.items()
        if name not in {"self", "cls"}
        and parameter.kind
        not in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}
    )


def _constructor_injections(
    service: type[object],
    consumers: Sequence[type[object]],
    environment: _InjectionEnvironment,
) -> tuple[Callable[..., object], frozenset[type[object]]] | None:
    """Create a graph-owned factory when native injection is requested.

    Each selected constructor parameter gets a private graph key. This keeps
    consumer-specific values separate while Dishka still constructs the
    service, owns its cache, and finalizes any resources it creates.

    Args:
        service: Concrete class instantiated by the generated factory.
        consumers: Service identity and implementation used for rule matching.
        environment: Rules, context, and provider for this service scope.

    Returns:
        A typed factory and discovered dependency classes, or ``None`` when
        the constructor needs no special injection.

    Raises:
        BindingError: If a declared source does not exist or is ambiguous.
    """
    parameters = _constructor_parameters(service)
    selected: dict[str, tuple[ContextualKind, object, type[object]]] = {}
    synthetic_types: set[type[object]] = set()
    for index, (name, annotation, _) in enumerate(parameters):
        source = select_dependency_source(
            consumers,
            name,
            annotation,
            environment.contextual,
        )
        if source is None:
            continue
        kind, value = source
        synthetic = _synthetic_key(service, name, index)
        selected[name] = (kind, value, synthetic)
        synthetic_types.add(synthetic)
        _provide_selected_source(
            _SelectedInjection(
                service,
                name,
                kind,
                value,
                synthetic,
                split_annotation(annotation)[0],
            ),
            environment,
        )

    if not selected:
        return None

    parameters_by_name = {name: parameter for name, _, parameter in parameters}
    factory_parameters: list[Parameter] = []
    for name, annotation, parameter in parameters:
        selected_source = selected.get(name)
        base_annotation, _metadata = split_annotation(annotation)
        if (
            selected_source is None
            and parameter.default is not Parameter.empty
            and base_annotation in _SCALAR_DEFAULT_TYPES
        ):
            # Preserve optional scalar defaults instead of asking the graph
            # to invent values for ordinary Python constructor parameters.
            continue
        factory_annotation = (
            selected_source[2] if selected_source is not None else annotation
        )
        factory_parameters.append(
            parameter.replace(annotation=factory_annotation)
        )
    factory_signature = Signature(
        factory_parameters,
        return_annotation=service,
    )

    def construct(*args: object, **kwargs: object) -> object:
        """Instantiate the selected class with graph-resolved arguments.

        Args:
            args: Positional values supplied by the backend graph.
            kwargs: Named values supplied by the backend graph.

        Returns:
            The concrete service instance owned by the backend scope.
        """
        bound = factory_signature.bind(*args, **kwargs)
        values = dict(bound.arguments)
        positional: list[object] = []
        named: dict[str, object] = {}
        for parameter_name, parameter in parameters_by_name.items():
            if parameter_name not in values:
                continue
            if parameter.kind is Parameter.POSITIONAL_ONLY:
                positional.append(values[parameter_name])
            else:
                named[parameter_name] = values[parameter_name]
        return service(*positional, **named)

    construct.__name__ = f"build_{service.__name__}"
    _set_factory_metadata(construct, factory_signature, service)
    return construct, frozenset()


def _provide_selected_source(
    selected: _SelectedInjection,
    environment: _InjectionEnvironment,
) -> None:
    """Register one selected source using documented provider operations.

    Args:
        selected: Consumer parameter and its selected native source.
        environment: Backend provider and graph context for this scope.

    Raises:
        BindingError: If a named service or tagged collection is unknown.
    """
    if selected.kind is ContextualKind.VALUE:
        environment.context[selected.synthetic] = selected.value
        environment.provider.from_context(
            selected.synthetic,
            scope=environment.scope,
            override=True,
        )
    elif selected.kind is ContextualKind.CONFIG:
        _provide_config_source(selected, environment)
    elif selected.kind is ContextualKind.NAMED:
        _provide_named_source(selected, environment)
    elif selected.kind is ContextualKind.TAGGED:
        _provide_tagged_source(selected, environment)
    else:
        _provide_implementation_source(selected, environment)


def _provide_config_source(
    selected: _SelectedInjection,
    environment: _InjectionEnvironment,
) -> None:
    """Register a typed factory backed by the canonical configuration key.

    Args:
        selected: Constructor source with a dotted configuration path.
        environment: Graph provider and lifecycle data.
    """
    key = cast("str", selected.value)

    def read_config(repository: ConfigReader) -> object:
        """Read and validate one typed configuration value.

        Args:
            repository: Native configuration reader contract.

        Returns:
            The validated value stored at the selected key.

        Raises:
            BindingError: If the annotation has no typed reader capability.
        """
        return read_config_value(
            repository,
            key,
            selected.annotation,
        )

    environment.provider.provide(
        read_config,
        provides=selected.synthetic,
        scope=environment.scope,
        cache=False,
        recursive=False,
    )


def _provide_named_source(
    selected: _SelectedInjection,
    environment: _InjectionEnvironment,
) -> None:
    """Register one typed forwarding factory for a native alias.

    Args:
        selected: Constructor source with the alias name.
        environment: Graph provider, alias registry, and lifecycle data.

    Raises:
        BindingError: If the alias is not registered.
    """
    name = cast("str", selected.value)
    target = environment.aliases.get(name)
    if target is None:
        message = f"No service alias is registered for {name!r}."
        raise BindingError(message)
    environment.provider.provide(
        _typed_forwarder(target),
        provides=selected.synthetic,
        scope=environment.scope,
        cache=False,
        recursive=False,
    )


def _provide_tagged_source(
    selected: _SelectedInjection,
    environment: _InjectionEnvironment,
) -> None:
    """Register ordered service forwarding factories for one native tag.

    Args:
        selected: Constructor source with the requested tag name.
        environment: Provider, tag registry, and lifecycle data.

    Raises:
        BindingError: If the tag has no registered services.
    """
    name = cast("str", selected.value)
    services = tuple(environment.tags.get(name, ()))
    if not services:
        message = f"No services are registered for tag {name!r}."
        raise BindingError(message)
    entries = tuple(
        _synthetic_key(selected.service, selected.parameter_name, index)
        for index, _ in enumerate(services)
    )
    for entry, target in zip(entries, services, strict=True):
        environment.provider.provide(
            _typed_forwarder(target),
            provides=entry,
            scope=environment.scope,
            cache=False,
            recursive=False,
        )
    environment.provider.provide(
        _tagged_factory(entries),
        provides=selected.synthetic,
        scope=environment.scope,
        cache=False,
        recursive=False,
    )


def _provide_implementation_source(
    selected: _SelectedInjection,
    environment: _InjectionEnvironment,
) -> None:
    """Register a concrete implementation or annotated factory.

    Args:
        selected: Constructor source with an implementation or factory.
        environment: Provider and lifecycle data for the native graph.

    Raises:
        BindingError: If the source is not a class or callable factory.
    """
    implementation = selected.value
    if not isinstance(implementation, type) and not callable(implementation):
        message = (
            f"Injection for {selected.service.__qualname__}."
            f"{selected.parameter_name} must select a class or typed factory."
        )
        raise BindingError(message)
    environment.provider.provide(
        implementation,
        provides=selected.synthetic,
        scope=environment.scope,
        cache=False,
        recursive=False,
    )


def _set_factory_metadata(
    factory: Callable[..., object],
    factory_signature: Signature,
    result_type: object,
) -> None:
    """Attach inspectable parameter types for backend factory discovery.

    Args:
        factory: Generated Python function passed to the backend provider.
        factory_signature: Signature matching the resolved constructor graph.
        result_type: Factory return annotation visible to the graph builder.
    """
    metadata_factory = cast("_FactoryMetadata", factory)
    metadata_factory.__signature__ = factory_signature
    metadata_factory.__annotations__ = {
        **{
            parameter.name: parameter.annotation
            for parameter in factory_signature.parameters.values()
        },
        "return": result_type,
    }


def _typed_forwarder(target: type[object]) -> Callable[..., object]:
    """Build a one-argument factory that resolves a canonical target key.

    Args:
        target: Service type that Dishka resolves through its graph.

    Returns:
        A factory whose parameter annotation references the target key.
    """

    def forward(value: object) -> object:
        """Return the service value resolved for this forwarding key.

        Args:
            value: Existing service resolved by the dependency graph.

        Returns:
            The same service instance without changing ownership.
        """
        return value

    forward.__annotations__ = {"value": target, "return": target}
    return forward


def _tagged_factory(
    entries: Sequence[type[object]],
) -> Callable[..., object]:
    """Build a factory aggregating tagged services in registration order.

    Args:
        entries: Synthetic dependency keys ordered like the registered tag.

    Returns:
        A factory whose result is a new list of the resolved service objects.
    """
    parameters = [
        Parameter(f"entry_{index}", Parameter.KEYWORD_ONLY, annotation=entry)
        for index, entry in enumerate(entries)
    ]
    factory_signature = Signature(parameters, return_annotation=object)

    def collect(**values: object) -> object:
        """Collect resolved entries without changing their resource owners.

        Args:
            values: Backend-resolved values keyed by generated parameter name.

        Returns:
            Entries in their original registration order.
        """
        return [values[f"entry_{index}"] for index in range(len(entries))]

    _set_factory_metadata(collect, factory_signature, object)
    return collect


def _synthetic_key(
    consumer: type[object],
    parameter_name: str,
    index: int,
) -> type[object]:
    """Create an isolated dependency key for one graph parameter.

    Args:
        consumer: Owning consumer class.
        parameter_name: Constructor parameter represented by the key.
        index: Stable position within the inspected constructor.

    Returns:
        A private marker type unique to this composed graph description.
    """
    key_name = (
        f"_Injection_{consumer.__name__}_{parameter_name}_"
        f"{index}_{id(consumer)}"
    )
    return type(key_name, (), {"__module__": __name__})


def _class_annotations(annotation: object) -> set[type[object]]:
    """Extract concrete class arguments from a typing annotation.

    Args:
        annotation: Resolved or deferred constructor annotation.

    Returns:
        Class-valued dependencies nested in the annotation.
    """
    if isinstance(annotation, str):
        return set()
    origin = get_origin(annotation)
    if origin is Annotated:
        arguments = get_args(annotation)
        return _class_annotations(arguments[0]) if arguments else set()
    if origin in {Union, UnionType}:
        dependencies: set[type[object]] = set()
        for argument in get_args(annotation):
            dependencies.update(_class_annotations(argument))
        return dependencies
    if origin is not None:
        dependencies = set()
        for argument in get_args(annotation):
            dependencies.update(_class_annotations(argument))
        return dependencies
    candidate = annotation
    if isinstance(candidate, type):
        return {cast("type[object]", candidate)}
    return set()


def _scope_for_name(name: str) -> Scope:
    """Map stable native scope names onto supported engine scopes.

    Args:
        name: Application, request, workflow, node, or tool scope name.

    Returns:
        The corresponding backend scope.

    Raises:
        ValueError: If the native scope name is unsupported.
    """
    scopes = {
        "application": Scope.APP,
        "request": Scope.REQUEST,
        "connection": Scope.REQUEST,
        "job": Scope.REQUEST,
        "workflow": Scope.REQUEST,
        "node": Scope.ACTION,
        "agent": Scope.ACTION,
        "tool": Scope.STEP,
        "task": Scope.STEP,
    }
    try:
        return scopes[name]
    except KeyError as error:
        message = f"Unsupported lifecycle scope: {name}"
        raise ValueError(message) from error
