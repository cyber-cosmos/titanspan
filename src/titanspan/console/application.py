"""Register commands and execute them through the native application.

The private parser handles command-line syntax. Foundation owns service
composition, dependency resolution, startup, and shutdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from importlib.metadata import entry_points
from inspect import (
    Parameter,
    Signature,
    isawaitable,
    isclass,
    iscoroutinefunction,
    isroutine,
    signature,
)
from pathlib import Path
from traceback import format_exception
from typing import (
    TYPE_CHECKING,
    Annotated,
    TypeGuard,
    get_args,
    get_origin,
    get_type_hints,
)

import anyio

from titanspan._application_context import active_application_context
from titanspan.console._backends.typer import TyperBridge
from titanspan.console.exceptions import (
    CommandDiscoveryError,
    CommandInvocationError,
    CommandRegistrationError,
    ConsoleExitError,
    ConsoleRuntimeError,
)
from titanspan.console.output import TerminalOutput
from titanspan.console.parameters import Argument, Option
from titanspan.console.results import ConsoleResult
from titanspan.console.service_provider import ConsoleServiceProvider
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from titanspan.contracts.console import (
        CommandHandler,
        ConsoleCommand,
        ConsoleOutput,
    )
    from titanspan.contracts.foundation import ServiceProvider

_COMMAND_ENTRY_POINT_GROUP = "titanspan.commands"
_APPLICATION_RUNTIME_ERROR = (
    "Console execution cannot start inside an active async runtime. "
    "Invoke the command from the process entry point."
)
_INVALID_ACTIVE_APPLICATION_ERROR = (
    "Console execution found an invalid active application context."
)
_INVALID_COMMAND_VALUES_ERROR = (
    "Programmatic command values must match registered CLI parameters."
)
_UNKNOWN_COMMAND_ERROR = "The requested command is not registered."
_MAX_EXCEPTION_DETAILS = 8192


@dataclass(frozen=True, slots=True)
class _RegisteredCommand:
    """Retain one command's handler and explicit CLI inputs.

    Programmatic execution uses this metadata without running another parser.
    """

    handler: CommandHandler | type[ConsoleCommand]
    parameters: tuple[tuple[Parameter, Argument | Option], ...]
    with_application: bool


@dataclass(slots=True)
class _RegistrationState:
    """Share duplicate detection across nested Console groups.

    The state belongs to one root Console and prevents child groups from
    creating conflicting command paths.
    """

    command_paths: set[str] = field(default_factory=set[str])
    group_paths: set[str] = field(default_factory=set[str])
    entry_points: set[tuple[str, str, str]] = field(
        default_factory=set[tuple[str, str, str]]
    )
    commands: dict[str, _RegisteredCommand] = field(
        default_factory=dict[str, _RegisteredCommand]
    )


class Console:
    """Own command registration and delegate parsing to the CLI backend.

    Commands use explicit ``Argument`` and ``Option`` metadata for values
    supplied by users. Other annotated parameters resolve from the active
    Application Container when the command runs.
    """

    def __init__(
        self,
        *,
        name: str = "titanspan",
        description: str = "Run application commands.",
        version: str | None = None,
        output: ConsoleOutput | None = None,
        application_factory: (
            Callable[[ServiceProvider], Application] | None
        ) = None,
        show_exception_details: bool = False,
        _state: _RegistrationState | None = None,
        _prefix: tuple[str, ...] = (),
    ) -> None:
        """Create a command host backed by a fresh or supplied Application.

        Args:
            name: CLI name shown in usage output.
            description: Root command description.
            version: Optional version value exposed as ``--version``.
            output: Native output service registered for each command.
            application_factory: Composition root that registers the supplied
                Console provider before Container composition.
            show_exception_details: Whether command failures include chained
                exception text and tracebacks in terminal output.
        """
        self._name = name
        self._output = output if output is not None else TerminalOutput()
        self._application_factory = application_factory or _build_application
        self._show_exception_details = show_exception_details
        self._state = _state or _RegistrationState()
        self._prefix = _prefix
        self._backend = TyperBridge(
            name=name,
            description=description,
            version=version,
            version_output=self._output.write,
        )

    def command[HandlerT](
        self,
        name: str,
        *,
        description: str | None = None,
        with_application: bool = True,
    ) -> Callable[[HandlerT], HandlerT]:
        """Register a handler and return it unchanged as a decorator.

        Args:
            name: Command name within the current group.
            description: Optional text shown in command help.
            with_application: Whether to start and stop Foundation per call.

        Returns:
            A decorator that registers and preserves the original handler.

        Raises:
            CommandRegistrationError: If the command name is invalid or used.
        """

        def register(handler: HandlerT) -> HandlerT:
            """Register a handler without wrapping its public identity.

            The original object remains available to decorators and callers.
            """
            self.register_command(
                name,
                _coerce_handler(handler),
                description=description,
                with_application=with_application,
            )
            return handler

        return register

    def register_command(
        self,
        name: str,
        handler: CommandHandler | type[ConsoleCommand],
        *,
        description: str | None = None,
        with_application: bool = True,
    ) -> None:
        """Register a function or an injectable command class.

        Positional arguments and options require ``Annotated`` metadata.
        Remaining typed parameters are resolved through the application
        Container. Application-free commands must accept only CLI values.

        Args:
            name: Command name within the current group.
            handler: Function, callable object, or class with ``handle``.
            description: Optional text shown in command help.
            with_application: Whether to use Foundation lifecycle handling.

        Raises:
            CommandRegistrationError: If the handler or name is invalid.
        """
        command_name = self._validate_name(name)
        target, command_class = _handler_target(handler)
        if command_class and not with_application:
            message = "Command classes require an active Application Container."
            raise CommandRegistrationError(message)
        parameters = _parser_parameters(target, command_class)
        if not with_application:
            _validate_bootstrap_parameters(target, parameters)
        command_path = " ".join((*self._prefix, command_name))
        if (
            command_path in self._state.command_paths
            or command_path in self._state.group_paths
        ):
            message = f"Command path [{command_path}] is already registered."
            raise CommandRegistrationError(message)

        def invoke(values: dict[str, object]) -> None:
            """Start the owning Application and dispatch parsed values.

            The parser passes only the parameters marked as CLI values.
            """
            self._dispatch(
                handler,
                values,
                command_path,
                with_application=with_application,
            )

        try:
            self._backend.register_command(
                command_name,
                invoke,
                parameters,
                description=description,
            )
        except Exception as error:
            message = (
                f"Could not register command [{command_path}] "
                f"({type(error).__name__})."
            )
            raise CommandRegistrationError(message) from error
        self._state.command_paths.add(command_path)
        self._state.commands[command_path] = _RegisteredCommand(
            handler=handler,
            parameters=parameters,
            with_application=with_application,
        )

    def add_group(
        self,
        name: str,
        *,
        description: str | None = None,
    ) -> Console:
        """Create a nested group that shares output and application policy.

        Args:
            name: Group name used in command paths.
            description: Optional group description.

        Returns:
            A child Console for registering commands and nested groups.

        Raises:
            CommandRegistrationError: If the group name is invalid or used.
        """
        group_name = self._validate_name(name)
        group_path = " ".join((*self._prefix, group_name))
        if (
            group_path in self._state.group_paths
            or group_path in self._state.command_paths
        ):
            message = f"Command group [{group_path}] is already registered."
            raise CommandRegistrationError(message)
        child = Console(
            name=f"{self._name} {group_name}",
            description=description or f"Commands for {group_name}.",
            output=self._output,
            application_factory=self._application_factory,
            _state=self._state,
            _prefix=(*self._prefix, group_name),
        )
        try:
            self._backend.add_group(
                group_name,
                child._backend,
                description=description,
            )
        except Exception as error:
            message = (
                f"Could not register command group [{group_path}] "
                f"({type(error).__name__})."
            )
            raise CommandRegistrationError(message) from error
        self._state.group_paths.add(group_path)
        return child

    def discover_commands(
        self,
        *,
        group: str = _COMMAND_ENTRY_POINT_GROUP,
    ) -> Console:
        """Load trusted installed command entry points in deterministic order.

        Discovery imports installed package code. Use only entry points from
        distributions trusted by the application owner.

        Args:
            group: Python entry-point group to inspect.

        Returns:
            This Console after discovered commands are registered.

        Raises:
            CommandDiscoveryError: If an entry point cannot load or register.
        """
        entries = sorted(
            entry_points(group=group),
            key=lambda entry: (entry.name, entry.value),
        )
        for entry in entries:
            identity = (group, entry.name, entry.value)
            if identity in self._state.entry_points:
                continue
            try:
                handler = _coerce_handler(entry.load())
                self.register_command(entry.name, handler)
            except Exception as error:
                message = (
                    f"Could not load command entry point [{entry.name}] "
                    f"({type(error).__name__})."
                )
                raise CommandDiscoveryError(message) from error
            self._state.entry_points.add(identity)
        return self

    def run(self) -> None:
        """Run the CLI parser against process arguments.

        Raises:
            ConsoleRuntimeError: If called from an active async runtime.
        """
        _ensure_process_runtime()
        self._backend.run()

    def invoke(
        self,
        arguments: Sequence[str],
        *,
        stdin: str | None = None,
    ) -> ConsoleResult:
        """Invoke one command synchronously and capture its terminal output.

        This method supports nested command groups and deterministic tests.
        It must run outside an active asynchronous runtime.

        Args:
            arguments: CLI argument vector, excluding the executable name.
            stdin: Optional text supplied to interactive prompts.

        Returns:
            The command status and captured output streams.

        Raises:
            ConsoleRuntimeError: If called from an active async runtime.
        """
        _ensure_process_runtime()
        code, stdout, stderr = self._backend.invoke(arguments, stdin=stdin)
        return ConsoleResult(code, stdout, stderr)

    async def execute_async(
        self,
        command_path: str,
        values: Mapping[str, object] | None = None,
    ) -> int:
        """Execute one registered command from an existing async runtime.

        This method skips CLI parsing. Supply typed Python values for declared
        command arguments and options. It reuses the active Application or
        owns a fresh Application lifecycle when no context is active.

        Args:
            command_path: Registered command path, with spaces between groups.
            values: Typed values for declared CLI parameters.

        Returns:
            A process-style status code from the command handler.

        Raises:
            CommandInvocationError: If the command or values are invalid.
            ConsoleRuntimeError: If the active application context is invalid.
        """
        registration = self._state.commands.get(command_path)
        if registration is None:
            raise CommandInvocationError(_UNKNOWN_COMMAND_ERROR)
        command_values = self._validate_programmatic_values(
            registration,
            {} if values is None else values,
        )
        try:
            await self._execute(
                registration.handler,
                command_values,
                command_path,
                registration.with_application,
            )
        except ConsoleExitError as exit_request:
            return exit_request.code
        except ConsoleRuntimeError:
            raise
        except Exception as error:
            self._output.write_error(
                self._failure_message(command_path, error),
            )
            return 1
        return 0

    @property
    def output(self) -> ConsoleOutput:
        """Return the configured output contract.

        Bootstrap commands use this object before application construction.
        """
        return self._output

    @property
    def command_names(self) -> tuple[str, ...]:
        """Return registered command paths in deterministic order.

        Nested group names use a single space between path segments.
        """
        return tuple(sorted(self._state.command_paths))

    def _dispatch(
        self,
        handler: CommandHandler | type[ConsoleCommand],
        values: Mapping[str, object],
        command_path: str,
        *,
        with_application: bool,
    ) -> None:
        """Run a command and map native failures to process exit statuses.

        Args:
            handler: Function, callable object, or injectable command class.
            values: Parsed CLI values passed by parameter name.
            command_path: Full group and command path for diagnostics.
            with_application: Whether Foundation owns command execution.
        """
        try:
            _ensure_process_runtime()
            anyio.run(
                self._execute,
                handler,
                dict(values),
                command_path,
                with_application,
            )
        except ConsoleExitError as exit_request:
            self._backend.exit(exit_request.code)
        except Exception as error:
            self._output.write_error(self._failure_message(command_path, error))
            self._backend.exit(1)

    def _failure_message(
        self,
        command_path: str,
        error: Exception,
    ) -> str:
        """Build a safe terminal message for one command failure.

        Args:
            command_path: Registered command path without invocation values.
            error: Exception raised while running the command.

        Returns:
            A classified message with optional bounded developer details.
        """
        message = f"Command [{command_path}] failed ({type(error).__name__})."
        if not self._show_exception_details:
            return message
        details = "".join(format_exception(error))
        if len(details) > _MAX_EXCEPTION_DETAILS:
            details = details[:_MAX_EXCEPTION_DETAILS] + "\n[TRUNCATED]"
        return f"{message}\n{details}"

    async def _execute(
        self,
        handler: CommandHandler | type[ConsoleCommand],
        values: dict[str, object],
        command_path: str,
        with_application: bool,
    ) -> None:
        """Resolve injected values and execute through Foundation lifecycle.

        Args:
            handler: Registered callable or command class.
            values: Parsed command values keyed by parameter name.
            command_path: Full group and command path for exception reports.
            with_application: Whether the command uses an Application.
        """
        if not with_application:
            await self._execute_without_application(handler, values)
            return

        application, owns_application = self._application_for_execution()

        async def operation() -> object:
            """Resolve a command class and invoke its handler.

            Foundation owns application context and resource cleanup.
            """
            try:
                if _is_command_class(handler):
                    if iscoroutinefunction(handler.handle):
                        command = await application.container.make_async(
                            handler,
                        )
                        return await application.container.call_async(
                            command.handle,
                            values,
                        )

                    command_type = handler

                    def run_sync_command() -> object:
                        """Construct and run a sync command in one worker.

                        Returns:
                            The command handler result.
                        """
                        command = application.container.make(command_type)
                        return application.container.call(
                            command.handle,
                            values,
                        )

                    return await anyio.to_thread.run_sync(
                        run_sync_command,
                        abandon_on_cancel=False,
                    )

                callback = _callable_target(handler)
                if iscoroutinefunction(callback):
                    return await application.container.call_async(
                        callback,
                        values,
                    )
                return await anyio.to_thread.run_sync(
                    application.container.call,
                    callback,
                    values,
                    abandon_on_cancel=False,
                )
            except ConsoleExitError:
                raise
            except Exception as error:
                application.report_exception(
                    error,
                    context={"component": "console", "command": command_path},
                )
                raise

        if owns_application:
            await application.run(operation)
        else:
            await operation()

    def _application_for_execution(self) -> tuple[Application, bool]:
        """Select the current app or create one owned by this command.

        Returns:
            The Application and whether this invocation owns its lifecycle.

        Raises:
            ConsoleRuntimeError: If the active context is not a valid native
                Application binding.
        """
        active = active_application_context()
        if active is None:
            provider = ConsoleServiceProvider(self._output)
            return self._application_factory(provider), True
        if (
            isinstance(active.application, Application)
            and active.container is active.application.container
        ):
            return active.application, False
        raise ConsoleRuntimeError(_INVALID_ACTIVE_APPLICATION_ERROR)

    async def _execute_without_application(
        self,
        handler: CommandHandler | type[ConsoleCommand],
        values: dict[str, object],
    ) -> None:
        """Run a synchronous or async bootstrap handler without DI.

        Args:
            handler: Registered bootstrap callable.
            values: Parsed CLI values keyed by parameter name.

        Raises:
            CommandRegistrationError: If a class handler is used.
        """
        if _is_command_class(handler):
            message = (
                "Application-free commands must be registered as functions."
            )
            raise CommandRegistrationError(message)
        callback = _callable_target(handler)
        if iscoroutinefunction(callback):
            result = callback(**values)
        else:
            result = await anyio.to_thread.run_sync(
                partial(callback, **values),
                abandon_on_cancel=False,
            )
        if isawaitable(result):
            await result

    @staticmethod
    def _validate_programmatic_values(
        registration: _RegisteredCommand,
        values: Mapping[str, object],
    ) -> dict[str, object]:
        """Require supplied values to match declared CLI parameters.

        Args:
            registration: Command registration with explicit CLI parameters.
            values: Values supplied by a Python caller.

        Returns:
            A shallow copy safe for one command invocation.

        Raises:
            CommandInvocationError: If a value is unknown or required input is
                missing.
        """
        parameters = tuple(
            parameter for parameter, _ in registration.parameters
        )
        declared = {parameter.name for parameter in parameters}
        if any(name not in declared for name in values):
            raise CommandInvocationError(_INVALID_COMMAND_VALUES_ERROR)
        missing = sorted(
            parameter.name
            for parameter in parameters
            if parameter.default is Parameter.empty
            and parameter.name not in values
        )
        if missing:
            missing_names = ", ".join(missing)
            message = (
                "Programmatic command values are missing required inputs: "
                f"{missing_names}."
            )
            raise CommandInvocationError(message)
        return dict(values)

    def _validate_name(self, name: str) -> str:
        """Validate one path segment before passing it to the parser.

        Args:
            name: Command or group name.

        Returns:
            The unchanged validated name.

        Raises:
            CommandRegistrationError: If the name is empty or contains spaces.
        """
        if (
            not name
            or name.strip() != name
            or any(char.isspace() for char in name)
        ):
            message = "Command and group names must be non-empty single tokens."
            raise CommandRegistrationError(message)
        return name

    _name: str
    _output: ConsoleOutput
    _show_exception_details: bool
    _application_factory: Callable[[ServiceProvider], Application]
    _state: _RegistrationState
    _prefix: tuple[str, ...]
    _backend: TyperBridge


def _build_application(provider: ServiceProvider) -> Application:
    """Build an application that owns the current command output service.

    Args:
        provider: Console provider registered with the application builder.

    Returns:
        A not-yet-started application with one canonical Container.
    """
    return (
        Application.builder()
        .with_base_path(Path.cwd())
        .discover_providers()
        .with_service_provider(provider)
        .build()
    )


def _handler_target(
    handler: CommandHandler | type[ConsoleCommand],
) -> tuple[Callable[..., object], bool]:
    """Select the callable whose signature defines injection and arguments.

    Args:
        handler: Registered function, callable object, or command class.

    Returns:
        The signature source and whether Container must construct a class.

    Raises:
        CommandRegistrationError: If the handler cannot be inspected.
    """
    if _is_command_class(handler):
        target = getattr(handler, "handle", None)
        if not callable(target):
            message = "Command classes must define a callable handle method."
            raise CommandRegistrationError(message)
        return target, True
    if isclass(handler):
        message = "Command classes must define a callable handle method."
        raise CommandRegistrationError(message)
    if not _is_callable_handler(handler):
        message = "Command handlers must be callable."
        raise CommandRegistrationError(message)
    return handler, False


def _parser_parameters(
    target: Callable[..., object],
    command_class: bool,
) -> tuple[tuple[Parameter, Argument | Option], ...]:
    """Select typed CLI parameters and leave service values for Container.

    Args:
        target: Function, callable instance, or command ``handle`` method.
        command_class: Whether the source is an unbound command method.

    Returns:
        Explicit command-line parameter declarations.

    Raises:
        CommandRegistrationError: If annotations or parameter kinds are invalid.
    """
    try:
        target_signature = signature(target)
        try:
            hints = get_type_hints(target, include_extras=True)
        except TypeError:
            # ``signature`` accepts callable instances, but ``get_type_hints``
            # requires their bound ``__call__`` method.
            hints = get_type_hints(target.__call__, include_extras=True)
    except (NameError, TypeError, ValueError) as error:
        message = f"Could not inspect command handler ({type(error).__name__})."
        raise CommandRegistrationError(message) from error

    parameters: list[tuple[Parameter, Argument | Option]] = []
    signature_parameters = tuple(target_signature.parameters.values())
    for index, parameter in enumerate(signature_parameters):
        if command_class and index == 0 and parameter.name in {"self", "cls"}:
            continue
        if parameter.kind not in {
            Parameter.POSITIONAL_OR_KEYWORD,
            Parameter.KEYWORD_ONLY,
        }:
            message = (
                "Command handlers must use named positional or keyword-only "
                "parameters."
            )
            raise CommandRegistrationError(message)
        annotation = hints.get(parameter.name, parameter.annotation)
        declaration = _cli_parameter(parameter, annotation)
        if declaration is not None:
            parameters.append(declaration)
    return tuple(parameters)


def _cli_parameter(
    parameter: Parameter,
    annotation: object,
) -> tuple[Parameter, Argument | Option] | None:
    """Validate one handler parameter and return its CLI declaration.

    Args:
        parameter: Inspected handler parameter.
        annotation: Resolved type and optional ``Annotated`` metadata.

    Returns:
        The parser parameter and its metadata, or ``None`` for injection.

    Raises:
        CommandRegistrationError: If required annotation or CLI metadata is
            invalid.
    """
    if annotation is Parameter.empty and parameter.default is Parameter.empty:
        message = (
            f"Required command parameter [{parameter.name}] needs a type "
            "annotation."
        )
        raise CommandRegistrationError(message)
    if get_origin(annotation) is not Annotated:
        return None

    parts = get_args(annotation)
    metadata = [
        item for item in parts[1:] if isinstance(item, (Argument, Option))
    ]
    if len(metadata) > 1:
        message = (
            f"Command parameter [{parameter.name}] has multiple CLI "
            "declarations."
        )
        raise CommandRegistrationError(message)
    if not metadata:
        return None
    parameter_type = parts[0]
    if parameter_type is Signature.empty:
        message = f"Command parameter [{parameter.name}] requires a type."
        raise CommandRegistrationError(message)
    return parameter.replace(annotation=parameter_type), metadata[0]


def _validate_bootstrap_parameters(
    target: Callable[..., object],
    cli_parameters: tuple[tuple[Parameter, Argument | Option], ...],
) -> None:
    """Require explicit CLI metadata for each bootstrap command value.

    Args:
        target: Bootstrap function with its inspected parameter signature.
        cli_parameters: Parameters declared with native CLI metadata.

    Raises:
        CommandRegistrationError: If a required value has no CLI declaration.
    """
    declared_names = {parameter.name for parameter, _ in cli_parameters}
    for parameter in signature(target).parameters.values():
        if (
            parameter.default is Parameter.empty
            and parameter.name not in declared_names
        ):
            message = (
                "Application-free commands must mark every required "
                "parameter with explicit CLI metadata."
            )
            raise CommandRegistrationError(message)


def _ensure_process_runtime() -> None:
    """Reject synchronous CLI entry from inside an active async runtime.

    Raises:
        ConsoleRuntimeError: If an AnyIO task is already active.
    """
    try:
        anyio.get_current_task()
    except RuntimeError:
        return
    raise ConsoleRuntimeError(_APPLICATION_RUNTIME_ERROR)


def _is_command_class(
    candidate: object,
) -> TypeGuard[type[ConsoleCommand]]:
    """Recognize command classes through their declared handler method.

    Construction remains the responsibility of the native Container.
    """
    return isclass(candidate) and callable(getattr(candidate, "handle", None))


def _is_callable_handler(candidate: object) -> TypeGuard[CommandHandler]:
    """Recognize functions and callable instances at plugin boundaries.

    Entry-point values are validated before parser registration.
    """
    return callable(candidate)


def _coerce_handler(
    candidate: object,
) -> CommandHandler | type[ConsoleCommand]:
    """Validate one dynamically loaded command before registration.

    Args:
        candidate: Object returned by a trusted entry point.

    Returns:
        A callable handler or class with a callable ``handle`` method.

    Raises:
        CommandRegistrationError: If the entry point returns another object.
    """
    if _is_command_class(candidate) or (
        not isclass(candidate) and _is_callable_handler(candidate)
    ):
        return candidate
    message = "Command entry points must return a callable or command class."
    raise CommandRegistrationError(message)


def _callable_target(handler: CommandHandler) -> CommandHandler:
    """Expose callable-object annotations through its bound method.

    Args:
        handler: Registered function, method, or callable instance.

    Returns:
        A function or bound method that the Container can inspect.
    """
    if isroutine(handler):
        return handler
    return handler.__call__


__all__ = ["Console"]
