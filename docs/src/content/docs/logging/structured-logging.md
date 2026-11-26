---
title: "Structured logging"
---

<span id="structured-logging"></span>

`LogRecord` is the stable Titanspan record format. It contains an aware UTC
timestamp, a native `LogLevel`, channel name, single-line message, bounded
context mapping, and optional exception metadata.

```python
Log.info(
    "Workflow completed",
    {"workflow_id": "wf-123", "duration_ms": 425},
    status="success",
)
```

Keyword values override duplicate keys in the mapping. The record is copied
and made immutable at its top-level boundary before any driver sees it.
`LogRecord.to_dict()` returns the machine-readable JSON-compatible schema.

Supported values include strings, booleans, integers, finite and non-finite
floats, `None`, enums, UUIDs, dates, aware datetimes, mappings, sized
sequences, and byte buffers represented by their size. Naive nested datetime
values and non-string mapping keys are rejected. Unknown objects are
represented by their qualified type name; Titanspan does not call arbitrary
`repr`, serialize model attributes, or inspect object fields.

Messages and nested text are bounded. Context nesting is limited to eight
levels and collections to one hundred entries per level. Excess content is
marked as truncated. Context values are redacted before queueing and
destination delivery.

Exception records include type, sanitized message, and formatted traceback
text without live frame objects or local-variable capture. `exception(...)`
uses the active exception when called in an exception handler; an exception
can also be supplied explicitly. It raises `InvalidLogContextError` if the
provided value is not an exception.

JSON output uses the same Titanspan record schema for console, file, syslog,
and webhook drivers. Backend-specific event dictionaries are private.
