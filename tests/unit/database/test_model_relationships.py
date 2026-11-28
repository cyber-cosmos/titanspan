"""Verify safe boundaries for mapped pivot operations.

These tests exercise validation that does not require a database connection.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Table
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from titanspan.database import DatabaseQueryError, Model, belongs_to_many

pytestmark = pytest.mark.unit


class _PivotRelated(Model):
    """Represent the related side of a mapped pivot table.

    The model exists only to provide concrete SQLAlchemy primary-key metadata.
    """

    table = "unit_pivot_related"
    name: Mapped[str]


_UNLINKED_PIVOT_TABLE = Table(
    "unit_unlinked_pivot",
    Model.metadata,
    Column("parent_id", Integer, primary_key=True),
    Column("related_id", Integer, primary_key=True),
)
_PIVOT_TABLE_ALIAS = _UNLINKED_PIVOT_TABLE.alias(
    "unit_unlinked_pivot_alias",
)
_COMPOSITE_PIVOT_TABLE = Table(
    "unit_composite_pivot_links",
    Model.metadata,
    Column("parent_id", Integer, primary_key=True),
    Column("related_id", Integer, primary_key=True),
)
_TIMESTAMPED_PIVOT_TABLE = Table(
    "unit_timestamped_pivot_links",
    Model.metadata,
    Column(
        "parent_id",
        Integer,
        ForeignKey("unit_timestamped_pivot_parents.id"),
        primary_key=True,
    ),
    Column(
        "related_id",
        Integer,
        ForeignKey("unit_pivot_related.id"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)


class _UnlinkedPivotParent(Model):
    """Represent a parent with an explicitly joined, keyless association.

    This relation maps successfully but cannot identify its pivot rows safely.
    """

    table = "unit_unlinked_pivot_parents"
    name: Mapped[str]
    related: Mapped[list[_PivotRelated]] = relationship(
        _PivotRelated,
        secondary=_UNLINKED_PIVOT_TABLE,
        primaryjoin=lambda: _UnlinkedPivotParent.id
        == foreign(_UNLINKED_PIVOT_TABLE.c.parent_id),
        secondaryjoin=lambda: foreign(_UNLINKED_PIVOT_TABLE.c.related_id)
        == _PivotRelated.id,
    )


class _AliasedPivotParent(Model):
    """Represent a parent whose association is a SQLAlchemy table alias.

    An alias can load through SQLAlchemy but is outside direct pivot updates.
    """

    table = "unit_aliased_pivot_parents"
    name: Mapped[str]
    related: Mapped[list[_PivotRelated]] = relationship(
        _PivotRelated,
        secondary=_PIVOT_TABLE_ALIAS,
        primaryjoin=lambda: _AliasedPivotParent.id
        == foreign(_PIVOT_TABLE_ALIAS.c.parent_id),
        secondaryjoin=lambda: foreign(_PIVOT_TABLE_ALIAS.c.related_id)
        == _PivotRelated.id,
    )


class _CompositePivotParent(Model):
    """Represent a parent with a composite primary key.

    Pivot mutation currently supports only one primary-key column per model.
    """

    table = "unit_composite_pivot_parents"
    tenant_id: Mapped[int] = mapped_column(primary_key=True)
    related: Mapped[list[_PivotRelated]] = relationship(
        _PivotRelated,
        secondary=_COMPOSITE_PIVOT_TABLE,
        primaryjoin=lambda: _CompositePivotParent.id
        == foreign(_COMPOSITE_PIVOT_TABLE.c.parent_id),
        secondaryjoin=lambda: foreign(_COMPOSITE_PIVOT_TABLE.c.related_id)
        == _PivotRelated.id,
    )


class _TimestampedPivotParent(Model):
    """Represent a parent with validated timestamped pivot metadata.

    Tests mutate its public relationship info to cover runtime validation.
    """

    table = "unit_timestamped_pivot_parents"
    name: Mapped[str]
    related: Mapped[list[_PivotRelated]] = belongs_to_many(
        _PivotRelated,
        _TIMESTAMPED_PIVOT_TABLE,
        timestamps=("created_at", "updated_at"),
    )


def test_pivot_update_rejects_association_without_foreign_keys() -> None:
    """Reject a direct association that does not identify both models.

    Explicit ORM joins allow relationship loading, but pivot mutation needs
    unambiguous direct foreign keys to each model's primary key.
    """
    parent = _UnlinkedPivotParent(name="Parent")

    with pytest.raises(DatabaseQueryError, match="unambiguous"):
        parent.relation("related").update_existing_pivot(
            1,
            {"label": "featured"},
        )


def test_pivot_update_rejects_aliased_secondary_tables() -> None:
    """Reject association aliases that cannot be safely mutated as tables.

    The supported mutation path needs a concrete SQLAlchemy ``Table``.
    """
    parent = _AliasedPivotParent(name="Parent")

    with pytest.raises(DatabaseQueryError, match="unambiguous"):
        parent.relation("related").update_existing_pivot(
            1,
            {"label": "featured"},
        )


def test_pivot_update_rejects_composite_model_identifiers() -> None:
    """Reject composite identifiers before constructing pivot predicates.

    Many-to-many mutation requires one model primary-key column.
    """
    parent = _CompositePivotParent(tenant_id=1)

    with pytest.raises(DatabaseQueryError, match="single-column"):
        parent.relation("related").update_existing_pivot(
            1,
            {"label": "featured"},
        )


def test_pivot_timestamps_require_distinct_table_columns() -> None:
    """Reject timestamp settings that cannot describe stored pivot values.

    Timestamp configuration must identify two real, separate table columns.
    """
    with pytest.raises(ValueError, match="two distinct column names"):
        belongs_to_many(
            _PivotRelated,
            _UNLINKED_PIVOT_TABLE,
            timestamps=("created_at", "created_at"),
        )
    with pytest.raises(ValueError, match="SQLAlchemy Table"):
        belongs_to_many(
            _PivotRelated,
            _UNLINKED_PIVOT_TABLE,
            timestamps=("created_at", "updated_at"),
        )
    with pytest.raises(TypeError, match="SQLAlchemy Table"):
        belongs_to_many(
            _PivotRelated,
            _PIVOT_TABLE_ALIAS,
            timestamps=("created_at", "updated_at"),
        )


def test_pivot_timestamp_relationship_info_is_validated_at_use() -> None:
    """Reject mutated timestamp settings before constructing relation APIs.

    SQLAlchemy exposes relationship info as mutable public metadata.
    """
    timestamp_key = "titanspan_pivot_timestamps"
    parent_info = _TimestampedPivotParent.related.property.info
    valid_parent_timestamps = parent_info[timestamp_key]
    parent_info[timestamp_key] = ["created_at", "updated_at"]
    try:
        with pytest.raises(DatabaseQueryError, match="direct association"):
            _TimestampedPivotParent(name="Parent").relation("related")
    finally:
        parent_info[timestamp_key] = valid_parent_timestamps

    alias_info = _AliasedPivotParent.related.property.info
    alias_info[timestamp_key] = ("created_at", "updated_at")
    try:
        with pytest.raises(DatabaseQueryError, match="direct association"):
            _AliasedPivotParent(name="Parent").relation("related")
    finally:
        alias_info.pop(timestamp_key)

    parent_info[timestamp_key] = ("parent_id", "updated_at")
    try:
        with pytest.raises(DatabaseQueryError, match="non-key association"):
            _TimestampedPivotParent(name="Parent").relation("related")
    finally:
        parent_info[timestamp_key] = valid_parent_timestamps
