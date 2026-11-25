# Logging component specification

`titanspan.logging` owns the public log levels, records, loggers, channels,
manager, drivers, formatters, processors, events, and testing utilities.
Private adapters may use mature Python logging libraries. Importing Titanspan
does not configure process-global logging state.

## Implemented API

| Area | Public owner | Evidence |
| --- | --- | --- |
| Severity and records | `LogLevel`, `LogRecord`, `LogValue` | `tests/unit/logging/test_level.py`, `test_record.py` |
| Logger and channels | `Logger`, `LogChannel` | `tests/unit/logging/test_logger.py`, `test_channel.py` |
| Configuration and resolution | `LoggingConfiguration`, `ChannelConfiguration`, `LogManager` | `tests/unit/logging/test_manager.py`, `test_configuration.py` |
| Native output formats | Console, JSON, and text formatters | `tests/unit/logging/test_formatters.py` |
| Redaction and processing | `LogProcessor`, `RedactionProcessor` | `tests/unit/logging/test_processors.py`, `test_redaction.py` |
| In-memory testing | `MemoryLogDriver` and facade assertions | `tests/unit/logging/test_fake.py`, `test_logging_public_api.py` |
| Standard-library integration | `StandardLogBridge` | `tests/integration/logging/` |
| Delivery and lifecycle | Native drivers, events, and failure policies | `tests/unit/logging/`, `tests/integration/logging/` |

## Behavioral guarantees

- Public methods use one `snake_case` spelling. Do not add compatibility-only
  aliases or wrappers.
- Context is execution-local and captured before background delivery.
- Redaction runs before events, queues, formatters, and transports.
- Queues are bounded. Delivery status distinguishes accepted, delivered,
  dropped, and failed records.
- Async APIs do not create an unmanaged task per record or block on queue
  capacity from an event-loop thread.
- Log levels map explicitly between Titanspan severity and standard-library
  levels.
- Emergency output avoids the failing logger and does not recursively log.
- File rotation and shared-file process safety follow the documented driver
  constraints; multiprocess delivery is not promised by ordinary handlers.
- Arbitrary object representations and full application payloads are never
  serialized automatically.

## Deferred behavior

External destinations and framework-specific execution metadata require
explicit configuration or an implemented integration hook. No paid service
or live external destination is part of the default test suite.

## Verification

Focused unit behavior is under `tests/unit/logging/`. Real standard-library,
file, lifecycle, and local network integration is under
`tests/integration/logging/`. Operational details are documented in
`docs/logging/`.
