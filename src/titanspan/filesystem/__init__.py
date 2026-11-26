"""Expose native disk storage APIs backed by fsspec.

Application managers own named disks and retain their backend-specific
consistency and capability boundaries.
"""

from titanspan.contracts.filesystem import (
    FileMetadata,
    StorageDisk,
    StorageManager,
)
from titanspan.filesystem.configuration import (
    FilesystemConfiguration,
    FilesystemDiskConfiguration,
)
from titanspan.filesystem.disk import FilesystemDisk
from titanspan.filesystem.exceptions import (
    FilesystemConfigurationError,
    FilesystemDiskError,
    FilesystemError,
    StorageFakeContextError,
    UnknownFilesystemDiskError,
    UnsafeStoragePathError,
)
from titanspan.filesystem.fake import FilesystemFake
from titanspan.filesystem.manager import (
    FilesystemDriverFactory,
    FilesystemManager,
)
from titanspan.filesystem.service_provider import FilesystemServiceProvider

__all__ = [
    "FileMetadata",
    "FilesystemConfiguration",
    "FilesystemConfigurationError",
    "FilesystemDisk",
    "FilesystemDiskConfiguration",
    "FilesystemDiskError",
    "FilesystemDriverFactory",
    "FilesystemError",
    "FilesystemFake",
    "FilesystemManager",
    "FilesystemServiceProvider",
    "StorageDisk",
    "StorageFakeContextError",
    "StorageManager",
    "UnknownFilesystemDiskError",
    "UnsafeStoragePathError",
]
