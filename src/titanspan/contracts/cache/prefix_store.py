"""Describe safely scoped deletion for composed cache stores.
"""  # fmt: skip

from typing import Protocol, runtime_checkable


@runtime_checkable
class PrefixClearStore(Protocol):
    """Describe deletion below a validated logical cache-key prefix.
    """  # fmt: skip

    def clear_prefix(self, prefix: str) -> None:
        """Delete entries whose logical keys begin with ``prefix``.
        """  # fmt: skip
        ...

    async def clear_prefix_async(self, prefix: str) -> None:
        """Asynchronously delete entries below a logical key prefix.
        """  # fmt: skip
        ...


__all__ = ["PrefixClearStore"]
