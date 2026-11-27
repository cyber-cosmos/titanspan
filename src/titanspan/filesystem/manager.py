"""Resolve one application's configured named storage disks.

The manager owns configuration and fsspec instances without adding another
storage backend or process-global registry. Execution-local disk overrides
use the same manager resolution boundary as configured disks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeGuard

from fsspec.spec import (  # pyright: ignore[reportMissingTypeStubs]
    AbstractFileSystem,
)

from titanspan.contracts.filesystem import StorageDisk, StorageManager
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
    from collections.abc import Generator
    from pathlib import Path

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
_MANAGER_CLOSED_ERROR = "The filesystem manager is closed."
_BACKEND_CLEANUP_ERROR = "One or more filesystem backends failed to close."


class FilesystemManager(StorageManager):
    """Construct and cache disks declared by one application's settings.

    Applications register custom fsspec drivers before resolving a disk.
    The instance lock covers first construction. Context-local overrides do
    not mutate this shared cache.
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
        self._owned_disks: dict[int, FilesystemDisk] = {}
        self._closed = False
        self._disk_overrides: ContextVar[Mapping[str, StorageDisk]] = (
            ContextVar(
                "titanspan_storage_disk_overrides",
                default=MappingProxyType({}),
            )
        )
        self._lock = RLock()

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        drivers: Mapping[str, FilesystemDriverFactory] | None = None,
        base_path: Path | None = None,
    ) -> FilesystemManager:
        """Construct a manager from the canonical configuration repository.

        Args:
            repository: Application-owned Config repository.
            drivers: Additional fsspec filesystem constructors.
            base_path: Effective root for relative local disk settings.

        Returns:
            A manager isolated to one application service graph.
        """
        return cls(
            FilesystemConfiguration.from_repository(
                repository,
                base_path=base_path,
            ),
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

    def disk(self, name: str | None = None) -> StorageDisk:
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
        if self._closed:
            raise FilesystemDiskError(_MANAGER_CLOSED_ERROR)
        configuration = self._configuration.disks.get(disk_name)
        if configuration is None:
            raise UnknownFilesystemDiskError(disk_name)
        override = self._disk_overrides.get().get(disk_name)
        if override is not None:
            return override
        with self._lock:
            if self._closed:
                raise FilesystemDiskError(_MANAGER_CLOSED_ERROR)
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
            self._owned_disks.setdefault(id(filesystem), disk)
            return disk

    async def aclose(self) -> None:
        """Finalize each manager-owned filesystem backend at most once.

        Backends without a public ``aclose`` or ``close`` capability need no
        manager cleanup. Every owned backend is attempted even when another
        backend fails.

        Raises:
            FilesystemDiskError: If one or more backends fail to close.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            disks = tuple(reversed(tuple(self._owned_disks.values())))
            self._owned_disks.clear()
            self._disks.clear()

        failed = False
        for disk in disks:
            try:
                await disk.aclose()
            except Exception:
                failed = True
        if failed:
            raise FilesystemDiskError(_BACKEND_CLEANUP_ERROR) from None

    @contextmanager
    def override_disk(
        self,
        name: str,
        disk: StorageDisk,
    ) -> Generator[None, None, None]:
        """Select a replacement disk within the active execution context.

        The override is separate from the configured disk cache. This lets a
        test replace a remote disk without constructing or accessing it.

        Args:
            name: Configured disk name to replace.
            disk: Replacement implementing the native storage contract.

        Yields:
            Control while the selected disk override is active.

        Raises:
            UnknownFilesystemDiskError: If ``name`` is not configured.
        """
        if name not in self._configuration.disks:
            raise UnknownFilesystemDiskError(name)
        if self._closed:
            raise FilesystemDiskError(_MANAGER_CLOSED_ERROR)
        overrides = dict(self._disk_overrides.get())
        overrides[name] = disk
        token = self._disk_overrides.set(MappingProxyType(overrides))
        try:
            yield
        finally:
            self._disk_overrides.reset(token)

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
    _disk_overrides: ContextVar[Mapping[str, StorageDisk]]
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
