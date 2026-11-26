---
title: "Events"
---

# Events

Events lets application components notify listeners without depending on
each listener's implementation. Titanspan uses Blinker to retain listener
registrations and applies framework ordering, dependency injection, and
application lifecycle rules around it.

Events can dispatch plain Python objects, typed classes, or named string
events. It works in an application or with a standalone dispatcher. Event
objects remain in memory. Titanspan does not serialize them automatically.

## Declare an event

Use a frozen dataclass when an event should carry a stable value snapshot.
Event classes do not need to inherit from a Titanspan base class.

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentProcessed:
    """Identify a completed document operation."""

    document_id: str
    workflow_id: str
```

The optional `Dispatchable` mixin adds class-based convenience methods. See
[Dispatching](dispatching.md).

## Register and dispatch

Use the `Event` facade when an application context is active:

```python
from titanspan.facades import Event

Event.listen(DocumentProcessed, notify_owner)
responses = Event.dispatch(DocumentProcessed("doc-1", "run-1"))
```

The facade resolves the same dispatcher as constructor injection and the
`event()` helpers. See [Listeners and discovery](listeners.md) for listener
forms and registration options.

## Use the asynchronous path

Synchronous dispatch accepts sync-safe listeners. Use `dispatch_async()` when
any matching listener is asynchronous:

```python
responses = await Event.dispatch_async(
    DocumentProcessed("doc-1", "run-1"),
)
```

Async dispatch runs listeners sequentially and awaits each listener before
starting the next. It does not create background tasks or parallel work.

## Available integrations

The dispatcher, listener injection, scoped fakes, deferred dispatch, trusted
module discovery, and JSON manifests are implemented. Queue execution,
database transaction callbacks, broadcasting, and event CLI commands await
their owning Titanspan components.

Read [dispatch semantics](dispatching.md),
[listeners and discovery](listeners.md),
[testing and lifecycle](testing.md), and the
[behavioral specification](../specifications/events.md).
