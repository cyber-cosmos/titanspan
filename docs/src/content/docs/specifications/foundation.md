---
title: "Foundation behavioral specification"
---

<span id="foundation-specification"></span>

This specification records the behavior verified by Foundation tests.

| Capability | Status | Evidence |
| --- | --- | --- |
| Application composition | Implemented | `Application` builds one native Container and ordered component providers. |
| Built-in component providers | Implemented | Cohesion integration tests resolve Validation, Filesystem, and Hashing contracts without repeated registration. |
| Typed application builder | Implemented | Unit tests cover paths, configuration, and provider registration. |
| Provider entry-point discovery | Implemented | Unit tests load and reject providers through real entry points. |
| Provider boot | Implemented | Integration tests verify registration order, injection, and rollback. |
| Provider shutdown | Implemented | Filesystem shutdown finalizes only resolved manager-owned backends before Container close. |
| Application lifecycle callbacks | Implemented | Integration tests cover ordering, callback failure, and registration freeze. |
| Standalone execution | Implemented | `Application.run()` and async context tests verify startup and shutdown. |
| ASGI lifecycle | Implemented | FastAPI lifespan delegates to native application startup and shutdown. |
| Request scope and context | Implemented | Real ASGI tests cover scope identity, streaming lifetime, and isolation. |
| Exception rendering | Implemented | Native handlers receive the request and exception through Container injection. |
| Request parsing errors | Implemented | Malformed native request input returns a safe 400 response; oversized input returns 413. |
| Generic error response | Implemented | Unhandled request failures are logged and return a generic JSON 500 response. |
| Validation response | Implemented | `ValidationException` uses the canonical response factory and returns safe field errors with status 422. |
| Configurable middleware | Implemented | Builder and constructor accept ordered native HTTP middleware. |
| Filesystem containment | Not provided | Path helpers compose trusted application paths; they do not validate untrusted input. |
| Shutdown callbacks resolving services | Unsupported | Container rejects new resolutions after shutdown admission closes. Use captured references or the provider shutdown hook. |
| External FastAPI provider graph | Advanced interop | Explicit `providers` input remains behind a private adapter. |

## Composition order

Foundation constructs the configuration repository, Container, logging
manager, HTTP services, Routing services, Events, Validation, Filesystem,
Hashing, and application providers. Core providers register first. One
explicit provider can replace each built-in Validation, Filesystem, or
Hashing provider. Other explicit and discovered providers follow in builder
order. Registrations remain in the canonical application Container.

Provider boot runs after registration and uses dependency injection. Startup
callbacks run after provider boot. Routing resolves conventional route files
from `Application.base_path` unless `routing.path` selects another root.
Routing compiles before startup completes.
If startup fails, Foundation closes initialized resources and restores the
application context.

Foundation registers `ApplicationPaths` before component providers. Filesystem
uses it to root relative local disks. Logging uses it to root relative file
destinations. Explicit absolute paths remain unchanged. Relative paths that
escape the application root are rejected.

## Lifecycle order

`startup()` arms cleanup callbacks, starts the Container, binds application
context, boots providers, runs startup callbacks, and installs routes.
`shutdown()` rejects active work and stops new Container resolutions. It runs
application callbacks first, provider shutdown hooks in reverse provider
order, then Container resource finalizers. Provider hooks may inspect already
resolved services through `find_resolved`; they must not construct new ones.
`Application.run()` and `async with Application()` use this same lifecycle.
The ASGI lifespan delegates to these methods.

Application lifecycle callbacks receive no injected arguments. Provider boot
uses Container injection. An optional provider shutdown hook receives the
stopped Container for non-constructing resource inspection. Providers must
close only resources they own. Application callbacks use captured references
because the Container stops accepting new resolutions before cleanup.

## Exception behavior

Unhandled `Exception` values are reported through the currently selected
application logger. Default reports include the exception class but omit its
message, traceback, and chained exception text. `app.debug` or the explicit
`include_details=True` argument enables detailed logs for trusted development
use. Reports after Container shutdown use the logging manager's emergency
destination and include only the exception class.
Malformed native request input returns JSON with status 400. Oversized bodies
return status 413. Other unhandled exceptions use JSON status 500 with a
generic detail value.
`ValidationException` returns status 422 with a generic detail value and safe
field messages. The response does not include rejected input values.
Custom handlers use native request and response contracts. They receive
explicit `request` and `exception` arguments, plus any additional services
resolved from the active request scope.

Cancellation is not converted to an application error response. The ASGI
stack propagates cancellation and finalizes request resources.

## Verification

Unit and integration evidence is maintained in:

- `tests/unit/test_application.py`
- `tests/integration/test_framework_cohesion.py`
- `tests/integration/test_container_lifecycle.py`
- `tests/integration/http/test_request_lifecycle.py`

This specification does not claim persistent route caching, arbitrary module
scanning, filesystem containment, or a second web dependency graph for native
services.
