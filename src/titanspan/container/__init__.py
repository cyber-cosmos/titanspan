"""Expose Titanspan's native dependency registration and resolution API.

Keep backend graph and provider types behind the private adapter boundary.
"""

from titanspan.container.binding import (
    Binding,
    Lifetime,
    ServiceExtension,
    ServiceFactory,
)
from titanspan.container.callbacks import (
    BeforeResolutionCallback,
    ResolutionCallback,
)
from titanspan.container.container import (
    Container,
    ContainerScope,
)
from titanspan.container.contextual_binding import (
    ContextualBinding,
    ContextualBindingBuilder,
    ContextualKind,
    NeedsBindingBuilder,
)
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
from titanspan.container.injection import FromConfig, Inject, Named, Tagged
from titanspan.container.scope import Scope
from titanspan.contracts import ServiceOverride

__all__ = [
    "AsyncResolutionRequiredError",
    "BeforeResolutionCallback",
    "Binding",
    "BindingError",
    "BindingResolutionError",
    "Container",
    "ContainerClosedError",
    "ContainerError",
    "ContainerScope",
    "ContextualBinding",
    "ContextualBindingBuilder",
    "ContextualKind",
    "FromConfig",
    "GraphLimitError",
    "Inject",
    "Lifetime",
    "Named",
    "NeedsBindingBuilder",
    "ResolutionCallback",
    "Scope",
    "ScopeError",
    "ServiceExtension",
    "ServiceFactory",
    "ServiceOverride",
    "Tagged",
    "scoped",
    "singleton",
]
