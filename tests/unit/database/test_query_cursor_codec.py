"""Verify cursor tokens preserve typed values and reject malformed input.
"""  # fmt: skip

from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest

from titanspan.database import DatabaseQueryError
from titanspan.database.query_builder import (
    _cursor_scalar,  # pyright: ignore[reportPrivateUsage]
    _CursorOrder,  # pyright: ignore[reportPrivateUsage]
    _decode_cursor,  # pyright: ignore[reportPrivateUsage]
    _decode_cursor_scalar,  # pyright: ignore[reportPrivateUsage]
    _encode_cursor,  # pyright: ignore[reportPrivateUsage]
    _encode_cursor_scalar,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit


def _encode_json_token(payload: object) -> str:
    """Encode one JSON payload as a URL-safe test cursor token.

    Args:
        payload: JSON value placed in the cursor envelope.

    Returns:
        URL-safe base64 token text.
    """
    raw = json.dumps(payload).encode("utf-8")
    return _encode_bytes_token(raw)


def _encode_bytes_token(value: bytes) -> str:
    """Encode bytes as URL-safe base64 without interpreting their contents.

    Args:
        value: Raw bytes used to construct one cursor token.

    Returns:
        URL-safe base64 token text.
    """
    return base64.urlsafe_b64encode(value).decode("ascii")


_SPECS: tuple[_CursorOrder, ...] = (("id", False),)
_CURSOR_SCALARS: tuple[object, ...] = (
    False,
    7,
    2.5,
    "entry",
    Decimal("12.340"),
    datetime(2026, 11, 28, 12, 30, tzinfo=UTC),
    date(2026, 11, 28),
    time(12, 30, 45),
    UUID("12345678-1234-5678-1234-567812345678"),
)
_INVALID_CURSOR_PAYLOADS: tuple[object, ...] = (
    None,
    [],
    {"version": 1},
    {
        "version": 1,
        "direction": "sideways",
        "columns": [["id", False]],
        "values": [["int", 1]],
    },
    {
        "version": True,
        "direction": "after",
        "columns": [["id", False]],
        "values": [["int", 1]],
    },
    {
        "version": 2,
        "direction": "after",
        "columns": [["id", False]],
        "values": [["int", 1]],
    },
    {
        "version": 1,
        "direction": "after",
        "columns": [["other", False]],
        "values": [["int", 1]],
    },
    {
        "version": 1,
        "direction": "after",
        "columns": [["id", False]],
        "values": "not-a-list",
    },
    {
        "version": 1,
        "direction": "after",
        "columns": [["id", False]],
        "values": [],
    },
)


@pytest.mark.parametrize("value", _CURSOR_SCALARS)
def test_supported_cursor_scalars_round_trip(value: object) -> None:
    """Encode and decode each supported cursor scalar without coercion.
    """  # fmt: skip
    scalar = _cursor_scalar(value)

    assert _decode_cursor_scalar(_encode_cursor_scalar(scalar)) == value


def test_cursor_envelope_round_trips_bound_order_values() -> None:
    """Decode a valid token against the exact query ordering metadata.
    """  # fmt: skip
    token = _encode_cursor("after", _SPECS, (17,))

    assert _decode_cursor(token, _SPECS) == ("after", (17,))


@pytest.mark.parametrize("payload", _INVALID_CURSOR_PAYLOADS)
def test_cursor_envelope_rejects_invalid_payloads(payload: object) -> None:
    """Reject tokens with invalid envelope fields or ordering metadata.
    """  # fmt: skip
    token = _encode_json_token(payload)

    with pytest.raises(DatabaseQueryError, match="cursor token"):
        _decode_cursor(token, _SPECS)


@pytest.mark.parametrize(
    "token",
    [
        ("",),
        ("!not-base64!",),
        ("snowman-☃",),
        (_encode_bytes_token(bytes((0xFF,))),),
        (_encode_bytes_token(b"not-json"),),
        ("x" * 2049,),
    ],
)
def test_cursor_envelope_rejects_malformed_tokens(token: str) -> None:
    """Reject invalid base64, encoding, JSON, and oversized token input.
    """  # fmt: skip
    with pytest.raises(DatabaseQueryError, match="cursor token"):
        _decode_cursor(token, _SPECS)


@pytest.mark.parametrize(
    "value",
    [
        (None,),
        (1,),
        ([],),
        (["int"],),
        ([1, 1],),
        (["int", True],),
        (["float", float("inf")],),
        (["decimal", "not-a-decimal"],),
        (["date", "not-a-date"],),
        (["datetime", "not-a-datetime"],),
        (["unknown", "value"],),
    ],
)
def test_cursor_scalar_decoder_rejects_invalid_values(
    value: object,
) -> None:
    """Reject values that do not match a safe untrusted cursor scalar tag.
    """  # fmt: skip
    with pytest.raises(DatabaseQueryError, match="cursor token"):
        _decode_cursor_scalar(value)


@pytest.mark.parametrize(
    "value",
    [
        (object(),),
        (float("nan"),),
        (float("inf"),),
        (Decimal("NaN"),),
    ],
)
def test_cursor_scalar_encoder_rejects_unsupported_or_non_finite_values(
    value: object,
) -> None:
    """Reject unsupported values and numbers that cannot be JSON encoded.
    """  # fmt: skip
    with pytest.raises(DatabaseQueryError, match="cursor ordering"):
        _encode_cursor_scalar(_cursor_scalar(value))


def test_cursor_encoder_requires_boundary_values_and_limits_token_size() -> (
    None
):
    """Refuse cursor tokens without a boundary or within safe size limits.
    """  # fmt: skip
    with pytest.raises(DatabaseQueryError, match="boundary row"):
        _encode_cursor("after", _SPECS, None)
    with pytest.raises(DatabaseQueryError, match="supported size limit"):
        _encode_cursor("after", (("x" * 5000, False),), (1,))
