"""Expose Titanspan-owned built-in logging drivers.

Destination internals are implemented with standard logging handlers behind
native driver classes and contracts.
"""

from titanspan.logging.drivers.background import BackgroundLogDriver
from titanspan.logging.drivers.core import (
    EmergencyLogDriver,
    MemoryLogDriver,
    NullLogDriver,
)
from titanspan.logging.drivers.network import WebhookLogDriver, webhook_options
from titanspan.logging.drivers.stack import StackLogDriver
from titanspan.logging.drivers.standard import (
    StandardHandlerLogDriver,
    create_console_driver,
    create_daily_file_driver,
    create_monthly_file_driver,
    create_rotating_file_driver,
    create_single_file_driver,
    create_syslog_driver,
)

__all__ = [
    "BackgroundLogDriver",
    "EmergencyLogDriver",
    "MemoryLogDriver",
    "NullLogDriver",
    "StackLogDriver",
    "StandardHandlerLogDriver",
    "WebhookLogDriver",
    "create_console_driver",
    "create_daily_file_driver",
    "create_monthly_file_driver",
    "create_rotating_file_driver",
    "create_single_file_driver",
    "create_syslog_driver",
    "webhook_options",
]
