"""Define typed continuation behavior for native Queue middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from titanspan.contracts.queue.context import JobContext

type JobNext = Callable[[], Awaitable[object]]
type SyncJobNext = Callable[[], object]


@runtime_checkable
class JobMiddleware(Protocol):
    """Wrap one job attempt and continue or short-circuit execution.

    Middleware instances resolve from the active job scope. They must not be
    mutated with request-specific state.
    """

    def handle(
        self,
        context: JobContext,
        next_handler: JobNext,
    ) -> object | Awaitable[object]:
        """Handle one attempt and optionally call the next stage.

        Args:
            context: Immutable metadata for the current attempt.
            next_handler: Async continuation for the next middleware or job.

        Returns:
            The job result or an intentional short-circuit value.
        """
        ...


@runtime_checkable
class SyncJobMiddleware(Protocol):
    """Wrap one job attempt during explicitly synchronous dispatch.

    Synchronous middleware runs only on a synchronous connection. It must not
    block on asynchronous work or create an event loop.
    """

    def handle(
        self,
        context: JobContext,
        next_handler: SyncJobNext,
    ) -> object:
        """Handle one attempt and optionally call the next stage.

        Args:
            context: Immutable metadata for the current attempt.
            next_handler: Synchronous continuation for the next stage.

        Returns:
            The job result or an intentional short-circuit value.
        """
        ...


type JobMiddlewareType = type[JobMiddleware] | type[SyncJobMiddleware]


__all__ = [
    "JobMiddleware",
    "JobMiddlewareType",
    "JobNext",
    "SyncJobMiddleware",
    "SyncJobNext",
]
