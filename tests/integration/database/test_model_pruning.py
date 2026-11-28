"""Verify bounded model pruning through real Database sessions.

Pruning tests cover ordinary lifecycle deletion, mass deletion, and pretend
queries against temporary SQLite databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabasePruningError,
    DatabaseServiceProvider,
    Model,
    ModelQueryBuilder,
    Schema,
    SoftDeletes,
)
from titanspan.database.events import ModelDeleting
from titanspan.facades.database import DB
from titanspan.facades.event import Event
from titanspan.foundation import Application

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_PRUNED_NAMES: list[str] = []
_EXPECTED_PRUNED_COUNT = 5
_EXPECTED_REMAINING_COUNT = 2
_EXPECTED_MASS_PRUNED_COUNT = 3
_EXPECTED_SOURCE_RECORD_COUNT = 7
_EXPECTED_SOFT_PRUNED_COUNT = 2
_EXPECTED_SOFT_REMAINING_COUNT = 1
_EXPECTED_SYNC_PRUNED_COUNT = 2
_EXPECTED_SYNC_MASS_PRUNED_COUNT = 2
_EXPECTED_MASS_SOURCE_COUNT = 4


class PrunableRecord(Model):
    """Represent rows that opt into per-model pruning behavior.

    The pruning hook records which model instances use ordinary deletion.
    """

    table = "prunable_records"
    name: Mapped[str] = mapped_column(String(80))
    expired: Mapped[bool]

    def prunable(
        self: PrunableRecord,
    ) -> ModelQueryBuilder[PrunableRecord]:
        """Return rows selected by the application's pruning policy.

        Returns:
            A query containing only expired records.
        """
        return PrunableRecord.query().where("expired", True)

    def pruning(self) -> None:
        """Record that the per-model hook ran before hard deletion.

        The test checks hook execution independently from row removal.
        """
        _PRUNED_NAMES.append(self.name)


class MassPrunableRecord(Model):
    """Represent rows selected for event-free set-based pruning.

    Mass pruning bypasses the ordinary instance hook by design.
    """

    table = "mass_prunable_records"
    name: Mapped[str] = mapped_column(String(80))
    expired: Mapped[bool]

    def prunable(
        self: MassPrunableRecord,
    ) -> ModelQueryBuilder[MassPrunableRecord]:
        """Return rows selected by the application's mass-pruning policy.

        Returns:
            A query containing only expired records.
        """
        return MassPrunableRecord.query().where("expired", True)


class SoftPrunableRecord(SoftDeletes, Model):
    """Represent soft-deletable records that pruning removes permanently.

    The tests verify that active and already-deleted rows are hard-deleted.
    """

    table = "soft_prunable_records"
    expired: Mapped[bool]

    def prunable(
        self: SoftPrunableRecord,
    ) -> ModelQueryBuilder[SoftPrunableRecord]:
        """Return expired records, including soft-deleted rows at execution.

        Returns:
            A query containing only expired records.
        """
        return SoftPrunableRecord.query().where("expired", True)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with a temporary SQLite connection.

    Args:
        tmp_path: Isolated application directory created by pytest.

    Returns:
        An unopened application with the native Database provider.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/pruning.sqlite",
                    },
                },
            },
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_prune_all_batches_hooks_and_pretend_are_side_effect_free(
    application: Application,
) -> None:
    """Prune only selected models and exercise the pretend count.

    Args:
        application: Application configured by the test fixture.
    """
    _PRUNED_NAMES.clear()
    async with application:
        async with Schema.create("prunable_records") as table:
            table.id()
            table.string("name", length=80)
            table.boolean("expired")
            table.timestamps()

        await (
            PrunableRecord.factory()
            .count(7)
            .sequence(
                {"name": "expired-0", "expired": True},
                {"name": "active", "expired": False},
                {"name": "expired-2", "expired": True},
                {"name": "expired-3", "expired": True},
                {"name": "active", "expired": False},
                {"name": "expired-5", "expired": True},
                {"name": "expired-6", "expired": True},
            )
            .create_async()
        )

        pretend_count = await PrunableRecord.prune_all_async(
            chunk_size=2,
            pretend=True,
        )
        assert pretend_count == _EXPECTED_PRUNED_COUNT
        assert (
            await DB.table("prunable_records").count_async()
            == _EXPECTED_SOURCE_RECORD_COUNT
        )
        assert not _PRUNED_NAMES

        pruned_count = await PrunableRecord.prune_all_async(chunk_size=2)

        assert pruned_count == _EXPECTED_PRUNED_COUNT
        assert await DB.table("prunable_records").count_async() == (
            _EXPECTED_REMAINING_COUNT
        )
        assert _PRUNED_NAMES == [
            "expired-0",
            "expired-2",
            "expired-3",
            "expired-5",
            "expired-6",
        ]
        assert await PrunableRecord.prune_all_async(chunk_size=2) == 0


async def test_mass_prune_is_bounded_and_skips_model_hooks(
    application: Application,
) -> None:
    """Delete selected models in bounded statements without hydration hooks.

    Args:
        application: Application configured by the test fixture.
    """
    _PRUNED_NAMES.clear()
    async with application:
        async with Schema.create("mass_prunable_records") as table:
            table.id()
            table.string("name", length=80)
            table.boolean("expired")
            table.timestamps()

        await (
            MassPrunableRecord.factory()
            .count(4)
            .sequence(
                {"name": "expired-0", "expired": True},
                {"name": "active", "expired": False},
                {"name": "expired-2", "expired": True},
                {"name": "expired-3", "expired": True},
            )
            .create_async()
        )

        pruned_count = await MassPrunableRecord.mass_prune_all_async(
            chunk_size=2,
            pretend=True,
        )

        assert pruned_count == _EXPECTED_MASS_PRUNED_COUNT
        assert (
            await DB.table("mass_prunable_records").count_async()
            == _EXPECTED_MASS_SOURCE_COUNT
        )
        pruned_count = await MassPrunableRecord.mass_prune_all_async(
            chunk_size=2,
        )

        assert pruned_count == _EXPECTED_MASS_PRUNED_COUNT
        assert await DB.table("mass_prunable_records").count_async() == 1
        assert await MassPrunableRecord.mass_prune_all_async() == 0
        assert not _PRUNED_NAMES


async def test_sync_pruning_uses_the_thread_owned_database_service(
    application: Application,
) -> None:
    """Run both pruning modes on the synchronous connection owner.

    Args:
        application: Application configured by the test fixture.
    """
    _PRUNED_NAMES.clear()
    async with application:
        async with Schema.create("prunable_records") as table:
            table.id()
            table.string("name", length=80)
            table.boolean("expired")
            table.timestamps()
        async with Schema.create("mass_prunable_records") as table:
            table.id()
            table.string("name", length=80)
            table.boolean("expired")
            table.timestamps()

        await PrunableRecord.factory().create_many_async(
            2,
            {"name": "Generated", "expired": True},
        )
        await MassPrunableRecord.factory().create_many_async(
            2,
            {"name": "Generated", "expired": True},
        )

        pretend_count = await anyio.to_thread.run_sync(
            lambda: PrunableRecord.prune_all(chunk_size=1, pretend=True),
        )
        assert pretend_count == _EXPECTED_SYNC_PRUNED_COUNT
        mass_pretend_count = await anyio.to_thread.run_sync(
            lambda: MassPrunableRecord.mass_prune_all(
                chunk_size=1,
                pretend=True,
            ),
        )
        assert mass_pretend_count == _EXPECTED_SYNC_MASS_PRUNED_COUNT
        assert not _PRUNED_NAMES
        pruned_count = await anyio.to_thread.run_sync(
            lambda: PrunableRecord.prune_all(chunk_size=1),
        )
        mass_pruned_count = await anyio.to_thread.run_sync(
            lambda: MassPrunableRecord.mass_prune_all(chunk_size=1),
        )

        assert pruned_count == _EXPECTED_SYNC_PRUNED_COUNT
        assert mass_pruned_count == _EXPECTED_SYNC_MASS_PRUNED_COUNT
        assert _PRUNED_NAMES == ["Generated", "Generated"]
        assert await anyio.to_thread.run_sync(PrunableRecord.prune_all) == 0
        assert (
            await anyio.to_thread.run_sync(
                MassPrunableRecord.mass_prune_all,
            )
            == 0
        )
        assert await DB.table("prunable_records").count_async() == 0
        assert await DB.table("mass_prunable_records").count_async() == 0


async def test_prune_hard_deletes_selected_soft_deleted_models(
    application: Application,
) -> None:
    """Include soft-deleted rows and remove them permanently when selected.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        async with Schema.create("soft_prunable_records") as table:
            table.id()
            table.boolean("expired")
            table.soft_deletes()
            table.timestamps()

        active = await SoftPrunableRecord.factory().create_async(
            {"expired": True},
        )
        already_deleted = await SoftPrunableRecord.factory().create_async(
            {"expired": True},
        )
        await SoftPrunableRecord.factory().create_async({"expired": False})
        assert await already_deleted.delete_async()

        model_pruned_count = await SoftPrunableRecord.prune_all_async(
            chunk_size=1,
        )

        assert model_pruned_count == _EXPECTED_SOFT_PRUNED_COUNT
        assert await DB.table("soft_prunable_records").count_async() == (
            _EXPECTED_SOFT_REMAINING_COUNT
        )

        active = await SoftPrunableRecord.factory().create_async(
            {"expired": True},
        )
        already_deleted = await SoftPrunableRecord.factory().create_async(
            {"expired": True},
        )
        assert await already_deleted.delete_async()
        assert not await anyio.to_thread.run_sync(already_deleted.delete)

        pruned_count = await SoftPrunableRecord.mass_prune_all_async(
            chunk_size=1,
        )

        assert pruned_count == _EXPECTED_SOFT_PRUNED_COUNT
        assert (
            await DB.table("soft_prunable_records").count_async()
            == _EXPECTED_SOFT_REMAINING_COUNT
        )
        assert (
            not await DB.table("soft_prunable_records")
            .where(
                "id",
                active.id,
            )
            .exists_async()
        )
        sync_active = await SoftPrunableRecord.factory().create_async(
            {"expired": True},
        )
        sync_pruned_count = await anyio.to_thread.run_sync(
            SoftPrunableRecord.prune_all,
        )
        assert sync_pruned_count == 1
        assert (
            not await DB.table("soft_prunable_records")
            .where("id", sync_active.id)
            .exists_async()
        )


async def test_cancelled_model_delete_is_not_counted_as_pruned(
    application: Application,
) -> None:
    """Count only models whose lifecycle accepts deletion.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        async with Schema.create("prunable_records") as table:
            table.id()
            table.string("name", length=80)
            table.boolean("expired")
            table.timestamps()
        await PrunableRecord.factory().create_async(
            {"name": "cancelled", "expired": True},
        )

        def cancel_deletion(event: ModelDeleting[PrunableRecord]) -> None:
            """Reject deletion before its SQL statement executes.

            Args:
                event: Pending model deletion event.
            """
            event.cancel()

        with Event.listen(ModelDeleting, cancel_deletion):
            pruned_count = await PrunableRecord.prune_all_async()
            sync_pruned_count = await anyio.to_thread.run_sync(
                PrunableRecord.prune_all,
            )

        assert pruned_count == 0
        assert sync_pruned_count == 0
        assert await DB.table("prunable_records").count_async() == 1


async def test_base_model_pruning_requires_an_explicit_policy(
    application: Application,
) -> None:
    """Refuse to prune a model without an application query policy.

    Args:
        application: Application configured by the test fixture.
    """
    async with application:
        with pytest.raises(DatabasePruningError, match="chunk size"):
            await Model.prune_all_async(chunk_size=0)
        with pytest.raises(DatabasePruningError, match="chunk size"):
            await Model.prune_all_async(chunk_size=True)
        with pytest.raises(DatabasePruningError, match="prunable"):
            await Model.prune_all_async()
