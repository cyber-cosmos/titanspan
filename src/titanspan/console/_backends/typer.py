"""Adapt native command metadata to Typer's parser and test runner.

No Typer class escapes this private adapter.
"""

from __future__ import annotations

from inspect import Parameter, Signature
from typing import TYPE_CHECKING, Annotated

import typer
from typer.testing import CliRunner

from titanspan.console.parameters import Argument, Option

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

type _CommandParameter = tuple[Parameter, Argument | Option]


class TyperBridge:
    """Own the private Typer application used by Console.

    The bridge translates only parser metadata and process output.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        version: str | None,
        version_output: Callable[[str], None],
    ) -> None:
        """Create a parser and register its native global options.

        Args:
            name: CLI name shown in usage output.
            description: Root description.
            version: Optional installed package version.
            version_output: Native writer used for version output.
        """
        self._application = typer.Typer(
            name=name,
            help=description,
            add_completion=False,
            no_args_is_help=True,
        )
        self._configure_root(version, version_output)

    def register_command(
        self,
        name: str,
        invoke: Callable[[dict[str, object]], None],
        parameters: Sequence[_CommandParameter],
        *,
        description: str | None,
    ) -> None:
        """Register one callback with parser-only parameter metadata.

        Args:
            name: Command name displayed by the CLI.
            invoke: Callback that dispatches parsed values to Console.
            parameters: Explicit positional and option declarations.
            description: Optional help text displayed for the command.
        """

        def callback(**values: object) -> None:
            """Forward parsed values to native command execution.

            The native Console owns all command lifecycle behavior.
            """
            invoke(values)

        click_parameters: list[Parameter] = []
        for parameter, metadata in parameters:
            annotation = parameter.annotation
            if isinstance(metadata, Argument):
                typer_metadata = typer.Argument(
                    ...,
                    help=metadata.description,
                    metavar=metadata.metavar,
                )
            else:
                typer_metadata = typer.Option(
                    ...,
                    *metadata.names,
                    help=metadata.description,
                )
            click_parameters.append(
                parameter.replace(
                    annotation=Annotated[annotation, typer_metadata],
                )
            )

        signature = Signature(click_parameters, return_annotation=None)
        callback.__dict__["__signature__"] = signature
        callback.__annotations__ = {
            parameter.name: parameter.annotation
            for parameter in click_parameters
        }
        callback.__annotations__["return"] = None
        callback.__name__ = name.replace(":", "_").replace("-", "_")
        self._application.command(name=name, help=description)(callback)

    def add_group(
        self,
        name: str,
        child: TyperBridge,
        *,
        description: str | None,
    ) -> None:
        """Mount a child parser as a nested command group.

        Args:
            name: Group name used in the command path.
            child: Parser owned by a child Console instance.
            description: Optional group description.
        """
        self._application.add_typer(
            child._application,
            name=name,
            help=description,
        )

    def run(self) -> None:
        """Run the parser against the current process arguments.

        Typer owns terminal parsing and exit behavior.
        """
        self._application()

    def exit(self, code: int) -> None:
        """Stop command dispatch with one process status.

        The status has already been checked by the native exception.
        """
        raise typer.Exit(code=code)

    def invoke(
        self,
        arguments: Sequence[str],
        *,
        stdin: str | None = None,
    ) -> tuple[int, str, str]:
        """Run the parser with captured streams for native tests.

        Args:
            arguments: CLI argument vector, excluding the executable name.
            stdin: Optional standard input supplied to prompts.

        Returns:
            Exit status, standard output, and standard error.
        """
        result = CliRunner().invoke(
            self._application,
            list(arguments),
            input=stdin,
            color=False,
        )
        return result.exit_code, result.stdout, result.stderr

    def _configure_root(
        self,
        version: str | None,
        version_output: Callable[[str], None],
    ) -> None:
        """Add a root callback and optional eager version flag.

        The callback preserves group parsing when one command is registered.
        """
        if version is None:

            def empty_root() -> None:
                """Keep command execution under a stable root group.

                No application work runs in this parser callback.
                """

            self._application.callback(invoke_without_command=True)(empty_root)
            return

        def version_root(
            show_version: bool = typer.Option(
                False,
                "--version",
                is_eager=True,
                help="Show the installed Titanspan version and exit.",
            ),
        ) -> None:
            """Display package metadata when the eager flag is selected.

            Typer stops normal dispatch after the version is written.
            """
            if show_version:
                version_output(f"Titanspan {version}")
                raise typer.Exit

        self._application.callback(invoke_without_command=True)(version_root)

    _application: typer.Typer


__all__ = ["TyperBridge"]
