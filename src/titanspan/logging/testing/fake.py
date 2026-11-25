"""Provide behavior-oriented assertions for captured native log records.

Fakes inspect the same sanitized record representation that production drivers
receive, without exposing backend capture facilities.
"""

from collections.abc import Callable, Mapping

from titanspan.logging.drivers.core import MemoryLogDriver
from titanspan.logging.exceptions import (
    LogAssertionError,
    LogConfigurationError,
)
from titanspan.logging.level import LogLevel
from titanspan.logging.record import LogRecord

RecordPredicate = Callable[[LogRecord], bool]


class FakeLog:
    """Assert logged behavior against a bounded memory driver.

    Attributes:
        driver: The native memory driver that owns captured records.

    Filters compose by severity, exact message, channel, context values, and
    an optional predicate. No backend-specific record types are exposed.
    """

    def __init__(self, driver: MemoryLogDriver) -> None:
        """Bind assertion helpers to one memory driver.

        Args:
            driver: The driver receiving fake application log records.
        """
        self.driver = driver

    def assert_logged(
        self,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> LogRecord:
        """Require at least one record matching the supplied filters.

        Args:
            level: Optional severity name, enum, or RFC number.
            message: Optional exact message string.
            channel: Optional exact channel identifier.
            context: Context values that must match the record.
            predicate: Optional application-specific record predicate.

        Returns:
            The first matching record in delivery order.

        Raises:
            AssertionError: If no captured record matches.
        """
        records = self._matching(
            level=level,
            message=message,
            channel=channel,
            context=context,
            predicate=predicate,
        )
        if not records:
            msg = "No matching log record was captured"
            raise LogAssertionError(msg)
        return records[0]

    def assert_not_logged(
        self,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> None:
        """Require that no record matches the supplied filters.

        Args:
            level: Optional severity name, enum, or RFC number.
            message: Optional exact message string.
            channel: Optional exact channel identifier.
            context: Context values that must match the record.
            predicate: Optional application-specific record predicate.

        Raises:
            AssertionError: If a matching record was captured.
        """
        records = self._matching(
            level=level,
            message=message,
            channel=channel,
            context=context,
            predicate=predicate,
        )
        if records:
            msg = "A matching log record was captured"
            raise LogAssertionError(msg)

    def assert_logged_times(
        self,
        count: int,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> None:
        """Require an exact count of records matching the filters.

        Args:
            count: Expected number of matching records.
            level: Optional severity name, enum, or RFC number.
            message: Optional exact message string.
            channel: Optional exact channel identifier.
            context: Context values that must match each record.
            predicate: Optional application-specific record predicate.

        Raises:
            AssertionError: If the captured count differs from ``count``.
            ValueError: If ``count`` is negative.
        """
        if count < 0:
            msg = "Expected log count cannot be negative"
            raise LogConfigurationError(msg)
        records = self._matching(
            level=level,
            message=message,
            channel=channel,
            context=context,
            predicate=predicate,
        )
        if len(records) != count:
            msg = f"Expected {count} records, captured {len(records)}"
            raise LogAssertionError(msg)

    def assert_nothing_logged(self) -> None:
        """Require that the memory driver captured no records.

        Raises:
            AssertionError: If any record was captured.
        """
        if self.driver.records:
            msg = "Expected no log records to be captured"
            raise LogAssertionError(msg)

    def _matching(
        self,
        *,
        level: LogLevel | str | int | None,
        message: str | None,
        channel: str | None,
        context: Mapping[str, object] | None,
        predicate: RecordPredicate | None,
    ) -> tuple[LogRecord, ...]:
        """Return records satisfying every supplied filter.

        Args:
            level: Optional severity filter.
            message: Optional exact message filter.
            channel: Optional channel filter.
            context: Optional subset of context values.
            predicate: Optional additional predicate.

        Returns:
            Matching records in original delivery order.
        """
        parsed_level = LogLevel.parse(level) if level is not None else None
        return tuple(
            record
            for record in self.driver.records
            if (parsed_level is None or record.level is parsed_level)
            and (message is None or record.message == message)
            and (channel is None or record.channel == channel)
            and _matches_context(record, context)
            and (predicate is None or predicate(record))
        )

    def assertLogged(  # noqa: N802
        self,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> LogRecord:
        """Assert a matching record using Laravel-compatible spelling.

        Args:
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required context values.
            predicate: Optional record predicate.

        Returns:
            The first matching record.
        """
        return self.assert_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    def assertNotLogged(  # noqa: N802
        self,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> None:
        """Assert no matching record using Laravel-compatible spelling.

        Args:
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required context values.
            predicate: Optional record predicate.
        """
        self.assert_not_logged(
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    def assertLoggedTimes(  # noqa: N802
        self,
        count: int,
        level: LogLevel | str | int | None = None,
        message: str | None = None,
        *,
        channel: str | None = None,
        context: Mapping[str, object] | None = None,
        predicate: RecordPredicate | None = None,
    ) -> None:
        """Assert an exact matching count with Laravel-compatible spelling.

        Args:
            count: Expected number of matching records.
            level: Optional severity filter.
            message: Optional exact message.
            channel: Optional channel name.
            context: Required context values.
            predicate: Optional record predicate.
        """
        self.assert_logged_times(
            count,
            level,
            message,
            channel=channel,
            context=context,
            predicate=predicate,
        )

    def assertNothingLogged(self) -> None:  # noqa: N802
        """Assert that no record was captured with Laravel-style spelling.

        Prefer :meth:`assert_nothing_logged` in Python code.
        """
        self.assert_nothing_logged()


def _matches_context(
    record: LogRecord,
    expected: Mapping[str, object] | None,
) -> bool:
    """Check whether a record contains every expected context value.

    Args:
        record: The captured native log record.
        expected: Required key/value subset, if any.

    Returns:
        Whether all requested context values compare equal.
    """
    if expected is None:
        return True
    return all(
        record.context.get(key) == value for key, value in expected.items()
    )
