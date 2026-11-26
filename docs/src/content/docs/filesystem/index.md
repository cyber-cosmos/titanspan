---
title: "Filesystem"
---

<span id="filesystem"></span>

Filesystem provides named storage disks over fsspec. Titanspan owns the disk
configuration, path rules, application registration, and developer API. fsspec
owns backend operations.

## Register storage

Pass `FilesystemServiceProvider` through the application's existing provider
extension. The provider reads `filesystem` settings from the canonical Config
repository and registers one manager in the application Container.

```python
from titanspan import Application, FilesystemServiceProvider
from titanspan.facades import Storage

application = Application(
    config={
        "filesystem": {
            "default": "local",
            "disks": {
                "local": {
                    "driver": "local",
                    "root": "storage/app",
                },
                "memory": {"driver": "memory"},
            },
        },
    },
    service_providers=(FilesystemServiceProvider(),),
)

with application.context():
    Storage.disk("local").put("documents/report.txt", "Ready")
    content = Storage.disk("local").get("documents/report.txt")
```

The local disk uses `storage/app` when no root is configured. Memory disks
receive private stores for each manager. Add custom fsspec drivers to
`FilesystemServiceProvider(drivers=...)` or call `FilesystemManager.extend`
before resolving any disk.

`FilesystemServiceProvider` is currently supplied explicitly. Foundation does
not include it among its built-in providers.

## Read and write files

`put` accepts text or bytes. `get` decodes text, and `get_bytes` returns exact
stored bytes. Use `exists`, `is_directory`, `size`, and `last_modified` for
metadata. Listing methods return sorted disk-relative paths.

```python
with application.context():
    disk = Storage.disk("local")
    disk.make_directory("reports/2026")
    disk.copy("documents/report.txt", "reports/2026/report.txt")
    disk.append("reports/2026/report.txt", "\nApproved")

    for path in disk.list_files("reports", recursive=True):
        print(path, disk.size(path))
```

`delete` removes one file. `delete_directory` removes a directory and accepts
`recursive=False` for empty directories. `copy` and `move` operate on files.
Pass `overwrite=False` to reject an existing destination.

## Asynchronous and streaming operations

Local and memory backends use synchronous fsspec APIs. Async methods offload
those calls to AnyIO's bounded worker pool, so they do not block the event
loop. The async methods do not make local I/O asynchronous at the backend.

```python
from fastapi import Request
from titanspan.facades import Storage


async def store_request(request: Request) -> bool:
    """Write request chunks without collecting the complete body.

    Args:
        request: Starlette request provided by the ASGI endpoint.

    Returns:
        Whether the configured disk accepted all chunks.
    """
    return await Storage.disk("local").write_stream_async(
        "uploads/generated-object.bin",
        request.stream(),
    )
```

Use server-generated names or validate names before creating storage keys.
`read_stream` and `read_stream_async` return bounded byte chunks. Stream
methods close their backend handles when iteration ends or is cancelled.
When a consumer stops early, close the iterator with `contextlib.closing` or
`contextlib.aclosing`.

Append uses backend append mode. A selected filesystem may reject append if
its implementation does not support that mode. Prepend reads and rewrites the
file, so it can buffer the previous contents in memory.

## Test fakes

`Storage.fake` overlays one named disk with a context-local memory disk.
Nested scopes restore the enclosing fake. Sibling asynchronous contexts own
independent stores.

```python
with application.context(), Storage.fake("local") as fake:
    Storage.disk("local").put("documents/report.txt", "Tested")
    fake.assert_stored("documents/report.txt", "Tested")
    Storage.assert_not_stored("documents/missing.txt", disk="local")
```

Assertions require an active fake. A fake does not initialize the configured
backend, so tests can exercise a remote disk without installing its optional
fsspec integration.

See the [Filesystem specification](/titanspan/specifications/filesystem/)
for path boundaries, error behavior, and backend limitations.
