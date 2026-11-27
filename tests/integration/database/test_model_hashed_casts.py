"""Verify model hashed casts use the application-owned Hashing service.

The tests persist real mapped records through the Database and Hashing
components together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import anyio
import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.database import (
    DatabaseQueryError,
    DatabaseServiceProvider,
    Model,
)
from titanspan.facades.database import DB
from titanspan.facades.hash import Hash
from titanspan.foundation import Application

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_INITIAL_CREDENTIAL = "correct horse battery staple"
_UPDATED_CREDENTIAL = "another correct password"


class HashedAccount(Model):
    """Represent an account whose credential is hashed before persistence.
    """  # fmt: skip

    table = "hashed_accounts"
    fillable = ("email", "password")
    hidden = ("password",)
    casts: ClassVar[Mapping[str, str]] = {"password": "hashed"}

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password: Mapped[str] = mapped_column(String(255))


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with isolated SQLite and Bcrypt services.

    Args:
        tmp_path: Temporary application root managed by Pytest.

    Returns:
        An unopened application with Database and Hashing providers.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/hashed_casts.sqlite",
                    },
                },
            },
            "hashing": {"driver": "bcrypt"},
        },
        service_providers=(DatabaseServiceProvider(),),
    )


async def test_async_hashed_cast_hashes_once_and_upserts_safely(
    application: Application,
) -> None:
    """Hash create and update values through async ORM persistence.

    Args:
        application: Isolated application configured with real Hashing.
    """
    async with application:
        await _create_schema()
        account = await HashedAccount.create_async(
            {"email": "ada@example.test", "password": _INITIAL_CREDENTIAL},
        )

        first_hash = account.password
        assert first_hash != _INITIAL_CREDENTIAL
        assert await Hash.check_async(_INITIAL_CREDENTIAL, first_hash)
        assert "password" not in account.to_dict()

        await account.save_async()
        assert account.password == first_hash

        account.password = _UPDATED_CREDENTIAL
        await account.save_async()
        assert await Hash.check_async(
            _UPDATED_CREDENTIAL,
            account.password,
        )
        assert not await Hash.check_async(
            _INITIAL_CREDENTIAL,
            account.password,
        )

        affected = await HashedAccount.upsert_async(
            [
                {
                    "email": "grace@example.test",
                    "password": _INITIAL_CREDENTIAL,
                },
            ],
            unique_by=("email",),
        )
        inserted = (
            await HashedAccount.query()
            .where(
                "email",
                "grace@example.test",
            )
            .first_or_fail_async()
        )
        assert affected == 1
        assert await Hash.check_async(
            _INITIAL_CREDENTIAL,
            inserted.password,
        )


async def test_sync_hashed_cast_uses_sync_hashing_in_worker(
    application: Application,
) -> None:
    """Hash synchronous model writes through their owning worker thread.

    Args:
        application: Isolated application configured with real Hashing.
    """
    async with application:
        await _create_schema()
        encoded = await anyio.to_thread.run_sync(_create_sync_account)

        assert encoded != _INITIAL_CREDENTIAL
        assert await Hash.check_async(_INITIAL_CREDENTIAL, encoded)


async def test_hashed_cast_rejects_non_string_values(
    application: Application,
) -> None:
    """Reject invalid typed values before the database flushes them.

    Args:
        application: Isolated application configured with real Hashing.
    """
    async with application:
        await _create_schema()

        with pytest.raises(DatabaseQueryError, match="must be strings"):
            await HashedAccount.create_async(
                {"email": "invalid@example.test", "password": 42},
            )

        assert await HashedAccount.query().count_async() == 0


async def _create_schema() -> None:
    """Create a constrained account table for hash cast verification.
    """  # fmt: skip
    await DB.statement_async(
        "CREATE TABLE hashed_accounts ("
        "id INTEGER PRIMARY KEY, "
        "email VARCHAR(320) NOT NULL UNIQUE, "
        "password VARCHAR(255) NOT NULL, "
        "created_at TIMESTAMP, updated_at TIMESTAMP)"
    )


def _create_sync_account() -> str:
    """Persist one account through the synchronous model API.

    Returns:
        The encoded password stored by the model cast.
    """
    account = HashedAccount.create(
        {
            "email": "grace@example.test",
            "password": _INITIAL_CREDENTIAL,
        },
    )
    return account.password
