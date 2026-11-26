"""Provide an immutable-by-default fluent wrapper for Python strings.

Transformations delegate to :class:`Str`; predicate and extraction methods
retain their native return types. Integer offsets remain mutable through
Python's standard item access methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from titanspan.support.conditionable import Conditionable
from titanspan.support.helpers import blank
from titanspan.support.html_string import HtmlString
from titanspan.support.macroable import Macroable
from titanspan.support.str import Str
from titanspan.support.tappable import Tappable

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Iterable, Mapping

_INDEX_TYPE_ERROR = "string offsets must be integers"
_INDEX_RANGE_ERROR = "string offset out of range"
_INDEX_CHARACTER_ERROR = "replacement must contain one code point"
_LINE_COUNT_ERROR = "count must be non-negative"


class Stringable(Macroable, Conditionable, Tappable):
    """Wrap a string with explicit, chainable transformation methods.

    Transformations return a new instance, while integer offset assignment
    and deletion update the current instance. Predicates and extraction
    methods return ordinary Python values. The class shares Titanspan's
    macro and conditional mixins without dynamic method lookup.

    Attributes:
        _value: The current string value.

    Notes:
        Python string indexing uses Unicode code points.
    """

    def __init__(self, value: str = "") -> None:
        """Create a fluent value from a Python string.

        Args:
            value: The string to wrap.
        """
        self._value = value

    def _new(self, value: str) -> Self:
        """Construct the current concrete type for a transformed value.

        Args:
            value: The transformed string.

        Returns:
            A new instance of this concrete class.
        """
        return type(self)(value)

    def value(self) -> str:
        """Return the underlying string value.

        Returns:
            The current string.
        """
        return self._value

    def to_string(self) -> str:
        """Return the underlying string for explicit conversion.

        Returns:
            The current string.
        """
        return self._value

    def __str__(self) -> str:
        """Return the wrapped text for Python string interoperability.

        Returns:
            The current string.
        """
        return self._value

    def __repr__(self) -> str:
        """Return an unambiguous constructor-style representation.

        Returns:
            A representation containing the wrapped string.
        """
        return f"{type(self).__name__}({self._value!r})"

    def __len__(self) -> int:
        """Return the number of Unicode code points in the value.

        Returns:
            The Python string length.
        """
        return len(self._value)

    def __getitem__(self, index: int | slice) -> str:
        """Read a character or slice using Python indexing rules.

        Args:
            index: An integer index or slice.

        Returns:
            The selected string content.
        """
        if isinstance(index, bool):
            raise TypeError(_INDEX_TYPE_ERROR)
        if isinstance(index, int):
            return self._value[self._checked_index(index)]
        return self._value[index]

    def __setitem__(self, index: int, character: str) -> None:
        """Replace one Unicode code point at an integer offset.

        Args:
            index: The character position, allowing negative indexing.
            character: Exactly one Unicode code point.

        Raises:
            IndexError: If the index lies outside the string.
            TypeError: If the index or replacement has an unsupported type.
            ValueError: If the replacement is not one code point.
        """
        position = self._checked_index(index)
        if len(character) != 1:
            raise ValueError(_INDEX_CHARACTER_ERROR)
        self._value = (
            self._value[:position] + character + self._value[position + 1 :]
        )

    def __delitem__(self, index: int) -> None:
        """Delete one Unicode code point at an integer offset.

        Args:
            index: The character position, allowing negative indexing.

        Raises:
            IndexError: If the index lies outside the string.
            TypeError: If the index is not an integer.
        """
        position = self._checked_index(index)
        self._value = self._value[:position] + self._value[position + 1 :]

    def _checked_index(self, index: int) -> int:
        """Normalize an integer index and reject booleans explicitly.

        Args:
            index: The index to validate.

        Returns:
            A non-negative index within the current string.

        Raises:
            IndexError: If the index lies outside the string.
            TypeError: If the value is not an integer index.
        """
        if isinstance(index, bool):
            raise TypeError(_INDEX_TYPE_ERROR)
        position = index if index >= 0 else len(self._value) + index
        if position < 0 or position >= len(self._value):
            raise IndexError(_INDEX_RANGE_ERROR)
        return position

    def offset_exists(self, offset: object) -> bool:
        """Check whether an integer character offset exists.

        Args:
            offset: A candidate integer offset.

        Returns:
            Whether the offset selects a character.
        """
        return (
            isinstance(offset, int)
            and not isinstance(offset, bool)
            and -len(self._value) <= offset < len(self._value)
        )

    def after(self, search: str) -> Self:
        """Return a new value containing text after the first delimiter.

        Args:
            search: The delimiter to find.

        Returns:
            A new fluent string.
        """
        return self._new(Str.after(self._value, search))

    def after_last(self, search: str) -> Self:
        """Return a new value containing text after the last delimiter.

        Args:
            search: The delimiter to find.

        Returns:
            A new fluent string.
        """
        return self._new(Str.after_last(self._value, search))

    def before(self, search: str) -> Self:
        """Return a new value containing text before the first delimiter.

        Args:
            search: The delimiter to find.

        Returns:
            A new fluent string.
        """
        return self._new(Str.before(self._value, search))

    def before_last(self, search: str) -> Self:
        """Return a new value containing text before the last delimiter.

        Args:
            search: The delimiter to find.

        Returns:
            A new fluent string.
        """
        return self._new(Str.before_last(self._value, search))

    def between(self, from_: str, to: str) -> Self:
        """Return text between the first start and last end delimiter.

        Args:
            from_: The starting delimiter.
            to: The ending delimiter.

        Returns:
            A new fluent string containing the selected text.
        """
        return self._new(Str.between(self._value, from_, to))

    def between_first(self, from_: str, to: str) -> Self:
        """Return text between the first matching delimiter pair.

        Args:
            from_: The starting delimiter.
            to: The ending delimiter.

        Returns:
            A new fluent string containing the selected text.
        """
        return self._new(Str.between_first(self._value, from_, to))

    def append(self, *values: str) -> Self:
        """Append one or more strings and return a new fluent value.

        Args:
            *values: Text fragments appended in argument order.

        Returns:
            A new fluent string.
        """
        return self._new(self._value + "".join(values))

    def prepend(self, *values: str) -> Self:
        """Prepend one or more strings and return a new fluent value.

        Args:
            *values: Text fragments prepended in argument order.

        Returns:
            A new fluent string.
        """
        return self._new("".join(values) + self._value)

    def new_line(self, count: int = 1) -> Self:
        """Append ``count`` line-feed characters.

        Args:
            count: The number of line feeds to append.

        Returns:
            A new fluent string.

        Raises:
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            raise ValueError(_LINE_COUNT_ERROR)
        return self.append("\n" * count)

    def ascii(self) -> Self:
        """Transliterate the value using Titanspan's standard-library rules.

        Args:
        Returns:
            A new fluent string.
        """
        return self._new(Str.ascii(self._value))

    def char_at(self, index: int) -> str:
        """Return the character at an index using Python string semantics.

        Args:
            index: The Python code point index.

        Returns:
            The character at the requested index.

        Raises:
            IndexError: If the index is outside the string.
        """
        return Str.char_at(self._value, index)

    def chop_start(self, needle: str | Iterable[str]) -> Self:
        """Remove a matching prefix from a new fluent value.

        Args:
            needle: One prefix or an iterable of prefixes.

        Returns:
            A new fluent string.
        """
        return self._new(Str.chop_start(self._value, needle))

    def chop_end(self, needle: str | Iterable[str]) -> Self:
        """Remove a matching suffix from a new fluent value.

        Args:
            needle: One suffix or an iterable of suffixes.

        Returns:
            A new fluent string.
        """
        return self._new(Str.chop_end(self._value, needle))

    def camel(self) -> Self:
        """Convert the value to camel case.

        Returns:
            A new fluent string.
        """
        return self._new(Str.camel(self._value))

    def contains(
        self,
        needles: str | Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether any requested substring is present.

        Args:
            needles: One needle or an iterable of needles.
            ignore_case: Whether to compare with Unicode case folding.

        Returns:
            Whether at least one needle is present.
        """
        return Str.contains(self._value, needles, ignore_case)

    def contains_all(
        self,
        needles: Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether all requested substrings are present.

        Args:
            needles: The substrings to find.
            ignore_case: Whether to compare with Unicode case folding.

        Returns:
            Whether every needle is present.
        """
        return Str.contains_all(self._value, needles, ignore_case)

    def doesnt_contain(
        self,
        needles: str | Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether none of the requested substrings are present.

        Args:
            needles: One needle or an iterable of needles.
            ignore_case: Whether to compare with Unicode case folding.

        Returns:
            Whether no needle is present.
        """
        return Str.doesnt_contain(self._value, needles, ignore_case)

    def convert_case(
        self,
        mode: int = 3,
    ) -> Self:
        """Convert case using the selected multibyte case mode.

        Args:
            mode: Upper, lower, title, or case-fold mode from zero to three.

        Returns:
            A new fluent string.
        """
        return self._new(Str.convert_case(self._value, mode))

    def deduplicate(self, characters: str | Iterable[str] = " ") -> Self:
        """Collapse repeated occurrences of selected characters.

        Args:
            characters: The characters or strings to collapse.

        Returns:
            A new fluent string.
        """
        return self._new(Str.deduplicate(self._value, characters))

    def ends_with(self, needles: str | Iterable[str]) -> bool:
        """Check whether the value ends with one candidate suffix.

        Args:
            needles: One suffix or an iterable of suffixes.

        Returns:
            Whether any suffix matches.
        """
        return Str.ends_with(self._value, needles)

    def exactly(self, value: str | Stringable) -> bool:
        """Check whether the underlying strings are exactly equal.

        Args:
            value: A string or another fluent string to compare.

        Returns:
            Whether both string values are identical.
        """
        candidate = (
            value.to_string() if isinstance(value, Stringable) else value
        )
        return self._value == candidate

    def doesnt_end_with(self, needles: str | Iterable[str]) -> bool:
        """Check whether no candidate suffix matches.

        Args:
            needles: One suffix or an iterable of suffixes.

        Returns:
            Whether no suffix matches.
        """
        return Str.doesnt_end_with(self._value, needles)

    def is_(
        self,
        pattern: str | Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Match the complete value against shell-style glob patterns.

        Args:
            pattern: One glob pattern or an iterable of patterns.
            ignore_case: Whether matching ignores case.

        Returns:
            Whether a pattern matches.
        """
        return Str.is_(pattern, self._value, ignore_case)

    def is_ascii(self) -> bool:
        """Check whether every character is ASCII.

        Returns:
            Whether the wrapped string is ASCII-only.
        """
        return Str.is_ascii(self._value)

    def is_json(self) -> bool:
        """Check whether the value contains valid JSON text.

        Returns:
            Whether the value parses as JSON.
        """
        return Str.is_json(self._value)

    def is_url(self, protocols: Iterable[str] = ()) -> bool:
        """Check whether the value has a valid URL form.

        Args:
            protocols: Optional allowed URL schemes.

        Returns:
            Whether the string passes the URL validator.
        """
        return Str.is_url(self._value, protocols)

    def is_uuid(self, version: int | None = None) -> bool:
        """Check whether the value is a UUID of an optional version.

        Args:
            version: An optional UUID version constraint.

        Returns:
            Whether the value is a valid UUID.
        """
        return Str.is_uuid(self._value, version)

    def is_ulid(self) -> bool:
        """Check whether the value is a valid ULID representation.

        Returns:
            Whether the value has a valid ULID form.
        """
        return Str.is_ulid(self._value)

    def is_empty(self) -> bool:
        """Check whether the wrapped string is empty.

        Returns:
            Whether its length is zero.
        """
        return self._value == ""

    def is_not_empty(self) -> bool:
        """Check whether the wrapped string has at least one code point.

        Returns:
            Whether the value is non-empty.
        """
        return not self.is_empty()

    def is_blank(self) -> bool:
        """Check whether the value contains only blank characters.

        Returns:
            Whether the shared blank-value helper considers it blank.
        """
        return blank(self._value)

    def is_not_blank(self) -> bool:
        """Check whether the value contains non-blank content.

        Returns:
            Whether the shared blank-value helper considers it filled.
        """
        return not self.is_blank()

    def kebab(self) -> Self:
        """Convert the value to kebab case.

        Returns:
            A new fluent string.
        """
        return self._new(Str.kebab(self._value))

    def length(self) -> int:
        """Return the number of Python Unicode code points.

        Args:
        Returns:
            The code point count.
        """
        return Str.length(self._value)

    def limit(
        self,
        limit: int = 100,
        end: str = "...",
        preserve_words: bool = False,
    ) -> Self:
        """Truncate the value and append a suffix when necessary.

        Args:
            limit: The maximum prefix length.
            end: Text appended after a truncated prefix.
            preserve_words: Whether to avoid ending inside a word.

        Returns:
            A new fluent string.
        """
        return self._new(Str.limit(self._value, limit, end, preserve_words))

    def lower(self) -> Self:
        """Convert the value to lowercase.

        Returns:
            A new fluent string.
        """
        return self._new(Str.lower(self._value))

    def match(self, pattern: str) -> Self:
        """Return the first regular-expression match as a fluent value.

        Args:
            pattern: A Python regular expression.

        Returns:
            A new fluent string containing the captured or full match.

        Raises:
            re.error: If the regular expression is invalid.
        """
        return self._new(Str.match(pattern, self._value))

    def is_match(self, pattern: str | Iterable[str]) -> bool:
        """Check whether any regular expression matches the value.

        Args:
            pattern: One regular expression or an iterable of expressions.

        Returns:
            Whether an expression matches.
        """
        return Str.is_match(pattern, self._value)

    def test(self, pattern: str | Iterable[str]) -> bool:
        """Check whether a regular expression matches the value.

        Args:
            pattern: One regular expression or an iterable of expressions.

        Returns:
            Whether an expression matches.
        """
        return self.is_match(pattern)

    def numbers(self) -> Self:
        """Remove non-decimal characters from the wrapped string.

        Returns:
            A new fluent string containing only decimal characters.
        """
        return self._new(Str.numbers(self._value))

    def pad_both(self, size: int, pad: str = " ") -> Self:
        """Pad the value on both sides to a minimum code point length.

        Args:
            size: The minimum length.
            pad: The repeating padding pattern.

        Returns:
            A new fluent string.
        """
        return self._new(Str.pad_both(self._value, size, pad))

    def pad_left(self, size: int, pad: str = " ") -> Self:
        """Pad the value on the left to a minimum code point length.

        Args:
            size: The minimum length.
            pad: The repeating padding pattern.

        Returns:
            A new fluent string.
        """
        return self._new(Str.pad_left(self._value, size, pad))

    def pad_right(self, size: int, pad: str = " ") -> Self:
        """Pad the value on the right to a minimum code point length.

        Args:
            size: The minimum length.
            pad: The repeating padding pattern.

        Returns:
            A new fluent string.
        """
        return self._new(Str.pad_right(self._value, size, pad))

    def parse_callback(
        self,
        default: str | None = None,
    ) -> tuple[str, str | None]:
        """Split a class and optional method from callback-style text.

        Args:
            default: The fallback method when the value has no separator.

        Returns:
            The class name and optional method name.
        """
        return Str.parse_callback(self._value, default)

    def position(
        self,
        needle: str,
        offset: int = 0,
    ) -> int | None:
        """Find a substring starting at a Python code point offset.

        Args:
            needle: The substring to locate.
            offset: The starting index, allowing negative offsets.

        Returns:
            The character position, or ``None`` when absent.
        """
        return Str.position(self._value, needle, offset)

    def remove(
        self,
        search: str | Iterable[str],
        case_sensitive: bool = True,
    ) -> Self:
        """Remove one or more literal strings.

        Args:
            search: A literal string or iterable of literal strings.
            case_sensitive: Whether matching preserves case.

        Returns:
            A new fluent string.
        """
        return self._new(Str.remove(search, self._value, case_sensitive))

    def reverse(self) -> Self:
        """Reverse the value by Python Unicode code point.

        Returns:
            A new fluent string.
        """
        return self._new(Str.reverse(self._value))

    def repeat(self, times: int) -> Self:
        """Repeat the value a requested number of times.

        Args:
            times: The number of repetitions.

        Returns:
            A new fluent string.
        """
        return self._new(Str.repeat(self._value, times))

    def replace(
        self,
        search: str | Iterable[str],
        replace: str,
        case_sensitive: bool = True,
    ) -> Self:
        """Replace literal text, optionally ignoring case.

        Args:
            search: A string or iterable of literal search values.
            replace: The replacement text.
            case_sensitive: Whether matching preserves case.

        Returns:
            A new fluent string.
        """
        return self._new(
            Str.replace(search, replace, self._value, case_sensitive)
        )

    def replace_array(self, search: str, replace: Iterable[str]) -> Self:
        """Replace delimiter occurrences with sequential values.

        Args:
            search: The literal delimiter.
            replace: Replacement strings consumed in order.

        Returns:
            A new fluent string.
        """
        return self._new(Str.replace_array(search, replace, self._value))

    def replace_first(self, search: str, replace: str) -> Self:
        """Replace the first literal occurrence.

        Args:
            search: The text to find.
            replace: Replacement text.

        Returns:
            A new fluent string.
        """
        return self._new(Str.replace_first(search, replace, self._value))

    def replace_start(self, search: str, replace: str) -> Self:
        """Replace a matching prefix.

        Args:
            search: The expected prefix.
            replace: The replacement prefix.

        Returns:
            A new fluent string.
        """
        return self._new(Str.replace_start(search, replace, self._value))

    def replace_last(self, search: str, replace: str) -> Self:
        """Replace the last literal occurrence.

        Args:
            search: The text to find.
            replace: Replacement text.

        Returns:
            A new fluent string.
        """
        return self._new(Str.replace_last(search, replace, self._value))

    def replace_end(self, search: str, replace: str) -> Self:
        """Replace a matching suffix.

        Args:
            search: The expected suffix.
            replace: The replacement suffix.

        Returns:
            A new fluent string.
        """
        return self._new(Str.replace_end(search, replace, self._value))

    def replace_matches(
        self,
        pattern: str,
        replace: str | Callable[[re.Match[str]], str],
        limit: int = -1,
    ) -> Self:
        """Replace regular-expression matches.

        Args:
            pattern: A Python regular expression.
            replace: Replacement text or a match callback.
            limit: Maximum replacements; negative means unlimited.

        Returns:
            A new fluent string.
        """
        return self._new(
            Str.replace_matches(pattern, replace, self._value, limit)
        )

    def swap(self, mapping: Mapping[str, str]) -> Self:
        """Replace literal terms in one pass using longest keys first.

        Args:
            mapping: Literal source terms and their replacement values.

        Returns:
            A new fluent string.
        """
        return self._new(Str.swap(mapping, self._value))

    def slug(
        self,
        separator: str = "-",
        dictionary: Mapping[str, str] | None = None,
    ) -> Self:
        """Create a lowercase ASCII-oriented slug.

        Args:
            separator: The separator between words.
            dictionary: Optional replacements applied before transliteration.

        Returns:
            A new fluent string.
        """
        return self._new(Str.slug(self._value, separator, dictionary))

    def snake(self, delimiter: str = "_") -> Self:
        """Convert the value to snake case.

        Args:
            delimiter: The word separator.

        Returns:
            A new fluent string.
        """
        return self._new(Str.snake(self._value, delimiter))

    def studly(self, normalize: bool = False) -> Self:
        """Convert the value to StudlyCase.

        Args:
            normalize: Whether to normalize the source before conversion.

        Returns:
            A new fluent string.
        """
        return self._new(Str.studly(self._value, normalize))

    def pascal(self, normalize: bool = False) -> Self:
        """Convert the value to PascalCase.

        Args:
            normalize: Whether to normalize the source before conversion.

        Returns:
            A new fluent string.
        """
        return self._new(Str.pascal(self._value, normalize))

    def start(self, prefix: str) -> Self:
        """Ensure the value starts with one copy of a prefix.

        Args:
            prefix: The prefix to add or normalize.

        Returns:
            A new fluent string.
        """
        return self._new(Str.start(self._value, prefix))

    def finish(self, cap: str) -> Self:
        """Ensure the value ends with one copy of a suffix.

        Args:
            cap: The suffix to add or normalize.

        Returns:
            A new fluent string.
        """
        return self._new(Str.finish(self._value, cap))

    def starts_with(self, needles: str | Iterable[str]) -> bool:
        """Check whether the value begins with any candidate prefix.

        Args:
            needles: One prefix or an iterable of prefixes.

        Returns:
            Whether at least one prefix matches.
        """
        return Str.starts_with(self._value, needles)

    def doesnt_start_with(self, needles: str | Iterable[str]) -> bool:
        """Check whether no candidate prefix matches.

        Args:
            needles: One prefix or an iterable of prefixes.

        Returns:
            Whether no prefix matches.
        """
        return Str.doesnt_start_with(self._value, needles)

    def upper(self) -> Self:
        """Convert the value to uppercase.

        Returns:
            A new fluent string.
        """
        return self._new(Str.upper(self._value))

    def title(self) -> Self:
        """Convert the value to title case.

        Returns:
            A new fluent string.
        """
        return self._new(Str.title(self._value))

    def headline(self) -> Self:
        """Convert separated words into headline case.

        Returns:
            A new fluent string.
        """
        return self._new(Str.headline(self._value))

    def initials(self, capitalize: bool = False) -> Self:
        """Return initials derived from the value's words.

        Args:
            capitalize: Whether to uppercase all initials.

        Returns:
            A new fluent string containing the initials.
        """
        return self._new(Str.initials(self._value, capitalize))

    def substr(
        self,
        start: int,
        length: int | None = None,
    ) -> Self:
        """Return a substring using Python code point indexing.

        Args:
            start: Starting index, allowing negative offsets.
            length: Optional result length or negative end offset.

        Returns:
            A new fluent string containing the selected portion.
        """
        return self._new(Str.substr(self._value, start, length))

    def substr_count(
        self,
        needle: str,
        offset: int = 0,
        length: int | None = None,
    ) -> int:
        """Count non-overlapping occurrences in a selected substring.

        Args:
            needle: The non-empty substring to count.
            offset: The starting code point offset.
            length: Optional length of the search region.

        Returns:
            The number of occurrences.
        """
        return Str.substr_count(self._value, needle, offset, length)

    def substr_replace(
        self,
        replace: str,
        offset: int = 0,
        length: int | None = None,
    ) -> Self:
        """Replace a selected part of the value.

        Args:
            replace: Replacement text.
            offset: Start index, allowing negative values.
            length: Number of code points replaced.

        Returns:
            A new fluent string.
        """
        return self._new(
            Str.substr_replace(self._value, replace, offset, length)
        )

    def take(self, limit: int) -> Self:
        """Return the first or last requested number of code points.

        Args:
            limit: Positive takes from the start; negative from the end.

        Returns:
            A new fluent string.
        """
        return self._new(Str.take(self._value, limit))

    def trim(self, characters: str | None = None) -> Self:
        """Trim whitespace or selected characters from both ends.

        Args:
            characters: Optional set of characters to remove.

        Returns:
            A new fluent string.
        """
        return self._new(Str.trim(self._value, characters))

    def ltrim(self, characters: str | None = None) -> Self:
        """Trim whitespace or selected characters from the left edge.

        Args:
            characters: Optional set of characters to remove.

        Returns:
            A new fluent string.
        """
        return self._new(Str.ltrim(self._value, characters))

    def rtrim(self, characters: str | None = None) -> Self:
        """Trim whitespace or selected characters from the right edge.

        Args:
            characters: Optional set of characters to remove.

        Returns:
            A new fluent string.
        """
        return self._new(Str.rtrim(self._value, characters))

    def squish(self) -> Self:
        """Trim surrounding and collapse internal whitespace.

        Returns:
            A new fluent string.
        """
        return self._new(Str.squish(self._value))

    def lcfirst(self) -> Self:
        """Lowercase the first Unicode code point.

        Returns:
            A new fluent string.
        """
        return self._new(Str.lcfirst(self._value))

    def ucfirst(self) -> Self:
        """Uppercase the first Unicode code point.

        Returns:
            A new fluent string.
        """
        return self._new(Str.ucfirst(self._value))

    def ucwords(self, separators: str = " \t\r\n\f\v") -> Self:
        """Uppercase each word's initial character.

        Args:
            separators: Characters treated as word separators.

        Returns:
            A new fluent string.
        """
        return self._new(Str.ucwords(self._value, separators))

    def word_count(self, characters: str | None = None) -> int:
        """Count words using Unicode character categories.

        Args:
            characters: Additional characters permitted inside words.

        Returns:
            The number of words.
        """
        return Str.word_count(self._value, characters)

    def words(self, words: int = 100, end: str = "...") -> Self:
        """Limit the value to a maximum number of whitespace-delimited words.

        Args:
            words: The maximum number of words retained.
            end: Text appended after truncation.

        Returns:
            A new fluent string.
        """
        return self._new(Str.words(self._value, words, end))

    def word_wrap(
        self,
        characters: int = 75,
        break_: str = "\n",
        cut_long_words: bool = False,
    ) -> Self:
        """Wrap the value at the requested line width.

        Args:
            characters: Maximum line width.
            break_: Separator inserted between lines.
            cut_long_words: Whether to split words longer than the width.

        Returns:
            A new fluent string.
        """
        return self._new(
            Str.word_wrap(self._value, characters, break_, cut_long_words)
        )

    def wrap(self, before: str, after: str | None = None) -> Self:
        """Place matching or distinct delimiters around the value.

        Args:
            before: The prefix delimiter.
            after: The suffix delimiter, defaulting to ``before``.

        Returns:
            A new fluent string.
        """
        return self._new(Str.wrap(self._value, before, after))

    def unwrap(self, before: str, after: str | None = None) -> Self:
        """Remove matching delimiters from the value when both are present.

        Args:
            before: The expected prefix delimiter.
            after: The expected suffix delimiter, defaulting to ``before``.

        Returns:
            A new fluent string.
        """
        return self._new(Str.unwrap(self._value, before, after))

    def to_base64(self) -> Self:
        """Encode the value as UTF-8 Base64 text.

        Returns:
            A new fluent string containing the encoded value.
        """
        return self._new(Str.to_base64(self._value))

    def from_base64(self, strict: bool = False) -> Self:
        """Decode a Base64 value as UTF-8 text.

        Args:
            strict: Reject non-alphabet characters when true.

        Returns:
            A new fluent string; invalid input becomes an empty string.
        """
        result = Str.from_base64(self._value, strict)
        return self._new(result if isinstance(result, str) else "")

    def to_html_string(self) -> HtmlString:
        """Wrap the current value as explicitly trusted HTML.

        Returns:
            An HtmlString containing the value without escaping.

        Security:
            This operation does not sanitize untrusted HTML.
        """
        return HtmlString(self._value)

    def _when_predicate(
        self,
        predicate: bool,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Delegate a string predicate to the shared conditional mixin.

        Args:
            predicate: The string condition to evaluate.
            callback: The operation for a true condition.
            default: The operation for a false condition.

        Returns:
            The selected callback result or this stringable value.
        """
        # Conditionable owns callback argument, fallback, and awaitable rules.
        return self.when(predicate, callback, default)

    def when_contains(
        self,
        needles: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when any requested substring is present.

        Args:
            needles: One substring or an iterable of candidates.
            callback: The operation for a matching string.
            default: The operation when no candidate matches.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.contains(needles), callback, default)

    def when_contains_all(
        self,
        needles: Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when all requested substrings are present.

        Args:
            needles: The substrings that must all be present.
            callback: The operation for a matching string.
            default: The operation when a substring is missing.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(
            self.contains_all(needles),
            callback,
            default,
        )

    def when_empty(
        self,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the wrapped string is empty.

        Args:
            callback: The operation for an empty string.
            default: The operation for a non-empty string.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_empty(), callback, default)

    def when_not_empty(
        self,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the wrapped string is not empty.

        Args:
            callback: The operation for a non-empty string.
            default: The operation for an empty string.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_not_empty(), callback, default)

    def when_ends_with(
        self,
        needles: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the value ends with a candidate suffix.

        Args:
            needles: One suffix or an iterable of candidates.
            callback: The operation for a matching suffix.
            default: The operation when no suffix matches.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.ends_with(needles), callback, default)

    def when_doesnt_end_with(
        self,
        needles: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when no candidate suffix matches.

        Args:
            needles: One suffix or an iterable of candidates.
            callback: The operation when no suffix matches.
            default: The operation for a matching suffix.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(
            self.doesnt_end_with(needles),
            callback,
            default,
        )

    def when_exactly(
        self,
        value: str | Stringable,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the value exactly equals the candidate.

        Args:
            value: The string or Stringable value to compare.
            callback: The operation for an exact match.
            default: The operation for a non-matching value.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.exactly(value), callback, default)

    def when_not_exactly(
        self,
        value: str | Stringable,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the value differs from the candidate.

        Args:
            value: The string or Stringable value to compare.
            callback: The operation for a non-matching value.
            default: The operation for an exact match.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(not self.exactly(value), callback, default)

    def when_is(
        self,
        pattern: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when a shell-style glob pattern matches.

        Args:
            pattern: One glob pattern or an iterable of patterns.
            callback: The operation for a matching pattern.
            default: The operation when no pattern matches.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_(pattern), callback, default)

    def when_is_ascii(
        self,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the wrapped string contains only ASCII.

        Args:
            callback: The operation for ASCII text.
            default: The operation for non-ASCII text.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_ascii(), callback, default)

    def when_is_uuid(
        self,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the wrapped string is a valid UUID.

        Args:
            callback: The operation for a valid UUID.
            default: The operation for an invalid UUID.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_uuid(), callback, default)

    def when_is_ulid(
        self,
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the wrapped string is a valid ULID.

        Args:
            callback: The operation for a valid ULID.
            default: The operation for an invalid ULID.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.is_ulid(), callback, default)

    def when_starts_with(
        self,
        needles: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the value starts with a candidate prefix.

        Args:
            needles: One prefix or an iterable of candidates.
            callback: The operation for a matching prefix.
            default: The operation when no prefix matches.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(
            self.starts_with(needles), callback, default
        )

    def when_doesnt_start_with(
        self,
        needles: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when no candidate prefix matches.

        Args:
            needles: One prefix or an iterable of candidates.
            callback: The operation when no prefix matches.
            default: The operation for a matching prefix.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(
            self.doesnt_start_with(needles),
            callback,
            default,
        )

    def when_test(
        self,
        pattern: str | Iterable[str],
        callback: Callable[[Self, object], object],
        default: Callable[[Self, object], object] | None = None,
    ) -> Self | object:
        """Run a callback when the value matches a regular expression.

        Args:
            pattern: One regular expression or an iterable of expressions.
            callback: The operation for a matching expression.
            default: The operation when no expression matches.

        Returns:
            The selected callback result or this stringable value.
        """
        return self._when_predicate(self.test(pattern), callback, default)


__all__ = ["Stringable"]
