"""Define metadata-only events emitted by native cache repositories.
"""  # fmt: skip

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CacheEvent:
    """Describe one cache operation without key or value contents.

    Attributes:
        action: Stable operation label such as ``hit`` or ``write``.
        store: Configured store name within the active application.
        success: Whether the requested operation completed successfully.
    """

    action: str
    store: str
    success: bool = True


__all__ = ["CacheEvent"]
