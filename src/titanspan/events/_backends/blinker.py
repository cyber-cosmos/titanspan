"""Provide ordered registration through Blinker public signal methods.

The adapter adds ordering through Blinker public registration hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blinker import ANY, Signal

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Set


class _OrderedSet(set[object]):
    """Retain insertion order for Blinker receiver identifiers.

    Blinker exposes ``set_class`` as its supported ordering customization.
    This set subclass keeps that dependency-owned registration store intact.
    """

    def __init__(self, values: Iterable[object] = ()) -> None:
        """Create an ordered set from unique receiver identifiers.

        Args:
            values: Existing identifiers inserted in iteration order.
        """
        super().__init__()
        self._order: dict[object, None] = {}
        for value in values:
            self.add(value)

    def add(self, value: object) -> None:
        """Add an identifier while preserving its first insertion position.

        Args:
            value: Hashable identifier stored by the signal.
        """
        super().add(value)
        self._order[value] = None

    def discard(self, value: object) -> None:
        """Remove an identifier from the set and ordered index.

        Args:
            value: Identifier to remove if it exists.
        """
        super().discard(value)
        self._order.pop(value, None)

    def copy(self) -> _OrderedSet:
        """Return an independent set with the same iteration order.

        Returns:
            An ordered copy used by Blinker receiver snapshots.
        """
        return type(self)(self)

    def __iter__(self) -> Iterator[object]:
        """Yield receiver identifiers in registration order.

        Returns:
            An iterator over insertion-ordered identifiers.
        """
        return iter(self._order)

    def __or__(self, other: Set[object]) -> _OrderedSet:
        """Combine sets without changing earlier receiver order.

        Args:
            other: Set of receiver identifiers to append.

        Returns:
            A new ordered set containing the union.
        """
        return type(self)([*self, *other])


class OrderedSignal(Signal):
    """Use a local ordered-set policy for one Titanspan dispatcher.

    Receiver snapshots preserve registration order for dispatch.
    """

    set_class = _OrderedSet

    def receivers_for_any(self) -> tuple[Callable[..., object], ...]:
        """Snapshot receivers connected to every event sender.

        Returns:
            Strong receiver references in registration order.
        """
        return tuple(self.receivers_for(ANY))


__all__ = ["OrderedSignal"]
