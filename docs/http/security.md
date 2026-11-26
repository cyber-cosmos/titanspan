# HTTP security

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
bounded connection limits. Redirect following is disabled by default. Retry
policy respects idempotency: unsafe methods are not retried without an
`Idempotency-Key`. Transport and status errors omit credentials, URLs, and
response payloads from their default messages.

Do not log full request or response bodies, authorization headers, cookies,
tokens, or sensitive query values. Titanspan does not provide SSRF
protection, trusted-proxy policy, URL destination authorization, redirect
destination validation for outgoing requests, or DNS rebinding defenses.
Applications accepting user-selected destinations must implement a network
egress policy at the connection boundary. URL string checks alone are not an
SSRF defense.

Authentication, authorization, session, CSRF, rate-limit, and CORS policy
components are not part of the current HTTP implementation.
