---
title: "Routing behavioral specification"
---

<span id="routing-behavioral-specification"></span>

This document records the implemented native route boundary and its evidence.
It does not claim that pending web capabilities are available.

## Implemented and verified

| Capability | Owner | Evidence |
| --- | --- | --- |
| One route catalog per app | `Router`, `RouteCollection` | Routing unit tests and application identity integration |
| Registration, names, groups, resources | `Router`, `RouteDefinition` | `tests/unit/routing/` |
| ASGI matching and method errors | Private FastAPI adapter | Real `TestClient` routing integration tests |
| Controller and callable injection | Native Container | `tests/integration/routing/test_dispatch.py` |
| Request-scoped dispatch and streaming | Foundation ASGI boundary | Request lifecycle and route streaming integration tests |
| URL generator contract | `contracts.routing.UriUrlGenerator` | Strict service injection and URI integration tests |
| URI factories and safe redirects | Support and HTTP contracts | `tests/integration/routing/test_uri_integration.py` |
| Named path reversal after compilation | FastAPI/Starlette router adapter | Compiled route reversal integration test |
| Trusted origin handling | `UrlGenerator` | URL generator and multi-application tests |
| Route constraints during reversal | `UrlGenerator` | URL generator tests reject values that do not fully match constraints |
| Domain-constrained absolute URLs | `UrlGenerator` | URL generator tests require the configured trusted origin to match the route domain |
| Constraint-aware method errors | FastAPI adapter | ASGI tests distinguish a constraint miss (404) from a valid path with a method miss (405 and `Allow`) |
| Global and route middleware composition | Foundation and Router | `tests/integration/routing/test_dispatch.py` verifies outer-to-inner order and explicit double registration |

## URL generation semantics

The canonical `UriUrlGenerator` contract lives under `contracts.routing`.
`support.UriUrlGenerator` re-exports the exact same protocol object for
existing Support imports. `RoutingServiceProvider` registers one concrete
`UrlGenerator` under both concrete and protocol keys. `Uri` factories,
application helpers, dependency injection, and named redirects read that
same service and route catalog.

`route()` requires a named route, substitutes declared path values, applies
route defaults, and serializes unused scalar and sequence values as query
parameters. Path values are percent-encoded. `to()` accepts local absolute
paths and requires a configured trusted origin. Absolute generation never
uses request Host or forwarded headers. URI query and fragment components are
preserved when an origin is added.

After FastAPI route compilation, named paths without custom path converters
delegate substitution to the application router's supported `url_path_for`
operation. Custom converter forms use native catalog substitution. The route
catalog remains authoritative in both cases. The URL generator validates each
substituted value against its declared route constraint using a full match. An
absolute URL for a domain-constrained route requires the configured trusted
origin to use that domain. Relative URL generation remains available.

`action()` inspects stored callable metadata without constructing a controller.
It accepts a dotted identifier or identifier sequence, rejects missing
actions, and rejects actions associated with distinct route paths. Named
routes are preferred when a callable has multiple intentional paths.

`Uri.redirect()` requires an active Application and delegates to the native
`ResponseFactory`. Its redirects inherit HTTP validation, including rejection
of external and protocol-relative targets. URI parsing and manipulation do
not require active application state.

HTTP method mismatches return 405 with an `Allow` header only when the path,
domain, and parameter constraints match. A constraint failure returns 404.
Global middleware wraps routing; route middleware wraps only the selected
endpoint. Explicitly registering one middleware at both levels runs it twice.

Signed URLs are unavailable because Titanspan has no key-management boundary
that supports both signing and verification. Both signed URI factory methods
fail explicitly with `RouteUrlError`.

## Pending capabilities

- Application route-file discovery and import lifecycle.
- Persistent route caching and route inspection CLI.
- WebSocket route scopes and dispatch.
- Database-backed model binding.
- Key-managed signed URL generation and verification.
- Complete OpenAPI schema synthesis from native validation metadata.
- Security policy integration for authentication, authorization, sessions,
  and route-level security exclusions.

See [Routing](/titanspan/routing/) and [URL generation](/titanspan/routing/url-generation/)
for application usage. Documentation navigation includes this specification
so capability status remains visible.
