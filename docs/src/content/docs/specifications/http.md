---
title: "HTTP behavioral specification"
---

<span id="http-behavioral-specification"></span>

This specification records the implemented Titanspan HTTP boundary. HTTP
request validation delegates to the Validation component and does not add a
second schema engine. It does not imply capabilities in Authentication,
Filesystem, Concurrency, or Telemetry components.

## Implemented and verified

| Capability | Public boundary | Evidence |
| --- | --- | --- |
| Incoming metadata and typed input | `HttpRequest`, `Request` | `tests/unit/http/test_request.py` |
| Application schema validation of request input | `Validation.validate_request` | `tests/integration/validation/test_validation_application.py` |
| Bounded body and multipart parsing | `ServerConfiguration`, `Request` | Request unit and ASGI tests |
| Request-owned upload lifecycle | `UploadedFile` | `tests/unit/http/test_uploaded_file.py` |
| Route metadata and request/correlation identifiers | `Request` | Request and dispatch integration tests |
| Native response construction, bodyless status and HEAD semantics | `ResponseFactory`, response classes | `tests/unit/http/test_response.py`, `tests/integration/http/test_asgi_backend.py` |
| Response cookies and removal | Native response classes | `tests/unit/http/test_response.py` |
| Streaming and SSE response encoding | `StreamResponse`, `ServerSentEvent` | Response unit and ASGI lifecycle tests |
| Ordered dependency-injected middleware | `HttpMiddleware` | `tests/integration/http/test_middleware.py` |
| CORS, trusted hosts, and HTTPS redirects | Native ASGI middleware | `tests/integration/http/test_middleware.py` |
| Sync/async pooled outgoing requests | `HttpClient`, `Http` | Loopback client integration tests |
| Multipart uploads and response cookies | `PendingRequest`, `ClientResponse` | `tests/integration/http/test_client.py` |
| Streaming outgoing response cleanup | `HttpClient.stream_async` | `tests/integration/http/test_client.py` |
| SSE client consumption | `ClientResponse.iter_sse_async` | Loopback and parser tests |
| Context-local fakes and request assertions | `Http.fake`, `Http.assert_sent` | `tests/integration/http/test_http_fakes.py` |
| Bounded async request pools | `Http.pool`, `HttpPoolRequest` | `tests/integration/http/test_http_fakes.py` |
| Outbound URL scheme and credential checks | `PendingRequest`, `HttpClient` | Builder and client integration tests |
| Application-scoped client and request scope | `HttpServiceProvider`, `Application` | HTTP application integration tests |
| URI redirects | `ResponseFactory.redirect`, `Uri.redirect`, named Routing redirects | Routing URI integration tests use the canonical generator and native response factory |

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
sending its complete body. Streaming iterators close before that boundary
exits, including disconnect and cancellation paths. The request then closes
parser-owned resources in a cancellation-shielded finalizer.

The Foundation global middleware stack wraps the HTTP application. Router
middleware wraps only the selected endpoint. This ordering is intentional:
global middleware enters first and exits last. Registering the same middleware
at both levels invokes it twice; neither layer silently deduplicates the other.

## Input and output semantics

Query access is synchronous and preserves duplicate values through
`query_values`. Body parsing is asynchronous and cached. Merged input reads
query values first, then overlays parsed body values. Missing values remain
distinct from explicit null, false, zero, and empty values. Typed accessors
validate and raise native errors without echoing untrusted content.
Request metadata also exposes AJAX and JSON detection, a bounded correlation
identifier, and route name and parameters through the request attributes set
by Routing.

Response fluent header methods mutate the response and return it. JSON values
are validated against the supported JSON model. Statuses 204, 205, and 304,
and every `HEAD` response, transmit no body. Redirects reject
protocol-relative and unsupported schemes; external HTTP(S) targets need
explicit permission.

`Uri.redirect()` and named Routing redirects delegate to the application-owned
`ResponseFactory`. Named destinations use the canonical `UriUrlGenerator` and
are relative by default. Redirect validation remains the HTTP component's
responsibility.

## Outgoing request behavior

Request-builder methods return independent immutable builder states. Ordinary
network requests are explicitly synchronous or asynchronous. HTTP error
statuses do not raise automatically. `throw` is opt-in. Retry attempts are
bounded and selected per request; non-idempotent methods require an explicit
idempotency key before retry. Streaming uses an explicit response context
that owns connection release.

Multipart attachments contain replayable immutable bytes. Response cookies
are exposed as immutable values, and the shared client does not retain
upstream cookie state between requests. SSE response iterators parse events
incrementally from streaming byte iterators and cap each in-progress event at
1 MiB of UTF-8 data.

`Http.fake` adapts native fake responses to HTTPX2 mock transports. URL globs
or structured request patterns can repeat one response or consume a response
sequence. Requests are recorded for inspection and assertions. Unmatched
requests raise without a real-network fallback. Fake selection uses a
context-local value and nested scopes restore the previous fake. Facade and
injected-client requests share the active fake.

`Http.pool(max_concurrency=...)` runs named mappings or indexed sequences
through a bounded number of AnyIO workers. Per-request timeouts are supported.
Fail-fast mode cancels pending work and closes responses already received;
collect-errors mode returns exceptions beside successful responses. The
caller owns successful response cleanup.

Outgoing URL checks reject non-HTTP(S) schemes, embedded credentials,
protocol-relative destinations, control characters, and backslashes.
Relative paths require a valid configured base URL at the transport
boundary. Redirect following is disabled by default. When enabled, HTTPX2
follows redirects without a destination allowlist. These checks do not
resolve DNS, restrict private network ranges, or prevent DNS rebinding and
must not be treated as comprehensive SSRF protection.

## External integration requirements

- Authentication and authorization require their service providers to expose
  identity and permission context through native request scope.
- Sessions and CSRF protection require a Session owner and state lifecycle.
- Distributed rate limiting requires a Cache-backed policy owner.
- Persisting uploads requires the Filesystem component to define destination
  and cleanup ownership. Temporary upload inspection is already available.
- OpenTelemetry spans and metrics require the Telemetry component to define
  instrumentation and export lifecycle.
- Trusted proxy behavior must be configured at the ASGI server boundary with
  an explicit proxy allowlist. HTTP does not trust forwarded headers itself.
- Route-specific middleware composition belongs to Routing, which owns route
  groups and dispatch. HTTP reads selected route metadata from request
  attributes.
- Concrete response classes support cookie creation and removal. To expose
  those methods through the dependency-injected `HttpResponse` middleware
  boundary, Foundation must add them to the contract surface it adapts and
  delegate them from `_NativeHttpResponseAdapter` to Starlette's response.
- Windows and multiprocess behavior for application-owned connection pools
  has not been verified.

These boundaries do not block the implemented HTTP behavior above.
