# Testing logging

Use `Log.fake()` to replace the active manager's destinations with a bounded
memory sink for one execution scope:

```python
with Log.fake():
    Log.info("Workflow completed", workflow_id="wf-123")
    Log.assert_logged(
        "info",
        "Workflow completed",
        context={"workflow_id": "wf-123"},
    )
    Log.assert_not_logged("error")
```

Assertions accept optional severity, message, channel, context subset, and
record predicate filters. Available assertions are `assert_logged`,
`assert_not_logged`, `assert_logged_times`, and `assert_nothing_logged`, with
Laravel-compatible camelCase aliases. A fake is isolated to the active
context and restores the previous manager on scope exit, including failure.

For direct unit tests, `MemoryLogDriver` retains a bounded sequence of native
`LogRecord` instances. For integration tests, use temporary directories,
captured standard streams, and loopback-only HTTP receivers. Do not configure
production credentials or notify external services in the default test
suite.
