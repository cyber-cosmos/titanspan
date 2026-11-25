"""Expose dependency-independent Titanspan protocols and interfaces.

The package re-exports canonical contracts without adding implementations.
"""

from titanspan.contracts.config_repository import ConfigRepository
from titanspan.contracts.container import (
    AsyncServiceContainer,
    InstanceRegistration,
    ServiceContainer,
)
from titanspan.contracts.support import (
    Arrayable,
    ArrayKey,
    DeferringDisplayableValue,
    Htmlable,
    Jsonable,
    LaravelArrayable,
    LaravelDeferringDisplayableValue,
    LaravelHtmlable,
    LaravelJsonable,
    LaravelResponsable,
    MessageBagData,
    MessageKey,
    MessageProvider,
    Renderable,
    Responsable,
    ValidatedData,
)

__all__ = [
    "ArrayKey",
    "Arrayable",
    "AsyncServiceContainer",
    "ConfigRepository",
    "DeferringDisplayableValue",
    "Htmlable",
    "InstanceRegistration",
    "Jsonable",
    "LaravelArrayable",
    "LaravelDeferringDisplayableValue",
    "LaravelHtmlable",
    "LaravelJsonable",
    "LaravelResponsable",
    "MessageBagData",
    "MessageKey",
    "MessageProvider",
    "Renderable",
    "Responsable",
    "ServiceContainer",
    "ValidatedData",
]
