"""Expose Titanspan's native structured logging API.

Application code uses Titanspan records, channels, formatters, processors,
drivers, and manager abstractions. Backend packages stay private.
"""

from titanspan.logging.bridge import StandardLogBridge
from titanspan.logging.channel import LogChannel
from titanspan.logging.configuration import (
    ChannelConfiguration,
    LoggingConfiguration,
)
from titanspan.logging.contracts import (
    AsyncLogDriver,
    LogCustomizer,
    LogDriver,
    LogFormatter,
    LogProcessor,
)
from titanspan.logging.delivery import DeliveryStatus
from titanspan.logging.drivers import (
    BackgroundLogDriver,
    EmergencyLogDriver,
    MemoryLogDriver,
    NullLogDriver,
    StackLogDriver,
)
from titanspan.logging.events import MessageLogged
from titanspan.logging.exceptions import (
    InvalidLogContextError,
    InvalidLogLevelError,
    LogAssertionError,
    LogBackendError,
    LogChannelNotFoundError,
    LogConfigurationError,
    LogContextError,
    LogDeliveryError,
    LogEventError,
    LoggingError,
    LogLifecycleError,
    LogQueueFullError,
)
from titanspan.logging.formatters import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    TextLogFormatter,
)
from titanspan.logging.level import (
    LogLevel,
    from_python_level,
    to_python_level,
)
from titanspan.logging.logger import Logger
from titanspan.logging.manager import LogManager
from titanspan.logging.processors import RedactionProcessor
from titanspan.logging.record import LogRecord, LogValue

__all__ = [
    "AsyncLogDriver",
    "BackgroundLogDriver",
    "ChannelConfiguration",
    "ConsoleLogFormatter",
    "DeliveryStatus",
    "EmergencyLogDriver",
    "InvalidLogContextError",
    "InvalidLogLevelError",
    "JsonLogFormatter",
    "LogAssertionError",
    "LogBackendError",
    "LogChannel",
    "LogChannelNotFoundError",
    "LogConfigurationError",
    "LogContextError",
    "LogCustomizer",
    "LogDeliveryError",
    "LogDriver",
    "LogEventError",
    "LogFormatter",
    "LogLevel",
    "LogLifecycleError",
    "LogManager",
    "LogProcessor",
    "LogQueueFullError",
    "LogRecord",
    "LogValue",
    "Logger",
    "LoggingConfiguration",
    "LoggingError",
    "MemoryLogDriver",
    "MessageLogged",
    "NullLogDriver",
    "RedactionProcessor",
    "StackLogDriver",
    "StandardLogBridge",
    "TextLogFormatter",
    "from_python_level",
    "to_python_level",
]
