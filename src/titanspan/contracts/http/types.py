"""Define backend-independent HTTP value types.

These aliases describe JSON-compatible values and request payloads using
standard Python containers only.
"""

from collections.abc import Mapping, Sequence

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type RequestPayload = Mapping[str, object] | str | bytes | None
type QueryParameterValue = (
    str | int | float | bool | None | Sequence[str | int | float | bool]
)
type QueryParameters = Mapping[str, QueryParameterValue]

__all__ = [
    "JsonValue",
    "QueryParameterValue",
    "QueryParameters",
    "RequestPayload",
]
