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
_BCRYPT_OPERATIONAL_MAX_ROUNDS = 16
_DEFAULT_HASHING_CONCURRENCY = 2
_MAX_HASHING_CONCURRENCY = 8
_ARGON2_MAX_TIME_COST = 10
_ARGON2_MAX_MEMORY_COST_KIB = 1_048_576
_ARGON2_MAX_PARALLELISM = 16
_ARGON2_MAX_OUTPUT_LENGTH = 128
_ARGON2_MAX_SALT_LENGTH = 128
_MAX_ENCODED_HASH_LENGTH = 2_048
_MAX_PASSWORD_BYTES = 1_048_576


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


def _argon2_encoded_length(settings: Argon2Configuration) -> int:
    """Estimate the backend's standard PHC length from configured sizes.

    Args:
        settings: Generation parameters for one Argon2 hash.

    Returns:
        A conservative character count used to validate configured limits.
    """
    header = (
        f"$argon2id$v=19$m={settings.memory_cost},"
        f"t={settings.time_cost},p={settings.parallelism}$"
    )
    salt = (settings.salt_length * 8 + 5) // 6
    digest = (settings.hash_length * 8 + 5) // 6
    return len(header) + salt + 1 + digest


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
            (
                self.time_cost,
                _ARGON2_DEFAULT_TIME_COST,
                _ARGON2_MAX_TIME_COST,
            ),
            (
                self.memory_cost,
                _ARGON2_DEFAULT_MEMORY_COST,
                _ARGON2_MAX_MEMORY_COST_KIB,
            ),
            (
                self.parallelism,
                _ARGON2_DEFAULT_PARALLELISM,
                _ARGON2_MAX_PARALLELISM,
            ),
            (
                self.hash_length,
                _ARGON2_DEFAULT_HASH_LENGTH,
                _ARGON2_MAX_OUTPUT_LENGTH,
            ),
            (
                self.salt_length,
                _ARGON2_DEFAULT_SALT_LENGTH,
                _ARGON2_MAX_SALT_LENGTH,
            ),
        )
        for value, minimum, maximum in values:
            if type(value) is not int or value < minimum or value > maximum:
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
            or self.rounds > _BCRYPT_OPERATIONAL_MAX_ROUNDS
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
class HashVerificationLimits:
    """Bound work and input sizes accepted during hash verification.

    Applications may lower these limits. Hard ceilings protect verification
    from encoded hashes with unreasonable computational costs.

    Attributes:
        max_argon2_memory_cost_kib: Maximum permitted Argon2 memory.
        max_argon2_time_cost: Maximum permitted Argon2 iterations.
        max_argon2_parallelism: Maximum permitted Argon2 lanes.
        max_argon2_hash_length: Maximum Argon2 digest size in bytes.
        max_argon2_salt_length: Maximum Argon2 salt size in bytes.
        max_bcrypt_rounds: Maximum permitted Bcrypt work factor.
        max_encoded_hash_length: Maximum encoded hash length in characters.
        max_password_bytes: Maximum UTF-8 password size.
    """

    max_argon2_memory_cost_kib: int = 262_144
    max_argon2_time_cost: int = 6
    max_argon2_parallelism: int = 8
    max_argon2_hash_length: int = 128
    max_argon2_salt_length: int = 128
    max_bcrypt_rounds: int = _BCRYPT_OPERATIONAL_MAX_ROUNDS
    max_encoded_hash_length: int = _MAX_ENCODED_HASH_LENGTH
    max_password_bytes: int = _MAX_PASSWORD_BYTES

    def __post_init__(self) -> None:
        """Reject limits above documented operational ceilings.

        Lower values remain valid for resource-constrained applications.
        """
        limits = (
            (
                self.max_argon2_memory_cost_kib,
                _ARGON2_DEFAULT_MEMORY_COST,
                _ARGON2_MAX_MEMORY_COST_KIB,
            ),
            (
                self.max_argon2_time_cost,
                _ARGON2_DEFAULT_TIME_COST,
                _ARGON2_MAX_TIME_COST,
            ),
            (
                self.max_argon2_parallelism,
                _ARGON2_DEFAULT_PARALLELISM,
                _ARGON2_MAX_PARALLELISM,
            ),
            (
                self.max_argon2_hash_length,
                _ARGON2_DEFAULT_HASH_LENGTH,
                _ARGON2_MAX_OUTPUT_LENGTH,
            ),
            (
                self.max_argon2_salt_length,
                _ARGON2_DEFAULT_SALT_LENGTH,
                _ARGON2_MAX_SALT_LENGTH,
            ),
            (self.max_bcrypt_rounds, _BCRYPT_DEFAULT_ROUNDS, 16),
            (self.max_encoded_hash_length, 60, _MAX_ENCODED_HASH_LENGTH),
            (self.max_password_bytes, 1, _MAX_PASSWORD_BYTES),
        )
        for value, minimum, maximum in limits:
            if type(value) is not int or value < minimum or value > maximum:
                raise HashingConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def from_values(
        cls,
        values: Mapping[object, object],
    ) -> HashVerificationLimits:
        """Read bounded verification limits from one configuration mapping.

        Args:
            values: Untrusted limit values from application configuration.

        Returns:
            Validated limits within the fixed operational ceilings.
        """
        defaults = cls()
        keys = (
            "max_argon2_memory_cost_kib",
            "max_argon2_time_cost",
            "max_argon2_parallelism",
            "max_argon2_hash_length",
            "max_argon2_salt_length",
            "max_bcrypt_rounds",
            "max_encoded_hash_length",
            "max_password_bytes",
        )
        return cls(
            **{
                key: _positive_integer(
                    values,
                    key,
                    getattr(defaults, key),
                    1,
                )
                for key in keys
            },
        )


@dataclass(frozen=True, slots=True)
class HashingConfiguration:
    """Select the current algorithm and preserve supported legacy settings.

    Attributes:
        driver: Algorithm name for newly generated hashes.
        argon2id: Argon2id settings used for new and replacement hashes.
        bcrypt: Bcrypt settings used for new and replacement hashes.
        max_concurrent_operations: Per-application password work budget.
    """

    driver: str = "argon2id"
    argon2id: Argon2Configuration = Argon2Configuration()
    bcrypt: BcryptConfiguration = BcryptConfiguration()
    verification_limits: HashVerificationLimits = HashVerificationLimits()
    max_concurrent_operations: int = _DEFAULT_HASHING_CONCURRENCY

    def __post_init__(self) -> None:
        """Validate the selected driver and operational hashing limits.

        Work-factor settings must fit the accepted verification policy.
        """
        if not self.driver or not self.driver.strip():
            raise HashingConfigurationError(_CONFIGURATION_ERROR)
        if (
            type(self.max_concurrent_operations) is not int
            or not 1
            <= self.max_concurrent_operations
            <= _MAX_HASHING_CONCURRENCY
        ):
            raise HashingConfigurationError(_CONFIGURATION_ERROR)
        limits = self.verification_limits
        argon2_exceeds_policy = (
            self.argon2id.memory_cost > limits.max_argon2_memory_cost_kib
            or self.argon2id.time_cost > limits.max_argon2_time_cost
            or self.argon2id.parallelism > limits.max_argon2_parallelism
            or self.argon2id.hash_length > limits.max_argon2_hash_length
            or self.argon2id.salt_length > limits.max_argon2_salt_length
            or _argon2_encoded_length(self.argon2id)
            > limits.max_encoded_hash_length
        )
        bcrypt_exceeds_policy = self.bcrypt.rounds > limits.max_bcrypt_rounds
        if (self.driver == "argon2id" and argon2_exceeds_policy) or (
            self.driver == "bcrypt" and bcrypt_exceeds_policy
        ):
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
            verification_limits=HashVerificationLimits.from_values(
                _section(values, "verification_limits"),
            ),
            max_concurrent_operations=_positive_integer(
                _section(values, "execution"),
                "max_concurrent_operations",
                _DEFAULT_HASHING_CONCURRENCY,
                1,
            ),
        )


__all__ = [
    "Argon2Configuration",
    "BcryptConfiguration",
    "HashVerificationLimits",
    "HashingConfiguration",
]
