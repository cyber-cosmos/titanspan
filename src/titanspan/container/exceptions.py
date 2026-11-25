"""Define native errors for dependency registration and resolution.

Callers can handle container failures without importing backend exceptions.
"""


class ContainerError(RuntimeError):
    """Represent an error raised by a Titanspan container operation.

    Subclasses identify registration, state, scope, or service-resolution
    failures. Backend exception details remain available through chaining.
    """


class BindingError(ContainerError):
    """Represent an invalid or conflicting service registration.

    Registration errors are raised before a graph is composed whenever the
    invalid state can be detected without executing application code.
    """


class BindingResolutionError(ContainerError):
    """Represent a dependency graph that cannot resolve a requested service.

    The original backend exception is retained as ``__cause__`` for diagnosis
    without exposing backend exception types through the public API.
    """


class AsyncResolutionRequiredError(BindingResolutionError):
    """Represent a graph that requires asynchronous initialization.

    Callers should use the asynchronous resolution method when a factory,
    resource lifecycle, or callback must be awaited.
    """


class ContainerClosedError(ContainerError):
    """Represent an operation attempted after container shutdown begins.

    Closing is terminal because backend graphs own resources whose lifetime
    cannot safely be restarted after finalization.
    """


class GraphLimitError(ContainerError):
    """Represent a request to exceed the configured graph generation bound.

    Graph generations own backend caches and resources. A finite bound avoids
    retaining an unbounded number of dynamically discovered graphs.
    """


class ScopeError(ContainerError):
    """Represent a lifecycle scope that cannot be entered or resolved.

    Scope errors include inactive inherited contexts and unsupported nesting
    order. Callers should enter scopes from the application container.
    """
