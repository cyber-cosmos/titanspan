---
title: "Dispatching events"
---

# Dispatching events

The dispatcher preserves event payloads as ordinary Python values. Use a
dataclass or another object for typed events. Use a string when a named event
family is more useful.

## Class and named events

Register a class, function, callable object, listener class, or
`ListenerReference`. A listener class must provide `handle()`. The native
container constructs listener classes inside the active application scope.

```python
class NotifyDocumentOwner:
    """Send a notification through an injected application service."""

    def __init__(self, notifications: NotificationService) -> None:
        """Retain the service resolved by the native container.

        Args:
            notifications: Application-owned notification service.
        """
        self._notifications = notifications

    async def handle(self, event: DocumentProcessed) -> None:
        """Notify the owner of the completed document.

        Args:
            event: Event value passed explicitly by the dispatcher.
        """
        await self._notifications.send(event.document_id)
```

For a named event, an exact listener receives its payload as the first
argument. An omitted payload supplies no argument. An explicit `None` remains
a supplied payload.

```python
Event.dispatch("workflow.completed", {"workflow_id": "run-1"})
```

Event class names use the fully qualified Python name
`module.qualname`. Exact class selectors match by class identity. Base classes
and runtime-checkable protocols match through Python's `isinstance()` rules.
Non-runtime-checkable protocols raise `EventRegistrationError` when matched.

## Listener order and results

Each dispatch takes one stable registration snapshot. Titanspan runs exact
class or name listeners first, named wildcard listeners second, then base
class or protocol listeners. Registrations keep their order within each
group. A listener registered more than once runs once per registration.

Listeners may register or remove listeners while dispatch runs. Those
changes affect the next dispatch. They do not change the current snapshot.

Ordinary dispatch returns listener responses in order. Returning the exact
boolean `False` stops propagation and does not appear in that result list.
The values `0`, `""`, `[]`, and `None` do not stop propagation.

`until()` returns the first response that is not `None`. It can return
`False`, zero, or an empty collection. The explicit asynchronous methods
provide the same result and propagation rules.

## Synchronous and asynchronous listeners

`dispatch()` executes only sync-safe listeners. It checks coroutine
callbacks and declared awaitable return types before invoking any listener.
It raises `AsyncDispatchRequiredError` when asynchronous work matches. Use
`dispatch_async()` to execute mixed listeners.

The asynchronous path resolves each listener through the native container,
awaits asynchronous callbacks, and preserves sequential ordering. Callback
exceptions and cancellation propagate to the caller.

Event parameters take precedence over service injection. The dispatcher
matches explicit event values by callback parameter name, then asks the
container to resolve remaining dependencies through `call()` or
`call_async()`.

Annotate callbacks that return awaitables. A broad or unresolved return
annotation prevents preflight. If that callback returns an awaitable, sync
dispatch closes coroutine results and raises `AsyncDispatchRequiredError`
when it reaches the listener. Earlier sync listeners may already have run.
The Container does not expose a public non-resolving check for async-only
dependency paths. An injected async-only dependency can therefore fail after
an earlier listener runs. Use `dispatch_async()` for such dependency graphs.

## Wildcard listeners

Use string patterns to observe named event families:

```python
Event.listen("workflow.*", record_workflow_activity)
```

Wildcard listeners receive the fully qualified event name and one payload
value. A missing named payload is represented by an empty tuple; an explicit
`None` remains `None`. For a class event, the payload is a one-item tuple
containing the original event object.

Patterns use Python's `fnmatchcase()` semantics, including `*`, `?`, and
character classes. Titanspan evaluates patterns at dispatch time and keeps no
per-event wildcard cache.

## Conditional class dispatch

`Dispatchable.dispatch_if()` and `dispatch_unless()` evaluate a boolean or
synchronous predicate before constructing the event. Their asynchronous
counterparts also accept an awaitable predicate. A skipped condition returns
`None` and does not construct or dispatch an event.

`event()` and `event_async()` dispatch an existing event through the active
application. They require no event inheritance.
