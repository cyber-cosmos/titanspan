"""Provide an explicitly context-bound configuration facade.

The facade reads the repository for the active application or execution
scope. It never creates or retains a process-global configuration store.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import TypeVar

from titanspan._application_context import ApplicationContextError
from titanspan.config.exceptions import (
    ConfigCapabilityError,
    ConfigContextError,
)
from titanspan.contracts.config import (
    ConfigArray,
    ConfigMacroRegistry,
    ConfigRepository,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.facades.base import Facade

Default = TypeVar("Default")
_MISSING_CONTEXT_ERROR = (
    "Bind an application context before using the Config facade."
)
_SCOPED_OVERRIDE_CAPABILITY = "scoped overrides"
_TYPED_RETRIEVAL_CAPABILITY = "typed retrieval"
_MACRO_CAPABILITY = "configuration macros"


class Config(Facade[ConfigRepository]):
    """Resolve configuration operations from the active application.

    The facade resolves its repository through the active application
    container. Use :meth:`Facade.use` for temporary, container-owned service
    replacement in tests and execution-local customization.
    """

    service_contract = ConfigRepository

    @classmethod
    def repository(cls) -> ConfigRepository:
        """Return the repository owned by the active application.

        Returns:
            The active repository implementation.

        Raises:
            ConfigContextError: If no application context is active.
        """
        try:
            return cls.resolve_service()
        except ApplicationContextError as error:
            raise ConfigContextError(_MISSING_CONTEXT_ERROR) from error

    @classmethod
    def has(cls, key: str) -> bool:
        """Check whether a configured path exists.

        Args:
            key: Direct key or dotted path.

        Returns:
            Whether the path exists, including explicit null values.
        """
        return cls.repository().has(key)

    @classmethod
    def get(
        cls,
        key: str | Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Read one path or multiple paths from the active repository.

        Args:
            key: Dotted path, sequence of paths, or per-path defaults.
            default: Shared fallback for missing path or sequence entries.

        Returns:
            The configured value or mapping of selected values.
        """
        repository = cls.repository()
        if isinstance(key, Mapping):
            return repository.get_many(key)
        if isinstance(key, str):
            return repository.get(key, default)
        return repository.get_many(key, default)

    @classmethod
    def get_many(
        cls,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Read many paths with a shared or path-specific fallback.

        Args:
            keys: Ordered path sequence or mapping of paths to defaults.
            default: Shared fallback for sequence entries.

        Returns:
            Resolved values keyed by their configuration paths.
        """
        return cls.repository().get_many(keys, default)

    @classmethod
    def set(
        cls,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one path or a mapping of dotted configuration paths.

        Args:
            key: Dotted path or batch mapping.
            value: Value assigned for a string path.
        """
        repository = cls.repository()
        if isinstance(key, Mapping):
            repository.set(key)
        else:
            repository.set(key, value)

    @classmethod
    def all(cls) -> Mapping[str, object]:
        """Return all active repository values as a mapping.

        Returns:
            Repository snapshot or read-only mapping.
        """
        return cls.repository().all()

    @classmethod
    def string(
        cls,
        key: str,
        default: str | Callable[[], str] | None = None,
    ) -> str:
        """Retrieve a string value using Titanspan type validation.

        Args:
            key: Configuration path.
            default: Optional typed value or lazy callback.

        Returns:
            The resolved string value.

        Raises:
            ConfigValueError: If the value does not have the required type.
        """
        return cls._typed_repository().string(key, default)

    @classmethod
    def integer(
        cls,
        key: str,
        default: int | Callable[[], int] | None = None,
    ) -> int:
        """Retrieve a strict integer value.

        Args:
            key: Configuration path.
            default: Optional typed value or lazy callback.

        Returns:
            The resolved integer value.
        """
        return cls._typed_repository().integer(key, default)

    @classmethod
    def float(
        cls,
        key: str,
        default: float | Callable[[], float] | None = None,
    ) -> float:
        """Retrieve a strict floating-point value.

        Args:
            key: Configuration path.
            default: Optional typed value or lazy callback.

        Returns:
            The resolved float value.
        """
        return cls._typed_repository().float(key, default)

    @classmethod
    def boolean(
        cls,
        key: str,
        default: bool | Callable[[], bool] | None = None,
    ) -> bool:
        """Retrieve a strict boolean value.

        Args:
            key: Configuration path.
            default: Optional typed value or lazy callback.

        Returns:
            The resolved boolean value.
        """
        return cls._typed_repository().boolean(key, default)

    @classmethod
    def array(
        cls,
        key: str,
        default: ConfigArray | Callable[[], ConfigArray] | None = None,
    ) -> ConfigArray:
        """Retrieve a mapping or list without coercion.

        Args:
            key: Configuration path.
            default: Optional array value or lazy callback.

        Returns:
            The resolved mapping or list.
        """
        return cls._typed_repository().array(key, default)

    @classmethod
    def prepend(cls, key: str, value: object) -> None:
        """Prepend a value to a configured list.

        Args:
            key: Dotted path to the list setting.
            value: Value inserted at the beginning.
        """
        cls.repository().prepend(key, value)

    @classmethod
    def push(cls, key: str, value: object) -> None:
        """Append a value to a configured list.

        Args:
            key: Dotted path to the list setting.
            value: Value appended at the end.
        """
        cls.repository().push(key, value)

    @classmethod
    def macro(
        cls,
        name: str,
        callback: Callable[..., object],
    ) -> None:
        """Register a macro on the active configuration repository.

        Args:
            name: Public macro name used by explicit invocation.
            callback: Callable stored in the repository's shared registry.
        """
        cls._macro_repository().macro(name, callback)

    @classmethod
    def mixin(cls, mixin: object, replace: bool = True) -> None:
        """Register callback factories from a mixin object.

        Args:
            mixin: Object whose callable methods return macro callbacks.
            replace: Whether existing macro names may be replaced.
        """
        cls._macro_repository().mixin(mixin, replace)

    @classmethod
    def has_macro(cls, name: str) -> bool:
        """Check whether a macro exists on the canonical repository class.

        Args:
            name: Macro name to inspect.

        Returns:
            Whether the repository class can resolve the macro.
        """
        return cls._macro_repository().has_macro(name)

    @classmethod
    def flush_macros(cls) -> None:
        """Clear macros registered directly on the repository class.

        Inherited macros remain available until their owning class is flushed.
        """
        cls._macro_repository().flush_macros()

    @classmethod
    def call_macro(
        cls,
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Invoke a registered macro without dynamic facade attributes.

        Args:
            name: Registered macro name.
            *args: Positional callback values.
            **kwargs: Named callback values.

        Returns:
            The value returned by the macro callback.
        """
        return cls._macro_repository().call_macro(name, *args, **kwargs)

    @classmethod
    @contextmanager
    def override(
        cls,
        values: Mapping[str, object],
    ) -> Generator[None, None, None]:
        """Apply context-local overrides to a native Repository.

        Args:
            values: Dotted paths and values visible within this scope.

        Yields:
            Control while the temporary values are active.

        Raises:
            ConfigContextError: If the active implementation does not support
                Titanspan's scoped override semantics.
        """
        repository = cls.repository()
        if not isinstance(repository, ScopedConfigOverrides):
            raise ConfigCapabilityError(_SCOPED_OVERRIDE_CAPABILITY)
        with repository.override(values):
            yield

    @classmethod
    def _typed_repository(cls) -> TypedConfigReader:
        """Resolve the optional typed-access configuration capability.

        Returns:
            The active typed configuration reader.

        Raises:
            ConfigCapabilityError: If the active repository lacks typed reads.
        """
        repository = cls.repository()
        if not isinstance(repository, TypedConfigReader):
            raise ConfigCapabilityError(_TYPED_RETRIEVAL_CAPABILITY)
        return repository

    @classmethod
    def _macro_repository(cls) -> ConfigMacroRegistry:
        """Resolve the optional runtime macro capability.

        Returns:
            The active repository's macro registry.

        Raises:
            ConfigCapabilityError: If macros are not supported.
        """
        repository = cls.repository()
        if not isinstance(repository, ConfigMacroRegistry):
            raise ConfigCapabilityError(_MACRO_CAPABILITY)
        return repository


__all__ = ["Config"]
