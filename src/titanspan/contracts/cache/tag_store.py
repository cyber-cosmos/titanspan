"""Describe optional backend prefix invalidation for tag groups.

Tag invalidation is scoped and may be non-atomic when a backend scans keys.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TaggableCacheStore(Protocol):
    """Describe store support for bounded tag-group key deletion.
    """  # fmt: skip

    def clear_tagged(self, prefix: str) -> None:
        """Remove entries under one fully application-scoped tag prefix.
        """  # fmt: skip
        ...

    async def clear_tagged_async(self, prefix: str) -> None:
        """Asynchronously remove one scoped tag-group prefix.
        """  # fmt: skip
        ...


__all__ = ["TaggableCacheStore"]
