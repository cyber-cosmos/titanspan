"""Offer typed Active Record relationship declarations over SQLAlchemy.

The helpers delegate relationship instrumentation and loading to SQLAlchemy.
Mapped annotations identify related types without duplicating class metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped
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


__all__ = ["belongs_to", "belongs_to_many", "has_many", "has_one"]
