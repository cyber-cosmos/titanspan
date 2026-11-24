"""Exercise Sleep through AnyIO's task scheduling and cancellation model.

The tests avoid real-duration waits while verifying that the underlying
AnyIO checkpoints and cancellation scopes remain observable to callers.
"""

from __future__ import annotations

import anyio
import pytest

from titanspan.support import Sleep


@pytest.mark.integration
@pytest.mark.anyio
async def test_async_sleep_yields_to_a_sibling_task() -> None:
    """Allow a sibling task to run during an asynchronous sleep.

    Returns:
        None.
    """
    peer_ran = anyio.Event()

    async def mark_peer_ran() -> None:
        """Record that a sibling task reached its first checkpoint.

        Returns:
            None.
        """
        await anyio.lowlevel.checkpoint()
        peer_ran.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(mark_peer_ran)
        await Sleep.for_(0).seconds().sleep_async()

    assert peer_ran.is_set()


@pytest.mark.integration
@pytest.mark.anyio
async def test_async_sleep_propagates_cancellation() -> None:
    """Keep AnyIO cancellation visible at the explicit sleep boundary.

    Returns:
        None.
    """
    completed_after_cancel = False

    with anyio.CancelScope() as scope:
        scope.cancel()
        await Sleep.for_(1).seconds().sleep_async()
        completed_after_cancel = True

    assert scope.cancel_called
    assert not completed_after_cancel
