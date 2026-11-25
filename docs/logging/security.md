# Logging security

Titanspan redacts sensitive context before a record reaches listeners,
background queues, files, streams, webhooks, or the emergency fallback.
Default field fragments include password, secret, token, API key,
authorization, cookie, private key, access token, refresh token, and client
secret variants. Configure additional key fragments with `sensitive_fields`.

Redaction applies recursively to normalized mappings and sequences. It does
not reliably detect credentials embedded in free-form messages, arbitrary
binary data, or keys that do not identify sensitive values. Do not log full
prompts, model responses, workflow states, retrieved documents, request
bodies, authentication headers, database records, or embedding payloads.

Text messages escape line breaks and control characters to prevent forged
physical log lines. Structured values and message text are bounded; unknown
objects are not rendered with their arbitrary representations. Exception
tracebacks are formatted without frame locals and are also bounded.

Webhook and Slack destinations require HTTPS unless local HTTP is explicitly
enabled. URLs with embedded credentials or fragments, unsafe headers, and
redirect responses are rejected. Endpoint URLs must come from trusted
configuration; application code must still enforce destination and egress
policy appropriate to its deployment.

Never place secrets in log configuration committed to source control. Use
environment-backed application settings or an external secret manager, and
avoid logging configuration mappings themselves.
