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
| Container injection | Implemented | Unit and Foundation integration tests; installed-wheel smoke invokes an injected command and captures its application logger |
| Application startup and shutdown | Implemented | Lifecycle callbacks run around each command |
| Trusted installed command discovery | Implemented | Deterministic entry-point loading tests |
| Installed application provider discovery | Implemented | Default factory uses Foundation provider discovery |
| Canonical application factory selection | Implemented | `test_default_factory_uses_conventional_application_bootstrap` |
| Conventional application commands | Implemented | `routes/console.py` handlers exposed through trusted `titanspan.commands` entry points |
| Terminal text, tables, prompts, and progress | Implemented | `TerminalOutput` implements `ConsoleOutput` |
| Process status and error reporting | Implemented | Exit-code, failure, and cleanup tests |
| Async programmatic execution | Implemented | Active app reuse, standalone lifecycle, input checks, and cancellation tests |
| Nested command execution | Implemented | `test_sync_command_executes_nested_command_in_the_same_application` and `test_async_nested_command_reuses_the_application` |
| Silent nested execution | Implemented | `test_silent_sync_nested_command_hides_output_and_preserves_status` and `test_silent_async_nested_command_hides_failure_output` |
| Parser-backed command tests | Implemented | `ConsoleTester` delegates to the production parser |
| Configuration commands | Implemented | `tests/unit/config/test_config_cli.py` |
| Framework information command | Implemented | `about` reports Titanspan and Python versions without starting an application |
| Route inspection commands | Implemented | `route:list`, `route:cache`, and `route:clear` use active application services |
| Event inspection commands | Implemented | `event:list`, `event:cache`, and `event:clear` use the Events discovery API and application configuration |
| Artifact generation | Implemented | Seven generators write typed files under `ApplicationPaths`; the installed-package smoke imports and dispatches a generated controller |
| Full application scaffolding | Deferred | No complete generated application template is maintained |

## Public API

| API | Behavior |
| --- | --- |
| `Console(...)` | Create one command registry and parser adapter |
| `Console(show_exception_details=False)` | Show only command and exception class unless detailed diagnostics are enabled |
| `command(name, ...)` | Register a handler and return it unchanged |
| `register_command(name, handler, ...)` | Register a function or command class |
| `add_group(name, ...)` | Create a nested registry sharing command-path state |
| `discover_commands(group=...)` | Load trusted installed entry points once |
| `run()` | Parse process arguments and execute one command |
| `invoke(arguments, stdin=...)` | Run the real parser with captured streams |
| `execute_async(command_path, values=None, silent=False)` | Run a registered command from Python; silent calls suppress output and retain the status |
| `execute_sync(command_path, values=None, silent=False)` | Run a nested command from a synchronous handler in the current Application |
| `output` | Return the configured `ConsoleOutput` implementation |
| `command_names` | Return registered command paths in sorted order |
| `Argument(...)`, `Option(...)` | Mark typed parameters as CLI values |
| `TerminalOutput` | Implement text, table, prompt, and progress output |
| `ConsoleTester` | Provide a native test helper around `Console.invoke()` |

Unmarked handler parameters resolve through the canonical application
Container. Explicit CLI values take precedence over injected values. Required
primitive parameters must use `Argument` or `Option` metadata.

## Application ownership

Each CLI application-aware command creates a fresh Application through its
configured factory. The factory receives `ConsoleServiceProvider`, which
registers the selected output instance through the shared `ServiceRegistry`
contract before Container composition. The default factory loads the fixed
`bootstrap/app.py:create_application` convention when present and passes the
Console provider to it. Otherwise, it builds from the current directory and
discovers trusted `titanspan.providers` entry points through Foundation.
`execute_async()` reuses an active Application. `execute_sync()` bridges from
a synchronous handler's AnyIO worker thread to the same runtime; it does not
create a nested event loop. Async handlers should await `execute_async()`.
Passing `silent=True` suppresses `ConsoleOutput` messages, errors, tables,
and progress while preserving the command status. Confirmation prompts remain
interactive so silent calls do not guess an answer.
Without an active context, `execute_async()`
creates and closes one Application through the same factory.

Foundation starts the Application, activates its context, runs provider boot
and invokes the handler through the Container. Foundation then shuts down the
Application on success, command exit, failure, or cancellation. The command
does not keep an Application singleton between invocations.

Bootstrap commands may set `with_application=False`. These commands run
without Container injection or Foundation lifecycle ownership. They must use
only explicit CLI values and services that are safe before application
construction.

Unexpected command failures return status 1. Terminal output shows the
command path and exception class by default. `show_exception_details=True`
prints bounded exception chains and traceback text. Detailed output can
contain secrets.

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
conventional `routes/console.py` module can provide handlers through the
application package's `titanspan.commands` entry points. Command discovery
sorts entries by name and value, records successful loads, and skips them on
repeated calls. The default Application factory uses the fixed
`bootstrap/app.py:create_application` convention when present; otherwise it
discovers service providers from `titanspan.providers`. Entry-point discovery
imports installed package code and therefore accepts only trusted
distributions. The bootstrap imports only that fixed application file and
isolates relative imports by resolved application root.
The built-in configuration commands accept `--path` to select an application
root. They default to the current directory and never call `chdir()`.
Route metadata commands use `ApplicationPaths` and write under the active
application's `bootstrap/cache` directory. The snapshot does not change route
discovery or startup compilation.

Artifact generators also use `ApplicationPaths`. They accept a class name or
dotted application module path, create missing parent directories, reject
resolved destinations outside the root, and open files exclusively. Existing
files remain unchanged. The listener generator requires a trusted dotted event
class path. Generated files are starter code and require application review.

Registration checks command and group paths before modifying the parser. A
failed backend registration does not retain the attempted path. The shared
`CommandRegistrar` protocol lets framework components and applications add
commands without importing Typer.

## Execution and errors

`run()` and `invoke()` are synchronous process boundaries. They reject calls
from an active asynchronous task instead of starting a nested runtime.
`execute_async()` runs async handlers in the current runtime. It accepts
typed Python values and skips command-line parsing. Synchronous
handlers execute in AnyIO worker threads. Dependency injection still uses the
application Container. Synchronous handlers must use thread-safe services;
thread-affine resources require an async handler.

Console waits for synchronous worker completion before propagating
cancellation. This keeps command resources alive until user code exits.

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

Console does not scan arbitrary application modules or generate a complete
application scaffold. Event cache commands require `events.manifest_path`.

`execute_async()` does not invoke the parser or coerce input strings. Callers
must provide typed values for the command's declared arguments and options.

## Verification

- Unit behavior: `tests/unit/console/` and `tests/unit/test_cli.py`.
- Configuration CLI: `tests/unit/config/test_config_cli.py`.
- Foundation integration: `tests/integration/console/`.
- Canonical factory: `tests/integration/console/test_console_lifecycle.py`.
- Artifact generation: `tests/unit/console/test_generators.py` and real
  Console/Application/ASGI coverage in `tests/integration/console/`.
