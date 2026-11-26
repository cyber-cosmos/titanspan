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
)
from titanspan.hashing.exceptions import HashingConfigurationError

pytestmark = pytest.mark.unit
_SECURE_ARGON2_MEMORY_KIB = 65_536
_SECURE_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_ROUNDS = 31


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


def test_configuration_accepts_bcrypt_backend_maximum_rounds() -> None:
    """Accept the highest work factor supported by the backend API.

    The upper bound prevents deferred backend failures at hash time.
    """
    assert BcryptConfiguration(rounds=_BCRYPT_MAX_ROUNDS).rounds == (
        _BCRYPT_MAX_ROUNDS
    )


@pytest.mark.parametrize(
    "values",
    [
        {"hashing": None},
        {"hashing": {"driver": 12}},
        {"hashing": {"argon2id": []}},
        {"hashing": {"argon2id": {"time_cost": True}}},
        {"hashing": {"bcrypt": {"rounds": 11}}},
        {"hashing": {"bcrypt": {"prefix": "2y"}}},
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
