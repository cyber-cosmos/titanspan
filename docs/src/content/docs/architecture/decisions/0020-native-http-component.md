---
title: "ADR 0020: Native HTTP component boundaries"
---

<span id="adr-0020-native-http-component-boundaries"></span>

- Status: Accepted
- Date: 2026-11-26

## Context

Titanspan needs one HTTP component for server requests, response creation,
middleware, streaming, and outgoing network requests. It must cooperate with
the application container, Config, Logging, Facades, and Foundation while
using maintained protocol implementations.

The sync-first container can resolve a client service synchronously, but
outgoing HTTP also requires asynchronous network calls and an asynchronous
pool lifecycle. Incoming request and streamed response resources belong to
the full ASGI call, not only to endpoint execution.

## Decision

- Use Starlette request, response, and ASGI machinery behind the Titanspan
  HTTP component. Keep FastAPI as the existing route integration boundary.
- Use HTTPX2 for pooled synchronous and asynchronous outgoing transport.
  Keep both connection pools on one application-owned service and close them
  through the native application lifecycle.
- Publish Titanspan-owned contracts, configuration, exceptions, response
  types, request wrappers, and immutable pending request builders. Translate
  backend exceptions at private adapter boundaries.
- Keep request metadata synchronous and body operations explicitly
  asynchronous. Keep synchronous network calls outside active async runtimes
  and expose `_async` methods for async network operations.
- Bind the application context, request context, logging context, and native
  request scope through a pure ASGI middleware boundary that remains active
  until response transmission has completed or been cancelled.
- Do not introduce a router, concurrent request pool, fake HTTP system, or
  SSRF destination policy in this component. These require their own
  implemented contracts and integration evidence.

## Consequences

Application services can consume `HttpClient` through the same native
container used by configuration and logging. Synchronous and asynchronous
transport resources remain distinct, so one client pool is not shared across
incompatible execution modes. Application startup initializes the service;
shutdown owns its cleanup.

Incoming request and upload resources remain valid during streaming response
generation. Middleware can resolve request-scoped dependencies and modify a
native response without buffering its body.

The HTTP component provides a useful initial web boundary but is not a
complete web stack. Route registration remains FastAPI-backed. HTTP fakes,
bounded concurrent client pools, outgoing multipart, SSRF policy, routing,
authentication, and telemetry are pending and are tracked in
`docs/src/content/docs/specifications/http.md`.
