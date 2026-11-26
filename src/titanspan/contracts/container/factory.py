"""Describe native synchronous and asynchronous resource factory callables.

Factories may return a value, an awaitable value, or a managed generator.
The container owns generator finalization according to the selected scope.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

type ServiceFactory[ServiceT] = Callable[
    ...,
    ServiceT
    | Awaitable[ServiceT]
    | Iterator[ServiceT]
    | AsyncIterator[ServiceT],
]

type ServiceExtension[ServiceT] = Callable[
    [ServiceT],
    ServiceT | Awaitable[ServiceT],
]

__all__ = ["ServiceExtension", "ServiceFactory"]
