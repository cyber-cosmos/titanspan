"""Exercise Timebox against AnyIO's running task scheduler.

Verify a minimum-duration wait yields control to a sibling task.
"""

from __future__ import annotations

import anyio
import pytest

from titanspan.support import Timebox


@pytest.mark.integration
@pytest.mark.anyio
async def test_async_timebox_yields_to_a_sibling_task() -> None:
    """Let other scoped tasks run while the timebox waits.

    Returns:
        None.
    """
    peer_ran = anyio.Event()

    async def mark_peer_ran() -> None:
        """Record that the task group scheduled a sibling operation.

        Returns:
            None.
        """
        await anyio.lowlevel.checkpoint()
        peer_ran.set()

    async def callback(_box: Timebox) -> str:
        """Return immediately so the timebox has to perform its wait.

        Returns:
            A stable callback result.
        """
        return "complete"

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(mark_peer_ran)
        result = await Timebox().call_async(callback, 10_000)
        assert result == "complete"
        task_group.cancel_scope.cancel()

    assert peer_ran.is_set()
