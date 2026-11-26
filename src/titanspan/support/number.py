"""Format, parse, and summarize numeric values for application code.

Babel provides locale-sensitive formatting and parsing. Number-to-word
conversions delegate to the optional num2words package. Scoped locale and
currency values use context variables so concurrent tasks do not share
temporary overrides.
"""

from __future__ import annotations

import builtins
import inspect
import math
import re
from contextvars import ContextVar
from decimal import Decimal
from enum import IntEnum
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from titanspan.support.exceptions import (
    AsyncCallbackUsageError,
    InvalidNumberParseTypeError,
    InvalidNumberPrecisionError,
    InvalidNumberPrecisionTypeError,
    InvalidNumberStepError,
    InvalidNumberValueError,
    MissingNumberDependencyError,
    NonAdvancingNumberRangeError,
)
from titanspan.support.macroable import Macroable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

type NumberValue = int | float
type _FormatValue = int | float | Decimal
type ParseFailure = Literal[False]
_T = TypeVar("_T")
_LOCALE: ContextVar[str] = ContextVar(
    "titanspan_support_number_locale",
    default="en",
)
_CURRENCY: ContextVar[str] = ContextVar(
    "titanspan_support_number_currency",
    default="USD",
)
_UNITS: tuple[tuple[int, str, str], ...] = (
    (3, " thousand", "K"),
    (6, " million", "M"),
    (9, " billion", "B"),
    (12, " trillion", "T"),
    (15, " quadrillion", "Q"),
)
_MAGNITUDE_BASE = Decimal(1000)
_MAGNITUDE_BLOCK = Decimal("1e15")
_FILE_SIZE_BASE = Decimal(1024)
_BABEL_PACKAGE = "Babel"
_NUM2WORDS_PACKAGE = "num2words"
_NUMBER_PATTERN = re.compile(
    r"(?P<integer>[#0][#,0]*)(?:\.(?P<fraction>[#0]+))?"
)


class NumberParseType(IntEnum):
    """Select the result type used when parsing a localized number.

    The numeric values follow the corresponding ICU number formatter modes.
    Python integers have arbitrary precision, so both integer modes produce
    ordinary Python integers without a platform-width overflow limit.
    """

    INT32 = 0
    INT64 = 1
    DOUBLE = 2


class Number(Macroable):
    """Provide locale-aware numeric helpers and explicit macro extension.

    Babel supplies locale data and formatting algorithms; this class owns
    Titanspan's method names, default precision, state scopes, and number
    summary conventions. Number-to-word calls use num2words only when those
    methods are invoked.

    Locale and currency defaults are scoped to the active execution context.
    Calls to ``with_locale`` and ``with_currency`` restore their prior values
    even when callbacks raise. Async callbacks use the explicit async forms.

    Notes:
        Install the ``numbers`` extra for Babel and num2words. This class can
        be imported without that extra; locale and spelling operations need
        their corresponding optional package at call time.
    """

    @classmethod
    def format(
        cls,
        number: NumberValue,
        precision: int | None = None,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        """Format a number with the active or explicitly selected locale.

        Args:
            number: The integer or floating-point value to format.
            precision: Exact fraction digit count, when specified.
            max_precision: Maximum fraction digit count; trailing zeroes are
                omitted when this limit is used.
            locale: Optional Babel locale identifier such as ``de``.

        Returns:
            The grouped, locale-formatted number.

        Raises:
            TypeError: If a boolean is supplied as a numeric value.
            ValueError: If a precision is negative or not an integer.
            ImportError: If the optional numbers extra is unavailable.
        """
        cls._validate_number(number)
        cls._validate_precision(precision, max_precision)
        active_locale = locale if locale is not None else _LOCALE.get()
        return cls._format_decimal(
            number,
            active_locale,
            precision,
            max_precision,
        )

    @classmethod
    def parse(
        cls,
        string: str,
        parse_type: NumberParseType | int = NumberParseType.DOUBLE,
        locale: str | None = None,
    ) -> float | int | ParseFailure:
        """Parse a localized decimal string into a numeric value.

        Args:
            string: The text to parse.
            parse_type: Integer or floating-point result mode.
            locale: Optional locale identifier; defaults to the active locale.

        Returns:
            A float or integer, or ``False`` when the text is invalid.

        Raises:
            TypeError: If the text or parser mode has an invalid type.
            ValueError: If the parser mode is not supported.
            ImportError: If the optional numbers extra is unavailable.

        Notes:
            Python integer results are not limited to a fixed machine width.
        """
        if isinstance(parse_type, bool):
            raise InvalidNumberParseTypeError
        try:
            selected_type = NumberParseType(parse_type)
        except (TypeError, ValueError) as exc:
            raise InvalidNumberParseTypeError from exc

        active_locale = locale if locale is not None else _LOCALE.get()
        try:
            from babel.numbers import NumberFormatError, parse_decimal
        except ImportError as exc:
            raise MissingNumberDependencyError(_BABEL_PACKAGE) from exc

        try:
            parsed = parse_decimal(string, locale=active_locale)
        except NumberFormatError:
            return False
        if selected_type is NumberParseType.DOUBLE:
            return float(parsed)
        return int(parsed)

    @classmethod
    def parse_int(
        cls,
        string: str,
        locale: str | None = None,
    ) -> int | ParseFailure:
        """Parse a localized number and truncate its fractional part.

        Args:
            string: The localized numeric text to parse.
            locale: Optional locale identifier.

        Returns:
            A Python integer, or ``False`` if parsing fails.
        """
        result = cls.parse(string, NumberParseType.INT64, locale)
        if result is False:
            return False
        return cast("int", result)

    @classmethod
    def parse_float(
        cls,
        string: str,
        locale: str | None = None,
    ) -> float | ParseFailure:
        """Parse a localized number as a floating-point value.

        Args:
            string: The localized numeric text to parse.
            locale: Optional locale identifier.

        Returns:
            A float, or ``False`` if parsing fails.
        """
        result = cls.parse(string, NumberParseType.DOUBLE, locale)
        if result is False:
            return False
        return cast("float", result)

    @classmethod
    def spell(
        cls,
        number: NumberValue,
        locale: str | None = None,
        after: int | None = None,
        until: int | None = None,
    ) -> str:
        """Spell a number unless it falls outside optional thresholds.

        Args:
            number: The value to spell or format.
            locale: Optional language or locale identifier.
            after: Values at or below this threshold use numeric formatting.
            until: Values at or above this threshold use numeric formatting.

        Returns:
            The spelled value or its locale-formatted numeric representation.

        Raises:
            ImportError: If the optional num2words package is unavailable.
            NotImplementedError: If num2words does not support the language.
        """
        cls._validate_number(number)
        if after is not None and number <= after:
            return cls.format(number, locale=locale)
        if until is not None and number >= until:
            return cls.format(number, locale=locale)
        return cls._spell_number(number, locale, "cardinal")

    @classmethod
    def ordinal(
        cls,
        number: NumberValue,
        locale: str | None = None,
    ) -> str:
        """Convert a number to its locale-specific ordinal digits.

        Args:
            number: The number to convert.
            locale: Optional language or locale identifier.

        Returns:
            The ordinal representation, such as ``1st``.

        Raises:
            ImportError: If the optional num2words package is unavailable.
            NotImplementedError: If num2words does not support the language.
        """
        cls._validate_number(number)
        return cls._spell_number(number, locale, "ordinal_num")

    @classmethod
    def spell_ordinal(
        cls,
        number: NumberValue,
        locale: str | None = None,
    ) -> str:
        """Spell a number in ordinal form.

        Args:
            number: The number to convert.
            locale: Optional language or locale identifier.

        Returns:
            The spelled ordinal, such as ``first``.

        Raises:
            ImportError: If the optional num2words package is unavailable.
            NotImplementedError: If num2words does not support the language.
        """
        cls._validate_number(number)
        return cls._spell_number(number, locale, "ordinal")

    @classmethod
    def percentage(
        cls,
        number: NumberValue,
        precision: int = 0,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        """Format a value as a percentage using its supplied scale.

        Args:
            number: The numeric percentage value, where ``10`` means 10%.
            precision: Exact fraction digit count, defaulting to zero.
            max_precision: Optional maximum fraction digit count.
            locale: Optional locale identifier.

        Returns:
            The locale-formatted percentage.

        Raises:
            TypeError: If ``number`` is a boolean.
            ValueError: If a precision is negative or not an integer.
            ImportError: If the optional numbers extra is unavailable.
        """
        cls._validate_number(number)
        cls._validate_precision(precision, max_precision)
        active_locale = locale if locale is not None else _LOCALE.get()
        try:
            from babel import Locale
            from babel.numbers import format_percent
        except ImportError as exc:
            raise MissingNumberDependencyError(_BABEL_PACKAGE) from exc

        pattern = Locale.parse(active_locale).percent_formats[None].pattern
        pattern = cls._with_precision(pattern, precision, max_precision)
        decimal_number = Decimal(str(number)) / Decimal(100)

        def formatter(candidate: _FormatValue) -> str:
            """Format one candidate with the same percent pattern.

            Args:
                candidate: A value considered for negative-zero handling.

            Returns:
                The locale-formatted percent string.
            """
            return format_percent(
                candidate,
                format=pattern,
                locale=active_locale,
            )

        normalized = cls._without_negative_zero(decimal_number, formatter)
        return formatter(normalized)

    @classmethod
    def currency(
        cls,
        number: NumberValue,
        in_: str = "",
        locale: str | None = None,
        precision: int | None = None,
    ) -> str:
        """Format a value as currency using locale-specific placement.

        Args:
            number: The value to format.
            in_: Currency code, such as ``EUR``; empty uses the active default.
            locale: Optional locale identifier.
            precision: Optional exact count of fraction digits.

        Returns:
            A locale-formatted currency string.

        Raises:
            TypeError: If the value is boolean or precision has the wrong type.
            ValueError: If precision is negative or the currency is invalid.
            ImportError: If the optional numbers extra is unavailable.

        Notes:
            ``in_`` names the keyword-like option without using a reserved
            identifier.
        """
        cls._validate_number(number)
        cls._validate_precision(precision, None)
        active_locale = locale if locale is not None else _LOCALE.get()
        currency_code = in_ if in_ else _CURRENCY.get()
        try:
            from babel import Locale
            from babel.numbers import format_currency
        except ImportError as exc:
            raise MissingNumberDependencyError(_BABEL_PACKAGE) from exc

        pattern = None
        if precision is not None:
            pattern = (
                Locale.parse(active_locale).currency_formats["standard"].pattern
            )
            pattern = cls._with_precision(pattern, precision, None)

        def formatter(candidate: _FormatValue) -> str:
            """Format one candidate with the selected currency pattern.

            Args:
                candidate: A value considered for negative-zero handling.

            Returns:
                The locale-formatted currency string.
            """
            return format_currency(
                candidate,
                currency_code,
                format=pattern,
                locale=active_locale,
                currency_digits=precision is None,
            )

        normalized = cls._without_negative_zero(number, formatter)
        return formatter(normalized)

    @classmethod
    def file_size(
        cls,
        byte_count: NumberValue,
        precision: int = 0,
        max_precision: int | None = None,
    ) -> str:
        """Format a byte count using powers of 1024.

        Args:
            byte_count: The byte count to format.
            precision: Exact fraction digit count, defaulting to zero.
            max_precision: Optional maximum fraction digit count.

        Returns:
            A formatted value with a binary unit from B through YB.

        Raises:
            TypeError: If the byte count is boolean.
            ValueError: If a precision is invalid.
            ImportError: If the optional numbers extra is unavailable.
        """
        cls._validate_number(byte_count)
        cls._validate_precision(precision, max_precision)
        if type(byte_count) is float and not math.isfinite(byte_count):
            return f"{cls.format(byte_count, precision, max_precision)} B"

        units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        scaled = Decimal(str(byte_count))
        unit_index = 0
        while (
            abs(scaled) / _FILE_SIZE_BASE > Decimal("0.9")
            and unit_index < len(units) - 1
        ):
            scaled /= _FILE_SIZE_BASE
            unit_index += 1
        formatted = cls._format_decimal(
            scaled,
            _LOCALE.get(),
            precision,
            max_precision,
        )
        return f"{formatted} {units[unit_index]}"

    @classmethod
    def abbreviate(
        cls,
        number: NumberValue,
        precision: int = 0,
        max_precision: int | None = None,
    ) -> str:
        """Summarize a number with compact magnitude suffixes.

        Args:
            number: The value to abbreviate.
            precision: Exact fraction digit count, defaulting to zero.
            max_precision: Optional maximum fraction digit count.

        Returns:
            A value with suffixes such as ``K``, ``M``, or ``Q``.
        """
        return cls.for_humans(
            number,
            precision,
            max_precision,
            abbreviate=True,
        )

    @classmethod
    def for_humans(
        cls,
        number: NumberValue,
        precision: int = 0,
        max_precision: int | None = None,
        abbreviate: bool = False,
    ) -> str:
        """Summarize a number with readable or compact magnitude units.

        Args:
            number: The value to summarize.
            precision: Exact fraction digit count, defaulting to zero.
            max_precision: Optional maximum fraction digit count.
            abbreviate: Use compact symbols instead of named units.

        Returns:
            A localized string with a human-readable magnitude suffix.

        Raises:
            TypeError: If ``number`` is boolean or precision has the wrong type.
            ValueError: If precision is negative.
            ImportError: If the optional numbers extra is unavailable.
        """
        cls._validate_number(number)
        cls._validate_precision(precision, max_precision)
        active_locale = _LOCALE.get()
        value = Decimal(str(number))
        if not value.is_finite():
            return cls._format_decimal(
                number,
                active_locale,
                precision,
                max_precision,
            )
        if value == 0:
            if precision > 0:
                return cls._format_decimal(
                    0,
                    active_locale,
                    precision,
                    max_precision,
                )
            return "0"

        was_negative = value < 0
        magnitude = abs(value)
        suffix = ""
        # Divide in 10^15 steps to handle large values without recursion.
        while magnitude >= _MAGNITUDE_BLOCK:
            magnitude /= _MAGNITUDE_BLOCK
            suffix += "Q" if abbreviate else " quadrillion"

        exponent = max(0, (magnitude.adjusted() // 3) * 3)
        magnitude /= Decimal(10) ** exponent
        formatted = cls._format_decimal(
            magnitude,
            active_locale,
            precision,
            max_precision,
        )
        rounded = cls._parse_decimal(formatted, active_locale)
        if rounded is not None and rounded >= _MAGNITUDE_BASE:
            # The normalized value is below 10^15, so the only carry step
            # available is at most from trillion to quadrillion.
            magnitude /= _MAGNITUDE_BASE
            exponent += 3
            formatted = cls._format_decimal(
                magnitude,
                active_locale,
                precision,
                max_precision,
            )

        unit = next(
            (
                entry[2 if abbreviate else 1]
                for entry in _UNITS
                if entry[0] == exponent
            ),
            "",
        )
        result = f"{formatted}{unit}{suffix}"
        if was_negative:
            zero = cls._format_decimal(
                0,
                active_locale,
                precision,
                max_precision,
            )
            if formatted != zero:
                result = f"-{result}"
        return result

    @classmethod
    def clamp(
        cls,
        number: NumberValue,
        minimum: NumberValue,
        maximum: NumberValue,
    ) -> NumberValue:
        """Clamp a numeric value to the inclusive supplied bounds.

        Args:
            number: The input value.
            minimum: The lower bound.
            maximum: The upper bound.

        Returns:
            The nearest bound when the value is outside the interval, or the
            original value when it is inside.
        """
        cls._validate_number(number)
        cls._validate_number(minimum)
        cls._validate_number(maximum)
        return builtins.min(builtins.max(number, minimum), maximum)

    @classmethod
    def pairs(
        cls,
        to: NumberValue,
        by: NumberValue,
        start: NumberValue = 0,
        offset: NumberValue = 1,
    ) -> list[tuple[NumberValue, NumberValue]]:
        """Split a range into consecutive lower and upper bound pairs.

        Args:
            to: Inclusive upper boundary for the generated pairs.
            by: Absolute distance between pair starts.
            start: First lower boundary.
            offset: Amount subtracted from each pair's upper boundary.

        Returns:
            Ordered pairs preserving integer or floating-point inputs.

        Raises:
            ValueError: If ``by`` is zero or cannot advance a finite range.
            TypeError: If an input is boolean.
        """
        for value in (to, by, start, offset):
            cls._validate_number(value)
        if by == 0:
            raise InvalidNumberStepError
        step = abs(by)
        lower = start
        output: list[tuple[NumberValue, NumberValue]] = []
        while lower < to:
            upper = builtins.min(lower + step - offset, to)
            output.append((lower, upper))
            next_lower = lower + step
            if next_lower <= lower:
                raise NonAdvancingNumberRangeError
            lower = next_lower

        if output and lower == to and output[-1][1] < to:
            output.append((lower, to))
        return output

    @classmethod
    def trim(cls, number: NumberValue) -> NumberValue:
        """Remove insignificant fractional zeroes from numeric values.

        Args:
            number: The integer or floating-point value to normalize.

        Returns:
            Integral finite floats as integers; other values remain unchanged.

        Raises:
            TypeError: If a boolean is supplied as a numeric value.
        """
        cls._validate_number(number)
        if isinstance(number, float) and not math.isfinite(number):
            return number
        if isinstance(number, float) and number.is_integer():
            return int(number)
        return number

    @classmethod
    def with_locale(
        cls,
        locale: str,
        callback: Callable[[], _T],
    ) -> _T:
        """Execute a synchronous callback with a temporary locale.

        Args:
            locale: Locale identifier active during the callback.
            callback: Synchronous zero-argument operation.

        Returns:
            The callback result.

        Raises:
            AsyncCallbackUsageError: If the callback returns an awaitable.
            Exception: Any exception raised by the callback is propagated.

        Notes:
            The previous locale is restored even if callback execution fails.
        """
        token = _LOCALE.set(locale)
        try:
            result = callback()
            cls._reject_awaitable(result, "with_locale_async()")
            return result
        finally:
            _LOCALE.reset(token)

    @classmethod
    async def with_locale_async(
        cls,
        locale: str,
        callback: Callable[[], Awaitable[_T]],
    ) -> _T:
        """Await a callback with a temporary task-local locale.

        Args:
            locale: Locale identifier active during the callback.
            callback: Asynchronous zero-argument operation.

        Returns:
            The awaited callback result.

        Raises:
            Exception: Callback failures and cancellation propagate unchanged.

        Notes:
            Context restoration occurs in ``finally`` after cancellation too.
        """
        token = _LOCALE.set(locale)
        try:
            return await callback()
        finally:
            _LOCALE.reset(token)

    @classmethod
    def with_currency(
        cls,
        currency: str,
        callback: Callable[[], _T],
    ) -> _T:
        """Execute a synchronous callback with a temporary currency.

        Args:
            currency: ISO currency code active during the callback.
            callback: Synchronous zero-argument operation.

        Returns:
            The callback result.

        Raises:
            AsyncCallbackUsageError: If the callback returns an awaitable.
            Exception: Any exception raised by the callback is propagated.

        Notes:
            The previous currency is restored even if callback execution fails.
        """
        token = _CURRENCY.set(currency)
        try:
            result = callback()
            cls._reject_awaitable(result, "with_currency_async()")
            return result
        finally:
            _CURRENCY.reset(token)

    @classmethod
    async def with_currency_async(
        cls,
        currency: str,
        callback: Callable[[], Awaitable[_T]],
    ) -> _T:
        """Await a callback with a temporary task-local currency.

        Args:
            currency: ISO currency code active during the callback.
            callback: Asynchronous zero-argument operation.

        Returns:
            The awaited callback result.

        Raises:
            Exception: Callback failures and cancellation propagate unchanged.

        Notes:
            Context restoration occurs in ``finally`` after cancellation too.
        """
        token = _CURRENCY.set(currency)
        try:
            return await callback()
        finally:
            _CURRENCY.reset(token)

    @classmethod
    def use_locale(cls, locale: str) -> None:
        """Set the locale default in the current execution context.

        Args:
            locale: Locale identifier used by subsequent Number operations.

        Notes:
            This is context-local rather than process-global so concurrent
            tasks cannot change one another's formatting behavior.
        """
        _LOCALE.set(locale)

    @classmethod
    def use_currency(cls, currency: str) -> None:
        """Set the currency default in the current execution context.

        Args:
            currency: ISO currency code used by subsequent operations.

        Notes:
            This is context-local rather than process-global so concurrent
            tasks cannot change one another's currency behavior.
        """
        _CURRENCY.set(currency)

    @classmethod
    def default_locale(cls) -> str:
        """Return the locale default active in the current context.

        Returns:
            The current context's locale identifier.
        """
        return _LOCALE.get()

    @classmethod
    def default_currency(cls) -> str:
        """Return the currency default active in the current context.

        Returns:
            The current context's ISO currency code.
        """
        return _CURRENCY.get()

    @classmethod
    def _format_decimal(
        cls,
        number: _FormatValue,
        locale: str,
        precision: int | None,
        max_precision: int | None,
    ) -> str:
        """Format a decimal with normalized precision and negative zero.

        Args:
            number: The value passed to Babel.
            locale: Babel locale identifier.
            precision: Exact minimum and maximum fraction digits.
            max_precision: Maximum fraction digits without forced zeroes.

        Returns:
            The Babel-formatted number string.
        """
        try:
            from babel.numbers import format_decimal
        except ImportError as exc:
            raise MissingNumberDependencyError(_BABEL_PACKAGE) from exc

        pattern = None
        if precision is not None or max_precision is not None:
            pattern = cls._with_precision(
                "#,##0.###",
                precision,
                max_precision,
            )

        def formatter(candidate: _FormatValue) -> str:
            """Format one value for the negative-zero comparison.

            Args:
                candidate: A value checked for display-equivalent zero.

            Returns:
                The locale-formatted string.
            """
            return format_decimal(
                candidate,
                format=pattern,
                locale=locale,
            )

        normalized = cls._without_negative_zero(number, formatter)
        return formatter(normalized)

    @classmethod
    def _parse_decimal(cls, string: str, locale: str) -> Decimal | None:
        """Parse a formatted decimal for magnitude carry detection.

        Args:
            string: The locale-formatted number.
            locale: The matching locale identifier.

        Returns:
            A decimal value, or ``None`` when the string cannot be parsed.
        """
        try:
            from babel.numbers import NumberFormatError, parse_decimal
        except ImportError as exc:
            raise MissingNumberDependencyError(_BABEL_PACKAGE) from exc

        try:
            return parse_decimal(string, locale=locale)
        except NumberFormatError:
            return None

    @classmethod
    def _spell_number(
        cls,
        number: NumberValue,
        locale: str | None,
        to: str,
    ) -> str:
        """Delegate a cardinal or ordinal conversion to num2words.

        Args:
            number: The value to spell.
            locale: Optional language or locale identifier.
            to: The num2words output mode.

        Returns:
            The generated words.

        Raises:
            ImportError: If the optional num2words package is unavailable.
            NotImplementedError: If its adapters do not support the language.
        """
        try:
            from num2words import num2words
        except ImportError as exc:
            raise MissingNumberDependencyError(_NUM2WORDS_PACKAGE) from exc

        language = (locale or _LOCALE.get()).replace("-", "_")
        return num2words(number, lang=language, to=to)

    @classmethod
    def _with_precision(
        cls,
        pattern: str,
        precision: int | None,
        max_precision: int | None,
    ) -> str:
        """Apply minimum and maximum fraction digits to a Babel pattern.

        Args:
            pattern: A locale number format pattern.
            precision: Exact fraction digit count, if specified.
            max_precision: Maximum fraction digit count, if specified.

        Returns:
            The pattern with updated fractional placeholders.
        """
        if precision is None and max_precision is None:
            return pattern
        minimum = 0 if max_precision is not None else precision or 0
        maximum = max_precision if max_precision is not None else precision or 0
        fraction = "0" * minimum + "#" * (maximum - minimum)

        def replace_digits(match: re.Match[str]) -> str:
            """Replace one numeric pattern's decimal placeholders.

            Args:
                match: A numeric section from Babel's LDML pattern.

            Returns:
                The integer placeholders and requested fraction section.
            """
            integer = match.group("integer")
            return f"{integer}.{fraction}" if fraction else integer

        subpatterns = pattern.split(";")
        return ";".join(
            _NUMBER_PATTERN.sub(replace_digits, item, count=1)
            for item in subpatterns
        )

    @classmethod
    def _without_negative_zero(
        cls,
        number: _FormatValue,
        formatter: Callable[[_FormatValue], str],
    ) -> _FormatValue:
        """Replace a negative value only when it formats identically to zero.

        Args:
            number: The value to inspect.
            formatter: The exact formatter used for the eventual result.

        Returns:
            The original value or integer zero.
        """
        if number == 0:
            return 0
        if number < 0 and formatter(abs(number)) == formatter(0):
            return 0
        return number

    @classmethod
    def _validate_number(cls, number: object) -> NumberValue:
        """Reject booleans that Python otherwise treats as integers.

        Args:
            number: The value being checked.

        Raises:
            TypeError: If ``number`` is a boolean or not numeric.
        """
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise InvalidNumberValueError
        return number

    @classmethod
    def _validate_precision(
        cls,
        precision: object,
        max_precision: object,
    ) -> None:
        """Validate fraction digit limits before formatting.

        Args:
            precision: Exact fraction digit count.
            max_precision: Maximum fraction digit count.

        Raises:
            TypeError: If a precision is not an integer.
            ValueError: If a precision is negative.
        """
        for name, value in (
            ("precision", precision),
            ("max_precision", max_precision),
        ):
            if value is None:
                continue
            if type(value) is not int:
                raise InvalidNumberPrecisionTypeError(name)
            if value < 0:
                raise InvalidNumberPrecisionError(name, "non-negative")

    @classmethod
    def _reject_awaitable(
        cls,
        result: object,
        async_api: str,
    ) -> None:
        """Reject asynchronous callback results from synchronous scopes.

        Args:
            result: The callback value to inspect.
            async_api: The explicit API for asynchronous callbacks.

        Raises:
            AsyncCallbackUsageError: If ``result`` is awaitable.
        """
        if not inspect.isawaitable(result):
            return
        if inspect.iscoroutine(result):
            result.close()
        source = "Number scope callback"
        raise AsyncCallbackUsageError(source, async_api)


__all__ = ["Number", "NumberParseType", "NumberValue"]
