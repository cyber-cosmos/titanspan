"""Verify safe boundaries for mapped pivot operations.

These tests exercise validation that does not require a database connection.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, Table
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from titanspan.database import DatabaseQueryError, Model

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
