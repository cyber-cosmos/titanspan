"""Verify native command registration and application integration.

Tests use the real Typer runner and Titanspan application container.
"""

from collections.abc import Sequence
from threading import get_ident
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated

import anyio
import pytest
from rich.text import Text

import titanspan.console.cli as console_cli
from titanspan.console import Argument, Console, ConsoleExitError, Option
from titanspan.console.exceptions import (
    CommandDiscoveryError,
    CommandRegistrationError,
    ConsoleOutputError,
    ConsoleRuntimeError,
)
from titanspan.console.output import TerminalOutput
from titanspan.console.service_provider import ConsoleServiceProvider
from titanspan.console.testing import ConsoleTester
from titanspan.contracts import (
    CommandRegistrar,
    ConfigRepository,
    ConsoleOutput,
    ServiceProvider,
)
from titanspan.contracts.console import ConsoleOutput as DomainConsoleOutput
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.unit
_REQUESTED_EXIT_CODE = 7
_INVALID_EXIT_CODE = 256
_MAX_BOUNDED_ERROR_OUTPUT = 9_000
_PRIVATE_COMMAND_FAILURE = "token=console-secret-value"
_NESTED_DEVELOPMENT_DETAIL = "nested development detail"
_TOP_LEVEL_DEVELOPMENT_DETAIL = "top-level development detail"


def test_sync_command_uses_container_and_application_lifecycle() -> None:
    """Resolve a sync handler through the active application Container.

    The assertions verify configuration injection and lifecycle callbacks.
    """
    lifecycle: list[str] = []
    command_threads: list[int] = []
    caller_thread = get_ident()

    def application_factory(provider: ServiceProvider) -> Application:
        """Build an Application whose lifecycle is visible to the test.

        The supplied provider binds the command's output contract.
        """
        return (
            Application.builder()
            .with_config({"app": {"name": "Console Test"}})
            .on_startup(lambda: lifecycle.append("started"))
            .on_shutdown(lambda: lifecycle.append("stopped"))
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)

    @console.command("greet")
    def greet(
        name: Annotated[str, Argument()],
        config: ConfigRepository,
        output: ConsoleOutput,
    ) -> None:
        """Print a configured greeting.

        The handler receives both a CLI value and Container services.
        """
        command_threads.append(get_ident())
        output.write(f"Hello {name} from {config.get('app.name')}.")

    result = ConsoleTester(console).invoke(["greet", "Ada"])

    assert result.exit_code == 0
    assert "Hello Ada from Console Test." in result.stdout
    assert lifecycle == ["started", "stopped"]
    assert len(command_threads) == 1
    assert command_threads[0] != caller_thread


def test_application_factory_console_includes_framework_commands() -> None:
    """Keep the canonical command catalog on custom application hosts.

    A selected application factory retains the installed command catalog.
    """
    console = Console(
        application_factory=lambda provider: (
            Application.builder().with_service_provider(provider).build()
        ),
    )

    assert {
        "about",
        "cache:clear",
        "migrate",
        "queue:work",
        "route:list",
    }.issubset(console.command_names)
    result = ConsoleTester(console).invoke(["about"])
    routes = ConsoleTester(console).invoke(["route:list"])

    assert result.exit_code == 0
    assert "Titanspan" in result.stdout
    assert routes.exit_code == 0
    assert "METHOD" in routes.stdout


def test_async_command_class_uses_injected_constructor_and_options() -> None:
    """Resolve command objects and async handlers with typed options.

    The test covers constructor injection and an option default.
    """
    console = Console()

    class CountCommand:
        """Print a selected count using the output contract.

        The Container constructs this command for each invocation.
        """

        def __init__(self, config: ConfigRepository) -> None:
            """Retain a contract resolved by the application Container.

            The command reads its application name from shared configuration.
            """
            self._config = config

        async def handle(
            self,
            output: ConsoleOutput,
            count: Annotated[int, Option("--count", "-c")] = 4,
        ) -> None:
            """Print one number through the framework output service.

            The asynchronous signature is awaited by the CLI runtime.
            """
            output.write(
                f"{self._config.get('app.name', 'Application')}: {count}"
            )

    console.register_command("count", CountCommand)
    result = ConsoleTester(console).invoke(["count", "--count", "7"])
    default_result = ConsoleTester(console).invoke(["count"])

    assert result.exit_code == 0
    assert "Titanspan: 7" in result.stdout
    assert default_result.exit_code == 0
    assert "Titanspan: 4" in default_result.stdout


def test_sync_command_class_constructs_and_runs_in_one_worker() -> None:
    """Keep synchronous command construction and handling off the loop.

    The native Container resolves constructor and method services there.
    """
    caller_thread = get_ident()
    command_threads: list[tuple[str, int]] = []
    console = Console()

    class InspectCommand:
        """Report the injected application name from one worker thread.

        The Container supplies configuration and command output.
        """

        def __init__(self, config: ConfigRepository) -> None:
            """Resolve command configuration through Foundation.

            Args:
                config: Application-owned configuration contract.
            """
            name = config.get("app.name", "Application")
            assert isinstance(name, str)
            self._name = name
            command_threads.append(("construct", get_ident()))

        def handle(self, output: ConsoleOutput) -> None:
            """Write the command result through the native output service.

            Args:
                output: Console output resolved by the Container.
            """
            command_threads.append(("handle", get_ident()))
            output.write(self._name)

    console.register_command("inspect", InspectCommand)
    result = ConsoleTester(console).invoke(["inspect"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Titanspan"
    assert [name for name, _ in command_threads] == ["construct", "handle"]
    assert command_threads[0][1] != caller_thread
    assert command_threads[1][1] != caller_thread


def test_application_free_sync_command_runs_in_a_worker() -> None:
    """Offload synchronous bootstrap handlers from the CLI event loop.

    Application-free commands still use AnyIO's managed worker pool.
    """
    caller_thread = get_ident()
    command_threads: list[int] = []
    console = Console()

    @console.command("bootstrap", with_application=False)
    def bootstrap(name: Annotated[str, Argument()]) -> None:
        """Record the worker thread that handles the CLI argument.

        Args:
            name: Name supplied through the native argument declaration.
        """
        _ = name
        command_threads.append(get_ident())

    result = ConsoleTester(console).invoke(["bootstrap", "Ada"])

    assert result.exit_code == 0
    assert len(command_threads) == 1
    assert command_threads[0] != caller_thread


def test_nested_groups_and_command_discovery_use_one_registry() -> None:
    """Dispatch nested groups and preserve decorated handler identity.

    The test uses the production parser for the complete command path.
    """
    console = Console()
    admin = console.add_group("admin")
    users = admin.add_group("users")

    @users.command("list")
    def list_users(output: ConsoleOutput) -> None:
        """Print a stable group command result.

        The handler receives output from the command Application.
        """
        output.write("users listed")

    assert console.command_names == ("admin users list",)
    result = ConsoleTester(console).invoke(["admin", "users", "list"])

    assert result.exit_code == 0
    assert "users listed" in result.stdout


def test_catalog_copy_preserves_nested_group_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep command groups and their handlers when copying a catalog.

    The copied parser must dispatch the same complete command path.
    """
    source = Console()
    admin = source.add_group("admin", description="Administration")
    users = admin.add_group("users", description="User commands")

    @users.command("list")
    def list_users(output: ConsoleOutput) -> None:
        """Write the user list from the copied command catalog.

        Args:
            output: Output service owned by command execution.
        """
        output.write("users listed")

    monkeypatch.setattr(console_cli, "console", source)
    target = Console(
        application_factory=lambda provider: (
            Application.builder().with_service_provider(provider).build()
        ),
    )
    result = ConsoleTester(target).invoke(["admin", "users", "list"])

    assert target.command_names == ("admin users list",)
    assert result.exit_code == 0
    assert "users listed" in result.stdout


def test_command_exit_code_survives_application_shutdown() -> None:
    """Restore application resources before returning an explicit exit code.

    The shutdown callback must run before the CLI reports the status.
    """
    closed: list[bool] = []
    console = Console(
        application_factory=lambda provider: Application.builder()
        .with_service_provider(provider)
        .on_shutdown(lambda: closed.append(True))
        .build()
    )

    @console.command("stop")
    def stop() -> None:
        """Stop the command with a caller-selected status code.

        Foundation still completes shutdown before Console handles the error.
        """
        raise ConsoleExitError(_REQUESTED_EXIT_CODE)

    result = ConsoleTester(console).invoke(["stop"])

    assert result.exit_code == _REQUESTED_EXIT_CODE
    assert closed == [True]


def test_command_failure_is_rendered_without_a_traceback() -> None:
    """Report a useful command failure and keep application cleanup.

    The test verifies a nonzero status without exposing a traceback.
    """
    closed: list[bool] = []
    console = Console(
        application_factory=lambda provider: Application.builder()
        .with_service_provider(provider)
        .on_shutdown(lambda: closed.append(True))
        .build()
    )

    @console.command("fail")
    def fail() -> None:
        """Raise one predictable command error.

        The command failure exercises Foundation reporting and shutdown.
        """
        raise ValueError(_PRIVATE_COMMAND_FAILURE)

    result = ConsoleTester(console).invoke(["fail"])

    assert result.exit_code == 1
    assert _PRIVATE_COMMAND_FAILURE not in result.stderr
    assert "Command [fail] failed" in result.stderr
    assert "ValueError" in result.stderr
    assert closed == [True]


def test_command_details_require_an_explicit_console_policy() -> None:
    """Show exception text and causes only when details are enabled.

    Detailed terminal diagnostics can contain private values from exception
    messages and chained causes.
    """
    console = Console(show_exception_details=True)

    @console.command("fail")
    def fail() -> None:
        """Raise an exception with a chained developer diagnostic.

        The test checks the explicit detailed-output policy.
        """
        cause = ValueError(_NESTED_DEVELOPMENT_DETAIL)
        error = RuntimeError(_TOP_LEVEL_DEVELOPMENT_DETAIL)
        error.__cause__ = cause
        raise error

    result = ConsoleTester(console).invoke(["fail"])

    assert result.exit_code == 1
    assert _TOP_LEVEL_DEVELOPMENT_DETAIL in result.stderr
    assert _NESTED_DEVELOPMENT_DETAIL in result.stderr
    assert "RuntimeError" in result.stderr


def test_detailed_command_output_is_bounded() -> None:
    """Bound opt-in traceback output for unusually large exceptions.

    Developers can request details, but a command cannot flood the terminal
    with an arbitrarily large exception message.
    """
    console = Console(show_exception_details=True)

    @console.command("fail")
    def fail() -> None:
        """Raise an exception larger than the output bound.

        The command output must include the truncation marker.
        """
        raise ValueError("x" * 10_000)

    result = ConsoleTester(console).invoke(["fail"])

    assert result.exit_code == 1
    assert "[TRUNCATED]" in result.stderr
    assert len(result.stderr) < _MAX_BOUNDED_ERROR_OUTPUT


def test_duplicate_command_names_are_rejected() -> None:
    """Reject conflicting command registrations before invocation.

    Duplicate names cannot mutate the parser registry.
    """
    console = Console()

    def first() -> None:
        """Return without side effects.

        This handler reserves the command name for the test.
        """

    def second() -> None:
        """Return without side effects.

        This handler conflicts with the first registration.
        """

    console.register_command("same", first)

    with pytest.raises(ValueError, match="already registered"):
        console.register_command("same", second)


def test_registered_handler_keeps_its_original_callable_identity() -> None:
    """Keep decorators transparent to code that retains a handler reference.

    Registration must not wrap the callable returned to application code.
    """
    console = Console()

    def handler() -> None:
        """Return without output.

        The test inspects this original function after decoration.
        """

    registered: Callable[[], None] = console.command("identity")(handler)

    assert registered is handler


def test_callable_object_uses_its_call_signature() -> None:
    """Register a callable object with CLI and Container parameters.

    The command parser inspects the bound ``__call__`` method.
    """
    console = Console()

    class CallableCommand:
        """Write a parsed value through the injected output contract.

        This instance acts as a command handler without a wrapper function.
        """

        def __call__(
            self,
            name: Annotated[str, Argument()],
            output: ConsoleOutput,
        ) -> None:
            """Report the parsed name.

            Args:
                name: Name supplied as a positional CLI argument.
                output: Output contract resolved by Foundation's Container.
            """
            output.write(name)

    console.register_command("callable", CallableCommand())
    result = ConsoleTester(console).invoke(["callable", "Ada"])

    assert result.exit_code == 0
    assert "Ada" in result.stdout


def test_console_satisfies_the_shared_command_registrar_contract() -> None:
    """Allow components to register commands through the shared contract.

    The top-level contract export must preserve canonical identity.
    """
    registrar: CommandRegistrar = Console()

    assert callable(registrar.register_command)
    assert DomainConsoleOutput is ConsoleOutput


def test_console_provider_registers_output_with_the_native_container() -> None:
    """Resolve the shared output service through Foundation's Container.

    The provider registers the same object used by the command host.
    """
    output = TerminalOutput()
    provider: ServiceProvider = ConsoleServiceProvider(output)
    application = Application.builder().with_service_provider(provider).build()

    assert application.container.make(ConsoleOutput) is output


def test_terminal_output_writes_plain_text_to_both_streams(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Render message text without interpreting terminal markup.

    The test checks standard output and standard error independently.
    """
    output = TerminalOutput()
    output.write("[bold]literal[/bold]")
    output.write_error("[red]failure[/red]")

    captured = capsys.readouterr()

    assert "[bold]literal[/bold]" in captured.out
    assert "[red]failure[/red]" in captured.err


def test_terminal_output_validates_tables_and_progress() -> None:
    """Reject malformed output and close valid progress displays.

    Rich owns rendering while the native adapter validates domain inputs.
    """
    output = TerminalOutput()

    with pytest.raises(ConsoleOutputError, match="at least one header"):
        output.table([], [])
    with pytest.raises(ConsoleOutputError, match="match the header count"):
        output.table(["Name"], [["Ada", "Grace"]])
    output.table(["Name"], [])
    with pytest.raises(ConsoleOutputError, match="cannot be negative"):
        output.progress(-1, "Invalid")

    with output.progress(2, "Processing") as progress:
        progress.advance()
        progress.complete()
        with pytest.raises(ConsoleOutputError, match="must be positive"):
            progress.advance(0)


def test_terminal_output_passes_confirmation_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass the prompt and safe default to Rich confirmation handling.

    The patch isolates the user response while keeping the native adapter.
    """
    calls: list[tuple[Text, bool]] = []

    def ask(
        prompt: Text,
        *,
        default: bool,
        console: object,
    ) -> bool:
        """Record the prompt and return the controlled user answer.

        The Rich Console argument is intentionally not inspected.
        """
        del console
        calls.append((prompt, default))
        return True

    monkeypatch.setattr(
        "titanspan.console._backends.rich_output.Confirm.ask",
        ask,
    )

    prompt = "[danger]literal[/danger]"
    assert TerminalOutput().confirm(prompt, default=False)
    assert calls[0][0].plain == prompt
    assert calls[0][1] is False


def test_command_discovery_loads_trusted_entries_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load installed command entry points in stable, idempotent order.

    Repeated discovery must not register the same installed command twice.
    """
    calls: list[str] = []

    def handler() -> None:
        """Return after the discovered command starts its Application.

        The test observes one invocation after repeated discovery.
        """
        calls.append("called")

    entry = SimpleNamespace(
        name="plugin",
        value="plugin:handler",
        load=lambda: handler,
    )

    def load_entries(*, group: str) -> Sequence[SimpleNamespace]:
        """Return the trusted command fixture for the requested group.

        This entry point replaces metadata lookup for the test.
        """
        assert group == "sample.commands"
        return [entry]

    monkeypatch.setattr(
        "titanspan.console.application.entry_points",
        load_entries,
    )
    console = Console()

    console.discover_commands(group="sample.commands")
    console.discover_commands(group="sample.commands")
    result = ConsoleTester(console).invoke(["plugin"])

    assert result.exit_code == 0
    assert console.command_names == ("plugin",)
    assert calls == ["called"]


def test_command_discovery_reports_invalid_entries_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrap a broken trusted entry point in a native discovery exception.

    Failure text does not expose the entry point object's representation.
    """
    entry = SimpleNamespace(
        name="broken",
        value="broken:command",
        load=lambda: object(),
    )

    def load_entries(*, group: str) -> Sequence[SimpleNamespace]:
        """Return the failing command fixture for the requested group.

        The entry point returns an invalid command value.
        """
        assert group == "sample.commands"
        return [entry]

    monkeypatch.setattr(
        "titanspan.console.application.entry_points",
        load_entries,
    )

    with pytest.raises(CommandDiscoveryError, match="broken"):
        Console().discover_commands(group="sample.commands")


def test_command_registration_rejects_invalid_signatures() -> None:
    """Reject positional-only handlers before parser construction.

    This validation keeps parser parameter names deterministic.
    """
    console = Console()

    def invalid(value: str, /) -> None:
        """Represent a handler with one positional-only value.

        Console must reject this signature during registration.
        """

    with pytest.raises(CommandRegistrationError, match="named positional"):
        console.register_command("invalid", invalid)


def test_bootstrap_commands_reject_required_unmarked_parameters() -> None:
    """Require CLI metadata when command execution has no Container.

    Bootstrap commands cannot inject a required application dependency.
    """

    def invalid(value: str) -> None:
        """Represent one required value without CLI metadata.

        The registration boundary must reject this ambiguous parameter.
        """

    with pytest.raises(CommandRegistrationError, match="explicit CLI metadata"):
        Console().register_command(
            "invalid",
            invalid,
            with_application=False,
        )


def test_command_registration_rejects_classes_without_handle() -> None:
    """Reject callable classes that do not follow command conventions.

    A class must define a handler method before registration.
    """

    class InvalidCommand:
        """Represent a class without the required command method.

        The test ensures classes are not mistaken for function handlers.
        """

    with pytest.raises(CommandRegistrationError, match="handle method"):
        Console().register_command("invalid", InvalidCommand)


def test_class_commands_require_an_application_container() -> None:
    """Reject command classes without application lifecycle ownership.

    Command objects require Container construction and injection.
    """

    class Worker:
        """Provide one injectable command handler.

        The test registers this class without an Application.
        """

        def handle(self) -> None:
            """Finish without side effects.

            Registration fails before this handler can execute.
            """

    with pytest.raises(CommandRegistrationError, match="Container"):
        Console().register_command(
            "worker",
            Worker,
            with_application=False,
        )


def test_nested_group_state_rejects_duplicate_paths() -> None:
    """Prevent conflicting groups in the shared command tree.

    Child Console objects use the root registry's path state.
    """
    console = Console()
    console.add_group("admin")

    with pytest.raises(CommandRegistrationError, match="already registered"):
        console.add_group("admin")


def test_backend_registration_failure_does_not_reserve_command_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep native command state unchanged after parser failure.

    A failed backend call must not block a corrected registration attempt.
    """
    console = Console()

    def fail_registration(*args: object, **kwargs: object) -> None:
        """Fail one parser registration attempt.

        Args:
            args: Ignored backend registration values.
            kwargs: Ignored backend registration options.
        """
        del args, kwargs
        raise RuntimeError

    def handler() -> None:
        """Complete without side effects.

        The handler is registered after the parser adapter recovers.
        """

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            "titanspan.console._backends.typer.TyperBridge.register_command",
            fail_registration,
        )
        with pytest.raises(
            CommandRegistrationError,
            match="Could not register",
        ):
            console.register_command("retry", handler)
    assert console.command_names == ()

    console.register_command("retry", handler)

    assert console.command_names == ("retry",)


def test_backend_group_failure_does_not_reserve_group_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow a group registration retry after the parser rejects it.

    Failed group setup must not mutate the shared path registry.
    """
    console = Console()

    def fail_group(*args: object, **kwargs: object) -> None:
        """Fail one parser group operation.

        Args:
            args: Ignored group registration values.
            kwargs: Ignored group registration options.
        """
        del args, kwargs
        raise RuntimeError

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            "titanspan.console._backends.typer.TyperBridge.add_group",
            fail_group,
        )
        with pytest.raises(
            CommandRegistrationError,
            match="Could not register",
        ):
            console.add_group("retry")

    child = console.add_group("retry")

    assert child.command_names == ()


def test_run_delegates_to_the_production_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the native process entry point through its parser adapter.

    The test replaces only Typer's process boundary.
    """
    console = Console()
    calls: list[bool] = []

    def run_backend(bridge: object) -> None:
        """Record that Console entered the configured parser.

        The parser method is replaced only for this test.
        """
        del bridge
        calls.append(True)

    monkeypatch.setattr(
        "titanspan.console._backends.typer.TyperBridge.run",
        run_backend,
    )
    console.run()

    assert calls == [True]


def test_async_bootstrap_command_uses_explicit_cli_values() -> None:
    """Await an application-free async command in the CLI runtime.

    Bootstrap handlers receive only parameters marked as command-line input.
    """
    console = Console()
    values: list[str] = []

    @console.command("bootstrap", with_application=False)
    async def bootstrap(
        name: Annotated[str, Argument()],
    ) -> None:
        """Record one explicitly supplied bootstrap value.

        Args:
            name: Value parsed by the native command definition.
        """
        values.append(name)

    result = ConsoleTester(console).invoke(["bootstrap", "ready"])

    assert result.exit_code == 0
    assert values == ["ready"]


def test_registration_rejects_missing_and_duplicate_cli_metadata() -> None:
    """Reject ambiguous required inputs and duplicate parser declarations.

    Invalid metadata must fail before the backend changes its parser.
    """
    console = Console()

    def missing_type(value: str) -> None:
        """Represent one required value without a type annotation.

        The test removes its runtime annotation to exercise validation.
        """
        del value

    missing_type.__annotations__.pop("value")

    def duplicate_metadata(
        value: Annotated[str, Argument(), Option("--value")],
    ) -> None:
        """Represent an input declared as both argument and option.

        Args:
            value: Ambiguous input that Console must reject.
        """

    with pytest.raises(CommandRegistrationError, match="needs a type"):
        console.register_command("missing", missing_type)
    with pytest.raises(CommandRegistrationError, match="multiple CLI"):
        console.register_command("duplicate", duplicate_metadata)


def test_option_metadata_requires_valid_names() -> None:
    """Require each option name to use a valid command-line prefix.

    The error remains a native ValueError before parser registration.
    """
    with pytest.raises(ValueError, match="begin with a hyphen"):
        Option()
    with pytest.raises(ValueError, match="begin with a hyphen"):
        Option("limit")
    with pytest.raises(ValueError, match="begin with a hyphen"):
        Option("-")


def test_console_invocation_rejects_an_active_async_runtime() -> None:
    """Avoid starting a second runtime from an async caller.

    Synchronous process entry points fail with a native actionable error.
    """

    async def invoke() -> None:
        """Attempt CLI execution inside a running event loop.

        The call must fail before the parser starts another runtime.
        """
        with pytest.raises(ConsoleRuntimeError, match="active async runtime"):
            Console().invoke(["--help"])

    anyio.run(invoke)


def test_console_exit_error_rejects_invalid_status_codes() -> None:
    """Constrain process statuses to the operating system range.

    Invalid values must fail when the native error is constructed.
    """
    with pytest.raises(ValueError, match="between 0 and 255"):
        ConsoleExitError(_INVALID_EXIT_CODE)
