---
title: "Console"
description: "Register typed commands and run them through Foundation."
---

Console provides native command registration, parsing, output, and testing.
Typer parses arguments. Rich renders terminal output. Foundation owns each
application-aware command lifecycle.

## Register a command

Use `Annotated` metadata for values supplied on the command line. Other typed
parameters resolve from the active application Container.

```python
from typing import Annotated

from titanspan.console import Argument, Console
from titanspan.contracts import ConsoleOutput

console = Console()


@console.command("greet")
def greet(
    name: Annotated[str, Argument()],
    output: ConsoleOutput,
) -> None:
    """Print a greeting for one name.

    Args:
        name: Person who receives the greeting.
        output: Application-owned terminal output service.
    """
    output.write(f"Hello, {name}.")
```

`Console.command()` preserves the handler object. Use
`Console.register_command()` when a component already has a handler object.
Both operations use the shared `CommandRegistrar` contract.

## Add options and groups

Use Python defaults for optional command-line values:

```python
from typing import Annotated

from titanspan.console import Console, Option
from titanspan.contracts import ConsoleOutput

console = Console()


@console.command("inspect")
def inspect(
    limit: Annotated[int, Option("--limit", "-l")] = 10,
    *,
    output: ConsoleOutput,
) -> None:
    """Show up to the selected number of records.

    Args:
        limit: Maximum number of records to show.
    """
    output.write(f"Limit: {limit}")
```

Create nested command groups with `add_group()`:

```python
from titanspan.console import Console

console = Console()
admin = console.add_group("admin")


def rebuild_index() -> None:
    """Rebuild the application search index.

    This function represents one application-owned command handler.
    """

admin.register_command("rebuild", rebuild_index)
```

Group state belongs to one `Console`. Names cannot conflict with another
command or group at the same path.

## Resolve command services

Functions and command classes use the application Container. Command classes
define a `handle()` method. The Container constructs a new command object for
each invocation.

```python
from titanspan.contracts import ConfigRepository, ConsoleOutput
from titanspan.console import Console


class StatusCommand:
    """Display the configured application name.

    The command receives its settings through the native Container.
    """

    def __init__(self, config: ConfigRepository) -> None:
        """Retain the shared configuration repository.

        Args:
            config: Application configuration contract.
        """
        self._config = config

    def handle(self, output: ConsoleOutput) -> None:
        """Write the configured application name.

        Args:
            output: Application-owned terminal output service.
        """
        output.write(self._config.get("app.name", "Titanspan"))


console = Console()
console.register_command("status", StatusCommand)
```

The default command factory builds an Application from the current directory.
It loads trusted installed service providers from `titanspan.providers`, then
registers the Console output provider in the same Container. Pass
`application_factory` when commands need explicit configuration or
application-specific provider setup. The factory receives the Console output
provider.

## Discover installed commands

Call `discover_commands()` to load trusted installed entry points from the
`titanspan.commands` group. Discovery order uses entry-point name and value.
This operation imports installed Python code. Install only trusted packages.

Use `with_application=False` only for bootstrap commands that need no
Container services. The built-in configuration commands use this mode because
they must work before application configuration is constructed.

## Terminal output

Inject the shared `ConsoleOutput` contract or construct `TerminalOutput`
directly. Output strings are rendered as plain text.

```python
from titanspan.console import TerminalOutput

output = TerminalOutput()
output.table(["Name", "State"], [["worker", "ready"]])

with output.progress(total=2, description="Indexing") as progress:
    progress.advance()
    progress.complete()
```

`ConsoleExitError` selects a process status from 0 through 255. Other command
exceptions are reported and return status 1. Foundation shuts down the
application before the CLI returns its status. The default terminal message
shows the command and exception class. Set `Console(show_exception_details=True)`
to print bounded chained exception details and a traceback. Those details may
contain secrets.

## Test commands

Use `ConsoleTester` to invoke the real parser and capture text output:

```python
from titanspan.console.testing import ConsoleTester

result = ConsoleTester(console).invoke(["greet", "Ada"])

assert result.exit_code == 0
```

The installed command provides `about`, configuration, route, and event
inspection commands. `route:list` displays the active catalog used for
matching and URL generation. `route:cache` writes a validated metadata
snapshot. `route:clear` removes it. Event cache commands require a configured
`events.manifest_path`. Route snapshots do not skip route discovery at startup.

## Generate application artifacts

Use the native generators to create typed starter files under the selected
application root:

```bash
titanspan make:controller reports.ReportController
titanspan make:middleware RequestId
titanspan make:provider Metrics
titanspan make:command Reindex
titanspan make:event DocumentReady
titanspan make:listener SendNotice --event app.events.DocumentReadyEvent
titanspan make:test documents
```

Names may use dotted application module paths. Generators create parent
directories, reject paths outside the root, and never replace existing files.
The listener generator requires a trusted event class path. Review generated
files before registering providers, middleware, listeners, or commands.

## Current limits

Console does not generate a complete application scaffold. Other components
can add commands through the shared `CommandRegistrar` contract.

Synchronous `run()` and `invoke()` cannot start inside an active async task.
Async handlers run in the CLI-owned AnyIO runtime. Synchronous handlers run
in AnyIO worker threads and must use thread-safe services. Use an async
handler with thread-affine resources. Do not call synchronous process entry
points from application async code.
