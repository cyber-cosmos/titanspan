"""Verify event registration, signature, and subscriber boundaries.

The cases exercise real dispatch and callback resolution paths.
"""

from __future__ import annotations

from collections.abc import Awaitable  # noqa: TC003
from typing import Annotated, Protocol

import pytest

from titanspan.container import Container
from titanspan.events import (
    AsyncDispatchRequiredError,
    EventRegistrationError,
    ListenerReference,
    NativeEventDispatcher,
    listener,
)
from titanspan.events._internal import selector_matches

pytestmark = pytest.mark.unit
_SIGNATURE_ERROR = "signature"


class SampleEvent:
    """Carry a value through listener boundary checks.

    Tests use the value to observe callback argument precedence.
    """

    def __init__(self, value: str) -> None:
        """Retain one event payload for the dispatcher.

        Args:
            value: Marker checked by event listener assertions.
        """
        self.value = value


class NonRuntimeProtocol(Protocol):
    """Define a protocol that Python cannot use with ``isinstance``.

    The test verifies the dispatcher's actionable selector error.
    """

    def describe(self) -> str:
        """Describe the structural value expected by this protocol.

        Returns:
            One diagnostic string.
        """
        ...


def test_selector_matching_and_protocol_errors() -> None:
    """Match named globs and report unsupported protocol checks.

    The result comes from the same matcher used by dispatch snapshots.
    """
    assert selector_matches("task.*", "task.started")
    assert not selector_matches(SampleEvent, "task.started")
    with pytest.raises(EventRegistrationError, match="runtime instance"):
        selector_matches(NonRuntimeProtocol, SampleEvent("protocol"))


def test_registration_rejects_empty_invalid_and_blank_selectors() -> None:
    """Reject selector shapes that cannot identify a listener event.

    Validation happens before the backend stores a receiver.
    """
    dispatcher = NativeEventDispatcher()

    def receive(event: SampleEvent) -> None:
        """Accept one event for registration validation.

        Args:
            event: Event supplied by the dispatcher.
        """
        _ = event

    with pytest.raises(EventRegistrationError, match="selectors"):
        dispatcher.listen((), receive)
    with pytest.raises(EventRegistrationError, match="selectors"):
        dispatcher.listen((1,), receive)  # type: ignore[arg-type]
    with pytest.raises(EventRegistrationError, match="must not be empty"):
        dispatcher.listen("", receive)
    with pytest.raises(ValueError, match="selector is required"):
        listener()


def test_registration_rejects_unsupported_targets_and_signatures() -> None:
    """Reject invalid listener shapes before invoking user code.

    Listener errors remain native and identify the failed boundary.
    """
    dispatcher = NativeEventDispatcher()

    class MissingHandle:
        """Provide a class without the required listener method.

        The dispatcher must reject it during registration.
        """

    class InvalidSignature:
        """Expose an uninspectable callable for signature validation.

        Python's inspection error becomes a framework registration error.
        """

        __signature__ = 42

        def __call__(self, event: SampleEvent) -> None:
            """Accept the event if preflight reaches callback inspection.

            Args:
                event: Event value provided by the dispatcher.
            """
            _ = event

    with pytest.raises(EventRegistrationError, match="handle"):
        dispatcher.listen(SampleEvent, MissingHandle)
    with pytest.raises(EventRegistrationError, match="callable"):
        dispatcher.listen(SampleEvent, object())
    dispatcher.listen(SampleEvent, InvalidSignature())
    with pytest.raises(EventRegistrationError, match="signatures"):
        dispatcher.dispatch(SampleEvent("bad-signature"))


def test_dispatch_rejects_payloads_for_class_events() -> None:
    """Reject a named payload when dispatch receives an event object.

    Class events carry their payload through the object itself.
    """
    dispatcher = NativeEventDispatcher()

    with pytest.raises(TypeError, match="payload only"):
        dispatcher.dispatch(SampleEvent("class"), "extra")


def test_wildcard_listener_requires_name_and_payload_arguments() -> None:
    """Require wildcard listeners to accept both canonical input values.

    Registration remains lazy, so dispatch reports the bad signature.
    """
    dispatcher = NativeEventDispatcher()

    def receive(name: str) -> None:
        """Accept only one argument to trigger wildcard validation.

        Args:
            name: Canonical named event supplied by dispatch.
        """
        _ = name

    dispatcher.listen("task.*", receive)

    with pytest.raises(EventRegistrationError, match="name and payload"):
        dispatcher.dispatch("task.started")


def test_listener_reference_can_resolve_a_class_without_a_container() -> None:
    """Construct an explicit class method target on every dispatch.

    The method reference follows the same path as listener classes.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    class MethodListener:
        """Resolve a named handler through an explicit reference.

        The test observes its result through ordinary dispatch.
        """

        def handle(self, event: SampleEvent) -> str:
            """Return the event value for its method reference.

            Args:
                event: Event value passed by the dispatcher.

            Returns:
                The event's stable marker.
            """
            observed.append(event.value)
            return event.value

    dispatcher.listen(
        SampleEvent,
        ListenerReference(MethodListener, "handle"),
    )

    assert dispatcher.dispatch(SampleEvent("method")) == ["method"]
    assert observed == ["method"]


@pytest.mark.anyio
async def test_async_method_reference_and_callable_objects_dispatch() -> None:
    """Resolve async class methods and callable instances through dispatch.

    Both listener forms use the normal dispatcher and response collection.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    class MethodListener:
        """Expose an asynchronous method selected by name.

        Async dispatch resolves a fresh class instance.
        """

        async def handle(self, event: SampleEvent) -> str:
            """Return the event value after the async boundary.

            Args:
                event: Value supplied by the explicit method reference.

            Returns:
                The event's stable marker.
            """
            observed.append(f"method:{event.value}")
            return event.value

    class AsyncCallable:
        """Provide an async ``__call__`` listener target.

        Callable instances follow normal async listener discovery.
        """

        async def __call__(self, event: SampleEvent) -> str:
            """Return the event value from this callable object.

            Args:
                event: Event value selected by the dispatcher.

            Returns:
                The event's stable marker.
            """
            observed.append(f"call:{event.value}")
            return event.value

    dispatcher.listen(
        SampleEvent,
        ListenerReference(MethodListener, "handle"),
    )
    dispatcher.listen(SampleEvent, AsyncCallable())

    assert await dispatcher.dispatch_async(SampleEvent("async")) == [
        "async",
        "async",
    ]
    assert observed == ["method:async", "call:async"]


@pytest.mark.anyio
async def test_async_subscription_accepts_awaitable_and_mapping_results() -> (
    None
):
    """Await subscriber registration before applying returned mappings.

    The mapped method executes through the same async dispatcher.
    """
    dispatcher = NativeEventDispatcher()
    observed: list[str] = []

    class AsyncSubscriber:
        """Return an awaitable subscriber result from a regular method.

        The subscriber exercises awaitable result adaptation.
        """

        def subscribe(
            self, dispatcher: NativeEventDispatcher
        ) -> Awaitable[dict[str, str]]:
            """Provide an awaitable event-to-method declaration.

            Args:
                dispatcher: Dispatcher available for imperative setup.

            Returns:
                An awaitable one-event mapping.
            """
            _ = dispatcher

            async def declarations() -> dict[str, str]:
                """Return one named event handler mapping.

                Returns:
                    Mapping for the subscriber's ``handle`` method.
                """
                return {"task.completed": "handle"}

            return declarations()

        async def handle(self, payload: object) -> str:
            """Record the payload selected by the mapping.

            Args:
                payload: Value passed by named event dispatch.

            Returns:
                A stable response marker.
            """
            observed.append(str(payload))
            return "handled"

    await dispatcher.subscribe_async(AsyncSubscriber())

    assert await dispatcher.dispatch_async("task.completed", 3) == [
        "handled",
    ]
    assert observed == ["3"]


def test_subscriber_mapping_validation_and_none_results() -> None:
    """Validate declarative subscriber results at registration time.

    Invalid mappings fail before any named event is dispatched.
    """
    dispatcher = NativeEventDispatcher()

    class EmptySubscriber:
        """Register imperatively and return no mapping.

        A missing mapping is a valid subscriber result.
        """

        def subscribe(self, dispatcher: NativeEventDispatcher) -> None:
            """Complete registration without declarations.

            Args:
                dispatcher: Dispatcher receiving imperative registrations.
            """
            _ = dispatcher

    class InvalidMapping:
        """Return a value that cannot describe event listeners.

        The dispatcher rejects mappings with the wrong shape.
        """

        def __init__(self, result: object) -> None:
            """Retain a selected result for subscriber validation.

            Args:
                result: Value returned by the subscriber method.
            """
            self.result = result

        def subscribe(self, dispatcher: NativeEventDispatcher) -> object:
            """Return the configured subscriber result.

            Args:
                dispatcher: Dispatcher supplied at subscription time.

            Returns:
                The result selected by the enclosing test.
            """
            _ = dispatcher
            return self.result

    dispatcher.subscribe(EmptySubscriber())
    with pytest.raises(EventRegistrationError, match="mappings"):
        dispatcher.subscribe(InvalidMapping([]))
    with pytest.raises(EventRegistrationError, match="keys"):
        dispatcher.subscribe(InvalidMapping({1: "handle"}))


def test_subscribe_requires_explicit_async_method() -> None:
    """Reject asynchronous setup from the synchronous subscription API.

    Callers receive an actionable instruction to use ``subscribe_async``.
    """
    dispatcher = NativeEventDispatcher()

    class AsyncSubscriber:
        """Declare asynchronous subscriber setup.

        The sync method must detect this before awaiting work.
        """

        async def subscribe(self, dispatcher: NativeEventDispatcher) -> None:
            """Expose an async-only subscription method.

            Args:
                dispatcher: Dispatcher provided for registration.
            """
            _ = dispatcher

    with pytest.raises(AsyncDispatchRequiredError, match="subscribe_async"):
        dispatcher.subscribe(AsyncSubscriber())


def test_subscription_helper_reports_missing_dispatcher_argument() -> None:
    """Reject subscriber callables that cannot accept the dispatcher.

    The helper keeps dependency invocation errors explicit.
    """

    class NoArgumentsSubscriber:
        """Expose a subscription callback without positional input.

        Subscription must supply its required dispatcher argument.
        """

        def subscribe(self) -> None:
            """Provide a signature that cannot receive the dispatcher.

            The subscriber fails before registration side effects.
            """

    with pytest.raises(EventRegistrationError, match="dispatcher argument"):
        NativeEventDispatcher(Container()).subscribe(NoArgumentsSubscriber())


def test_annotated_union_return_is_preflighted_as_async() -> None:
    """Detect awaitable return members inside annotated unions.

    Synchronous dispatch fails before it creates a coroutine value.
    """
    dispatcher = NativeEventDispatcher()

    def receive(event: SampleEvent) -> Annotated[Awaitable[str] | None, "tag"]:
        """Declare an awaitable result in an annotated union.

        Args:
            event: Event supplied by sync preflight.

        Returns:
            An awaitable result requiring async dispatch.
        """
        _ = event

        async def value() -> str:
            """Return a stable async result.

            Returns:
                One marker string.
            """
            return "async"

        return value()

    dispatcher.listen(SampleEvent, receive)

    with pytest.raises(AsyncDispatchRequiredError, match="dispatch_async"):
        dispatcher.dispatch(SampleEvent("annotated"))
