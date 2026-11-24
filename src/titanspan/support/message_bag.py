r"""Store and format keyed validation and application messages.

The implementation follows Laravel's ``Illuminate\\Support\\MessageBag``
contract while using Python mappings, explicit aliases, and standard JSON
serialization.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Self, cast

from titanspan.support.str import Str

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.contracts.message_bag import MessageKey, MessageProvider

_DEFAULT_FORMAT = ":message"
_JSON_PRETTY_PRINT = 128
_JSON_UNESCAPED_UNICODE = 256
_MESSAGE_KEY_ERROR = "Message keys must be strings or integers."
_MESSAGE_VALUE_ERROR = "Messages must be strings."
_MESSAGE_INPUT_ERROR = "Message input must be a mapping or iterable."


class MessageBag:
    """Manage unique messages grouped by field or application key.

    Construction removes duplicate messages within each key. Explicit
    :meth:`add` operations also preserve uniqueness; :meth:`merge` follows
    Laravel's recursive merge behavior and can append repeated messages.

    Attributes:
        _messages: The internal ordered mapping of keys to message lists.
    """

    def __init__(
        self,
        messages: object = None,
    ) -> None:
        """Create a bag from field names and one or more string messages.

        Args:
            messages: Optional keyed messages. A string is treated as one
                message; other iterables are treated as message sequences.

        Raises:
            TypeError: If a key or message is not a string.
        """
        self._messages: dict[MessageKey, list[str]] = {}
        self._format = _DEFAULT_FORMAT
        if messages is None:
            return
        if isinstance(messages, Mapping):
            entries = cast("Mapping[object, object]", messages).items()
        elif isinstance(messages, Iterable) and not isinstance(
            messages,
            (str, bytes, bytearray),
        ):
            entries = enumerate(cast("Iterable[object]", messages))
        else:
            raise TypeError(_MESSAGE_INPUT_ERROR)
        for key, raw_messages in entries:
            values = self._normalize_messages(raw_messages)
            self._validate_message(key, "")
            self._messages[cast("MessageKey", key)] = list(
                dict.fromkeys(values),
            )

    def keys(self) -> list[MessageKey]:
        """Return field keys in insertion order.

        Returns:
            A new list of message keys.
        """
        return list(self._messages)

    def add(self, key: MessageKey, message: str) -> Self:
        """Add a message only when the same message is not already present.

        Args:
            key: The field or message group receiving the message.
            message: The text to add.

        Returns:
            This instance for fluent chaining.

        Raises:
            TypeError: If ``key`` or ``message`` is not a string.
        """
        self._validate_message(key, message)
        bucket = self._messages.setdefault(key, [])
        if message not in bucket:
            bucket.append(message)
        return self

    def add_if(
        self,
        condition: bool,
        key: MessageKey,
        message: str,
    ) -> Self:
        """Add a message when ``condition`` is true.

        Args:
            condition: Whether the message should be added.
            key: The field or message group receiving the message.
            message: The text to add when selected.

        Returns:
            This instance for fluent chaining.
        """
        if condition:
            self.add(key, message)
        return self

    def addIf(self, condition: bool, key: MessageKey, message: str) -> Self:
        """Add a message through Laravel's camelCase method name.

        Args:
            condition: Whether the message should be added.
            key: The field or message group receiving the message.
            message: The text to add when selected.

        Returns:
            This instance for fluent chaining.
        """
        return self.add_if(condition, key, message)

    def merge(
        self,
        messages: Mapping[object, object] | MessageProvider,
    ) -> Self:
        """Append messages from another bag or mapping.

        Unlike :meth:`add`, merge preserves duplicates to match PHP's
        ``array_merge_recursive`` behavior for repeated field values.

        Args:
            messages: A message provider or mapping of keys to message values.

        Returns:
            This instance after merging.

        Raises:
            TypeError: If an input key or message is not a string.
        """
        if isinstance(messages, Mapping):
            incoming = messages
        else:
            incoming = messages.get_message_bag().get_messages()
        for key, raw_messages in incoming.items():
            values = self._normalize_messages(raw_messages)
            for message in values:
                self._validate_message(key, message)
                self._messages.setdefault(cast("MessageKey", key), []).append(
                    message,
                )
        return self

    def has(
        self,
        key: MessageKey | Iterable[MessageKey] | None = None,
        *more_keys: MessageKey,
    ) -> bool:
        """Check that messages exist for every requested key.

        Args:
            key: One key, a sequence of keys, or ``None`` for any message.
            *more_keys: Additional keys checked alongside ``key``.

        Returns:
            Whether all selected keys have a non-empty first message.
        """
        if self.is_empty():
            return False
        if key is None:
            return self.any()
        keys: list[MessageKey | None] = (
            [key] if isinstance(key, (str, int)) else list(key)
        )
        keys.extend(more_keys)
        return all(self.first(item) != "" for item in keys)

    def has_any(
        self,
        keys: MessageKey | Iterable[MessageKey] | None = (),
        *more_keys: MessageKey,
    ) -> bool:
        """Check whether at least one requested key has messages.

        Args:
            keys: One field name or an iterable of field names.
            *more_keys: Additional fields checked alongside ``keys``.

        Returns:
            Whether one or more selected keys have messages.
        """
        if self.is_empty():
            return False
        selected = (
            [keys]
            if keys is None or isinstance(keys, (str, int))
            else list(keys)
        )
        selected.extend(more_keys)
        return any(self.has(key) for key in selected)

    def hasAny(
        self,
        keys: MessageKey | Iterable[MessageKey] | None = (),
        *more_keys: MessageKey,
    ) -> bool:
        """Check selected keys using Laravel's camelCase method name.

        Args:
            keys: One field name or an iterable of field names.
            *more_keys: Additional fields checked alongside ``keys``.

        Returns:
            Whether one or more selected keys have messages.
        """
        return self.has_any(keys, *more_keys)

    def missing(
        self,
        key: MessageKey | Iterable[MessageKey] | None,
        *more_keys: MessageKey,
    ) -> bool:
        """Check that none of the requested keys have messages.

        Args:
            key: One field name or an iterable of field names.
            *more_keys: Additional fields checked alongside ``key``.

        Returns:
            Whether all requested keys are missing.
        """
        return not self.has_any(key, *more_keys)

    def first(
        self,
        key: MessageKey | None = None,
        format: str | None = None,
    ) -> str:
        """Return the first formatted message for a field or the whole bag.

        Args:
            key: The field to query, or ``None`` for the first global message.
            format: An optional ``:message``/``:key`` format template.

        Returns:
            The first matching message or an empty string.
        """
        messages = self.all(format) if key is None else self.get(key, format)
        if isinstance(messages, dict):
            for first_group in messages.values():
                return first_group[0] if first_group else ""
            return ""
        return messages[0] if messages else ""

    def get(
        self,
        key: MessageKey,
        format: str | None = None,
    ) -> list[str] | dict[MessageKey, list[str]]:
        """Get formatted messages for a key or wildcard pattern.

        Args:
            key: A field key or Laravel-style wildcard pattern.
            format: An optional message format template.

        Returns:
            A list for an exact key or a mapping for wildcard matches.
        """
        if key in self._messages:
            selected_format = self._check_format(format)
            return self._transform(self._messages[key], selected_format, key)
        if not isinstance(key, str) or "*" not in key:
            return []
        return {
            message_key: self._transform(
                values,
                self._check_format(format),
                message_key,
            )
            for message_key, values in self._messages.items()
            if Str.is_(key, str(message_key))
        }

    def all(self, format: str | None = None) -> list[str]:
        """Return every formatted message in key and insertion order.

        Args:
            format: An optional message format template.

        Returns:
            A flat list of formatted messages.
        """
        selected_format = self._check_format(format)
        return [
            message
            for key, values in self._messages.items()
            for message in self._transform(values, selected_format, key)
        ]

    def unique(self, format: str | None = None) -> list[str]:
        """Return formatted messages with duplicate text removed in order.

        Args:
            format: An optional message format template.

        Returns:
            A list containing the first occurrence of each formatted message.
        """
        return list(dict.fromkeys(self.all(format)))

    def forget(self, key: MessageKey) -> Self:
        """Remove all messages associated with one key.

        Args:
            key: The field or message group to remove.

        Returns:
            This instance for fluent chaining.
        """
        self._messages.pop(key, None)
        return self

    def get_messages(self) -> dict[MessageKey, list[str]]:
        """Return a defensive copy of raw keyed messages.

        Returns:
            A new mapping with new per-key message lists.
        """
        return {key: list(values) for key, values in self._messages.items()}

    def messages(self) -> dict[MessageKey, list[str]]:
        """Return raw messages through Laravel's ``messages`` method.

        Returns:
            A defensive copy of the stored messages.
        """
        return self.get_messages()

    def getMessages(self) -> dict[MessageKey, list[str]]:
        """Return raw messages using Laravel's camelCase method name.

        Returns:
            A defensive copy of raw keyed messages.
        """
        return self.get_messages()

    def messages_copy(self) -> dict[MessageKey, list[str]]:
        """Return raw messages through an explicit non-shadowing API.

        Returns:
            A defensive copy of raw keyed messages.
        """
        return self.get_messages()

    def get_message_bag(self) -> Self:
        """Return this object as a message provider.

        Returns:
            This message bag instance.
        """
        return self

    def getMessageBag(self) -> Self:
        """Return this provider through Laravel's camelCase method name.

        Returns:
            This message bag instance.
        """
        return self.get_message_bag()

    def get_format(self) -> str:
        """Return the configured default message format.

        Returns:
            The active format template.
        """
        return self._format

    def getFormat(self) -> str:
        """Return the configured format using Laravel's method name.

        Returns:
            The active format template.
        """
        return self.get_format()

    def set_format(self, format: str = _DEFAULT_FORMAT) -> Self:
        """Set the default formatting template for future queries.

        Args:
            format: A template supporting ``:message`` and ``:key``.

        Returns:
            This instance for fluent chaining.
        """
        self._format = format
        return self

    def setFormat(self, format: str = _DEFAULT_FORMAT) -> Self:
        """Set the default format using Laravel's camelCase method name.

        Args:
            format: A template supporting ``:message`` and ``:key``.

        Returns:
            This instance for fluent chaining.
        """
        return self.set_format(format)

    def is_empty(self) -> bool:
        """Return whether the bag contains no messages.

        Returns:
            Whether all message groups are empty.
        """
        return self.count() == 0

    def isEmpty(self) -> bool:
        """Check emptiness through Laravel's camelCase method name.

        Returns:
            Whether all message groups are empty.
        """
        return self.is_empty()

    def is_not_empty(self) -> bool:
        """Return whether the bag contains at least one message.

        Returns:
            Whether the bag has any messages.
        """
        return not self.is_empty()

    def isNotEmpty(self) -> bool:
        """Check non-emptiness using Laravel's camelCase method name.

        Returns:
            Whether the bag has any messages.
        """
        return self.is_not_empty()

    def any(self) -> bool:
        """Return whether at least one message exists.

        Returns:
            Whether the message count is non-zero.
        """
        return self.count() > 0

    def count(self) -> int:
        """Return the number of messages across all keys.

        Returns:
            The sum of message list lengths.
        """
        return sum(len(values) for values in self._messages.values())

    def to_array(self) -> dict[MessageKey, list[str]]:
        """Convert the bag to a defensive raw-message mapping.

        Returns:
            A new mapping of field names to messages.
        """
        return self.get_messages()

    def toArray(self) -> dict[MessageKey, list[str]]:
        """Convert to a mapping using Laravel's camelCase method name.

        Returns:
            A new mapping of field names to messages.
        """
        return self.to_array()

    def json_serialize(self) -> dict[MessageKey, list[str]]:
        """Return a JSON-compatible raw-message mapping.

        Returns:
            A new mapping of field names to messages.
        """
        return self.to_array()

    def jsonSerialize(self) -> dict[MessageKey, list[str]]:
        """Return JSON data using Laravel's camelCase method name.

        Returns:
            A new mapping of field names to messages.
        """
        return self.json_serialize()

    def to_json(self, options: int = 0) -> str:
        """Serialize raw messages to JSON.

        Args:
            options: A bitmask supporting pretty printing and Unicode output.

        Returns:
            A JSON string.

        Raises:
            TypeError: If the options or data cannot be serialized.
        """
        indent = 4 if options & _JSON_PRETTY_PRINT else None
        ensure_ascii = not bool(options & _JSON_UNESCAPED_UNICODE)
        separators = None if indent is not None else (",", ":")
        return json.dumps(
            self.json_serialize(),
            indent=indent,
            ensure_ascii=ensure_ascii,
            separators=separators,
            allow_nan=False,
        )

    def toJson(self, options: int = 0) -> str:
        """Serialize messages using Laravel's camelCase method name.

        Args:
            options: A bitmask supporting pretty printing and Unicode output.

        Returns:
            A JSON string.
        """
        return self.to_json(options)

    def to_pretty_json(self, options: int = 0) -> str:
        """Serialize messages as indented JSON.

        Args:
            options: Additional supported JSON option bits.

        Returns:
            An indented JSON string.
        """
        return self.to_json(options | _JSON_PRETTY_PRINT)

    def toPrettyJson(self, options: int = 0) -> str:
        """Serialize indented JSON with Laravel's camelCase method name.

        Args:
            options: Additional supported JSON option bits.

        Returns:
            An indented JSON string.
        """
        return self.to_pretty_json(options)

    def __len__(self) -> int:
        """Return the number of stored messages.

        Returns:
            The total message count.
        """
        return self.count()

    def __str__(self) -> str:
        """Return the compact JSON representation of raw messages.

        Returns:
            The default JSON serialization.
        """
        return self.to_json()

    def _check_format(self, format: str | None) -> str:
        """Choose the explicit format or the configured default.

        Args:
            format: A query-specific format, if provided.

        Returns:
            The selected non-empty format string.
        """
        return format or self._format

    @staticmethod
    def _transform(
        messages: Sequence[str],
        format: str,
        key: MessageKey,
    ) -> list[str]:
        """Replace Laravel message placeholders in each string.

        Args:
            messages: The raw field messages.
            format: The selected output template.
            key: The field key used for ``:key`` substitution.

        Returns:
            Formatted messages in their original order.
        """
        if format == _DEFAULT_FORMAT:
            return list(messages)
        return [
            format.replace(":message", message).replace(":key", str(key))
            for message in messages
        ]

    @staticmethod
    def _validate_message(key: object, message: object) -> None:
        """Ensure message keys and contents follow the public string API.

        Args:
            key: The candidate field key.
            message: The candidate message.

        Raises:
            TypeError: If either value is not a string.
        """
        if not isinstance(key, (str, int)) or isinstance(key, bool):
            raise TypeError(_MESSAGE_KEY_ERROR)
        if not isinstance(message, str):
            raise TypeError(_MESSAGE_VALUE_ERROR)

    @staticmethod
    def _normalize_messages(messages: object) -> list[str]:
        """Validate one message or an iterable of message values.

        Args:
            messages: A single string or an iterable of strings.

        Returns:
            Validated messages in their input order.

        Raises:
            TypeError: If the input is not a string or iterable of strings.
        """
        if isinstance(messages, str):
            return [messages]
        if not isinstance(messages, Iterable):
            raise TypeError(_MESSAGE_VALUE_ERROR)
        values = list(cast("Iterable[object]", messages))
        for message in values:
            MessageBag._validate_message("", message)
        return cast("list[str]", values)


__all__ = ["MessageBag"]
