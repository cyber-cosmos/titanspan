"""Verify binary identifier conversion and codec registration behaviour.

The cases cover the distinction between text and byte sequences along with
UUID and ULID round trips.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.support import BinaryCodec

if TYPE_CHECKING:
    from titanspan.support.binary_codec import BinaryCodecValue

pytestmark = pytest.mark.unit


class _UlidLike:
    """Provide a small test object with a native byte representation.

    The object models common ULID packages that expose ``__bytes__`` without
    making any optional identifier package a requirement for Titanspan.
    """

    def __init__(self, value: bytes) -> None:
        """Store the test identifier bytes.

        Args:
            value: The 16-byte encoded identifier.
        """
        self._value = value

    def __bytes__(self) -> bytes:
        """Return the identifier's encoded byte sequence.

        Returns:
            The value supplied to the test object.
        """
        return self._value


@pytest.fixture(autouse=True)
def reset_binary_codecs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate registered codecs so custom formats do not leak between tests.

    Args:
        monkeypatch: Fixture that restores the class registry after each case.
    """
    monkeypatch.setattr(
        "titanspan.support.binary_codec.BinaryCodec._custom_codecs",
        {},
    )


def test_formats_include_defaults_in_stable_order() -> None:
    """Expose the UUID and ULID codecs before registered formats.

    The stable order makes built-in formats predictable in user interfaces.
    """
    assert BinaryCodec.formats() == ["uuid", "ulid"]


def test_register_adds_a_custom_format() -> None:
    """Register a codec and delegate both operations to callbacks.

    Custom handlers are listed with built-in formats and used for conversion.
    """

    def encode(_value: object) -> bytes:
        """Return a constant encoding for the test input.

        Args:
            _value: The value passed to the registered codec.
        """
        return b"encoded" if _value == "input" else b"other"

    def decode(_value: str | bytes | None) -> str:
        """Return a constant decoded value for the test input.

        Args:
            _value: The value passed to the registered codec.
        """
        return "decoded" if _value == b"input" else "other"

    BinaryCodec.register("custom", encode, decode)

    assert BinaryCodec.formats() == ["uuid", "ulid", "custom"]
    assert BinaryCodec.encode("input", "custom") == b"encoded"
    assert BinaryCodec.decode(b"input", "custom") == "decoded"


def test_registered_codec_overrides_a_builtin_format() -> None:
    """Let custom registrations take precedence over built-in codecs.

    The built-in format remains listed once after a replacement is installed.
    """

    def encode(_value: object) -> bytes:
        """Return the replacement encoding.

        Args:
            _value: The value passed to the registered codec.
        """
        return b"replacement"

    def decode(_value: str | bytes | None) -> str:
        """Return the replacement decoded value.

        Args:
            _value: The value passed to the registered codec.
        """
        return "replacement"

    BinaryCodec.register("uuid", encode, decode)

    assert BinaryCodec.encode("value", "uuid") == b"replacement"
    assert BinaryCodec.decode("value", "uuid") == "replacement"
    assert BinaryCodec.formats() == ["uuid", "ulid"]


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", b"", b"   "],
)
def test_blank_values_encode_and_decode_as_none(
    value: str | bytes | None,
) -> None:
    """Return ``None`` when the input is an empty string or byte sequence.

    Args:
        value: A nullable textual or byte input.
    """
    assert BinaryCodec.encode(value, "uuid") is None
    assert BinaryCodec.encode(value, "ulid") is None
    assert BinaryCodec.decode(value, "uuid") is None
    assert BinaryCodec.decode(value, "ulid") is None


def test_invalid_format_raises_a_value_error() -> None:
    """Reject unsupported codec names for non-blank values.

    Both conversion directions use the same format error category.
    """
    with pytest.raises(ValueError, match=r"Format \[invalid\] is invalid"):
        BinaryCodec.encode("value", "invalid")
    with pytest.raises(ValueError, match=r"Format \[invalid\] is invalid"):
        BinaryCodec.decode("value", "invalid")


def test_blank_input_short_circuits_invalid_format_lookup() -> None:
    """Preserve blank-input handling before format validation.

    Blank values return ``None`` without attempting a registry lookup.
    """
    assert BinaryCodec.encode(None, "invalid") is None
    assert BinaryCodec.decode(None, "invalid") is None


def test_uuid_codec_converts_strings_objects_and_binary_values() -> None:
    """Use UUID objects and bytes for the binary representation.

    Text inputs decode to Python's canonical lowercase UUID form.
    """
    value = "550e8400-e29b-41d4-a716-446655440000"
    encoded = bytes.fromhex("550e8400e29b41d4a716446655440000")

    assert BinaryCodec.encode(value, "uuid") == encoded
    assert BinaryCodec.encode(uuid.UUID(value), "uuid") == encoded
    assert BinaryCodec.encode(encoded, "uuid") == encoded
    assert BinaryCodec.encode(value.encode("ascii"), "uuid") == encoded
    assert BinaryCodec.decode(encoded, "uuid") == value
    assert BinaryCodec.decode(value, "uuid") == value
    assert BinaryCodec.decode(value.encode("ascii"), "uuid") == value


def test_uuid_binary_values_are_not_mistaken_for_utf8_text() -> None:
    """Treat 16-byte values as binary even when they are valid UTF-8.

    Python distinguishes text from bytes and can preserve the raw value.
    """
    encoded = b"abcdefghijklmnop"
    value = uuid.UUID(bytes=encoded)

    assert BinaryCodec.encode(encoded, "uuid") == encoded
    assert BinaryCodec.decode(encoded, "uuid") == str(value)
    assert BinaryCodec.encode(_UlidLike(encoded), "uuid") == encoded
    with pytest.raises(ValueError, match="exactly 16 bytes"):
        BinaryCodec.encode(_UlidLike(b"short"), "uuid")


def test_uuid_codec_rejects_values_outside_its_typed_input() -> None:
    """Defend the runtime boundary from untyped callers.

    Static typing prevents ordinary callers from supplying unrelated values.
    """
    value = cast("BinaryCodecValue", 42)

    with pytest.raises(TypeError, match="UUID values"):
        BinaryCodec.encode(value, "uuid")


def test_uuid_text_containing_nul_bytes_uses_binary_semantics() -> None:
    """Interpret NUL-bearing strings as byte payloads like the source API.

    A 16-byte NUL-containing value maps directly to a UUID.
    """
    encoded = b"\x00" + b"a" * 15
    value = encoded.decode("ascii")

    assert BinaryCodec.encode(value, "uuid") == encoded
    assert BinaryCodec.decode(value, "uuid") == str(uuid.UUID(bytes=encoded))


def test_uuid_codec_rejects_malformed_values() -> None:
    """Raise value errors for invalid UUID text and binary widths.

    Malformed inputs never silently pass through unchanged.
    """
    with pytest.raises(ValueError, match="badly formed hexadecimal UUID"):
        BinaryCodec.encode("not-a-uuid", "uuid")
    with pytest.raises(ValueError, match="exactly 16 bytes"):
        BinaryCodec.encode(b"\x00" * 15, "uuid")
    with pytest.raises(ValueError, match="exactly 16 bytes"):
        BinaryCodec.decode(b"\x00" * 15, "uuid")


def test_ulid_codec_converts_text_and_bytes() -> None:
    """Encode ULID text using its 128-bit Crockford Base32 value.

    The test vector exercises both text and binary round trips.
    """
    value = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    encoded = bytes.fromhex("01563e3ab5d3d6764c61efb99302bd5b")

    assert BinaryCodec.encode(value, "ulid") == encoded
    assert BinaryCodec.encode(encoded, "ulid") == encoded
    assert BinaryCodec.decode(encoded, "ulid") == value
    assert BinaryCodec.decode(value, "ulid") == value
    assert BinaryCodec.decode(value.lower(), "ulid") == value
    assert BinaryCodec.encode(value.encode("ascii"), "ulid") == encoded
    assert BinaryCodec.decode(value.encode("ascii"), "ulid") == value


def test_ulid_codec_handles_nul_bearing_text_as_binary() -> None:
    """Treat a 16-byte NUL-bearing string as an already encoded identifier.

    Text inputs are detected without converting them to bytes first.
    """
    encoded = b"\x00" * 16
    binary_text = encoded.decode("ascii")

    assert BinaryCodec.encode(binary_text, "ulid") == encoded
    assert BinaryCodec.decode(binary_text, "ulid") == "0" * 26


def test_ulid_codec_accepts_objects_with_native_bytes() -> None:
    """Interop with ULID objects without requiring a particular package.

    The byte protocol keeps the integration optional and structurally typed.
    """
    value = bytes.fromhex("01563e3ab5d3d6764c61efb99302bd5b")

    assert BinaryCodec.encode(_UlidLike(value), "ulid") == value


def test_ulid_codec_rejects_uuid_objects_and_malformed_values() -> None:
    """Reject values that cannot represent a valid ULID.

    Error paths cover type mismatches and invalid encoded values.
    """
    with pytest.raises(TypeError, match="UUID object"):
        BinaryCodec.encode(uuid.uuid4(), "ulid")
    with pytest.raises(ValueError, match="26 characters"):
        BinaryCodec.encode("too-short", "ulid")
    with pytest.raises(ValueError, match="16 bytes"):
        BinaryCodec.encode("\x00" * 5, "ulid")
    with pytest.raises(ValueError, match="16 bytes"):
        BinaryCodec.decode("\x00" * 15, "ulid")
    with pytest.raises(ValueError, match="invalid character"):
        BinaryCodec.encode("01ARZ3NDEKTSV4RRFFQ69G5F!V", "ulid")
    with pytest.raises(ValueError, match="128 bits"):
        BinaryCodec.encode("8" + "0" * 25, "ulid")
    with pytest.raises(ValueError, match="16 bytes"):
        BinaryCodec.encode(b"\x00" * 15, "ulid")
    with pytest.raises(ValueError, match="16 bytes"):
        BinaryCodec.decode(b"\x00" * 15, "ulid")
    with pytest.raises(ValueError, match="16 bytes"):
        BinaryCodec.encode(_UlidLike(b"short"), "ulid")
    invalid = cast("BinaryCodecValue", 42)
    with pytest.raises(TypeError, match="ULID values"):
        BinaryCodec.encode(invalid, "ulid")


def test_binary_detection_handles_text_bytes_and_invalid_utf8() -> None:
    """Classify binary data using NUL and UTF-8 validity checks.

    Both Python text and byte inputs are accepted by the public predicate.
    """
    assert not BinaryCodec.is_binary(None)
    assert not BinaryCodec.is_binary(123)
    assert not BinaryCodec.is_binary(b"")
    assert not BinaryCodec.is_binary(b"hello")
    assert not BinaryCodec.is_binary("héllo")
    assert not BinaryCodec.is_binary("日本語")
    assert BinaryCodec.is_binary(b"hello\x00world")
    assert BinaryCodec.is_binary(b"\xff\xfe")
    assert BinaryCodec.is_binary("hello\x00world")
    assert BinaryCodec.is_binary("\ud800")
    assert BinaryCodec.is_binary(b"\xff\xfe")
