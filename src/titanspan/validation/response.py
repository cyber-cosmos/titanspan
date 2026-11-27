"""Define the public body used for safe HTTP validation failures.

Pydantic supplies the schema while Foundation supplies the HTTP response.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from titanspan.contracts.http.types import JsonValue


class ValidationErrorBody(BaseModel):
    """Describe the stable public shape of a validation error response.

    Dynamic field paths map to safe messages. The model stores no rejected
    request values or backend exception details.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    DEFAULT_DETAIL: ClassVar[str] = "Request validation failed."

    detail: str
    errors: dict[str, list[str]]

    def to_json(self) -> JsonValue:
        """Return the validated body through the native JSON value contract.

        Returns:
            A JSON object with the detail and safe field messages.
        """
        errors: dict[str, JsonValue] = {
            field: list(messages) for field, messages in self.errors.items()
        }
        return {"detail": self.detail, "errors": errors}


__all__ = ["ValidationErrorBody"]
