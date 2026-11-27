"""Verify optional Redis configuration and key-scope boundaries.
"""  # fmt: skip

import pytest

from titanspan.cache import CacheConfiguration, CacheManager
from titanspan.cache.exceptions import CacheConfigurationError
from titanspan.contracts.cache import PrefixClearStore

pytestmark = pytest.mark.unit
_INVALID_REDIS_OPTIONS = [
    pytest.param({"url": ""}),
    pytest.param({"url": 7}),
    pytest.param({"url": "http://example.test"}),
    pytest.param({"url": "redis://"}),
    pytest.param({"url": "redis://[::1]:70000"}),
    pytest.param({"unsupported": True}),
    pytest.param({"port": "6379"}),
    pytest.param({"db": False}),
    pytest.param({"ssl": 1}),
    pytest.param({"max_connections": True}),
    pytest.param({"max_connections": 0}),
    pytest.param({"host": 4}),
    pytest.param({"username": 4}),
    pytest.param({"password": 4}),
    pytest.param({"socket_timeout": 0}),
    pytest.param({"socket_timeout": float("inf")}),
    pytest.param({"socket_timeout": 61}),
    pytest.param({"socket_connect_timeout": "slow"}),
]
_INVALID_PREFIXES = [
    pytest.param(""),
    pytest.param("bad*"),
    pytest.param("bracket["),
    pytest.param("é"),
    pytest.param("x" * 513),
]


def _manager(options: dict[str, object]) -> CacheManager:
    """Build one Redis manager without opening a network connection.
    """  # fmt: skip
    return CacheManager(
        CacheConfiguration(
            default="redis",
            stores={
                "redis": {"driver": "redis", "options": options},
            },
        )
    )


@pytest.mark.parametrize("options", _INVALID_REDIS_OPTIONS)
def test_redis_store_rejects_invalid_connection_configuration(
    options: dict[str, object],
) -> None:
    """Reject malformed settings while lazily constructing a Redis store.
    """  # fmt: skip
    pytest.importorskip("redis")
    manager = _manager(options)

    with pytest.raises(CacheConfigurationError):
        manager.resolve_backend("redis")


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", _INVALID_PREFIXES)
async def test_redis_prefix_clear_rejects_unsafe_patterns(
    prefix: str,
) -> None:
    """Reject user-controlled glob patterns before Redis receives a scan.
    """  # fmt: skip
    pytest.importorskip("redis")
    manager = _manager({"host": "127.0.0.1", "port": 1})
    backend = manager.resolve_backend("redis")
    assert isinstance(backend, PrefixClearStore)

    with pytest.raises(CacheConfigurationError):
        backend.clear_prefix(prefix)
    with pytest.raises(CacheConfigurationError):
        await backend.clear_prefix_async(prefix)

    await manager.aclose()
