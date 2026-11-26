"""Provide isolated in-memory disks and storage assertions for tests.

The facade owns context binding; this value keeps fake contents and checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titanspan.filesystem.disk import FilesystemDisk

_MISSING_FILE_ERROR = "Expected a stored file at the selected path."
_EXISTING_FILE_ERROR = "Expected no stored file at the selected path."
_CONTENT_MISMATCH_ERROR = "Stored file content did not match expected bytes."


class FilesystemFake:
    """Expose one isolated memory disk with deterministic assertions.

    Attributes:
        disk: Disk selected by the active Storage facade fake scope.
    """

    def __init__(self, disk: FilesystemDisk) -> None:
        """Retain the memory-backed disk scoped by the facade.

        Args:
            disk: Independent fsspec memory disk used by this fake.
        """
        self.disk = disk

    def assert_exists(self, path: str) -> None:
        """Assert that a file or directory exists in the fake disk.

        Args:
            path: Disk-relative path to verify.

        Raises:
            AssertionError: If the selected path is absent.
        """
        if not self.disk.exists(path):
            raise AssertionError(_MISSING_FILE_ERROR)

    def assert_missing(self, path: str) -> None:
        """Assert that a file or directory is absent from the fake disk.

        Args:
            path: Disk-relative path to verify.

        Raises:
            AssertionError: If the selected path exists.
        """
        if self.disk.exists(path):
            raise AssertionError(_EXISTING_FILE_ERROR)

    def assert_stored(
        self,
        path: str,
        content: str | bytes | None = None,
        *,
        encoding: str = "utf-8",
    ) -> None:
        """Assert that a file exists and optionally matches exact content.

        Args:
            path: Disk-relative file path.
            content: Optional expected text or byte content.
            encoding: Encoding used when expected content is text.

        Raises:
            AssertionError: If the file is absent or content differs.
        """
        if not self.disk.exists(path) or self.disk.is_directory(path):
            raise AssertionError(_MISSING_FILE_ERROR)
        if content is None:
            return
        expected = (
            content.encode(encoding) if isinstance(content, str) else content
        )
        if self.disk.get_bytes(path) != expected:
            raise AssertionError(_CONTENT_MISMATCH_ERROR)

    def assert_not_stored(self, path: str) -> None:
        """Assert that no file or directory exists at a path.

        Args:
            path: Disk-relative path to verify.

        Raises:
            AssertionError: If the selected path exists.
        """
        self.assert_missing(path)

    disk: FilesystemDisk


__all__ = ["FilesystemFake"]
