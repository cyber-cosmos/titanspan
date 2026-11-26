---
title: "HTTP configuration and lifecycle"
---

<span id="http-configuration-and-lifecycle"></span>

HTTP settings are read once from the canonical `ConfigRepository` during
application composition. The `http.server` namespace configures request
limits; `http.client` configures both pooled outgoing clients.

```python
application = Application(
    config={
        "app": {"name": "Documents"},
        "http": {
            "server": {
                "max_body_size": 10_485_760,
                "max_form_files": 100,
                "max_form_fields": 1000,
                "max_part_size": 1_048_576,
            },
            "client": {
                "timeout": 30.0,
                "connect_timeout": 5.0,
                "max_connections": 100,
                "max_keepalive_connections": 20,
                "keepalive_expiry": 5.0,
                "follow_redirects": False,
                "verify_tls": True,
                "base_url": "",
                "http2": False,
            },
        },
    },
)
```

Limits must be positive integers. Timeouts must be positive finite numbers;
booleans are not accepted as numbers. `max_keepalive_connections` cannot be
greater than `max_connections`. Validation errors name the configuration
path but do not include configured values.

Precedence is framework defaults, canonical application configuration,
explicit `Application` configuration values, then immutable per-request
builder options. Configuration remains shared with the application and is
not reloaded on every request.

At startup, `HttpServiceProvider` resolves the HTTP client and initializes
both connection pools. Native `Application.shutdown` closes the async pool
and sync pool, including ASGI shutdown and startup rollback paths. A client
from one application is not shared with another application. Do not keep
responses or client references beyond their owning application's lifetime.
