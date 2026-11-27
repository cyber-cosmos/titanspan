---
title: "Logging"
---

<span id="logging"></span>

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
from titanspan import Application
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

application = Application()
with application.context(), Log.use(manager):
    Log.info("Application started", component="api")

manager.close()
```

`Log.use()` replaces the application manager through the Container. It is
useful for isolated tests and explicit execution-local substitution. Normal
application code resolves the configured manager without a replacement.

The configured severity uses RFC 5424 values. `LogLevel` defines `emergency`,
`alert`, `critical`, `error`, `warning`, `notice`, `info`, and `debug`.

## Guides

- [Configuration](/framework/logging/configuration/): validated channel settings.
- [Channels and stacks](/framework/logging/channels/): channel resolution and fan-out.
- [Drivers](/framework/logging/drivers/): supported output destinations.
- [Context](/framework/logging/context/): task-local and shared metadata.
- [Structured records](/framework/logging/structured-logging/): values, exceptions, and schema.
- [Async logging](/framework/logging/async-logging/): thread offloading and bounded queues.
- [Security](/framework/logging/security/): redaction and payload limits.
- [Testing](/framework/logging/testing/): in-memory logging fakes and assertions.
- [Deployment](/framework/logging/deployment/): stdout collection and process boundaries.
- [Native logging specification](/framework/specifications/logging): implemented
  boundaries and deferred work.

## Current limits

This component is still early-stage. It does not yet provide a deprecation
channel, the complete event-dispatcher integration, or every destination
available from its implementation dependencies. The native specification
records current boundaries. Do not infer features from similarly named APIs.
