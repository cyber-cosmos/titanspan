"""Verify Hashing configuration parsing and secure parameter boundaries.

Configuration is read from the same native repository used by other services.
"""

from collections.abc import Callable

import pytest

from titanspan.config import Repository
from titanspan.hashing import (
    Argon2Configuration,
    BcryptConfiguration,
    HashingConfiguration,
    HashVerificationLimits,
)
from titanspan.hashing.exceptions import HashingConfigurationError

pytestmark = pytest.mark.unit
_SECURE_ARGON2_MEMORY_KIB = 65_536
_SECURE_BCRYPT_ROUNDS = 12
_BCRYPT_OPERATIONAL_MAX_ROUNDS = 16
_RAISED_ARGON2_TIME_COST = 7
_CONFIGURED_HASHING_CONCURRENCY = 3


def test_configuration_reads_selected_driver_and_work_factors() -> None:
    """Use canonical Config values for selected password hashing settings.

    Unspecified secure work factors retain their backend defaults.
    """
    repository = Repository(
        {
            "hashing": {
                "driver": "bcrypt",
                "bcrypt": {"rounds": _SECURE_BCRYPT_ROUNDS + 1},
            },
        },
    )

    configuration = HashingConfiguration.from_repository(repository)

    assert configuration.driver == "bcrypt"
    assert configuration.bcrypt.rounds == _SECURE_BCRYPT_ROUNDS + 1
    assert configuration.argon2id.memory_cost == _SECURE_ARGON2_MEMORY_KIB


def test_configuration_reads_application_hashing_execution_budget() -> None:
    """Read the per-application concurrent operation limit from Config.

    The default keeps expensive work bounded without application settings.
    """
    repository = Repository(
        {
            "hashing": {
                "execution": {
                    "max_concurrent_operations": (
                        _CONFIGURED_HASHING_CONCURRENCY
                    ),
                },
            },
        },
    )

    configuration = HashingConfiguration.from_repository(repository)

    assert (
        configuration.max_concurrent_operations
        == _CONFIGURED_HASHING_CONCURRENCY
    )


@pytest.mark.parametrize("value", [0, 9, True, 1.5])
def test_configuration_rejects_invalid_hashing_execution_budget(
    value: object,
) -> None:
    """Reject non-integer and excessive hashing concurrency limits.

    Application configuration cannot create an unbounded worker policy.
    """
    repository = Repository(
        {
            "hashing": {
                "execution": {"max_concurrent_operations": value},
            },
        },
    )

    with pytest.raises(HashingConfigurationError):
        HashingConfiguration.from_repository(repository)


@pytest.mark.parametrize(
    "configuration_factory",
    [
        lambda: Argon2Configuration(time_cost=2),
        lambda: Argon2Configuration(memory_cost=32_768),
        lambda: BcryptConfiguration(rounds=11),
        lambda: BcryptConfiguration(rounds=32),
    ],
)
def test_configuration_rejects_weaker_or_unsupported_settings(
    configuration_factory: Callable[[], object],
) -> None:
    """Reject lowered factors and unsupported Bcrypt creation prefixes.

    The component does not silently reduce its configured security baseline.
    """
    with pytest.raises(HashingConfigurationError):
        configuration_factory()


def test_configuration_accepts_bcrypt_operational_maximum_rounds() -> None:
    """Accept the highest Bcrypt work factor allowed by framework policy.

    Lower costs remain available only for recognized legacy verification.
    """
    assert BcryptConfiguration(
        rounds=_BCRYPT_OPERATIONAL_MAX_ROUNDS,
    ).rounds == (_BCRYPT_OPERATIONAL_MAX_ROUNDS)


def test_configuration_rejects_excessive_verification_work() -> None:
    """Reject verification policy values beyond documented hard ceilings.

    Configuration cannot opt into algorithm-valid but unsafe work factors.
    """
    with pytest.raises(HashingConfigurationError):
        BcryptConfiguration(rounds=_BCRYPT_OPERATIONAL_MAX_ROUNDS + 1)
    with pytest.raises(HashingConfigurationError):
        Argon2Configuration(time_cost=11)
    with pytest.raises(HashingConfigurationError):
        HashVerificationLimits(max_argon2_memory_cost_kib=1_048_577)


def test_generation_settings_must_fit_verification_limits() -> None:
    """Ensure generated hashes remain verifiable under the same policy.

    Applications must raise the verification ceiling with stronger settings.
    """
    with pytest.raises(HashingConfigurationError):
        HashingConfiguration(
            argon2id=Argon2Configuration(
                time_cost=_RAISED_ARGON2_TIME_COST,
            ),
        )

    configuration = HashingConfiguration(
        argon2id=Argon2Configuration(
            time_cost=_RAISED_ARGON2_TIME_COST,
        ),
        verification_limits=HashVerificationLimits(
            max_argon2_time_cost=_RAISED_ARGON2_TIME_COST,
        ),
    )
    assert configuration.argon2id.time_cost == _RAISED_ARGON2_TIME_COST


@pytest.mark.parametrize(
    "values",
    [
        {"hashing": None},
        {"hashing": {"driver": 12}},
        {"hashing": {"argon2id": []}},
        {"hashing": {"argon2id": {"time_cost": True}}},
        {"hashing": {"bcrypt": {"rounds": 11}}},
        {"hashing": {"bcrypt": {"prefix": "2y"}}},
        {"hashing": {"verification_limits": []}},
        {
            "hashing": {
                "verification_limits": {"max_bcrypt_rounds": 17},
            },
        },
    ],
)
def test_repository_rejects_invalid_hashing_configuration(
    values: dict[str, object],
) -> None:
    """Reject malformed configuration without echoing submitted values.

    Invalid values produce the same safe configuration error.
    """
    repository = Repository(values)

    with pytest.raises(HashingConfigurationError):
        HashingConfiguration.from_repository(repository)


def test_configuration_rejects_blank_driver_names() -> None:
    """Require a non-empty selected driver before manager construction.

    Whitespace does not identify a built-in or custom algorithm.
    """
    with pytest.raises(HashingConfigurationError):
        HashingConfiguration(driver=" ")
