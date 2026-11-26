"""Define ownership and lifecycle for a bridged standard logger.

The contract limits cleanup to the handler installed by Titanspan and
preserves unrelated process-wide logger configuration.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LogBridge(Protocol):
    """Represent one explicitly installed standard-logging bridge.

    Closing a bridge removes only handlers installed by that bridge and does
    not change unrelated process-wide logger configuration.
    """

    @property
    def logger_name(self) -> str:
        """Return the selected external logger name.

        Returns:
            The logger identifier that was explicitly bridged.
        """
        ...

    @property
    def channel_name(self) -> str:
        """Return the native destination channel name.

        Returns:
            The Titanspan channel receiving bridged records.
        """
        ...

    @property
    def closed(self) -> bool:
        """Report whether bridge cleanup has completed.

        Returns:
            Whether the bridge has removed its owned handler.
        """
        ...

    def close(self) -> None:
        """Remove the bridge-owned handler exactly once.

        Repeated calls are safe and leave unrelated handlers installed.
        """
        ...


__all__ = ["LogBridge"]
