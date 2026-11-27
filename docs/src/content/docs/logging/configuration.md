---
title: "Logging configuration"
---

<span id="logging-configuration"></span>

`LogManager` accepts either a validated `LoggingConfiguration` or a mapping.
`Application(logging=...)` passes the same native configuration to the
application-owned manager. There is no automatic `config/logging.py` loader
yet; applications may keep a mapping in that file and pass it explicitly.

```python
logging_configuration = {
    "default": "application",
    "channels": {
        "application": {
            "driver": "console",
            "level": "info",
            "formatter": "console",
            "tap": ["capture"],
        },
        "audit": {
            "driver": "daily",
            "path": "storage/logs/audit.log",
            "days": 14,
            "level": "notice",
            "formatter": "json",
        },
    },
}
```

The top-level `default` is a configured channel name. Channel configuration
is validated before a logger is resolved. Unknown fields, invalid severity
levels, missing stack references, duplicate stack children, unknown drivers,
unknown formatters, invalid file options, and recursive stack graphs fail
explicitly.

## Channel fields

| Field | Meaning |
| --- | --- |
| `driver` | Native driver identifier. |
| `name` | Optional record name for a dynamically built channel. |
| `level` | Lowest accepted RFC severity; default is `debug`. |
| `formatter` | `console`, `text`, `json`, or a registered formatter. |
| `path` | File path for `single`, `daily`, `monthly`, and `rotating`. |
| `days` | Daily file retention count; default is 14. |
| `max_files` | Monthly archive retention count; default is 3. |
| `max_bytes` | Rotating file size bound; default is 10 MiB. |
| `backup_count` | Number of rotated files to retain; default is 5. |
| `channels` | Ordered children for a `stack` driver. |
| `tap` | Ordered registered native customizer names. |
| `ignore_exceptions` | Continue stack delivery after child failures. |
| `options` | Native options consumed by a custom or network driver. |
| `color` | Explicit console color selection; `None` detects a TTY. |
| `sensitive_fields` | Additional context key fragments to redact. |
| `background` | Dispatch synchronous sink writes through one worker. |
| `queue_capacity` | Maximum records waiting in the bounded queue. |
| `overflow_policy` | `drop_newest`, `drop_oldest`, `raise`, `emergency`, or `await`. |
| `queue_wait_timeout` | Maximum async wait for queue space, from 0 to 60 seconds. |

## File paths and secrets

Application-owned file destinations resolve relative to
`Application.base_path`. `LogManager` used directly keeps Python's normal
process-relative path behavior. Absolute paths remain unchanged. Application
paths that escape the root are rejected. Create and permission the containing
directory as part of deployment. Do not put credentials in `options`,
filenames, or log context.

Webhook URLs are validated and treated as secret configuration. HTTPS is
required unless `allow_http` is explicitly enabled for a local test receiver.
See [drivers](/titanspan/logging/drivers/) for the complete network configuration boundary.

## Custom formatter registration

Register native formatter factories on the manager before resolving a
channel that references them:

```python
from titanspan.logging import LogManager, LogRecord


class PrefixFormatter:
    """Render records with a fixed application prefix.

    The formatter follows the native `LogFormatter` protocol.
    """

    def format(self, record: LogRecord) -> str:
        """Render one sanitized record.

        Args:
            record: The Titanspan record being formatted.

        Returns:
            A single-line record with an application prefix.
        """
        return f"APP {record.level.value}: {record.message}"


manager = LogManager(
    {"channels": {"default": {"driver": "console", "formatter": "app"}}},
    formatters={"app": lambda _: PrefixFormatter()},
)
```

Register a custom destination with `LogManager.extend(name, factory)`. The
factory receives a validated `ChannelConfiguration` and returns an object
implementing Titanspan's `LogDriver` protocol. See [custom drivers](/titanspan/logging/drivers/).

Register native customizers through `LogManager(customizers=...)` and list
their names in a channel's `tap` field. Customizers run during channel
creation and must be synchronous. See [channel customizers](/titanspan/logging/drivers/).
