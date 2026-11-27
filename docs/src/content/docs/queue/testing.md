---
title: "Test queue dispatch"
description: "Assert Queue and Bus behavior without connecting to a broker."
---

Queue fakes replace broker and inline execution effects for one execution
context. A fake belongs to its application manager. It does not install a
process-wide broker replacement.

## Record dispatches

```python
from titanspan.facades.queue import Queue


async def test_submit_document() -> None:
    """Verify one service dispatches the expected payload."""
    async with Queue.fake() as fake:
        await Queue.dispatch_async(
            ProcessDocument(42),
            connection="redis",
            queue="documents",
        )

        fake.assert_pushed(ProcessDocument)
        fake.assert_pushed_count(ProcessDocument, 1)
        fake.assert_pushed_on("documents")
        fake.assert_pushed_on_connection("redis")
        fake.assert_pushed_with(
            ProcessDocument,
            document_id=42,
        )
```

The fake is available through `Queue.fake()` and `Bus.fake()`. Both facades,
the injected `QueueDispatcher`, and direct `QueueManager` calls use the same
application manager. Fake dispatch does not instantiate the broker or run the
handler.

## Nested and concurrent contexts

Nested fakes restore the preceding fake when their context exits. Separate
application managers keep separate fakes. A child task that inherits a fake
context cannot publish after the owning fake closes; Queue raises an error
instead of sending the job to a real broker.

Use real Redis integration tests for publication, worker consumption, retry,
and chain continuation. A fake does not verify transport acknowledgements or
worker behavior.

## Assertions

`QueueFake` provides `assert_pushed`, `assert_pushed_count`,
`assert_nothing_pushed`, `assert_pushed_on`,
`assert_pushed_on_connection`, `assert_pushed_with`, and
`assert_pushed_delayed`. Selective faking, job execution helpers, failure
assertions, and fluent chain matchers are not implemented.
