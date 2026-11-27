"""Verify malformed cache configuration is rejected at its boundary.

These cases use the canonical Config repository and immutable value objects.
"""

from typing import Any, cast

import pytest

from titanspan.cache import (
    CacheConfiguration,
    CacheConfigurationError,
    CacheStoreConfiguration,
)
from titanspan.config import Repository

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("values", "message"),
    [
        pytest.param({"cache": []}, "configuration value", id="root"),
        pytest.param(
            {"cache": {"namespace": 5}},
            "namespace must be a string",
            id="namespace",
        ),
        pytest.param(
            {"cache": {"stores": []}},
            "stores must be a map",
            id="stores",
        ),
        pytest.param(
            {"cache": {"default": 5}},
            "must be text",
            id="default",
        ),
        pytest.param(
            {"cache": {"prefix": 5}},
            "must be text",
            id="prefix",
        ),
        pytest.param(
            {"cache": {"max_batch_size": True}},
            "must be an int",
            id="batch-bool",
        ),
        pytest.param(
            {"cache": {"max_value_bytes": "large"}},
            "must be an int",
            id="value-limit",
        ),
        pytest.param(
            {"cache": {"events": 1}},
            "must be a boolean",
            id="events",
        ),
        pytest.param(
            {"cache": {"stores": {"bad": 5}}},
            "definitions must be maps",
            id="store-definition",
        ),
        pytest.param(
            {"cache": {"stores": {"redis": {"driver": 5}}}},
            "driver must be a string",
            id="store-driver",
        ),
        pytest.param(
            {
                "cache": {
                    "stores": {"redis": {"driver": "redis", "options": []}}
                }
            },
            "options must be a map",
            id="store-options",
        ),
        pytest.param(
            {
                "cache": {
                    "stores": {"redis": {"driver": "redis", "events": "yes"}}
                }
            },
            "events must be configured as a boolean",
            id="store-events",
        ),
        pytest.param(
            {"cache": {"stores": {1: {"driver": "memory"}}}},
            "store name is invalid",
            id="store-name",
        ),
    ],
)
def test_repository_configuration_rejects_malformed_values(
    values: dict[str, object],
    message: str,
) -> None:
    """Raise a native configuration error without coercing input values.
    """  # fmt: skip
    repository = Repository(values)

    with pytest.raises(CacheConfigurationError, match=message):
        CacheConfiguration.from_repository(repository)


def test_application_display_names_produce_stable_safe_namespaces() -> None:
    """Normalize unsafe display names without collapsing distinct apps.
    """  # fmt: skip
    first = Repository({"app": {"name": "Sales / West"}})
    second = Repository({"app": {"name": "Sales ? West"}})

    first_namespace = CacheConfiguration.from_repository(first).namespace
    second_namespace = CacheConfiguration.from_repository(second).namespace

    repeated_namespace = CacheConfiguration.from_repository(first).namespace

    assert first_namespace == repeated_namespace
    assert first_namespace != second_namespace
    assert first_namespace.isascii()
    assert all(
        character.isalnum() or character in "-_."
        for character in first_namespace
    )


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param({"driver": 5}, id="driver"),
        pytest.param({"options": []}, id="options-type"),
        pytest.param({"options": {1: "value"}}, id="option-name"),
        pytest.param({"events": 1}, id="events"),
    ],
)
def test_store_configuration_rejects_invalid_direct_values(
    arguments: dict[str, object],
) -> None:
    """Reject direct backend configuration with the same strict rules.
    """  # fmt: skip
    values = {"driver": "memory", **arguments}

    with pytest.raises(CacheConfigurationError):
        CacheStoreConfiguration(**cast("Any", values))


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"app": {"name": 4}}, id="application-namespace"),
        pytest.param(
            {
                "cache": {
                    "stores": {
                        "redis": {
                            "driver": "redis",
                            "options": {1: 2},
                        }
                    }
                }
            },
            id="nested-option-name",
        ),
    ],
)
def test_repository_rejects_invalid_names_and_nested_option_keys(
    values: dict[str, object],
) -> None:
    """Validate application names and text-only option names.
    """  # fmt: skip
    repository = Repository(values)

    with pytest.raises(CacheConfigurationError):
        CacheConfiguration.from_repository(repository)


def test_repository_store_options_require_text_keys() -> None:
    """Reject a mapping whose backend option names are not strings.
    """  # fmt: skip
    repository = Repository(
        {
            "cache": {
                "stores": {
                    "redis": {
                        "driver": "redis",
                        "options": {1: "private"},
                    }
                }
            }
        }
    )

    with pytest.raises(CacheConfigurationError, match="options must be a map"):
        CacheConfiguration.from_repository(repository)
