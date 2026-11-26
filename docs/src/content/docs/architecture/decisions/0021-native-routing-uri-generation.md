---
title: "ADR 0021: Native routing and URI generation integration"
---

<span id="adr-0021-native-routing-and-uri-generation-integration"></span>

- Status: Accepted
- Date: 2026-11-26

## Context

URI parsing and query manipulation belong to Support and must remain usable
without an active application. URI route factories, named redirects, and
incoming route dispatch must nevertheless use the same registered route
definitions and trusted application origin. A Support-local resolver or a
second route registry would allow app contexts to leak and URLs to disagree
with the routes that actually dispatch.

The active Application context already uses `ContextVar` tokens and the HTTP
component already owns safe redirect construction. The selected ASGI router
also exposes supported named path reversal after route compilation.

## Decision

- Define `UriUrlGenerator` once in `contracts.routing`; Support re-exports the
  exact same protocol object.
- Register one application-owned `UrlGenerator` under its concrete class and
  contract, backed by the Router's canonical `RouteCatalog`.
- Resolve the `UriUrlGenerator` contract from URI factories, Routing helpers,
  dependency injection, and named redirects. A contract substitution must be
  visible through every public URL-generation entry point.
- Return relative URLs by default from named route factories and helpers.
  Callers request the configured trusted origin with `absolute=True`.
- Bind lazy URI URL and response-factory resolvers together with Foundation's
  active application context. Restore all tokens for nested contexts,
  exceptions, cancellation, and concurrent tasks.
- Keep URI parse and component operations independent of application state.
  Route-aware URI factories and URI redirects require the active app context.
- Delegate named path reversal to the supported Starlette/FastAPI router
  after compilation. Before compilation, validate supported built-in path
  converters and encode values against the same route metadata.
- Use Support's `Arr.query` for remaining route parameters so URI and Routing
  query output share RFC 3986 encoding and nested value semantics.
- Route `Uri.redirect()` through the native HTTP `ResponseFactory`, preserving
  its safe local-destination defaults.
- Reject signed URL requests until key management supports both generation
  and verification. Never degrade to an unsigned URL.

## Consequences

`Uri.route`, `Uri.action`, Routing helpers, dependency injection, and named
redirects agree on one application's route catalog. Separate Application
contexts retain independent origins, and Support does not import a concrete
Router or ASGI implementation. Absolute route generation requires an
explicit trusted origin; Host and forwarded headers are not used.

URI redirects cannot bypass native redirect validation. An absolute URL is
rejected by the default redirect policy, including a trusted origin; callers
should generate a relative named route when redirecting. Signed URLs,
verification, and key lifecycle remain pending.

The relative default aligns `Uri.route()` and `Uri.action()` with the Routing
`route()` helper. Callers that relied on an absolute URI must pass
`absolute=True`. Custom Starlette converters remain unsupported by the native
Router; URL generation rejects them instead of returning a path that may not
match.
