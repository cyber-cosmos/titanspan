"""Expose event operations through the active application context.

Every facade call resolves through active application state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from titanspan.contracts.events import EventDispatcher
from titanspan.events._internal import MISSING_EVENT_PAYLOAD
from titanspan.facades.base import Facade

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from titanspan.contracts.events import EventSelector
    from titanspan.events.dispatcher import ListenerRegistration
    from titanspan.events.testing import EventFake


class Event(Facade[EventDispatcher]):
    """Resolve the canonical dispatcher owned by the active application.

    The facade delegates each operation to the canonical dispatcher.
    """

    service_contract = EventDispatcher

    @classmethod
    def dispatcher(cls) -> EventDispatcher:
        """Return the active application's canonical dispatcher.

        Returns:
            Dispatcher resolved from the shared service graph.
        """
        return cls.resolve_service()

    @classmethod
    def listen(
        cls,
        event: EventSelector | Sequence[EventSelector],
        listener: object,
    ) -> ListenerRegistration:
        """Register one listener on the active dispatcher.

        Args:
            event: Event selectors accepted by the dispatcher.
            listener: Callable, listener class, or method reference.

        Returns:
            A removable registration handle.
        """
        return cast(
            "ListenerRegistration",
            cls.dispatcher().listen(event, listener),
        )

    @classmethod
    def dispatch(
        cls,
        event: object | str,
        payload: object = MISSING_EVENT_PAYLOAD,
    ) -> list[object]:
        """Dispatch synchronously through the active application.

        Args:
            event: Event object or named event.
            payload: Optional named-event payload.

        Returns:
            Listener responses in registration order.
        """
        return cls.dispatcher().dispatch(event, payload)

    @classmethod
    async def dispatch_async(
        cls,
        event: object | str,
        payload: object = MISSING_EVENT_PAYLOAD,
    ) -> list[object]:
        """Dispatch through the asynchronous listener path.

        Args:
            event: Event object or named event.
            payload: Optional named-event payload.

        Returns:
            Listener responses in registration order.
        """
        return await cls.dispatcher().dispatch_async(event, payload)

    @classmethod
    def until(
        cls,
        event: object | str,
        payload: object = MISSING_EVENT_PAYLOAD,
    ) -> object | None:
        """Return the first non-None synchronous listener result.

        Args:
            event: Event object or named event.
            payload: Optional named-event payload.

        Returns:
            The first response that is not ``None``.
        """
        return cls.dispatcher().until(event, payload)

    @classmethod
    async def until_async(
        cls,
        event: object | str,
        payload: object = MISSING_EVENT_PAYLOAD,
    ) -> object | None:
        """Return the first non-None async listener result.

        Args:
            event: Event object or named event.
            payload: Optional named-event payload.

        Returns:
            The first response that is not ``None``.
        """
        return await cls.dispatcher().until_async(event, payload)

    @classmethod
    def has_listeners(cls, event: object | str) -> bool:
        """Check whether the active dispatcher has a matching listener.

        Matching uses the active dispatcher registration snapshot.
        """
        return cls.dispatcher().has_listeners(event)

    @classmethod
    def has_wildcard_listeners(cls, event: str | None = None) -> bool:
        """Check for matching named-event wildcard listeners.

        Wildcard patterns match canonical named events.
        """
        return cls.dispatcher().has_wildcard_listeners(event)

    @classmethod
    def get_listeners(cls, event: object | str) -> Sequence[object]:
        """Return matching listener targets in registration order.

        The returned targets preserve dispatcher ordering.
        """
        return cls.dispatcher().get_listeners(event)

    @classmethod
    def forget(
        cls,
        event: EventSelector,
        listener: object | None = None,
    ) -> None:
        """Remove listener registrations matching a selector and target.

        Removal changes the active dispatcher registry for later dispatches.
        """
        cls.dispatcher().forget(event, listener)

    @classmethod
    def push(
        cls,
        event: str,
        payload: object = MISSING_EVENT_PAYLOAD,
    ) -> None:
        """Retain a named event payload until a matching flush.

        The payload remains until explicitly flushed or forgotten.
        """
        cls.dispatcher().push(event, payload)

    @classmethod
    def flush(cls, event: str) -> list[object]:
        """Dispatch the retained payloads for one pushed event.

        Flushed payloads remain stored until ``forget_pushed``.
        """
        return cls.dispatcher().flush(event)

    @classmethod
    async def flush_async(cls, event: str) -> list[object]:
        """Asynchronously dispatch the retained payloads for one event.

        Flushed payloads remain stored until ``forget_pushed``.
        """
        return await cls.dispatcher().flush_async(event)

    @classmethod
    def forget_pushed(cls) -> None:
        """Remove every payload retained through :meth:`push`.

        The operation clears retained payloads without removing listeners.
        """
        cls.dispatcher().forget_pushed()

    @classmethod
    def subscribe(cls, subscriber: object | type[object]) -> None:
        """Register a subscriber through the active dispatcher.

        Args:
            subscriber: Subscriber instance or container-resolved class.
        """
        cls.dispatcher().subscribe(subscriber)

    @classmethod
    async def subscribe_async(
        cls,
        subscriber: object | type[object],
    ) -> None:
        """Asynchronously resolve and register one subscriber.

        Args:
            subscriber: Subscriber instance or container-resolved class.
        """
        await cls.dispatcher().subscribe_async(subscriber)

    @classmethod
    def defer(
        cls,
        events: Sequence[EventSelector] | None = None,
    ) -> AbstractContextManager[None]:
        """Return a context manager that defers selected event dispatches.

        Successful exit dispatches buffered events; exceptions discard them.
        """
        return cls.dispatcher().defer(events)

    @classmethod
    def defer_async(
        cls,
        events: Sequence[EventSelector] | None = None,
    ) -> AbstractAsyncContextManager[None]:
        """Return an async context manager for selected deferred events.

        Cancellation also discards this context buffer.
        """
        return cls.dispatcher().defer_async(events)

    @classmethod
    def fake(
        cls,
        events: Sequence[EventSelector] | None = None,
    ) -> EventFake:
        """Create an execution-local fake for selected active dispatches.

        The fake records selected events through every shared entry point.
        """
        return cast("EventFake", cls.dispatcher().fake(events))

    @classmethod
    def fake_except(cls, events: Sequence[EventSelector]) -> EventFake:
        """Fake active dispatches except for selected event values.

        Unselected events continue to real listener dispatch.
        """
        return cast("EventFake", cls.dispatcher().fake_except(events))


__all__ = ["Event"]
