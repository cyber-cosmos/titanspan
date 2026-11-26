"""Verify locale-aware numeric formatting and parsing behavior.

The cases cover API names, locale formatting, number spelling, boundaries,
optional dependencies, task-local state, and async callback handling.
"""

from __future__ import annotations

import asyncio
import builtins
import math
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.support import (
    MissingNumberDependencyError,
    Number,
    NumberParseType,
)

pytestmark = pytest.mark.unit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence
    from types import ModuleType


@pytest.fixture
def anyio_backend() -> str:
    """Select asyncio for tests using asyncio synchronization primitives.

    This fixture keeps task-isolation tests on the backend their events use.
    """
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_number_defaults() -> Iterator[None]:
    """Reset context-local numeric defaults around each test.

    The Number defaults use context variables to prevent independent tasks
    from observing temporary locale or currency overrides.
    """
    Number.use_locale("en")
    Number.use_currency("USD")
    yield
    Number.use_locale("en")
    Number.use_currency("USD")


def test_default_locale_and_currency_are_documented() -> None:
    """Use and update the documented locale and currency defaults.

    Updates affect only the active execution context.
    """
    assert Number.default_locale() == "en"
    assert Number.default_currency() == "USD"
    Number.use_locale("de")
    assert Number.default_locale() == "de"
    Number.use_locale("fr")
    assert Number.default_locale() == "fr"
    Number.use_currency("GBP")
    assert Number.default_currency() == "GBP"
    Number.use_currency("EUR")
    assert Number.default_currency() == "EUR"


def test_format_uses_locale_grouping_and_precision() -> None:
    """Format values with locale separators and fixed or maximum decimals.

    The examples exercise both Babel locale conventions and optional digits.
    """
    assert Number.format(100_000) == "100,000"
    assert Number.format(100_000, precision=2) == "100,000.00"
    assert Number.format(100_000.1236, max_precision=3) == "100,000.124"
    assert Number.format(123_456_789, locale="de") == "123.456.789"
    assert (
        Number.format(
            1234.5,
            precision=None,
            max_precision=None,
        )
        == "1,234.5"
    )


def test_format_normalizes_negative_zero_after_rounding() -> None:
    """Avoid negative zero only when the displayed magnitude is zero.

    A negative value remains negative when its configured precision displays
    a non-zero result.
    """
    assert Number.format(-0.4, precision=0) == "0"
    assert Number.format(-0.04, precision=1) == "0.0"
    assert Number.format(-0.06, precision=1) == "-0.1"
    assert Number.format(-0.0) == "0"


def test_format_rejects_negative_precision() -> None:
    """Reject decimal precision values that number formats cannot express.

    Validation occurs before the locale formatter is called.
    """
    with pytest.raises(ValueError, match="precision"):
        Number.format(12.3, precision=-1)


def test_parse_uses_current_or_explicit_locale() -> None:
    """Parse decimal strings according to an explicit or active locale.

    Grouping and decimal separators follow the selected locale's data.
    """
    assert Number.parse("1,234.56") == 1234.56
    assert Number.parse("1.234,56", locale="de") == 1234.56
    assert Number.parse("1 234,56", locale="fr") == 1234.56


def test_parse_respects_numeric_result_type() -> None:
    """Return floats or integers according to the selected parse type.

    Integer parsing truncates the fractional part without fixed-width limits.
    """
    assert Number.parse("1,234.5") == 1234.5
    assert Number.parse("1,234.5", NumberParseType.INT64) == 1234
    assert Number.parse("1,234.5", 0) == 1234
    assert Number.parse_int("1,234.5") == 1234
    assert Number.parse_float("1,234") == 1234.0
    assert Number.parse_int("3,000,000,000") == 3_000_000_000


def test_parse_returns_false_for_invalid_input() -> None:
    """Return ``False`` for invalid numeric text.

    The same failure convention is shared by all three parsing entry points.
    """
    assert Number.parse("not a number") is False
    assert Number.parse_int("not a number") is False
    assert Number.parse_float("not a number") is False


def test_parse_rejects_unknown_type() -> None:
    """Reject parser modes outside the supported ICU-compatible values.

    Unsupported values fail explicitly instead of selecting an implicit mode.
    """
    with pytest.raises(ValueError, match="type"):
        Number.parse("10", 99)


def test_parse_rejects_boolean_parser_mode() -> None:
    """Reject booleans even though Python models them as integers.

    This avoids accepting ``True`` as the integer parser mode ``1``.
    """
    with pytest.raises(ValueError, match="type"):
        Number.parse("10", cast("int", True))


def test_spell_uses_locale_and_thresholds() -> None:
    """Spell cardinal numbers and format values outside threshold bounds.

    Locale selection applies to spelling while thresholded values use digits.
    """
    assert Number.spell(10) == "ten"
    assert Number.spell(1.2) == "one point two"
    assert Number.spell(3, locale="fr") == "trois"
    assert Number.spell(9, after=10) == "9"
    assert Number.spell(11, after=10) == "eleven"
    assert Number.spell(9, until=10) == "nine"
    assert Number.spell(11, until=10) == "11"


def test_ordinal_and_spelled_ordinal() -> None:
    """Provide numeric and spoken ordinal representations.

    The tests cover English suffix boundaries and method aliases.
    """
    assert Number.ordinal(1) == "1st"
    assert Number.ordinal(2) == "2nd"
    assert Number.ordinal(3) == "3rd"
    assert Number.ordinal(11) == "11th"
    assert Number.spell_ordinal(1) == "first"
    assert Number.spell_ordinal(2) == "second"


def test_percentage_matches_integer_scale_semantics() -> None:
    """Format values as percentage points without rescaling them.

    Values represent percentage points rather than fractional ratios.
    """
    assert Number.percentage(10) == "10%"
    assert Number.percentage(10, precision=2) == "10.00%"
    assert Number.percentage(1.75, precision=2) == "1.75%"
    assert Number.percentage(100.1234, max_precision=3) == "100.123%"
    assert Number.percentage(-0.4) == "0%"


def test_currency_uses_default_or_explicit_currency_and_locale() -> None:
    """Format currency with locale-sensitive placement and symbols.

    Explicit precision overrides the currency's default fraction digits.
    """
    assert Number.currency(1) == "$1.00"
    assert Number.currency(1, "EUR") == "€1.00"
    assert Number.currency(1, "EUR", locale="de") == "1,00\u00a0€"
    assert Number.currency(5, precision=0) == "$5"
    assert Number.currency(-0.4, precision=0) == "$0"


def test_file_size_uses_binary_units_and_precision() -> None:
    """Scale byte counts by 1024 and use the documented unit labels.

    Values beyond the largest named unit remain representable in that unit.
    """
    assert Number.file_size(0) == "0 B"
    assert Number.file_size(1024) == "1 KB"
    assert Number.file_size(1264, precision=2) == "1.23 KB"
    assert Number.file_size(1264.12345, max_precision=3) == "1.234 KB"
    assert Number.file_size(-(1024**3) * 5) == "-5 GB"
    assert Number.file_size(1024**9) == "1,024 YB"
    assert Number.file_size(math.inf) == "∞ B"
    assert Number.file_size(-math.inf) == "-∞ B"
    assert Number.file_size(math.nan) == "NaN B"


@pytest.mark.parametrize(
    ("value", "precision", "expected"),
    [
        (1, 0, "1"),
        (1234, 0, "1 thousand"),
        (1234, 2, "1.23 thousand"),
        (1_000_000, 0, "1 million"),
        (10**18, 0, "1 thousand quadrillion"),
        (-1234, 2, "-1.23 thousand"),
        (999_500, 0, "1 million"),
    ],
)
def test_for_humans_summarizes_values(
    value: int,
    precision: int,
    expected: str,
) -> None:
    """Render named powers and rounded magnitude boundaries.

    The parametrized values include negative inputs and suffix carry points.
    """
    assert Number.for_humans(value, precision=precision) == expected


def test_abbreviate_uses_short_magnitude_suffixes() -> None:
    """Render named powers using the configured short suffixes.

    Non-finite values and negatives retain their documented display behavior.
    """
    assert Number.abbreviate(1000) == "1K"
    assert Number.abbreviate(1234, precision=2) == "1.23K"
    assert Number.abbreviate(10**18) == "1KQ"
    assert Number.abbreviate(-0.4) == "0"
    assert Number.abbreviate(math.inf) == "∞"
    assert Number.abbreviate(math.nan) == "NaN"


def test_for_humans_formats_zero_and_unscaled_values() -> None:
    """Preserve zero precision and values without a magnitude suffix.

    Precision is retained for zero only when the caller requests it.
    """
    assert Number.for_humans(0) == "0"
    assert Number.for_humans(0, precision=2) == "0.00"
    assert Number.for_humans(123) == "123"


def test_number_clamp_preserves_values_inside_bounds() -> None:
    """Clamp values to the inclusive minimum and maximum.

    Inputs already within the requested interval are returned unchanged.
    """
    assert Number.clamp(1, 2, 3) == 2
    assert Number.clamp(5, 2, 3) == 3
    assert Number.clamp(4.5, 1, 10) == 4.5


def test_number_pairs_preserves_inclusive_range_semantics() -> None:
    """Split ranges into adjacent lower and upper pairs.

    Integer and fractional boundaries preserve the caller's numeric types.
    """
    assert Number.pairs(25, 10) == [(0, 9), (10, 19), (20, 25)]
    assert Number.pairs(20, 10) == [(0, 9), (10, 19), (20, 20)]
    assert Number.pairs(10, 2.5, 0.5, 0.5) == [
        (0.5, 2.5),
        (3.0, 5.0),
        (5.5, 7.5),
        (8.0, 10.0),
    ]
    assert Number.pairs(100, -10) == Number.pairs(100, 10)
    assert Number.pairs(0, 10) == []


def test_number_pairs_rejects_zero_step() -> None:
    """Reject a step that would prevent the range from advancing.

    The failure is raised before allocating any output pairs.
    """
    with pytest.raises(ValueError, match="must not be zero"):
        Number.pairs(100, 0)


def test_number_pairs_rejects_a_float_step_that_cannot_advance() -> None:
    """Reject a float step erased by the current value's precision.

    This protects the list-producing API from a non-advancing loop.
    """
    start = 10_000_000_000_000_000.0
    end = 10_000_000_000_000_002.0
    with pytest.raises(ValueError, match="too small"):
        Number.pairs(end, 1.0, start)


def test_trim_removes_fractional_zeroes_and_preserves_non_finite_values() -> (
    None
):
    """Normalize integral floats while retaining non-finite values.

    Fractional floats remain floats and NaN remains a NaN value.
    """
    assert Number.trim(12.0) == 12
    assert Number.trim(12.3) == 12.3
    assert Number.trim(12.30) == 12.3
    assert Number.trim(math.inf) == math.inf
    assert Number.trim(-math.inf) == -math.inf
    assert math.isnan(Number.trim(math.nan))


def test_locale_and_currency_scopes_restore_after_success_and_failure() -> None:
    """Restore prior values after nested callback scopes and exceptions.

    Context-local state returns to its prior values at scope boundaries.
    """
    result = Number.with_locale(
        "de",
        lambda: Number.with_currency(
            "EUR",
            lambda: Number.currency(1),
        ),
    )
    assert result == "1,00\u00a0€"
    assert Number.default_locale() == "en"

    with pytest.raises(RuntimeError, match="callback"):
        Number.with_currency(
            "EUR",
            lambda: (_ for _ in ()).throw(RuntimeError("callback")),
        )
    assert Number.default_currency() == "USD"

    with pytest.raises(RuntimeError, match="callback"):
        Number.with_locale(
            "fr",
            lambda: (_ for _ in ()).throw(RuntimeError("callback")),
        )
    assert Number.default_locale() == "en"


@pytest.mark.anyio
async def test_async_locale_scope_restores_after_callback() -> None:
    """Await scoped callbacks and restore state after normal completion.

    Locale formatting inside the callback observes the temporary override.
    """

    async def callback() -> str:
        """Format a value using the callback's active locale.

        Returns:
            The formatted value using the scoped locale.
        """
        return Number.format(1234)

    result = await Number.with_locale_async("de", callback)
    assert result == "1.234"
    assert Number.default_locale() == "en"


@pytest.mark.anyio
async def test_async_locale_scope_restores_after_cancellation() -> None:
    """Restore context-local state when an async callback is cancelled.

    Cancellation propagates instead of being converted to a normal result.
    """

    async def cancelled() -> str:
        """Raise cancellation at the callback boundary.

        Raises:
            asyncio.CancelledError: Always, to exercise scope cleanup.
        """
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await Number.with_locale_async("de", cancelled)
    assert Number.default_locale() == "en"


@pytest.mark.anyio
async def test_async_currency_scope_restores_after_callback() -> None:
    """Keep a currency override active only while the callback is awaited.

    The default currency is restored when the awaited callback completes.
    """

    async def callback() -> str:
        """Format one value using the active currency context.

        Returns:
            The currency-formatted value.
        """
        return Number.currency(1)

    result = await Number.with_currency_async("EUR", callback)
    assert result == "€1.00"
    assert Number.default_currency() == "USD"


@pytest.mark.anyio
async def test_locale_defaults_are_isolated_between_async_tasks() -> None:
    """Prevent concurrent tasks from observing each other's locale state.

    Events synchronize both tasks without relying on timing-based sleeps.
    """
    ready = asyncio.Event()
    release = asyncio.Event()
    completed = 0

    async def read_locale(locale: str) -> str:
        """Read one locale after both task contexts have been initialized.

        Args:
            locale: The override stored in this task's context.

        Returns:
            The locale observed after synchronization.
        """
        nonlocal completed
        Number.use_locale(locale)
        completed += 1
        if completed == 2:
            ready.set()
        await release.wait()
        return Number.default_locale()

    tasks = [
        asyncio.create_task(read_locale("de")),
        asyncio.create_task(read_locale("fr")),
    ]
    await ready.wait()
    release.set()
    assert await asyncio.gather(*tasks) == ["de", "fr"]
    assert Number.default_locale() == "en"


def test_sync_locale_scope_rejects_and_closes_async_callbacks() -> None:
    """Require callers to choose the explicit async locale scope.

    A coroutine produced through a synchronous callback is closed before the
    API raises, avoiding an unawaited-coroutine warning.
    """

    async def callback() -> str:
        """Provide a coroutine to the synchronous scope for rejection.

        Returns:
            A result that is never awaited by the synchronous API.
        """
        return "value"

    sync_callback = cast("Callable[[], object]", callback)
    with pytest.raises(TypeError, match="with_locale_async"):
        Number.with_locale("de", sync_callback)
    assert Number.default_locale() == "en"


@pytest.mark.anyio
async def test_sync_locale_scope_rejects_future_results() -> None:
    """Reject awaitables that are not coroutine objects without taking over.

    Notes:
        The callback owns the future; this scope only rejects implicit async
        execution and does not cancel caller-owned work.
    """
    future = asyncio.get_running_loop().create_future()
    with pytest.raises(TypeError, match="with_locale_async"):
        Number.with_locale("de", lambda: future)
    assert Number.default_locale() == "en"
    future.cancel()


def test_number_inherits_explicit_macro_registration() -> None:
    """Expose the shared Support macro lifecycle on Number.

    Cleanup restores the class macro registry for the remaining test suite.
    """

    def double(value: int) -> int:
        """Double one integer when invoked through the registered macro.

        Args:
            value: The integer value supplied to the macro.

        Returns:
            The doubled integer.
        """
        return value * 2

    Number.macro("doubleForTest", double)
    try:
        assert Number.has_macro("doubleForTest")
        assert Number.invoke_macro("doubleForTest", 4) == 8
    finally:
        Number.flush_macros()


def test_number_rejects_boolean_values_as_numbers() -> None:
    """Reject booleans despite their integer subclass relationship.

    Numeric helpers accept only values explicitly represented as integers or
    floats.
    """
    with pytest.raises(TypeError, match="number"):
        Number.format(cast("int | float", True))


def test_number_rejects_boolean_precision() -> None:
    """Reject booleans instead of accepting them as one decimal digit.

    Precision validation applies the same explicit type rule as value input.
    """
    with pytest.raises(TypeError, match="precision"):
        Number.format(1.2, precision=True)


def test_number_reports_missing_babel_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give a useful package error when Babel is not installed.

    Args:
        monkeypatch: Pytest's temporary import replacement fixture.
    """
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globalns: Mapping[str, object] | None = None,
        localns: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> ModuleType:
        """Fail only on Babel imports while delegating all other imports.

        Args:
            name: The module requested by the import statement.
            globalns: Optional importer global namespace.
            localns: Optional importer local namespace.
            fromlist: Imported names requested by the caller.
            level: Relative import level.

        Returns:
            The imported module for an allowed dependency.

        Raises:
            ModuleNotFoundError: If the request is for Babel.
        """
        if name == "babel" or name.startswith("babel."):
            raise ModuleNotFoundError(name=name)
        return original_import(name, globalns, localns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    operations: tuple[Callable[[], object], ...] = (
        lambda: Number.format(1),
        lambda: Number.parse("1"),
        lambda: Number.percentage(1),
        lambda: Number.currency(1),
        lambda: Number.abbreviate(1000),
    )
    for operation in operations:
        with pytest.raises(MissingNumberDependencyError):
            operation()


def test_number_reports_missing_num2words_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give a useful package error when number spelling is unavailable.

    Args:
        monkeypatch: Pytest's temporary import replacement fixture.
    """
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globalns: Mapping[str, object] | None = None,
        localns: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> ModuleType:
        """Fail on num2words imports and delegate all other imports.

        Args:
            name: The module requested by the import statement.
            globalns: Optional importer global namespace.
            localns: Optional importer local namespace.
            fromlist: Imported names requested by the caller.
            level: Relative import level.

        Returns:
            The imported module for an allowed dependency.

        Raises:
            ModuleNotFoundError: If the request is for num2words.
        """
        if name == "num2words":
            raise ModuleNotFoundError(name=name)
        return original_import(name, globalns, localns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(MissingNumberDependencyError):
        Number.spell(1)
