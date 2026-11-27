"""Validate disk selection and backend options from native configuration.

Filesystem settings live under the ``filesystem`` configuration namespace.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from titanspan.filesystem.exceptions import FilesystemConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

_DEFAULT_DISK = "local"
_DEFAULT_LOCAL_ROOT = Path("storage/app")
_CONFIGURATION_ERROR = "The filesystem configuration is invalid."
_LOCAL_ROOT_ESCAPE_ERROR = (
    "A relative local disk root must remain inside the application root."
)


def _empty_options() -> dict[str, object]:
    """Return an independent empty driver-options mapping.

    Returns:
        A newly allocated dictionary for one disk configuration.
    """
    return {}


@dataclass(frozen=True, slots=True)
class FilesystemDiskConfiguration:
    """Hold one named disk's driver, root, options, and error policy.

    Attributes:
        driver: Registered fsspec driver name.
        root: Trusted local root or backend-relative prefix.
        raise_errors: Whether failed write operations raise backend errors.
        options: Driver-specific values passed only to the registered factory.
    """

    driver: str
    root: str | Path | None = None
    raise_errors: bool = True
    options: Mapping[str, object] = field(default_factory=_empty_options)

    def __post_init__(self) -> None:
        """Validate and freeze values shared by the manager and driver.

        Raises:
            FilesystemConfigurationError: If fields have unsupported values.
        """
        if not self.driver or not self.driver.strip():
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        options = dict(self.options)
        object.__setattr__(self, "driver", self.driver.strip())
        object.__setattr__(self, "options", MappingProxyType(options))


def _default_disks() -> dict[str, FilesystemDiskConfiguration]:
    """Return the built-in local disk configuration.

    Returns:
        A new mapping that avoids shared mutable configuration state.
    """
    return {
        _DEFAULT_DISK: FilesystemDiskConfiguration(
            driver="local",
            root=_DEFAULT_LOCAL_ROOT,
        ),
    }


@dataclass(frozen=True, slots=True)
class FilesystemConfiguration:
    """Hold the application default disk and named disk declarations.

    Foundation anchors relative local roots to each application's base path.
    Absolute local roots and remote backend prefixes retain their meaning.
    """

    default_disk: str = _DEFAULT_DISK
    disks: Mapping[str, FilesystemDiskConfiguration] = field(
        default_factory=_default_disks,
    )

    def __post_init__(self) -> None:
        """Validate disk names and freeze the selected configuration.

        Raises:
            FilesystemConfigurationError: If the default or a disk is invalid.
        """
        normalized = dict(self.disks)
        if (
            not self.default_disk
            or self.default_disk not in normalized
            or any(not _valid_disk_name(name) for name in normalized)
        ):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        object.__setattr__(self, "disks", MappingProxyType(normalized))

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        base_path: Path | None = None,
    ) -> FilesystemConfiguration:
        """Build validated settings from the canonical Config repository.

        Args:
            repository: Application-owned configuration repository.
            base_path: Application root used to anchor relative local roots.

        Returns:
            Immutable settings for one manager.

        Raises:
            FilesystemConfigurationError: If the namespace has invalid shape.
        """
        values = repository.get("filesystem", {})
        if not isinstance(values, Mapping):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        raw_values = cast("Mapping[str, object]", values)
        default_disk = raw_values.get("default", _DEFAULT_DISK)
        raw_disks = raw_values.get("disks")
        if not isinstance(default_disk, str):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        if raw_disks is None:
            disks = _default_disks()
        elif isinstance(raw_disks, Mapping):
            disks = _parse_disks(
                cast("Mapping[object, object]", raw_disks),
            )
        else:
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        try:
            if base_path is not None:
                disks = _anchor_local_roots(disks, base_path)
            return cls(default_disk=default_disk, disks=disks)
        except FilesystemConfigurationError:
            raise
        except (TypeError, ValueError) as error:
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR) from error


def _parse_disks(
    values: Mapping[object, object],
) -> dict[str, FilesystemDiskConfiguration]:
    """Convert untrusted nested settings into typed disk declarations.

    Args:
        values: Disk names mapped to application configuration values.

    Returns:
        Validated disk declarations in configuration order.

    Raises:
        FilesystemConfigurationError: If any disk has an invalid shape.
    """
    disks: dict[str, FilesystemDiskConfiguration] = {}
    for name, raw_configuration in values.items():
        if not isinstance(name, str) or not _valid_disk_name(name):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        if not isinstance(raw_configuration, Mapping):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        configuration = cast(
            "Mapping[str, object]",
            raw_configuration,
        )
        driver = configuration.get("driver", name)
        root = configuration.get("root")
        raise_errors = configuration.get("raise_errors", True)
        options = configuration.get("options", {})
        if (
            not isinstance(driver, str)
            or (root is not None and not isinstance(root, (str, Path)))
            or not isinstance(raise_errors, bool)
            or not isinstance(options, Mapping)
        ):
            raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
        if root is None and driver == "local":
            root = _DEFAULT_LOCAL_ROOT
        disks[name] = FilesystemDiskConfiguration(
            driver=driver,
            root=root,
            raise_errors=raise_errors,
            options=cast("Mapping[str, object]", options),
        )
    if not disks:
        raise FilesystemConfigurationError(_CONFIGURATION_ERROR)
    return disks


def _anchor_local_roots(
    disks: Mapping[str, FilesystemDiskConfiguration],
    base_path: Path,
) -> dict[str, FilesystemDiskConfiguration]:
    """Resolve relative local roots and reject paths outside the app root.

    Args:
        disks: Validated named disk settings.
        base_path: Effective root selected during application composition.

    Returns:
        A copy with relative local roots anchored to the application.

    Raises:
        FilesystemConfigurationError: If a relative local root escapes.
    """
    root = base_path.resolve()
    anchored: dict[str, FilesystemDiskConfiguration] = {}
    for name, disk in disks.items():
        disk_root = disk.root
        anchored_disk = disk
        if disk.driver == "local" and disk_root is not None:
            path = Path(disk_root).expanduser()
            if not path.is_absolute():
                resolved = (root / path).resolve(strict=False)
                if not resolved.is_relative_to(root):
                    raise FilesystemConfigurationError(
                        _LOCAL_ROOT_ESCAPE_ERROR,
                    )
                anchored_disk = FilesystemDiskConfiguration(
                    driver=disk.driver,
                    root=resolved,
                    raise_errors=disk.raise_errors,
                    options=disk.options,
                )
        anchored[name] = anchored_disk
    return anchored


def _valid_disk_name(name: str) -> bool:
    """Validate a stable name used by the application disk manager.

    Args:
        name: Candidate disk identifier.

    Returns:
        Whether the identifier uses supported ASCII name characters.
    """
    return bool(name) and all(
        character.isascii()
        and (character.isalnum() or character in {"_", "-", "."})
        for character in name
    )


__all__ = ["FilesystemConfiguration", "FilesystemDiskConfiguration"]
