"""Select the application's configured password hashing driver.

The manager owns one stable hasher and exposes custom drivers through typed
factories without creating a separate service registry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from titanspan.contracts.hashing import Hasher
from titanspan.hashing._backends import _NativeHasher
from titanspan.hashing.configuration import HashingConfiguration
from titanspan.hashing.exceptions import HashingConfigurationError

if TYPE_CHECKING:
    from titanspan.contracts.config import ConfigRepository

type HasherFactory = Callable[[HashingConfiguration], Hasher]

_INVALID_DRIVER_ERROR = "A hashing driver registration is invalid."
_UNKNOWN_DRIVER_ERROR = "The configured hashing driver is unavailable."
_DRIVER_CREATION_ERROR = "The configured hashing driver could not be created."


def _create_argon2id_hasher(
    configuration: HashingConfiguration,
) -> Hasher:
    """Create the built-in Argon2id driver with Bcrypt verification.

    Args:
        configuration: Validated settings for all built-in drivers.

    Returns:
        A service configured for new Argon2id hashes.
    """
    return _NativeHasher(configuration)


def _create_bcrypt_hasher(
    configuration: HashingConfiguration,
) -> Hasher:
    """Create the built-in Bcrypt driver with Argon2 verification.

    Args:
        configuration: Validated settings for all built-in drivers.

    Returns:
        A service configured for new Bcrypt hashes.
    """
    return _NativeHasher(configuration)


class HashingManager:
    """Construct the configured hasher for one application service graph.

    The manager freezes driver selection at construction. A provider supplies
    custom factories before the application resolves its hashing services.
    """

    def __init__(
        self,
        configuration: HashingConfiguration | None = None,
        *,
        drivers: Mapping[str, HasherFactory] | None = None,
    ) -> None:
        """Select one built-in or application-registered password hasher.

        Args:
            configuration: Optional typed hashing settings.
            drivers: Custom hasher factories keyed by their algorithm name.

        Raises:
            HashingConfigurationError: If the selected driver is unavailable
                or a factory returns an incompatible service.
        """
        selected = configuration or HashingConfiguration()
        factories: dict[str, HasherFactory] = {
            "argon2id": _create_argon2id_hasher,
            "bcrypt": _create_bcrypt_hasher,
        }
        for name, factory in (drivers or {}).items():
            if (
                not name.isidentifier()
                or name in factories
                or not callable(factory)
            ):
                raise HashingConfigurationError(_INVALID_DRIVER_ERROR)
            factories[name] = factory
        factory = factories.get(selected.driver)
        if factory is None:
            raise HashingConfigurationError(_UNKNOWN_DRIVER_ERROR)
        try:
            hasher = factory(selected)
        except Exception:
            raise HashingConfigurationError(_DRIVER_CREATION_ERROR) from None
        if hasher.algorithm != selected.driver:
            raise HashingConfigurationError(_INVALID_DRIVER_ERROR)
        self._configuration = selected
        self._hasher = hasher
        self._driver_names = tuple(factories)

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        drivers: Mapping[str, HasherFactory] | None = None,
    ) -> HashingManager:
        """Build one manager from the canonical configuration repository.

        Args:
            repository: Application-owned configuration repository.
            drivers: Custom hasher factories selected by configuration.

        Returns:
            One manager with an application-local driver selection.
        """
        return cls(
            HashingConfiguration.from_repository(repository),
            drivers=drivers,
        )

    @property
    def default_driver(self) -> str:
        """Return the configured driver for new and replacement hashes.

        The manager keeps this choice stable for its application lifetime.
        """
        return self._configuration.driver

    @property
    def driver_names(self) -> tuple[str, ...]:
        """Return available driver names in deterministic registration order.

        Built-in names precede custom names supplied to the manager.
        """
        return self._driver_names

    def hasher(self) -> Hasher:
        """Return the stable hasher selected for this application.

        Returns:
            The same contract implementation exposed to dependency injection.
        """
        return self._hasher

    _configuration: HashingConfiguration
    _driver_names: tuple[str, ...]
    _hasher: Hasher


__all__ = ["HasherFactory", "HashingManager"]
