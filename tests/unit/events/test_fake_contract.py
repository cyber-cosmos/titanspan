"""Verify event fake recording and assertion behavior.

Tests use the real dispatcher interception context.
"""

from __future__ import annotations

import pytest

from titanspan.events import NativeEventDispatcher

pytestmark = pytest.mark.unit
_TWO_RECORDS = 2


def test_fake_filters_records_and_accepts_successful_assertions() -> None:
    """Filter event records and check the fake's successful assertions.

    The recorder preserves event order and original payload values.
    """
    dispatcher = NativeEventDispatcher()

    def listener(payload: object) -> None:
        """Accept payloads for exact named registration checks.

        Args:
            payload: Explicit named-event payload.
        """
        _ = payload

    dispatcher.listen("job.*", listener)
    with dispatcher.fake() as fake:
        fake.assert_nothing_dispatched()
        dispatcher.dispatch("job.started", {"id": 1})
        dispatcher.dispatch("job.completed", {"id": 2})

        assert len(fake.dispatched()) == _TWO_RECORDS
        assert len(fake.dispatched("job.*")) == _TWO_RECORDS
        assert (
            len(
                fake.dispatched(predicate=lambda record: record.has_payload),
            )
            == _TWO_RECORDS
        )
        fake.assert_dispatched("job.started")
        fake.assert_dispatched("job.completed", times=1)
        fake.assert_not_dispatched("job.failed")
        fake.assert_listening("job.*", listener)


def test_fake_assertions_report_missing_and_unexpected_activity() -> None:
    """Report assertion failures with the selected event or listener.

    The fake exposes failures through standard ``AssertionError`` values.
    """
    dispatcher = NativeEventDispatcher()

    def listener(payload: object) -> None:
        """Accept one payload for fake recording.

        Args:
            payload: Explicit named-event payload.
        """
        _ = payload

    dispatcher.listen("job.started", listener)

    with dispatcher.fake() as fake:
        fake.assert_nothing_dispatched()
        fake.assert_not_listening("job.completed", listener)
        dispatcher.dispatch("job.started")
        with pytest.raises(AssertionError, match="recorded"):
            fake.assert_dispatched("job.started", times=2)
        with pytest.raises(AssertionError, match="not to be dispatched"):
            fake.assert_not_dispatched("job.started")
        with pytest.raises(AssertionError, match="no events"):
            fake.assert_nothing_dispatched()
        with pytest.raises(AssertionError, match="listen for"):
            fake.assert_listening("job.completed", listener)
        with pytest.raises(AssertionError, match="Did not expect"):
            fake.assert_not_listening("job.started", listener)


def test_fake_instance_cannot_be_reentered_and_ignores_inactive_records() -> (
    None
):
    """Reject context reentry and ignore records after deactivation.

    The fake state returns to the previous execution-local stack after exit.
    """
    dispatcher = NativeEventDispatcher()
    fake = dispatcher.fake()

    with (
        fake,
        pytest.raises(RuntimeError, match="cannot be re-entered"),
        fake,
    ):
        pass

    assert not fake.matches("job.started")
