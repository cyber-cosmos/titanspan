"""Expose Titanspan's native dependency registration and resolution API.

Keep backend graph and provider types behind the private adapter boundary.
"""

from titanspan.container.binding import Binding, Lifetime, ServiceFactory
from titanspan.container.container import Container, ContainerScope
from titanspan.container.decorators import scoped, singleton
from titanspan.container.exceptions import (
    AsyncResolutionRequiredError,
    BindingError,
    BindingResolutionError,
    ContainerClosedError,
    ContainerError,
    GraphLimitError,
    ScopeError,
)
from titanspan.container.scope import Scope

__all__ = [
    "AsyncResolutionRequiredError",
    "Binding",
    "BindingError",
    "BindingResolutionError",
    "Container",
    "ContainerClosedError",
    "ContainerError",
    "ContainerScope",
    "GraphLimitError",
    "Lifetime",
    "Scope",
    "ScopeError",
    "ServiceFactory",
    "scoped",
    "singleton",
]
