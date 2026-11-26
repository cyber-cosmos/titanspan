"""Expose the canonical filesystem contracts and metadata values.

Storage implementations re-export these exact objects for convenience.
"""

from titanspan.contracts.filesystem.storage import (
    FileMetadata,
    StorageDisk,
    StorageManager,
)

__all__ = ["FileMetadata", "StorageDisk", "StorageManager"]
