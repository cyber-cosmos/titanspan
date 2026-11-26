"""Expose dependency-independent Titanspan contracts.

Domain packages own each protocol. These exports provide convenient imports
without creating additional contract identities or concrete implementations.
"""

from titanspan.contracts.config import (
    ConfigArray,
    ConfigDiagnostics,
    ConfigKeySequence,
    ConfigMacroRegistry,
    ConfigReader,
    ConfigRepository,
    ConfigWriter,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.contracts.container import (
    AsyncServiceContainer,
    InstanceRegistration,
    Scope,
    ServiceContainer,
    ServiceFactory,
    ServiceRegistry,
)
from titanspan.contracts.foundation import (
    BootableServiceProvider,
    ServiceProvider,
)
from titanspan.contracts.logging import (
    AsyncLogDriver,
    DeliveryStatus,
    LogBridge,
    LogCustomizer,
    LogDriver,
    LogFormatter,
    LoggingManager,
    LogProcessor,
    LogWriter,
)
from titanspan.contracts.support import (
    DeferredDisplayValue,
    HtmlRenderable,
    MessageBagProtocol,
    MessageKey,
    MessageProvider,
)

__all__ = [
    "AsyncLogDriver",
    "AsyncServiceContainer",
    "BootableServiceProvider",
    "ConfigArray",
    "ConfigDiagnostics",
    "ConfigKeySequence",
    "ConfigMacroRegistry",
    "ConfigReader",
    "ConfigRepository",
    "ConfigWriter",
    "DeferredDisplayValue",
    "DeliveryStatus",
    "HtmlRenderable",
    "InstanceRegistration",
    "LogBridge",
    "LogCustomizer",
    "LogDriver",
    "LogFormatter",
    "LogProcessor",
    "LogWriter",
    "LoggingManager",
    "MessageBagProtocol",
    "MessageKey",
    "MessageProvider",
    "Scope",
    "ScopedConfigOverrides",
    "ServiceContainer",
    "ServiceFactory",
    "ServiceProvider",
    "ServiceRegistry",
    "TypedConfigReader",
]
