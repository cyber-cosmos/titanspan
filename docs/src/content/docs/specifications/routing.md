---
title: "Routing behavioral specification"
---

<span id="routing-behavioral-specification"></span>

This specification records Routing behavior and integration evidence. It
distinguishes supported behavior from work that needs another component.

## Implemented and verified

| Capability | Implementation owner | Evidence |
| --- | --- | --- |
| One authoritative route catalog per application | `Router`, `RouteCollection` | Route identity, registration, and concurrent application tests |
| HTTP methods, decorators, actions, names, and constraints | `Router`, `RouteDefinition` | Routing unit tests and real ASGI integration tests |
| Groups, nested groups, and inherited metadata | `RouteGroupBuilder` | Group and resource unit tests |
| Full, API, nested, shallow, and singleton resources | `ResourceRegistrar` | `tests/unit/routing/test_groups_and_resources.py` |
| Typed dispatch and explicit sync or async binding | FastAPI adapter and `Router` | `tests/integration/routing/test_advanced_routing.py` |
| Controller and callable dependency injection | Canonical Container | `tests/integration/routing/test_dispatch.py` |
| Middleware aliases, groups, inheritance, and exclusions | `Router`, HTTP middleware contract | `tests/integration/routing/test_dispatch.py` and group unit tests |
| Ordered conventional and configured route discovery | `RouteDiscovery` provider boot | `tests/integration/routing/test_route_discovery.py` |
| Stable inspection and safe route metadata cache | `RouteCollection`, `RouteCache` | `tests/unit/routing/test_route_cache.py` and inspection tests |
| WebSocket acceptance, messaging, and connection cleanup | FastAPI, Starlette, Container `CONNECTION` scope | `tests/integration/routing/test_advanced_routing.py` |
| OpenAPI inputs and response metadata | FastAPI and Pydantic | `test_openapi_documents_models_and_hides_container_services` |
| One URL generator contract across application consumers | `UriUrlGenerator` and provider | `tests/integration/routing/test_uri_integration.py` |
| Route matching, method errors, and generated URL dispatch | FastAPI and Starlette | Routing integration suite |

The private FastAPI adapter delegates route matching, HTTP method handling,
WebSocket dispatch, OpenAPI generation, and supported path reversal. The
native `Router` and `RouteCollection` remain the source of route identity and
metadata. Startup freezes and compiles this catalog into the existing ASGI
application.

## Registration and dispatch

Direct methods and decorators register the same `RouteDefinition`. `route`
accepts a sequence of HTTP methods; convenience methods cover GET, POST, PUT,
PATCH, DELETE, HEAD, OPTIONS, CONNECT, and TRACE. `any` covers common methods
except CONNECT and TRACE. Actions may be functions, callable objects,
controller classes, or controller and method pairs. Controller construction,
constructor injection, and method injection use the native Container.

The adapter constructs controllers through the Container's async resolver.
Async actions use call_async. Synchronous actions run in AnyIO's managed
worker through the Container's synchronous call API. The Container bridges
worker lookups to the owning application loop, preserving application,
request, and connection scopes.

FastAPI parses supported typed path and query inputs. Handler values are
passed explicitly by name. Enums are converted through their annotations.
Defaults are converted against handler annotations during startup and checked
against declared constraints. A single optional segment is supported only
at the end of a path. Constraint misses produce 404 responses; valid paths
with method mismatches produce 405 with `Allow` metadata.

`Router.bind` associates a parameter name with a synchronous or asynchronous
callback. Returning `None` raises `RouteBindingNotFoundError` and returns a
native 404 for HTTP. The callback receives the raw matched path value and
replaces it in explicit controller or handler arguments.

Resource registrations expand into ordinary entries in the same catalog.
They support nested names and parameters, custom action names, filtering,
parameter remapping, middleware, shallow item paths, and singleton resources.
Full resources include browser create and edit actions; API resources omit
them. Singleton creation and deletion actions are opt-in.

## Middleware

Middleware runs in declaration order through the existing HTTP middleware
contract. Nested groups inherit outer middleware first. Route-local and
controller `route_middleware` declarations follow group middleware. Alias
and group expansion is deterministic and deduplicated. Route exclusions
remove selected aliases or classes after expansion. `current_route()` is
available during route middleware and action execution.

The HTTP middleware contract does not yet carry route-specific parameter
configuration. Parameterized middleware remains pending until HTTP provides
an immutable declaration and supported execution mechanism. Authentication,
authorization, rate limiting, and session policies remain owned by their
components.

## Discovery, inspection, and cache

Routing provider startup imports explicitly configured dotted module names
in order, then conventional `routes/web.py` and `routes/api.py` files. Each
module must expose `register_routes(router)` and may use a synchronous or
asynchronous hook. Conventional imports are restricted to the resolved
`routing.path` root and use a temporary per-Router package namespace for
relative imports. Duplicate route conflicts retain `DuplicateRouteError`.

`routing.discover=False` disables conventional files but keeps explicit
modules. When `routing.path` is absent, Foundation passes its effective
`Application.base_path` to `RoutingServiceProvider`. An explicit `routing.path`
setting takes precedence. Relative values resolve beneath the application
root; absolute values remain explicit.

`Router.inspect` and `RouteFilter` filter by exact method, path, name,
protocol, domain, or middleware and preserve registration order and route
identity. `RouteCache` stores JSON inspection metadata only. It never uses
pickle or serializes actions, containers, or live services. A read validates
the file against the already discovered live catalog. Applications must
still run route discovery and registration; this cache is not a startup
shortcut. Local or stateful handlers without stable identities are rejected.

Console provides native command registration, application lifecycle handling,
and typed terminal output. Its `route:list` command receives the active
catalog through `RouteCatalog` and renders through `ConsoleOutput`. Routing
does not add a second CLI engine.

## WebSockets and OpenAPI

WebSocket routes use FastAPI and Starlette. Handlers must be asynchronous and
receive one typed Starlette `WebSocket` connection. Starlette owns connection
acceptance, message operations, and disconnect behavior. Routing resolves
dependencies through the canonical Container inside `Scope.CONNECTION` and
exits that scope when the handler returns, fails, or is cancelled. Explicit
binding callbacks also apply to WebSocket path values.

FastAPI generates OpenAPI operation IDs from route names and generates path,
query, and supported request-body schemas from handler annotations. Routes
may declare tags, summary, description, deprecation, status code, response
model, and response metadata. Container services are excluded from client
inputs. A future Validation integration needs a supported Pydantic schema
boundary; Routing does not implement a separate schema engine.

## URL generation

The canonical `UriUrlGenerator` contract lives in `contracts.routing`.
`support.UriUrlGenerator` re-exports the same protocol object. The provider
registers one application-owned generator for its concrete and contract
types. `Uri.to`, `Uri.route`, `Uri.action`, `route()`, `url()`, dependency
injection, and named redirects resolve this service and catalog.

`route()`, `url()`, `Uri.route()`, and `Uri.action()` default to relative
URLs. `Uri.to()` remains absolute and uses the configured trusted origin.
Pass `absolute=True` to request absolute named-route or helper URLs. Absolute
generation never uses request Host or forwarded headers. Domain routes
require a matching configured origin.

Path parameters use declared defaults, are encoded as UTF-8, and are checked
against constraints and built-in converters: str, int, float, uuid, and path.
Unused values use Support's Arr.query: sequences use indexed bracket keys,
nested mappings use bracket notation, null entries are omitted, and boolean
values use 1 or 0. Local URL query strings retain repeated keys and fragments
when an origin is added. Optional trailing segments use native catalog
substitution. Custom Starlette converters remain unsupported. Other named
route forms use Starlette's url_path_for. Both forms select the same route
that handles incoming requests. Uri.action inspects stored callable
identities without constructing a controller and raises when one action maps
to distinct paths.

Named redirects generate relative paths and delegate response construction
to the active HTTP `ResponseFactory`. URI parsing and component manipulation
remain independent of application state. URI factories and redirects use
application context-local service bindings.

## Pending component prerequisites

- Database-backed model binding needs a Database-owned lookup contract or
  service. Routing can pass the matched string key and translate a missing
  result through `RouteBindingNotFoundError`; it does not need an ORM.
- Signed URLs need application key management that supports signing,
  verification, rotation, and lifecycle ownership. Routing retains explicit
  unsupported behavior until that service exists.
- View routes need the View component's rendering contract and response
  integration.
- Parameterized middleware needs the HTTP contract change described above.

Security policies remain with authentication, authorization, rate limiting,
and session components. No Routing-specific security engine is introduced.
