"""Offer optional event-object dispatch conveniences.

Dispatch resolves through the active application context.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Self, cast

from titanspan.events.helpers import event, event_async

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class Dispatchable:
    """Add active-application dispatch methods to an ordinary event class.

    The mixin does not participate in event payload requirements. Dataclasses
    and ordinary Python classes remain the event's owning component contract.
    """

    __slots__ = ()

    @classmethod
    def dispatch(cls, **values: object) -> list[object]:
        """Construct and synchronously dispatch this event class.

        Args:
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses from the active application dispatcher.
        """
        event_type = cast("Callable[..., Self]", cls)
        return event(event_type(**values))

    @classmethod
    async def dispatch_async(cls, **values: object) -> list[object]:
        """Construct and asynchronously dispatch this event class.

        Args:
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses from the active application dispatcher.
        """
        event_type = cast("Callable[..., Self]", cls)
        return await event_async(event_type(**values))

    @classmethod
    def dispatch_if(
        cls,
        condition: bool | Callable[[], bool],
        **values: object,
    ) -> list[object] | None:
        """Construct and dispatch only when a synchronous condition passes.

        Args:
            condition: Boolean value or zero-argument predicate.
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses, or ``None`` when dispatch is skipped.
        """
        if not _condition_value(condition):
            return None
        return cls.dispatch(**values)

    @classmethod
    def dispatch_unless(
        cls,
        condition: bool | Callable[[], bool],
        **values: object,
    ) -> list[object] | None:
        """Construct and dispatch unless a synchronous condition passes.

        Args:
            condition: Boolean value or zero-argument predicate.
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses, or ``None`` when dispatch is skipped.
        """
        if _condition_value(condition):
            return None
        return cls.dispatch(**values)

    @classmethod
    async def dispatch_if_async(
        cls,
        condition: bool | Callable[[], bool | Awaitable[bool]],
        **values: object,
    ) -> list[object] | None:
        """Await a condition before constructing and dispatching the event.

        Args:
            condition: Boolean value or synchronous/asynchronous predicate.
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses, or ``None`` when dispatch is skipped.
        """
        if not await _condition_value_async(condition):
            return None
        return await cls.dispatch_async(**values)

    @classmethod
    async def dispatch_unless_async(
        cls,
        condition: bool | Callable[[], bool | Awaitable[bool]],
        **values: object,
    ) -> list[object] | None:
        """Await a condition and dispatch only when it is false.

        Args:
            condition: Boolean value or synchronous/asynchronous predicate.
            values: Keyword values passed to the event constructor.

        Returns:
            Listener responses, or ``None`` when dispatch is skipped.
        """
        if await _condition_value_async(condition):
            return None
        return await cls.dispatch_async(**values)


def _condition_value(condition: bool | Callable[[], bool]) -> bool:
    """Evaluate a synchronous condition without constructing an event.

    Args:
        condition: Boolean value or zero-argument predicate.

    Returns:
        The selected condition value.
    """
    return condition() if callable(condition) else condition


async def _condition_value_async(
    condition: bool | Callable[[], bool | Awaitable[bool]],
) -> bool:
    """Evaluate a condition through an explicit asynchronous boundary.

    Args:
        condition: Boolean value or sync/async zero-argument predicate.

    Returns:
        The resolved condition value.
    """
    if not callable(condition):
        return condition
    result = condition()
    if inspect.isawaitable(result):
        return await result
    return result


__all__ = ["Dispatchable"]
