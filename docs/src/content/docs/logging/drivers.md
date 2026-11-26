---
title: "Logging drivers"
---

<span id="logging-drivers"></span>

Titanspan exposes destination names in its own configuration. Drivers are
Titanspan-owned implementations that delegate stream, file, rotation, syslog,
and transport work to maintained Python infrastructure.

| Driver | Configuration | Behavior |
| --- | --- | --- |
| `console` | `formatter`, `color` | Human-readable output to stderr. |
| `stdout` | `formatter`, `color` | Output to standard output. |
| `stderr` | `formatter`, `color` | Output to standard error. |
| `errorlog` | `formatter`, `color` | Alias for standard error output. |
| `single` | `path`, `formatter` | One append-only file. |
| `daily` | `path`, `days`, `formatter` | Midnight UTC rotation with retention. |
| `monthly` | `path`, `max_files`, `formatter` | UTC calendar-month rotation with retention. |
| `rotating` | `path`, `max_bytes`, `backup_count` | Size-based rotation. |
| `syslog` | optional `options.address` | Local or explicitly configured syslog destination. |
| `webhook` | `options.url`, optional headers and timeout | JSON record POST to a configured endpoint. |
| `slack` | `options.url`, optional headers and timeout | Slack-compatible `text` payload. |
| `memory` | `options.max_records` | Bounded in-memory records for tests and inspection. |
| `null` | none | Explicitly discard records. |
| `emergency` | none | Minimal stderr fallback output. |
| `stack` | `channels`, `ignore_exceptions` | Ordered fan-out to named channels. |
| custom | application factory | A native driver implementing `LogDriver`. |

The default syslog address is `/dev/log`. An address may also be a socket
path, host string, or `(host, port)` pair. The standard logging syslog handler
owns transport details, and Titanspan maps all eight RFC levels explicitly
without registering process-global Python log levels.

## Webhook options

The `options` mapping for `webhook` and `slack` accepts:

| Option | Meaning |
| --- | --- |
| `url` | Trusted endpoint URL; HTTPS is required by default. |
| `allow_http` | Permit HTTP for local integration tests only. |
| `timeout` | Bounded request timeout from greater than 0 to 60 seconds. |
| `headers` | Optional configured HTTP headers. |

Credentials in URL userinfo, URL fragments, unsafe header names, framing
headers, and malformed URLs are rejected. Redirects are not followed. This
driver is intended for trusted deployment configuration and is not a general
SSRF defense for user-controlled URLs.

## Custom drivers

Use the `LogDriver` protocol and register a factory on `LogManager`:

```python
manager.extend("audit_sink", create_audit_driver)
```

The driver receives sanitized native `LogRecord` values through `write`,
implements `flush`, and releases resources through `close`. A driver that
supports native async delivery may also implement `AsyncLogDriver`. No
backend logger or handler object is required in application code.

## Channel customizers

Register a native customizer with the manager and name it in the channel's
`tap` sequence. Customizers run once when a channel is created, before it is
cached. The manager closes the channel if customization fails.

```python
from titanspan.logging import LogCustomizer, LogManager, Logger, MessageLogged


class CaptureMessages:
    """Connect channel messages to an application-owned event list.

    The customizer receives only Titanspan logging types.
    """

    def __init__(self) -> None:
        """Initialize the event collection used by this customizer."""
        self.messages: list[MessageLogged] = []

    def customize(self, logger: Logger) -> None:
        """Attach a listener to the newly created channel.

        Args:
            logger: Titanspan logger being initialized.
        """
        logger.listen(self.messages.append)


customizer = CaptureMessages()
typed_customizer: LogCustomizer = customizer
manager = LogManager(
    {
        "channels": {
            "default": {
                "driver": "console",
                "tap": ["capture"],
            },
        },
    },
    customizers={"capture": typed_customizer},
)
```

Customizers are registered as native objects instead of import paths. This
keeps configuration explicit and avoids resolving arbitrary code from a
string. Async customizers are unsupported because channel resolution is
synchronous.

Deprecation routing and backend-specific handler configuration are not
currently supported. See the
[component specification](/titanspan/specifications/logging/) for current status.
