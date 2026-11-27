"""Normalize cache expirations to backend-independent seconds.
"""  # fmt: skip

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil, isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titanspan.contracts.cache import CacheTTL

_MAX_DURATION_SECONDS = 315_576_000
_INVALID_ABSOLUTE_TTL = "Cache expiration datetimes must be timezone-aware."
_INVALID_TTL = "Cache expiration must be seconds, timedelta, datetime, or None."
_INVALID_TTL_FINITE = "Cache expiration must be finite and bounded."


def normalize_ttl(ttl: CacheTTL) -> float | None:
    """Convert supported expiration forms into millisecond-precision seconds.

    Args:
        ttl: Seconds, timedelta, absolute aware datetime, or ``None`` forever.

    Returns:
        Positive duration, zero for immediate expiry, or ``None`` forever.

    Raises:
        ValueError: If a duration is invalid, non-finite, or over ten years.
    """
    if ttl is None:
        return None
    if isinstance(ttl, datetime):
        if ttl.tzinfo is None or ttl.utcoffset() is None:
            raise ValueError(_INVALID_ABSOLUTE_TTL)
        seconds = (ttl.astimezone(UTC) - datetime.now(UTC)).total_seconds()
    elif isinstance(ttl, timedelta):
        seconds = ttl.total_seconds()
    elif type(ttl) in (int, float):
        seconds = float(ttl)
    else:
        raise ValueError(_INVALID_TTL)
    if not isfinite(seconds) or seconds > _MAX_DURATION_SECONDS:
        raise ValueError(_INVALID_TTL_FINITE)
    if seconds <= 0:
        return 0.0
    return ceil(seconds * 1000) / 1000


__all__ = ["normalize_ttl"]
