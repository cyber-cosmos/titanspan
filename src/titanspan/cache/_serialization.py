"""Encode cache values in a bounded, non-executable JSON format.

This serializer creates consistent bytes for memory and remote stores and
rejects object reconstruction protocols such as pickle.
"""

from __future__ import annotations

import json
import math
from typing import cast

from titanspan.cache.exceptions import CacheSerializationError

_MAX_DEPTH = 64
_MAX_NODES = 100_000


class JSONSerializer:
    """Encode JSON values without accepting arbitrary Python objects.

    The accepted values are ``None``, booleans, integers, finite floats,
    strings, lists, and string-keyed dictionaries. Decoding never imports or
    constructs application classes.
    """

    def __init__(self, max_bytes: int) -> None:
        """Set the maximum encoded value size.

        Args:
            max_bytes: Positive byte limit applied to every write.
        """
        self._max_bytes = max_bytes

    def encode(self, value: object) -> bytes:
        """Validate and encode one portable cache value.

        Args:
            value: JSON-safe value selected by the application.

        Returns:
            UTF-8 JSON bytes with stable separators.

        Raises:
            CacheSerializationError: If the value is unsupported or oversized.
        """
        _validate_value(value)
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as error:
            msg = "The cache value cannot be encoded as JSON."
            raise CacheSerializationError(msg) from error
        if len(payload) > self._max_bytes:
            msg = "The encoded cache value exceeds its configured size limit."
            raise CacheSerializationError(msg)
        return payload

    def decode(self, payload: bytes) -> object:
        """Decode JSON bytes without constructing executable objects.

        Args:
            payload: Bytes returned by a cache backend.

        Returns:
            A JSON value composed only of safe built-in types.

        Raises:
            CacheSerializationError: If stored bytes are invalid or oversized.
        """
        if len(payload) > self._max_bytes:
            msg = "The stored cache value exceeds its configured size limit."
            raise CacheSerializationError(msg)
        try:
            value = json.loads(
                payload.decode("utf-8"),
                parse_constant=_reject_non_finite,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            msg = "The stored cache value is not valid safe JSON."
            raise CacheSerializationError(msg) from error
        _validate_value(value)
        return value

    _max_bytes: int


def _validate_value(value: object) -> None:
    """Bound the shape and type of values before JSON processing.

    Args:
        value: Value being checked at the serialization boundary.

    Raises:
        CacheSerializationError: If depth, node count, or value types exceed
            the portable cache format.
    """
    pending: list[tuple[object, int]] = [(value, 0)]
    visited: set[int] = set()
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_NODES or depth > _MAX_DEPTH:
            msg = "The cache value exceeds the safe structure limit."
            raise CacheSerializationError(msg)
        value_type = type(current)
        if current is None or value_type in (str, bool, int):
            continue
        if value_type is float:
            if not math.isfinite(cast("float", current)):
                msg = "Cache values must not contain non-finite floats."
                raise CacheSerializationError(msg)
            continue
        if value_type in (list, dict):
            identity = id(current)
            if identity in visited:
                msg = "Cache values must not contain recursive containers."
                raise CacheSerializationError(msg)
            visited.add(identity)
            if value_type is list:
                items = cast("list[object]", current)
                pending.extend((item, depth + 1) for item in items)
                continue
            mapping = cast("dict[object, object]", current)
            if not all(type(key) is str for key in mapping):
                msg = "Cache mapping keys must be strings."
                raise CacheSerializationError(msg)
            pending.extend((item, depth + 1) for item in mapping.values())
            continue
        msg = "Cache values must use the supported JSON data types."
        raise CacheSerializationError(msg)


def _reject_non_finite(value: str) -> None:
    """Reject JavaScript numeric constants accepted by Python's JSON parser.

    Args:
        value: Non-standard numeric token reported by ``json``.

    Raises:
        ValueError: Always, because the token is not valid safe JSON.
    """
    msg = f"Unsupported JSON numeric constant: {value}."
    raise ValueError(msg)


__all__ = ["JSONSerializer"]
