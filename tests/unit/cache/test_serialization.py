"""Verify safe cache serialization bounds and executable-object rejection.

The same JSON representation is used by local memory and Redis stores.
"""

import math

import pytest

from titanspan.cache._serialization import JSONSerializer
from titanspan.cache.exceptions import CacheSerializationError

pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        0,
        1.5,
        "text",
        [],
        {"items": ["one", 2]},
    ],
)
def test_safe_values_round_trip_without_type_reconstruction(
    value: object,
) -> None:
    """Round-trip built-in JSON types without invoking object hooks.
    """  # fmt: skip
    serializer = JSONSerializer(1024)

    assert serializer.decode(serializer.encode(value)) == value


@pytest.mark.parametrize(
    "value",
    [
        object(),
        b"arbitrary bytes",
        {1: "numeric mapping key"},
        math.nan,
        math.inf,
    ],
)
def test_unsafe_python_values_are_rejected(value: object) -> None:
    """Reject object and non-standard JSON values before storage.
    """  # fmt: skip
    with pytest.raises(CacheSerializationError):
        JSONSerializer(1024).encode(value)


def test_recursive_values_are_rejected() -> None:
    """Prevent cycles from causing unbounded traversal or encoding.
    """  # fmt: skip
    value: list[object] = []
    value.append(value)

    with pytest.raises(CacheSerializationError, match="recursive"):
        JSONSerializer(1024).encode(value)


def test_depth_node_and_payload_limits_are_enforced() -> None:
    """Bound serialization work and payload memory use.
    """  # fmt: skip
    deeply_nested: object = "value"
    for _ in range(66):
        deeply_nested = [deeply_nested]

    with pytest.raises(CacheSerializationError, match="structure limit"):
        JSONSerializer(1024).encode(deeply_nested)
    with pytest.raises(CacheSerializationError, match="size limit"):
        JSONSerializer(3).encode("long")
    with pytest.raises(CacheSerializationError, match="size limit"):
        JSONSerializer(2).decode(b'"long"')


@pytest.mark.parametrize("payload", [b"NaN", b"Infinity", b"{", b"\xff"])
def test_malformed_or_nonstandard_json_bytes_are_rejected(
    payload: bytes,
) -> None:
    """Reject corrupt backend payloads without evaluating object types.
    """  # fmt: skip
    with pytest.raises(CacheSerializationError):
        JSONSerializer(1024).decode(payload)
