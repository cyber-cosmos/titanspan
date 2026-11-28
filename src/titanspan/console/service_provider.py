"""Register the active terminal output service with an Application.

Foundation composes this provider before the command Container is built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.contracts.console import ConsoleOutput

if TYPE_CHECKING:
    from titanspan.console.application import Console
    from titanspan.contracts.container import ServiceRegistry


class ConsoleServiceProvider:
    """Bind the active command host to the application graph.

    Command handlers resolve output and the host for nested execution through
    the canonical application Container.
    """

    def __init__(
        self,
        output: ConsoleOutput,
        console: Console | None = None,
    ) -> None:
        """Retain the output service owned by the active command host.

        Args:
            output: Native terminal output used by command handlers.
            console: Optional command host for nested invocations.
        """
        self._output = output
        self._console = console

    def register(self, container: ServiceRegistry) -> None:
        """Register the active Console services through the native registry.

        Args:
            container: Application registry shared by all providers.
        """
        container.instance(ConsoleOutput, self._output)
        if self._console is not None:
            container.instance(type(self._console), self._console)

    _output: ConsoleOutput
    _console: Console | None


__all__ = ["ConsoleServiceProvider"]
