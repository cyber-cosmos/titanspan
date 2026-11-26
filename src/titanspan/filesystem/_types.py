"""Describe the narrow public fsspec surface used by the adapter.

fsspec does not ship type stubs, so factories cross one runtime-validated
boundary before backend calls use these typed structural interfaces.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

type FilesystemInfo = Mapping[str, object]
type FilesystemListing = list[str | FilesystemInfo]
type FilesystemFindResult = list[str] | dict[str, FilesystemInfo]


class FilesystemStream(Protocol):
    """Describe a binary stream returned by an fsspec filesystem.

    The adapter uses only byte reads, writes, and deterministic close calls.
    """

    def read(self, size: int = -1) -> bytes:
        """Read bytes from the selected file.

        Args:
            size: Maximum bytes requested, or negative for all bytes.

        Returns:
            Bytes read from the stream.
        """
        ...

    def write(self, data: bytes) -> int:
        """Write one bytes chunk to the selected file.

        Args:
            data: Bytes to write.

        Returns:
            Number of bytes accepted by the stream.
        """
        ...

    def close(self) -> None:
        """Close the stream and flush backend-owned buffers.

        Returns:
            None.
        """
        ...


class FsspecFilesystem(Protocol):
    """Describe fsspec operations required by the disk adapter.

    The interface is private because fsspec does not ship type stubs.
    """

    def exists(self, path: str, **kwargs: object) -> bool:
        """Check whether a backend path exists.

        Args:
            path: Selected backend path.
            **kwargs: Optional fsspec-specific existence options.

        Returns:
            Whether the path exists.
        """
        ...

    def isdir(self, path: str) -> bool:
        """Check whether one backend path names a directory.

        Args:
            path: Selected backend path.

        Returns:
            Whether the path names a directory.
        """
        ...

    def rm(self, path: str, recursive: bool = False) -> None:
        """Remove a file or directory through the backend.

        Args:
            path: Selected backend path.
            recursive: Whether directory descendants may be removed.
        """
        ...

    def rmdir(self, path: str) -> None:
        """Remove an empty directory through the backend.

        Args:
            path: Selected backend directory.
        """
        ...

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        """Create a directory and any missing parents.

        Args:
            path: Selected backend directory.
            exist_ok: Whether an existing directory is accepted.
        """
        ...

    def mkdir(self, path: str, create_parents: bool = True) -> None:
        """Create one directory using backend-native semantics.

        Args:
            path: Selected backend directory.
            create_parents: Whether missing parents may also be created.
        """
        ...

    def copy(self, path1: str, path2: str) -> None:
        """Copy one file within this backend.

        Args:
            path1: Existing backend file.
            path2: Backend destination path.
        """
        ...

    def mv(self, path1: str, path2: str) -> None:
        """Move one file within this backend.

        Args:
            path1: Existing backend file.
            path2: Backend destination path.
        """
        ...

    def ls(
        self,
        path: str,
        detail: bool = True,
    ) -> FilesystemListing:
        """List immediate children and optional metadata.

        Args:
            path: Selected backend directory.
            detail: Whether metadata mappings should be returned.

        Returns:
            Child paths or child metadata mappings.
        """
        ...

    def find(
        self,
        path: str,
        *,
        withdirs: bool = False,
        detail: bool = False,
    ) -> FilesystemFindResult:
        """Find files and optional directories below one path.

        Args:
            path: Selected backend directory.
            withdirs: Whether directory entries should be included.
            detail: Whether metadata should be returned for each entry.

        Returns:
            Path names or a path-to-metadata mapping.
        """
        ...

    def info(self, path: str) -> FilesystemInfo:
        """Return public metadata for one backend path.

        Args:
            path: Selected backend path.

        Returns:
            Metadata supplied by the backend.
        """
        ...

    def open(self, path: str, mode: str = "rb") -> FilesystemStream:
        """Open a backend file using a supported binary mode.

        Args:
            path: Selected backend file.
            mode: Binary read, write, or append mode.

        Returns:
            An open binary stream owned by the caller.
        """
        ...


__all__ = ["FilesystemStream", "FsspecFilesystem"]
