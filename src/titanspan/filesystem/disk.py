"""Provide rooted file operations over supported fsspec filesystems.

fsspec owns backend mechanics. This adapter owns disk-relative paths, safe
local-root checks, native values, and explicit async worker execution.
"""

from __future__ import annotations

import math
import posixpath
import secrets
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

import anyio
from fsspec.implementations.local import (  # pyright: ignore
    LocalFileSystem,
)

from titanspan.contracts.filesystem import FileMetadata
from titanspan.filesystem.exceptions import UnsafeStoragePathError

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterable,
        Callable,
        Generator,
        Iterable,
        Iterator,
    )

    from titanspan.filesystem._types import (
        FilesystemStream,
        FsspecFilesystem,
    )

_DEFAULT_CHUNK_SIZE = 65_536
_INVALID_PATH_ERROR = "Storage paths must be safe disk-relative names."
_INVALID_CHUNK_SIZE_ERROR = "Stream chunk size must be a positive integer."
_INVALID_SUFFIX_ERROR = "Temporary file suffixes must be safe filenames."
_SAME_PATH_ERROR = "Source and destination paths must differ."
_STREAM_CHUNK_TYPE_ERROR = "Storage stream chunks must be bytes."
_CONTROL_CHARACTER_LIMIT = 32
_INVALID_FILENAME_CHARACTERS = frozenset('<>"|?*')
_RESERVED_WINDOWS_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    },
)


async def _run_async[ResultT](operation: Callable[[], ResultT]) -> ResultT:
    """Run one synchronous filesystem call in AnyIO's bounded worker pool.

    Args:
        operation: Backend call that may block on filesystem I/O.

    Returns:
        The result produced by the worker operation.
    """
    return await anyio.to_thread.run_sync(operation)


class FilesystemDisk:
    """Adapt one fsspec filesystem to a disk-relative Python API.

    The local adapter resolves a trusted root and rejects symlinks in each
    existing path component before delegating to LocalFileSystem. Async
    methods offload synchronous fsspec operations to AnyIO's bounded workers.
    """

    def __init__(
        self,
        filesystem: FsspecFilesystem,
        *,
        root: str | Path | None = None,
        raise_errors: bool = True,
    ) -> None:
        """Retain one fsspec instance and its configured path boundary.

        Args:
            filesystem: Backend instance created by the disk manager.
            root: Trusted local root or backend path prefix.
            raise_errors: Default policy for failed mutating operations.
        """
        self._filesystem = filesystem
        self._raise_errors = raise_errors
        self._local_root: Path | None = None
        self._prefix = ""
        if isinstance(filesystem, LocalFileSystem):
            local_root = Path("storage/app") if root is None else Path(root)
            self._local_root = local_root.expanduser().resolve(strict=False)
        else:
            self._prefix = _normalize_prefix(root)

    def put(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Write content and return the outcome selected by error policy.

        Args:
            path: Disk-relative destination path.
            content: Text or bytes to store.
            encoding: Encoding used when content is text.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Optional per-operation write error policy.

        Returns:
            ``True`` after writing, or ``False`` for a suppressed I/O failure.

        Raises:
            FileExistsError: If overwrite is disabled and the file exists.
            UnsafeStoragePathError: If the path escapes the configured root.
        """
        backend_path = self._backend_path(path)
        data = content.encode(encoding) if isinstance(content, str) else content

        def write() -> None:
            """Write all bytes through a managed fsspec stream.

            Returns:
                None.
            """
            self._check_overwrite(backend_path, overwrite)
            self._prepare_parent(backend_path)
            stream = self._open_write(backend_path, "wb")
            try:
                stream.write(data)
            finally:
                stream.close()

        return self._mutate(write, raise_errors)

    def get(self, path: str, *, encoding: str = "utf-8") -> str:
        """Read and decode a file, preserving native missing-file errors.

        Args:
            path: Disk-relative source path.
            encoding: Encoding used for returned text.

        Returns:
            Decoded file content.

        Raises:
            FileNotFoundError: If the file does not exist.
            IsADirectoryError: If the path names a directory.
            UnsafeStoragePathError: If a local symlink is encountered.
        """
        return self.get_bytes(path).decode(encoding)

    def get_bytes(self, path: str) -> bytes:
        """Read exact file bytes through a managed fsspec stream.

        Args:
            path: Disk-relative source path.

        Returns:
            File content without decoding.
        """
        backend_path = self._backend_path(path)
        stream = self._open_read(backend_path)
        try:
            return stream.read()
        finally:
            stream.close()

    def exists(self, path: str) -> bool:
        """Check path existence without exposing backend path prefixes.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            Whether the path exists on the selected backend.
        """
        backend_path = self._backend_path(path, allow_root=True)
        return self._filesystem.exists(backend_path)

    def is_directory(self, path: str) -> bool:
        """Check whether an existing path is a backend directory.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the backend identifies the path as a directory.
        """
        backend_path = self._backend_path(path, allow_root=True)
        return self._filesystem.isdir(backend_path)

    def delete(
        self,
        path: str,
        *,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete one file without recursively deleting a directory.

        Args:
            path: Disk-relative file path.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether a file was removed.
        """
        backend_path = self._backend_path(path)

        def remove() -> bool:
            """Remove one existing file through the backend.

            Returns:
                Whether a file was removed.
            """
            if not self._filesystem.exists(backend_path):
                return False
            if self._filesystem.isdir(backend_path):
                raise IsADirectoryError(path)
            self._filesystem.rm(backend_path)
            return True

        return self._mutate(remove, raise_errors)

    def delete_directory(
        self,
        path: str,
        *,
        recursive: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Remove a directory through fsspec's backend implementation.

        Args:
            path: Disk-relative directory path.
            recursive: Whether to remove descendants.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether an existing directory was removed.
        """
        backend_path = self._backend_path(path)

        def remove() -> bool:
            """Remove the directory if it still exists.

            Returns:
                Whether a directory was removed.
            """
            if not self._filesystem.exists(backend_path):
                return False
            if not self._filesystem.isdir(backend_path):
                raise NotADirectoryError(path)
            if recursive:
                self._filesystem.rm(backend_path, recursive=True)
            else:
                self._filesystem.rmdir(backend_path)
            return True

        return self._mutate(remove, raise_errors)

    def make_directory(
        self,
        path: str,
        *,
        create_parents: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Create a directory and optionally its missing ancestors.

        Args:
            path: Disk-relative directory path.
            create_parents: Whether to create missing parent directories.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the directory exists after creation.
        """
        backend_path = self._backend_path(path)

        def create() -> None:
            """Delegate directory creation to fsspec.

            Returns:
                None.
            """
            if create_parents:
                self._filesystem.makedirs(backend_path, exist_ok=True)
            else:
                self._filesystem.mkdir(
                    backend_path,
                    create_parents=False,
                )

        return self._mutate(create, raise_errors)

    def copy(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Copy one file using fsspec's selected backend semantics.

        Args:
            source: Disk-relative source file.
            destination: Disk-relative destination file.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the copy completed.
        """
        source_path = self._backend_path(source)
        destination_path = self._backend_path(destination)
        if source_path == destination_path:
            raise ValueError(_SAME_PATH_ERROR)

        def copy_file() -> None:
            """Validate the destination and delegate the copy operation.

            Returns:
                None.
            """
            if not self._filesystem.exists(source_path):
                raise FileNotFoundError(source)
            if self._filesystem.isdir(source_path):
                raise IsADirectoryError(source)
            self._check_overwrite(destination_path, overwrite)
            self._prepare_parent(destination_path)
            self._filesystem.copy(source_path, destination_path)

        return self._mutate(copy_file, raise_errors)

    def move(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Move one file using fsspec's selected backend semantics.

        Args:
            source: Disk-relative source file.
            destination: Disk-relative destination file.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the move completed.
        """
        source_path = self._backend_path(source)
        destination_path = self._backend_path(destination)
        if source_path == destination_path:
            raise ValueError(_SAME_PATH_ERROR)

        def move_file() -> None:
            """Validate the destination and delegate the move operation.

            Returns:
                None.
            """
            if not self._filesystem.exists(source_path):
                raise FileNotFoundError(source)
            if self._filesystem.isdir(source_path):
                raise IsADirectoryError(source)
            self._check_overwrite(destination_path, overwrite)
            self._prepare_parent(destination_path)
            self._filesystem.mv(source_path, destination_path)

        return self._mutate(move_file, raise_errors)

    def list_files(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """Return sorted disk-relative file paths beneath a directory.

        Args:
            path: Directory path, or empty string for the disk root.
            recursive: Whether to include nested directories.

        Returns:
            Sorted disk-relative file paths.
        """
        return tuple(
            entry.path
            for entry in self.list_contents(path, recursive=recursive)
            if entry.is_file
        )

    def list_directories(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """Return sorted disk-relative directory paths beneath a directory.

        Args:
            path: Directory path, or empty string for the disk root.
            recursive: Whether to include nested directories.

        Returns:
            Sorted disk-relative directory paths.
        """
        return tuple(
            entry.path
            for entry in self.list_contents(path, recursive=recursive)
            if entry.is_directory
        )

    def list_contents(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[FileMetadata, ...]:
        """Return sorted metadata for a directory's immediate or nested items.

        Args:
            path: Directory path, or empty string for the disk root.
            recursive: Whether to include nested directories.

        Returns:
            Sorted disk-relative metadata entries.

        Raises:
            FileNotFoundError: If a selected non-root directory is absent.
            NotADirectoryError: If the selected path is a file.
        """
        backend_path = self._backend_path(path, allow_root=True)
        if not self._filesystem.exists(backend_path):
            if path == "":
                return ()
            raise FileNotFoundError(path)
        if not self._filesystem.isdir(backend_path):
            raise NotADirectoryError(path)
        selected_path = self._relative_path(backend_path)
        records = self._list_records(backend_path, recursive=recursive)
        records = [
            (name, info)
            for name, info in records
            if self._relative_path(name) not in {"", selected_path}
        ]
        entries = [
            self._metadata_from_record(name, info) for name, info in records
        ]
        entries.sort(key=lambda entry: entry.path)
        return tuple(entries)

    def metadata(self, path: str) -> FileMetadata:
        """Return backend-independent metadata for one existing path.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            Normalized metadata with an aware timestamp when available.
        """
        backend_path = self._backend_path(path)
        info = self._filesystem.info(backend_path)
        return self._metadata_from_record(backend_path, info)

    def size(self, path: str) -> int | None:
        """Return the size reported for a file or directory.

        Args:
            path: Disk-relative path.

        Returns:
            File size in bytes, or ``None`` when the backend omits it.
        """
        return self.metadata(path).size

    def last_modified(self, path: str) -> datetime | None:
        """Return an aware UTC modification time when supplied by fsspec.

        Args:
            path: Disk-relative path.

        Returns:
            Normalized UTC timestamp or ``None``.
        """
        return self.metadata(path).modified

    def read_stream(
        self,
        path: str,
        *,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        """Yield bounded byte chunks and close the backend stream on exit.

        Args:
            path: Disk-relative source path.
            chunk_size: Maximum bytes requested for one read.

        Yields:
            Non-empty file chunks in order.

        Raises:
            ValueError: If ``chunk_size`` is not positive.
        """
        _validate_chunk_size(chunk_size)
        stream = self._open_read(self._backend_path(path))
        try:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            stream.close()

    def write_stream(
        self,
        path: str,
        chunks: Iterable[bytes],
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Write byte chunks incrementally without whole-stream buffering.

        Args:
            path: Disk-relative destination path.
            chunks: Ordered source chunks consumed once.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the write completed.

        Raises:
            TypeError: If any source item is not ``bytes``.
        """
        backend_path = self._backend_path(path)

        def write_chunks() -> None:
            """Write each chunk directly to one managed backend stream.

            Returns:
                None.
            """
            self._check_overwrite(backend_path, overwrite)
            self._prepare_parent(backend_path)
            stream = self._open_write(backend_path, "wb")
            try:
                for chunk in chunks:
                    if not isinstance(cast("object", chunk), bytes):
                        raise TypeError(_STREAM_CHUNK_TYPE_ERROR)
                    stream.write(chunk)
            finally:
                stream.close()

        return self._mutate(write_chunks, raise_errors)

    def append(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Append text or bytes with backend-native append mode.

        Args:
            path: Disk-relative file path.
            content: Text or bytes appended to the file.
            encoding: Encoding used when ``content`` is text.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the append completed.
        """
        backend_path = self._backend_path(path)
        data = content.encode(encoding) if isinstance(content, str) else content

        def append_content() -> None:
            """Append bytes through a backend-managed stream.

            Returns:
                None.
            """
            if self._filesystem.isdir(backend_path):
                raise IsADirectoryError(path)
            self._prepare_parent(backend_path)
            stream = self._open_write(backend_path, "ab")
            try:
                stream.write(data)
            finally:
                stream.close()

        return self._mutate(append_content, raise_errors)

    def prepend(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Prepend content by reading and rewriting one file.

        Prepending is not atomic for all backends because fsspec does not
        provide a universal atomic replace operation.

        Args:
            path: Disk-relative file path.
            content: Text or bytes placed before the current contents.
            encoding: Encoding used when ``content`` is text.
            raise_errors: Optional per-operation write error policy.

        Returns:
            Whether the prepend completed.
        """
        backend_path = self._backend_path(path)
        prefix = (
            content.encode(encoding) if isinstance(content, str) else content
        )

        def prepend_content() -> None:
            """Rewrite the old bytes after the new prefix.

            Returns:
                None.
            """
            if self._filesystem.isdir(backend_path):
                raise IsADirectoryError(path)
            previous = b""
            if self._filesystem.exists(backend_path):
                reader = self._open_read(backend_path)
                try:
                    previous = reader.read()
                finally:
                    reader.close()
            self._prepare_parent(backend_path)
            writer = self._open_write(backend_path, "wb")
            try:
                writer.write(prefix)
                writer.write(previous)
            finally:
                writer.close()

        return self._mutate(prepend_content, raise_errors)

    @contextmanager
    def temporary_file(
        self,
        *,
        directory: str = "",
        suffix: str = ".tmp",
    ) -> Generator[str, None, None]:
        """Yield a unique storage key and remove it when the context exits.

        Args:
            directory: Optional disk-relative directory.
            suffix: Safe suffix included in the generated filename.

        Yields:
            A disk-relative temporary path that callers may read or write.

        Raises:
            UnsafeStoragePathError: If the directory or suffix is unsafe.
        """
        path = self._temporary_path(directory, suffix)
        created = False
        try:
            created = self.put(path, b"", overwrite=False, raise_errors=True)
            yield path
        finally:
            if created:
                self.delete(path, raise_errors=True)

    async def put_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Offload a complete write to AnyIO's bounded worker pool.

        Args:
            path: Disk-relative destination path.
            content: Text or bytes to store.
            encoding: Text encoding when content is a string.
            overwrite: Whether an existing file may be replaced.
            raise_errors: Optional write error policy.

        Returns:
            Whether the write completed.
        """
        return await _run_async(
            partial(
                self.put,
                path,
                content,
                encoding=encoding,
                overwrite=overwrite,
                raise_errors=raise_errors,
            ),
        )

    async def get_async(self, path: str, *, encoding: str = "utf-8") -> str:
        """Read text without blocking the event loop.

        Args:
            path: Disk-relative source path.
            encoding: Decoder used for returned text.

        Returns:
            Decoded file content.
        """
        return await _run_async(partial(self.get, path, encoding=encoding))

    async def get_bytes_async(self, path: str) -> bytes:
        """Read bytes without blocking the event loop.

        Args:
            path: Disk-relative source path.

        Returns:
            Exact file content bytes.
        """
        return await _run_async(partial(self.get_bytes, path))

    async def exists_async(self, path: str) -> bool:
        """Check existence without blocking the event loop.

        Args:
            path: Disk-relative file or directory path.

        Returns:
            Whether the path exists.
        """
        return await _run_async(partial(self.exists, path))

    async def is_directory_async(self, path: str) -> bool:
        """Check directory metadata without blocking the event loop.

        Args:
            path: Disk-relative path.

        Returns:
            Whether the path names a directory.
        """
        return await _run_async(partial(self.is_directory, path))

    async def delete_async(
        self,
        path: str,
        *,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete one file in an AnyIO worker.

        Args:
            path: Disk-relative file path.
            raise_errors: Optional write error policy.

        Returns:
            Whether a file was removed.
        """
        return await _run_async(
            partial(self.delete, path, raise_errors=raise_errors),
        )

    async def delete_directory_async(
        self,
        path: str,
        *,
        recursive: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Delete a directory in an AnyIO worker.

        Args:
            path: Disk-relative directory path.
            recursive: Whether descendants may also be removed.
            raise_errors: Optional write error policy.

        Returns:
            Whether a directory was removed.
        """
        return await _run_async(
            partial(
                self.delete_directory,
                path,
                recursive=recursive,
                raise_errors=raise_errors,
            ),
        )

    async def make_directory_async(
        self,
        path: str,
        *,
        create_parents: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Create a directory in an AnyIO worker.

        Args:
            path: Disk-relative directory path.
            create_parents: Whether to create missing ancestors.
            raise_errors: Optional write error policy.

        Returns:
            Whether the directory exists after creation.
        """
        return await _run_async(
            partial(
                self.make_directory,
                path,
                create_parents=create_parents,
                raise_errors=raise_errors,
            ),
        )

    async def copy_async(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Copy one file in an AnyIO worker.

        Args:
            source: Disk-relative source path.
            destination: Disk-relative target path.
            overwrite: Whether an existing target may be replaced.
            raise_errors: Optional write error policy.

        Returns:
            Whether the copy completed.
        """
        return await _run_async(
            partial(
                self.copy,
                source,
                destination,
                overwrite=overwrite,
                raise_errors=raise_errors,
            ),
        )

    async def move_async(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Move one file in an AnyIO worker.

        Args:
            source: Disk-relative source path.
            destination: Disk-relative target path.
            overwrite: Whether an existing target may be replaced.
            raise_errors: Optional write error policy.

        Returns:
            Whether the move completed.
        """
        return await _run_async(
            partial(
                self.move,
                source,
                destination,
                overwrite=overwrite,
                raise_errors=raise_errors,
            ),
        )

    async def list_files_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List files in an AnyIO worker.

        Args:
            path: Directory path, or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted disk-relative paths.
        """
        return await _run_async(
            partial(self.list_files, path, recursive=recursive),
        )

    async def list_directories_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        """List directories in an AnyIO worker.

        Args:
            path: Directory path, or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted disk-relative paths.
        """
        return await _run_async(
            partial(self.list_directories, path, recursive=recursive),
        )

    async def list_contents_async(
        self,
        path: str = "",
        *,
        recursive: bool = False,
    ) -> tuple[FileMetadata, ...]:
        """List normalized entries in an AnyIO worker.

        Args:
            path: Directory path, or empty disk root.
            recursive: Whether to include descendants.

        Returns:
            Sorted metadata entries.
        """
        return await _run_async(
            partial(self.list_contents, path, recursive=recursive),
        )

    async def metadata_async(self, path: str) -> FileMetadata:
        """Read path metadata in an AnyIO worker.

        Args:
            path: Disk-relative path.

        Returns:
            Normalized metadata.
        """
        return await _run_async(partial(self.metadata, path))

    async def size_async(self, path: str) -> int | None:
        """Read a file's size in an AnyIO worker.

        Args:
            path: Disk-relative path.

        Returns:
            File size in bytes or ``None``.
        """
        return await _run_async(partial(self.size, path))

    async def last_modified_async(self, path: str) -> datetime | None:
        """Read the last modification timestamp in an AnyIO worker.

        Args:
            path: Disk-relative path.

        Returns:
            Normalized UTC timestamp or ``None``.
        """
        return await _run_async(partial(self.last_modified, path))

    async def read_stream_async(
        self,
        path: str,
        *,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> AsyncGenerator[bytes, None]:
        """Read bounded chunks without blocking the event loop.

        The worker stream closes under a shield when iteration finishes or
        the consumer cancels its task.

        Args:
            path: Disk-relative source path.
            chunk_size: Maximum bytes requested per worker read.

        Yields:
            Non-empty chunks in file order.
        """
        _validate_chunk_size(chunk_size)
        backend_path = await _run_async(partial(self._backend_path, path))
        stream = await _run_async(partial(self._open_read, backend_path))
        try:
            while True:
                chunk = await _run_async(
                    partial(stream.read, chunk_size),
                )
                if not chunk:
                    break
                yield chunk
        finally:
            with anyio.CancelScope(shield=True):
                await _run_async(stream.close)

    async def write_stream_async(
        self,
        path: str,
        chunks: AsyncIterable[bytes],
        *,
        overwrite: bool = True,
        raise_errors: bool | None = None,
    ) -> bool:
        """Consume async byte chunks while writing in a bounded worker pool.

        Args:
            path: Disk-relative destination path.
            chunks: Ordered asynchronous byte chunks.
            overwrite: Whether an existing destination may be replaced.
            raise_errors: Optional write error policy.

        Returns:
            Whether the write completed.

        Raises:
            TypeError: If a source chunk is not bytes.
        """
        backend_path = await _run_async(partial(self._backend_path, path))
        should_raise = self._should_raise(raise_errors)

        def open_prepared_write() -> FilesystemStream:
            """Prepare one destination and open it within a worker.

            Returns:
                The open destination stream.
            """
            self._check_overwrite(backend_path, overwrite)
            self._prepare_parent(backend_path)
            return self._open_write(backend_path, "wb")

        try:
            stream = await _run_async(open_prepared_write)
        except OSError:
            if should_raise:
                raise
            return False
        completed = True
        try:
            async for chunk in chunks:
                if not isinstance(cast("object", chunk), bytes):
                    raise TypeError(_STREAM_CHUNK_TYPE_ERROR)
                try:
                    await _run_async(partial(stream.write, chunk))
                except OSError:
                    if should_raise:
                        raise
                    completed = False
                    break
        finally:
            with anyio.CancelScope(shield=True):
                await _run_async(stream.close)
        return completed

    async def append_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Append content in an AnyIO worker.

        Args:
            path: Disk-relative file path.
            content: Text or bytes to append.
            encoding: Encoding used for text input.
            raise_errors: Optional write error policy.

        Returns:
            Whether the append completed.
        """
        return await _run_async(
            partial(
                self.append,
                path,
                content,
                encoding=encoding,
                raise_errors=raise_errors,
            ),
        )

    async def prepend_async(
        self,
        path: str,
        content: str | bytes,
        *,
        encoding: str = "utf-8",
        raise_errors: bool | None = None,
    ) -> bool:
        """Prepend content in an AnyIO worker.

        Args:
            path: Disk-relative file path.
            content: Text or bytes placed before current content.
            encoding: Encoding used for text input.
            raise_errors: Optional write error policy.

        Returns:
            Whether the prepend completed.
        """
        return await _run_async(
            partial(
                self.prepend,
                path,
                content,
                encoding=encoding,
                raise_errors=raise_errors,
            ),
        )

    @asynccontextmanager
    async def temporary_file_async(
        self,
        *,
        directory: str = "",
        suffix: str = ".tmp",
    ) -> AsyncGenerator[str, None]:
        """Yield a temporary key and clean it up after async use.

        Args:
            directory: Optional disk-relative directory.
            suffix: Safe suffix included in the generated filename.

        Yields:
            Disk-relative key removed when the context exits.
        """
        path = self._temporary_path(directory, suffix)
        created = False
        try:
            created = await self.put_async(
                path,
                b"",
                overwrite=False,
                raise_errors=True,
            )
            yield path
        finally:
            if created:
                await self.delete_async(path, raise_errors=True)

    def _backend_path(
        self,
        path: str,
        *,
        allow_root: bool = False,
    ) -> str:
        """Validate a disk-relative key and map it to the backend namespace.

        Args:
            path: User-visible key using POSIX separators.
            allow_root: Whether the empty key may name the disk root.

        Returns:
            Backend-specific path accepted by fsspec.

        Raises:
            UnsafeStoragePathError: If the key is absolute or escapes its root.
        """
        parts = _normalize_key(path, allow_root=allow_root)
        if self._local_root is not None:
            return str(self._safe_local_path(parts))
        if not parts:
            return self._prefix or "/"
        return posixpath.join(self._prefix or "/", *parts)

    def _safe_local_path(self, parts: tuple[str, ...]) -> Path:
        """Reject existing symlink components and resolved root escapes.

        Args:
            parts: Validated relative key components.

        Returns:
            Canonical path under the trusted configured root.

        Raises:
            UnsafeStoragePathError: If a path uses a symlink or escapes root.
        """
        root = self._local_root
        if root is None:
            raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
        candidate = root.joinpath(*parts)
        # fsspec's public API takes paths, so validate before every operation.
        if _has_symlink_component(root, parts):
            raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as error:
            raise UnsafeStoragePathError(_INVALID_PATH_ERROR) from error
        return resolved

    def _prepare_parent(self, backend_path: str) -> None:
        """Create the destination parent using fsspec's public API.

        Args:
            backend_path: Validated backend destination path.
        """
        parent = posixpath.dirname(backend_path.rstrip("/"))
        if not parent:
            parent = "/" if not self._local_root else str(self._local_root)
        if self._local_root is not None:
            relative_parent = Path(parent).relative_to(self._local_root)
            self._safe_local_path(tuple(relative_parent.parts))
        self._filesystem.makedirs(parent, exist_ok=True)

    def _check_overwrite(self, path: str, overwrite: bool) -> None:
        """Reject a destination conflict before a backend mutates it.

        Args:
            path: Validated backend destination.
            overwrite: Whether existing files may be replaced.

        Raises:
            FileExistsError: If a destination exists and replacement is off.
            IsADirectoryError: If a file operation targets a directory.
        """
        if not self._filesystem.exists(path):
            return
        if self._filesystem.isdir(path):
            raise IsADirectoryError(path)
        if not overwrite:
            raise FileExistsError(path)

    def _mutate(
        self,
        operation: Callable[[], bool | None],
        raise_errors: bool | None,
    ) -> bool:
        """Run one mutating backend call with the selected OSError policy.

        Args:
            operation: Validated backend mutation.
            raise_errors: Per-call policy or the configured disk default.

        Returns:
            Whether the operation completed or failed under suppression mode.
        """
        try:
            result = operation()
        except OSError:
            if self._should_raise(raise_errors):
                raise
            return False
        return result is not False

    def _should_raise(self, raise_errors: bool | None) -> bool:
        """Select the configured default or an explicit operation policy.

        Args:
            raise_errors: Optional caller policy.

        Returns:
            Whether operation failures should be raised.
        """
        return self._raise_errors if raise_errors is None else raise_errors

    def _open_read(self, path: str) -> FilesystemStream:
        """Open a validated path for binary reads.

        Args:
            path: Validated backend path.

        Returns:
            The fsspec stream's binary read and close surface.
        """
        if self._filesystem.isdir(path):
            raise IsADirectoryError(path)
        return self._filesystem.open(path, "rb")

    def _open_write(self, path: str, mode: str) -> FilesystemStream:
        """Open a validated path in one binary write mode.

        Args:
            path: Validated backend path.
            mode: Supported binary mode selected by this adapter.

        Returns:
            The fsspec stream's binary write and close surface.
        """
        return self._filesystem.open(path, mode)

    def _list_records(
        self,
        path: str,
        *,
        recursive: bool,
    ) -> list[tuple[str, Mapping[str, object]]]:
        """Read detailed entries from fsspec list or find operations.

        Args:
            path: Validated backend directory path.
            recursive: Whether to use the backend recursive listing API.

        Returns:
            Backend path and metadata pairs in backend order.
        """
        if recursive:
            raw = self._filesystem.find(
                path,
                withdirs=True,
                detail=True,
            )
            if isinstance(raw, Mapping):
                return list(raw.items())
            return [(name, self._filesystem.info(name)) for name in raw]
        raw_entries = self._filesystem.ls(path, detail=True)
        records: list[tuple[str, Mapping[str, object]]] = []
        for item in raw_entries:
            if isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str):
                    records.append((name, item))
            else:
                records.append(
                    (
                        item,
                        self._filesystem.info(item),
                    ),
                )
        return records

    def _metadata_from_record(
        self,
        backend_path: str,
        info: Mapping[str, object],
    ) -> FileMetadata:
        """Convert backend details to the dependency-independent value type.

        Args:
            backend_path: Backend path returned or selected by fsspec.
            info: Public fsspec ``info`` or detailed listing mapping.

        Returns:
            Normalized metadata with an application-relative path.
        """
        relative_path = self._relative_path(backend_path)
        entry_type = info.get("type")
        is_directory = entry_type in {"directory", "dir"}
        is_file = entry_type == "file"
        if not is_directory and not is_file:
            is_directory = self._filesystem.isdir(backend_path)
            is_file = not is_directory
        raw_size = info.get("size")
        size = raw_size if type(raw_size) is int and raw_size >= 0 else None
        modified = _normalize_modified_time(
            info.get("mtime", info.get("LastModified", info.get("created"))),
        )
        return FileMetadata(
            path=relative_path,
            size=size,
            modified=modified,
            is_file=is_file,
            is_directory=is_directory,
        )

    def _relative_path(self, backend_path: str) -> str:
        """Strip the configured root while preserving relative POSIX keys.

        Args:
            backend_path: Path returned by the backend.

        Returns:
            Path relative to this disk's configured root.

        Raises:
            UnsafeStoragePathError: If a listing escapes its root.
        """
        if self._local_root is not None:
            candidate = Path(backend_path)
            try:
                self._safe_local_path(
                    tuple(candidate.relative_to(self._local_root).parts),
                )
                relative = candidate.relative_to(self._local_root)
                if relative == Path():
                    return ""
                return relative.as_posix()
            except (OSError, ValueError) as error:
                raise UnsafeStoragePathError(_INVALID_PATH_ERROR) from error
        normalized = backend_path.replace("\\", "/")
        prefix = self._prefix.rstrip("/")
        if prefix:
            if normalized == prefix:
                return ""
            if not normalized.startswith(f"{prefix}/"):
                raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
            return normalized[len(prefix) + 1 :]
        return normalized.lstrip("/")

    def _temporary_path(self, directory: str, suffix: str) -> str:
        """Generate one unpredictable key under the selected disk root.

        Args:
            directory: Optional relative parent directory.
            suffix: Safe filename suffix.

        Returns:
            Unique disk-relative key not yet created on the backend.

        Raises:
            UnsafeStoragePathError: If the directory or suffix is unsafe.
        """
        directory_parts = _normalize_key(directory, allow_root=True)
        if (
            "/" in suffix
            or "\\" in suffix
            or any(
                ord(character) < _CONTROL_CHARACTER_LIMIT
                for character in suffix
            )
            or "\x00" in suffix
        ):
            raise UnsafeStoragePathError(_INVALID_SUFFIX_ERROR)
        filename = f".titanspan-{secrets.token_hex(16)}{suffix}"
        return "/".join((*directory_parts, filename))

    _filesystem: FsspecFilesystem
    _local_root: Path | None
    _prefix: str
    _raise_errors: bool


def _has_symlink_component(root: Path, parts: tuple[str, ...]) -> bool:
    """Check existing local path components without following links.

    Args:
        root: Canonical trusted root.
        parts: Validated disk-relative components.

    Returns:
        Whether any component is a symbolic link.
    """
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _is_string(value: object) -> bool:
    """Check the runtime type of a value entering a typed path API.

    Args:
        value: Value supplied to a public disk operation.

    Returns:
        Whether the value is a string.
    """
    return isinstance(value, str)


def _normalize_key(path: str, *, allow_root: bool) -> tuple[str, ...]:
    """Validate user key syntax before any backend path is constructed.

    Args:
        path: User-visible path using POSIX separators.
        allow_root: Whether the empty string may denote the disk root.

    Returns:
        Non-empty relative path components, or an empty root tuple.

    Raises:
        UnsafeStoragePathError: If the key is absolute or malformed.
    """
    if not _is_string(path) or "\x00" in path:
        raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
    if not path and allow_root:
        return ()
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(ord(character) < _CONTROL_CHARACTER_LIMIT for character in path)
    ):
        raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
    parts = tuple(path.split("/"))
    if any(
        part in {"", ".", ".."}
        or ":" in part
        or any(character in _INVALID_FILENAME_CHARACTERS for character in part)
        or part.endswith((".", " "))
        or part.split(".", 1)[0].upper() in _RESERVED_WINDOWS_NAMES
        for part in parts
    ):
        raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
    return parts


def _normalize_prefix(root: str | Path | None) -> str:
    """Normalize a backend-relative root prefix without allowing traversal.

    Args:
        root: Configured fsspec path prefix.

    Returns:
        Canonical slash-prefixed backend root or an empty prefix.

    Raises:
        UnsafeStoragePathError: If the configured prefix contains traversal.
    """
    if root is None or str(root) in {"", "/"}:
        return ""
    value = str(root).replace("\\", "/")
    if "\x00" in value or any(
        ord(character) < _CONTROL_CHARACTER_LIMIT for character in value
    ):
        raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
    parts = tuple(part for part in value.split("/") if part not in {"", "."})
    if any(part == ".." or ":" in part for part in parts):
        raise UnsafeStoragePathError(_INVALID_PATH_ERROR)
    return "/" + "/".join(parts)


def _normalize_modified_time(value: object) -> datetime | None:
    """Convert standard fsspec timestamp values to aware UTC datetimes.

    Args:
        value: Backend modification timestamp or creation timestamp.

    Returns:
        UTC timestamp or ``None`` for absent and invalid values.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _validate_chunk_size(chunk_size: int) -> None:
    """Reject invalid chunk sizes before opening a file handle.

    Args:
        chunk_size: Maximum byte count requested per stream operation.

    Raises:
        ValueError: If the size is not a positive integer.
    """
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError(_INVALID_CHUNK_SIZE_ERROR)


__all__ = ["FilesystemDisk"]
