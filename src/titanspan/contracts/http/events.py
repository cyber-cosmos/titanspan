"""Define the native Server-Sent Event value and its wire encoding.

Callers rely on native contracts, not concrete backend types.
"""

import json
from dataclasses import dataclass

from titanspan.contracts.http.types import JsonValue

_NUL_EVENT_ID_ERROR = "Event identifiers must not contain NUL."
_NEGATIVE_RETRY_ERROR = "Event retry must be non-negative."
_SSE_CARRIAGE_RETURN_ERROR = "SSE metadata must not contain carriage returns."


@dataclass(frozen=True, slots=True)
class ServerSentEvent:
    """Describe one event with optional standard SSE metadata fields.

    Callers rely on native contracts, not concrete backend types.
    """

    data: JsonValue
    event: str | None = None
    identifier: str | None = None
    retry: int | None = None

    def encode(self) -> bytes:
        """Encode the event using UTF-8 and the SSE line grammar.

        Returns:
            One complete event ending with a blank line.

        Raises:
            ValueError: If metadata contains invalid line controls or a
                negative retry delay.
        """
        lines: list[str] = []
        if self.event is not None:
            lines.extend(_field_lines("event", self.event))
        if self.identifier is not None:
            if "\x00" in self.identifier:
                raise ValueError(_NUL_EVENT_ID_ERROR)
            lines.extend(_field_lines("id", self.identifier))
        if self.retry is not None:
            if self.retry < 0:
                raise ValueError(_NEGATIVE_RETRY_ERROR)
            lines.append(f"retry: {self.retry}")
        data = (
            self.data
            if isinstance(self.data, str)
            else json.dumps(self.data, separators=(",", ":"))
        )
        lines.extend(f"data: {line}" for line in data.splitlines() or [""])
        return ("\n".join(lines) + "\n\n").encode("utf-8")


def _field_lines(name: str, value: str) -> list[str]:
    """Return safe SSE metadata lines without permitting field injection.

    Args:
        name: SSE field name.
        value: Metadata value.

    Returns:
        One line per newline-separated metadata value.

    Raises:
        ValueError: If the metadata contains carriage returns.
    """
    if "\r" in value:
        raise ValueError(_SSE_CARRIAGE_RETURN_ERROR)
    return [f"{name}: {line}" for line in value.split("\n")]


__all__ = ["ServerSentEvent"]
