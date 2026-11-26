---
title: "Testing and execution lifecycle"
---

# Testing and execution lifecycle

Use the dispatcher fake to record events without invoking real listeners.
The fake implements the dispatcher interception used by the facade, helpers,
and injected dispatcher.

```python
with Event.fake([DocumentProcessed]) as fake:
    service.process(document)
    fake.assert_dispatched(DocumentProcessed, times=1)
```

`fake()` intercepts all events when called without selectors. Pass selected
event types or names to intercept only those events. `fake_except()` records
all events except its selected values. Use `dispatched()` to filter records
by selector or predicate. Use `assert_not_dispatched()` and
`assert_nothing_dispatched()` for negative assertions. Use
`assert_listening()` and `assert_not_listening()` to check an exact selector
and listener target by identity.

Fakes are bound to the current execution context. Nested fake scopes restore
the earlier fake when they exit. Child tasks inherit their parent's context,
as defined by Python `ContextVar` behavior. A fake that has exited stops
recording even if a child task retains the inherited reference.

## Deferred dispatch

Use `defer()` to buffer selected dispatch calls until a synchronous block
completes successfully. Use `defer_async()` for asynchronous work:

```python
from titanspan.facades import Event


async with Event.defer_async():
    await create_document()
    await update_metadata()
```

Events flush in their original order after successful completion. A failed
block or cancellation discards its pending events. A nested successful block
flushes at its own boundary, before its parent's remaining events. Each frame
uses the configured buffer limit.

Child tasks inherit the active deferred frame. Their dispatches join that
frame while it remains active. If the owner exits first, a later child
dispatch follows an active parent frame or runs normally.

Deferred dispatch is an in-process lifecycle convenience. It does not track
database transactions, persist events, retry delivery, or guarantee delivery
after process failure.

## Pushed events

`push(name, payload)` retains a named payload until `flush(name)` dispatches
it. Flush leaves the payload registered, so a later flush dispatches it
again. Call `forget_pushed()` to clear all retained payloads. Pushed values
remain in memory and share the configured buffer bound. They are not Queue
jobs.

## Context, concurrency, and AI workflows

An application owns one dispatcher. Independent applications receive
independent listener registries and fake state. The registry lock protects
registration snapshots but is not held while listeners execute. Concurrent
async dispatches can therefore interleave listener calls across tasks;
each dispatch itself preserves sequential listener order.

Listeners run in the active application context. Container resolution uses
the current native execution scope, so scoped services remain bound to the
request, job, or other supported context. Events does not copy or serialize
event values and does not create background work.

AI, agent, tool, and workflow components can define their own event classes
and depend on the dispatcher contract. Queue, durable workflow replay,
transaction callbacks, high-frequency streaming, remote broadcasting, and
exactly-once delivery require separate components. Listener side effects are
not replay-safe by default.
