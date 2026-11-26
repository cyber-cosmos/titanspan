"""Verify deterministic native event dispatch behavior.

The enclosing test observes this target through the framework.
"""

from __future__ import annotations

# Runtime hint resolution detects awaitable callbacks before invocation.
from collections.abc import Awaitable  # noqa: TC003
from dataclasses import dataclass

import anyio
import pytest

from titanspan.events import (
    AsyncDispatchRequiredError,
    NativeEventDispatcher,
)

pytestmark = pytest.mark.unit
_ROLLBACK_MESSAGE = "rollback"


@dataclass(frozen=True, slots=True)
class DocumentProcessed:
    """Identify one processed document.

    The enclosing test observes this target through the framework.
    """

    document_id: str


def test_dispatch_preserves_registration_order_and_stops_on_false() -> None:
    """Run listeners in order and omit the exact stopping response.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def first(event: DocumentProcessed) -> str:
        """Record the first response.

        The enclosing test observes this target through the framework.
        """
        observed.append(f"first:{event.document_id}")
        return "first"

    def stop(event: DocumentProcessed) -> bool:
        """Stop propagation with the exact boolean value.

        The enclosing test observes this target through the framework.
        """
        observed.append(f"stop:{event.document_id}")
        return False

    def last(event: DocumentProcessed) -> str:
        """Record whether propagation reached the final listener.

        The enclosing test observes this target through the framework.
        """
        observed.append(f"last:{event.document_id}")
        return "last"

    dispatcher.listen(DocumentProcessed, first)
    dispatcher.listen(DocumentProcessed, stop)
    dispatcher.listen(DocumentProcessed, last)

    responses = dispatcher.dispatch(DocumentProcessed("doc-1"))

    assert observed == ["first:doc-1", "stop:doc-1"]
    assert responses == ["first"]


def test_until_returns_false_as_a_valid_response() -> None:
    """Treat every non-None response as a halting result.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()

    def reject(event: DocumentProcessed) -> bool:
        """Return a false response that still halts ``until``.

        The enclosing test observes this target through the framework.
        """
        _ = event
        return False

    dispatcher.listen(DocumentProcessed, reject)

    result = dispatcher.until(DocumentProcessed("doc-2"))

    assert result is False


def test_wildcard_listener_receives_name_and_payload() -> None:
    """Pass canonical named-event data to wildcard listeners.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[tuple[str, object]] = []

    def record(event_name: str, payload: object) -> None:
        """Retain the wildcard arguments for an assertion.

        The enclosing test observes this target through the framework.
        """
        observed.append((event_name, payload))

    dispatcher.listen("workflow.*", record)

    dispatcher.dispatch("workflow.completed", {"run_id": "run-1"})

    assert observed == [
        ("workflow.completed", {"run_id": "run-1"}),
    ]


@pytest.mark.anyio
async def test_async_dispatch_awaits_listeners_in_registration_order() -> None:
    """Await each mixed listener before starting the next listener.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def sync_listener(event: DocumentProcessed) -> str:
        """Record synchronous listener completion.

        The enclosing test observes this target through the framework.
        """
        observed.append("sync")
        return event.document_id

    async def async_listener(event: DocumentProcessed) -> str:
        """Record asynchronous listener completion.

        The enclosing test observes this target through the framework.
        """
        observed.append("async-start")
        observed.append("async-end")
        return event.document_id

    dispatcher.listen(DocumentProcessed, sync_listener)
    dispatcher.listen(DocumentProcessed, async_listener)

    responses = await dispatcher.dispatch_async(
        DocumentProcessed("doc-3"),
    )

    assert observed == ["sync", "async-start", "async-end"]
    assert responses == ["doc-3", "doc-3"]


@pytest.mark.anyio
async def test_sync_dispatch_preflights_async_only_listeners() -> None:
    """Reject async-only dispatch before invoking earlier listeners.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def sync_listener(event: DocumentProcessed) -> None:
        """Record a side effect that preflight must prevent.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)

    async def async_listener(event: DocumentProcessed) -> None:
        """Require the explicit asynchronous dispatch method.

        The enclosing test observes this target through the framework.
        """

    dispatcher.listen(DocumentProcessed, sync_listener)
    dispatcher.listen(DocumentProcessed, async_listener)

    with pytest.raises(AsyncDispatchRequiredError, match="dispatch_async"):
        dispatcher.dispatch(DocumentProcessed("doc-4"))

    assert observed == []


def test_sync_dispatch_preflights_awaitable_return_annotations() -> None:
    """Reject declared awaitable results before earlier listeners run.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def sync_listener(event: DocumentProcessed) -> None:
        """Record a side effect that preflight must prevent.

        The enclosing test observes this target through the framework.
        """
        _ = event
        observed.append("sync")

    async def complete_later() -> str:
        """Return one result for the awaitable listener declaration.

        The enclosing test observes this target through the framework.
        """
        return "async"

    def awaitable_listener(event: DocumentProcessed) -> Awaitable[str]:
        """Declare an awaitable result without using ``async def``.

        Args:
            event: Event selected by the dispatcher.

        Returns:
            Awaitable result requiring asynchronous dispatch.
        """
        _ = event
        return complete_later()

    dispatcher.listen(DocumentProcessed, sync_listener)
    dispatcher.listen(DocumentProcessed, awaitable_listener)

    with pytest.raises(AsyncDispatchRequiredError, match="dispatch_async"):
        dispatcher.dispatch(DocumentProcessed("awaitable-annotation"))

    assert observed == []


def test_sync_dispatch_rejects_unannotated_awaitable_results() -> None:
    """Never return an awaitable from sync dispatch, even if unannotated.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()

    async def complete_later() -> str:
        """Return a coroutine result that sync dispatch must close.

        The enclosing test observes this target through the framework.
        """
        return "async"

    def awaitable_listener(event: DocumentProcessed) -> object:
        """Return a coroutine behind an intentionally broad annotation.

        Args:
            event: Event selected by the dispatcher.

        Returns:
            The runtime awaitable result.
        """
        _ = event
        return complete_later()

    dispatcher.listen(DocumentProcessed, awaitable_listener)

    with pytest.raises(AsyncDispatchRequiredError, match="dispatch_async"):
        dispatcher.dispatch(DocumentProcessed("awaitable-result"))


def test_duplicates_are_preserved_and_registration_handles_remove_one() -> None:
    """Keep duplicate registrations distinct and individually removable.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: DocumentProcessed) -> str:
        """Record the event for duplicate registration assertions.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)
        return event.document_id

    first = dispatcher.listen(DocumentProcessed, record)
    dispatcher.listen(DocumentProcessed, record)
    dispatcher.dispatch(DocumentProcessed("duplicate"))

    first.close()
    dispatcher.dispatch(DocumentProcessed("remaining"))

    assert observed == ["duplicate", "duplicate", "remaining"]
    assert len(dispatcher.get_listeners(DocumentProcessed("query"))) == 1


def test_false_like_results_do_not_stop_ordinary_dispatch() -> None:
    """Reserve propagation stopping for the exact boolean ``False``.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[int] = []

    def zero() -> int:
        """Record a valid zero response.

        The enclosing test observes this target through the framework.
        """
        observed.append(0)
        return 0

    def empty_text() -> str:
        """Record a valid empty-string response.

        The enclosing test observes this target through the framework.
        """
        observed.append(1)
        return ""

    def empty_list() -> list[object]:
        """Record a valid empty-collection response.

        The enclosing test observes this target through the framework.
        """
        observed.append(2)
        return []

    dispatcher.listen(DocumentProcessed, zero)
    dispatcher.listen(DocumentProcessed, empty_text)
    dispatcher.listen(DocumentProcessed, empty_list)

    responses = dispatcher.dispatch(DocumentProcessed("false-like"))

    assert observed == [0, 1, 2]
    assert responses == [0, "", []]


@pytest.mark.anyio
async def test_async_dispatch_stops_only_on_exact_false() -> None:
    """Apply exact-false propagation to asynchronous listener results.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    async def continue_with_zero() -> int:
        """Return a valid false-like response before propagation stops.

        The enclosing test observes this target through the framework.
        """
        observed.append("zero")
        return 0

    async def stop() -> bool:
        """Return the exact boolean that halts listener propagation.

        The enclosing test observes this target through the framework.
        """
        observed.append("stop")
        return False

    async def unreachable() -> str:
        """Record an invocation that must follow no stopping listener.

        The enclosing test observes this target through the framework.
        """
        observed.append("unreachable")
        return "late"

    dispatcher.listen(DocumentProcessed, continue_with_zero)
    dispatcher.listen(DocumentProcessed, stop)
    dispatcher.listen(DocumentProcessed, unreachable)

    responses = await dispatcher.dispatch_async(
        DocumentProcessed("async-stop"),
    )
    halting_response = await dispatcher.until_async(
        DocumentProcessed("async-until"),
    )

    assert responses == [0]
    assert halting_response == 0
    assert observed == ["zero", "stop", "zero"]


@pytest.mark.anyio
async def test_until_async_returns_false_as_a_non_none_result() -> None:
    """Preserve false as a value in halting asynchronous dispatch.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()

    async def reject(event: DocumentProcessed) -> bool:
        """Return false to verify None-only stopping in ``until_async``.

        The enclosing test observes this target through the framework.
        """
        _ = event
        return False

    dispatcher.listen(DocumentProcessed, reject)

    assert (
        await dispatcher.until_async(
            DocumentProcessed("async-false"),
        )
        is False
    )


def test_named_event_distinguishes_missing_payload_from_none() -> None:
    """Pass explicit ``None`` while omitting an absent payload argument.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[object] = []

    def without_payload() -> None:
        """Record dispatch without a named payload.

        The enclosing test observes this target through the framework.
        """
        observed.append("missing")

    def with_payload(payload: object) -> None:
        """Record an explicit payload, including ``None``.

        The enclosing test observes this target through the framework.
        """
        observed.append(payload)

    dispatcher.listen("named.event", without_payload)
    dispatcher.listen("named.none", with_payload)

    dispatcher.dispatch("named.event")
    dispatcher.dispatch("named.none", None)

    assert observed == ["missing", None]


def test_exact_named_listeners_run_before_wildcard_listeners() -> None:
    """Match Laravel's exact-name then wildcard listener ordering.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def exact(payload: object) -> None:
        """Record delivery through the exact event name.

        The enclosing test observes this target through the framework.
        """
        _ = payload
        observed.append("exact")

    def wildcard(event_name: str, payload: object) -> None:
        """Record delivery through the matching wildcard.

        The enclosing test observes this target through the framework.
        """
        _ = event_name, payload
        observed.append("wildcard")

    dispatcher.listen("workflow.*", wildcard)
    dispatcher.listen("workflow.completed", exact)
    dispatcher.dispatch("workflow.completed", None)

    assert observed == ["exact", "wildcard"]


def test_class_listeners_follow_exact_wildcard_then_base_order() -> None:
    """Order inherited type matches after exact and wildcard listeners.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    @dataclass(frozen=True, slots=True)
    class DerivedDocumentProcessed(DocumentProcessed):
        """Identify the derived event in matching-order assertions.

        The enclosing test observes this target through the framework.
        """

    def exact(event: DerivedDocumentProcessed) -> None:
        """Record the exact class selector.

        The enclosing test observes this target through the framework.
        """
        _ = event
        observed.append("exact")

    def wildcard(name: str, payload: object) -> None:
        """Record the fully qualified event wildcard selector.

        The enclosing test observes this target through the framework.
        """
        _ = name, payload
        observed.append("wildcard")

    def base(event: DocumentProcessed) -> None:
        """Record the inherited event class selector.

        The enclosing test observes this target through the framework.
        """
        _ = event
        observed.append("base")

    dispatcher.listen(DocumentProcessed, base)
    dispatcher.listen(f"{DerivedDocumentProcessed.__module__}.*", wildcard)
    dispatcher.listen(DerivedDocumentProcessed, exact)
    dispatcher.dispatch(DerivedDocumentProcessed("derived"))

    assert observed == ["exact", "wildcard", "base"]


def test_listener_exceptions_propagate_without_running_later_listeners() -> (
    None
):
    """Preserve callback failures and stop the current dispatch.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def fail(event: DocumentProcessed) -> None:
        """Raise the application error unchanged.

        The enclosing test observes this target through the framework.
        """
        raise LookupError(event.document_id)

    def later(event: DocumentProcessed) -> None:
        """Record a listener that must not run after failure.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)

    dispatcher.listen(DocumentProcessed, fail)
    dispatcher.listen(DocumentProcessed, later)

    with pytest.raises(LookupError, match="expected"):
        dispatcher.dispatch(DocumentProcessed("expected"))

    assert observed == []


def test_recursive_dispatch_stops_at_its_configured_depth() -> None:
    """Bound reentrant dispatch and restore the depth after an exception.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher(max_dispatch_depth=2)

    def recurse(event: DocumentProcessed) -> None:
        """Dispatch recursively until the native guard rejects the call.

        The enclosing test observes this target through the framework.
        """
        dispatcher.dispatch(event)

    registration = dispatcher.listen(DocumentProcessed, recurse)

    with pytest.raises(RuntimeError, match="depth limit"):
        dispatcher.dispatch(DocumentProcessed("recursive"))

    registration.close()

    def recover(event: DocumentProcessed) -> str:
        """Return an event value after the depth guard unwinds.

        The enclosing test observes this target through the framework.
        """
        return event.document_id

    dispatcher.listen(DocumentProcessed, recover)

    assert dispatcher.dispatch(DocumentProcessed("recovered")) == [
        "recovered",
    ]


def test_pushed_events_flush_repeatedly_until_forgotten() -> None:
    """Retain pushed payloads through repeated explicit flushes.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[object] = []

    def record(payload: object) -> None:
        """Record one pushed payload for order assertions.

        The enclosing test observes this target through the framework.
        """
        observed.append(payload)

    dispatcher.listen("jobs.completed", record)
    dispatcher.push("jobs.completed", {"id": 1})
    dispatcher.push("jobs.completed", {"id": 2})

    dispatcher.flush("jobs.completed")
    dispatcher.flush("jobs.completed")
    dispatcher.forget_pushed()
    dispatcher.flush("jobs.completed")

    assert observed == [
        {"id": 1},
        {"id": 2},
        {"id": 1},
        {"id": 2},
    ]


def test_deferred_dispatch_flushes_after_success_and_discards_failure() -> None:
    """Flush successful deferred work and discard failed execution events.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: DocumentProcessed) -> None:
        """Record each delivered event in execution order.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)

    dispatcher.listen(DocumentProcessed, record)

    with dispatcher.defer():
        dispatcher.dispatch(DocumentProcessed("first"))
        assert observed == []

    def rollback() -> None:
        """Raise after buffering to verify frame cleanup.

        The enclosing test observes this target through the framework.
        """
        with dispatcher.defer():
            dispatcher.dispatch(DocumentProcessed("discarded"))
            raise ValueError(_ROLLBACK_MESSAGE)

    with pytest.raises(ValueError, match=_ROLLBACK_MESSAGE):
        rollback()

    assert observed == ["first"]


def test_nested_deferred_events_flush_at_the_inner_boundary() -> None:
    """Flush inner buffers immediately and outer buffers at their boundary.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: DocumentProcessed) -> None:
        """Record the delivered event identifier.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)

    dispatcher.listen(DocumentProcessed, record)

    with dispatcher.defer():
        dispatcher.dispatch(DocumentProcessed("outer-before"))
        with dispatcher.defer():
            dispatcher.dispatch(DocumentProcessed("inner"))
        assert observed == ["inner"]
        dispatcher.dispatch(DocumentProcessed("outer-after"))

    assert observed == ["inner", "outer-before", "outer-after"]


@pytest.mark.anyio
async def test_async_defer_discards_events_when_cancelled() -> None:
    """Discard pending events and restore deferred state after cancellation.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    def record(event: DocumentProcessed) -> None:
        """Record an event only if deferred work is flushed.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)

    dispatcher.listen(DocumentProcessed, record)

    with anyio.CancelScope() as cancel_scope:
        async with dispatcher.defer_async():
            await dispatcher.dispatch_async(DocumentProcessed("cancelled"))
            cancel_scope.cancel()
            await anyio.lowlevel.checkpoint()

    await dispatcher.dispatch_async(DocumentProcessed("after"))
    assert observed == ["after"]


@pytest.mark.anyio
async def test_async_defer_flushes_successful_events_in_order() -> None:
    """Await buffered async listeners in the original dispatch order.

    The assertions verify this contract through real listener callbacks.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    async def record(event: DocumentProcessed) -> str:
        """Record and return the identifier of a flushed event.

        The enclosing test observes this target through the framework.
        """
        observed.append(event.document_id)
        return event.document_id

    dispatcher.listen(DocumentProcessed, record)

    async with dispatcher.defer_async():
        await dispatcher.dispatch_async(DocumentProcessed("first"))
        await dispatcher.dispatch_async(DocumentProcessed("second"))
        assert observed == []

    assert observed == ["first", "second"]


@pytest.mark.anyio
async def test_child_dispatch_after_closed_frame_is_normal() -> None:
    """Run later child dispatch outside its parent's closed buffer.

    A stale inherited frame does not retain events after its owner exits.
    """
    dispatcher = NativeEventDispatcher()
    child_ready = anyio.Event()
    release_child = anyio.Event()
    observed: list[str] = []

    async def record(event: DocumentProcessed) -> None:
        """Record event execution after deferred-frame cleanup.

        Args:
            event: Event dispatched from the child task.
        """
        observed.append(event.document_id)

    async def child() -> None:
        """Wait until the owning task closes its deferred frame.

        The inherited ContextVar still refers to that closed frame.
        """
        child_ready.set()
        await release_child.wait()
        await dispatcher.dispatch_async(DocumentProcessed("after-exit"))

    dispatcher.listen(DocumentProcessed, record)

    async with anyio.create_task_group() as tasks:
        async with dispatcher.defer_async():
            tasks.start_soon(child)
            await child_ready.wait()
        assert observed == []
        release_child.set()

    assert observed == ["after-exit"]
