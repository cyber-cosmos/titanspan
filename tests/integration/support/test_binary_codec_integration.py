"""Verify codec integration with Python's standard identifier types.

This test crosses the package export boundary and exercises a real UUID.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from titanspan.support import BinaryCodec

pytestmark = pytest.mark.integration


def test_public_codec_interoperates_with_stdlib_uuid() -> None:
    """Round-trip a UUID through the package-level Support API.

    No optional identifier package is needed for standard UUID support.
    """
    identifier = UUID("550e8400-e29b-41d4-a716-446655440000")

    encoded = BinaryCodec.encode(identifier, "uuid")

    assert encoded == identifier.bytes
    assert BinaryCodec.decode(encoded, "uuid") == str(identifier)
