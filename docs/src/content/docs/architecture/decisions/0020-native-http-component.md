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
  HTTP component. FastAPI and Starlette provide the ASGI host and supported
  routing backend; the separate Routing component owns route definitions and
  dispatch.
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
- Keep route definitions and dispatch in the Routing component. Implement
  HTTP-specific concurrent requests with AnyIO task groups and test fakes
  with HTTPX2 mock transports. Outbound URL checks reject unsafe syntax but
  do not claim comprehensive SSRF protection.

## Consequences

Application services can consume `HttpClient` through the same native
container used by configuration and logging. Synchronous and asynchronous
transport resources remain distinct, so one client pool is not shared across
incompatible execution modes. Application startup initializes the service;
shutdown owns its cleanup.

Incoming request and upload resources remain valid during streaming response
generation. Middleware can resolve request-scoped dependencies and modify a
native response without buffering its body.

The HTTP component provides a cohesive web boundary but does not own route
definitions. The separate native Routing component compiles its canonical
route catalog into the ASGI host; see ADR 0021 and
`docs/specifications/routing.md`. HTTP fakes, bounded request pools, outgoing
multipart, SSE client parsing, and supported Starlette middleware are
implemented through native APIs. Authentication, sessions, CSRF, distributed
rate limiting, Filesystem persistence, trusted proxy configuration, and
Telemetry remain integration boundaries documented in
`docs/specifications/http.md`.
