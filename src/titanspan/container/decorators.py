"""Declare service lifetimes without changing class identity.

Decorators attach immutable metadata for the active container to inspect while
building a dependency graph. They never register against a global container.
"""

from collections.abc import Callable

from titanspan.container.binding import BindingDeclaration, Lifetime
from titanspan.container.exceptions import BindingError
from titanspan.container.scope import Scope

_DECLARATION_ATTRIBUTE = "__titanspan_binding_declaration__"
_APPLICATION_SCOPED_ERROR = (
    "Use singleton for application-owned class declarations."
)
_CONFLICTING_DECLARATION_ERROR = (
    "A service class cannot declare conflicting lifetimes."
)


def singleton[ServiceT](service: type[ServiceT]) -> type[ServiceT]:
    """Declare an application-owned cache lifetime for a service class.

    The decorator preserves the class object and stores metadata only on that
    class. Each container owns its own resolved instance.

    Args:
        service: Class to reuse for the owning application container.

    Returns:
        The same service class with immutable lifetime metadata.

    Raises:
        BindingError: If a conflicting lifetime was already declared.
    """
    return _declare(service, Lifetime.SINGLETON, Scope.APPLICATION)


def scoped[ServiceT](
    scope: Scope = Scope.REQUEST,
) -> Callable[[type[ServiceT]], type[ServiceT]]:
    """Declare that a class instance belongs to one execution scope.

    Args:
        scope: Active execution scope that owns the cached service instance.
            Application scope is represented by the ``singleton`` decorator.

    Returns:
        A class decorator that preserves the decorated class identity.

    Raises:
        BindingError: If application scope is selected.
    """
    if scope is Scope.APPLICATION:
        raise BindingError(_APPLICATION_SCOPED_ERROR)

    def decorate(service: type[ServiceT]) -> type[ServiceT]:
        """Attach the selected lifecycle declaration to one service class.

        Args:
            service: Class whose instances use the selected scope.

        Returns:
            The same service class with immutable lifetime metadata.
        """
        return _declare(service, Lifetime.SCOPED, scope)

    return decorate


def binding_declaration(
    service: type[object],
) -> BindingDeclaration | None:
    """Return lifetime metadata declared directly on a service class.

    Args:
        service: Class inspected during dependency graph composition.

    Returns:
        The native declaration, or ``None`` when the class has no metadata.
    """
    declaration = vars(service).get(_DECLARATION_ATTRIBUTE)
    if isinstance(declaration, BindingDeclaration):
        return declaration
    return None


def _declare[ServiceT](
    service: type[ServiceT],
    lifetime: Lifetime,
    scope: Scope,
) -> type[ServiceT]:
    """Attach one stable declaration without wrapping the original class.

    Args:
        service: Class receiving container metadata.
        lifetime: Cache behavior selected by the decorator.
        scope: Lifecycle owner for cached values.

    Returns:
        The original class object.

    Raises:
        BindingError: If another decorator declared a different lifetime.
    """
    declaration = BindingDeclaration(lifetime=lifetime, scope=scope)
    existing = binding_declaration(service)
    if existing is not None and existing != declaration:
        raise BindingError(_CONFLICTING_DECLARATION_ERROR)
    setattr(service, _DECLARATION_ATTRIBUTE, declaration)
    return service


__all__ = ["binding_declaration", "scoped", "singleton"]
