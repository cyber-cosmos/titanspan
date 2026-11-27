---
title: "Routing"
---

<span id="routing"></span>

Routing owns one route catalog for registration, dispatch metadata,
inspection, URL generation, and redirects. FastAPI and Starlette provide
matching, method handling, WebSocket dispatch, OpenAPI, and supported path
reversal through the application's existing ASGI host.

## Register routes

Register routes on `application.router` during application composition.
Methods support direct and decorator registration:

```python
@application.router.get("/documents/{document_id}")
async def show_document(document_id: int) -> dict[str, int]:
    return {"document_id": document_id}

application.router.match(
    ("PUT", "PATCH"),
    "/documents/{document_id}",
    (DocumentController, "update"),
).name("documents.update")
```

Use `get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `connect`,
and `trace` for individual methods. `match` accepts one or more explicit
methods. `any` registers GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS;
it does not register CONNECT or TRACE. A path may be named through
`.name("documents.show")` or the `name` argument to `route`.

Actions can be functions, callable instances, controller classes, or
`(Controller, "method")` pairs. The canonical Container constructs
controllers and resolves constructor and method dependencies. Explicit path
values are passed by name and converted according to handler annotations.
Enums and native FastAPI and Pydantic input declarations are supported.

## Groups and constraints

Group attributes inherit through nested context managers. Child prefixes are
joined, name prefixes concatenate, middleware preserves declaration order,
and child constraints and defaults replace matching parent values.

```python
with application.router.prefix("/admin").name("admin.").group():
    with application.router.prefix("/documents").middleware("staff").group():
        application.router.get(
            "/{document_id}",
            (DocumentController, "show"),
        ).where_number("document_id")
```

Route definitions support `where`, `where_number`, `where_alpha`,
`where_alpha_numeric`, `where_uuid`, and `where_in`. Constraints apply to
dispatch and URL generation. `domain` restricts the incoming host. Defaults
fill omitted handler arguments and must satisfy the path annotation and
declared constraint. A final optional segment such as `/{locale?}` produces
routes with and without that segment; only one optional final segment is
supported.

## Resources

`resource` registers the seven REST actions. `api_resource` omits browser
`create` and `edit` actions. Nested names use dot or slash separators and
produce parent parameters. Registrars support `only`, `except_`, `parameters`,
`names`, and `middleware`. `shallow()` shortens nested item paths and names.
`singleton` registers one address without an item key; `creatable()` and
`destroyable()` opt into its additional actions. `api_singleton` provides the
API action set.

Resource routes are ordinary definitions in the canonical catalog, so their
matching, metadata, middleware, inspection, and named URLs use the same path.
View routes are unavailable because Titanspan does not yet have a View
component.

## Binding and middleware

Register `router.bind("document_id", callback)` to replace one raw path value
with a resolved application value. Callbacks can be synchronous or
asynchronous. Returning `None` raises `RouteBindingNotFoundError` and produces
a native 404 response. A database-backed binder should use the future
Database component; Routing does not provide an ORM or model lookup service.

Middleware uses the existing HTTP middleware contract. Register aliases with
`alias_middleware` and reusable ordered groups with `middleware_group`.
Groups, route declarations, and a controller's `route_middleware` class
attribute contribute middleware in order. `without_middleware` removes
selected aliases or classes for a route. Current-route helpers are available
while route middleware and the action execute. Use
`MiddlewareDeclaration(alias_or_class, parameters)` for immutable string
parameters. Exact duplicate declarations run once; the same target with
different parameters runs once per distinct declaration. Exclusions by alias
or class remove every matching parameterized declaration.

## Discovery and inspection

At application startup, Routing loads configured `routing.modules` in their
listed order, then `routes/web.py` and `routes/api.py` from `routing.path`.
When that setting is absent, Foundation supplies the effective
`Application.base_path`. A relative `routing.path` is resolved beneath that
root; an absolute path remains explicit.
Each module defines `register_routes(router)`; synchronous and asynchronous
hooks are supported. Set `routing.discover` to `False` to disable conventional
files while retaining explicit modules. Imports occur within the trusted
application startup lifecycle, not at module import time.

`application.router.inspect(RouteFilter(...))` returns original route
definitions in declaration order. Filters select exact methods, paths, names,
protocols, domains, or middleware. `RouteCache` writes JSON metadata without
serializing live callables or containers. Reading validates the snapshot
against routes that the application has already discovered and registered;
it does not skip startup or claim faster startup.

The installed Console provides `route:list`. It starts the application and
reads this same catalog through the shared `RouteCatalog` contract.

## WebSockets and OpenAPI

Register an asynchronous WebSocket handler with `router.websocket`. Its
signature includes one Starlette `WebSocket` connection plus typed path
parameters. Starlette owns acceptance, message exchange, and disconnect
handling. Routing opens the existing Container `CONNECTION` scope around the
handler and closes it on return, failure, or cancellation.

FastAPI generates OpenAPI for HTTP routes. Route names supply operation IDs;
route metadata supports tags, summaries, descriptions, deprecation, status
codes, response models, and response declarations. FastAPI and Pydantic
provide supported path, query, and request-body schemas. Container-injected
services are excluded from client input schemas. Typed routes document the
stable safe 422 response body. Explicit `Validation.validate_request` calls
do not add request schemas to OpenAPI. Use
`.validate_input("payload", rules=..., async_rules=...)` to apply the canonical
Validation service to an annotated HTTP input. Route middleware can reject a
request before these application rules run. WebSocket routes do not support
HTTP input validation.

## Lifecycle and pending integrations

Application startup freezes route registration before requests are served.
The same Router and URL generator are application-owned Container services.
Request context remains active through complete ASGI response transmission,
including streaming cleanup.

Signed URLs remain unsupported until framework key management can generate,
verify, and rotate application signatures. Database-backed model binding and
View routes need the owning components described above. See the
[routing specification](/framework/specifications/routing/) for evidence and
integration requirements, and [URL generation](./url-generation) for helper
semantics.
