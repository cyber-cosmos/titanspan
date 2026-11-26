"""Provide bounded, asynchronous access to one multipart upload.

Upload reads are bounded; cleanup follows request ownership.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import PurePosixPath

_INVALID_READ_SIZE_ERROR = "Upload read size must be -1 or non-negative."
_CLOSED_UPLOAD_ERROR = "The request-owned upload is closed."
_INVALID_CHUNK_SIZE_ERROR = "Upload chunk size must be positive."


class UploadedFile:
    """Wrap a parser-owned temporary upload without exposing its backend.

    The upload remains owned by its request. Its creator must close the
    request after downstream response transmission has completed.
    """

    def __init__(
        self,
        *,
        filename: str,
        content_type: str | None,
        size: int | None,
        read_bytes: Callable[[int], Awaitable[bytes]],
        close_file: Callable[[], Awaitable[None]],
    ) -> None:
        """Retain safe metadata and asynchronous operations for one upload.

        Args:
            filename: Untrusted client-supplied filename for display only.
            content_type: Optional client-supplied media type.
            size: Parsed file size when the parser provides it.
            read_bytes: Async reader owned by the private ASGI adapter.
            close_file: Async finalizer owned by the private adapter.
        """
        self.filename = filename
        self.content_type = content_type
        self.size = size
        self._read_bytes = read_bytes
        self._close_file = close_file
        self._closed = False

    @property
    def safe_filename(self) -> str:
        """Return a basename with path separators and control bytes removed.

        Returns:
            A sanitized display or storage candidate. Callers must still
            choose an application-owned destination path.
        """
        basename = PurePosixPath(self.filename.replace("\\", "/")).name
        safe = "".join(char for char in basename if char.isprintable())
        return safe.strip() or "upload"

    async def read(self, size: int = -1) -> bytes:
        """Read upload bytes asynchronously.

        Args:
            size: Maximum bytes to read, or ``-1`` for the remaining content.

        Returns:
            The bytes returned by the underlying spooled upload.

        Raises:
            ValueError: If ``size`` is less than ``-1``.
            RuntimeError: If the request has already closed the upload.
        """
        if size < -1:
            raise ValueError(_INVALID_READ_SIZE_ERROR)
        if self._closed:
            raise RuntimeError(_CLOSED_UPLOAD_ERROR)
        return await self._read_bytes(size)

    async def iter_chunks(
        self,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """Yield bounded chunks until the upload reaches end of file.

        Args:
            chunk_size: Maximum number of bytes returned per iteration.

        Yields:
            Upload content in bounded memory chunks.

        Raises:
            ValueError: If ``chunk_size`` is not positive.
        """
        if chunk_size <= 0:
            raise ValueError(_INVALID_CHUNK_SIZE_ERROR)
        while chunk := await self.read(chunk_size):
            yield chunk

    async def aclose(self) -> None:
        """Close the underlying temporary upload exactly once.

        Repeated calls are harmless. Request lifecycle code normally owns
        finalization, but explicit close is available to early consumers.
        """
        if self._closed:
            return
        self._closed = True
        await self._close_file()

    filename: str
    content_type: str | None
    size: int | None
    _read_bytes: Callable[[int], Awaitable[bytes]]
    _close_file: Callable[[], Awaitable[None]]
    _closed: bool


__all__ = ["UploadedFile"]
