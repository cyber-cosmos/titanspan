# Binary codecs

`BinaryCodec` encodes and decodes UUID and ULID identifiers using the
`uuid.UUID` type and Python byte values. It follows Laravel Support's
`Illuminate\Support\BinaryCodec` API, including the original `isBinary`
spelling and Titanspan's `is_binary` alias.

```python
from uuid import UUID

from titanspan.support import BinaryCodec

identifier = UUID("550e8400-e29b-41d4-a716-446655440000")
encoded = BinaryCodec.encode(identifier, "uuid")

assert encoded == identifier.bytes
assert BinaryCodec.decode(encoded, "uuid") == str(identifier)
```

ULID text uses the canonical 26-character Crockford Base32 form. Binary
identifiers use exactly 16 bytes. Python objects that expose a `__bytes__`
method can be supplied to the ULID encoder, which allows interoperability
with ULID packages without making one a Titanspan runtime dependency.

```python
value = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
encoded = BinaryCodec.encode(value, "ulid")

assert BinaryCodec.decode(encoded, "ulid") == value
```

Custom formats can be registered and can replace a built-in format:

```python
def encode_hex(value: object) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Hex codec expects text.")
    return bytes.fromhex(value)


def decode_hex(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.hex()
    return bytes.fromhex(value).hex()


BinaryCodec.register(
    "hex",
    encode_hex,
    decode_hex,
)
```

The registry is process-wide and protected against concurrent thread access.
Registration changes are intended for application setup and tests. Avoid
changing codecs while requests or workers depend on stable conversion rules.

`None`, empty values, and whitespace-only strings or bytes return `None`.
Unsupported formats and malformed identifiers raise `ValueError`. For
`bytes` inputs, exactly 16 bytes are treated as binary regardless of whether
those bytes also happen to be valid UTF-8. This explicit type distinction
avoids ambiguity present in byte-bearing string APIs.

See the [method-level compatibility inventory](/compatibility/laravel-support)
for the pinned upstream source, test evidence, and Python-specific differences.
