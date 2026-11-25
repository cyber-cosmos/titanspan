"""Define general-purpose data and presentation contracts.

These protocols describe behavior without importing the Support module or
any rendering, HTTP, or serialization backend.
"""

from collections.abc import Iterator
from typing import Protocol, TypeVar, runtime_checkable

from titanspan.contracts.deferring_displayable_value import (
    DeferringDisplayableValue,
    LaravelDeferringDisplayableValue,
)
from titanspan.contracts.htmlable import Htmlable, LaravelHtmlable
from titanspan.contracts.message_bag import (
    MessageBagData,
    MessageKey,
    MessageProvider,
)

type ArrayKey = str | int
KeyT = TypeVar("KeyT", bound=ArrayKey)
ValueT = TypeVar("ValueT")
RequestT_contra = TypeVar("RequestT_contra", contravariant=True)
ResponseT_co = TypeVar("ResponseT_co", covariant=True)


@runtime_checkable
class Arrayable(Protocol[KeyT, ValueT]):
    """Describe an object that exports a typed mapping representation.

    Implementations return a new or otherwise caller-safe mapping. Keys use
    Python's string and integer equivalents of PHP array keys. This protocol
    does not prescribe recursive conversion of nested values.
    """

    def to_array(self) -> dict[KeyT, ValueT]:
        """Convert the object to a Python mapping.

        Returns:
            A mapping of supported keys to values.
        """
        ...


@runtime_checkable
class LaravelArrayable(Protocol[KeyT, ValueT]):
    """Accept objects that retain Laravel's ``toArray`` method spelling.

    This compatibility protocol is separate so Python implementations do not
    need to implement duplicate camelCase and snake_case methods.
    """

    def toArray(self) -> dict[KeyT, ValueT]:
        """Convert the object using the upstream method spelling.

        Returns:
            A mapping of supported keys to values.
        """
        ...


@runtime_checkable
class Jsonable(Protocol):
    """Describe an object that provides its own JSON text representation.

    The protocol concerns the returned JSON document only. It does not
    prescribe serializer options or authorize arbitrary object serialization.
    """

    def to_json(self) -> str:
        """Return this object's JSON representation.

        Returns:
            A valid JSON document encoded as Unicode text.
        """
        ...


@runtime_checkable
class LaravelJsonable(Protocol):
    """Accept the upstream ``toJson`` method and its integer options value.

    The integer is Laravel/PHP encoding flags and has no implicit mapping to
    Python's JSON encoder options.
    """

    def toJson(self, options: int = 0) -> str:
        """Return a JSON representation using upstream encoding flags.

        Args:
            options: PHP JSON encoding flags understood by the implementation.

        Returns:
            A valid JSON document encoded as Unicode text.
        """
        ...


@runtime_checkable
class Renderable(Protocol):
    """Describe an object that renders itself to text.

    Rendering is synchronous at this contract boundary. Implementations that
    perform I/O should provide an explicit asynchronous API separately.
    """

    def render(self) -> str:
        """Render the object to a Unicode string.

        Returns:
            The completed textual representation.
        """
        ...


@runtime_checkable
class Responsable(Protocol[RequestT_contra, ResponseT_co]):
    """Create an application response from a caller-owned request value.

    Generic request and response parameters preserve application-specific
    types without importing FastAPI, Starlette, or another HTTP implementation.
    """

    def to_response(self, request: RequestT_contra) -> ResponseT_co:
        """Create a response for the supplied request.

        Args:
            request: Request value supplied by the owning HTTP integration.

        Returns:
            The response type selected by the owning application.
        """
        ...


@runtime_checkable
class LaravelResponsable(Protocol[RequestT_contra, ResponseT_co]):
    """Accept the upstream response method without requiring a Python alias.

    Request and response types remain generic so this protocol does not expose
    a backend-specific HTTP request or response object.
    """

    def toResponse(self, request: RequestT_contra) -> ResponseT_co:
        """Create a response using Laravel's original method spelling.

        Args:
            request: Request value supplied by the owning HTTP integration.

        Returns:
            The response type selected by the owning application.
        """
        ...


@runtime_checkable
class ValidatedData(Arrayable[KeyT, ValueT], Protocol[KeyT, ValueT]):
    """Describe validated values that support mapping-style read access.

    The protocol is a type boundary only; it does not perform validation or
    establish trust in values that were not validated by their producer.
    """

    def __getitem__(self, key: KeyT) -> ValueT:
        """Retrieve one validated value.

        Args:
            key: The validated field key.

        Returns:
            The value associated with the requested key.
        """
        ...

    def __iter__(self) -> Iterator[KeyT]:
        """Iterate the validated field keys.

        Yields:
            Keys in the implementation's documented iteration order.
        """
        ...

    def __len__(self) -> int:
        """Return the number of available validated fields.

        Returns:
            The number of fields exposed by this value.
        """
        ...


__all__ = [
    "ArrayKey",
    "Arrayable",
    "DeferringDisplayableValue",
    "Htmlable",
    "Jsonable",
    "LaravelArrayable",
    "LaravelDeferringDisplayableValue",
    "LaravelHtmlable",
    "LaravelJsonable",
    "LaravelResponsable",
    "MessageBagData",
    "MessageKey",
    "MessageProvider",
    "Renderable",
    "Responsable",
    "ValidatedData",
]
