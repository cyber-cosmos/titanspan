"""Verify uploaded-file metadata, bounded reads, and ownership behavior.

Local fixtures keep these assertions deterministic.
"""

import pytest

from titanspan.http.uploaded_file import UploadedFile

pytestmark = pytest.mark.unit


def test_uploaded_file_sanitizes_only_the_display_basename() -> None:
    """Remove path components and control characters from display names.

    The assertions verify the public result and its error paths.
    """
    upload = _upload("../../private\\report\n.txt")

    assert upload.filename == "../../private\\report\n.txt"
    assert upload.safe_filename == "report.txt"


@pytest.mark.anyio
async def test_uploaded_file_reads_chunks_and_closes_once() -> None:
    """Read a bounded sequence and finalize the parser-owned file once.

    The assertions verify the public result and its error paths.
    """
    content = bytearray(b"abcdefgh")
    closed = False

    async def read_bytes(size: int) -> bytes:
        """Remove up to the requested byte count from local test content.

        Local fixtures keep these assertions deterministic.
        """
        if size < 0:
            size = len(content)
        result = bytes(content[:size])
        del content[:size]
        return result

    async def close_file() -> None:
        """Record resource finalization.

        Local fixtures keep these assertions deterministic.
        """
        nonlocal closed
        closed = True

    upload = UploadedFile(
        filename="report.bin",
        content_type="application/octet-stream",
        size=8,
        read_bytes=read_bytes,
        close_file=close_file,
    )

    assert [chunk async for chunk in upload.iter_chunks(3)] == [
        b"abc",
        b"def",
        b"gh",
    ]
    await upload.aclose()
    await upload.aclose()

    assert closed
    with pytest.raises(RuntimeError, match="upload is closed"):
        await upload.read()


@pytest.mark.anyio
async def test_uploaded_file_rejects_invalid_read_sizes() -> None:
    """Reject negative limits other than the documented read-all sentinel.

    The assertions verify the public result and its error paths.
    """
    upload = _upload("file.txt")

    with pytest.raises(ValueError, match="-1 or non-negative"):
        await upload.read(-2)
    with pytest.raises(ValueError, match="must be positive"):
        _ = [chunk async for chunk in upload.iter_chunks(0)]


def _upload(filename: str) -> UploadedFile:
    """Create a small upload using an explicitly typed async reader.

    Local fixtures keep these assertions deterministic.
    """

    async def read_bytes(size: int) -> bytes:
        """Return a deterministic prefix for unit-level metadata checks.

        Local fixtures keep these assertions deterministic.
        """
        del size
        return b"data"

    async def close_file() -> None:
        """Complete a no-op parser cleanup operation.

        Local fixtures keep these assertions deterministic.
        """
        return

    return UploadedFile(
        filename=filename,
        content_type=None,
        size=None,
        read_bytes=read_bytes,
        close_file=close_file,
    )
