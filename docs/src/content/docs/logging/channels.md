---
title: "Channels and stacks"
---

<span id="channels-and-stacks"></span>

A channel is a named configuration and a `Logger` wrapper. Resolve a channel
through the facade or its manager:

```python
from titanspan.facades import Log

Log.channel("audit").notice("Policy changed", policy_id="p-17")
```

The manager caches configured channels. `forget_channel(name)` closes and
removes a cached channel while leaving its configuration available for a
later fresh resolution. `purge(name)` is the explicit equivalent. A stack
that references a forgotten channel is also evicted so it cannot retain a
closed child.

## On-demand channels

`Log.build(configuration)` creates an independently owned channel. Use its
context manager to close it when the work finishes:

```python
with Log.build(
    {
        "driver": "single",
        "name": "import-run",
        "path": "storage/logs/import.log",
        "level": "debug",
        "formatter": "json",
    },
) as import_log:
    import_log.info("Import started", batch_id="batch-4")
```

Closing an on-demand channel closes only its own driver. It does not close
channels shared by the application manager. The manager also tracks on-demand
channels and closes any that remain open during application shutdown.

## Stacks

Stacks deliver to children in the configured order. Each child applies its
own severity threshold, formatter, processors, and destination. Duplicate
child names and recursive references are rejected during configuration
validation.

```python
Log.stack(["console", "audit"], channel="combined").info(
    "Import completed",
    batch_id="batch-4",
)
```

By default, a child delivery error is raised to the caller. Set
`ignore_exceptions=True` on a stack to continue after failed children. The
stack records bounded, payload-free failure type diagnostics and reports a
`partial` delivery status. Ignoring exceptions does not mean all destinations
succeeded.

Stacks coordinate delivery but do not own shared children. The manager owns
configured child channels and controls their flush and close order.
