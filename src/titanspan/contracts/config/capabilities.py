"""Define optional, capability-oriented configuration contracts.

Implementations may provide typed access, scoped mutation, diagnostics, and
macro registration independently of the basic repository contract.
"""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from titanspan.contracts.config.repository import ConfigArray


@runtime_checkable
class TypedConfigReader(Protocol):
    """Validate and return values through explicit typed accessors.

    Values are validated without coercion. Missing values use a supplied
    typed fallback, and error messages must not include the rejected value.
    """

    def string(
        self,
        key: str,
        default: str | Callable[[], str] | None = None,
    ) -> str:
        """Read a string value without coercion.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            A validated string.
        """
        ...

    def integer(
        self,
        key: str,
        default: int | Callable[[], int] | None = None,
    ) -> int:
        """Read an integer while rejecting booleans and other numeric types.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            A validated integer.
        """
        ...

    def float(
        self,
        key: str,
        default: float | Callable[[], float] | None = None,
    ) -> float:
        """Read a floating-point value without coercion.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            A validated float.
        """
        ...

    def boolean(
        self,
        key: str,
        default: bool | Callable[[], bool] | None = None,
    ) -> bool:
        """Read a boolean value without treating integers as booleans.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            A validated boolean.
        """
        ...

    def array(
        self,
        key: str,
        default: ConfigArray | Callable[[], ConfigArray] | None = None,
    ) -> ConfigArray:
        """Read a mapping or list without coercion.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            A validated mapping or list.
        """
        ...


@runtime_checkable
class ScopedConfigOverrides(Protocol):
    """Apply task-local temporary configuration mutations.

    Each scope restores its previous layer after normal return, failure, or
    cancellation. Mutation within a scope does not alter base configuration.
    """

    def override(
        self,
        values: Mapping[str, object],
    ) -> AbstractContextManager[None]:
        """Create an execution-local override scope.

        Args:
            values: Dotted paths or nested mappings applied temporarily.

        Returns:
            A synchronous context manager that restores prior values.
        """
        ...


@runtime_checkable
class ConfigDiagnostics(Protocol):
    """Expose configuration for diagnostics with secret values redacted.

    This capability is separate from ordinary reads so inspection tools do
    not require every repository to implement Titanspan's redaction policy.
    """

    def redacted(self) -> Mapping[str, object]:
        """Return a safe snapshot suitable for logs or CLI output.

        Returns:
            A bounded mapping with recognized credentials masked.
        """
        ...


@runtime_checkable
class ConfigMacroRegistry(Protocol):
    """Expose optional runtime macro registration capabilities.

    Macro implementations define collision behavior and keep registration
    scoped to their owning class or repository type.
    """

    @classmethod
    def macro(
        cls,
        name: str,
        callback: Callable[..., object],
    ) -> None:
        """Register an explicitly invoked macro callback.

        Args:
            name: Macro name used by the explicit invocation method.
            callback: Callable stored by the implementation.
        """
        ...

    @classmethod
    def mixin(
        cls,
        mixin: object,
        replace: bool = True,
    ) -> None:
        """Register macros supplied by a mixin object.

        Args:
            mixin: Object exposing callback factories.
            replace: Whether existing macro names can be replaced.
        """
        ...

    @classmethod
    def has_macro(cls, name: str) -> bool:
        """Check whether a macro name has been registered.

        Args:
            name: Name to inspect.

        Returns:
            Whether an implementation can invoke the name.
        """
        ...

    @classmethod
    def flush_macros(cls) -> None:
        """Remove macros owned by the current registration class.

        Inherited registrations remain associated with their defining class.
        """
        ...

    def call_macro(
        self,
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Invoke a macro without dynamic attribute forwarding.

        Args:
            name: Registered macro name.
            *args: Positional callback values.
            **kwargs: Keyword callback values.

        Returns:
            The callback result.
        """
        ...


__all__ = [
    "ConfigDiagnostics",
    "ConfigMacroRegistry",
    "ScopedConfigOverrides",
    "TypedConfigReader",
]
