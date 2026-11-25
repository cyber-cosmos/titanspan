# Logging

Titanspan provides an early native logging component with structured records,
named channels, standard severity levels, context-local metadata, file and
stream destinations, bounded background dispatch, and a Python logging
bridge.

The application API belongs to Titanspan. The component delegates structured
dispatch to Structlog and file, stream, rotation, and syslog handling to
Python's standard logging infrastructure. Application code uses Titanspan
types and configuration; it does not configure backend processors or
handlers.

## Quick start

`Application` owns a `LogManager` and binds it to the active HTTP execution
scope. Standalone use can bind a manager explicitly:

```python
from titanspan.facades import Log
from titanspan.logging import LogManager

manager = LogManager(
    {
        "default": "console",
        "channels": {
            "console": {
                "driver": "console",
                "level": "info",
                "formatter": "console",
            },
        },
    },
)

with Log.use(manager):
    Log.info("Application started", component="api")

manager.close()
```

The configured severity uses RFC 5424 values. `LogLevel` defines `emergency`,
`alert`, `critical`, `error`, `warning`, `notice`, `info`, and `debug`.

## Guides

- [Configuration](./configuration): validated channel settings.
- [Channels and stacks](./channels): channel resolution and fan-out.
- [Drivers](./drivers): supported output destinations.
- [Context](./context): task-local and shared metadata.
- [Structured records](./structured-logging): values, exceptions, and schema.
- [Async logging](./async-logging): thread offloading and bounded queues.
- [Security](./security): redaction and payload limits.
- [Testing](./testing): in-memory logging fakes and assertions.
- [Deployment](./deployment): stdout collection and process boundaries.
- [Laravel compatibility](../compatibility/laravel-logging): pinned API
  inventory and documented differences.

## Current limits

This component is still early-stage. It does not yet provide Laravel's
deprecation channel, full context repository,
event-dispatcher integration, or Monolog extension surface. The
compatibility inventory records each item and its status. Do not infer these
features from similarly named APIs.
