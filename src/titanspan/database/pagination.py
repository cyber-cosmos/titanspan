"""Represent immutable page results for Core and ORM queries.

Page metadata stays separate from the selected result items.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class LengthAwarePaginator[T]:
    """Store page items with an exact total count.

    Attributes:
        items: Selected page items in database result order.
        total: Number of matching rows without the page limit.
        per_page: Requested maximum page size.
        current_page: One-based selected page number.
    """

    items: tuple[T, ...]
    total: int
    per_page: int
    current_page: int

    @property
    def last_page(self) -> int:
        """Return the final page number, including one empty-result page.

        Returns:
            A one-based page number.
        """
        return max((self.total + self.per_page - 1) // self.per_page, 1)

    @property
    def has_more_pages(self) -> bool:
        """Report whether a later page can contain matching rows.

        Returns:
            Whether ``current_page`` is before ``last_page``.
        """
        return self.current_page < self.last_page

    @property
    def previous_page(self) -> int | None:
        """Return the previous one-based page when it exists.

        Returns:
            The prior page or ``None`` for the first page.
        """
        return self.current_page - 1 if self.current_page > 1 else None

    @property
    def next_page(self) -> int | None:
        """Return the next one-based page when it exists.

        Returns:
            The following page or ``None`` after the last page.
        """
        return self.current_page + 1 if self.has_more_pages else None

    def __iter__(self) -> Iterator[T]:
        """Iterate through this page's items.

        Yields:
            Page items in database result order.
        """
        return iter(self.items)

    def __len__(self) -> int:
        """Return the number of items present on this page.

        Returns:
            The page item count.
        """
        return len(self.items)

    def to_dict(self) -> dict[str, object]:
        """Return pagination metadata and items as a native mapping.

        Returns:
            Serializable page metadata with the original item values.
        """
        return {
            "data": list(self.items),
            "total": self.total,
            "per_page": self.per_page,
            "current_page": self.current_page,
            "last_page": self.last_page,
            "has_more_pages": self.has_more_pages,
            "previous_page": self.previous_page,
            "next_page": self.next_page,
        }


@dataclass(frozen=True, slots=True)
class Paginator[T]:
    """Store a count-free page with one-row lookahead metadata.

    Attributes:
        items: Selected page items in database result order.
        per_page: Requested maximum page size.
        current_page: One-based selected page number.
        has_more_pages: Whether the extra lookahead row existed.
    """

    items: tuple[T, ...]
    per_page: int
    current_page: int
    has_more_pages: bool

    @property
    def previous_page(self) -> int | None:
        """Return the previous one-based page when it exists.

        Returns:
            The prior page or ``None`` for the first page.
        """
        return self.current_page - 1 if self.current_page > 1 else None

    @property
    def next_page(self) -> int | None:
        """Return the next one-based page when a lookahead row exists.

        Returns:
            The following page or ``None`` when no more rows were found.
        """
        return self.current_page + 1 if self.has_more_pages else None

    def __iter__(self) -> Iterator[T]:
        """Iterate through this page's items.

        Yields:
            Page items in database result order.
        """
        return iter(self.items)

    def __len__(self) -> int:
        """Return the number of items present on this page.

        Returns:
            The page item count.
        """
        return len(self.items)

    def to_dict(self) -> dict[str, object]:
        """Return page items and navigation metadata as a mapping.

        Returns:
            Serializable page metadata with the original item values.
        """
        return {
            "data": list(self.items),
            "per_page": self.per_page,
            "current_page": self.current_page,
            "has_more_pages": self.has_more_pages,
            "previous_page": self.previous_page,
            "next_page": self.next_page,
        }


__all__ = ["LengthAwarePaginator", "Paginator"]
