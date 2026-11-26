"""Declare dependency selection metadata for ``typing.Annotated`` values.

Metadata remains Titanspan-owned and is translated into ordinary dependency
keys while a private graph is composed.
"""

from dataclasses import dataclass

from titanspan.container.exceptions import BindingError

_EMPTY_INJECTION_NAME_ERROR = (
    "Injection names and configuration paths cannot be empty."
)


@dataclass(frozen=True, slots=True)
class Inject:
    """Select a concrete service implementation for one constructor value.

    Attributes:
        implementation: Concrete type resolved for the annotated parameter.
    """

    implementation: type[object]


@dataclass(frozen=True, slots=True)
class FromConfig:
    """Select a value from the registered configuration reader contract.

    Attributes:
        key: Dotted path retrieved from the active configuration service.
    """

    key: str

    def __post_init__(self) -> None:
        """Reject empty paths before graph composition begins.

        Raises:
            BindingError: If the configured path is empty.
        """
        if not self.key:
            raise BindingError(_EMPTY_INJECTION_NAME_ERROR)


@dataclass(frozen=True, slots=True)
class Named:
    """Resolve a dependency through a registered service alias.

    Attributes:
        name: Alias selected from the active container registry.
    """

    name: str

    def __post_init__(self) -> None:
        """Reject empty service aliases during declaration.

        Raises:
            BindingError: If the alias is empty.
        """
        if not self.name:
            raise BindingError(_EMPTY_INJECTION_NAME_ERROR)


@dataclass(frozen=True, slots=True)
class Tagged:
    """Resolve all services registered under one ordered tag.

    Attributes:
        name: Tag whose service keys are resolved for the parameter.
    """

    name: str

    def __post_init__(self) -> None:
        """Reject empty tag names during declaration.

        Raises:
            BindingError: If the tag is empty.
        """
        if not self.name:
            raise BindingError(_EMPTY_INJECTION_NAME_ERROR)


__all__ = ["FromConfig", "Inject", "Named", "Tagged"]
