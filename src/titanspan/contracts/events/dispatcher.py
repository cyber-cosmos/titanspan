"""Describe event registration and dispatch without backend types.

The protocol leaves execution and dependency resolution to adapters.
"""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Protocol, runtime_checkable

type EventSelector = type[object] | str


@runtime_checkable
class EventDispatcher(Protocol):
    """Describe the ordered, application-owned event dispatch boundary.

    Implementations dispatch listeners sequentially and preserve listener
    failures. Asynchronous execution is always explicit.
    """

    def listen(
        self,
        event: EventSelector | Sequence[EventSelector],
        listener: object,
    ) -> object:
        """Register one listener for one or more event selectors.

        Args:
            event: Event class, name, glob pattern, or ordered sequence.
            listener: Callable, listener class, or explicit method reference.

        Returns:
            A handle that can remove this registration.
        """
        ...

    def has_listeners(self, event: object | str) -> bool:
        """Check whether any registered listener matches an event value.

        Exact, wildcard, and supported inherited matches count.
        """
        ...

    def get_listeners(self, event: object | str) -> Sequence[object]:
        """Return matching listener targets in registration order.

        Returned targets preserve match category and registration order.
        """
        ...

    def has_wildcard_listeners(self, event: str | None = None) -> bool:
        """Check whether a named-event wildcard is registered or matches.

        Wildcard matching applies only to named events.
        """
        ...

    def subscribe(self, subscriber: object | type[object]) -> None:
        """Register related listeners through one subscriber object.

        Class subscribers resolve named methods in the active dispatch scope.
        Explicit instances remain owned by this dispatcher.
        """
        ...

    async def subscribe_async(
        self,
        subscriber: object | type[object],
    ) -> None:
        """Register a subscriber that requires asynchronous resolution.

        Named methods from a class subscriber resolve in the dispatch scope.
        """
        ...

    def push(self, event: str, payload: object = None) -> None:
        """Retain a named event payload for explicit later flushing.

        A flush dispatches retained payloads without clearing them.
        """
        ...

    def flush(self, event: str) -> list[object]:
        """Dispatch retained payloads for one named event.

        Call ``forget_pushed`` to release retained payloads.
        """
        ...

    async def flush_async(self, event: str) -> list[object]:
        """Asynchronously dispatch retained payloads for one event.

        Call ``forget_pushed`` to release retained payloads.
        """
        ...

    def forget_pushed(self) -> None:
        """Remove every retained payload registered through ``push``.

        This operation changes pushed storage, not listeners.
        """
        ...

    def defer(
        self,
        events: Sequence[EventSelector] | None = None,
    ) -> AbstractContextManager[None]:
        """Return a synchronous context manager for deferred dispatch.

        Successful exit flushes buffered events; failure discards them.
        """
        ...

    def defer_async(
        self,
        events: Sequence[EventSelector] | None = None,
    ) -> AbstractAsyncContextManager[None]:
        """Return an asynchronous context manager for deferred dispatch.

        Failure and cancellation discard this context buffer.
        """
        ...

    def fake(self, events: Sequence[EventSelector] | None = None) -> object:
        """Return a context manager that records selected dispatches.

        Selected events are recorded without invoking listeners.
        """
        ...

    def fake_except(self, events: Sequence[EventSelector]) -> object:
        """Return a context manager that records all except selected events.

        Excluded events continue through real listeners.
        """
        ...

    def dispatch(
        self,
        event: object | str,
        payload: object = None,
    ) -> list[object]:
        """Dispatch synchronously and collect listener results.

        Responses follow listener order; exact ``False`` stops propagation.
        """
        ...

    async def dispatch_async(
        self,
        event: object | str,
        payload: object = None,
    ) -> list[object]:
        """Dispatch synchronously and asynchronously registered listeners.

        Each listener completes before dispatch invokes the next.
        """
        ...

    def until(
        self,
        event: object | str,
        payload: object = None,
    ) -> object | None:
        """Return the first non-None listener result.

        False and other false-like non-``None`` values stop this search.
        """
        ...

    async def until_async(
        self,
        event: object | str,
        payload: object = None,
    ) -> object | None:
        """Asynchronously return the first non-None listener result.

        The first non-``None`` listener result ends this search.
        """
        ...

    def forget(
        self,
        event: EventSelector,
        listener: object | None = None,
    ) -> None:
        """Remove registrations matching an event and optional target.

        Removal affects snapshots created after this operation.
        """
        ...


__all__ = ["EventDispatcher", "EventSelector"]
