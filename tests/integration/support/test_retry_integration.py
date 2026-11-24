"""Verify retry helper behavior through the real Tenacity engine.

The integration boundary confirms that Titanspan's attempt and exception
semantics survive actual Tenacity controller execution.
"""

import pytest

from titanspan.support import retry

EXPECTED_ATTEMPTS = 3


class TemporaryTransportError(Exception):
    """Represent a transient integration failure.

    The failure is raised by the operation and handled by the actual retry
    controller without replacing its exception type.
    """


@pytest.mark.integration
def test_retry_uses_tenacity_for_real_bounded_execution() -> None:
    """Run a flaky operation through Tenacity and preserve attempt numbers.

    Returns:
        None.
    """
    observed_attempts: list[int] = []

    def operation(attempt: int) -> str:
        """Fail until the final configured attempt.

        Args:
            attempt: The current one-based attempt number.

        Returns:
            A result after the operation succeeds.

        Raises:
            TemporaryTransportError: While the operation remains transient.
        """
        observed_attempts.append(attempt)
        if attempt < EXPECTED_ATTEMPTS:
            raise TemporaryTransportError
        return "delivered"

    result = retry(EXPECTED_ATTEMPTS, operation)

    assert result == "delivered"
    assert observed_attempts == [1, 2, 3]
