"""Resolve the active dispatcher for concise event dispatch calls.

Helpers use the active application dispatcher for every call.
"""

from titanspan.events._internal import MISSING_EVENT_PAYLOAD
from titanspan.facades.event import Event


def event(
    value: object | str,
    payload: object = MISSING_EVENT_PAYLOAD,
) -> list[object]:
    """Dispatch one event through the active application.

    Args:
        value: Event object or named event.
        payload: Optional single payload for a named event.

    Returns:
        Listener responses in registration order.
    """
    return Event.dispatch(value, payload)


async def event_async(
    value: object | str,
    payload: object = MISSING_EVENT_PAYLOAD,
) -> list[object]:
    """Asynchronously dispatch one event through the active application.

    Args:
        value: Event object or named event.
        payload: Optional single payload for a named event.

    Returns:
        Listener responses in registration order.
    """
    return await Event.dispatch_async(value, payload)


__all__ = ["event", "event_async"]
