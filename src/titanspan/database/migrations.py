"""Expose native migration methods through Alembic Operations.

Alembic owns revision discovery, dependency graphs, version state, and DDL
execution. This module adapts Schema blueprints to Alembic's active context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from alembic import op
from alembic.operations import Operations

from titanspan.database.schema import use_migration_operations

type MigrationDirection = Literal["up", "down"]


class Migration(ABC):
    """Declare one reversible schema revision using native Schema helpers.

    Subclasses implement both operations for revision execution.
    """

    @abstractmethod
    def up(self) -> None:
        """Apply this revision's schema changes.

        Raises:
            NotImplementedError: If a concrete migration omits this method.
        """
        raise NotImplementedError

    @abstractmethod
    def down(self) -> None:
        """Reverse this revision's schema changes.

        Raises:
            NotImplementedError: If a concrete migration omits this method.
        """
        raise NotImplementedError


def run_migration(
    migration: Migration,
    direction: MigrationDirection,
) -> None:
    """Run one native migration inside Alembic's current revision context.

    Args:
        migration: Concrete schema migration implementation.
        direction: Whether Alembic is applying or reversing the revision.
    """
    operations = Operations(op.get_context())
    with use_migration_operations(operations):
        if direction == "up":
            migration.up()
        else:
            migration.down()


__all__ = ["Migration", "MigrationDirection", "run_migration"]
