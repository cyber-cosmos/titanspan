"""Verify cache convenience exports retain canonical object identities.

Package-level imports must not create alternate contracts or facades.
"""

import pytest

from titanspan.cache import CacheRepository as CachePackageRepository
from titanspan.cache import LockClearStore as CachePackageLockClearStore
from titanspan.contracts import CacheRepository, LockClearStore
from titanspan.facades import Cache
from titanspan.facades.cache import Cache as CacheFacade

pytestmark = pytest.mark.unit


def test_package_exports_use_canonical_contracts_and_facade() -> None:
    """Keep cache package exports as aliases to canonical public objects.

    Consumers can import from component packages without splitting identity.
    """
    assert CachePackageRepository is CacheRepository
    assert CachePackageLockClearStore is LockClearStore
    assert Cache is CacheFacade
