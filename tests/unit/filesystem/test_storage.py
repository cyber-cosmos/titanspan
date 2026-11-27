"""Verify the filesystem disk API and its native safety boundaries.

Tests use real fsspec LocalFileSystem and MemoryFileSystem backends.
"""

from __future__ import annotations

from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import anyio
import fsspec.implementations.memory as _memory  # pyright: ignore
import pytest

from titanspan.config import Repository
from titanspan.contracts.filesystem import StorageDisk
from titanspan.filesystem import (
    FilesystemConfiguration,
    FilesystemConfigurationError,
    FilesystemDisk,
    FilesystemDiskConfiguration,
    FilesystemDiskError,
    FilesystemDriverFactory,
    FilesystemFake,
    FilesystemManager,
    UnknownFilesystemDiskError,
    UnsafeStoragePathError,
)
from titanspan.filesystem._backends import (
    create_local_filesystem,
    create_memory_filesystem,
)

pytestmark = pytest.mark.unit
_BODY_SIZE = 4
_PRIVATE_FACTORY_ERROR = "secret-token-value"
_PRIVATE_BACKEND_CLOSE_ERROR = "backend credential close failure"
_OPEN_FAILED_ERROR = "open failed"
_WRITE_FAILED_ERROR = "write failed"

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from titanspan.filesystem._types import (
        FilesystemStream,
        FsspecFilesystem,
    )


def _local_disk(root: Path) -> FilesystemManager:
    """Build a manager with one rooted local disk.

    Args:
        root: Temporary directory used as the disk root.

    Returns:
        A manager whose local disk cannot access paths outside ``root``.
    """
    configuration = FilesystemConfiguration(
        default_disk="local",
        disks={
            "local": FilesystemDiskConfiguration(
                driver="local",
                root=root,
            ),
        },
    )
    return FilesystemManager(configuration)


def _local_manager_with_filesystem(
    root: Path,
) -> tuple[FilesystemManager, FsspecFilesystem]:
    """Return a manager and its captured local fsspec backend.

    Args:
        root: Trusted local directory used as the disk root.

    Returns:
        A resolved manager and the backend instance used by its disk.
    """
    captured: list[FsspecFilesystem] = []

    def make_filesystem(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create and retain one local backend for stream instrumentation.

        Args:
            configuration: Settings selected by the disk manager.

        Returns:
            The isolated local fsspec implementation.
        """
        filesystem = create_local_filesystem(configuration)
        captured.append(filesystem)
        return filesystem

    manager = FilesystemManager(
        FilesystemConfiguration(
            default_disk="local",
            disks={
                "local": FilesystemDiskConfiguration(
                    driver="tracked-local",
                    root=root,
                ),
            },
        ),
        drivers={"tracked-local": make_filesystem},
    )
    manager.disk()
    return manager, captured[0]


def _collision_token(size: int) -> str:
    """Return a fixed token to exercise temporary-name collisions.

    Args:
        size: Requested token length, ignored by this deterministic test.

    Returns:
        A stable token that matches the pre-existing test file.
    """
    _ = size
    return "collision"


class _AsyncClosableMemoryFilesystem(
    _memory.MemoryFileSystem,  # pyright: ignore[reportUnknownBaseType]
):
    """Record asynchronous backend cleanup through a public close hook.

    The locked fsspec release does not publish complete typing stubs.
    """

    def __init__(self, closed: list[str]) -> None:
        """Create an isolated memory backend with observable cleanup.

        Args:
            closed: List updated by whichever close hook executes.
        """
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            global_store=False,
        )
        self._closed = closed

    async def aclose(self) -> None:
        """Record asynchronous backend finalization.

        The manager awaits this hook directly.
        """
        self._closed.append("aclose")

    _closed: list[str]
    cachable = False


class _AwaitableCloseMemoryFilesystem(
    _memory.MemoryFileSystem,  # pyright: ignore[reportUnknownBaseType]
):
    """Return an awaitable from a synchronous backend close hook.

    Some fsspec adapters expose a synchronous wrapper for async cleanup.
    """

    def __init__(self, closed: list[str]) -> None:
        """Create an isolated memory backend with observable cleanup.

        Args:
            closed: List updated after the awaitable close completes.
        """
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            global_store=False,
        )
        self._closed = closed

    async def _close_async(self) -> None:
        """Record cleanup after the synchronous close returns its awaitable.

        The disk adapter must await this result rather than discard it.
        """
        self._closed.append("close-awaitable")

    def close(self) -> object:
        """Return the coroutine that owns asynchronous finalization.

        Returns:
            An awaitable result consumed by the disk adapter.
        """
        return self._close_async()

    _closed: list[str]
    cachable = False


class _FailingCloseMemoryFilesystem(
    _memory.MemoryFileSystem,  # pyright: ignore[reportUnknownBaseType]
):
    """Raise one backend cleanup error without leaking its message.

    The manager must continue finalizing the remaining owned filesystems.
    """

    cachable = False

    def close(self) -> None:
        """Raise a secret-bearing close failure for manager translation.

        Raises:
            OSError: Always, to exercise cleanup failure handling.
        """
        raise OSError(_PRIVATE_BACKEND_CLOSE_ERROR)


class _TrackedStream:
    """Observe closure while delegating real local file operations.

    The wrapper keeps tests on supported fsspec stream APIs.
    """

    def __init__(
        self,
        stream: FilesystemStream,
        closed: list[bool],
    ) -> None:
        """Retain one real backend stream and its close observations.

        Args:
            stream: Binary stream returned by the real fsspec backend.
            closed: Mutable test evidence updated by ``close``.
        """
        self._stream = stream
        self._closed = closed

    def read(self, size: int = -1) -> bytes:
        """Read bytes through the wrapped backend stream.

        Args:
            size: Maximum bytes requested from the backend.

        Returns:
            Bytes returned by the wrapped stream.
        """
        return self._stream.read(size)

    def write(self, data: bytes) -> int:
        """Write bytes through the wrapped backend stream.

        Args:
            data: Bytes written by the storage adapter.

        Returns:
            Number of bytes accepted by the backend.
        """
        return self._stream.write(data)

    def close(self) -> None:
        """Close the backend stream and record deterministic cleanup.

        The test reads the evidence after AnyIO finishes the worker operation.
        """
        try:
            self._stream.close()
        finally:
            self._closed.append(True)

    _stream: FilesystemStream
    _closed: list[bool]


class _FailingWriteStream:
    """Raise from writes while delegating deterministic stream cleanup.

    The wrapper exercises the disk's configured async error policy.
    """

    def __init__(self, stream: FilesystemStream) -> None:
        """Retain the backend stream whose writes will be rejected.

        Args:
            stream: Real fsspec stream opened for one test operation.
        """
        self._stream = stream

    def read(self, size: int = -1) -> bytes:
        """Read bytes through the wrapped backend stream.

        Args:
            size: Maximum bytes requested from the backend.

        Returns:
            Bytes returned by the wrapped stream.
        """
        return self._stream.read(size)

    def write(self, data: bytes) -> int:
        """Raise a backend write error without exposing file content.

        Args:
            data: Bytes supplied by the storage adapter.

        Returns:
            No byte count is returned when the write fails.
        """
        _ = data
        raise OSError(_WRITE_FAILED_ERROR)

    def close(self) -> None:
        """Close the wrapped backend handle after a failed write.

        Returns:
            None.
        """
        self._stream.close()

    _stream: FilesystemStream


def test_filesystem_configuration_uses_the_native_repository(
    tmp_path: Path,
) -> None:
    """Parse named disk settings and retain pathlib roots as native values.

    Configuration validation rejects malformed namespaces without leaking
    implementation exceptions from nested mapping access.
    """
    repository = Repository(
        {
            "filesystem": {
                "default": "archive",
                "disks": {
                    "archive": {
                        "driver": "local",
                        "root": tmp_path,
                    },
                },
            },
        },
    )
    configuration = FilesystemConfiguration.from_repository(repository)

    assert configuration.default_disk == "archive"
    assert configuration.disks["archive"].root == tmp_path
    with pytest.raises(FilesystemConfigurationError):
        FilesystemConfiguration(default_disk="unknown")
    with pytest.raises(FilesystemConfigurationError):
        FilesystemConfiguration.from_repository(
            Repository({"filesystem": "invalid"}),
        )


def test_application_relative_roots_are_anchored_and_absolute_roots_remain(
    tmp_path: Path,
) -> None:
    """Anchor local relative paths without rewriting absolute paths.

    Remote backend prefixes remain backend-owned values.
    """
    application_root = tmp_path / "application"
    absolute_root = tmp_path / "external-storage"
    repository = Repository(
        {
            "filesystem": {
                "default": "relative",
                "disks": {
                    "relative": {
                        "driver": "local",
                        "root": "storage/app",
                    },
                    "absolute": {
                        "driver": "local",
                        "root": str(absolute_root),
                    },
                    "remote": {
                        "driver": "remote",
                        "root": "bucket/documents",
                    },
                },
            },
        },
    )

    configuration = FilesystemConfiguration.from_repository(
        repository,
        base_path=application_root,
    )

    assert (
        configuration.disks["relative"].root
        == (application_root / "storage/app").resolve()
    )
    assert configuration.disks["absolute"].root == str(absolute_root)
    assert configuration.disks["remote"].root == "bucket/documents"


def test_application_relative_local_root_cannot_escape_application(
    tmp_path: Path,
) -> None:
    """Reject parent traversal in application-relative disk roots.

    Explicit absolute roots remain available for trusted configurations.
    """
    with pytest.raises(
        FilesystemConfigurationError,
        match="inside the application root",
    ):
        FilesystemConfiguration.from_repository(
            Repository(
                {
                    "filesystem": {
                        "disks": {
                            "local": {
                                "driver": "local",
                                "root": "../shared",
                            },
                        },
                    },
                },
            ),
            base_path=tmp_path,
        )


def test_manager_rejects_unknown_disk_and_driver() -> None:
    """Report disk selection and driver errors through native exceptions.

    Driver failures use safe configuration messages without backend details.
    """
    with pytest.raises(UnknownFilesystemDiskError):
        FilesystemManager().disk("missing")

    configuration = FilesystemConfiguration(
        default_disk="remote",
        disks={
            "remote": FilesystemDiskConfiguration(driver="unavailable"),
        },
    )
    with pytest.raises(FilesystemDiskError):
        FilesystemManager(configuration).disk()


@pytest.mark.anyio
async def test_manager_closes_async_backend_once_after_shutdown() -> None:
    """Use the explicit asynchronous close hook and reject later access.

    Repeated shutdown must not finalize a backend more than once.
    """
    closed: list[str] = []

    def make_backend(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create an isolated fsspec backend with asynchronous cleanup.

        Args:
            configuration: Named disk settings supplied by the manager.

        Returns:
            A real memory filesystem with a tracked async close hook.
        """
        _ = configuration
        # fsspec's incomplete stubs hide this real AbstractFileSystem surface.
        return cast(
            "FsspecFilesystem",
            _AsyncClosableMemoryFilesystem(closed),
        )

    configuration = FilesystemConfiguration(
        default_disk="memory",
        disks={
            "memory": FilesystemDiskConfiguration(driver="tracked"),
        },
    )
    manager = FilesystemManager(
        configuration,
        drivers={"tracked": make_backend},
    )
    disk = manager.disk()

    await manager.aclose()
    await manager.aclose()

    assert closed == ["aclose"]
    with pytest.raises(FilesystemDiskError):
        manager.disk()
    with (
        pytest.raises(FilesystemDiskError),
        manager.override_disk("memory", disk),
    ):
        pass


@pytest.mark.anyio
async def test_disk_awaits_async_result_from_backend_close() -> None:
    """Await async cleanup returned by a synchronous fsspec close method.

    The disk adapter supports backends that bridge asynchronous close hooks.
    """
    closed: list[str] = []

    def make_backend(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create an isolated backend with a coroutine-returning close hook.

        Args:
            configuration: Named disk settings supplied by the manager.

        Returns:
            A real memory filesystem with an awaitable close result.
        """
        _ = configuration
        # The locked fsspec stubs omit several AbstractFileSystem methods.
        return cast("FsspecFilesystem", _AwaitableCloseMemoryFilesystem(closed))

    manager = FilesystemManager(
        FilesystemConfiguration(
            default_disk="memory",
            disks={
                "memory": FilesystemDiskConfiguration(driver="tracked"),
            },
        ),
        drivers={"tracked": make_backend},
    )
    manager.disk()

    await manager.aclose()

    assert closed == ["close-awaitable"]


@pytest.mark.anyio
async def test_manager_finalizes_all_backends_after_cleanup_failure() -> None:
    """Continue resource cleanup when one backend close operation fails.

    The manager reports a safe error after attempting every owned backend.
    """
    closed: list[str] = []

    def make_backend(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create a backend selected by the configured root marker.

        Args:
            configuration: Disk settings supplied by the manager.

        Returns:
            A failing or observable real fsspec memory filesystem.
        """
        if configuration.root == "failure":
            return cast(
                "FsspecFilesystem",
                _FailingCloseMemoryFilesystem(),
            )
        return cast(
            "FsspecFilesystem",
            _AsyncClosableMemoryFilesystem(closed),
        )

    manager = FilesystemManager(
        FilesystemConfiguration(
            default_disk="failure",
            disks={
                "failure": FilesystemDiskConfiguration(
                    driver="tracked",
                    root="failure",
                ),
                "success": FilesystemDiskConfiguration(
                    driver="tracked",
                    root="success",
                ),
            },
        ),
        drivers={"tracked": make_backend},
    )
    manager.disk("failure")
    manager.disk("success")

    with pytest.raises(FilesystemDiskError) as captured:
        await manager.aclose()

    assert closed == ["aclose"]
    assert _PRIVATE_BACKEND_CLOSE_ERROR not in str(captured.value)
    assert captured.value.__cause__ is None


def test_manager_wraps_custom_driver_failures_without_sensitive_messages() -> (
    None
):
    """Avoid printing backend factory details in safe configuration errors.

    Third-party filesystem factories may include credentials in their errors.
    """

    def make_backend(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Raise a private-looking error while constructing a disk.

        Args:
            configuration: Named disk settings supplied by the manager.

        Returns:
            No backend is produced by this failing factory.
        """
        _ = configuration
        raise OSError(_PRIVATE_FACTORY_ERROR)

    configuration = FilesystemConfiguration(
        default_disk="remote",
        disks={
            "remote": FilesystemDiskConfiguration(driver="remote"),
        },
    )
    manager = FilesystemManager(
        configuration,
        drivers={"remote": make_backend},
    )

    with pytest.raises(FilesystemConfigurationError) as failure:
        manager.disk()
    assert _PRIVATE_FACTORY_ERROR not in str(failure.value)
    assert failure.value.__cause__ is None


@pytest.mark.parametrize(
    "settings",
    [
        {"default": 1},
        {"disks": "invalid"},
        {"default": "missing", "disks": {"local": {"driver": "local"}}},
        {"disks": {"": {"driver": "local"}}},
        {"disks": {"local": None}},
        {"disks": {"local": {"driver": 1}}},
        {"disks": {"local": {"driver": "local", "root": 42}}},
        {
            "disks": {
                "local": {"driver": "local", "raise_errors": "false"},
            },
        },
        {"disks": {"local": {"driver": "local", "options": []}}},
        {"disks": {}},
    ],
)
def test_filesystem_configuration_rejects_invalid_shapes(
    settings: dict[str, object],
) -> None:
    """Reject malformed filesystem namespaces with a native exception.

    Nested application configuration never leaks mapping or type errors.
    """
    with pytest.raises(FilesystemConfigurationError):
        FilesystemConfiguration.from_repository(
            Repository({"filesystem": settings}),
        )


def test_filesystem_configuration_uses_local_defaults_and_freezes_options() -> (
    None
):
    """Apply local defaults while keeping disk settings immutable.

    Caller mutations cannot change options already retained by a disk config.
    """
    options: dict[str, object] = {"auto_mkdir": True}
    disk_configuration = FilesystemDiskConfiguration(
        driver="local",
        options=options,
    )
    options["auto_mkdir"] = False
    assert disk_configuration.options["auto_mkdir"] is True
    with pytest.raises(TypeError):
        cast("dict[str, object]", disk_configuration.options)["auto_mkdir"] = (
            False
        )
    with pytest.raises(FilesystemConfigurationError):
        FilesystemDiskConfiguration(driver=" ")

    configuration = FilesystemConfiguration.from_repository(
        Repository({"filesystem": {"disks": {"local": {"driver": "local"}}}}),
    )
    assert configuration.default_disk == "local"
    assert configuration.disks["local"].root == Path("storage/app")


@pytest.mark.parametrize(
    ("factory", "options"),
    [
        (create_local_filesystem, {"skip_instance_cache": False}),
        (create_local_filesystem, {"protocol": "memory"}),
        (create_memory_filesystem, {"global_store": True}),
        (create_memory_filesystem, {"skip_instance_cache": False}),
        (create_memory_filesystem, {"protocol": "file"}),
    ],
)
def test_builtin_drivers_reject_options_that_break_isolation(
    factory: FilesystemDriverFactory,
    options: dict[str, object],
) -> None:
    """Protect local and memory backend settings owned by the manager.

    Applications cannot override protocols or memory-store isolation.
    """
    driver = "local" if factory is create_local_filesystem else "memory"
    configuration = FilesystemDiskConfiguration(
        driver=driver,
        options=options,
    )
    with pytest.raises(FilesystemConfigurationError):
        factory(configuration)


def test_local_disk_supports_file_operations_and_metadata(
    tmp_path: Path,
) -> None:
    """Write, copy, move, inspect, append, and prepend through fsspec.

    The public disk API returns application-relative paths and native values.
    """
    disk = _local_disk(tmp_path).disk()
    assert isinstance(disk, StorageDisk)

    assert disk.put("documents/report.txt", "body")
    assert disk.get("documents/report.txt") == "body"
    assert disk.get_bytes("documents/report.txt") == b"body"
    assert disk.exists("documents/report.txt")
    assert disk.is_directory("documents")
    assert disk.size("documents/report.txt") == _BODY_SIZE
    metadata = disk.metadata("documents/report.txt")
    assert metadata.path == "documents/report.txt"
    assert metadata.size == _BODY_SIZE
    assert metadata.modified is not None
    assert metadata.is_file
    assert not metadata.is_directory
    assert disk.last_modified("documents/report.txt") is not None
    assert disk.list_files("", recursive=True) == ("documents/report.txt",)
    assert disk.list_directories("", recursive=True) == ("documents",)
    assert disk.copy("documents/report.txt", "documents/copy.txt")
    assert disk.append("documents/copy.txt", "!")
    assert disk.prepend("documents/copy.txt", "new ")
    assert disk.get("documents/copy.txt") == "new body!"
    assert disk.move("documents/copy.txt", "documents/archive/copy.txt")
    assert disk.get("documents/archive/copy.txt") == "new body!"
    assert disk.delete("documents/archive/copy.txt")
    assert disk.make_directory("empty/nested")
    with pytest.raises(OSError, match="Directory not empty"):
        disk.delete_directory("empty", recursive=False)
    assert disk.delete_directory("empty/nested", recursive=False)
    assert disk.delete_directory("empty", recursive=True)


def test_copy_and_move_honor_existing_destination_policy(
    tmp_path: Path,
) -> None:
    """Preserve destination content when replacement is explicitly disabled.

    Existing local backend operations replace files only after the adapter's
    overwrite validation permits the change.
    """
    disk = _local_disk(tmp_path).disk()
    assert disk.put("source.txt", "source")
    assert disk.put("copy.txt", "copy")
    assert disk.put("move.txt", "move")

    with pytest.raises(FileExistsError):
        disk.copy("source.txt", "copy.txt", overwrite=False)
    with pytest.raises(FileExistsError):
        disk.move("source.txt", "move.txt", overwrite=False)

    assert disk.copy("source.txt", "copy.txt")
    assert disk.move("source.txt", "move.txt")
    assert disk.get("copy.txt") == "source"
    assert disk.get("move.txt") == "source"
    assert not disk.exists("source.txt")


def test_file_and_directory_operations_preserve_native_errors(
    tmp_path: Path,
) -> None:
    """Reject file and directory operation mismatches consistently.

    Missing deletes are idempotent while invalid targets keep native errors.
    """
    disk = _local_disk(tmp_path).disk()
    assert not disk.delete("missing.txt")
    assert disk.put("file.txt", "content")
    assert disk.make_directory("folder")

    with pytest.raises(IsADirectoryError):
        disk.delete("folder")
    with pytest.raises(IsADirectoryError):
        disk.put("folder", "content")
    assert not disk.delete_directory("missing")
    with pytest.raises(NotADirectoryError):
        disk.delete_directory("file.txt")
    with pytest.raises(FileNotFoundError):
        disk.copy("missing.txt", "copy.txt")
    with pytest.raises(IsADirectoryError):
        disk.copy("folder", "copy.txt")
    with pytest.raises(ValueError, match="must differ"):
        disk.copy("file.txt", "file.txt")
    with pytest.raises(FileNotFoundError):
        disk.move("missing.txt", "moved.txt")
    with pytest.raises(IsADirectoryError):
        disk.move("folder", "moved.txt")
    with pytest.raises(ValueError, match="must differ"):
        disk.move("file.txt", "file.txt")
    with pytest.raises(IsADirectoryError):
        disk.append("folder", "more")
    with pytest.raises(IsADirectoryError):
        disk.prepend("folder", "before")


def test_listing_handles_missing_roots_paths_and_files(
    tmp_path: Path,
) -> None:
    """Return an empty missing root and preserve invalid listing errors.

    Selecting a missing child or a file as a directory remains an error.
    """
    disk = _local_disk(tmp_path / "not-created").disk()
    assert disk.list_contents("") == ()
    with pytest.raises(FileNotFoundError):
        disk.list_contents("missing")
    assert disk.put("file.txt", "content")
    with pytest.raises(NotADirectoryError):
        disk.list_contents("file.txt")


def test_directory_creation_can_require_existing_parents(
    tmp_path: Path,
) -> None:
    """Honor strict parent creation and configurable I/O error handling.

    Suppressed backend errors return false without accepting unsafe paths.
    """
    disk = _local_disk(tmp_path).disk()
    with pytest.raises(FileNotFoundError):
        disk.make_directory("missing/child", create_parents=False)
    assert not disk.make_directory(
        "missing/child",
        create_parents=False,
        raise_errors=False,
    )
    with pytest.raises(UnsafeStoragePathError):
        disk.make_directory("../outside", raise_errors=False)


def test_streaming_rejects_invalid_chunks_and_temporary_paths(
    tmp_path: Path,
) -> None:
    """Reject malformed stream chunks and unsafe temporary file names.

    Path validation remains active when operation errors are suppressed.
    """
    disk = _local_disk(tmp_path).disk()
    with pytest.raises(ValueError, match="positive integer"):
        next(disk.read_stream("unused.txt", chunk_size=0))
    with pytest.raises(ValueError, match="positive integer"):
        next(disk.read_stream("unused.txt", chunk_size=True))
    with pytest.raises(TypeError):
        disk.write_stream(
            "invalid.bin",
            cast("Iterable[bytes]", ("not bytes",)),
        )
    with (
        pytest.raises(UnsafeStoragePathError),
        disk.temporary_file(suffix="/unsafe"),
    ):
        pytest.fail("Unsafe suffix opened a temporary file.")
    with pytest.raises(UnsafeStoragePathError):
        FilesystemDisk(
            create_memory_filesystem(
                FilesystemDiskConfiguration(driver="memory"),
            ),
            root="../escape",
        )


@pytest.mark.parametrize(
    "path",
    [
        ("bad?name.txt",),
        ("CON.txt",),
        ("nested/NUL",),
        ("trailing.",),
        ("trailing ",),
        ("control\nname",),
    ],
)
def test_disk_rejects_nonportable_or_controlled_names(
    tmp_path: Path,
    path: str,
) -> None:
    """Reject unsafe filenames before the selected backend sees the path.

    The same disk-key rules apply to local and remote fsspec implementations.
    """
    disk = _local_disk(tmp_path).disk()

    with pytest.raises(UnsafeStoragePathError):
        disk.put(path, "blocked")


def test_memory_disks_are_isolated_between_application_managers() -> None:
    """Keep independent fsspec memory filesystems from sharing file state.

    The fsspec memory backend uses process-global storage unless disabled.
    """
    configuration = FilesystemConfiguration(
        default_disk="memory",
        disks={
            "memory": FilesystemDiskConfiguration(
                driver="memory",
                root="tenant-a",
            ),
        },
    )
    first = FilesystemManager(configuration).disk()
    second = FilesystemManager(configuration).disk()

    assert first.put("notes.txt", "private")
    assert first.get("notes.txt") == "private"
    assert not second.exists("notes.txt")


def test_memory_manager_accepts_a_custom_fsspec_driver() -> None:
    """Build configured custom disks through a registered fsspec factory.

    Custom storage delegates operations to a supported fsspec filesystem.
    """

    def make_custom_disk(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create the test backend selected by a custom driver name.

        Args:
            configuration: Disk settings supplied by the manager.

        Returns:
            An independent fsspec memory filesystem.
        """
        _ = configuration
        return create_memory_filesystem(configuration)

    configuration = FilesystemConfiguration(
        default_disk="archive",
        disks={
            "archive": FilesystemDiskConfiguration(
                driver="test-memory",
                root="archive",
            ),
        },
    )
    manager = FilesystemManager(configuration)
    manager.extend("test-memory", make_custom_disk)

    assert manager.disk().put("report.txt", "archived")
    assert manager.disk().get("report.txt") == "archived"


def test_custom_driver_registration_closes_after_disk_resolution() -> None:
    """Keep a manager's driver graph stable once it creates a disk.

    Existing disk handles must not silently use an older driver factory.
    """
    configuration = FilesystemConfiguration(
        default_disk="memory",
        disks={
            "memory": FilesystemDiskConfiguration(driver="memory"),
        },
    )
    manager = FilesystemManager(configuration)
    manager.disk()

    def make_memory(
        settings: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Create a backend for a driver registration expected to fail.

        Args:
            settings: Disk settings supplied by the manager.

        Returns:
            An isolated in-memory fsspec filesystem.
        """
        _ = settings
        return create_memory_filesystem(settings)

    with pytest.raises(FilesystemDiskError, match="already resolved"):
        manager.extend("archive", make_memory)


def test_manager_rejects_duplicate_invalid_and_non_fsspec_drivers() -> None:
    """Validate custom driver names, uniqueness, and backend instances.

    A bad factory result must not be accepted as an application disk.
    """
    manager = FilesystemManager()
    with pytest.raises(FilesystemConfigurationError):
        FilesystemManager(drivers={"memory": create_memory_filesystem})
    with pytest.raises(FilesystemConfigurationError):
        manager.extend("bad driver", create_memory_filesystem)

    manager.extend("archive", create_memory_filesystem)
    with pytest.raises(FilesystemDiskError, match="already registered"):
        manager.extend("archive", create_memory_filesystem)

    def make_invalid_filesystem(
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Return a value that is not an fsspec filesystem instance.

        Args:
            configuration: Disk configuration passed by the manager.

        Returns:
            A deliberately invalid object for manager validation.
        """
        _ = configuration
        return cast("FsspecFilesystem", object())

    invalid = FilesystemManager(
        FilesystemConfiguration(
            default_disk="invalid",
            disks={
                "invalid": FilesystemDiskConfiguration(driver="invalid"),
            },
        ),
        drivers={"invalid": make_invalid_filesystem},
    )
    with pytest.raises(
        FilesystemConfigurationError,
        match="fsspec filesystem instance",
    ):
        invalid.disk()


def test_paths_cannot_escape_the_configured_local_root(
    tmp_path: Path,
) -> None:
    """Reject absolute paths, traversal, and symlinks escaping the root.

    Valid-looking relative paths must not follow a child symlink outside.
    """
    root = tmp_path / "root"
    outside = tmp_path / "outside.txt"
    root.mkdir()
    outside.write_text("private", encoding="utf-8")
    disk = _local_disk(root).disk()
    (root / "linked.txt").symlink_to(outside)

    with pytest.raises(UnsafeStoragePathError):
        disk.get("../outside.txt")
    with pytest.raises(UnsafeStoragePathError):
        disk.get(str(outside))
    with pytest.raises(UnsafeStoragePathError):
        disk.get("linked.txt")
    assert outside.read_text(encoding="utf-8") == "private"


def test_disk_rejects_unsafe_names_and_respects_overwrite_policy(
    tmp_path: Path,
) -> None:
    """Reject unsafe keys and honor explicit destination overwrite choices.

    Invalid path inputs remain errors even if operation errors are suppressed.
    """
    disk = _local_disk(tmp_path).disk()
    assert disk.put("report.txt", b"one")

    with pytest.raises(FileExistsError):
        disk.put("report.txt", b"two", overwrite=False)
    with pytest.raises(UnsafeStoragePathError):
        disk.put("../report.txt", b"outside", raise_errors=False)
    with pytest.raises(UnsafeStoragePathError):
        disk.put("bad\\name.txt", b"invalid")
    assert disk.get_bytes("report.txt") == b"one"


def test_disabled_operation_errors_return_false(
    tmp_path: Path,
) -> None:
    """Use disk configuration to suppress storage operation errors.

    Reads keep native missing-file errors because they cannot return data.
    """
    manager = FilesystemManager(
        FilesystemConfiguration(
            default_disk="local",
            disks={
                "local": FilesystemDiskConfiguration(
                    driver="local",
                    root=tmp_path,
                    raise_errors=False,
                ),
            },
        ),
    )
    disk = manager.disk()

    assert not disk.delete("missing.txt")
    assert not disk.copy("missing.txt", "copy.txt")
    with pytest.raises(FileNotFoundError):
        disk.get("missing.txt")


def test_streams_and_temporary_keys_close_and_clean_up(
    tmp_path: Path,
) -> None:
    """Stream data in bounded chunks and remove temporary keys on exit.

    Temporary resources remain scoped to their context even after failure.
    """
    disk = _local_disk(tmp_path).disk()
    chunks: Iterable[bytes] = (b"first", b"second")

    assert disk.write_stream("large.bin", chunks)
    assert tuple(disk.read_stream("large.bin", chunk_size=3)) == (
        b"fir",
        b"sts",
        b"eco",
        b"nd",
    )

    temporary_path = ""
    with disk.temporary_file(directory="scratch", suffix=".txt") as path:
        temporary_path = path
        assert disk.exists(path)
        assert disk.put(path, "temporary")
        assert disk.get(path) == "temporary"
    assert temporary_path
    assert not disk.exists(temporary_path)


def test_temporary_file_collision_preserves_existing_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid deleting a pre-existing path when temporary creation fails.

    Cleanup owns a key only after the selected backend creates it.
    """
    disk = _local_disk(tmp_path).disk()
    collision_path = ".titanspan-collision.tmp"
    assert disk.put(collision_path, "preserve")
    monkeypatch.setattr(
        "titanspan.filesystem.disk.secrets.token_hex",
        _collision_token,
    )

    with pytest.raises(FileExistsError), disk.temporary_file():
        pytest.fail("A colliding temporary path was accepted.")

    assert disk.get(collision_path) == "preserve"


@pytest.mark.anyio
async def test_async_disk_operations_offload_filesystem_work(
    tmp_path: Path,
) -> None:
    """Expose explicit async forms for sync fsspec local operations.

    Async methods preserve the same native values and bounded chunk interface.
    """
    disk = _local_disk(tmp_path).disk()

    assert await disk.put_async("async/report.txt", "body")
    assert await disk.get_async("async/report.txt") == "body"
    assert await disk.get_bytes_async("async/report.txt") == b"body"
    assert await disk.exists_async("async/report.txt")
    assert await disk.is_directory_async("async")
    assert await disk.size_async("async/report.txt") == _BODY_SIZE
    assert await disk.last_modified_async("async/report.txt") is not None
    assert await disk.list_files_async("async") == ("async/report.txt",)
    assert await disk.make_directory_async("async/empty")
    assert await disk.list_directories_async("async") == ("async/empty",)
    assert tuple(
        entry.path
        for entry in await disk.list_contents_async(
            "async",
            recursive=True,
        )
    ) == ("async/empty", "async/report.txt")
    assert (await disk.metadata_async("async/report.txt")).path == (
        "async/report.txt"
    )
    assert await disk.delete_directory_async("async/empty")
    assert await disk.copy_async(
        "async/report.txt",
        "async/copy.txt",
    )
    assert await disk.append_async("async/copy.txt", "!")
    assert await disk.prepend_async("async/copy.txt", "new ")
    assert await disk.get_async("async/copy.txt") == "new body!"
    assert await disk.move_async("async/copy.txt", "async/moved.txt")
    assert await disk.delete_async("async/moved.txt")

    assert await disk.write_stream_async(
        "async/stream.bin",
        _async_chunks((b"a", b"b")),
    )
    assert tuple(
        [chunk async for chunk in disk.read_stream_async("async/stream.bin")]
    ) == (b"ab",)
    async with disk.temporary_file_async(directory="async") as path:
        assert await disk.exists_async(path)
        assert await disk.put_async(path, b"temporary")
    assert not await disk.exists_async(path)

    async def invalid_chunks() -> AsyncIterator[bytes]:
        """Yield one non-byte chunk for runtime validation.

        Yields:
            One invalid value hidden behind the declared stream contract.
        """
        yield cast("bytes", "not bytes")

    with pytest.raises(TypeError, match="chunks must be bytes"):
        await disk.write_stream_async(
            "async/invalid.bin",
            invalid_chunks(),
        )


@pytest.mark.anyio
async def test_async_temporary_file_collision_preserves_existing_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid deleting an existing path after async temporary creation fails.

    Async cleanup removes only the file created by its own context.
    """
    disk = _local_disk(tmp_path).disk()
    collision_path = ".titanspan-collision.tmp"
    assert await disk.put_async(collision_path, "preserve")
    monkeypatch.setattr(
        "titanspan.filesystem.disk.secrets.token_hex",
        _collision_token,
    )

    with pytest.raises(FileExistsError):
        async with disk.temporary_file_async():
            pytest.fail("A colliding temporary path was accepted.")

    assert await disk.get_async(collision_path) == "preserve"


@pytest.mark.anyio
async def test_async_streams_close_backend_handles_on_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close real fsspec streams after async read and write cancellation.

    AnyIO cancellation reaches iterator cleanup while shielded finalizers close
    the backend-owned file handles.
    """
    manager, filesystem = _local_manager_with_filesystem(tmp_path)
    disk = manager.disk()
    assert disk.put("source.bin", b"source bytes")
    closed: list[bool] = []
    original_open = filesystem.open

    def tracking_open(path: str, mode: str = "rb") -> FilesystemStream:
        """Wrap one fsspec stream and observe its close call.

        Args:
            path: Backend path opened by the disk adapter.
            mode: Binary mode selected by the adapter.

        Returns:
            A wrapper around the real backend stream.
        """
        return _TrackedStream(original_open(path, mode), closed)

    monkeypatch.setattr(filesystem, "open", tracking_open)
    read_started = anyio.Event()

    async def read_until_cancelled() -> None:
        """Hold an async read stream open until the parent cancels it.

        Cancellation should run the stream's shielded close finalizer.
        """
        async with aclosing(disk.read_stream_async("source.bin")) as chunks:
            assert await anext(chunks) == b"source bytes"
            read_started.set()
            await anyio.sleep_forever()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(read_until_cancelled)
        await read_started.wait()
        tasks.cancel_scope.cancel()
    assert closed == [True]

    write_started = anyio.Event()

    async def write_until_cancelled() -> AsyncIterator[bytes]:
        """Yield one chunk and keep the source open for cancellation.

        The parent cancels after the adapter requests the next chunk.
        """
        yield b"partial"
        write_started.set()
        await anyio.sleep_forever()

    async def write_stream() -> None:
        """Write one chunk before its async source is cancelled.

        The disk must still close the fsspec destination handle.
        """
        await disk.write_stream_async("partial.bin", write_until_cancelled())

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(write_stream)
        await write_started.wait()
        tasks.cancel_scope.cancel()
    assert closed == [True, True]


@pytest.mark.anyio
async def test_async_stream_write_error_policy_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply configured errors and close streams after write failures.

    Both backend open and write errors preserve the selected policy.
    """
    manager, filesystem = _local_manager_with_filesystem(tmp_path)
    disk = manager.disk()
    original_open = filesystem.open

    def fail_open(path: str, mode: str = "rb") -> FilesystemStream:
        """Raise when the disk tries to create an async write stream.

        Args:
            path: Backend path selected by the storage adapter.
            mode: Binary mode selected by the adapter.

        Returns:
            No stream is returned when the backend raises.
        """
        _ = path, mode
        raise OSError(_OPEN_FAILED_ERROR)

    monkeypatch.setattr(filesystem, "open", fail_open)
    assert not await disk.write_stream_async(
        "open-failed.bin",
        _async_chunks((b"chunk",)),
        raise_errors=False,
    )
    with pytest.raises(OSError, match=_OPEN_FAILED_ERROR):
        await disk.write_stream_async(
            "open-failed-again.bin",
            _async_chunks((b"chunk",)),
        )

    def fail_write_open(path: str, mode: str = "rb") -> FilesystemStream:
        """Wrap a real destination stream with an erroring writer.

        Args:
            path: Backend path selected by the storage adapter.
            mode: Binary mode selected by the adapter.

        Returns:
            A stream that raises on writes and closes its backend handle.
        """
        return _FailingWriteStream(original_open(path, mode))

    monkeypatch.setattr(filesystem, "open", fail_write_open)
    assert not await disk.write_stream_async(
        "write-failed.bin",
        _async_chunks((b"chunk",)),
        raise_errors=False,
    )
    with pytest.raises(OSError, match=_WRITE_FAILED_ERROR):
        await disk.write_stream_async(
            "write-failed-again.bin",
            _async_chunks((b"chunk",)),
        )


async def _async_chunks(
    values: tuple[bytes, ...],
) -> AsyncIterator[bytes]:
    """Yield fixed chunks for one async write-stream assertion.

    Args:
        values: Ordered byte chunks written to the stream.

    Yields:
        Each input chunk in order.
    """
    for value in values:
        yield value


def test_filesystem_fake_assertions_cover_presence_and_content(
    tmp_path: Path,
) -> None:
    """Assert fake files and directories with optional exact content.

    Failed assertions report safe messages without exposing stored bytes.
    """
    disk = _local_disk(tmp_path).disk()
    assert disk.put("stored.txt", "actual")
    assert disk.make_directory("folder")
    fake = FilesystemFake(disk)

    fake.assert_exists("stored.txt")
    fake.assert_exists("folder")
    fake.assert_missing("missing.txt")
    fake.assert_stored("stored.txt")
    fake.assert_stored("stored.txt", "actual")
    fake.assert_not_stored("missing.txt")

    with pytest.raises(AssertionError):
        fake.assert_exists("missing.txt")
    with pytest.raises(AssertionError):
        fake.assert_missing("stored.txt")
    with pytest.raises(AssertionError):
        fake.assert_stored("missing.txt")
    with pytest.raises(AssertionError):
        fake.assert_stored("folder")
    with pytest.raises(AssertionError):
        fake.assert_stored("stored.txt", "wrong")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime.fromisoformat("2025-01-02T03:04:05"),
            datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        ),
        (
            datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
            datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        ),
        (0, datetime(1970, 1, 1, tzinfo=UTC)),
        (float("nan"), None),
        (1e300, None),
        ("2025-01-02T03:04:05", datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)),
        (
            "2025-01-02T03:04:05+02:00",
            datetime(2025, 1, 2, 1, 4, 5, tzinfo=UTC),
        ),
        ("invalid", None),
        (None, None),
    ],
)
def test_modified_time_values_normalize_to_utc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
    expected: datetime | None,
) -> None:
    """Normalize supported backend timestamps and reject malformed values.

    Local and remote metadata expose one consistent aware UTC type.
    """
    manager, filesystem = _local_manager_with_filesystem(tmp_path)
    disk = manager.disk()

    def report_modified_time(path: str) -> dict[str, object]:
        """Return synthetic public metadata for a controlled timestamp.

        Args:
            path: Backend path requested by the metadata operation.

        Returns:
            A metadata record using the supplied timestamp value.
        """
        return {
            "name": path,
            "type": "file",
            "size": 0,
            "mtime": value,
        }

    monkeypatch.setattr(filesystem, "info", report_modified_time)
    assert disk.metadata("timestamp.txt").modified == expected
