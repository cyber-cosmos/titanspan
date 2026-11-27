"""Define the native request-owned uploaded-file capability.

The HTTP parser owns temporary file resources through request finalization.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class HttpUploadedFile(Protocol):
    """Expose safe metadata and bounded async reads for one upload.

    The uploaded filename is untrusted display data. Select a destination
    path from application-owned values before storage.
    """

    @property
    def filename(self) -> str:
        """Return the client-supplied filename.

        Use this value for display only.
        """
        ...

    @property
    def safe_filename(self) -> str:
        """Return a sanitized filename.

        Path separators and control characters are removed.
        """
        ...

    @property
    def content_type(self) -> str | None:
        """Return the client-supplied media type.

        Treat this value as untrusted input.
        """
        ...

    @property
    def size(self) -> int | None:
        """Return the parsed upload size.

        The parser may not provide this value.
        """
        ...

    async def read(self, size: int = -1) -> bytes:
        """Read at most ``size`` bytes or the remaining content.

        Args:
            size: Maximum bytes to read, or ``-1`` for remaining content.

        Returns:
            The bytes returned by the parser-owned temporary file.
        """
        ...

    def iter_chunks(
        self,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """Yield bounded upload chunks without materializing the file.

        Args:
            chunk_size: Maximum bytes yielded for each chunk.

        Returns:
            An async iterator owned by the request lifecycle.
        """
        ...

    async def aclose(self) -> None:
        """Close this upload before request finalization.

        Use this method when the application needs early cleanup.
        """
        ...


__all__ = ["HttpUploadedFile"]
