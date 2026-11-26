"""Share private typing support among collection implementations.

The protocol mirrors the ordering expected by Python's built-in operations.
"""

from __future__ import annotations

from typing import Protocol


class SupportsOrdering(Protocol):
    """Describe values accepted by Python's ordering operations.

    Methods are called only through native sorting and aggregation functions.
    """

    def __lt__(self, other: object, /) -> bool:
        """Compare this value as less than another value.

        Args:
            other: A value accepted by the concrete comparison method.

        Returns:
            Whether this value sorts before ``other``.
        """
        ...

    def __gt__(self, other: object, /) -> bool:
        """Compare this value as greater than another value.

        Args:
            other: A value accepted by the concrete comparison method.

        Returns:
            Whether this value sorts after ``other``.
        """
        ...
