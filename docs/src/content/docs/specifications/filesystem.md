---
title: "Filesystem component specification"
---

<span id="filesystem-component-specification"></span>

Filesystem provides named disks over fsspec's public filesystem API. Titanspan
owns configuration parsing, disk identity, key validation, metadata values,
and application integration. It does not implement a storage engine.

## Application integration

`FilesystemServiceProvider` registers one `FilesystemManager` singleton and
binds `StorageManager` to that same instance. The provider consumes the
application's `ConfigRepository`. `Storage` resolves `StorageManager` from the
active application's canonical Container.

Applications opt in through `Application.service_providers`. Foundation does
not register the provider by default. Adding it to Foundation's built-in
provider list would require a focused lifecycle integration change by the
Foundation owner.

Settings live under `filesystem`:

```python
{
    "filesystem": {
        "default": "local",
        "disks": {
            "local": {
                "driver": "local",
                "root": "storage/app",
                "raise_errors": True,
                "options": {},
            },
            "memory": {
                "driver": "memory",
                "root": "documents",
            },
        },
    },
}
```

The default configuration provides a `local` disk rooted at `storage/app`.
Each manager owns its fsspec filesystem objects. Memory storage disables
fsspec's process-global store and instance cache.

Custom driver factories receive immutable `FilesystemDiskConfiguration`
values. They return an fsspec `AbstractFileSystem`; optional remote packages
can be installed by applications that register those factories. Backend
options remain backend-specific and are passed only to the selected factory.

## Disk semantics

All operation keys are disk-relative POSIX names. Empty keys are accepted
only when a listing method selects the disk root. Keys reject absolute names,
parent traversal, backslashes, control characters, unsafe punctuation,
Windows device names, and trailing dots or spaces.

Local paths resolve beneath the configured root. Existing symbolic-link
components are rejected before an operation. The public fsspec API accepts
path strings rather than directory handles, so a privileged process that
changes a path concurrently can race this check. Do not let untrusted users
modify the configured root or its parents.

`put`, `copy`, `move`, `append`, and `prepend` return `True` after success.
Missing deletes return `False`. Set `raise_errors=False` per disk or operation
to return `False` for suppressed `OSError` failures. Path validation errors
and programming errors always raise. Reads preserve native `OSError`
subclasses such as `FileNotFoundError` and `IsADirectoryError`.

`delete` removes files only. `delete_directory` removes directories and uses
`rmdir` for non-recursive deletion. `copy` and `move` accept files, not
directory trees. These methods delegate replacement and consistency behavior
to the selected fsspec backend.

`FileMetadata.size` and `FileMetadata.modified` are optional when a backend
does not provide those values. Modification timestamps normalize to aware UTC
values. Listings sort by disk-relative path and exclude their selected root.

## Async operations and streaming

Synchronous methods call the configured backend directly. Explicit async
methods use AnyIO's bounded worker pool around synchronous fsspec operations.
Async methods are available for common reads, writes, metadata, directory
operations, and streaming. Local and memory backends do not provide genuine
async filesystem I/O.

Streaming reads and writes consume bounded chunks without buffering the full
file. Async stream reads close their backend handle in shielded cleanup after
normal completion, failure, or cancellation. Async writes close their handle
in a shielded cleanup block. A failed or cancelled direct write may leave a
partial file; no cross-backend atomic-write guarantee exists.

Consumers that stop reading early must close the sync or async iterator. Use
`contextlib.closing` or `contextlib.aclosing` for deterministic cleanup.

`temporary_file` and `temporary_file_async` create an unpredictable empty file
and remove it when the context exits. The backend must support ordinary file
creation and deletion. Cleanup failures remain visible.

Append requires support for the backend's `ab` mode. Prepend reads the current
file and rewrites it, so large files require memory proportional to their
size. Prepend is not atomic.

## Fakes and assertions

`Storage.fake(name)` selects a private in-memory disk for the active
application and execution context. It restores nested overlays on every exit.
The fake does not construct the configured backend. `FilesystemFake` and
`Storage` provide existence, absence, and exact-content assertions.

Production code never resolves fakes from a process-global registry. Each
application's manager remains the sole owner of configured production disks.

## Integration boundaries

- HTTP request streams can be passed to `write_stream_async` as an
  `AsyncIterable[bytes]`. HTTP does not select storage destinations or own
  filesystem cleanup policies.
- Future AI document ingestion can consume `read_stream_async` without
  loading the complete file into memory.
- Remote storage drivers require their optional fsspec integrations and a
  trusted custom factory. Titanspan does not implement S3, Azure, or GCS
  clients.
- Database-backed model binding is outside Routing and remains excluded until
  the dedicated Database component exists.
- Filesystem does not provide encryption, key management, signed URLs, or
  authorization policies.

## Verification

`tests/unit/filesystem/test_storage.py` exercises real local and memory
fsspec implementations, path validation, overwrite behavior, metadata,
streaming, and cleanup. `tests/integration/test_filesystem.py` verifies
Container identity, context-local fakes, application isolation, and request
stream persistence through the real ASGI stack.
