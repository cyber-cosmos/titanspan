"""Encode UUID and ULID identifiers using compact binary values.

The codec delegates UUID parsing to Python's standard library and applies the
ULID Crockford Base32 representation directly to its 128-bit value.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import ClassVar, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class _ByteConvertible(Protocol):
    """Describe identifiers that expose their binary representation.

    ULID libraries can integrate through Python's standard byte conversion.
    """

    def __bytes__(self) -> bytes:
        """Return the identifier's 16-byte representation.

        Returns:
            The binary identifier value.
        """
        ...


type BinaryCodecValue = UUID | str | bytes | _ByteConvertible | None
type _Encoder = Callable[[BinaryCodecValue], bytes | None]
type _Decoder = Callable[[str | bytes | None], str | None]
type _Codec = tuple[_Encoder, _Decoder]

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_VALUES = {
    character: value for value, character in enumerate(_ULID_ALPHABET)
}
_ULID_LENGTH = 26
_ULID_BITS = 128
_UUID_LENGTH = 16
_BINARY_UUID_ERROR = "A binary UUID must contain exactly 16 bytes."
_BINARY_ULID_ERROR = "A binary ULID must contain exactly 16 bytes."
_INVALID_ULID_CHARACTER_ERROR = "The ULID contains an invalid character."
_ULID_LENGTH_ERROR = "A ULID string must contain 26 characters."
_ULID_OVERFLOW_ERROR = "The ULID value exceeds 128 bits."
_UUID_NOT_ULID_ERROR = "A UUID object is not a ULID value."
_UUID_VALUE_TYPE_ERROR = "UUID values must be strings, UUIDs, or bytes."
_ULID_VALUE_TYPE_ERROR = "ULID values must be strings or bytes."


class BinaryCodec:
    """Convert UUID and ULID strings to compact binary representations.

    The built-in UUID codec uses :class:`uuid.UUID`; the ULID codec maps the
    standard 26-character Crockford Base32 form to its 16-byte integer value.
    Applications can register additional named encoders and decoders.

    Attributes:
        _custom_codecs: Class-scoped codec overrides and extensions.

    Notes:
        Registration is process-wide for this class, matching Laravel's
        static registry. Registry access is protected for concurrent threads.
    """

    _custom_codecs: ClassVar[dict[str, _Codec]] = {}
    _registry_lock: ClassVar[RLock] = RLock()

    @classmethod
    def register(cls, name: str, encode: _Encoder, decode: _Decoder) -> None:
        """Register or replace a named codec.

        Args:
            name: The format identifier accepted by ``encode`` and ``decode``.
            encode: Callback converting a supported value to binary bytes.
            decode: Callback converting text or bytes to a canonical string.

        Notes:
            A registration with an existing name replaces that codec,
            including built-in names such as ``uuid`` and ``ulid``.
        """
        with cls._registry_lock:
            cls._custom_codecs[name] = (encode, decode)

    @classmethod
    def encode(
        cls,
        value: BinaryCodecValue,
        format: str,
    ) -> bytes | None:
        """Encode a UUID or ULID value to its 16-byte representation.

        Args:
            value: A UUID object, canonical string, or binary byte sequence.
            format: Built-in ``uuid`` or ``ulid`` format, or a registered name.

        Returns:
            ``None`` for blank input; otherwise the encoded binary value.

        Raises:
            ValueError: If the format or identifier is invalid.

        Notes:
            Existing binary input is returned unchanged. Python uses ``bytes``
            for binary values rather than PHP's byte-bearing string type.
        """
        if cls._is_blank(value):
            return None

        with cls._registry_lock:
            codec = cls._custom_codecs.get(format)
        if codec is not None:
            return codec[0](value)

        if format == "uuid":
            return cls._encode_uuid(value)
        if format == "ulid":
            return cls._encode_ulid(value)
        message = f"Format [{format}] is invalid."
        raise ValueError(message)

    @classmethod
    def decode(
        cls,
        value: str | bytes | None,
        format: str,
    ) -> str | None:
        """Decode binary or textual UUID and ULID values to canonical text.

        Args:
            value: A canonical text identifier, binary bytes, or ``None``.
            format: Built-in ``uuid`` or ``ulid`` format, or a registered name.

        Returns:
            ``None`` for blank input; otherwise the canonical text identifier.

        Raises:
            ValueError: If the format or binary identifier is invalid.
        """
        if value is None:
            return None
        if cls._is_blank(value):
            return None

        with cls._registry_lock:
            codec = cls._custom_codecs.get(format)
        if codec is not None:
            return codec[1](value)

        if format == "uuid":
            return cls._decode_uuid(value)
        if format == "ulid":
            return cls._decode_ulid(value)
        message = f"Format [{format}] is invalid."
        raise ValueError(message)

    @classmethod
    def formats(cls) -> list[str]:
        """Return built-in and registered codec names without duplicates.

        Returns:
            A list beginning with the built-in UUID and ULID formats.
        """
        with cls._registry_lock:
            return list(dict.fromkeys(("uuid", "ulid", *cls._custom_codecs)))

    @classmethod
    def is_binary(cls, value: object) -> bool:
        """Determine whether bytes or text contain binary data.

        Args:
            value: The object to inspect.

        Returns:
            ``True`` for non-empty bytes containing NUL or invalid UTF-8, or
            strings containing NUL or unpaired surrogate code points.
        """
        if isinstance(value, bytes):
            if not value:
                return False
            if b"\x00" in value:
                return True
            try:
                value.decode("utf-8")
            except UnicodeDecodeError:
                return True
            return False

        if not isinstance(value, str) or value == "":
            return False
        if "\x00" in value:
            return True
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return True
        return False

    @classmethod
    def _encode_uuid(cls, value: BinaryCodecValue) -> bytes:
        """Encode a UUID string, object, or existing bytes.

        Args:
            value: A UUID-compatible value already checked as non-blank.

        Returns:
            The UUID's 16-byte network-order representation.

        Raises:
            ValueError: If the value is not a valid UUID or byte width.
        """
        if isinstance(value, UUID):
            return value.bytes
        if isinstance(value, bytes) and len(value) == _UUID_LENGTH:
            return UUID(bytes=value).bytes
        if isinstance(value, bytes) and cls.is_binary(value):
            raise ValueError(_BINARY_UUID_ERROR)
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if isinstance(value, str) and cls.is_binary(value):
            return value.encode("utf-8")
        if isinstance(value, _ByteConvertible) and not isinstance(value, str):
            raw_value = bytes(value)
            if len(raw_value) != _UUID_LENGTH:
                raise ValueError(_BINARY_UUID_ERROR)
            return UUID(bytes=raw_value).bytes
        if not isinstance(value, str):
            raise TypeError(_UUID_VALUE_TYPE_ERROR)
        return UUID(value).bytes

    @classmethod
    def _decode_uuid(cls, value: str | bytes) -> str:
        """Decode textual or binary UUID data to canonical lowercase text.

        Args:
            value: Text, valid UTF-8 bytes, or a 16-byte UUID value.

        Returns:
            Canonical lowercase UUID text.

        Raises:
            ValueError: If the text or binary length is invalid.
        """
        if isinstance(value, bytes) and len(value) == _UUID_LENGTH:
            return str(UUID(bytes=value))
        if isinstance(value, bytes) and cls.is_binary(value):
            raise ValueError(_BINARY_UUID_ERROR)
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if cls.is_binary(value):
            return str(UUID(bytes=value.encode("utf-8")))
        return str(UUID(value))

    @classmethod
    def _encode_ulid(cls, value: BinaryCodecValue) -> bytes:
        """Encode ULID text or preserve an existing binary value.

        Args:
            value: A canonical ULID string or existing binary bytes.

        Returns:
            The ULID's 16-byte big-endian value.

        Raises:
            ValueError: If the ULID alphabet, length, or value is invalid.
        """
        if isinstance(value, UUID):
            raise TypeError(_UUID_NOT_ULID_ERROR)
        if isinstance(value, bytes) and len(value) == _UUID_LENGTH:
            return value
        if isinstance(value, bytes) and cls.is_binary(value):
            raise ValueError(_BINARY_ULID_ERROR)
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if isinstance(value, _ByteConvertible) and not isinstance(value, str):
            raw_value = bytes(value)
            if len(raw_value) != _UUID_LENGTH:
                raise ValueError(_BINARY_ULID_ERROR)
            return raw_value
        if not isinstance(value, str):
            raise TypeError(_ULID_VALUE_TYPE_ERROR)
        if cls.is_binary(value):
            raw_value = value.encode("utf-8")
            if len(raw_value) != _UUID_LENGTH:
                raise ValueError(_BINARY_ULID_ERROR)
            return raw_value

        return cls._parse_ulid_text(value)

    @staticmethod
    def _parse_ulid_text(value: str) -> bytes:
        """Parse ULID text after checking its alphabet and numeric width.

        Args:
            value: A 26-character Crockford Base32 representation.

        Returns:
            The 16-byte big-endian identifier.

        Raises:
            ValueError: If the identifier has invalid characters or width.
        """
        normalized = value.upper()
        if len(normalized) != _ULID_LENGTH:
            raise ValueError(_ULID_LENGTH_ERROR)
        number = 0
        for character in normalized:
            try:
                digit = _ULID_VALUES[character]
            except KeyError as exc:
                raise ValueError(_INVALID_ULID_CHARACTER_ERROR) from exc
            number = (number << 5) | digit
        if number >= 1 << _ULID_BITS:
            raise ValueError(_ULID_OVERFLOW_ERROR)
        return number.to_bytes(_UUID_LENGTH, "big")

    @classmethod
    def _decode_ulid(cls, value: str | bytes) -> str:
        """Decode textual or 16-byte ULID data to canonical uppercase text.

        Args:
            value: A ULID string or binary ULID value.

        Returns:
            Canonical uppercase Crockford Base32 text.

        Raises:
            ValueError: If the text or byte length is invalid.
        """
        if isinstance(value, bytes) and len(value) == _UUID_LENGTH:
            number = int.from_bytes(value, "big")
            return cls._encode_ulid_text(number)
        if isinstance(value, bytes) and cls.is_binary(value):
            raise ValueError(_BINARY_ULID_ERROR)
        if isinstance(value, bytes):
            value = value.decode("ascii")
        if cls.is_binary(value):
            raw_value = value.encode("utf-8")
            if len(raw_value) != _UUID_LENGTH:
                raise ValueError(_BINARY_ULID_ERROR)
            return cls._encode_ulid_text(int.from_bytes(raw_value, "big"))
        encoded = cls._encode_ulid(value)
        return cls._encode_ulid_text(int.from_bytes(encoded, "big"))

    @staticmethod
    def _encode_ulid_text(number: int) -> str:
        """Convert a validated 128-bit integer into 26 Base32 characters.

        Args:
            number: The unsigned integer represented by 16 bytes.

        Returns:
            The canonical uppercase ULID string.
        """
        characters = ["0"] * _ULID_LENGTH
        for index in range(_ULID_LENGTH - 1, -1, -1):
            characters[index] = _ULID_ALPHABET[number & 31]
            number >>= 5
        return "".join(characters)

    @staticmethod
    def _is_blank(value: object) -> bool:
        """Apply Laravel's blank semantics to supported codec input values.

        Args:
            value: A UUID, string, byte sequence, or ``None``.

        Returns:
            ``True`` for ``None`` and empty or whitespace-only text/bytes.
        """
        return value is None or (
            isinstance(value, (str, bytes)) and not value.strip()
        )

    # Preserve Laravel's public method spelling for compatibility.
    isBinary = is_binary


__all__ = ["BinaryCodec", "BinaryCodecValue"]
