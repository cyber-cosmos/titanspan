"""Define detached, backend-independent database result values.

Result rows contain copied values and never retain a live cursor, connection,
ORM session, or identity map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class DatabaseResult:
    """Represent rows and affected-row metadata from one statement.

    Attributes:
        rows: Detached mapping rows copied before the result is closed.
        rowcount: Driver-reported affected rows or ``-1`` when unavailable.
    """

    rows: tuple[Mapping[str, object], ...]
    rowcount: int


__all__ = ["DatabaseResult"]
