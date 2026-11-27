"""Verify database-backed Validation rules use safe bound Core queries.

The tests combine real SQLite storage with the native Validation service.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from titanspan.contracts.validation import ValidationService
from titanspan.database import (
    DatabaseServiceProvider,
    Model,
    exists_rule,
    unique_rule,
)
from titanspan.facades.database import DB
from titanspan.foundation import Application
from titanspan.validation import ValidationException, ValidationServiceProvider

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
_EXISTING_EMAIL = "ada@example.test"
_EXISTING_STATE = "active"
_OTHER_STATE = "archived"


class ValidationContact(Model):
    """Represent a record used by Database validation integration tests.

    Its named connection checks model-based table and connection discovery.
    """

    table = "validation_contacts"
    connection = "analytics"
    fillable = ("email", "state")

    email: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(32))


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """Create an application with isolated default and named databases.

    Args:
        tmp_path: Temporary root for both SQLite database files.

    Returns:
        A lazy Application with Database and Validation providers.
    """
    return Application(
        base_path=tmp_path,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": "database/default.sqlite",
                    },
                    "analytics": {
                        "driver": "sqlite",
                        "database": "database/analytics.sqlite",
                    },
                },
            },
        },
        service_providers=(
            DatabaseServiceProvider(),
            ValidationServiceProvider(),
        ),
    )


async def test_unique_and_exists_rules_use_application_validation(
    application: Application,
) -> None:
    """Check duplicates, trusted ignores, scopes, and existing records.

    Args:
        application: App owning the two temporary database connections.
    """
    async with application:
        await DB.connection("analytics").statement_async(
            "CREATE TABLE validation_contacts ("
            "id INTEGER PRIMARY KEY, email VARCHAR(120) NOT NULL, "
            "state VARCHAR(32) NOT NULL)"
        )
        await DB.connection("analytics").statement_async(
            "INSERT INTO validation_contacts (id, email, state) "
            "VALUES (1, :email, :state)",
            {"email": _EXISTING_EMAIL, "state": _EXISTING_STATE},
        )
        validator = await application.container.make_async(ValidationService)

        duplicate = unique_rule(
            ValidationContact,
            "email",
            field="email",
            constraints={"state": _EXISTING_STATE},
        )
        with pytest.raises(ValidationException) as duplicate_error:
            await validator.apply_rules_async(
                {"email": _EXISTING_EMAIL},
                async_rules=(duplicate,),
                messages={"unique": "Email is unavailable."},
            )
        assert duplicate_error.value.issues[0].code == "unique"
        assert (
            duplicate_error.value.issues[0].message == "Email is unavailable."
        )

        update_rule = unique_rule(
            ValidationContact,
            "email",
            field="email",
            ignore=("id", 1),
        )
        assert await validator.apply_rules_async(
            {"email": _EXISTING_EMAIL},
            async_rules=(update_rule,),
        ) == {"email": _EXISTING_EMAIL}

        scoped_rule = unique_rule(
            ValidationContact,
            "email",
            field="email",
            constraints={"state": _OTHER_STATE},
        )
        assert await validator.apply_rules_async(
            {"email": _EXISTING_EMAIL},
            async_rules=(scoped_rule,),
        ) == {"email": _EXISTING_EMAIL}

        injection_value = {"email": "x' OR 1=1 --"}
        assert (
            await validator.apply_rules_async(
                injection_value,
                async_rules=(
                    unique_rule(
                        ValidationContact,
                        "email",
                        field="email",
                    ),
                ),
            )
            == injection_value
        )

        existing_rule = exists_rule(
            ValidationContact,
            "email",
            field="email",
        )
        assert await validator.apply_rules_async(
            {"email": _EXISTING_EMAIL},
            async_rules=(existing_rule,),
        ) == {"email": _EXISTING_EMAIL}

        with pytest.raises(ValidationException) as missing_error:
            await validator.apply_rules_async(
                {"email": "missing@example.test"},
                async_rules=(existing_rule,),
            )
        assert missing_error.value.issues[0].code == "exists"


async def test_database_rules_support_nested_values_and_optional_fields(
    application: Application,
) -> None:
    """Support dotted mapping fields and typed object attributes.

    Args:
        application: App owning the named SQLite connection.
    """
    async with application:
        await DB.connection("analytics").statement_async(
            "CREATE TABLE validation_contacts ("
            "id INTEGER PRIMARY KEY, email VARCHAR(120) NOT NULL, "
            "state VARCHAR(32) NOT NULL)"
        )
        await DB.connection("analytics").statement_async(
            "INSERT INTO validation_contacts (id, email, state) "
            "VALUES (1, :email, :state)",
            {"email": _EXISTING_EMAIL, "state": _EXISTING_STATE},
        )
        validator = await application.container.make_async(ValidationService)
        nested_rule = exists_rule(
            "validation_contacts",
            "email",
            field="contact.email",
            connection="analytics",
            constraints={"state": _EXISTING_STATE},
        )

        nested = {"contact": {"email": _EXISTING_EMAIL}}
        assert (
            await validator.apply_rules_async(
                nested,
                async_rules=(nested_rule,),
            )
            == nested
        )
        assert await validator.apply_rules_async(
            SimpleNamespace(email=_EXISTING_EMAIL),
            async_rules=(
                exists_rule(
                    ValidationContact,
                    "email",
                    field="email",
                ),
            ),
        ) == SimpleNamespace(email=_EXISTING_EMAIL)

        optional_rule = exists_rule(
            "unavailable_table",
            "email",
            field="email",
        )
        optional = {"email": None}
        assert (
            await validator.apply_rules_async(
                optional,
                async_rules=(optional_rule,),
            )
            == optional
        )


def test_database_rule_factories_reject_unsafe_identifiers() -> None:
    """Reject executable table, column, and field path fragments.

    Identifiers are trusted configuration, while values remain bound data.
    """
    with pytest.raises(ValueError, match="identifiers must be safe"):
        exists_rule(
            "validation_contacts; DROP TABLE users",
            "email",
            field="email",
        )
    with pytest.raises(ValueError, match="identifiers must be safe"):
        unique_rule(
            "validation_contacts",
            "email; DROP TABLE users",
            field="email",
        )
    with pytest.raises(ValueError, match="field path"):
        exists_rule("validation_contacts", "email", field="contact..email")
