"""Provide a typed mixin for side-effecting fluent observation.

The mixin delegates callback execution and proxy behavior to Titanspan's
shared ``tap`` helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, overload

from titanspan.support.helpers import HigherOrderTapProxy
from titanspan.support.helpers import tap as tap_value

if TYPE_CHECKING:
    from collections.abc import Callable


class Tappable:
    """Run side effects while preserving an instance's fluent identity.

    ``tap`` supports a synchronous callback or an explicit higher-order proxy
    whose :meth:`HigherOrderTapProxy.call` method invokes one target method.

    Notes:
        Async callbacks are rejected by the shared helper; callers that need
        asynchronous side effects should use ``tap_async`` directly.
    """

    @overload
    def tap(self) -> HigherOrderTapProxy[Self]:
        """Return a typed proxy when no callback is supplied.

        Returns:
            A proxy that can invoke one method on this instance.
        """

    @overload
    def tap(
        self,
        callback: Callable[[Self], object],
    ) -> Self:
        """Run a callback and return this instance.

        Args:
            callback: A synchronous side-effect callback.

        Returns:
            This instance after callback execution.
        """

    @overload
    def tap(self, callback: None) -> HigherOrderTapProxy[Self]:
        """Return a typed proxy for an explicit ``None`` callback.

        Args:
            callback: An explicit absence of a callback.

        Returns:
            A proxy that can invoke one method on this instance.
        """

    def tap(
        self,
        callback: Callable[[Self], object] | None = None,
    ) -> Self | HigherOrderTapProxy[Self]:
        """Delegate callback and proxy execution to the shared helper.

        Args:
            callback: Optional synchronous side-effect callback.

        Returns:
            This instance or a higher-order tap proxy.

        Raises:
            AsyncCallbackUsageError: If the callback returns an awaitable.
        """
        return tap_value(self, callback)


__all__ = ["Tappable"]
