"""Provide typed, Laravel-inspired string transformations.

The implementation uses Python's Unicode strings and standard library.
It intentionally exposes both snake_case names and Illuminate-compatible
camelCase aliases while documenting behavior that cannot be identical.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import textwrap
import unicodedata
import uuid
from typing import TYPE_CHECKING, ClassVar, overload
from urllib.parse import urlsplit

from titanspan.support.macroable import Macroable

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from titanspan.support.stringable import Stringable

_ULID_PATTERN = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}", re.IGNORECASE)
_URL_SCHEMES = frozenset({"http", "https", "ftp", "ftps", "mailto"})
_CASE_MODES = {0: "upper", 1: "lower", 2: "title", 3: "fold"}
_ASCII_REPLACEMENTS = {
    "ß": "ss",
    "ẞ": "SS",
    "Æ": "AE",
    "æ": "ae",
    "Ø": "O",
    "ø": "o",
    "Ł": "L",
    "ł": "l",
    "Đ": "D",
    "đ": "d",
    "Þ": "Th",
    "þ": "th",
}


def _needles(value: str | Iterable[str]) -> tuple[str, ...]:
    """Normalize a single needle or iterable without treating text as items.

    Args:
        value: One candidate string or a collection of candidates.

    Returns:
        An immutable tuple of candidate strings.
    """
    return (value,) if isinstance(value, str) else tuple(value)


def _word_parts(value: str) -> list[str]:
    """Split identifier words at separators and lower-to-upper boundaries.

    Args:
        value: The text or identifier to split.

    Returns:
        The non-empty words in their original casing.
    """
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [part for part in re.split(r"[\W_]+", value) if part]


def _slice_start(value: str, start: int) -> int:
    """Normalize PHP-style negative offsets to Python string positions.

    Args:
        value: The string being sliced.
        start: A positive or negative code point offset.

    Returns:
        A clamped non-negative start position.
    """
    return max(len(value) + start, 0) if start < 0 else min(start, len(value))


def _python_substr(
    value: str,
    start: int,
    length: int | None = None,
) -> str:
    """Slice text with PHP-compatible negative length interpretation.

    Args:
        value: The source string.
        start: A code point offset, which may be negative.
        length: A forward length or negative end offset.

    Returns:
        The requested substring, using Python code point indexing.
    """
    offset = _slice_start(value, start)
    if length is None:
        return value[offset:]
    end = len(value) + length if length < 0 else offset + length
    return value[offset : max(offset, end)]


def _pad_string(value: str, size: int, pad: str, side: str) -> str:
    """Pad a string to a code point length using a repeated pattern.

    Args:
        value: The input string.
        size: The minimum resulting length.
        pad: The non-empty padding string.
        side: One of ``left``, ``right``, or ``both``.

    Returns:
        The padded string.

    Raises:
        ValueError: If the requested padding pattern is empty.
    """
    if size <= len(value):
        return value
    if not pad:
        raise ValueError(  # noqa: TRY003
            "padding string must not be empty"  # noqa: EM101
        )  # Public validation detail should identify the invalid argument.
    missing = size - len(value)
    left = missing // 2 if side == "both" else missing if side == "left" else 0
    right = missing - left
    return (
        (pad * ((left + len(pad) - 1) // len(pad)))[:left]
        + value
        + (pad * ((right + len(pad) - 1) // len(pad)))[:right]
    )


class Str(Macroable):
    """Expose static string utilities with Laravel-compatible naming.

    ``Str`` groups pure text transformations and validators. It follows
    Python string indexing and regular expression rules, and uses only the
    standard library. Runtime macros are inherited from :class:`Macroable`.

    Notes:
        Unicode operations index code points, not grapheme clusters or
        display columns. Transliteration is limited to Unicode decomposition
        and a small set of common Latin letter expansions.
    """

    INVISIBLE_CHARACTERS: ClassVar[str] = (
        "\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e"
        "\u200b\u200c\u200d\u200e\u200f\u202f\u205f\u2060"
        "\u2061\u2062\u2063\u2064\u2065\u206a\u206b\u206c"
        "\u206d\u206e\u206f\u2800\u3164\ufeff\uffa0"
    )

    @staticmethod
    def of(value: str = "") -> Stringable:
        """Create a fluent wrapper for a string value.

        Args:
            value: The string to wrap.

        Returns:
            A Stringable instance that delegates to this utility class.
        """
        from titanspan.support.stringable import Stringable  # noqa: PLC0415

        return Stringable(value)

    @staticmethod
    def after(subject: str, search: str) -> str:
        """Return the remainder after the first occurrence of ``search``.

        Args:
            subject: The source string.
            search: The delimiter to locate.

        Returns:
            The suffix after the delimiter, or the original string when the
            delimiter is empty or absent.
        """
        if not search:
            return subject
        position = subject.find(search)
        return subject[position + len(search) :] if position >= 0 else subject

    @staticmethod
    def after_last(subject: str, search: str) -> str:
        """Return the remainder after the last occurrence of ``search``.

        Args:
            subject: The source string.
            search: The delimiter to locate.

        Returns:
            The suffix after the last delimiter, or the original string when
            the delimiter is empty or absent.
        """
        if not search:
            return subject
        position = subject.rfind(search)
        return subject[position + len(search) :] if position >= 0 else subject

    @staticmethod
    def before(subject: str, search: str) -> str:
        """Return the prefix before the first occurrence of ``search``.

        Args:
            subject: The source string.
            search: The delimiter to locate.

        Returns:
            The prefix before the delimiter, or the original string when it
            is empty or absent.
        """
        if not search:
            return subject
        position = subject.find(search)
        return subject[:position] if position >= 0 else subject

    @staticmethod
    def before_last(subject: str, search: str) -> str:
        """Return the prefix before the last occurrence of ``search``.

        Args:
            subject: The source string.
            search: The delimiter to locate.

        Returns:
            The prefix before the last delimiter, or the original string
            when it is empty or absent.
        """
        if not search:
            return subject
        position = subject.rfind(search)
        return subject[:position] if position >= 0 else subject

    @staticmethod
    def between(subject: str, from_: str, to: str) -> str:
        """Return the substring between the first start and last end marker.

        Args:
            subject: The string to inspect.
            from_: The starting delimiter.
            to: The ending delimiter.

        Returns:
            The portion between the delimiters, or the original string when
            either delimiter is empty.
        """
        if not from_ or not to:
            return subject
        return Str.before_last(Str.after(subject, from_), to)

    @staticmethod
    def between_first(subject: str, from_: str, to: str) -> str:
        """Return the substring between the first matching delimiters.

        Args:
            subject: The string to inspect.
            from_: The starting delimiter.
            to: The ending delimiter.

        Returns:
            The portion between the first delimiters, or the original string
            when either delimiter is empty.
        """
        if not from_ or not to:
            return subject
        return Str.before(Str.after(subject, from_), to)

    @staticmethod
    def camel(value: str) -> str:
        """Convert a separated identifier to lower camel case.

        Args:
            value: The identifier to convert.

        Returns:
            The lower camel case form.
        """
        parts = _word_parts(value)
        if not parts:
            return ""
        return parts[0].lower() + "".join(
            part[:1].upper() + part[1:] for part in parts[1:]
        )

    @staticmethod
    def char_at(subject: str, index: int) -> str | bool:
        """Return one Unicode code point at ``index`` or ``False``.

        Args:
            subject: The source string.
            index: A zero-based index; negative indexes count from the end.

        Returns:
            The requested one-character string, or ``False`` out of range.
        """
        position = index if index >= 0 else len(subject) + index
        if position < 0 or position >= len(subject):
            return False
        return subject[position]

    @staticmethod
    def chop_start(subject: str, needle: str | Iterable[str]) -> str:
        """Remove the first matching non-empty prefix from ``subject``.

        Args:
            subject: The string to update.
            needle: A prefix or ordered collection of candidate prefixes.

        Returns:
            The string with one matching prefix removed.
        """
        for candidate in _needles(needle):
            if candidate and subject.startswith(candidate):
                return subject[len(candidate) :]
        return subject

    @staticmethod
    def chop_end(subject: str, needle: str | Iterable[str]) -> str:
        """Remove the first matching non-empty suffix from ``subject``.

        Args:
            subject: The string to update.
            needle: A suffix or ordered collection of candidate suffixes.

        Returns:
            The string with one matching suffix removed.
        """
        for candidate in _needles(needle):
            if candidate and subject.endswith(candidate):
                return subject[: -len(candidate)]
        return subject

    @staticmethod
    def contains(
        haystack: str,
        needles: str | Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether any non-empty needle occurs in ``haystack``.

        Args:
            haystack: The string to search.
            needles: One needle or an iterable of candidates.
            ignore_case: Compare using Unicode case folding when true.

        Returns:
            Whether at least one candidate occurs.
        """
        value = haystack.casefold() if ignore_case else haystack
        return any(
            candidate
            and (candidate.casefold() if ignore_case else candidate) in value
            for candidate in _needles(needles)
        )

    @staticmethod
    def contains_all(
        haystack: str,
        needles: Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether every candidate occurs and at least one was given.

        Args:
            haystack: The string to search.
            needles: The candidate strings.
            ignore_case: Compare using Unicode case folding when true.

        Returns:
            Whether all non-empty candidates occur in the string.
        """
        candidates = tuple(needles)
        return bool(candidates) and all(
            Str.contains(haystack, item, ignore_case) for item in candidates
        )

    @staticmethod
    def convert_case(
        string: str,
        mode: int = 3,
        encoding: str | None = "UTF-8",
    ) -> str:
        """Convert text using the four standard multibyte case modes.

        Args:
            string: The text to convert.
            mode: Upper, lower, title, or Unicode case-fold mode (0 through 3).
            encoding: Accepted for API compatibility; Python strings are
                Unicode and do not require a selected encoding.

        Returns:
            The transformed string.

        Raises:
            ValueError: If ``mode`` is not one of the supported values.
        """
        del encoding
        operation = _CASE_MODES.get(mode)
        if operation is None:
            raise ValueError(  # noqa: TRY003
                "mode must be one of 0, 1, 2, or 3"  # noqa: EM101
            )  # Preserve a clear validation message for invalid case modes.
        if operation == "upper":
            return string.upper()
        if operation == "lower":
            return string.lower()
        if operation == "title":
            return string.title()
        return string.casefold()

    @staticmethod
    def doesnt_contain(
        haystack: str,
        needles: str | Iterable[str],
        ignore_case: bool = False,
    ) -> bool:
        """Check whether none of the candidate strings occur.

        Args:
            haystack: The string to search.
            needles: One needle or an iterable of candidates.
            ignore_case: Compare using Unicode case folding when true.

        Returns:
            Whether :meth:`contains` returns false.
        """
        return not Str.contains(haystack, needles, ignore_case)

    @staticmethod
    def deduplicate(string: str, characters: str | Iterable[str] = " ") -> str:
        """Collapse repeated occurrences of selected characters.

        Args:
            string: The text to normalize.
            characters: One repeated character or ordered character strings.

        Returns:
            The string with each selected run reduced to one occurrence.
        """
        candidates = (
            (characters,) if isinstance(characters, str) else tuple(characters)
        )
        for character in candidates:
            if character:
                string = re.sub(
                    f"(?:{re.escape(character)})+",
                    lambda _match, replacement=character: replacement,
                    string,
                )
        return string

    @staticmethod
    def ends_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Check whether ``haystack`` ends with one non-empty needle.

        Args:
            haystack: The string to check.
            needles: One suffix or an iterable of suffixes.

        Returns:
            Whether a candidate is a suffix.
        """
        return any(
            candidate and haystack.endswith(candidate)
            for candidate in _needles(needles)
        )

    @staticmethod
    def doesnt_end_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Check that ``haystack`` does not end with a candidate.

        Args:
            haystack: The string to check.
            needles: One suffix or an iterable of suffixes.

        Returns:
            The inverse of :meth:`ends_with`.
        """
        return not Str.ends_with(haystack, needles)

    @staticmethod
    def excerpt(
        text: str,
        phrase: str = "",
        options: Mapping[str, int | str] | None = None,
    ) -> str | None:
        """Extract a radius-limited excerpt around a case-insensitive phrase.

        Args:
            text: The source text.
            phrase: The text to locate; an empty phrase matches at the start.
            options: Optional ``radius`` and ``omission`` values.

        Returns:
            The excerpt, or ``None`` when the phrase is absent.

        Raises:
            ValueError: If the radius is not a non-negative integer.
            TypeError: If the omission marker is not a string.
        """
        settings: Mapping[str, int | str] = {} if options is None else options
        radius_value = settings.get("radius", 100)
        omission_value = settings.get("omission", "...")
        if not isinstance(radius_value, int) or radius_value < 0:
            raise ValueError(  # noqa: TRY003
                "radius must be a non-negative integer"  # noqa: EM101
            )  # Preserve actionable validation details for caller input.
        if not isinstance(omission_value, str):
            raise TypeError(  # noqa: TRY003
                "omission must be a string"  # noqa: EM101
            )  # Validate this structured option before constructing output.

        radius = radius_value
        omission = omission_value
        found = re.search(re.escape(phrase), text, flags=re.IGNORECASE)
        if found is None:
            return None
        before = text[: found.start()].lstrip()
        after = text[found.end() :].rstrip()
        before_context = before[-radius:] if radius else ""
        after_context = after[:radius] if radius else ""
        prefix = omission if len(before) > radius else ""
        suffix = omission if len(after) > radius else ""
        return prefix + before_context + found.group(0) + after_context + suffix

    @staticmethod
    def finish(value: str, cap: str) -> str:
        """Ensure a string ends with exactly one copy of ``cap``.

        Args:
            value: The source string.
            cap: The suffix to ensure.

        Returns:
            The normalized string with one trailing suffix.
        """
        if not cap:
            return value
        while value.endswith(cap + cap):
            value = value[: -len(cap)]
        return value if value.endswith(cap) else value + cap

    @staticmethod
    def wrap(value: str, before: str, after: str | None = None) -> str:
        """Place matching or distinct delimiters around a string.

        Args:
            value: The inner string.
            before: The prefix delimiter.
            after: The suffix delimiter, defaulting to ``before``.

        Returns:
            The wrapped string.
        """
        return f"{before}{value}{before if after is None else after}"

    @staticmethod
    def unwrap(value: str, before: str, after: str | None = None) -> str:
        """Remove a matching prefix and suffix when they are present.

        Args:
            value: The source string.
            before: The prefix to remove.
            after: The suffix to remove, defaulting to ``before``.

        Returns:
            The unwrapped string.
        """
        suffix = before if after is None else after
        if before and value.startswith(before):
            value = value[len(before) :]
        if suffix and value.endswith(suffix):
            value = value[: -len(suffix)]
        return value

    @staticmethod
    def is_(
        pattern: str | Iterable[str],
        value: str,
        ignore_case: bool = False,
    ) -> bool:
        """Match a whole string against one or more ``*`` glob patterns.

        Args:
            pattern: A pattern or iterable of patterns.
            value: The value to compare.
            ignore_case: Use case-insensitive matching when true.

        Returns:
            Whether any pattern matches the complete value.
        """
        for candidate in _needles(pattern):
            expression = re.escape(candidate).replace(r"\*", ".*")
            flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
            if re.fullmatch(expression, value, flags):
                return True
        return False

    @staticmethod
    def is_ascii(value: str) -> bool:
        """Check whether every code point is in the ASCII range.

        Args:
            value: The string to inspect.

        Returns:
            Whether the value contains only ASCII code points.
        """
        return value.isascii()

    @staticmethod
    def is_json(value: object) -> bool:
        """Check whether a string contains valid JSON.

        Args:
            value: The candidate JSON string.

        Returns:
            Whether the value parses as JSON without non-standard constants.
        """
        if not isinstance(value, str):
            return False
        try:
            json.loads(value, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError):
            return False
        return True

    @staticmethod
    def is_url(value: object, protocols: Iterable[str] = ()) -> bool:
        """Validate a URL using an explicit, conservative scheme policy.

        Args:
            value: The candidate URL.
            protocols: Optional allowed schemes; defaults to common schemes.

        Returns:
            Whether the URL has an allowed scheme and a syntactically valid
            authority when its scheme requires one.

        Notes:
            This is syntax validation, not an SSRF or network safety check.
        """
        if (
            not isinstance(value, str)
            or not value
            or any(character.isspace() for character in value)
        ):
            return False
        parsed = urlsplit(value)
        allowed = {scheme.lower() for scheme in protocols} or _URL_SCHEMES
        if parsed.scheme.lower() not in allowed:
            return False
        if parsed.scheme.lower() == "mailto":
            return bool(parsed.path and "@" in parsed.path)
        try:
            host = parsed.hostname
            _port = parsed.port
        except ValueError:
            return False
        if not host:
            return False
        if ":" in host:
            return True
        labels = host.rstrip(".").split(".")
        if not all(labels) or any(
            label.startswith("-") or label.endswith("-") for label in labels
        ):
            return False
        valid_idna = True
        try:
            host.encode("idna")
        except UnicodeError:
            valid_idna = False
        return valid_idna

    @staticmethod
    def is_uuid(value: object, version: int | None = None) -> bool:
        """Check UUID syntax and optionally require a particular version.

        Args:
            value: The candidate UUID string.
            version: An optional UUID version number.

        Returns:
            Whether the candidate is a valid UUID of the requested version.
        """
        if not isinstance(value, str):
            return False
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError):
            return False
        return version is None or parsed.version == version

    @staticmethod
    def is_ulid(value: object) -> bool:
        """Check the canonical 26-character Crockford ULID form.

        Args:
            value: The candidate ULID string.

        Returns:
            Whether the candidate matches the ULID alphabet and length.
        """
        if not isinstance(value, str) or _ULID_PATTERN.fullmatch(value) is None:
            return False
        return value[0] in "01234567"

    @staticmethod
    def ascii(value: str, language: str = "en") -> str:
        """Transliterate decomposable text into a limited ASCII form.

        Args:
            value: The input string.
            language: A reserved compatibility argument; no locale tables are
                loaded by this standard-library implementation.

        Returns:
            ASCII text with combining marks removed where possible.
        """
        del language
        expanded = "".join(
            _ASCII_REPLACEMENTS.get(char, char) for char in value
        )
        decomposed = unicodedata.normalize("NFKD", expanded)
        return (
            "".join(
                char for char in decomposed if not unicodedata.combining(char)
            )
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    @staticmethod
    def kebab(value: str) -> str:
        """Convert an identifier to lowercase kebab case.

        Args:
            value: The text or identifier to convert.

        Returns:
            The kebab-case representation.
        """
        return "-".join(part.lower() for part in _word_parts(value))

    @staticmethod
    def length(value: str, encoding: str | None = None) -> int:
        """Return the number of Python Unicode code points in a string.

        Args:
            value: The string to measure.
            encoding: Accepted for API compatibility and otherwise unused.

        Returns:
            The code point length.
        """
        del encoding
        return len(value)

    @staticmethod
    def limit(
        value: str,
        limit: int = 100,
        end: str = "...",
        preserve_words: bool = False,
    ) -> str:
        """Truncate a string and append a suffix when it exceeds ``limit``.

        Args:
            value: The source text.
            limit: The maximum prefix length, in code points.
            end: The suffix appended after truncation.
            preserve_words: Avoid ending in the middle of a word.

        Returns:
            The original or truncated string.

        Raises:
            ValueError: If ``limit`` is negative.
        """
        if limit < 0:
            raise ValueError(  # noqa: TRY003
                "limit must be non-negative"  # noqa: EM101
            )  # Public validation detail should identify the invalid argument.
        if len(value) <= limit:
            return value
        prefix = value[:limit].rstrip()
        if preserve_words:
            prefix = re.sub(r"\s+\S*$", "", prefix)
        return prefix + end

    @staticmethod
    def lower(value: str) -> str:
        """Convert text to lowercase using Unicode casing rules.

        Args:
            value: The text to convert.

        Returns:
            The lowercase string.
        """
        return value.lower()

    @staticmethod
    def words(value: str, words: int = 100, end: str = "...") -> str:
        """Limit a string to a maximum number of whitespace-delimited words.

        Args:
            value: The source text.
            words: Maximum number of words to retain.
            end: The suffix appended when truncation occurs.

        Returns:
            The original or shortened string.

        Raises:
            ValueError: If ``words`` is negative.
        """
        if words < 0:
            raise ValueError(  # noqa: TRY003
                "words must be non-negative"  # noqa: EM101
            )  # Public validation detail should identify the invalid argument.
        matches = list(re.finditer(r"\S+", value))
        if len(matches) <= words:
            return value
        if words == 0:
            return end
        return value[: matches[words - 1].end()].rstrip() + end

    @staticmethod
    def mask(
        string: str,
        character: str,
        index: int,
        length: int | None = None,
        encoding: str = "UTF-8",
    ) -> str:
        """Replace a selected range with the first code point of a marker.

        Args:
            string: The input string.
            character: The marker repeated across the selected range.
            index: The start position, with negative offsets from the end.
            length: Number of code points to mask; defaults to the remainder.
            encoding: Accepted for compatibility; Python strings are Unicode.

        Returns:
            The masked string.
        """
        del encoding
        if not character or not string:
            return string
        start = _slice_start(string, index)
        size = len(string) - start if length is None else max(length, 0)
        size = min(size, len(string) - start)
        return string[:start] + character[0] * size + string[start + size :]

    @staticmethod
    def match(pattern: str, subject: str) -> str:
        """Return the first capture group or full regular-expression match.

        Args:
            pattern: A Python regular expression.
            subject: The string to search.

        Returns:
            The first capture group, complete match, or an empty string.

        Raises:
            re.error: If ``pattern`` is invalid.
        """
        found = re.search(pattern, subject)
        if found is None:
            return ""
        return found.group(1) if found.lastindex else found.group(0)

    @staticmethod
    def is_match(pattern: str | Iterable[str], value: str) -> bool:
        """Check whether any Python regular expression matches the string.

        Args:
            pattern: One expression or an iterable of expressions.
            value: The string to inspect.

        Returns:
            Whether at least one expression matches.

        Raises:
            re.error: If any evaluated expression is invalid.
        """
        return any(
            re.search(item, value) is not None for item in _needles(pattern)
        )

    @staticmethod
    def match_all(pattern: str, subject: str) -> list[str]:
        """Return first capture groups or complete regular-expression matches.

        Args:
            pattern: A Python regular expression.
            subject: The string to search.

        Returns:
            The captured values in source order.

        Raises:
            re.error: If ``pattern`` is invalid.
        """
        matches = re.findall(pattern, subject)
        return [
            match if isinstance(match, str) else match[0] for match in matches
        ]

    @overload
    @staticmethod
    def numbers(value: str) -> str:
        """Return decimal characters from one string value.

        Args:
            value: The source text.

        Returns:
            The filtered string.
        """

    @overload
    @staticmethod
    def numbers(value: Iterable[str]) -> str | list[str]:
        """Return decimal characters for each input string.

        Args:
            value: The source strings.

        Returns:
            A filtered string or a list for an iterable input.
        """

    @staticmethod
    def numbers(value: str | Iterable[str]) -> str | list[str]:
        """Remove non-decimal characters from one string or an iterable.

        Args:
            value: A string or iterable of strings.

        Returns:
            One filtered string or a list of filtered strings.
        """
        if isinstance(value, str):
            return "".join(char for char in value if char.isdecimal())
        return [
            "".join(char for char in item if char.isdecimal()) for item in value
        ]

    @staticmethod
    def pad_both(value: str, size: int, pad: str = " ") -> str:
        """Pad a string on both sides to a minimum code point length.

        Args:
            value: The source text.
            size: The minimum resulting length.
            pad: The repeating padding pattern.

        Returns:
            The padded string.
        """
        return _pad_string(value, size, pad, "both")

    @staticmethod
    def pad_left(value: str, size: int, pad: str = " ") -> str:
        """Pad a string on the left to a minimum code point length.

        Args:
            value: The source text.
            size: The minimum resulting length.
            pad: The repeating padding pattern.

        Returns:
            The padded string.
        """
        return _pad_string(value, size, pad, "left")

    @staticmethod
    def pad_right(value: str, size: int, pad: str = " ") -> str:
        """Pad a string on the right to a minimum code point length.

        Args:
            value: The source text.
            size: The minimum resulting length.
            pad: The repeating padding pattern.

        Returns:
            The padded string.
        """
        return _pad_string(value, size, pad, "right")

    @staticmethod
    def parse_callback(
        callback: str,
        default: str | None = None,
    ) -> tuple[str, str | None]:
        """Split a ``Class@method`` callback into its two components.

        Args:
            callback: The class label with an optional method suffix.
            default: The method name used when no suffix is present.

        Returns:
            A pair containing the class label and method name.

        Notes:
            PHP anonymous class names can contain ``@``. If their marker is
            present, the final ``@`` separates an optional method suffix.
        """
        if "@anonymous\0" in callback:
            if callback.count("@") > 1:
                class_name, method = callback.rsplit("@", 1)
                return class_name, method
            return callback, default
        if "@" not in callback:
            return callback, default
        class_name, method = callback.split("@", 1)
        return class_name, method

    @staticmethod
    def position(
        haystack: str,
        needle: str,
        offset: int = 0,
        encoding: str | None = None,
    ) -> int | None:
        """Find a substring from a code point offset.

        Args:
            haystack: The string to search.
            needle: The target substring.
            offset: Start offset, including negative offsets from the end.
            encoding: Accepted for compatibility; Python strings are Unicode.

        Returns:
            The zero-based position, or ``None`` when absent.
        """
        del encoding
        start = _slice_start(haystack, offset)
        found = haystack.find(needle, start)
        return found if found >= 0 else None

    @staticmethod
    def repeat(string: str, times: int) -> str:
        """Repeat a string a requested number of times.

        Args:
            string: The source text.
            times: The number of repetitions.

        Returns:
            The repeated string, or an empty string when ``times`` is below 1.
        """
        if times < 0:
            raise ValueError(  # noqa: TRY003
                "times must be non-negative"  # noqa: EM101
            )  # Public validation detail should identify the invalid argument.
        return string * times

    @staticmethod
    def replace_array(search: str, replace: Iterable[str], subject: str) -> str:
        """Replace each delimiter occurrence with successive values.

        Args:
            search: The literal delimiter.
            replace: Replacement values consumed in order.
            subject: The string to update.

        Returns:
            The string with sequential replacement values.
        """
        if not search:
            return subject
        replacements = iter(replace)
        pieces = subject.split(search)
        result = [pieces[0]]
        for piece in pieces[1:]:
            result.append(next(replacements, search))
            result.append(piece)
        return "".join(result)

    @staticmethod
    def swap(mapping: Mapping[str, str], subject: str) -> str:
        """Replace mapped keywords with longest keys taking precedence.

        Args:
            mapping: Literal source terms and their replacements.
            subject: The string to transform.

        Returns:
            The transformed string.

        Notes:
            Empty source terms are ignored. A single regular-expression pass
            prevents replacement text from being processed a second time.
        """
        terms = sorted(
            (term for term in mapping if term), key=len, reverse=True
        )
        if not terms:
            return subject
        expression = re.compile("|".join(re.escape(term) for term in terms))
        return expression.sub(
            lambda match: mapping[match.group(0)],
            subject,
        )

    @staticmethod
    def replace(
        search: str | Iterable[str],
        replace: str,
        subject: str,
        case_sensitive: bool = True,
    ) -> str:
        """Replace literal occurrences, optionally ignoring case.

        Args:
            search: One literal search string or ordered candidates.
            replace: Replacement text.
            subject: The text to update.
            case_sensitive: Whether matching preserves case.

        Returns:
            The transformed string.
        """
        for candidate in _needles(search):
            if not candidate:
                continue
            if case_sensitive:
                subject = subject.replace(candidate, replace)
            else:
                subject = re.sub(
                    re.escape(candidate),
                    lambda _match: replace,
                    subject,
                    flags=re.IGNORECASE,
                )
        return subject

    @staticmethod
    def replace_first(search: str, replace: str, subject: str) -> str:
        """Replace the first literal occurrence in a string.

        Args:
            search: The literal text to find.
            replace: Replacement text.
            subject: The string to update.

        Returns:
            The updated string.
        """
        return subject.replace(search, replace, 1) if search else subject

    @staticmethod
    def replace_start(search: str, replace: str, subject: str) -> str:
        """Replace a literal prefix when the string starts with it.

        Args:
            search: The expected prefix.
            replace: Replacement text.
            subject: The string to update.

        Returns:
            The updated or original string.
        """
        return (
            replace + subject[len(search) :]
            if search and subject.startswith(search)
            else subject
        )

    @staticmethod
    def replace_last(search: str, replace: str, subject: str) -> str:
        """Replace the last literal occurrence in a string.

        Args:
            search: The literal text to find.
            replace: Replacement text.
            subject: The string to update.

        Returns:
            The updated string.
        """
        position = subject.rfind(search) if search else -1
        return (
            subject[:position] + replace + subject[position + len(search) :]
            if position >= 0
            else subject
        )

    @staticmethod
    def replace_end(search: str, replace: str, subject: str) -> str:
        """Replace a literal suffix when the string ends with it.

        Args:
            search: The expected suffix.
            replace: Replacement text.
            subject: The string to update.

        Returns:
            The updated or original string.
        """
        return (
            subject[: -len(search)] + replace
            if search and subject.endswith(search)
            else subject
        )

    @staticmethod
    def replace_matches(
        pattern: str,
        replace: str | Callable[[re.Match[str]], str],
        subject: str,
        limit: int = -1,
    ) -> str:
        """Replace regular-expression matches in a string.

        Args:
            pattern: A Python regular expression.
            replace: Replacement string or match callback.
            subject: The string to update.
            limit: Maximum number of replacements; negative means unlimited.

        Returns:
            The transformed string.

        Raises:
            re.error: If ``pattern`` is invalid.
        """
        return re.sub(pattern, replace, subject, count=max(limit, 0))

    @staticmethod
    def remove(
        search: str | Iterable[str],
        subject: str,
        case_sensitive: bool = True,
    ) -> str:
        """Remove one or more literal terms from a string.

        Args:
            search: One term or ordered terms to remove.
            subject: The text to update.
            case_sensitive: Whether matching preserves case.

        Returns:
            The text after all terms have been removed.
        """
        return Str.replace(search, "", subject, case_sensitive)

    @staticmethod
    def reverse(value: str) -> str:
        """Reverse a string by Python Unicode code point.

        Args:
            value: The source string.

        Returns:
            The reversed string.
        """
        return value[::-1]

    @staticmethod
    def start(value: str, prefix: str) -> str:
        """Ensure a string begins with exactly one copy of ``prefix``.

        Args:
            value: The source string.
            prefix: The prefix to ensure.

        Returns:
            The normalized string.
        """
        if not prefix:
            return value
        while value.startswith(prefix + prefix):
            value = value[len(prefix) :]
        return value if value.startswith(prefix) else prefix + value

    @staticmethod
    def upper(value: str) -> str:
        """Convert text to uppercase using Unicode casing rules.

        Args:
            value: The text to convert.

        Returns:
            The uppercase string.
        """
        return value.upper()

    @staticmethod
    def title(value: str) -> str:
        """Convert text to Unicode title case.

        Args:
            value: The text to convert.

        Returns:
            The title-cased string.
        """
        return value.title()

    @staticmethod
    def headline(value: str) -> str:
        """Convert separated identifiers into a readable title.

        Args:
            value: The input label or identifier.

        Returns:
            A title with separators normalized to single spaces.
        """
        parts = _word_parts(value.replace("_", " ").replace("-", " "))
        return " ".join(part[:1].upper() + part[1:].lower() for part in parts)

    @staticmethod
    def initials(value: str, capitalize: bool = False) -> str:
        """Return the first code point from each whitespace-delimited word.

        Args:
            value: The input name or phrase.
            capitalize: Uppercase the resulting initials when true.

        Returns:
            The concatenated initials.
        """
        result = "".join(part[0] for part in value.split() if part)
        return result.upper() if capitalize else result

    @staticmethod
    def slug(
        title: str,
        separator: str = "-",
        language: str = "en",
        dictionary: Mapping[str, str] | None = None,
    ) -> str:
        """Create a lowercase ASCII-oriented slug from a title.

        Args:
            title: The source title.
            separator: The word separator in the result.
            language: Accepted for compatibility; locale transliteration is
                not loaded by this standard-library implementation.
            dictionary: Optional replacements applied before transliteration.

        Returns:
            A normalized slug.
        """
        del language
        replacements = {"@": "at"} if dictionary is None else dictionary
        for source, target in replacements.items():
            title = title.replace(source, f" {target} ")
        normalized = Str.ascii(title).lower()
        words = re.findall(r"[a-z0-9]+", normalized)
        return separator.join(words)

    @staticmethod
    def snake(value: str, delimiter: str = "_") -> str:
        """Convert a camel, Pascal, or separated identifier to snake case.

        Args:
            value: The identifier to convert.
            delimiter: The separator used between words.

        Returns:
            The lowercase identifier.
        """
        return delimiter.join(part.lower() for part in _word_parts(value))

    @staticmethod
    def trim(value: str, charlist: str | None = None) -> str:
        """Remove whitespace or selected characters from both ends.

        Args:
            value: The text to trim.
            charlist: Optional set of characters to remove.

        Returns:
            The trimmed text.
        """
        return value.strip(charlist)

    @staticmethod
    def ltrim(value: str, charlist: str | None = None) -> str:
        """Remove whitespace or selected characters from the left edge.

        Args:
            value: The text to trim.
            charlist: Optional set of characters to remove.

        Returns:
            The left-trimmed text.
        """
        return value.lstrip(charlist)

    @staticmethod
    def rtrim(value: str, charlist: str | None = None) -> str:
        """Remove whitespace or selected characters from the right edge.

        Args:
            value: The text to trim.
            charlist: Optional set of characters to remove.

        Returns:
            The right-trimmed text.
        """
        return value.rstrip(charlist)

    @staticmethod
    def squish(value: str) -> str:
        """Trim surrounding whitespace and collapse internal whitespace.

        Args:
            value: The source text.

        Returns:
            The normalized single-space string.
        """
        return " ".join(value.split())

    @staticmethod
    def starts_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Check whether a string starts with a non-empty candidate.

        Args:
            haystack: The string to check.
            needles: One prefix or an iterable of prefixes.

        Returns:
            Whether a candidate is a prefix.
        """
        return any(
            candidate and haystack.startswith(candidate)
            for candidate in _needles(needles)
        )

    @staticmethod
    def doesnt_start_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Check that a string does not start with a candidate.

        Args:
            haystack: The string to check.
            needles: One prefix or an iterable of prefixes.

        Returns:
            The inverse of :meth:`starts_with`.
        """
        return not Str.starts_with(haystack, needles)

    @staticmethod
    def studly(value: str, normalize: bool = False) -> str:
        """Convert a separated identifier to StudlyCase.

        Args:
            value: The identifier to convert.
            normalize: Lowercase all-uppercase words before capitalizing.

        Returns:
            The StudlyCase representation.
        """
        parts = _word_parts(value)
        if normalize:
            parts = [part.lower() if part.isupper() else part for part in parts]
        return "".join(part[:1].upper() + part[1:] for part in parts)

    @staticmethod
    def pascal(value: str, normalize: bool = False) -> str:
        """Convert a separated identifier to PascalCase.

        Args:
            value: The identifier to convert.
            normalize: Lowercase all-uppercase words before capitalizing.

        Returns:
            The PascalCase representation.
        """
        return Str.studly(value, normalize)

    @staticmethod
    def substr(
        string: str,
        start: int,
        length: int | None = None,
        encoding: str = "UTF-8",
    ) -> str:
        """Return a substring using Python code point indexing.

        Args:
            string: The source string.
            start: Starting offset, possibly negative.
            length: Optional forward length or negative end offset.
            encoding: Accepted for compatibility; Python strings are Unicode.

        Returns:
            The selected substring.
        """
        del encoding
        return _python_substr(string, start, length)

    @staticmethod
    def substr_count(
        haystack: str,
        needle: str,
        offset: int = 0,
        length: int | None = None,
    ) -> int:
        """Count non-overlapping occurrences in a selected substring.

        Args:
            haystack: The complete string.
            needle: The non-empty substring to count.
            offset: Starting code point offset.
            length: Optional substring length or negative end offset.

        Returns:
            The number of non-overlapping matches.

        Raises:
            ValueError: If ``needle`` is empty.
        """
        if not needle:
            raise ValueError(  # noqa: TRY003
                "needle must not be empty"  # noqa: EM101
            )  # Public validation detail should identify the invalid argument.
        return _python_substr(haystack, offset, length).count(needle)

    @staticmethod
    def substr_replace(
        string: str,
        replace: str,
        offset: int = 0,
        length: int | None = None,
    ) -> str:
        """Replace a selected slice of a string.

        Args:
            string: The original text.
            replace: Replacement text.
            offset: Starting code point offset, possibly negative.
            length: Number of code points replaced; negative preserves a tail.

        Returns:
            The string with the selected portion replaced.
        """
        start = _slice_start(string, offset)
        stop = (
            len(string)
            if length is None
            else (len(string) + length if length < 0 else start + length)
        )
        return (
            string[:start]
            + replace
            + string[min(max(stop, start), len(string)) :]
        )

    @staticmethod
    def take(string: str, limit: int) -> str:
        """Return the first or last requested number of code points.

        Args:
            string: The source text.
            limit: Positive takes from the start; negative takes from the end.

        Returns:
            The selected text.
        """
        return (
            _python_substr(string, 0, limit)
            if limit >= 0
            else _python_substr(string, limit)
        )

    @staticmethod
    def to_base64(string: str) -> str:
        """Encode UTF-8 text as standard Base64.

        Args:
            string: The text to encode.

        Returns:
            The ASCII Base64 representation.
        """
        return base64.b64encode(string.encode("utf-8")).decode("ascii")

    @staticmethod
    def from_base64(string: str, strict: bool = False) -> str | bool:
        """Decode Base64 text as UTF-8.

        Args:
            string: The encoded text.
            strict: Reject non-alphabet characters when true.

        Returns:
            Decoded text or ``False`` for invalid input.
        """
        try:
            raw = base64.b64decode(string, validate=strict)
            return raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False

    @staticmethod
    def lcfirst(string: str) -> str:
        """Lowercase the first Unicode code point.

        Args:
            string: The input text.

        Returns:
            The string with its first code point lowercased.
        """
        return string[:1].lower() + string[1:]

    @staticmethod
    def ucfirst(string: str) -> str:
        """Uppercase the first Unicode code point.

        Args:
            string: The input text.

        Returns:
            The string with its first code point uppercased.
        """
        return string[:1].upper() + string[1:]

    @staticmethod
    def ucwords(string: str, separators: str = " \t\r\n\f\v") -> str:
        """Uppercase the first character and characters after separators.

        Args:
            string: The source text.
            separators: Characters that begin a new word.

        Returns:
            The transformed string.
        """
        separator_set = set(separators)
        result: list[str] = []
        capitalize_next = True
        for character in string:
            result.append(character.upper() if capitalize_next else character)
            capitalize_next = character in separator_set
        return "".join(result)

    @staticmethod
    def ucsplit(string: str) -> list[str]:
        """Split a string immediately before each uppercase code point.

        Args:
            string: The source text.

        Returns:
            Non-empty pieces in source order.
        """
        if not string:
            return []
        parts: list[str] = []
        start = 0
        for index, character in enumerate(string):
            if index and character.isupper():
                parts.append(string[start:index])
                start = index
        parts.append(string[start:])
        return parts

    @staticmethod
    def word_count(string: str, characters: str | None = None) -> int:
        """Count Unicode words, optionally including extra characters.

        Args:
            string: The source text.
            characters: Additional characters accepted inside words.

        Returns:
            The number of non-empty word matches.
        """
        extra = "" if characters is None else re.escape(characters)
        return len(re.findall(rf"[\w{extra}]+", string, flags=re.UNICODE))

    @staticmethod
    def word_wrap(
        string: str,
        characters: int = 75,
        break_: str = "\n",
        cut_long_words: bool = False,
    ) -> str:
        """Wrap text at a requested code point width.

        Args:
            string: The source text.
            characters: Maximum output line width.
            break_: The inserted line separator.
            cut_long_words: Split words that exceed the width when true.

        Returns:
            Wrapped text using the requested separator.

        Raises:
            ValueError: If ``characters`` is not positive.
        """
        if characters <= 0:
            raise ValueError(  # noqa: TRY003
                "characters must be positive"  # noqa: EM101
            )  # Public validation detail should identify the invalid argument.
        return break_.join(
            textwrap.wrap(
                string,
                width=characters,
                break_long_words=cut_long_words,
                break_on_hyphens=False,
                replace_whitespace=False,
                drop_whitespace=True,
            )
        )

    afterLast = after_last
    beforeLast = before_last
    betweenFirst = between_first
    charAt = char_at
    chopStart = chop_start
    chopEnd = chop_end
    containsAll = contains_all
    convertCase = convert_case
    doesntContain = doesnt_contain
    endsWith = ends_with
    doesntEndWith = doesnt_end_with
    isAscii = is_ascii
    isJson = is_json
    isUrl = is_url
    isUuid = is_uuid
    isUlid = is_ulid
    padBoth = pad_both
    padLeft = pad_left
    padRight = pad_right
    replaceArray = replace_array
    replaceFirst = replace_first
    replaceStart = replace_start
    replaceLast = replace_last
    replaceEnd = replace_end
    replaceMatches = replace_matches
    doesntStartWith = doesnt_start_with
    startsWith = starts_with
    parseCallback = parse_callback
    substrCount = substr_count
    substrReplace = substr_replace
    toBase64 = to_base64
    fromBase64 = from_base64
    ucwords = ucwords
    ucsplit = ucsplit
    wordCount = word_count
    wordWrap = word_wrap
    isMatch = is_match


def _reject_json_constant(value: str) -> None:
    """Reject JavaScript numeric constants that are not valid JSON.

    Args:
        value: The non-standard constant supplied by ``json.loads``.

    Raises:
        ValueError: Always, because JSON does not define this constant.
    """
    del value
    raise ValueError(  # noqa: TRY003
        "non-standard numeric constant is not valid JSON"  # noqa: EM101
    )  # json.loads requires an exception from this callback for rejection.


__all__ = ["Str"]
