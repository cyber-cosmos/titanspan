"""Record intercepted dispatches without executing registered listeners.

The fake intercepts the shared dispatcher without replacing its registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

from titanspan.contracts.events import EventSelector
from titanspan.events._internal import selector_matches

_FAKE_REENTRY_ERROR = "An event fake context cannot be re-entered."

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextvars import Token
    from types import TracebackType

    from titanspan.contracts.events import EventSelector


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Store one fake-visible dispatch without serializing its payload.

    Attributes:
        event: Original event object or exact named event.
        payload: Explicit payload for named events.
        has_payload: Distinguish omitted payload from explicit ``None``.
    """

    event: object | str
    payload: object | None
    has_payload: bool


class EventFake:
    """Intercept selected dispatches in the current execution context.

    The fake is bound to one dispatcher. Context-local state keeps concurrent
    application tasks independent and restores nested scopes on every exit.
    """

    def __init__(
        self,
        activate: Callable[[EventFake], Token[tuple[EventFake, ...]]],
        deactivate: Callable[[Token[tuple[EventFake, ...]]], None],
        is_listening: Callable[[EventSelector, object | None], bool],
        selectors: Sequence[EventSelector] | None,
        *,
        except_selectors: Sequence[EventSelector] = (),
    ) -> None:
        """Retain selection rules for one scoped interception.

        Args:
            activate: Operation that binds this fake in the active context.
            deactivate: Operation that restores the previous fake context.
            is_listening: Query for exact event and target registrations.
            selectors: Events to fake, or ``None`` to fake every event.
            except_selectors: Events that continue through real dispatch.
        """
        self._activate = activate
        self._deactivate = deactivate
        self._is_listening = is_listening
        self._selectors = None if selectors is None else tuple(selectors)
        self._except_selectors = tuple(except_selectors)
        self._records: list[EventRecord] = []
        self._token: Token[tuple[EventFake, ...]] | None = None
        self._active = False
        self._lock = RLock()

    def __enter__(self) -> EventFake:
        """Install this fake until its context exits.

        Returns:
            This recorder for inline assertions.

        Raises:
            RuntimeError: If this fake instance is already active.
        """
        if self._token is not None:
            raise RuntimeError(_FAKE_REENTRY_ERROR)
        self._active = True
        self._token = self._activate(self)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore the previous fake state after success or failure.

        Args:
            exception_type: Active exception class, if any.
            exception: Active exception instance, if any.
            traceback: Traceback associated with the active exception.
        """
        _ = exception_type, exception, traceback
        token = self._token
        if token is not None:
            with self._lock:
                self._active = False
            self._deactivate(token)
            self._token = None

    def matches(self, event: object | str) -> bool:
        """Check whether this fake intercepts an event value.

        Args:
            event: Event object or named event about to be dispatched.

        Returns:
            Whether this fake selects the event.
        """
        with self._lock:
            if not self._active:
                return False
            excluded = any(
                selector_matches(selector, event)
                for selector in self._except_selectors
            )
            if excluded:
                return False
            if self._selectors is None:
                return True
            return any(
                selector_matches(selector, event)
                for selector in self._selectors
            )

    def record(self, record: EventRecord) -> None:
        """Add one intercepted event to this recorder.

        Args:
            record: Event and payload reference observed at dispatch time.
        """
        with self._lock:
            if self._active:
                self._records.append(record)

    def dispatched(
        self,
        event: EventSelector | None = None,
        *,
        predicate: Callable[[EventRecord], bool] | None = None,
    ) -> tuple[EventRecord, ...]:
        """Return recorded events matching an optional type and predicate.

        Args:
            event: Optional event class, exact name, or glob pattern.
            predicate: Optional record filter applied after type matching.

        Returns:
            Matching records in dispatch order.
        """
        with self._lock:
            records = tuple(self._records)
        if event is not None:
            records = tuple(
                record
                for record in records
                if selector_matches(event, record.event)
            )
        if predicate is not None:
            records = tuple(record for record in records if predicate(record))
        return records

    def assert_dispatched(
        self,
        event: EventSelector,
        *,
        times: int | None = None,
        predicate: Callable[[EventRecord], bool] | None = None,
    ) -> None:
        """Assert that matching events were dispatched an expected number.

        Args:
            event: Event class, exact name, or glob pattern.
            times: Exact expected count, or ``None`` for at least one.
            predicate: Optional condition applied to recorded event values.

        Raises:
            AssertionError: If no matching record or the count differs.
        """
        records = self.dispatched(event, predicate=predicate)
        if times is None and records:
            return
        if len(records) != times:
            message = (
                f"Expected {event!r} {times!r} times; recorded "
                f"{len(records)} matching events."
            )
            raise AssertionError(message)

    def assert_not_dispatched(
        self,
        event: EventSelector,
        *,
        predicate: Callable[[EventRecord], bool] | None = None,
    ) -> None:
        """Assert that no matching event record exists.

        Args:
            event: Event class, exact name, or glob pattern.
            predicate: Optional condition applied to recorded event values.

        Raises:
            AssertionError: If a matching record exists.
        """
        records = self.dispatched(event, predicate=predicate)
        if records:
            message = f"Expected {event!r} not to be dispatched."
            raise AssertionError(message)

    def assert_nothing_dispatched(self) -> None:
        """Assert that this fake did not record any event.

        Raises:
            AssertionError: If at least one event was recorded.
        """
        with self._lock:
            count = len(self._records)
        if count:
            message = f"Expected no events; recorded {count}."
            raise AssertionError(message)

    def assert_listening(
        self,
        event: EventSelector,
        listener: object,
    ) -> None:
        """Assert that an exact event selector retains a listener target.

        Args:
            event: Exact event class, name, or wildcard pattern.
            listener: Registered listener target compared by identity.

        Raises:
            AssertionError: If the exact target registration is absent.
        """
        if not self._is_listening(event, listener):
            message = f"Expected {listener!r} to listen for {event!r}."
            raise AssertionError(message)

    def assert_not_listening(
        self,
        event: EventSelector,
        listener: object,
    ) -> None:
        """Assert that an exact event selector has no listener target.

        Args:
            event: Exact event class, name, or wildcard pattern.
            listener: Listener target compared by identity.

        Raises:
            AssertionError: If the target is registered for the selector.
        """
        if self._is_listening(event, listener):
            message = f"Did not expect {listener!r} for {event!r}."
            raise AssertionError(message)


__all__ = ["EventFake", "EventRecord"]
