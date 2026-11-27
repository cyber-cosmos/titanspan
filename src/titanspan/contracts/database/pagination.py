"""Describe backend-independent result types for paginated queries.

The protocols keep consumers independent of execution details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


class LengthAwarePage[ItemT](Protocol):
    """Describe a page with an exact total count.

    Its item tuple preserves the order returned by the query.
    """

    @property
    def items(self) -> tuple[ItemT, ...]:
        """Return items in database result order.

        Returns:
            The immutable sequence of page items.
        """
        ...

    @property
    def total(self) -> int:
        """Return the matching-row count before page slicing.

        Returns:
            The exact number of matching rows.
        """
        ...

    @property
    def per_page(self) -> int:
        """Return the configured page size.

        Returns:
            The positive maximum number of page items.
        """
        ...

    @property
    def current_page(self) -> int:
        """Return the selected one-based page.

        Returns:
            The current page number.
        """
        ...

    @property
    def last_page(self) -> int:
        """Return the final available page number.

        Returns:
            The final one-based page.
        """
        ...

    @property
    def has_more_pages(self) -> bool:
        """Report whether later pages contain matching items.

        Returns:
            Whether another page is available.
        """
        ...

    @property
    def previous_page(self) -> int | None:
        """Return the prior page when one exists.

        Returns:
            The prior page number or None.
        """
        ...

    @property
    def next_page(self) -> int | None:
        """Return the next page when one exists.

        Returns:
            The following page number or None.
        """
        ...

    def __iter__(self) -> Iterator[ItemT]:
        """Iterate over this page's items.

        Yields:
            Items in database result order.
        """
        ...

    def __len__(self) -> int:
        """Return the number of items in this page.

        Returns:
            The page item count.
        """
        ...


class SimplePage[ItemT](Protocol):
    """Describe a page with a one-row lookahead and no total query.

    The lookahead supplies navigation without a count statement.
    """

    @property
    def items(self) -> tuple[ItemT, ...]:
        """Return items in database result order.

        Returns:
            The immutable sequence of page items.
        """
        ...

    @property
    def per_page(self) -> int:
        """Return the configured page size.

        Returns:
            The positive maximum number of page items.
        """
        ...

    @property
    def current_page(self) -> int:
        """Return the selected one-based page.

        Returns:
            The current page number.
        """
        ...

    @property
    def has_more_pages(self) -> bool:
        """Report whether the lookahead row was found.

        Returns:
            Whether another page is available.
        """
        ...

    @property
    def previous_page(self) -> int | None:
        """Return the prior page when one exists.

        Returns:
            The prior page number or None.
        """
        ...

    @property
    def next_page(self) -> int | None:
        """Return the next page when one exists.

        Returns:
            The following page number or None.
        """
        ...

    def __iter__(self) -> Iterator[ItemT]:
        """Iterate over this page's items.

        Yields:
            Items in database result order.
        """
        ...

    def __len__(self) -> int:
        """Return the number of items in this page.

        Returns:
            The page item count.
        """
        ...


class CursorPage[ItemT](Protocol):
    """Describe a page navigated by validated cursor tokens.

    Cursor tokens contain bound order values, not executable query content.
    """

    @property
    def items(self) -> tuple[ItemT, ...]:
        """Return items in natural query order.

        Returns:
            The immutable sequence of page items.
        """
        ...

    @property
    def per_page(self) -> int:
        """Return the configured page size.

        Returns:
            The positive maximum number of returned items.
        """
        ...

    @property
    def next_cursor(self) -> str | None:
        """Return the token for the following page when one exists.

        Returns:
            An opaque cursor or ``None``.
        """
        ...

    @property
    def previous_cursor(self) -> str | None:
        """Return the token for the previous page when one exists.

        Returns:
            An opaque cursor or ``None``.
        """
        ...

    @property
    def has_more_pages(self) -> bool:
        """Report whether an additional page follows this page.

        Returns:
            Whether the query found a lookahead row.
        """
        ...

    @property
    def has_previous_pages(self) -> bool:
        """Report whether a previous-page cursor is available.

        Returns:
            Whether the result includes a previous cursor.
        """
        ...

    def __iter__(self) -> Iterator[ItemT]:
        """Iterate through the page items.

        Yields:
            Items in natural query order.
        """
        ...

    def __len__(self) -> int:
        """Return the number of returned items.

        Returns:
            The result item count.
        """
        ...


__all__ = ["CursorPage", "LengthAwarePage", "SimplePage"]
