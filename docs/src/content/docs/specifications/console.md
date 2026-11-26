---
title: "Console behavioral specification"
---

# Console behavioral specification

This specification records verified behavior in `titanspan.console`. Typer
owns command parsing. Rich owns terminal rendering. Foundation owns
application composition and resource cleanup.

## Capability inventory

| Capability | Status | Evidence |
| --- | --- | --- |
| Native command registration | Implemented | `tests/unit/console/`; shared `CommandRegistrar` contract |
| Decorator registration | Implemented | Handler identity and invocation tests |
| Nested command groups | Implemented | Real Typer invocation tests |
| Typed arguments and options | Implemented | `Annotated` metadata and default-value tests |
| Function and class handlers | Implemented | Sync function and async class command tests |
| Callable object handlers | Implemented | Bound `__call__` signature and injection test |
| Container injection | Implemented | Unit and Foundation integration tests |
| Application startup and shutdown | Implemented | Lifecycle callbacks run around each command |
| Trusted installed command discovery | Implemented | Deterministic entry-point loading tests |
| Installed application provider discovery | Implemented | Default factory uses Foundation provider discovery |
| Terminal text, tables, prompts, and progress | Implemented | `TerminalOutput` implements `ConsoleOutput` |
| Process status and error reporting | Implemented | Exit-code, failure, and cleanup tests |
| Parser-backed command tests | Implemented | `ConsoleTester` delegates to the production parser |
| Configuration commands | Implemented | `tests/unit/config/test_config_cli.py` |
| Route inspection command | Implemented | `route:list` resolves the shared `RouteCatalog` and `ConsoleOutput` contracts; `tests/integration/console/test_route_list_command.py` |
| Event inspection command | Pending | The Events component does not expose a stable read-only inspection contract |
| Application and command generation | Pending | No supported template lifecycle exists |

## Public API

| API | Behavior |
| --- | --- |
| `Console(...)` | Create one command registry and parser adapter |
| `command(name, ...)` | Register a handler and return it unchanged |
| `register_command(name, handler, ...)` | Register a function or command class |
| `add_group(name, ...)` | Create a nested registry sharing command-path state |
| `discover_commands(group=...)` | Load trusted installed entry points once |
| `run()` | Parse process arguments and execute one command |
| `invoke(arguments, stdin=...)` | Run the real parser with captured streams |
| `output` | Return the configured `ConsoleOutput` implementation |
| `command_names` | Return registered command paths in sorted order |
| `Argument(...)`, `Option(...)` | Mark typed parameters as CLI values |
| `TerminalOutput` | Implement text, table, prompt, and progress output |
| `ConsoleTester` | Provide a native test helper around `Console.invoke()` |

Unmarked handler parameters resolve through the canonical application
Container. Explicit CLI values take precedence over injected values. Required
primitive parameters must use `Argument` or `Option` metadata.

## Application ownership

Each application-aware command creates a fresh Application through its
configured factory. The factory receives `ConsoleServiceProvider`, which
registers the selected output instance through the shared `ServiceRegistry`
contract before Container composition. The default factory first discovers
trusted `titanspan.providers` entry points through Foundation. It then adds
the Console provider, so application services and Console output share one
Container.

Foundation starts the Application, activates its context, runs provider boot
and invokes the handler through the Container. Foundation then shuts down the
Application on success, command exit, failure, or cancellation. The command
does not keep an Application singleton between invocations.

Bootstrap commands may set `with_application=False`. These commands run
without Container injection or Foundation lifecycle ownership. They must use
only explicit CLI values and services that are safe before application
construction.

## Command parameters

CLI parameters use `typing.Annotated` with `Argument` or `Option`. Their Python
parameter defaults remain the parser defaults. Other parameters use Container
injection. Positional-only and variadic parameters fail during registration.
Unresolved dependencies fail through the Container's native error behavior.

Command classes expose a callable `handle()` method. The Container resolves
the command class and its constructor dependencies for every invocation. The
bound `handle()` method then receives parsed CLI values and injected services.
Callable instances expose their bound `__call__` signature for parsing and
Container injection.

## Discovery and registration

`discover_commands()` reads Python entry points from one named group. The
installed `titanspan` entry point discovers commands before parsing. The
default Application factory discovers service providers from
`titanspan.providers`. Both discovery paths sort entries by name and value,
record successful loads, and skip them on repeated calls. Discovery imports
installed package code and therefore accepts only trusted distributions.

Registration checks command and group paths before modifying the parser. A
failed backend registration does not retain the attempted path. The shared
`CommandRegistrar` protocol lets framework components and applications add
commands without importing Typer.

## Execution and errors

`run()` and `invoke()` are synchronous process boundaries. They reject calls
from an active asynchronous task instead of starting a nested runtime.
Handlers may be synchronous or asynchronous. Console owns one AnyIO runtime
for each command invocation.

`ConsoleExitError` carries an operating-system status from 0 through 255.
Other `Exception` values are reported through Foundation when an Application
is active. Console writes a concise error and returns status 1. Cancellation
propagates through Foundation cleanup.

## Shared contracts

`CommandHandler`, `ConsoleCommand`, `CommandRegistrar`, `ConsoleOutput`, and
`ProgressTask` are defined once under `titanspan.contracts.console`. The
top-level `titanspan.contracts` module re-exports the same objects. Console
and `TerminalOutput` implement these boundaries without exposing Typer or
Rich types.

## Limitations

Console does not scan arbitrary application modules. It does not generate
application scaffolds or command classes. It does not provide event
inspection until Events exposes a stable read-only inspection contract.

Nested command groups are supported. Invoking a second command from inside an
active command is unsupported because the synchronous entry point cannot
start another runtime.

## Verification

- Unit behavior: `tests/unit/console/` and `tests/unit/test_cli.py`.
- Configuration CLI: `tests/unit/config/test_config_cli.py`.
- Foundation integration: `tests/integration/console/`.
