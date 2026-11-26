"""Dispatch application events through Blinker and the native container.

Blinker stores receivers while Titanspan owns dispatch policy.
"""

from __future__ import annotations

import inspect
from collections.abc import (
    Awaitable,
    Coroutine,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import RLock
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from titanspan.contracts.events import (
    EventDispatcher as EventDispatcherContract,
)
from titanspan.events._backends.blinker import OrderedSignal
from titanspan.events._internal import (
    MISSING_EVENT_PAYLOAD,
    canonical_event_name,
    selector_is_wildcard,
    selector_matches,
)
from titanspan.events.exceptions import (
    AsyncDispatchRequiredError,
    DeferredBufferOverflowError,
    EventError,
    EventRegistrationError,
)
from titanspan.events.listener import ListenerReference
from titanspan.events.testing import EventFake, EventRecord

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator

    from titanspan.container import Container
    from titanspan.contracts.events import EventSelector

_MISSING = MISSING_EVENT_PAYLOAD
_ASYNC_DISPATCH_MESSAGE = (
    "This event has an asynchronous listener; use dispatch_async."
)
_MAX_BUFFER_MESSAGE = (
    "The event buffer reached its configured limit; flush or reduce events."
)
_EVENT_LIMITS_ERROR = "Event limits must be positive integers."
_SUBSCRIBER_METHOD_ERROR = "Subscribers must define subscribe(dispatcher)."
_ASYNC_SUBSCRIBER_ERROR = "Use subscribe_async for asynchronous subscribers."
_SUBSCRIBER_MAPPING_ERROR = (
    "Subscriber results must be event-to-listener mappings."
)
_SUBSCRIBER_KEY_ERROR = "Subscriber keys must be event names or types."
_PUSHED_NAME_ERROR = "Pushed events require an exact name."
_INVALID_PAYLOAD_ERROR = "Pass payload only when dispatching a named event."
_DISPATCH_DEPTH_ERROR = "The event dispatch depth limit was reached."
_SELECTOR_ERROR = "Event selectors must be names or types."
_EVENT_NAME_ERROR = "Event names must not be empty."
_LISTENER_CLASS_ERROR = "Listener classes must define handle()."
_LISTENER_CALLABLE_ERROR = "Listener target has no callable handler."
_HANDLE_METHOD_NAME = "handle"
_LISTENER_SIGNATURE_ERROR = "Event listener signatures must be inspectable."
_WILDCARD_SIGNATURE_ERROR = (
    "Wildcard listeners must accept event name and payload."
)
_WILDCARD_ARGUMENT_COUNT = 2
_EXACT_EVENT_MATCH_CATEGORY = 0
_WILDCARD_EVENT_MATCH_CATEGORY = 1
_BASE_EVENT_MATCH_CATEGORY = 2


@dataclass(slots=True)
class _ListenerBinding:
    """Associate event selectors with one Blinker receiver registration.

    The signal keeps one receiver while selector ownership stays local.
    """

    selectors: tuple[EventSelector, ...]
    target: object
    active: bool = True

    def receive(self, sender: object, **kwargs: object) -> None:
        """Serve as a strongly retained receiver in the Blinker registry.

        Args:
            sender: Signal sender supplied by Blinker.
            kwargs: Signal payload, unused by the registry adapter.
        """
        _ = sender, kwargs

    @property
    def receiver(self) -> Callable[..., None]:
        """Return the bound receiver used for registration and removal.

        Returns:
            The strongly retained Blinker receiver method.
        """
        return self.receive


@dataclass(slots=True)
class ListenerRegistration:
    """Own one removable registration in an application dispatcher.

    Each handle removes only the registration it owns.
    """

    _close_callback: Callable[[], None]

    def close(self) -> None:
        """Remove this exact listener registration if it remains active.

        Repeated cleanup leaves later dispatcher state unchanged.
        """
        self._close_callback()

    def __enter__(self) -> ListenerRegistration:
        """Return the registration handle for context-managed cleanup.

        Returns:
            This registration handle.
        """
        return self

    def __exit__(self, *args: object) -> None:
        """Remove this registration when its owning context exits.

        Args:
            args: Standard context-manager exception details.
        """
        _ = args
        self.close()


@dataclass(slots=True)
class _DeferredFrame:
    """Hold an execution-local event buffer with nested selection rules.

    The frame owns pending events until its context boundary.
    """

    parent: _DeferredFrame | None
    selectors: tuple[EventSelector, ...] | None
    limit: int
    active: bool = True
    events: list[tuple[object | str, object]] = field(init=False)
    lock: RLock = field(init=False)

    def __post_init__(self) -> None:
        """Initialize typed storage owned by this one execution frame.

        The frame keeps its buffer and lock together.
        """
        self.events: list[tuple[object | str, object]] = []
        self.lock = RLock()

    def append(self, event: object | str, payload: object) -> bool:
        """Add one event if this frame has remaining capacity.

        Args:
            event: Event value retained until context completion.
            payload: Explicit payload or the dispatcher's missing sentinel.

        Returns:
            Whether the frame accepted the event while still active.

        Raises:
            DeferredBufferOverflowError: If the configured bound is full.
        """
        with self.lock:
            if not self.active:
                return False
            if len(self.events) >= self.limit:
                raise DeferredBufferOverflowError(_MAX_BUFFER_MESSAGE)
            self.events.append((event, payload))
            return True

    def take(self) -> tuple[tuple[object | str, object], ...]:
        """Remove and return this frame's pending events in order.

        Returns:
            Immutable pending events for final dispatch.
        """
        with self.lock:
            events = tuple(self.events)
            self.events.clear()
            self.active = False
            return events


class NativeEventDispatcher(EventDispatcherContract):
    """Coordinate ordered event listeners, deferred dispatch, and fakes.

    Blinker owns receiver registration and strong receiver references. The
    dispatcher adapts its public receiver snapshots to Titanspan's ordered,
    sequential result and propagation semantics.
    """

    def __init__(
        self,
        container: Container | None = None,
        *,
        deferred_buffer_limit: int = 10_000,
        max_dispatch_depth: int = 32,
    ) -> None:
        """Create an isolated dispatcher with bounded execution state.

        Args:
            container: Optional native container for listener construction.
            deferred_buffer_limit: Maximum events held by each buffer.
            max_dispatch_depth: Maximum recursive dispatch depth.

        Raises:
            ValueError: If a configured limit is not positive.
        """
        if deferred_buffer_limit <= 0 or max_dispatch_depth <= 0:
            raise ValueError(_EVENT_LIMITS_ERROR)
        self._container = container
        self._deferred_buffer_limit = deferred_buffer_limit
        self._max_dispatch_depth = max_dispatch_depth
        self._signal = OrderedSignal()
        self._lock = RLock()
        self._deferred: ContextVar[_DeferredFrame | None] = ContextVar(
            f"titanspan_events_deferred_{id(self)}",
            default=None,
        )
        self._fakes: ContextVar[tuple[EventFake, ...]] = ContextVar(
            f"titanspan_events_fakes_{id(self)}",
            default=(),
        )
        self._dispatch_depth: ContextVar[int] = ContextVar(
            f"titanspan_events_depth_{id(self)}",
            default=0,
        )
        self._pushed: dict[str, list[object]] = {}
        self._discovered: set[str] = set()

    def listen(
        self,
        event: EventSelector | Sequence[EventSelector],
        listener: object,
    ) -> ListenerRegistration:
        """Register one function, class, callable, or method reference.

        Args:
            event: Event class, exact name, glob, or ordered selectors.
            listener: Callable target or :class:`ListenerReference`.

        Returns:
            A handle that removes this registration when closed.

        Raises:
            EventRegistrationError: If selectors or the target are invalid.
        """
        selectors = _normalize_selectors(event)
        _validate_target(listener)
        binding = _ListenerBinding(selectors, listener)
        with self._lock:
            self._signal.connect(binding.receiver, weak=False)

        def close_registration() -> None:
            """Disconnect the registration represented by this handle.

            Disconnecting a handle affects later listener snapshots.
            """
            self._forget_binding(binding)

        return ListenerRegistration(close_registration)

    def has_listeners(self, event: object | str) -> bool:
        """Check whether a registered listener matches an event value.

        Args:
            event: Named event or ordinary event object.

        Returns:
            Whether at least one matching registration exists.
        """
        return bool(self._matching_bindings(event))

    def has_wildcard_listeners(self, event: str | None = None) -> bool:
        """Check registered named-event patterns, optionally for one name.

        Args:
            event: Optional named event checked against wildcard selectors.

        Returns:
            Whether any wildcard selector exists or matches the name.
        """
        for binding in self._binding_snapshot():
            for selector in binding.selectors:
                if selector_is_wildcard(selector) and (
                    event is None or selector_matches(selector, event)
                ):
                    return True
        return False

    def get_listeners(self, event: object | str) -> tuple[object, ...]:
        """Return matching listener targets in registration order.

        Args:
            event: Named event or ordinary event object.

        Returns:
            Listener targets selected by the current stable snapshot.
        """
        return tuple(
            binding.target for binding in self._matching_bindings(event)
        )

    def dispatch(
        self,
        event: object | str,
        payload: object = _MISSING,
    ) -> list[object]:
        """Run sync-safe listeners and collect responses in order.

        Returning the exact boolean ``False`` stops propagation and is omitted
        from the response list. Other false-like values remain valid results.

        Args:
            event: Event object or exact named event.
            payload: One explicit named-event payload, including ``None``.

        Returns:
            Listener responses collected before propagation stops.

        Raises:
            AsyncDispatchRequiredError: If a matching listener is async-only.
            EventRegistrationError: If a listener signature is invalid.
            EventError: If recursive dispatch exceeds the configured bound.
        """
        if self._capture_or_defer(event, payload):
            return []
        bindings = self._matching_bindings(event)
        callbacks = self._preflight(bindings, event, payload)
        with self._dispatching():
            responses: list[object] = []
            for binding, arguments in callbacks:
                result = self._invoke_sync(binding, arguments)
                if result is False:
                    break
                responses.append(result)
        return responses

    async def dispatch_async(
        self,
        event: object | str,
        payload: object = _MISSING,
    ) -> list[object]:
        """Run sync and async listeners sequentially and collect responses.

        Args:
            event: Event object or exact named event.
            payload: One explicit named-event payload, including ``None``.

        Returns:
            Listener responses collected before exact ``False`` stops dispatch.

        Raises:
            EventRegistrationError: If a listener signature is invalid.
        """
        if self._capture_or_defer(event, payload):
            return []
        bindings = self._matching_bindings(event)
        callbacks = self._preflight(
            bindings,
            event,
            payload,
            allow_async=True,
        )
        responses: list[object] = []
        with self._dispatching():
            for binding, arguments in callbacks:
                result = await self._invoke_async(
                    binding,
                    arguments,
                )
                if result is False:
                    break
                responses.append(result)
        return responses

    def until(
        self,
        event: object | str,
        payload: object = _MISSING,
    ) -> object | None:
        """Return the first non-None listener result.

        Args:
            event: Event object or exact named event.
            payload: One explicit named-event payload, including ``None``.

        Returns:
            First non-None response, including ``False`` or zero.
        """
        if self._capture_or_defer(event, payload):
            return None
        bindings = self._matching_bindings(event)
        callbacks = self._preflight(bindings, event, payload)
        with self._dispatching():
            for binding, arguments in callbacks:
                result = self._invoke_sync(binding, arguments)
                if result is not None:
                    return result
        return None

    async def until_async(
        self,
        event: object | str,
        payload: object = _MISSING,
    ) -> object | None:
        """Asynchronously return the first non-None listener result.

        Args:
            event: Event object or exact named event.
            payload: One explicit named-event payload, including ``None``.

        Returns:
            First non-None response, including ``False`` or zero.
        """
        if self._capture_or_defer(event, payload):
            return None
        bindings = self._matching_bindings(event)
        callbacks = self._preflight(
            bindings,
            event,
            payload,
            allow_async=True,
        )
        with self._dispatching():
            for binding, arguments in callbacks:
                result = await self._invoke_async(
                    binding,
                    arguments,
                )
                if result is not None:
                    return result
        return None

    def forget(
        self,
        event: EventSelector,
        listener: object | None = None,
    ) -> None:
        """Remove registrations containing a selector and optional target.

        Args:
            event: Selector whose registrations should be removed.
            listener: Optional target identity limiting removal.
        """
        with self._lock:
            for binding in self._binding_snapshot():
                if event not in binding.selectors:
                    continue
                if listener is None or binding.target is listener:
                    self._forget_binding(binding)

    def subscribe(self, subscriber: object | type[object]) -> None:
        """Register several listeners through one subscriber object.

        A class is constructed through the application container. An instance
        is retained only through listeners it registers, so callers should
        pass application-lifetime instances.

        Args:
            subscriber: Class or instance exposing ``subscribe(dispatcher)``.

        Raises:
            AsyncDispatchRequiredError: If subscription itself is async.
            EventRegistrationError: If the subscriber shape is invalid.
        """
        instance = self._subscriber_instance(subscriber)
        callback = getattr(instance, "subscribe", None)
        if not callable(callback):
            raise EventRegistrationError(_SUBSCRIBER_METHOD_ERROR)
        if _is_async_callback(callback):
            raise AsyncDispatchRequiredError(_ASYNC_SUBSCRIBER_ERROR)
        if self._container is None:
            result = callback(self)
        else:
            result = self._container.call(
                callback,
                _named_arguments(callback, "dispatcher", self),
            )
        self._register_subscription_result(instance, result)

    async def subscribe_async(
        self,
        subscriber: object | type[object],
    ) -> None:
        """Resolve and execute one subscriber through the async container.

        Args:
            subscriber: Class or instance exposing ``subscribe(dispatcher)``.

        Raises:
            EventRegistrationError: If the subscriber shape is invalid.
        """
        instance = await self._subscriber_instance_async(subscriber)
        callback = getattr(instance, "subscribe", None)
        if not callable(callback):
            raise EventRegistrationError(_SUBSCRIBER_METHOD_ERROR)
        if self._container is None:
            result = callback(self)
            if inspect.isawaitable(result):
                result = await cast("Awaitable[object]", result)
        else:
            result = await self._container.call_async(
                callback,
                _named_arguments(callback, "dispatcher", self),
            )
        self._register_subscription_result(instance, result)

    def _subscriber_instance(self, subscriber: object | type[object]) -> object:
        """Resolve a subscriber class synchronously when necessary.

        Args:
            subscriber: Subscriber instance or class.

        Returns:
            Instance used to register one related listener group.
        """
        if not isinstance(subscriber, type):
            return subscriber
        subscriber_type = cast("type[object]", subscriber)
        if self._container is not None:
            return self._container.make(subscriber_type)
        return subscriber_type()

    async def _subscriber_instance_async(
        self,
        subscriber: object | type[object],
    ) -> object:
        """Resolve a subscriber class through async dependency creation.

        Args:
            subscriber: Subscriber instance or class.

        Returns:
            Instance used to register one related listener group.
        """
        if not isinstance(subscriber, type):
            return subscriber
        subscriber_type = cast("type[object]", subscriber)
        if self._container is not None:
            return await self._container.make_async(subscriber_type)
        return subscriber_type()

    def _register_subscription_result(
        self,
        instance: object,
        result: object,
    ) -> None:
        """Apply a declarative event-to-method subscriber mapping.

        Args:
            instance: Subscriber retained by explicit method references.
            result: Optional mapping returned by its subscribe method.

        Raises:
            EventRegistrationError: If a mapping contains invalid targets.
        """
        if result is None:
            return
        if not isinstance(result, Mapping):
            raise EventRegistrationError(_SUBSCRIBER_MAPPING_ERROR)
        declarations = cast("Mapping[object, object]", result)
        for event, raw_targets in declarations.items():
            if not isinstance(event, (str, type)):
                raise EventRegistrationError(_SUBSCRIBER_KEY_ERROR)
            targets: Sequence[object] | tuple[object, ...] = (
                cast("Sequence[object]", raw_targets)
                if isinstance(raw_targets, Sequence)
                and not isinstance(raw_targets, (str, bytes))
                else (raw_targets,)
            )
            for target in targets:
                listener_target = (
                    ListenerReference(instance, target)
                    if isinstance(target, str)
                    else target
                )
                self.listen(event, listener_target)

    def push(self, event: str, payload: object = _MISSING) -> None:
        """Retain a named event payload for explicit later flushing.

        Pushed values remain registered after a flush, matching Laravel's
        repeated-flush behavior. They are bounded and never durable jobs.

        Args:
            event: Exact event name used by :meth:`flush`.
            payload: Explicit named-event payload, if provided.

        Raises:
            DeferredBufferOverflowError: If the push bound is reached.
        """
        if not event or "*" in event:
            raise EventRegistrationError(_PUSHED_NAME_ERROR)
        with self._lock:
            count = sum(len(values) for values in self._pushed.values())
            if count >= self._deferred_buffer_limit:
                raise DeferredBufferOverflowError(_MAX_BUFFER_MESSAGE)
            self._pushed.setdefault(event, []).append(payload)

    def flush(self, event: str) -> list[object]:
        """Dispatch every retained payload for one pushed event name.

        Args:
            event: Exact name previously supplied to :meth:`push`.

        Returns:
            Listener results in payload and registration order.
        """
        with self._lock:
            payloads = tuple(self._pushed.get(event, ()))
        responses: list[object] = []
        for payload in payloads:
            responses.extend(self.dispatch(event, payload))
        return responses

    async def flush_async(self, event: str) -> list[object]:
        """Asynchronously dispatch retained payloads for one event name.

        Args:
            event: Exact name previously supplied to :meth:`push`.

        Returns:
            Listener results in payload and registration order.
        """
        with self._lock:
            payloads = tuple(self._pushed.get(event, ()))
        responses: list[object] = []
        for payload in payloads:
            responses.extend(await self.dispatch_async(event, payload))
        return responses

    def forget_pushed(self) -> None:
        """Remove all named event payloads retained by :meth:`push`.

        Removing retained payloads leaves listener registrations active.
        """
        with self._lock:
            self._pushed.clear()

    @contextmanager
    def defer(
        self,
        events: Sequence[EventSelector] | None = None,
    ) -> Generator[None, None, None]:
        """Buffer selected events and dispatch them after successful work.

        Nested successful frames flush independently. Exceptions and
        cancellation discard the active frame's pending events.

        Args:
            events: Optional selectors to defer; ``None`` selects all events.

        Yields:
            Control while selected dispatch calls are buffered.
        """
        frame = self._new_deferred_frame(events)
        token = self._deferred.set(frame)
        try:
            yield
        except BaseException:
            frame.take()
            raise
        else:
            pending = frame.take()
            self._flush_deferred_sync(pending)
        finally:
            self._deferred.reset(token)

    @asynccontextmanager
    async def defer_async(
        self,
        events: Sequence[EventSelector] | None = None,
    ) -> AsyncGenerator[None, None]:
        """Buffer selected events and await them after successful work.

        Args:
            events: Optional selectors to defer; ``None`` selects all events.

        Yields:
            Control while selected dispatch calls are buffered.
        """
        frame = self._new_deferred_frame(events)
        token = self._deferred.set(frame)
        try:
            yield
        except BaseException:
            frame.take()
            raise
        else:
            pending = frame.take()
            await self._flush_deferred_async(pending)
        finally:
            self._deferred.reset(token)

    def fake(
        self,
        events: Sequence[EventSelector] | None = None,
    ) -> EventFake:
        """Create an execution-local fake for all or selected events.

        Args:
            events: Optional selectors to intercept; ``None`` selects all.

        Returns:
            A context manager that records matching dispatches.
        """
        return EventFake(
            self._activate_fake,
            self._deactivate_fake,
            self._is_listening,
            events,
        )

    def fake_except(self, events: Sequence[EventSelector]) -> EventFake:
        """Create a fake that intercepts every event except selected values.

        Args:
            events: Event selectors that continue through real dispatch.

        Returns:
            A context manager that records all other dispatches.
        """
        return EventFake(
            self._activate_fake,
            self._deactivate_fake,
            self._is_listening,
            None,
            except_selectors=events,
        )

    def _is_listening(
        self,
        event: EventSelector,
        listener: object | None,
    ) -> bool:
        """Check exact selector registration targets without invoking them.

        Args:
            event: Selector recorded in the listener registration.
            listener: Optional target identity to check.

        Returns:
            Whether one active registration matches both values.
        """
        return any(
            event in binding.selectors
            and (listener is None or binding.target is listener)
            for binding in self._binding_snapshot()
        )

    def _activate_fake(self, fake: EventFake) -> Token[tuple[EventFake, ...]]:
        """Append one fake to the task-local interception stack.

        Args:
            fake: Recorder entering its context.

        Returns:
            Context token used to restore the previous fake stack.
        """
        current = self._fakes.get()
        return self._fakes.set((*current, fake))

    def _deactivate_fake(self, token: Token[tuple[EventFake, ...]]) -> None:
        """Restore the fake stack that preceded one context.

        Args:
            token: Token returned by :meth:`_activate_fake`.
        """
        self._fakes.reset(token)

    def _capture_or_defer(self, event: object | str, payload: object) -> bool:
        """Intercept a selected fake or append to an active deferred frame.

        Args:
            event: Event value about to be dispatched.
            payload: Explicit payload or the missing sentinel.

        Returns:
            Whether dispatch was intercepted.
        """
        if not isinstance(event, str) and payload is not _MISSING:
            raise TypeError(_INVALID_PAYLOAD_ERROR)
        for fake in reversed(self._fakes.get()):
            if fake.matches(event):
                fake.record(
                    EventRecord(
                        event,
                        None if payload is _MISSING else payload,
                        payload is not _MISSING,
                    ),
                )
                return True
        frame = self._deferred.get()
        while frame is not None:
            if (
                frame.active
                and _frame_matches(frame, event)
                and frame.append(event, payload)
            ):
                return True
            frame = frame.parent
        return False

    def _new_deferred_frame(
        self,
        events: Sequence[EventSelector] | None,
    ) -> _DeferredFrame:
        """Create one selected, bounded child frame.

        Args:
            events: Optional selectors stored with the frame.

        Returns:
            A fresh frame linked to the currently active frame.
        """
        selectors = None if events is None else tuple(events)
        return _DeferredFrame(
            self._deferred.get(),
            selectors,
            self._deferred_buffer_limit,
        )

    def _flush_deferred_sync(
        self,
        events: Sequence[tuple[object | str, object]],
    ) -> None:
        """Dispatch a successful frame without recapturing its parent.

        Args:
            events: Pending event values in original call order.
        """
        token = self._deferred.set(None)
        try:
            self._preflight_deferred(events)
            for event, payload in events:
                self.dispatch(event, payload)
        finally:
            self._deferred.reset(token)

    async def _flush_deferred_async(
        self,
        events: Sequence[tuple[object | str, object]],
    ) -> None:
        """Await a successful frame without recapturing its parent.

        Args:
            events: Pending event values in original call order.
        """
        token = self._deferred.set(None)
        try:
            for event, payload in events:
                await self.dispatch_async(event, payload)
        finally:
            self._deferred.reset(token)

    def _preflight_deferred(
        self,
        events: Sequence[tuple[object | str, object]],
    ) -> None:
        """Validate every buffered event before synchronous side effects.

        Args:
            events: Buffered events about to be synchronously dispatched.
        """
        for event, payload in events:
            self._preflight(self._matching_bindings(event), event, payload)

    def _matching_bindings(
        self,
        event: object | str,
    ) -> tuple[_ListenerBinding, ...]:
        """Take a stable snapshot in exact, wildcard, then base-type order.

        Args:
            event: Event value matched against receiver metadata.

        Returns:
            Matching listeners in Laravel-compatible category order, retaining
            registration order within each category.
        """
        exact: list[_ListenerBinding] = []
        wildcard: list[_ListenerBinding] = []
        inherited: list[_ListenerBinding] = []
        for binding in self._binding_snapshot():
            category = _binding_match_category(binding, event)
            if category == _EXACT_EVENT_MATCH_CATEGORY:
                exact.append(binding)
            elif category == _WILDCARD_EVENT_MATCH_CATEGORY:
                wildcard.append(binding)
            elif category == _BASE_EVENT_MATCH_CATEGORY:
                inherited.append(binding)
        return (*exact, *wildcard, *inherited)

    def _binding_snapshot(self) -> tuple[_ListenerBinding, ...]:
        """Read active receiver registrations through Blinker public APIs.

        Returns:
            Receiver bindings in their configured insertion order.
        """
        with self._lock:
            receivers = self._signal.receivers_for_any()
            bindings: list[_ListenerBinding] = []
            for receiver in receivers:
                candidate = cast(
                    "object",
                    getattr(receiver, "__self__", None),
                )
                if isinstance(candidate, _ListenerBinding) and candidate.active:
                    bindings.append(candidate)
            return tuple(bindings)

    def _preflight(
        self,
        bindings: Sequence[_ListenerBinding],
        event: object | str,
        payload: object,
        *,
        allow_async: bool = False,
    ) -> tuple[tuple[_ListenerBinding, dict[str, object]], ...]:
        """Validate listener callbacks and reject async paths before execution.

        Args:
            bindings: Stable matching registration snapshot.
            event: Event value used to prepare explicit callback arguments.
            payload: Explicit named payload or the missing sentinel.
            allow_async: Permit coroutine callbacks on async dispatch paths.

        Returns:
            Ordered registrations and container injection arguments.

        Raises:
            AsyncDispatchRequiredError: If a listener is coroutine-only.
            EventRegistrationError: If a listener target or signature fails.
        """
        prepared: list[tuple[_ListenerBinding, dict[str, object]]] = []
        for binding in bindings:
            raw_callback = _raw_callback(binding.target)
            if not allow_async and _is_async_callback(raw_callback):
                raise AsyncDispatchRequiredError(_ASYNC_DISPATCH_MESSAGE)
            arguments = _event_arguments(
                raw_callback,
                event,
                payload,
                _binding_is_wildcard(binding, event),
            )
            prepared.append((binding, arguments))
        return tuple(prepared)

    def _invoke_sync(
        self,
        binding: _ListenerBinding,
        arguments: Mapping[str, object],
    ) -> object:
        """Resolve a listener and its remaining dependencies synchronously.

        Args:
            binding: Registration resolved for synchronous invocation.
            arguments: Event values that take precedence over injection.

        Returns:
            The synchronous callback result.
        """
        target = _resolve_callback_sync(binding, self._container)
        if self._container is not None:
            result = self._container.call(target, arguments)
        else:
            result = target(**arguments)
        _reject_awaitable_result(result)
        return result

    async def _invoke_async(
        self,
        binding: _ListenerBinding,
        arguments: Mapping[str, object],
    ) -> object:
        """Resolve and invoke a listener through the explicit async path.

        Args:
            binding: Registration resolved for asynchronous invocation.
            arguments: Event values that take precedence over injection.

        Returns:
            The resolved callback result.
        """
        target = await _resolve_callback_async(binding, self._container)
        if self._container is not None:
            return await self._container.call_async(target, arguments)
        result = target(**arguments)
        if inspect.isawaitable(result):
            return await cast("Awaitable[object]", result)
        return result

    @contextmanager
    def _dispatching(self) -> Generator[None, None, None]:
        """Enforce a context-local bound on recursive event dispatch.

        Yields:
            Control while one nested dispatch occupies a depth slot.

        Raises:
            EventError: If the configured dispatch depth is exceeded.
        """
        depth = self._dispatch_depth.get()
        if depth >= self._max_dispatch_depth:
            raise EventError(_DISPATCH_DEPTH_ERROR)
        token = self._dispatch_depth.set(depth + 1)
        try:
            yield
        finally:
            self._dispatch_depth.reset(token)

    def _forget_binding(self, binding: _ListenerBinding) -> None:
        """Disconnect one receiver without affecting active snapshots.

        Args:
            binding: Registration to remove from future dispatch snapshots.
        """
        with self._lock:
            if not binding.active:
                return
            binding.active = False
            self._signal.disconnect(binding.receiver)

    def claim_discovery(self, discovery_key: str) -> bool:
        """Claim one deterministic discovery entry at most once.

        Args:
            discovery_key: Stable module and member descriptor.

        Returns:
            Whether this call claimed a previously unseen descriptor.
        """
        with self._lock:
            if discovery_key in self._discovered:
                return False
            self._discovered.add(discovery_key)
            return True

    _container: Container | None
    _deferred_buffer_limit: int
    _max_dispatch_depth: int
    _signal: OrderedSignal
    _lock: RLock
    _deferred: ContextVar[_DeferredFrame | None]
    _fakes: ContextVar[tuple[EventFake, ...]]
    _dispatch_depth: ContextVar[int]
    _pushed: dict[str, list[object]]
    _discovered: set[str]


def _normalize_selectors(
    event: EventSelector | Sequence[EventSelector],
) -> tuple[EventSelector, ...]:
    """Convert one or several selectors to a validated immutable tuple.

    Args:
        event: Single event selector or an ordered sequence of selectors.

    Returns:
        Unique selectors in their original order.

    Raises:
        EventRegistrationError: If a selector is missing or unsupported.
    """
    raw_values: tuple[object, ...] = (
        (event,) if isinstance(event, (str, type)) else tuple(event)
    )
    if not raw_values or any(
        not _is_event_selector(value) for value in raw_values
    ):
        raise EventRegistrationError(_SELECTOR_ERROR)
    values = cast("tuple[EventSelector, ...]", raw_values)
    selectors = tuple(dict.fromkeys(values))
    if any(isinstance(value, str) and not value for value in selectors):
        raise EventRegistrationError(_EVENT_NAME_ERROR)
    return selectors


def _is_event_selector(value: object) -> bool:
    """Check untyped registration input for a supported selector shape.

    Args:
        value: Runtime value supplied at the registration boundary.

    Returns:
        Whether the value is an event name or Python class.
    """
    return isinstance(value, (str, type))


def _validate_target(target: object) -> None:
    """Reject listener values that cannot be resolved or invoked.

    Args:
        target: Listener target submitted for registration.

    Raises:
        EventRegistrationError: If no callback can be selected.
    """
    try:
        _raw_callback(target)
    except (AttributeError, TypeError) as error:
        message = "Listeners must be callable or expose a handle method."
        raise EventRegistrationError(message) from error


def _raw_callback(target: object) -> Callable[..., object]:
    """Select a raw callback while leaving class construction to Container.

    Args:
        target: Function, listener class, callable instance, or reference.

    Returns:
        Callback inspected before listener invocation.

    Raises:
        TypeError: If the target does not expose a supported callback.
    """
    if isinstance(target, ListenerReference):
        raw = getattr(target.target, target.method)
        return cast("Callable[..., object]", raw)
    if isinstance(target, type):
        raw = getattr(target, "handle", None)
        if raw is None:
            raise TypeError(_LISTENER_CLASS_ERROR)
        return cast("Callable[..., object]", raw)
    handle = getattr(target, "handle", None)
    if callable(handle) and not callable(target):
        return handle
    if callable(target):
        return target
    raise TypeError(_LISTENER_CALLABLE_ERROR)


def _event_arguments(
    callback: Callable[..., object],
    event: object | str,
    payload: object,
    wildcard: bool,
) -> dict[str, object]:
    """Map event values to listener parameter names for DI precedence.

    Args:
        callback: Raw callable inspected before execution.
        event: Event object or exact name.
        payload: Explicit named payload or the missing sentinel.
        wildcard: Whether a matching selector is a named glob.

    Returns:
        Explicit payload values keyed by callback parameter name.

    Raises:
        EventRegistrationError: If a wildcard callback has fewer than two
            positional parameters or its signature cannot be inspected.
    """
    try:
        parameters = tuple(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError) as error:
        raise EventRegistrationError(_LISTENER_SIGNATURE_ERROR) from error
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and parameter.name not in {"self", "cls"}
    ]
    if wildcard:
        if len(positional) < _WILDCARD_ARGUMENT_COUNT:
            raise EventRegistrationError(_WILDCARD_SIGNATURE_ERROR)
        value = event if isinstance(event, str) else (event,)
        named_payload = (
            (() if payload is _MISSING else payload)
            if isinstance(event, str)
            else value
        )
        return {
            positional[0].name: canonical_event_name(event),
            positional[1].name: named_payload,
        }
    if not positional:
        return {}
    if isinstance(event, str):
        return {} if payload is _MISSING else {positional[0].name: payload}
    return {positional[0].name: event}


def _resolve_callback_sync(
    binding: _ListenerBinding,
    container: Container | None,
) -> Callable[..., object]:
    """Resolve class listener targets before synchronous invocation.

    Args:
        binding: Listener registration selected by preflight.
        container: Application container, if this is an application listener.

    Returns:
        Bound callback ready for ``Container.call``.
    """
    target = binding.target
    if isinstance(target, ListenerReference):
        owner = target.target
        if isinstance(owner, type):
            owner_type = cast("type[object]", owner)
            instance: object = (
                container.make(owner_type)
                if container is not None
                else owner_type()
            )
            return cast(
                "Callable[..., object]", getattr(instance, target.method)
            )
        return cast("Callable[..., object]", getattr(owner, target.method))
    if isinstance(target, type):
        target_type = cast("type[object]", target)
        instance = (
            container.make(target_type)
            if container is not None
            else target_type()
        )
        return cast(
            "Callable[..., object]",
            getattr(instance, _HANDLE_METHOD_NAME),
        )
    handle = getattr(target, "handle", None)
    if callable(handle) and not callable(target):
        return handle
    if callable(target):
        return target
    raise EventRegistrationError(_LISTENER_CALLABLE_ERROR)


async def _resolve_callback_async(
    binding: _ListenerBinding,
    container: Container | None,
) -> Callable[..., object]:
    """Resolve class listener targets through async container construction.

    Args:
        binding: Listener registration selected by preflight.
        container: Application container, if this is an application listener.

    Returns:
        Bound callback ready for ``Container.call_async``.
    """
    target = binding.target
    if isinstance(target, ListenerReference):
        owner = target.target
        if isinstance(owner, type):
            owner_type = cast("type[object]", owner)
            instance: object = (
                await container.make_async(owner_type)
                if container is not None
                else owner_type()
            )
            return cast(
                "Callable[..., object]", getattr(instance, target.method)
            )
        return cast("Callable[..., object]", getattr(owner, target.method))
    if isinstance(target, type):
        target_type = cast("type[object]", target)
        instance = (
            await container.make_async(target_type)
            if container is not None
            else target_type()
        )
        return cast(
            "Callable[..., object]",
            getattr(instance, _HANDLE_METHOD_NAME),
        )
    handle = getattr(target, "handle", None)
    if callable(handle) and not callable(target):
        return handle
    if callable(target):
        return target
    raise EventRegistrationError(_LISTENER_CALLABLE_ERROR)


def _frame_matches(frame: _DeferredFrame, event: object | str) -> bool:
    """Check a deferred frame's selector policy.

    Args:
        frame: Frame currently considered for event interception.
        event: Event value about to be dispatched.

    Returns:
        Whether this frame captures the event.
    """
    return frame.selectors is None or any(
        selector_matches(selector, event) for selector in frame.selectors
    )


def _binding_is_wildcard(
    binding: _ListenerBinding,
    event: object | str,
) -> bool:
    """Check whether the event matched a named wildcard selector.

    Args:
        binding: Listener registration being prepared.
        event: Event value selected by dispatch.

    Returns:
        Whether a matching selector uses named wildcard semantics.
    """
    return any(
        selector_is_wildcard(selector) and selector_matches(selector, event)
        for selector in binding.selectors
    )


def _binding_match_category(
    binding: _ListenerBinding,
    event: object | str,
) -> int | None:
    """Choose the highest-priority matching selector category.

    Args:
        binding: Listener registration being prepared.
        event: Event value checked against its selectors.

    Returns:
        The exact, wildcard, or base-type category value, or ``None`` when
        this registration does not match.
    """
    category: int | None = None
    for selector in binding.selectors:
        if not selector_matches(selector, event):
            continue
        if isinstance(selector, str):
            selected_category = (
                _WILDCARD_EVENT_MATCH_CATEGORY
                if selector_is_wildcard(selector)
                else _EXACT_EVENT_MATCH_CATEGORY
            )
        elif not isinstance(event, str) and selector is type(event):
            selected_category = _EXACT_EVENT_MATCH_CATEGORY
        else:
            selected_category = _BASE_EVENT_MATCH_CATEGORY
        if category is None or selected_category < category:
            category = selected_category
    return category


def _is_async_callback(callback: Callable[..., object]) -> bool:
    """Identify coroutine functions and async callable objects.

    Args:
        callback: Raw callback selected for one listener registration.

    Returns:
        Whether invoking this callback requires ``await``.
    """
    if inspect.iscoroutinefunction(callback):
        return True
    call_method = callback.__call__
    if inspect.iscoroutinefunction(call_method):
        return True
    annotation_target = callback if inspect.isroutine(callback) else call_method
    try:
        return_annotation = get_type_hints(
            annotation_target,
            include_extras=True,
        ).get("return")
    except (NameError, TypeError, ValueError):
        return_annotation = inspect.signature(
            annotation_target,
        ).return_annotation
    return _annotation_is_awaitable(return_annotation)


def _annotation_is_awaitable(annotation: object) -> bool:
    """Identify declared awaitable results, including optional return types.

    Args:
        annotation: Resolved or inspectable callback return annotation.

    Returns:
        Whether the annotation includes an awaitable value.
    """
    origin = get_origin(annotation)
    if origin in (Awaitable, Coroutine):
        return True
    arguments = get_args(annotation)
    if origin is Annotated and arguments:
        return _annotation_is_awaitable(arguments[0])
    if origin in (Union, UnionType):
        return any(_annotation_is_awaitable(value) for value in arguments)
    return False


def _reject_awaitable_result(result: object) -> None:
    """Prevent synchronous dispatch from returning an awaitable response.

    Args:
        result: Value returned by a listener through the sync path.

    Raises:
        AsyncDispatchRequiredError: If the listener returned an awaitable.
    """
    if not inspect.isawaitable(result):
        return
    if inspect.iscoroutine(result):
        result.close()
    raise AsyncDispatchRequiredError(_ASYNC_DISPATCH_MESSAGE)


def _named_arguments(
    callback: Callable[..., object],
    parameter_name: str,
    value: object,
) -> dict[str, object]:
    """Map one explicit framework value to a callback parameter.

    Args:
        callback: Bound subscriber callback to inspect.
        parameter_name: Preferred conventional parameter name.
        value: Dispatcher supplied to the subscriber.

    Returns:
        The explicit parameter mapping used by container invocation.

    Raises:
        EventRegistrationError: If the subscriber does not accept a value.
    """
    try:
        parameters = tuple(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError) as error:
        message = "Subscriber signatures must be inspectable."
        raise EventRegistrationError(message) from error
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if not positional:
        message = "Subscribers must accept the event dispatcher argument."
        raise EventRegistrationError(message)
    selected = next(
        (
            parameter
            for parameter in positional
            if parameter.name == parameter_name
        ),
        positional[0],
    )
    return {selected.name: value}


__all__ = ["ListenerRegistration", "NativeEventDispatcher"]
