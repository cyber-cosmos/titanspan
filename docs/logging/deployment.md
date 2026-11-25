# Logging deployment

For containers and multiprocess web servers, structured stdout output is a
first-class configuration:

```python
logging_configuration = {
    "default": "stdout",
    "channels": {
        "stdout": {
            "driver": "stdout",
            "formatter": "json",
            "level": "info",
        },
    },
}
```

Let the process supervisor or log collector own aggregation, retention, and
forwarding. Ordinary rotating file handlers are process-local and should not
be treated as a safe shared multi-process file coordination mechanism. Use
stdout collection, per-process files, or a centralized destination for
multiple workers.

The standard logging bridge captures only explicitly selected logger names.
Importing Titanspan does not configure root loggers. Bridge handles are owned
by `LogManager` and close during manager shutdown. Existing handlers,
thresholds, and propagation settings remain application-owned.

Background dispatch is process-local and in-memory. Pending records are
drained on graceful shutdown but cannot survive process termination. Use a
dedicated durable queue or external collector when loss across crashes is
unacceptable; Titanspan does not currently provide a distributed log store.
