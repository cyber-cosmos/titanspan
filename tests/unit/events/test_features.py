"""Verify dispatcher lifecycle, filtering, fakes, and convenience APIs.

The enclosing test observes this target through the framework.
"""

from __future__ import annotations

import anyio
import pytest

from titanspan.contracts.events import EventDispatcher
from titanspan.events import (
    DeferredBufferOverflowError,
    Dispatchable,
    ListenerReference,
    NativeEventDispatcher,
)
from titanspan.events import (
    EventDispatcher as PublicEventDispatcher,
)

pytestmark = pytest.mark.unit
_FAILURE_MESSAGE = "failure"


class WorkEvent:
    """Identify one ordinary class-based event.

    The enclosing test observes this target through the framework.
    """

    def __init__(self, value: str) -> None:
        """Retain the event value used by listener assertions.

        Args:
            value: Event payload value.
        """
        self.value = value

    value: str


class ChangedEvent(WorkEvent):
    """Identify an event derived from another event class.

    The enclosing test observes this target through the framework.
    """


def test_inherited_event_selectors_and_explicit_method_references_match() -> (
    None
):
    """Match a base event class and invoke one explicit handler method.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    class Listener:
        """Expose a method selected without requiring a base class.

        The enclosing test observes this target through the framework.
        """

        def record(self, event: WorkEvent) -> None:
            """Record the event value supplied to the selected method.

            Args:
                event: Class-based event matched by its base type.
            """
            observed.append(event.value)

    dispatcher.listen(WorkEvent, ListenerReference(Listener(), "record"))
    dispatcher.dispatch(ChangedEvent("inherited"))

    assert observed == ["inherited"]


def test_events_package_reexports_the_canonical_dispatcher_contract() -> None:
    """Keep the contract identity shared by both public import paths.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()

    assert PublicEventDispatcher is EventDispatcher
    assert isinstance(dispatcher, EventDispatcher)


def test_dispatch_snapshots_registrations_before_running_user_code() -> None:
    """Keep an in-flight listener snapshot stable across removal.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def second() -> None:
        """Record the second listener from the original snapshot.

        The enclosing test observes this target through the framework.
        """
        observed.append("second")

    second_handle = dispatcher.listen(WorkEvent, second)

    def first() -> None:
        """Remove another registration while this dispatch is active.

        The enclosing test observes this target through the framework.
        """
        observed.append("first")
        second_handle.close()

    dispatcher.listen(WorkEvent, first)
    dispatcher.dispatch(WorkEvent("snapshot"))
    dispatcher.dispatch(WorkEvent("next"))

    assert observed == ["second", "first", "first"]


def test_partial_and_nested_fakes_restore_real_dispatch() -> None:
    """Intercept selected events and restore listeners after nested scopes.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: WorkEvent) -> None:
        """Record real listener execution.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.value)

    dispatcher.listen(WorkEvent, record)

    with dispatcher.fake_except([ChangedEvent]) as outer:
        dispatcher.dispatch(WorkEvent("outer-fake"))
        with dispatcher.fake([WorkEvent]) as inner:
            dispatcher.dispatch(WorkEvent("inner-fake"))
            inner.assert_dispatched(WorkEvent, times=1)
        dispatcher.dispatch(ChangedEvent("excluded"))
        outer.assert_dispatched(WorkEvent, times=1)
        outer.assert_not_dispatched(ChangedEvent)

    dispatcher.dispatch(WorkEvent("real"))

    assert observed == ["excluded", "real"]


def test_fake_checks_exact_listener_registration_identity() -> None:
    """Assert listener registrations without invoking listener callbacks.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()

    def record(event: WorkEvent) -> None:
        """Accept a test event without recording any side effects.

        The enclosing test observes this target through the framework.
        """
        _ = event

    dispatcher.listen(WorkEvent, record)

    with dispatcher.fake() as fake:
        fake.assert_listening(WorkEvent, record)
        fake.assert_not_listening(ChangedEvent, record)


def test_fake_state_restores_after_an_exception() -> None:
    """Restore real dispatch after a fake context raises.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: WorkEvent) -> None:
        """Record events delivered to the real listener.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.value)

    dispatcher.listen(WorkEvent, record)

    def fail_inside_fake() -> None:
        """Raise while interception is active to verify restoration.

        The enclosing test observes this target through the framework.
        """
        with dispatcher.fake():
            dispatcher.dispatch(WorkEvent("fake"))
            raise ValueError(_FAILURE_MESSAGE)

    with pytest.raises(ValueError, match=_FAILURE_MESSAGE):
        fail_inside_fake()

    dispatcher.dispatch(WorkEvent("real"))
    assert observed == ["real"]


def test_deferred_selectors_allow_unselected_events_to_run_immediately() -> (
    None
):
    """Defer only selected event classes in one context manager.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: WorkEvent) -> None:
        """Record every event delivered by the dispatcher.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.value)

    dispatcher.listen(WorkEvent, record)

    with dispatcher.defer([ChangedEvent]):
        dispatcher.dispatch(WorkEvent("immediate"))
        dispatcher.dispatch(ChangedEvent("deferred"))
        assert observed == ["immediate"]

    assert observed == ["immediate", "deferred"]


def test_deferred_buffer_enforces_its_configured_bound() -> None:
    """Bound pending memory and preserve the event-specific overflow error.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher(deferred_buffer_limit=1)

    def exceed_buffer() -> None:
        """Buffer one event beyond the configured capacity.

        The enclosing test observes this target through the framework.
        """
        with dispatcher.defer():
            dispatcher.dispatch(WorkEvent("first"))
            dispatcher.dispatch(WorkEvent("second"))

    with pytest.raises(DeferredBufferOverflowError, match="buffer"):
        exceed_buffer()


def test_push_buffer_overflow_uses_the_same_configured_limit() -> None:
    """Bound stored push payloads independently of event dispatch.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher(deferred_buffer_limit=1)
    dispatcher.push("task.started", 1)

    with pytest.raises(DeferredBufferOverflowError):
        dispatcher.push("task.started", 2)


def test_subscriber_can_register_imperative_and_declarative_handlers() -> None:
    """Support imperative listener registration and returned mappings.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    class ListenerGroup:
        """Provide two registration styles through one test subscriber.

        The enclosing test observes this target through the framework.
        """

        def subscribe(
            self,
            dispatcher: NativeEventDispatcher,
        ) -> dict[str, str]:
            """Register one handler and return another named mapping.

            Args:
                dispatcher: Dispatcher receiving both handler declarations.

            Returns:
                Mapping for a second event handler.
            """
            dispatcher.listen("manual.event", self.manual)
            return {"mapped.event": "mapped"}

        def manual(self, payload: object) -> str:
            """Record the manually registered event payload.

            Args:
                payload: Explicit named-event payload.

            Returns:
                Stable marker for this handler.
            """
            observed.append(f"manual:{payload}")
            return "manual"

        def mapped(self, payload: object) -> str:
            """Record the subscriber mapping payload.

            Args:
                payload: Explicit named-event payload.

            Returns:
                Stable marker for the mapped handler.
            """
            observed.append(f"mapped:{payload}")
            return "mapped"

    dispatcher.subscribe(ListenerGroup())

    assert dispatcher.dispatch("manual.event", 1) == ["manual"]
    assert dispatcher.dispatch("mapped.event", 2) == ["mapped"]
    assert observed == ["manual:1", "mapped:2"]


def test_dispatchable_skips_event_construction_when_condition_fails() -> None:
    """Evaluate conditions before constructing event values.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    created: list[str] = []

    class ConditionalEvent(Dispatchable):
        """Track construction without requiring a dataclass contract.

        The enclosing test observes this target through the framework.
        """

        def __init__(self, value: str) -> None:
            """Retain the value and record construction.

            Args:
                value: Event value selected by the caller.
            """
            created.append(value)

    assert ConditionalEvent.dispatch_if(False, value="skipped") is None
    assert ConditionalEvent.dispatch_unless(True, value="skipped") is None
    assert created == []


@pytest.mark.anyio
async def test_async_dispatchable_awaits_condition_before_construction() -> (
    None
):
    """Skip event construction when an asynchronous condition fails.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    created: list[str] = []

    class ConditionalEvent(Dispatchable):
        """Record construction after an async condition selects dispatch.

        The enclosing test observes this target through the framework.
        """

        def __init__(self, value: str) -> None:
            """Retain the constructed value for this assertion.

            Args:
                value: Event value selected by the caller.
            """
            created.append(value)

    async def should_dispatch() -> bool:
        """Return a false condition without creating an event.

        The enclosing test observes this target through the framework.
        """
        return False

    result = await ConditionalEvent.dispatch_if_async(
        should_dispatch,
        value="skipped",
    )

    assert result is None
    assert created == []


@pytest.mark.anyio
async def test_fake_state_isolated_to_the_task_that_enters_it() -> None:
    """Keep a child task's fake from affecting its parent context.

    The assertions inspect this behavior at the dispatcher boundary.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: WorkEvent) -> None:
        """Retain event values that reach the real listener.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.value)

    dispatcher.listen(WorkEvent, record)

    async def fake_dispatch() -> None:
        """Record one child-task dispatch in its scoped fake.

        The enclosing test observes this target through the framework.
        """
        with dispatcher.fake() as fake:
            await dispatcher.dispatch_async(WorkEvent("fake"))
            fake.assert_dispatched(WorkEvent, times=1)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(fake_dispatch)
        await dispatcher.dispatch_async(WorkEvent("real"))

    assert observed == ["real"]
