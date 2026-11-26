"""Parse and validate password hashing settings from native Config.

Applications may increase work factors without selecting weaker defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from titanspan.hashing.exceptions import HashingConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

_CONFIGURATION_ERROR = "The hashing configuration is invalid."
_ARGON2_DEFAULT_TIME_COST = 3
_ARGON2_DEFAULT_MEMORY_COST = 65_536
_ARGON2_DEFAULT_PARALLELISM = 4
_ARGON2_DEFAULT_HASH_LENGTH = 32
_ARGON2_DEFAULT_SALT_LENGTH = 16
_BCRYPT_DEFAULT_ROUNDS = 12
_BCRYPT_DEFAULT_PREFIX = "2b"
_BCRYPT_MAX_ROUNDS = 31


def _section(
    values: Mapping[object, object],
    key: str,
) -> Mapping[object, object]:
    """Return one nested configuration mapping or an empty default.

    Args:
        values: Untrusted configuration values.
        key: Section name to read.

    Returns:
        The selected nested mapping.

    Raises:
        HashingConfigurationError: If the section has another shape.
    """
    value = values.get(key, {})
    if not isinstance(value, Mapping):
        raise HashingConfigurationError(_CONFIGURATION_ERROR)
    return cast("Mapping[object, object]", value)


def _positive_integer(
    values: Mapping[object, object],
    key: str,
    default: int,
    minimum: int,
) -> int:
    """Read one integer work factor without accepting boolean values.

    Args:
        values: Configuration section containing the factor.
        key: Work-factor setting name.
        default: Secure dependency-provided default.
        minimum: Smallest permitted value.

    Returns:
        A validated integer factor.

    Raises:
        HashingConfigurationError: If the setting is invalid or below default.
    """
    value = values.get(key, default)
    if type(value) is not int or value < minimum:
        raise HashingConfigurationError(_CONFIGURATION_ERROR)
    return value


@dataclass(frozen=True, slots=True)
class Argon2Configuration:
    """Hold Argon2id work factors with secure minimum values.

    Attributes:
        time_cost: Number of computation iterations.
        memory_cost: Memory in kibibytes.
        parallelism: Number of parallel lanes.
        hash_length: Output length in bytes.
        salt_length: Random salt length in bytes.
    """

    time_cost: int = _ARGON2_DEFAULT_TIME_COST
    memory_cost: int = _ARGON2_DEFAULT_MEMORY_COST
    parallelism: int = _ARGON2_DEFAULT_PARALLELISM
    hash_length: int = _ARGON2_DEFAULT_HASH_LENGTH
    salt_length: int = _ARGON2_DEFAULT_SALT_LENGTH

    def __post_init__(self) -> None:
        """Reject settings outside supported secure algorithm boundaries.

        Applications may raise the configured work factors.
        """
        values = (
            (self.time_cost, _ARGON2_DEFAULT_TIME_COST),
            (self.memory_cost, _ARGON2_DEFAULT_MEMORY_COST),
            (self.parallelism, _ARGON2_DEFAULT_PARALLELISM),
            (self.hash_length, _ARGON2_DEFAULT_HASH_LENGTH),
            (self.salt_length, _ARGON2_DEFAULT_SALT_LENGTH),
        )
        for value, minimum in values:
            if type(value) is not int or value < minimum:
                raise HashingConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def from_values(
        cls,
        values: Mapping[object, object],
    ) -> Argon2Configuration:
        """Build settings from one untrusted configuration section.

        Args:
            values: Mapping with optional Argon2 work-factor overrides.

        Returns:
            A validated immutable Argon2 configuration.
        """
        return cls(
            time_cost=_positive_integer(
                values,
                "time_cost",
                _ARGON2_DEFAULT_TIME_COST,
                _ARGON2_DEFAULT_TIME_COST,
            ),
            memory_cost=_positive_integer(
                values,
                "memory_cost",
                _ARGON2_DEFAULT_MEMORY_COST,
                _ARGON2_DEFAULT_MEMORY_COST,
            ),
            parallelism=_positive_integer(
                values,
                "parallelism",
                _ARGON2_DEFAULT_PARALLELISM,
                _ARGON2_DEFAULT_PARALLELISM,
            ),
            hash_length=_positive_integer(
                values,
                "hash_length",
                _ARGON2_DEFAULT_HASH_LENGTH,
                _ARGON2_DEFAULT_HASH_LENGTH,
            ),
            salt_length=_positive_integer(
                values,
                "salt_length",
                _ARGON2_DEFAULT_SALT_LENGTH,
                _ARGON2_DEFAULT_SALT_LENGTH,
            ),
        )


@dataclass(frozen=True, slots=True)
class BcryptConfiguration:
    """Hold Bcrypt creation settings without weakening its default cost.

    Attributes:
        rounds: Bcrypt work factor used for new hashes.
        prefix: Encoded Bcrypt prefix used for new hashes.
    """

    rounds: int = _BCRYPT_DEFAULT_ROUNDS
    prefix: Literal["2a", "2b"] = "2b"

    def __post_init__(self) -> None:
        """Reject unsupported prefixes and costs below the secure default.

        New hashes use only prefixes supported by the selected backend.
        """
        if (
            type(self.rounds) is not int
            or self.rounds < _BCRYPT_DEFAULT_ROUNDS
            or self.rounds > _BCRYPT_MAX_ROUNDS
            or self.prefix not in ("2a", "2b")
        ):
            raise HashingConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def from_values(
        cls,
        values: Mapping[object, object],
    ) -> BcryptConfiguration:
        """Build settings from one untrusted configuration section.

        Args:
            values: Mapping with optional Bcrypt work-factor overrides.

        Returns:
            A validated immutable Bcrypt configuration.
        """
        rounds = _positive_integer(
            values,
            "rounds",
            _BCRYPT_DEFAULT_ROUNDS,
            _BCRYPT_DEFAULT_ROUNDS,
        )
        prefix = values.get("prefix", _BCRYPT_DEFAULT_PREFIX)
        if prefix not in ("2a", "2b"):
            raise HashingConfigurationError(_CONFIGURATION_ERROR)
        return cls(rounds=rounds, prefix=prefix)


@dataclass(frozen=True, slots=True)
class HashingConfiguration:
    """Select the current algorithm and preserve supported legacy settings.

    Attributes:
        driver: Algorithm name for newly generated hashes.
        argon2id: Argon2id settings used for new and replacement hashes.
        bcrypt: Bcrypt settings used for new and replacement hashes.
    """

    driver: str = "argon2id"
    argon2id: Argon2Configuration = Argon2Configuration()
    bcrypt: BcryptConfiguration = BcryptConfiguration()

    def __post_init__(self) -> None:
        """Validate the configured driver identifier.

        The manager resolves the name from built-in or registered factories.
        """
        if not self.driver or not self.driver.strip():
            raise HashingConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
    ) -> HashingConfiguration:
        """Read and validate the application's canonical hashing settings.

        Args:
            repository: Application-owned configuration repository.

        Returns:
            Immutable hashing settings.

        Raises:
            HashingConfigurationError: If settings have invalid values.
        """
        raw = repository.get("hashing", {})
        if not isinstance(raw, Mapping):
            raise HashingConfigurationError(_CONFIGURATION_ERROR)
        values = cast("Mapping[object, object]", raw)
        driver = values.get("driver", "argon2id")
        if not isinstance(driver, str):
            raise HashingConfigurationError(_CONFIGURATION_ERROR)
        return cls(
            driver=driver,
            argon2id=Argon2Configuration.from_values(
                _section(values, "argon2id"),
            ),
            bcrypt=BcryptConfiguration.from_values(
                _section(values, "bcrypt"),
            ),
        )


__all__ = [
    "Argon2Configuration",
    "BcryptConfiguration",
    "HashingConfiguration",
]
