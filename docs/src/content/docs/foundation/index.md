---
title: "Application foundation"
---

<span id="application-foundation"></span>

Foundation composes one application Container and owns its lifecycle. It
coordinates configuration, logging, providers, request scopes, and shutdown.
FastAPI and Starlette provide the ASGI host and protocol implementation.

Create an application directly or use the typed builder:

```python
from titanspan import Application

application = (
    Application.builder()
    .with_base_path(".")
    .with_config({"app": {"name": "Documents", "env": "production"}})
    .build()
)
```

The builder collects inputs. `Application` remains the only composition root.
Calls to `with_config()` replace the previous builder override mapping.
Built-in providers register before application providers. Application
providers retain their supplied order.

Use `Application.run()` for one standalone operation:

```python
async def main() -> None:
    """Run one application operation with managed startup and shutdown."""
    application = Application()
    name = await application.run(lambda: application.config.get("app.name"))
    print(name)
```

Use `async with application` when one application must serve several
operations. Both forms bind the active application context. The `app()`
helper returns this application only while that context is active.

## Providers

Register native provider instances with `with_service_provider()`. Providers
register services synchronously. Bootable providers run after all services
are registered, in application registration order, with Container injection.
Providers that implement `ShutdownableServiceProvider` close their owned
resources after application callbacks and before Container finalization.
Shutdown hooks run in reverse provider order. They receive the stopped
Container and can inspect existing values with `find_resolved`; they must not
resolve new services.

Foundation registers Config, Logging, HTTP, Routing, Events, Validation,
Filesystem, and Hashing providers by default. Applications can supply one
custom provider for Validation, Filesystem, or Hashing. That instance replaces
the matching default and keeps its driver configuration. Registering the same
built-in provider more than once raises `ValueError`.

Applications can opt in to installed provider discovery:

```python
application = (
    Application.builder()
    .discover_providers(group="documents.providers")
    .build()
)
```

Discovery loads every installed entry point in that group. Entry points run
Python code and must come from trusted installed distributions. Titanspan
does not scan application modules or import configured filesystem paths.
Provider entry points must load a provider instance or a zero-argument
provider class.

Declare an entry point in a package's project metadata:

```toml
[project.entry-points."documents.providers"]
database = "documents.providers:DatabaseProvider"
```

The builder also accepts HTTP middleware and explicit FastAPI interoperability
providers. Ordinary Titanspan services use the native Container.

## Application paths and environment

`base_path` is the resolved application root. `path()` joins path segments to
that root. `config_path`, `bootstrap_path`, and `storage_path` return
conventional paths without creating directories. They do not enforce
filesystem containment for untrusted values.

Foundation supplies this root to conventional route discovery, local storage
roots, and relative file-log destinations. An explicit `routing.path` setting
takes precedence. Relative storage and log paths resolve below the root;
absolute paths remain unchanged. Relative paths that escape the root are
rejected. Other components must use `Application.base_path` or
`Application.path()` for application-relative resources.

`environment` reads `app.env` and defaults to `production`.
`is_environment()` compares names without case sensitivity. `debug` returns
the validated `app.debug` value.

## Lifecycle hooks

Register zero-argument callbacks before startup:

```python
application.on_startup(initialize_runtime)
application.on_shutdown(close_runtime)
```

Startup callbacks run after providers boot and before native routes install.
Shutdown callbacks run in reverse registration order before Container-owned
resources close. Callbacks can be synchronous or asynchronous. Use providers
for dependency-injected initialization. Shutdown callbacks should close
resources they own through captured references.

Startup failure runs registered shutdown callbacks and finalizes owned
resources. Callback registration freezes as startup begins. Shutdown remains
idempotent and rejects active scopes or service operations.

## Exception handling

Foundation logs unhandled request exceptions and returns a generic JSON 500
response. It does not include exception details in the response body.
Malformed native request input returns a safe 400 response. Oversized request
bodies return 413. Validation errors return 422.
Default logs record the exception class without its message or traceback.
Application debug mode enables detailed logs. Call
`application.report_exception(error, include_details=True)` only when detailed
diagnostics are appropriate for a trusted development environment.

Register a typed renderer before startup:

```python
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    ResponseFactory,
)

def render_invalid(
    request: HttpRequest,
    exception: ValueError,
    factory: ResponseFactory,
) -> HttpResponse:
    """Return a safe response for one application error."""
    return factory.json({"detail": "Invalid request"}, status=422)

application.add_exception_handler(ValueError, render_invalid)
```

Handlers receive `request` and `exception` values by name. Additional typed
services resolve from the active request scope. The handler must return a
native response accepted by the ASGI adapter. Never place secrets in
exception messages or public response bodies.

## Request lifecycle

The ASGI adapter binds application context, a request scope, the native
request, and logging context. The scope remains active until the complete ASGI
response finishes, including streaming and disconnect handling. Application
shutdown closes application-owned resources after active scopes finish.

`Application.dependency()` is an explicit FastAPI integration boundary. It
resolves from the native Container. Raw third-party provider objects remain
an advanced interoperability input.

See the [Foundation specification](/framework/specifications/foundation/)
for verified behavior and limitations.
