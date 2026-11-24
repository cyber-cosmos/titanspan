"""Verify the Support Tappable mixin delegates to the shared tap helper.

The tests cover callback return identity, explicit proxy calls, and rejection
of asynchronous callbacks from synchronous code.
"""

from __future__ import annotations

import pytest

from titanspan.support import AsyncCallbackUsageError, Stringable, Tappable


@pytest.mark.unit
def test_tappable_returns_the_same_instance_after_callback() -> None:
    """Run a side effect and preserve the original object identity.

    Returns:
        None.
    """
    value = Stringable("titanspan")
    result = value.tap(lambda current: current.__setitem__(0, "T"))

    assert result is value
    assert value.to_string() == "Titanspan"
    assert isinstance(Tappable(), Tappable)


@pytest.mark.unit
def test_tappable_proxy_uses_explicit_method_invocation() -> None:
    """Preserve the target after one explicit higher-order call.

    Returns:
        None.
    """
    value = Stringable("TITANSPAN")
    proxy = value.tap()

    assert proxy.call("lower") is value
    assert value.to_string() == "TITANSPAN"


@pytest.mark.unit
def test_tappable_rejects_awaitables_in_synchronous_callbacks() -> None:
    """Reject callbacks that require an asynchronous execution path.

    Returns:
        None.
    """
    value = Stringable("titanspan")

    async def callback(current: Stringable) -> None:
        """Represent a callback that must run asynchronously.

        Args:
            current: The value being observed.

        Returns:
            None.
        """
        del current

    with pytest.raises(AsyncCallbackUsageError):
        value.tap(callback)
