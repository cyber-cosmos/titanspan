"""Define structural contracts for hierarchical configuration access.

Readers and writers are separate capabilities so consumers can depend on the
smallest supported surface. ``ConfigRepository`` combines the common mutable
repository behavior; typed reads, overrides, macros, and diagnostics are
optional capabilities declared separately.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol, overload, runtime_checkable

type ConfigArray = Mapping[str, object] | list[object]
type ConfigKeySequence = list[str] | tuple[str, ...]


@runtime_checkable
class ConfigReader(Protocol):
    """Read hierarchical values without requiring a concrete implementation.

    Missing values use the supplied default, while explicit ``None`` remains
    a present stored value. Batch lookup preserves input order in its result.
    """

    def has(self, key: str) -> bool:
        """Check whether one dotted configuration path exists.

        Args:
            key: Direct key or nested path.

        Returns:
            Whether a value is present, including explicit ``None``.
        """
        ...

    @overload
    def get(self, key: str, default: object = None) -> object:
        """Retrieve one path with an optional lazy fallback.

        Args:
            key: Direct key or nested path.
            default: Fallback value or zero-argument callback.

        Returns:
            The stored value or resolved fallback.
        """
        ...

    @overload
    def get(
        self,
        key: ConfigKeySequence,
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several paths using a shared fallback.

        Args:
            key: Ordered paths to retrieve.
            default: Fallback value or callback for absent paths.

        Returns:
            A mapping keyed by each requested path.
        """
        ...

    @overload
    def get(
        self,
        key: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Retrieve paths with an individual fallback per path.

        Args:
            key: Paths mapped to fallback values or callbacks.

        Returns:
            A mapping keyed by each requested path.
        """
        ...

    def get(
        self,
        key: str | ConfigKeySequence | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Retrieve one or multiple values.

        Args:
            key: A dotted path, ordered paths, or per-path defaults.
            default: Shared fallback for a path or ordered paths.

        Returns:
            A stored value or mapping of requested values.
        """
        ...

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve multiple paths through one canonical operation.

        Args:
            keys: Ordered paths or paths mapped to individual defaults.
            default: Shared fallback used for an ordered path sequence.

        Returns:
            A mapping keyed by each requested path.
        """
        ...

    def all(self) -> Mapping[str, object]:
        """Return a read-only snapshot or view of all configuration values.

        Returns:
            A mapping of top-level namespace names to configured values.
        """
        ...


@runtime_checkable
class ConfigWriter(Protocol):
    """Mutate a configuration repository through explicit operations.

    Implementations document whether startup mutation is atomic or safe to
    perform concurrently with readers.
    """

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one path or apply a mapping of path assignments.

        Args:
            key: Dotted path or mapping of paths to values.
            value: Value assigned when ``key`` is a string.
        """
        ...

    def prepend(self, key: str, value: object) -> None:
        """Insert a value before entries in a list-valued setting.

        Args:
            key: Dotted path to the list.
            value: Value inserted at index zero.
        """
        ...

    def push(self, key: str, value: object) -> None:
        """Append a value after entries in a list-valued setting.

        Args:
            key: Dotted path to the list.
            value: Value appended after existing entries.
        """
        ...


@runtime_checkable
class ConfigRepository(ConfigReader, ConfigWriter, Protocol):
    """Represent the standard mutable configuration service contract.

    Typed access, scoped overrides, diagnostic redaction, and macros are
    separate capabilities. A basic implementation is not required to provide
    those extensions.
    """


__all__ = [
    "ConfigArray",
    "ConfigKeySequence",
    "ConfigReader",
    "ConfigRepository",
    "ConfigWriter",
]
