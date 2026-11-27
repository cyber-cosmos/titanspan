"""Register native Queue worker and generation commands through Console.
"""  # fmt: skip

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from titanspan.console import (
    Argument,
    ArtifactKind,
    CommandGenerationError,
    ConsoleExitError,
    Option,
    generate_artifact,
)
from titanspan.contracts.console import ConsoleOutput  # noqa: TC001
from titanspan.contracts.foundation import ApplicationPaths  # noqa: TC001
from titanspan.queue.manager import QueueManager  # noqa: TC001

if TYPE_CHECKING:
    from titanspan.contracts.console import CommandRegistrar


def register_queue_commands(registrar: CommandRegistrar) -> None:
    """Register supported worker and job-generation commands.

    Args:
        registrar: Canonical Console command registrar.
    """

    async def work(
        manager: QueueManager,
        output: ConsoleOutput,
        connection: Annotated[
            str | None,
            Option("--connection", description="Configured connection."),
        ] = None,
        queue: Annotated[
            str | None,
            Option("--queue", description="Logical queue to consume."),
        ] = None,
        concurrency: Annotated[
            int | None,
            Option("--concurrency", description="Maximum active jobs."),
        ] = None,
        prefetch: Annotated[
            int | None,
            Option("--prefetch", description="Additional messages to fetch."),
        ] = None,
    ) -> None:
        """Run a bounded Taskiq worker until shutdown or cancellation.

        Args:
            manager: Canonical application-owned Queue manager.
            output: Native plain-text Console output service.
            connection: Optional configured transport connection.
            queue: Optional logical queue name.
            concurrency: Optional active handler limit.
            prefetch: Optional additional backend message limit.
        """
        output.write("Queue worker started. Press Ctrl+C to stop.")
        await manager.work_async(
            connection=connection,
            queue=queue,
            concurrency=concurrency,
            prefetch=prefetch,
        )

    async def listen(
        manager: QueueManager,
        output: ConsoleOutput,
        connection: Annotated[
            str | None,
            Option("--connection", description="Configured connection."),
        ] = None,
        queue: Annotated[
            str | None,
            Option("--queue", description="Logical queue to consume."),
        ] = None,
    ) -> None:
        """Run one concurrent consumer through Taskiq's worker lifecycle.

        Args:
            manager: Canonical application-owned Queue manager.
            output: Native plain-text Console output service.
            connection: Optional configured transport connection.
            queue: Optional logical queue name.
        """
        output.write("Queue listener started. Press Ctrl+C to stop.")
        await manager.work_async(
            connection=connection,
            queue=queue,
            concurrency=1,
        )

    def make_job(
        name: Annotated[str, Argument(description="Job class name.")],
        paths: ApplicationPaths,
        output: ConsoleOutput,
    ) -> None:
        """Generate a typed Queue job beneath the active application root.

        Args:
            name: Class name or trusted dotted application module path.
            paths: Effective application paths supplied by Foundation.
            output: Native output service used for safe status text.
        """
        _generate("job", name, paths, output)

    def make_job_middleware(
        name: Annotated[str, Argument(description="Middleware class name.")],
        paths: ApplicationPaths,
        output: ConsoleOutput,
    ) -> None:
        """Generate typed asynchronous job middleware.

        Args:
            name: Class name or trusted dotted application module path.
            paths: Effective application paths supplied by Foundation.
            output: Native output service used for safe status text.
        """
        _generate("job_middleware", name, paths, output)

    registrar.register_command(
        "queue:work",
        work,
        description="Run a bounded asynchronous Queue worker.",
    )
    registrar.register_command(
        "queue:listen",
        listen,
        description="Run one asynchronous Queue consumer.",
    )
    registrar.register_command(
        "make:job",
        make_job,
        description="Generate a typed Queue job.",
    )
    registrar.register_command(
        "make:job-middleware",
        make_job_middleware,
        description="Generate typed job middleware.",
    )


def _generate(
    kind: ArtifactKind,
    name: str,
    paths: ApplicationPaths,
    output: ConsoleOutput,
) -> None:
    """Generate one artifact and report a safe application-relative path.

    Args:
        kind: Queue artifact kind selected by the command.
        name: Validated artifact name supplied by the caller.
        paths: Effective application path boundary.
        output: Native terminal output contract.

    Raises:
        ConsoleExitError: If the artifact name or destination is invalid.
    """
    try:
        target = generate_artifact(paths, kind, name)
    except CommandGenerationError as error:
        output.write_error(str(error))
        raise ConsoleExitError(1) from error
    output.write(f"Generated {target.relative_to(paths.base_path)}.")


__all__ = ["register_queue_commands"]
