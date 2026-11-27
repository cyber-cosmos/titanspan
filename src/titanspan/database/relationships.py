"""Offer typed Active Record relationship declarations over SQLAlchemy.

The helpers delegate relationship instrumentation and loading to SQLAlchemy.
Mapped annotations identify related types without duplicating class metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import FromClause


def has_one[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[RelatedT]:
    """Declare a one-to-one relationship using its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for one related object.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=False,
        ),
    )


def has_many[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a one-to-many relationship from its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.
    """
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=True,
        ),
    )


def belongs_to[RelatedT](
    related_model: type[RelatedT],
    *,
    back_populates: str | None = None,
) -> Mapped[RelatedT]:
    """Declare a many-to-one relationship from its Mapped annotation.

    Args:
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for one related object.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            back_populates=back_populates,
            uselist=False,
        ),
    )


def belongs_to_many[RelatedT](
    related_model: type[RelatedT],
    secondary: FromClause,
    *,
    back_populates: str | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a many-to-many relationship with an explicit association.

    Args:
        secondary: Trusted SQLAlchemy association table or selectable.
        back_populates: Optional inverse relationship attribute name.
        related_model: Mapped related class.

    Returns:
        SQLAlchemy relationship instrumentation for related objects.
    """
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            secondary=secondary,
            back_populates=back_populates,
            uselist=True,
        ),
    )


def has_one_through[RelatedT](
    related_model: type[RelatedT],
    through_model: type[object],
    *,
    back_populates: str | None = None,
    primaryjoin: ColumnElement[bool] | None = None,
    secondaryjoin: ColumnElement[bool] | None = None,
) -> Mapped[RelatedT]:
    """Declare a read-only one-to-one path through a mapped table.

    Foreign keys on the intermediate table infer both joins by default. Supply
    explicit joins when the schema has multiple possible foreign-key paths.

    Args:
        related_model: Final mapped class returned by the relationship.
        through_model: Mapped class whose table connects both relationship
            endpoints.
        back_populates: Optional inverse view-only relationship attribute.
        primaryjoin: Optional parent-to-intermediate SQLAlchemy predicate.
        secondaryjoin: Optional intermediate-to-related predicate.

    Returns:
        SQLAlchemy relationship instrumentation for one related model.
    """
    return cast(
        "Mapped[RelatedT]",
        relationship(
            related_model,
            secondary=_mapped_table(through_model),
            back_populates=back_populates,
            primaryjoin=primaryjoin,
            secondaryjoin=secondaryjoin,
            uselist=False,
            viewonly=True,
        ),
    )


def has_many_through[RelatedT](
    related_model: type[RelatedT],
    through_model: type[object],
    *,
    back_populates: str | None = None,
    primaryjoin: ColumnElement[bool] | None = None,
    secondaryjoin: ColumnElement[bool] | None = None,
) -> Mapped[list[RelatedT]]:
    """Declare a read-only one-to-many path through a mapped table.

    Foreign keys on the intermediate table infer both joins by default. Supply
    explicit joins when the schema has multiple possible foreign-key paths.

    Args:
        related_model: Final mapped class returned by the relationship.
        through_model: Mapped class whose table connects both relationship
            endpoints.
        back_populates: Optional inverse view-only relationship attribute.
        primaryjoin: Optional parent-to-intermediate SQLAlchemy predicate.
        secondaryjoin: Optional intermediate-to-related predicate.

    Returns:
        SQLAlchemy relationship instrumentation for related models.
    """
    return cast(
        "Mapped[list[RelatedT]]",
        relationship(
            related_model,
            secondary=_mapped_table(through_model),
            back_populates=back_populates,
            primaryjoin=primaryjoin,
            secondaryjoin=secondaryjoin,
            uselist=True,
            viewonly=True,
        ),
    )


def _mapped_table(model: type[object]) -> FromClause:
    """Read a mapped table through SQLAlchemy's supported inspection API.

    Args:
        model: Intermediate mapped class used as a secondary table.

    Returns:
        The intermediate table expression used by SQLAlchemy relationships.
    """
    return cast("FromClause", sa_inspect(model).local_table)


__all__ = [
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_many_through",
    "has_one",
    "has_one_through",
]
