"""Declare listener targets and event registration metadata.

Registration metadata preserves ordinary Python callable behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from titanspan.contracts.events import EventSelector

_EVENT_METADATA = "__titanspan_event_listeners__"
_SUBSCRIBER_METADATA = "__titanspan_event_subscriber__"
_EMPTY_EVENT_SELECTORS_ERROR = "At least one event selector is required."


@dataclass(frozen=True, slots=True)
class ListenerReference:
    """Select one method on a listener instance or container service.

    Attributes:
        target: Listener instance or class resolved by the active container.
        method: Method name invoked for matching events.
    """

    target: object
    method: str


def listener[ListenerT](
    *events: EventSelector,
) -> Callable[[ListenerT], ListenerT]:
    """Attach event selectors to a function or listener class.

    Args:
        events: Event classes, exact names, or named-event glob patterns.

    Returns:
        A decorator that adds discovery metadata without registering globally.
    """
    if not events:
        raise ValueError(_EMPTY_EVENT_SELECTORS_ERROR)

    def decorate(target: ListenerT) -> ListenerT:
        """Attach immutable registration metadata to one target.

        Args:
            target: Function or class declared by the application.

        Returns:
            The original target with its registration metadata attached.
        """
        previous = getattr(target, _EVENT_METADATA, ())
        metadata = tuple(previous) + tuple(events)
        setattr(target, _EVENT_METADATA, metadata)
        return target

    return decorate


def subscriber[ListenerT](target: ListenerT) -> ListenerT:
    """Mark one subscriber class for explicit module discovery.

    Args:
        target: Subscriber class with a ``subscribe`` method.

    Returns:
        The original subscriber class with discovery metadata.
    """
    setattr(target, _SUBSCRIBER_METADATA, True)
    return target


def declared_events(target: object) -> tuple[EventSelector, ...]:
    """Return decorator selectors attached to one listener target.

    Args:
        target: Function, class, or bound method under inspection.

    Returns:
        Selectors declared with :func:`listener`, or an empty tuple.
    """
    source = getattr(target, "__func__", target)
    values = getattr(source, _EVENT_METADATA, ())
    return cast("tuple[EventSelector, ...]", tuple(values))


def is_subscriber(target: object) -> bool:
    """Check whether a class opted into automatic subscriber discovery.

    Args:
        target: Module member inspected by trusted discovery.

    Returns:
        Whether :func:`subscriber` marked the target.
    """
    return bool(getattr(target, _SUBSCRIBER_METADATA, False))


__all__ = [
    "ListenerReference",
    "declared_events",
    "is_subscriber",
    "listener",
    "subscriber",
]
