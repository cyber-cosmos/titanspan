"""Define an optional safe namespace-scoped lock clearing contract.
"""  # fmt: skip

from typing import Protocol, runtime_checkable


@runtime_checkable
class LockClearStore(Protocol):
    """Describe a backend that clears its own lock namespace.
    """  # fmt: skip

    def clear_locks(self) -> None:
        """Remove active and expired locks owned by this store namespace.
        """  # fmt: skip
        ...

    async def clear_locks_async(self) -> None:
        """Asynchronously clear this store's lock namespace.
        """  # fmt: skip
        ...


__all__ = ["LockClearStore"]
