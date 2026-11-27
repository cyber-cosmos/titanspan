"""Register native cache maintenance commands through Console contracts.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from titanspan.cache.manager import CacheManager  # noqa: TC001
from titanspan.console.parameters import Argument
from titanspan.contracts.console import ConsoleOutput  # noqa: TC001

if TYPE_CHECKING:
    from titanspan.contracts.console import CommandRegistrar


def register_cache_commands(registrar: CommandRegistrar) -> None:
    """Add namespace-safe cache maintenance commands to a registrar.

    Args:
        registrar: Native command registration contract supplied by Console.
    """

    def clear(manager: CacheManager, output: ConsoleOutput) -> None:
        """Clear the configured default application's cache namespace.
        """  # fmt: skip
        manager.store().flush()
        output.write("The default cache namespace was cleared.")

    def forget(
        key: Annotated[str, Argument(description="Cache key to remove")],
        manager: CacheManager,
        output: ConsoleOutput,
    ) -> None:
        """Remove one key from the configured default store.
        """  # fmt: skip
        removed = manager.store().forget(key)
        output.write("Cache key removed." if removed else "Cache key missing.")

    def status(manager: CacheManager, output: ConsoleOutput) -> None:
        """Print safe store drivers, capabilities, and aggregate statistics.
        """  # fmt: skip
        rows: list[tuple[str, str, str]] = []
        for name in manager.store_names:
            configuration = manager.configuration.store_configurations[name]
            details = str(manager.status(name))
            rows.append((name, configuration.driver, details))
        output.table(
            ("Store", "Driver", "Details"),
            rows,
        )

    registrar.register_command(
        "cache:clear",
        clear,
        description="Clear the application's default cache namespace.",
    )
    registrar.register_command(
        "cache:forget",
        forget,
        description="Remove one key from the default cache store.",
    )
    registrar.register_command(
        "cache:status",
        status,
        description="Inspect safe cache store capabilities and statistics.",
    )


__all__ = ["register_cache_commands"]
