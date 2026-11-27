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
from titanspan import Application
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
)

with application.context():
    Storage.disk("local").put("documents/report.txt", "Ready")
    content = Storage.disk("local").get("documents/report.txt")
```

The local disk uses `storage/app` under the application root when no root is
configured. Relative local roots resolve under `Application.base_path`.
Absolute roots remain unchanged, and relative roots that escape the root are
rejected. Memory disks receive private stores for each manager. Supply one
`FilesystemServiceProvider(drivers=...)` to customize registered fsspec
drivers. It replaces Foundation's default provider.

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

`Storage.fake` selects a context-local memory disk through the canonical
manager. Facade calls and injected `StorageManager.disk()` calls see the same
disk. Nested scopes restore the enclosing override, and sibling asynchronous
contexts own independent stores. The fake does not initialize the configured
backend.

```python
with application.context(), Storage.fake("local") as fake:
    Storage.disk("local").put("documents/report.txt", "Tested")
    fake.assert_stored("documents/report.txt", "Tested")
    Storage.assert_not_stored("documents/missing.txt", disk="local")
```

Assertions require an active fake. Custom managers implement the optional
`StorageDiskOverride` contract to support this substitution. Managers without
that capability fail explicitly. Tests can exercise a configured remote disk
without installing its optional fsspec integration.

See the [Filesystem specification](/framework/specifications/filesystem/)
for path boundaries, error behavior, and backend limitations.
