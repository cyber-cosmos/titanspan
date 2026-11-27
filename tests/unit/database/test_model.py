"""Verify native model naming and mass-assignment policy boundaries.

These tests exercise SQLAlchemy's real instrumentation without opening a DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

# SQLAlchemy evaluates mapped declarations during class construction.
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from titanspan.database import (
    DatabaseQueryError,
    MassAssignmentError,
    Model,
)

if TYPE_CHECKING:
    from sqlalchemy import Table

pytestmark = pytest.mark.unit


class StrictRecord(Model):
    """Represent a strict model used to verify column assignment policy.

    The guarded field must be rejected by strict mass assignment.
    """

    table = "strict_records"
    fillable = ("name",)
    strict_mass_assignment = True
    timestamps = False

    name: Mapped[str]
    is_admin: Mapped[bool]


class GeneratedRecord(Model):
    """Represent a model whose table name follows Python conventions.

    Its inferred table name is derived from the class name.
    """

    timestamps = False

    title: Mapped[str]


class CompositeRecord(Model):
    """Represent a mapped model with an unsupported compound identity.

    Query convenience methods require one deterministic identifier column.
    """

    table = "composite_records"
    timestamps = False

    part_a: Mapped[int] = mapped_column(primary_key=True)
    part_b: Mapped[int] = mapped_column(primary_key=True)


def test_model_table_names_follow_stable_python_conventions() -> None:
    """Infer plural snake-case names and preserve explicit table overrides.

    These names provide stable defaults while allowing explicit overrides.
    """
    assert GeneratedRecord.__tablename__ == "generated_records"
    assert StrictRecord.__tablename__ == "strict_records"


def test_primary_key_name_reports_query_capability_error() -> None:
    """Reject compound identities with the database query error category.

    The model's key shape is valid SQLAlchemy but unsupported by this helper.
    """
    with pytest.raises(DatabaseQueryError, match="single-column"):
        CompositeRecord.primary_key_name()


def test_composite_model_metadata_compiles_for_sqlite() -> None:
    """Avoid autoincrement on an inherited composite primary key.

    Alembic inspects every mapped table during autogeneration. SQLite rejects
    an auto-increment declaration on a composite primary key.
    """
    table = cast("Table", CompositeRecord.__table__)
    CreateTable(table).compile(dialect=sqlite_dialect())


def test_fill_rejects_disallowed_columns_without_assigning_them() -> None:
    """Strict mass assignment reports guarded values before persistence.

    Allowed attributes remain assigned when another value is rejected.
    """
    record = StrictRecord()

    with pytest.raises(MassAssignmentError, match="is_admin"):
        record.fill({"name": "Ada", "is_admin": True})

    assert record.name == "Ada"
    assert record.is_admin is None


def test_unguarded_scope_restores_after_errors_and_force_fill_is_explicit() -> (
    None
):
    """Limit temporary unguarded behavior to its context and task.

    Explicit force filling still rejects unmapped attribute names.
    """
    record = StrictRecord()
    with StrictRecord.unguarded():
        record.fill({"is_admin": True})

    assert record.is_admin is True

    with pytest.raises(MassAssignmentError):
        record.force_fill({"unmapped": True})
