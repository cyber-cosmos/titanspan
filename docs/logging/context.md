# Logging context

Context is execution-local. `LogManager` stores local and shared values in
`ContextVar` instances, so concurrent requests and tasks do not mutate one
process-wide dictionary.

```python
from titanspan.facades import Log

Log.with_context(request_id="req-123")
Log.share_context(tenant_id="tenant-7")
Log.info("Request received")

with Log.context(workflow_id="wf-12"):
    Log.info("Workflow started")
```

The application HTTP middleware binds the app name and a bounded request ID
for each request. Invalid, non-printable, missing, or overlong request IDs
are replaced with a generated identifier. Other workflow, agent, tool, job,
and trace fields are not inferred until their owning components provide
execution-scope integrations.

## Merge precedence

Records combine values in this order, from lowest to highest precedence:

1. Shared execution context from `share_context`.
2. Local execution context from `with_context` or application middleware.
3. Context bound to a derived `Logger.with_context` instance.
4. The positional context mapping passed to the log call.
5. Keyword values passed to the log call.

Later values replace earlier values with the same key. Keyword values
therefore override the positional mapping. Redaction happens after merging
and before events, queueing, or destination delivery.

Use `without_context`, `flush_shared_context`, and `flush_context` to remove
values. The `Log.context(...)` scope restores its previous values in a
`finally` block, including when application code raises or is cancelled.

The facade must be bound with `Log.use(manager)` for standalone use. Titanspan
does not keep a global mutable manager or global context repository. Laravel's
hidden context, dehydration/hydration, and persistent context repository APIs
are not implemented yet.
