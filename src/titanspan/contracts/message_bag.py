"""Define contracts for keyed messages and message providers.

Validation, HTTP, and presentation modules can share this API without
depending on a concrete Support implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Self

type MessageKey = str | int


@runtime_checkable
class MessageProvider(Protocol):
    """Expose a message bag through a framework-independent contract.

    Implementations may return their native bag type as long as it follows
    :class:`MessageBagData`.
    """

    def get_message_bag(self) -> MessageBagData:
        """Return the provider's keyed message representation.

        Returns:
            An object implementing :class:`MessageBagData`.
        """
        ...


@runtime_checkable
class MessageBagData(Protocol):
    """Describe the public operations of a keyed message bag.

    The protocol mirrors the Laravel message-bag contract and also includes
    Python snake_case spellings for IDE discovery and typed callers.
    """

    def keys(self) -> list[MessageKey]:
        """Return keys in insertion order.

        Returns:
            A list of stored keys.
        """
        ...

    def add(self, key: MessageKey, message: str) -> Self:
        """Add one unique message to a key.

        Args:
            key: The message group key.
            message: The message to add.

        Returns:
            This bag for fluent chaining.
        """
        ...

    def merge(
        self,
        messages: Mapping[object, object] | MessageProvider,
    ) -> Self:
        """Append messages supplied by a mapping or provider.

        Args:
            messages: The source messages.

        Returns:
            This bag for fluent chaining.
        """
        ...

    def has(
        self,
        key: MessageKey | Iterable[MessageKey] | None = None,
        *more_keys: MessageKey,
    ) -> bool:
        """Check that every selected key has a non-empty first message.

        Args:
            key: One key, several keys, or ``None`` for any message.
            *more_keys: Additional keys to check.

        Returns:
            Whether every selected key has a message.
        """
        ...

    def has_any(
        self,
        keys: MessageKey | Iterable[MessageKey] | None = (),
        *more_keys: MessageKey,
    ) -> bool:
        """Check whether one or more selected keys have messages.

        Args:
            keys: One key, several keys, or an iterable of keys.
            *more_keys: Additional keys to check.

        Returns:
            Whether one selected key has a message.
        """
        ...

    def hasAny(
        self,
        keys: MessageKey | Iterable[MessageKey] | None = (),
        *more_keys: MessageKey,
    ) -> bool:
        """Check keys using Laravel's camelCase method name.

        Args:
            keys: One key, several keys, or an iterable of keys.
            *more_keys: Additional keys to check.

        Returns:
            Whether one selected key has a message.
        """
        ...

    def missing(
        self,
        key: MessageKey | Iterable[MessageKey] | None,
        *more_keys: MessageKey,
    ) -> bool:
        """Check whether every selected key is missing.

        Args:
            key: One key, several keys, or an iterable of keys.
            *more_keys: Additional keys to check.

        Returns:
            Whether none of the keys have a message.
        """
        ...

    def first(
        self,
        key: MessageKey | None = None,
        format: str | None = None,
    ) -> str:
        """Return the first formatted message for a key or the whole bag.

        Args:
            key: The key to query, or ``None`` for the first global message.
            format: An optional formatting template.

        Returns:
            The first matching message or an empty string.
        """
        ...

    def get(
        self,
        key: MessageKey,
        format: str | None = None,
    ) -> list[str] | dict[MessageKey, list[str]]:
        """Return messages for an exact key or wildcard pattern.

        Args:
            key: The field key or wildcard pattern.
            format: An optional formatting template.

        Returns:
            The matching formatted messages.
        """
        ...

    def all(self, format: str | None = None) -> list[str]:
        """Return all messages in insertion order.

        Args:
            format: An optional formatting template.

        Returns:
            A flat list of formatted messages.
        """
        ...

    def unique(self, format: str | None = None) -> list[str]:
        """Return unique messages in insertion order.

        Args:
            format: An optional formatting template.

        Returns:
            A flat list without duplicate formatted messages.
        """
        ...

    def forget(self, key: MessageKey) -> Self:
        """Remove all messages associated with one key.

        Args:
            key: The key to remove.

        Returns:
            This bag for fluent chaining.
        """
        ...

    def messages(self) -> Mapping[MessageKey, list[str]]:
        """Return a read-only view or copy of raw messages.

        Returns:
            The mapping of keys to messages.
        """
        ...

    def get_messages(self) -> Mapping[MessageKey, list[str]]:
        """Return raw messages through the Python method spelling.

        Returns:
            The mapping of keys to messages.
        """
        ...

    def getMessages(self) -> Mapping[MessageKey, list[str]]:
        """Return raw messages through Laravel's camelCase spelling.

        Returns:
            The mapping of keys to messages.
        """
        ...

    def get_format(self) -> str:
        """Return the configured default message format.

        Returns:
            The current formatting template.
        """
        ...

    def getFormat(self) -> str:
        """Return the format through Laravel's camelCase method name.

        Returns:
            The current formatting template.
        """
        ...

    def set_format(self, format: str = ":message") -> Self:
        """Set the default message format.

        Args:
            format: A template supporting ``:message`` and ``:key``.

        Returns:
            This bag for fluent chaining.
        """
        ...

    def setFormat(self, format: str = ":message") -> Self:
        """Set the format through Laravel's camelCase method name.

        Args:
            format: A template supporting ``:message`` and ``:key``.

        Returns:
            This bag for fluent chaining.
        """
        ...

    def is_empty(self) -> bool:
        """Check whether the bag has no messages.

        Returns:
            Whether the bag is empty.
        """
        ...

    def isEmpty(self) -> bool:
        """Check emptiness through Laravel's camelCase method name.

        Returns:
            Whether the bag is empty.
        """
        ...

    def is_not_empty(self) -> bool:
        """Check whether the bag contains messages.

        Returns:
            Whether the bag is non-empty.
        """
        ...

    def isNotEmpty(self) -> bool:
        """Check non-emptiness through Laravel's camelCase method name.

        Returns:
            Whether the bag is non-empty.
        """
        ...


__all__ = ["MessageBagData", "MessageKey", "MessageProvider"]
