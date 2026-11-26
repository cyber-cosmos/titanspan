---
title: "ADR 0012: Native logging API over private Python backends"
---

<span id="adr-0012-native-logging-api-over-private-python-backends"></span>

- Status: Accepted
- Date: 2026-11-25

## Context

Titanspan needs structured, contextual logging for asynchronous applications
while keeping its application API independent of one Python logging backend.
Python's standard logging package provides mature stream, file, rotation, and
syslog handlers. Structlog provides structured dispatch and standard logging
interoperability.

The initial application lifecycle already owns configuration, dependency
resources, request scopes, and shutdown. A logging manager must therefore be
an application-owned resource rather than a process-global singleton. Slow
sinks and multi-process deployments also require explicit limits and lifecycle
semantics.

## Decision

Titanspan owns `LogRecord`, `LogLevel`, `Logger`, `LogManager`, channel and
driver contracts, formatters, processors, redaction, exceptions, events,
configuration, and testing helpers. Direct backend integration stays in
`titanspan.logging._backends`.

Use Structlog for isolated structured dispatch and standard logging handlers
for stream, file, rotation, and syslog destinations. Keep the standard
library's process-global root logger configuration unchanged. Provide an
explicit bridge for selected standard-library loggers.

Represent severity using RFC 5424 ordering in the public API and translate it
at the backend boundary. Preserve all eight native severity values without
registering process-global Python level names.

Keep context in execution-local `ContextVar` values. Redact structured fields
before delivery, bound record values and background buffers, expose explicit
delivery status, and close logger resources during application shutdown.

## Alternatives considered

- Expose Structlog loggers and processor configuration directly: rejected
  because it would make backend details part of the public API.
- Use only Python's standard logger as the public abstraction: rejected
  because Titanspan needs native RFC levels, structured records, context
  semantics, and test assertions.
- Implement file rotation, queue workers, and distributed storage from
  scratch: rejected where mature standard handlers or explicit external
  collectors already provide those capabilities.
- Store shared context in global mutable dictionaries: rejected because
  concurrent requests and workflow tasks would leak values.

## Consequences

- Application APIs use Titanspan types and can replace the backend adapter.
- Python's standard logging ecosystem can be bridged explicitly.
- Blocking handlers can run through bounded background dispatch or an
  explicit async method that offloads work.
- Background delivery is in-process and does not promise durable or exactly
  once delivery.
- Deprecation routing, the full context repository, and global
  event-dispatcher integration remain pending.
- Backend-specific interoperability is an explicit extension boundary and
  must not leak into ordinary logging tutorials.

## Risks

- Context propagation and worker shutdown need ongoing concurrency tests.
- Standard logging handlers do not coordinate shared rotating files across
  independent processes.
- Redaction by field name cannot detect every secret embedded in free-form
  messages.
- A backend integration upgrade may alter dispatch behavior; verify it against
  the locked package and integration suite.

## References

- [Python logging handlers](https://docs.python.org/3/library/logging.handlers.html)
- [Structlog standard-library integration](https://www.structlog.org/en/stable/standard-library.html)
- [RFC 5424](https://www.rfc-editor.org/rfc/rfc5424)
