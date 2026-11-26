"""Define the shared storage disk and manager interfaces.

The contract remains independent of fsspec and concrete storage backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import (
        AsyncIterable,
        AsyncIterator,
        Iterable,
        Iterator,
    )
    from contextlib import AbstractAsyncContextManager, AbstractContextManager
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Describe a path using backend-independent metadata values.

    Attributes:
        path: Disk-relative path using POSIX separators.
        size: File size in bytes, or ``None`` for directories and unknown
            backend sizes.
        modified: Modification timestamp normalized to an aware UTC datetime.
        is_file: Whether the backend identifies the path as a file.
        is_directory: Whether the backend identifies the path as a directory.
    """

    path: str
    size: int | None
    modified: datetime | None
    is_file: bool
    is_directory: bool


@runtime_checkable
class StorageDisk(Protocol):
    """Describe synchronous and explicit asynchronous disk operations.

    Implementations document backend-specific consistency and atomicity.
    All paths are relative to the configured disk root.
    """

    def put(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Write text or bytes and report whether the operation succeeded.

        Args:
            path: Disk-relative destination.
            content: Text or byte content to store.
            encoding: Encoding used when ``content`` is text.
            overwrite: Whether an existing file may be replaced.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the write completed when errors are configured to return.
        """
        ...

    def get(self, path: str, *, encoding: str = "utf-8") -> str:
        """Read text from one file.

        Args:
            path: Disk-relative source path.
            encoding: Text decoding used for the returned value.

        Returns:
            Decoded file content.

        Raises:
            FileNotFoundError: If the path is absent.
            IsADirectoryError: If the path names a directory.
        """
        ...

    def get_bytes(self, path: str) -> bytes:
        """Read the exact bytes stored at one file path.

        Args:
            path: Disk-relative source path.

        Returns:
            File content without text decoding.
        """
        ...

    def exists(self, path: str) -> bool:
        """Check whether a file or directory exists on this disk.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the backend contains the path.
        """
        ...

    def is_directory(self, path: str) -> bool:
        """Check whether a path names a directory.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the backend identifies the path as a directory.
        """
        ...

    def delete(
        self,
        path: str,
        *,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete one file without recursively removing directories.

        Args:
            path: Disk-relative file path.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether an existing file was removed.
        """
        ...

    def delete_directory(
        self,
        path: str,
        *,
        recursive: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete a directory through the backend's native operation.

        Args:
            path: Disk-relative directory path.
            recursive: Whether descendants may also be removed.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether an existing directory was removed.
        """
        ...

    def make_directory(
        self,
        path: str,
        *,
        create_parents: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Create a directory using the selected backend.

        Args:
            path: Disk-relative directory path.
            create_parents: Whether to create missing parent directories.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the directory exists after the operation.
        """
        ...

    def copy(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Copy one file through the backend's copy implementation.

        Args:
            source: Disk-relative source file.
            destination: Disk-relative destination file.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the copy completed.
        """
        ...

    def move(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Move one file through the backend's native move operation.

        Args:
            source: Disk-relative source file.
            destination: Disk-relative destination file.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the move completed.
        """
        ...

    def list_files(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List file paths relative to this disk.

        Args:
            path: Directory path, or the empty string for the disk root.
            recursive: Whether to include descendant directories.

        Returns:
            Sorted disk-relative file paths.
        """
        ...

    def list_directories(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List directory paths relative to this disk.

        Args:
            path: Directory path, or the empty string for the disk root.
            recursive: Whether to include descendant directories.

        Returns:
            Sorted disk-relative directory paths.
        """
        ...

    def list_contents(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[FileMetadata, ...]:
        """List files and directories with normalized metadata.

        Args:
            path: Directory path, or the empty string for the disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted metadata entries with disk-relative paths.
        """
        ...

    def metadata(self, path: str) -> FileMetadata:
        """Return normalized metadata for one existing path.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            Backend-independent metadata.
        """
        ...

    def size(self, path: str) -> int | None:
        """Return a file's byte size when the backend reports it.

        Args:
            path: Disk-relative file path.

        Returns:
            File size in bytes, or ``None`` when the backend omits it.
        """
        ...

    def last_modified(self, path: str) -> datetime | None:
        """Return the normalized modification time when available.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            An aware UTC timestamp or ``None`` when unsupported.
        """
        ...

    def read_stream(
        self,
        path: str,
        *,
        chunk_size: int = 65_536,
    ) -> Iterator[bytes]:
        """Yield file bytes in bounded chunks and close the stream on exit.

        Args:
            path: Disk-relative file path.
            chunk_size: Maximum bytes requested from the backend per read.

        Yields:
            Non-empty chunks in file order.
        """
        ...

    def write_stream(
        self,
        path: str,
        chunks: Iterable[bytes],
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Write an iterable of byte chunks without buffering them all.

        Args:
            path: Disk-relative destination.
            chunks: Ordered byte chunks consumed once.
            overwrite: Whether an existing file may be replaced.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the write completed.
        """
        ...

    def append(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Append text or bytes to a file, creating it when absent.

        Args:
            path: Disk-relative file path.
            content: Text or bytes to append.
            encoding: Encoding used when ``content`` is text.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the append completed.
        """
        ...

    def prepend(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Prepend text or bytes to a file, creating it when absent.

        Args:
            path: Disk-relative file path.
            content: Text or bytes to prepend.
            encoding: Encoding used when ``content`` is text.
            raise_errors: Override this disk's configured write error policy.

        Returns:
            Whether the prepend completed.
        """
        ...

    def temporary_file(
        self,
        *,
        directory: str = "",
        suffix: str = ".tmp",
    ) -> AbstractContextManager[str]:
        """Yield a unique disk-relative key and remove it when the context ends.

        Args:
            directory: Optional disk-relative directory for the key.
            suffix: Filename suffix retained for backend interoperability.

        Returns:
            A context manager yielding the temporary disk-relative path.
        """
        ...

    async def put_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Run the write operation without blocking the event loop.

        Args:
            path: Disk-relative destination.
            content: Text or byte content.
            encoding: Encoding used when ``content`` is text.
            overwrite: Whether an existing file may be replaced.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the write completed.
        """
        ...

    async def get_async(
        self,
        path: str,
        *,
        encoding: str = "utf-8",
    ) -> str:
        """Read and decode text without blocking the event loop.

        Args:
            path: Disk-relative file path.
            encoding: Text decoding used for the returned value.

        Returns:
            Decoded file content.
        """
        ...

    async def get_bytes_async(self, path: str) -> bytes:
        """Read bytes without blocking the event loop.

        Args:
            path: Disk-relative file path.

        Returns:
            Exact file bytes.
        """
        ...

    async def exists_async(self, path: str) -> bool:
        """Check path existence without blocking the event loop.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the path exists.
        """
        ...

    async def is_directory_async(self, path: str) -> bool:
        """Check for a directory without blocking the event loop.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the path is a directory.
        """
        ...

    async def delete_async(
        self,
        path: str,
        *,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete one file without blocking the event loop.

        Args:
            path: Disk-relative file path.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether a file was removed.
        """
        ...

    async def delete_directory_async(
        self,
        path: str,
        *,
        recursive: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete a directory without blocking the event loop.

        Args:
            path: Disk-relative directory path.
            recursive: Whether descendants may also be removed.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether a directory was removed.
        """
        ...

    async def make_directory_async(
        self,
        path: str,
        *,
        create_parents: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Create a directory without blocking the event loop.

        Args:
            path: Disk-relative directory path.
            create_parents: Whether to create missing ancestors.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the directory exists after the operation.
        """
        ...

    async def copy_async(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Copy a file without blocking the event loop.

        Args:
            source: Disk-relative source path.
            destination: Disk-relative destination path.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the copy completed.
        """
        ...

    async def move_async(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Move a file without blocking the event loop.

        Args:
            source: Disk-relative source path.
            destination: Disk-relative destination path.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the move completed.
        """
        ...

    async def list_files_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List files without blocking the event loop.

        Args:
            path: Directory path or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted disk-relative file paths.
        """
        ...

    async def list_directories_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List directories without blocking the event loop.

        Args:
            path: Directory path or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted disk-relative directory paths.
        """
        ...

    async def list_contents_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[FileMetadata, ...]:
        """List normalized entries without blocking the event loop.

        Args:
            path: Directory path or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted metadata entries.
        """
        ...

    async def metadata_async(self, path: str) -> FileMetadata:
        """Read normalized metadata without blocking the event loop.

        Args:
            path: Disk-relative path.

        Returns:
            Metadata for the existing path.
        """
        ...

    async def size_async(self, path: str) -> int | None:
        """Read file size without blocking the event loop.

        Args:
            path: Disk-relative file path.

        Returns:
            File size in bytes or ``None``.
        """
        ...

    async def last_modified_async(self, path: str) -> datetime | None:
        """Read the modification timestamp without blocking the event loop.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            An aware UTC timestamp or ``None``.
        """
        ...

    def read_stream_async(
        self,
        path: str,
        *,
        chunk_size: int = 65_536,
    ) -> AsyncIterator[bytes]:
        """Yield bounded chunks without blocking the event loop.

        Args:
            path: Disk-relative file path.
            chunk_size: Maximum bytes requested per worker read.

        Yields:
            Non-empty chunks in file order.
        """
        ...

    async def write_stream_async(
        self,
        path: str,
        chunks: AsyncIterable[bytes],
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Write async byte chunks without buffering the complete stream.

        Args:
            path: Disk-relative destination.
            chunks: Ordered asynchronous byte chunks consumed once.
            overwrite: Whether an existing file may be replaced.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the write completed.
        """
        ...

    async def append_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Append content without blocking the event loop.

        Args:
            path: Disk-relative file path.
            content: Text or byte content.
            encoding: Encoding used for text content.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the append completed.
        """
        ...

    async def prepend_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Prepend content without blocking the event loop.

        Args:
            path: Disk-relative file path.
            content: Text or byte content.
            encoding: Encoding used for text content.
            raise_errors: Override this disk's configured write policy.

        Returns:
            Whether the prepend completed.
        """
        ...

    def temporary_file_async(
        self,
        *,
        directory: str = "",
        suffix: str = ".tmp",
    ) -> AbstractAsyncContextManager[str]:
        """Yield an async-managed temporary path and remove it on exit.

        Args:
            directory: Optional disk-relative directory.
            suffix: Filename suffix retained for interoperability.

        Returns:
            An asynchronous context manager yielding the temporary path.
        """
        ...


@runtime_checkable
class StorageManager(Protocol):
    """Describe the application-owned named disk manager.

    The manager owns one configured disk registry for the active application.
    """

    @property
    def default_disk(self) -> str:
        """Return the configured default disk name.

        Returns:
            Name selected by application configuration.
        """
        ...

    def disk(self, name: str | None = None) -> StorageDisk:
        """Resolve a configured named disk.

        Args:
            name: Optional disk name; the default is used when omitted.

        Returns:
            The application-owned disk instance.
        """
        ...


__all__ = ["FileMetadata", "StorageDisk", "StorageManager"]
