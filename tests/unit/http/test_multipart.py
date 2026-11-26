"""Verify immutable multipart attachments validate their header metadata.

Invalid upload values fail before the HTTP transport is called.
"""

from typing import cast

import pytest

from titanspan.contracts.http import MultipartFile

pytestmark = pytest.mark.unit


def test_multipart_attachment_rejects_invalid_filename() -> None:
    """Reject empty filenames and control characters in part headers.

    HTTPX2 receives only safe metadata from native attachments.
    """
    for filename in ("", "report\r\ninjected: true"):
        with pytest.raises(ValueError, match="filename"):
            MultipartFile(filename, b"content")


def test_multipart_attachment_rejects_invalid_media_type() -> None:
    """Reject malformed media types and line breaks in content type values.

    Attachment headers cannot introduce extra wire-level fields.
    """
    for content_type in ("invalid", "text/plain\r\nX-Injected: yes"):
        with pytest.raises(ValueError, match="content type"):
            MultipartFile("report.txt", b"content", content_type)


def test_multipart_attachment_requires_immutable_bytes() -> None:
    """Require immutable bytes so request retries can safely replay uploads.

    Mutable buffers are rejected rather than copied implicitly.
    """
    with pytest.raises(TypeError, match="must be bytes"):
        MultipartFile("report.txt", cast("bytes", bytearray(b"content")))
