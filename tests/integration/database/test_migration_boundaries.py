"""Exercise migration lifecycle and command safety boundaries.
"""  # fmt: skip

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import anyio
import pytest

from titanspan.console import Console
from titanspan.console.testing import ConsoleTester
from titanspan.database import (
    DatabaseMigrationError,
    DatabaseServiceProvider,
    MigrationManager,
    Schema,
)
from titanspan.database.commands import register_database_commands
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

    from titanspan.contracts.foundation import ServiceProvider

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXPECTED_BRANCH_COUNT = 2


@pytest.fixture
def migration_application(tmp_path: Path) -> Application:
    """Create a fresh application with a file-backed SQLite connection.

    Args:
        tmp_path: Pytest-owned application root and disposable database path.

    Returns:
        An application configured with only the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "app": {"env": "testing"},
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/migration-boundaries.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_rollback_rejects_nonpositive_steps_before_database_io(
    migration_application: Application,
) -> None:
    """Reject invalid rollback counts in sync and async manager APIs.

    Args:
        migration_application: Disposable SQLite-backed application.
    """
    async with migration_application:
        manager = await migration_application.container.make_async(
            MigrationManager,
        )

        with pytest.raises(
            DatabaseMigrationError,
            match="steps must be positive",
        ):
            await anyio.to_thread.run_sync(manager.rollback, 0)

        with pytest.raises(
            DatabaseMigrationError,
            match="steps must be positive",
        ):
            await manager.rollback_async(-1)


async def test_install_refresh_and_reset_keep_revision_state_coherent(
    migration_application: Application,
) -> None:
    """Round-trip one revision through public sync and async APIs.

    Args:
        migration_application: Disposable SQLite-backed application.
    """
    async with migration_application:
        manager = await migration_application.container.make_async(
            MigrationManager,
        )

        await manager.install_async()
        await anyio.to_thread.run_sync(manager.install)
        assert await Schema.has_table_async("alembic_version")

        await manager.create_revision_async("migration lifecycle")
        await manager.upgrade_async()
        assert (await manager.status_async())[0].applied

        await anyio.to_thread.run_sync(manager.rollback, 1)
        assert not (await manager.status_async())[0].applied

        await manager.upgrade_async()
        await manager.refresh_async()
        assert (await manager.status_async())[0].applied

        await anyio.to_thread.run_sync(manager.refresh)
        assert (await manager.status_async())[0].applied

        await manager.reset_async()
        assert not (await manager.status_async())[0].applied

        await anyio.to_thread.run_sync(manager.reset)
        assert not (await manager.status_async())[0].applied


async def test_status_tracks_multiple_applied_revision_heads(
    migration_application: Application,
) -> None:
    """Report both independent Alembic heads before and after application.

    Args:
        migration_application: Disposable SQLite-backed application.
    """
    async with migration_application:
        manager = await migration_application.container.make_async(
            MigrationManager,
        )
        first_path = await manager.create_revision_async("first branch")
        second_path = await manager.create_revision_async("second branch")
        parent_revision = _revision_identifier(first_path)

        second_source = second_path.read_text(encoding="utf-8")
        parent_declaration = (
            f"down_revision: str | Sequence[str] | None = {parent_revision!r}"
        )
        independent_declaration = (
            "down_revision: str | Sequence[str] | None = None"
        )
        assert parent_declaration in second_source
        second_path.write_text(
            second_source.replace(parent_declaration, independent_declaration),
            encoding="utf-8",
        )

        pending = await manager.status_async()
        assert len(pending) == _EXPECTED_BRANCH_COUNT
        assert {item.current_head for item in pending} == {False}
        assert {item.applied for item in pending} == {False}

        await manager.upgrade_async()
        applied = await manager.status_async()
        assert len(applied) == _EXPECTED_BRANCH_COUNT
        assert {item.current_head for item in applied} == {True}
        assert {item.applied for item in applied} == {True}


def test_console_reports_migration_argument_and_lock_failures(
    tmp_path: Path,
) -> None:
    """Keep invalid migration commands from mutating the test database.

    Args:
        tmp_path: Isolated application root used by Console invocations.
    """

    def application_factory(provider: ServiceProvider) -> Application:
        """Build a fresh application for one Console invocation.

        Args:
            provider: Console-owned provider for output and command services.

        Returns:
            A test application with an isolated SQLite database file.
        """
        return (
            Application.builder()
            .with_base_path(tmp_path)
            .with_config(
                {
                    "app": {"env": "testing"},
                    "database": {
                        "default": "sqlite",
                        "connections": {
                            "sqlite": {
                                "driver": "sqlite",
                                "database": "database/command.sqlite",
                            },
                        },
                    },
                },
            )
            .with_service_provider(DatabaseServiceProvider())
            .with_service_provider(provider)
            .build()
        )

    console = Console(application_factory=application_factory)
    register_database_commands(console)
    tester = ConsoleTester(console)

    rollback = tester.invoke(
        ["migrate:rollback", "--step", "0", "--force"],
    )
    assert rollback.exit_code == 1
    assert "steps must be positive" in rollback.stderr

    isolated = tester.invoke(["migrate:install", "--isolated"])
    assert isolated.exit_code == 1
    assert "require PostgreSQL or MySQL" in isolated.stderr


def _revision_identifier(path: Path) -> str:
    """Read an Alembic revision literal without importing generated code.

    Args:
        path: Generated migration file produced by Alembic.

    Returns:
        Its literal revision identifier.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for statement in tree.body:
        if not isinstance(statement, ast.AnnAssign):
            continue
        if not isinstance(statement.target, ast.Name):
            continue
        if statement.target.id != "revision" or statement.value is None:
            continue
        value = ast.literal_eval(statement.value)
        if isinstance(value, str):
            return value
    message = "Generated migration has no revision identifier."
    raise AssertionError(message)
