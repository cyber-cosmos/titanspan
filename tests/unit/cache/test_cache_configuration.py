"""Verify cache configuration validation and canonical repository loading.

Configuration values are immutable snapshots and never render backend
credentials through their ordinary representation.
"""

from typing import TYPE_CHECKING, cast

import pytest

from titanspan.cache import (
    CacheConfiguration,
    CacheConfigurationError,
    CacheStoreConfiguration,
)
from titanspan.config import Repository

pytestmark = pytest.mark.unit
_INITIAL_CAPACITY = 12
_MUTATED_CAPACITY = 20

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any


def test_configuration_uses_the_application_name_as_namespace() -> None:
    """Use canonical Config values and preserve independent stores.
    """  # fmt: skip
    repository = Repository(
        {
            "app": {"name": "orders"},
            "cache": {
                "default": "redis_primary",
                "stores": {
                    "redis_primary": {
                        "driver": "redis",
                        "options": {"url": "redis://localhost/3"},
                    },
                    "redis_secondary": {
                        "driver": "redis",
                        "options": {"url": "redis://localhost/4"},
                    },
                },
            },
        }
    )

    configuration = CacheConfiguration.from_repository(repository)

    assert configuration.default == "redis_primary"
    assert configuration.namespace == "orders"
    assert configuration.store_configurations["redis_primary"].driver == "redis"
    assert (
        configuration.store_configurations["redis_secondary"].options["url"]
        == "redis://localhost/4"
    )


def test_configuration_freezes_store_options() -> None:
    """Retain an immutable snapshot after caller mutations.
    """  # fmt: skip
    options = {"max_items": _INITIAL_CAPACITY}
    store = CacheStoreConfiguration("memory", options)
    options["max_items"] = _MUTATED_CAPACITY

    assert store.options["max_items"] == _INITIAL_CAPACITY
    with pytest.raises(TypeError):
        cast("MutableMapping[str, Any]", store.options)["max_items"] = 4


@pytest.mark.parametrize(
    "configuration",
    [
        {"default": "missing"},
        {"namespace": "bad:namespace"},
        {"prefix": "bad prefix"},
        {"max_batch_size": 0},
        {"max_value_bytes": 0},
        {"events": 1},
        {"stores": {"bad/name": {"driver": "memory"}}},
    ],
)
def test_invalid_configuration_is_rejected(
    configuration: dict[str, object],
) -> None:
    """Reject unsafe namespace, limits, booleans, and store references.
    """  # fmt: skip
    with pytest.raises(CacheConfigurationError):
        CacheConfiguration(**cast("Any", configuration))


def test_configuration_representation_does_not_expose_credentials() -> None:
    """Avoid rendering configured Redis passwords during diagnostics.
    """  # fmt: skip
    configuration = CacheConfiguration(
        stores={
            "secure": {
                "driver": "redis",
                "options": {
                    "password": "secret",  # pragma: allowlist secret
                },
            }
        },
        default="secure",
    )

    assert "secret" not in repr(configuration)


def test_application_cache_configuration_is_not_config_snapshot_cache() -> None:
    """Read only application cache settings from the dedicated cache path.
    """  # fmt: skip
    repository = Repository(
        {
            "app": {"name": "config-isolation"},
            "config": {"cache": {"driver": "filesystem"}},
        }
    )

    configuration = CacheConfiguration.from_repository(repository)

    assert configuration.default == "memory"
    assert configuration.namespace == "config-isolation"
