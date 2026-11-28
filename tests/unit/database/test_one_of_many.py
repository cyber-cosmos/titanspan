"""Verify validation of one-of-many relationship declarations.

These tests reject malformed mapping metadata before application startup.
"""

from __future__ import annotations

from typing import Literal, cast

import pytest
from sqlalchemy import ForeignKey, literal_column
from sqlalchemy.orm import Mapped, column_property, mapped_column

from titanspan.database import Model, of_many

pytestmark = pytest.mark.unit


class _OneOfManyValidationParent(Model):
    """Represent the parent table for declaration validation.

    Its mapped key resolves the related model's foreign-key constraint.
    """

    table = "unit_one_of_many_parents"
    label: Mapped[str]


class _OneOfManyValidationChild(Model):
    """Represent the related table with valid and sortable columns.

    The mapped score exercises validation of aggregate ordering metadata.
    """

    table = "unit_one_of_many_children"
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("unit_one_of_many_parents.id"),
    )
    score: Mapped[int]
    pair: Mapped[int] = column_property(
        literal_column("parent_id"),
        literal_column("score"),
    )


def test_of_many_rejects_an_unmapped_foreign_key() -> None:
    """Require a mapped related-model attribute for the parent key.

    Raises:
        ValueError: If the selected foreign-key attribute is absent.
    """
    assert _OneOfManyValidationParent.__table__.c.id.primary_key
    with pytest.raises(ValueError, match="foreign key"):
        of_many(_OneOfManyValidationChild, "missing_parent_id")


def test_of_many_rejects_empty_aggregate_mappings() -> None:
    """Require at least one aggregate attribute for custom selection.

    Raises:
        ValueError: If the aggregate mapping is empty.
    """
    with pytest.raises(ValueError, match="cannot be empty"):
        of_many(
            _OneOfManyValidationChild,
            "parent_id",
            aggregates={},
        )


def test_of_many_rejects_unmapped_sort_attributes() -> None:
    """Require aggregate ordering by mapped model columns.

    Raises:
        ValueError: If a sort attribute is absent from the related model.
    """
    with pytest.raises(ValueError, match="mapped columns"):
        of_many(
            _OneOfManyValidationChild,
            "parent_id",
            aggregates={"missing_score": "max"},
        )


def test_of_many_rejects_multi_column_foreign_keys() -> None:
    """Require the related parent key to identify one mapped column.

    Raises:
        ValueError: If the foreign-key property combines multiple columns.
    """
    with pytest.raises(ValueError, match="foreign key must map one column"):
        of_many(_OneOfManyValidationChild, "pair")


def test_of_many_rejects_multi_column_sort_attributes() -> None:
    """Require aggregate sort properties to identify one mapped column.

    Raises:
        ValueError: If the sort property combines multiple columns.
    """
    with pytest.raises(ValueError, match="sort attributes must map one column"):
        of_many(
            _OneOfManyValidationChild,
            "parent_id",
            aggregates={"pair": "max"},
        )


def test_of_many_rejects_unsupported_aggregate_functions() -> None:
    """Reject runtime aggregate values outside the typed public API.

    Raises:
        ValueError: If a caller supplies an unsupported aggregate function.
    """
    invalid_aggregate = cast("Literal['min', 'max']", "average")
    with pytest.raises(ValueError, match="aggregates must be"):
        of_many(
            _OneOfManyValidationChild,
            "parent_id",
            aggregates={"score": invalid_aggregate},
        )
