"""Register the active terminal output service with an Application.

Foundation composes this provider before the command Container is built.
"""

from titanspan.contracts.console import ConsoleOutput
from titanspan.contracts.container import ServiceRegistry


class ConsoleServiceProvider:
    """Bind the command host's output to the application graph.

    Each command invocation receives its Console output through the canonical
    application Container.
    """

    def __init__(self, output: ConsoleOutput) -> None:
        """Retain the output service owned by the active command host.

        Args:
            output: Native terminal output used by command handlers.
        """
        self._output = output

    def register(self, container: ServiceRegistry) -> None:
        """Register output through the application's canonical registry.

        Args:
            container: Application registry shared by all providers.
        """
        container.instance(ConsoleOutput, self._output)

    _output: ConsoleOutput


__all__ = ["ConsoleServiceProvider"]
