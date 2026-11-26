---
title: "HTTP behavioral specification"
---

<span id="http-behavioral-specification"></span>

This specification records the implemented Titanspan HTTP boundary. It does
not imply capabilities in future Routing, Authentication, Filesystem,
Validation, Concurrency, or Telemetry components.

## Implemented and verified

| Capability | Public boundary | Evidence |
| --- | --- | --- |
| Incoming metadata and typed input | `HttpRequest`, `Request` | `tests/unit/http/test_request.py` |
| Bounded body and multipart parsing | `ServerConfiguration`, `Request` | Request unit and ASGI tests |
| Request-owned upload lifecycle | `UploadedFile` | `tests/unit/http/test_uploaded_file.py` |
| Native response construction | `ResponseFactory`, response classes | `tests/unit/http/test_response.py` |
| Streaming and SSE response encoding | `StreamResponse`, `ServerSentEvent` | Response unit and ASGI lifecycle tests |
| Ordered dependency-injected middleware | `HttpMiddleware` | `tests/integration/http/test_middleware.py` |
| Sync/async pooled outgoing requests | `HttpClient`, `Http` | Loopback client integration tests |
| Streaming outgoing response cleanup | `HttpClient.stream_async` | `tests/integration/http/test_client.py` |
| Application-scoped client and request scope | `HttpServiceProvider`, `Application` | HTTP application integration tests |

## Resolution and lifecycle

The application composition root registers one outgoing `HttpClient` behind
the native contract. Its sync and async connection pools are distinct because
the transport implementations have different execution constraints. Both
belong to one application service and close through application shutdown.
The sync pool rejects use from a running async task. Sync-safe configuration
and facade resolution remain synchronous.

The incoming `Request` is created per ASGI call and registered in the native
request scope under both its implementation key and `HttpRequest`. The pure
ASGI context boundary remains active until downstream ASGI execution finishes
sending its complete body. This includes streaming responses and disconnect
or cancellation paths. The request closes parser-owned resources in a
cancellation-shielded finalizer.

## Input and output semantics

Query access is synchronous and preserves duplicate values through
`query_values`. Body parsing is asynchronous and cached. Merged input reads
query values first, then overlays parsed body values. Missing values remain
distinct from explicit null, false, zero, and empty values. Typed accessors
validate and raise native errors without echoing untrusted content.

Response fluent header methods mutate the response and return it. JSON values
are validated against the supported JSON model. Bodyless statuses do not
transmit a body. Redirects reject protocol-relative and unsupported schemes;
external HTTP(S) targets need explicit permission.

## Outgoing request behavior

Request-builder methods return independent immutable builder states. Ordinary
network requests are explicitly synchronous or asynchronous. HTTP error
statuses do not raise automatically. `throw` is opt-in. Retry attempts are
bounded and selected per request; non-idempotent methods require an explicit
idempotency key before retry. Streaming uses an explicit response context
that owns connection release.

## Pending capabilities

These features are not currently implemented and must not be described as
available:

- Outgoing HTTP fakes, request recording, and assertion helpers.
- Bounded concurrent request pooling and partial-result policies.
- Outgoing multipart file uploads and SSE client parsing.
- Native SSRF destination enforcement, trusted proxy rules, or redirect
  destination policy.
- Native CORS, trusted-host, authentication, authorization, CSRF, and
  rate-limiting middleware.
- Routing-owned route middleware groups, aliases, and route-level policies.
- Native OpenTelemetry spans and metrics.
- Windows and multiprocess guarantees for application-owned HTTP pools.

These require a production contract and real integration tests before their
status can change.
