"""Define the typed contract for mutable application configuration.

The protocol describes repository behavior only. Pydantic Settings remains
the canonical implementation for Titanspan's current application settings.
"""

from collections.abc import Mapping
from typing import Protocol, overload, runtime_checkable

type _ConfigKeySequence = list[str] | tuple[str, ...]


@runtime_checkable
class ConfigRepository(Protocol):
    """Expose mutable configuration through a backend-neutral interface.

    Implementations preserve explicitly stored ``None`` values when checking
    presence. Multi-key retrieval returns a mapping keyed by the requested
    configuration paths. ``set`` accepts either one path and value or a
    mapping of paths to values.

    Sequence updates initialize a missing value as a list. Implementations
    must document how incompatible pre-existing values are handled.
    """

    def has(self, key: str) -> bool:
        """Check whether a configuration path is present.

        Args:
            key: A dotted path within the configuration repository.

        Returns:
            Whether the path exists, including when its value is ``None``.
        """
        ...

    @overload
    def get(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Retrieve one configuration path.

        Args:
            key: A dotted path within the configuration repository.
            default: Value used when the path is absent.

        Returns:
            The stored value or the supplied default.
        """
        ...

    @overload
    def get(
        self,
        key: _ConfigKeySequence,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several paths as one mapping.

        Args:
            key: The paths to retrieve, in requested order.
            default: Value substituted for each absent path.

        Returns:
            Values keyed by their requested configuration paths.
        """
        ...

    def get(
        self,
        key: str | _ConfigKeySequence,
        default: object = None,
    ) -> object:
        """Retrieve one path or several paths from the repository.

        Args:
            key: One dotted path or a sequence of dotted paths.
            default: Value used for each absent path.

        Returns:
            A stored value or mapping of requested values.
        """
        ...

    def all(self) -> Mapping[str, object]:
        """Return the repository's top-level configuration values.

        Returns:
            A mapping view or snapshot of configured values. Callers should
            treat the returned mapping as read-only.
        """
        ...

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one path or merge a mapping into the repository.

        Args:
            key: A dotted path or mapping of dotted paths to values.
            value: Value assigned when ``key`` is a string. ``None`` is a
                valid stored value.
        """
        ...

    def prepend(self, key: str, value: object) -> None:
        """Insert a value at the start of a sequence-valued setting.

        Args:
            key: The configuration path to update.
            value: Value inserted before existing sequence elements.

        Raises:
            TypeError: If the existing setting is not sequence-valued.
        """
        ...

    def push(self, key: str, value: object) -> None:
        """Append a value to a sequence-valued setting.

        Args:
            key: The configuration path to update.
            value: Value appended after existing sequence elements.

        Raises:
            TypeError: If the existing setting is not sequence-valued.
        """
        ...


__all__ = ["ConfigRepository"]
