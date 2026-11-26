# Public backend boundaries

Ordinary Titanspan application code should depend on Titanspan APIs. A small
number of explicit interoperability boundaries remain because the current
application lifecycle is still being consolidated. Framework service
composition is native; the table records remaining public integration
boundaries.

| Surface | Current boundary | Status |
| --- | --- | --- |
| `Application.asgi` | Exposes the configured FastAPI application for routes, middleware, and ASGI hosting. | Deliberate web integration escape hatch; web APIs beyond ASGI remain FastAPI-specific. |
| `Application.dependency` | Creates an async HTTP dependency resolver for a native service contract. | Uses the active application container and request scope; streaming response tests verify the scope remains active until the final body message. |
| `Application.providers` | Accepts explicit web integration provider values; the private adapter recognizes `InstanceRegistration` and otherwise passes values to the Dishka route graph. | Advanced interoperability for external route providers; ordinary Titanspan services use `Application.dependency` and the canonical native container. |
| `Settings` | Native typed settings class uses a private Pydantic Settings base and translates validation failures. Pydantic's inherited methods remain discoverable through the class MRO. | Ordinary docs use Titanspan methods; inherited backend methods are not a supported contract. A composition-based schema needs a separate design. |
| `Container` | Native registration, resolution, scopes, and errors delegate to a private Dishka adapter. | Public signatures use Titanspan types. This is the application composition root; native FastAPI dependencies resolve from it directly. |
| `Facade` | Typed base resolves each component facade's declared contract through the active application context. | Config and Log use the same container path; their explicit context managers are temporary test overrides, not production registries. |
| Logging | Native records, channels, drivers, and public contracts; Structlog and Python handler implementations stay behind `_backends/`. | Verified by component import and integration tests. Standard-library logging bridging is explicit. |
| Configuration repository | Native `Repository`, `ConfigRepository`, source loader, cache, and exceptions. Pydantic Settings and dotenv parsing are implementation details. | Verified by repository, source-loading, cache, facade, and application integration tests. |

## Container and application follow-up

FastAPI handlers can resolve Titanspan services through the native
`Application.dependency` bridge. The raw `Application.providers` input remains
for explicit external provider interoperability; removing it requires a
separate migration and resource-lifecycle review. Do not cast arbitrary
application values to backend provider types in new code.

The Config component is usable independently and provides synchronous access.
Its typed `Settings` declarations remain convenient for applications, but
subclassing exposes inherited validation-library methods. If the supported
surface must be fully independent of that method set, design and test a
composition-based declaration model before changing the API.

See [the architecture overview](/architecture/) and the [Container
specification](/specifications/container) for the owning integration
boundaries.
