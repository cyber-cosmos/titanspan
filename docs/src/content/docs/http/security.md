---
title: "HTTP security"
---

<span id="http-security"></span>

Incoming request values and external responses are untrusted. Use typed
request accessors, enforce domain validation, and bound the amount of input
the application consumes. Request body and multipart limits are configured
at application startup. Uploaded filenames are display metadata only; choose
an application-owned destination path when storing an upload.

Response header names and values reject malformed tokens and line breaks.
Cookie values and attributes are validated, with `Secure`, `HttpOnly`, and
`SameSite=Lax` defaults. Redirects are local by default; external redirects
require explicit permission. File downloads require a trusted application
path.

Outgoing TLS verification is enabled by default. Set finite timeouts and
bounded connection limits. Redirect following is disabled by default. Direct
outbound destinations reject non-HTTP(S) schemes, embedded credentials,
protocol-relative URLs, control characters, and backslashes. Relative paths
must resolve against a configured HTTP(S) base URL. Retry policy respects
idempotency: unsafe methods are not retried without an `Idempotency-Key`.
Transport and status errors omit credentials, URLs, and response payloads
from their default messages.

Do not log full request or response bodies, authorization headers, cookies,
tokens, or sensitive query values. The outbound URL checks are practical
input restrictions. They do not resolve DNS, reject private or link-local
addresses, validate redirect targets, or prevent DNS rebinding. They do not
provide comprehensive SSRF protection. Applications accepting user-selected
destinations need an egress policy at the connection boundary.

Use `CorsMiddleware`, `TrustedHostMiddleware`, and
`HttpsRedirectMiddleware` for their documented Starlette behavior. Configure
the ASGI server's trusted proxy handling with an explicit proxy allowlist.
Titanspan does not trust forwarded headers by default.

Authentication, authorization, session, CSRF, and distributed rate-limit
policies require their owning components.
