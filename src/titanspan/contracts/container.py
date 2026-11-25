"""Define backend-neutral contracts for asynchronous service resolution.

The protocol isolates dependency consumers from a particular container
implementation while leaving registration and scope construction to the
application's composition root.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AsyncServiceContainer(Protocol):
    """Resolve typed services and finalize owned asynchronous resources.

    Resolution uses the requested class as its service key and preserves its
    concrete type for static callers. Implementations own scope-specific
    resource finalization. A container must be closed after its owning
    application or execution scope ends.

    Runtime protocol checks verify required attribute presence only. They do
    not validate generic signatures, scope isolation, or cleanup behavior.
    """

    async def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Resolve a service from the active dependency scope.

        Args:
            service: The class used as the dependency key.

        Returns:
            An instance compatible with the requested service type.

        Notes:
            Adapters should translate backend resolution errors into
            framework-owned errors before exposing a public implementation.
        """
        ...

    async def close(self) -> None:
        """Finalize resources owned by this dependency scope.

        Implementations should propagate cleanup failures and preserve
        cancellation behavior. Callers must not assume that repeated close
        operations are safe unless the concrete implementation documents it.

        Notes:
            Backends must not expose their exception classes as Titanspan
            public contract types.
        """
        ...


__all__ = ["AsyncServiceContainer"]
