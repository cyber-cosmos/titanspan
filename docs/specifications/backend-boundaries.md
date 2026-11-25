# Public backend boundaries

Ordinary Titanspan application code should depend on Titanspan APIs. A small
number of explicit interoperability boundaries remain because the current
application lifecycle is still being consolidated. Framework service
composition is native; the table records remaining public integration
boundaries.

| Surface | Current boundary | Status |
| --- | --- | --- |
| `Application.asgi` | Exposes the configured FastAPI application for routes, middleware, and ASGI hosting. | Deliberate web integration escape hatch; web APIs beyond ASGI remain FastAPI-specific. |
| `Application.providers` | Accepts explicit web integration provider values; the private adapter recognizes `InstanceRegistration` and otherwise passes values to the Dishka route graph. | Transitional ASGI route interoperability; framework services use native `ServiceProvider` registration and the application-owned `Container`. |
| `Settings` | Native typed settings class uses a private Pydantic Settings base and translates validation failures. Pydantic's inherited methods remain discoverable through the class MRO. | Ordinary docs use Titanspan methods; inherited backend methods are not a supported contract. A composition-based schema needs a separate design. |
| `Container` | Native registration, resolution, scopes, and errors delegate to a private Dishka adapter. | Public signatures use Titanspan types. This is the application composition root for framework services; FastAPI route dependencies still use a separate graph. |
| `Facade` | Typed base resolves each component facade's declared contract through the active application context. | Config and Log use the same container path; their explicit context managers are temporary test overrides, not production registries. |
| Logging | Native records, channels, drivers, and public contracts; Structlog and Python handler implementations stay behind `_backends/`. | Verified by component import and integration tests. Standard-library logging bridging is explicit. |
| Configuration repository | Native `Repository`, `ConfigRepository`, source loader, cache, and exceptions. Pydantic Settings and dotenv parsing are implementation details. | Verified by repository, source-loading, cache, facade, and application integration tests. |

## Container and application follow-up

The remaining container integration work is limited to unifying FastAPI route
injection with the native application registry and removing or replacing the
raw `Application.providers` interoperability input. Preserve request scope,
resource cleanup, and existing ASGI behavior while doing so. Do not cast
arbitrary application values to backend provider types in new code.

The Config component is usable independently and provides synchronous access.
Its typed `Settings` declarations remain convenient for applications, but
subclassing exposes inherited validation-library methods. If the supported
surface must be fully independent of that method set, design and test a
composition-based declaration model before changing the API.

See [the architecture overview](/architecture/) and the [Container
specification](/specifications/container) for the owning integration
boundaries.
