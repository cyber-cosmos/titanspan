# Routing

The Routing component owns route definitions, route metadata, controller
dispatch, and URL generation for one Titanspan Application. Foundation
compiles those definitions into its existing ASGI host. The same native
route catalog serves dispatch, inspection, URI factories, helpers, and named
redirects.

```python
application.router.get(
    "/documents/{document_id}",
    (DocumentController, "show"),
).name("documents.show")
```

Routes are registered before application startup. Startup freezes route
metadata and installs the compiled matcher. Controllers and middleware are
resolved per request through the canonical Container, and request scope plus
application context remain active through streamed response transmission.

## Implemented

- Explicit GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS registration.
- Method matching, fallback, redirect, and bounded common-method routes.
- Nested registration groups with prefixes, middleware, defaults, constraints,
  domains, and name prefixes.
- Resource and API resource registration.
- Controller and callable dispatch with native Container injection.
- Middleware aliases and groups through the HTTP middleware contract.
- Route names, metadata, parameter constraints, and OpenAPI metadata.
- Application-scoped URL generation and context-aware route helpers.

See [URL generation](./url-generation) for `Uri`, route helpers, trusted
origins, and safe redirects.

## Lifecycle

Register routes on `application.router` before `await application.startup()`
or before the ASGI lifespan starts. The route collection is frozen during
startup. The Application owns startup, request scope, active context, and
resource cleanup. Routing does not create another service registry or
dependency graph.

The native request context encloses the complete ASGI call. A streaming
generator can therefore continue using request-scoped dependencies until its
body has been sent or cancelled.

## Current boundaries

The ASGI adapter uses FastAPI and Starlette for matching, method handling,
route reversal after compilation, OpenAPI wiring, and protocol dispatch.
Route definitions remain Titanspan-owned. Secure signed URLs are unavailable
until framework key management supports signing and verification. Route-file
discovery, persistent route caching, WebSockets, and database-backed model
binding are also pending.

See the [routing specification](/specifications/routing) for capability
status and integration evidence.
