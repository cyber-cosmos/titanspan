"""Expose native command registration and process execution APIs.

Parser and terminal libraries remain behind private adapters.
"""

from titanspan.console.application import Console
from titanspan.console.exceptions import (
    CommandDiscoveryError,
    CommandRegistrationError,
    ConsoleError,
    ConsoleExitError,
    ConsoleOutputError,
    ConsoleRuntimeError,
)
from titanspan.console.output import TerminalOutput
from titanspan.console.parameters import Argument, Option
from titanspan.console.results import ConsoleResult
from titanspan.console.service_provider import ConsoleServiceProvider

__all__ = [
    "Argument",
    "CommandDiscoveryError",
    "CommandRegistrationError",
    "Console",
    "ConsoleError",
    "ConsoleExitError",
    "ConsoleOutputError",
    "ConsoleResult",
    "ConsoleRuntimeError",
    "ConsoleServiceProvider",
    "Option",
    "TerminalOutput",
]
