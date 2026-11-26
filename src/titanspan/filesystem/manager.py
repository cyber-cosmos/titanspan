"""Resolve one application's configured named storage disks.

The manager owns configuration and fsspec instances without adding another
storage backend or process-global registry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import RLock
from typing import TYPE_CHECKING, TypeGuard

from fsspec.spec import (  # pyright: ignore[reportMissingTypeStubs]
    AbstractFileSystem,
)

from titanspan.contracts.filesystem import StorageManager
from titanspan.filesystem._backends import (
    create_local_filesystem,
    create_memory_filesystem,
)
from titanspan.filesystem._types import FsspecFilesystem
from titanspan.filesystem.configuration import (
    FilesystemConfiguration,
    FilesystemDiskConfiguration,
)
from titanspan.filesystem.disk import FilesystemDisk
from titanspan.filesystem.exceptions import (
    FilesystemConfigurationError,
    FilesystemDiskError,
    UnknownFilesystemDiskError,
)

if TYPE_CHECKING:
    from _thread import RLock as RLockType

    from titanspan.contracts.config import ConfigRepository

type FilesystemDriverFactory = Callable[
    [FilesystemDiskConfiguration],
    FsspecFilesystem,
]

_DISK_RESOLVED_ERROR = "A disk is already resolved by this manager."
_DRIVER_EXISTS_ERROR = "The filesystem driver is already registered."
_UNKNOWN_DRIVER_ERROR = "The filesystem disk driver is not registered."
_INVALID_FILESYSTEM_ERROR = (
    "A filesystem driver must return an fsspec filesystem instance."
)
_DRIVER_CREATION_ERROR = (
    "The configured filesystem driver could not be created."
)


class FilesystemManager(StorageManager):
    """Construct and cache disks declared by one application's settings.

    Applications register custom fsspec drivers before resolving a disk.
    The instance lock covers only first construction so concurrent requests
    share the same disk object.
    """

    def __init__(
        self,
        configuration: FilesystemConfiguration | None = None,
        *,
        drivers: Mapping[str, FilesystemDriverFactory] | None = None,
    ) -> None:
        """Retain typed settings and built-in plus custom disk factories.

        Args:
            configuration: Named disk settings; defaults to one local disk.
            drivers: Additional named fsspec filesystem constructors.

        Raises:
            FilesystemConfigurationError: If a driver registration is invalid.
        """
        selected = configuration or FilesystemConfiguration()
        factories: dict[str, FilesystemDriverFactory] = {
            "local": create_local_filesystem,
            "memory": create_memory_filesystem,
        }
        for name, factory in (drivers or {}).items():
            self._validate_factory(name, factory)
            if name in factories:
                raise FilesystemConfigurationError(_DRIVER_EXISTS_ERROR)
            factories[name] = factory
        self._configuration = selected
        self._drivers = factories
        self._disks: dict[str, FilesystemDisk] = {}
        self._lock = RLock()

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        drivers: Mapping[str, FilesystemDriverFactory] | None = None,
    ) -> FilesystemManager:
        """Construct a manager from the canonical configuration repository.

        Args:
            repository: Application-owned Config repository.
            drivers: Additional fsspec filesystem constructors.

        Returns:
            A manager isolated to one application service graph.
        """
        return cls(
            FilesystemConfiguration.from_repository(repository),
            drivers=drivers,
        )

    @property
    def default_disk(self) -> str:
        """Return the disk name selected by configuration.

        Returns:
            Configured default disk identifier.
        """
        return self._configuration.default_disk

    @property
    def disk_names(self) -> tuple[str, ...]:
        """Return configured names in deterministic insertion order.

        Returns:
            Immutable disk name sequence from application configuration.
        """
        return tuple(self._configuration.disks)

    def disk(self, name: str | None = None) -> FilesystemDisk:
        """Resolve the cached instance for one configured disk.

        Args:
            name: Configured disk name, or the application default.

        Returns:
            One application-owned disk wrapper.

        Raises:
            UnknownFilesystemDiskError: If the requested disk is absent.
            FilesystemDiskError: If its driver cannot be constructed.
        """
        disk_name = self.default_disk if name is None else name
        configuration = self._configuration.disks.get(disk_name)
        if configuration is None:
            raise UnknownFilesystemDiskError(disk_name)
        with self._lock:
            current = self._disks.get(disk_name)
            if current is not None:
                return current
            filesystem = self._make_filesystem(configuration)
            disk = FilesystemDisk(
                filesystem,
                root=configuration.root,
                raise_errors=configuration.raise_errors,
            )
            self._disks[disk_name] = disk
            return disk

    def extend(
        self,
        driver: str,
        factory: FilesystemDriverFactory,
    ) -> None:
        """Register a custom fsspec driver before resolving any disk.

        Args:
            driver: Native driver key selected in a disk configuration.
            factory: Constructor returning a supported fsspec filesystem.

        Raises:
            FilesystemDiskError: If registration conflicts or is too late.
            FilesystemConfigurationError: If the name or factory is invalid.
        """
        self._validate_factory(driver, factory)
        with self._lock:
            if self._disks:
                raise FilesystemDiskError(_DISK_RESOLVED_ERROR)
            if driver in self._drivers:
                raise FilesystemDiskError(_DRIVER_EXISTS_ERROR)
            self._drivers[driver] = factory

    def _make_filesystem(
        self,
        configuration: FilesystemDiskConfiguration,
    ) -> FsspecFilesystem:
        """Build one backend using its registered public factory.

        Args:
            configuration: Disk declaration selected by name.

        Returns:
            A supported fsspec filesystem implementation.

        Raises:
            FilesystemDiskError: If the configured driver is unknown.
            FilesystemConfigurationError: If factory construction fails.
        """
        factory = self._drivers.get(configuration.driver)
        if factory is None:
            raise FilesystemDiskError(_UNKNOWN_DRIVER_ERROR)
        try:
            filesystem = factory(configuration)
        except Exception:
            raise FilesystemConfigurationError(_DRIVER_CREATION_ERROR) from None
        if not _is_fsspec_filesystem(filesystem):
            raise FilesystemConfigurationError(_INVALID_FILESYSTEM_ERROR)
        return filesystem

    @staticmethod
    def _validate_factory(
        name: str,
        factory: FilesystemDriverFactory,
    ) -> None:
        """Reject invalid driver identifiers and callable registrations.

        Args:
            name: Driver identifier used by disk settings.
            factory: Backend factory to validate.

        Raises:
            FilesystemConfigurationError: If either value is invalid.
        """
        if (
            not name
            or not name.isascii()
            or not name.replace("_", "").replace("-", "").isalnum()
            or not callable(factory)
        ):
            raise FilesystemConfigurationError(_UNKNOWN_DRIVER_ERROR)

    _configuration: FilesystemConfiguration
    _drivers: dict[str, FilesystemDriverFactory]
    _disks: dict[str, FilesystemDisk]
    _lock: RLockType


__all__ = ["FilesystemDriverFactory", "FilesystemManager"]


def _is_fsspec_filesystem(
    filesystem: object,
) -> TypeGuard[FsspecFilesystem]:
    """Verify that a custom factory returned an fsspec filesystem object.

    Args:
        filesystem: Untrusted driver factory result.

    Returns:
        Whether fsspec recognizes the object as an AbstractFileSystem.
    """
    return isinstance(filesystem, AbstractFileSystem)
