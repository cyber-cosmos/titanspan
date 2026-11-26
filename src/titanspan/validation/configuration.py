"""Load safe application-level Validation defaults from Config.

Per-call options override the immutable settings captured by the provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from titanspan.validation.exceptions import ValidationConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

_INVALID_CONFIGURATION_ERROR = (
    "The [validation] configuration must be a strict boolean mapping."
)


class ValidationConfiguration(BaseModel):
    """Define shared coercion and object-extraction defaults.

    Attributes:
        strict: Whether Pydantic should reject coercible input by default.
        from_attributes: Whether Python object attributes may satisfy schemas.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    strict: bool = False
    from_attributes: bool = False

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
    ) -> ValidationConfiguration:
        """Build defaults from the canonical ``validation`` namespace.

        Args:
            repository: Application-owned configuration repository.

        Returns:
            Immutable settings captured during provider construction.

        Raises:
            ValidationConfigurationError: If the namespace is malformed.
        """
        values = repository.get("validation", {})
        if not isinstance(values, Mapping):
            raise ValidationConfigurationError(_INVALID_CONFIGURATION_ERROR)
        try:
            return cls.model_validate(values, strict=True)
        except ValidationError:
            raise ValidationConfigurationError(
                _INVALID_CONFIGURATION_ERROR
            ) from None


__all__ = ["ValidationConfiguration"]
