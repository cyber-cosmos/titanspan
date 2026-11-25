"""Adapt the dependency engine to the native container lifecycle.

This module owns all direct dependency-engine imports. The adapter exposes
only asynchronous resolution and scope context managers to its caller.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from inspect import isabstract, signature
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from dishka import AsyncContainer, Provider, Scope, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from titanspan.container._backends.providers import adapt_providers
from titanspan.container.binding import Lifetime
from titanspan.container.decorators import binding_declaration

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Mapping, Sequence


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
class GraphRequest:
    """Describe one requested root and its automatic-discovery policy.

    Attributes:
        service: Native root requested from the composed graph.
        auto_resolve: Whether an unregistered concrete root is added directly.
    """

    service: type[object]
    auto_resolve: bool


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


def create_dependency_graph(
    *,
    providers: Sequence[object],
    bindings: Sequence[EngineBinding],
    request: GraphRequest,
    resolution_scope: str,
    instances: Mapping[type[object], object],
    instance_scopes: Mapping[type[object], str],
) -> DependencyGraph:
    """Compose a validated graph using only supported backend APIs.

    Args:
        providers: Optional provider objects supplied at an interoperability
            boundary.
        bindings: Native Titanspan registrations for this graph generation.
        request: Root type and automatic-discovery policy.
        resolution_scope: Scope where the auto-resolved root is requested.
        instances: Previously resolved shared values to preserve across graph
            generations.
        instance_scopes: Lifecycle names for tracked values.

    Returns:
        A private adapter around a validated asynchronous graph.

    Raises:
        Exception: Backend graph validation errors are preserved as causes by
            the native container boundary.
    """
    provider_values = list(adapt_providers(providers))
    native_provider = Provider(scope=Scope.APP)

    for binding in bindings:
        engine_scope = _scope_for_name(binding.scope)
        if binding.is_instance:
            native_provider.from_context(
                binding.service,
                scope=engine_scope,
                override=True,
            )
            continue

        implementation = cast(
            "type[object] | Callable[..., object]",
            binding.implementation,
        )
        native_provider.provide(
            implementation,
            provides=binding.service,
            scope=engine_scope,
            cache=binding.lifetime != "transient",
            recursive=isinstance(implementation, type),
        )

    explicit_keys = {binding.service for binding in bindings}
    implementation_types = {
        binding.implementation
        for binding in bindings
        if not binding.is_instance and isinstance(binding.implementation, type)
    }
    dependency_roots = [
        root
        for root in (
            request.service if request.auto_resolve else None,
            *(
                cast("type[object]", binding.implementation)
                for binding in bindings
                if not binding.is_instance
                and isinstance(binding.implementation, type)
            ),
        )
        if root is not None
    ]
    known_types: set[type[object]] = set()
    for root in dependency_roots:
        known_types.update(_discover_types(root))
    automatic_types = {
        service
        for service in known_types
        if not isabstract(service)
        and not getattr(service, "_is_protocol", False)
    }
    automatic_types.difference_update(explicit_keys)
    automatic_types.difference_update(implementation_types)

    # Class declarations are translated at graph composition time so their
    # cache policy remains owned by the requesting application container.
    declared_types = {
        service: declaration
        for service in known_types
        if service not in explicit_keys and service not in implementation_types
        if (declaration := binding_declaration(service)) is not None
    }
    automatic_types.difference_update(declared_types)
    for service, declaration in declared_types.items():
        native_provider.provide(
            service,
            scope=_scope_for_name(declaration.scope.value),
            cache=declaration.lifetime is not Lifetime.TRANSIENT,
        )

    providers_for_graph = [*provider_values, native_provider]
    if automatic_types:
        auto_scope = _scope_for_name(resolution_scope)
        auto_provider = Provider(scope=auto_scope)
        auto_provider.provide_all(
            *sorted(
                automatic_types,
                key=lambda value: (
                    value.__module__,
                    value.__qualname__,
                ),
            ),
            scope=auto_scope,
            cache=False,
        )
        providers_for_graph.append(auto_provider)

    cached_provider = Provider(scope=Scope.APP)
    for service in instances:
        if any(
            binding.service is service and binding.is_instance
            for binding in bindings
        ):
            continue
        cached_provider.from_context(
            service,
            scope=_scope_for_name(instance_scopes[service]),
            override=True,
        )
    if instances:
        providers_for_graph.append(cached_provider)

    container = make_async_container(
        *providers_for_graph,
        FastapiProvider(),
        context=dict(instances),
    )
    return DependencyGraph(
        container,
        discover_dependency_types(request.service, bindings),
        instances,
    )


def discover_dependency_types(
    root: type[object],
    bindings: Sequence[EngineBinding],
) -> frozenset[type[object]]:
    """Return the annotated type closure used to coordinate shared creation.

    Args:
        root: Native service type requested by the caller.
        bindings: Explicit service-to-implementation registrations.

    Returns:
        Types in the constructor graph, including registered implementations.

    Notes:
        This inspects annotations only. The dependency engine remains
        responsible for graph validation, service construction, and caching.
    """
    bindings_by_service = {binding.service: binding for binding in bindings}
    pending = [root]
    visited: set[type[object]] = set()
    discovered: set[type[object]] = set()
    while pending:
        service = pending.pop()
        if service in visited:
            continue
        visited.add(service)
        binding = bindings_by_service.get(service)
        if binding is not None and binding.is_instance:
            discovered.add(service)
            continue
        implementation = (
            binding.implementation if binding is not None else service
        )
        dependencies: set[type[object]]
        if isinstance(implementation, type):
            dependencies = _discover_types(implementation)
        elif callable(implementation):
            dependencies = _discover_factory_types(implementation)
        else:
            dependencies = set()
        discovered.update(dependencies)
        pending.extend(
            dependency
            for dependency in dependencies
            if dependency in bindings_by_service
        )
    return frozenset(discovered)


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
    candidate = origin if isinstance(origin, type) else annotation
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
