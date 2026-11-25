"""Test the fail-closed mandatory CI gate validator.

The gate must treat absent, malformed, skipped, and unsuccessful results
as unsatisfied mandatory checks.
"""

from __future__ import annotations

import json

import pytest
from scripts.ci.check_gate import (
    EXPECTED_JOBS,
    GateInputError,
    load_needs,
    validate_needs,
)

pytestmark = pytest.mark.unit
EXPECTED_ERROR_COUNT = 2


def _successful_results() -> dict[str, object]:
    """Return a valid result object for the full mandatory job inventory.

    Each result uses the shape emitted by the GitHub Actions ``needs``
    context for a completed job.
    """
    return {name: {"result": "success"} for name in EXPECTED_JOBS}


def test_gate_accepts_every_expected_success() -> None:
    """Accept a complete inventory when every mandatory job passed.

    The expected inventory is deliberately obtained from the validator so
    policy changes must update its tests and workflow-graph validation.
    """
    assert validate_needs(_successful_results()) == []


def test_gate_rejects_one_failed_job() -> None:
    """Reject a failed mandatory status and identify its job name.

    Other successful statuses cannot compensate for one failed check.
    """
    results = _successful_results()
    results[EXPECTED_JOBS[0]] = {"result": "failure"}

    errors = validate_needs(results)

    assert len(errors) == 1
    assert EXPECTED_JOBS[0] in errors[0]
    assert "failure" in errors[0]


@pytest.mark.parametrize("result", ["cancelled", "skipped"])
def test_gate_rejects_cancelled_or_skipped_jobs(result: str) -> None:
    """Reject mandatory work that did not complete successfully.

    Args:
        result: Unsuccessful GitHub Actions job result to validate.
    """
    results = _successful_results()
    results[EXPECTED_JOBS[0]] = {"result": result}

    assert validate_needs(results)


def test_gate_reports_multiple_unsuccessful_jobs() -> None:
    """Report every unsuccessful job in a single gate evaluation.

    This makes failures actionable without requiring a second CI run.
    """
    results = _successful_results()
    results[EXPECTED_JOBS[0]] = {"result": "failure"}
    results[EXPECTED_JOBS[1]] = {"result": "cancelled"}

    errors = validate_needs(results)

    assert len(errors) == EXPECTED_ERROR_COUNT


def test_gate_rejects_missing_job_results() -> None:
    """Fail closed when a mandatory job is missing from the JSON object.

    Missing status data must not be interpreted as a skipped optional check.
    """
    results = _successful_results()
    results.pop(EXPECTED_JOBS[0])

    errors = validate_needs(results)

    assert any(EXPECTED_JOBS[0] in error for error in errors)


def test_gate_rejects_unexpected_job_results() -> None:
    """Reject workflow jobs that are absent from the expected inventory.

    New CI jobs must be added to the gate inventory before they are trusted.
    """
    results = _successful_results()
    results["unreviewed-job"] = {"result": "success"}

    errors = validate_needs(results)

    assert any("unreviewed-job" in error for error in errors)


@pytest.mark.parametrize("payload", ["", "[]", "{invalid"])
def test_gate_rejects_empty_or_invalid_json(payload: str) -> None:
    """Reject malformed JSON and JSON values with the wrong top-level shape.

    Args:
        payload: Raw environment value supplied by the workflow runner.
    """
    with pytest.raises(GateInputError):
        load_needs(payload)


def test_gate_rejects_invalid_result_shapes() -> None:
    """Reject a result entry that lacks a valid string result value.

    A missing or wrongly typed result must never pass by truthiness.
    """
    results = _successful_results()
    results[EXPECTED_JOBS[0]] = {"result": None}

    errors = validate_needs(results)

    assert any(EXPECTED_JOBS[0] in error for error in errors)


def test_gate_loads_github_needs_json() -> None:
    """Decode the mapping passed by the GitHub Actions gate.

    Return the complete job result mapping without dropping any status.
    """
    payload = json.dumps(_successful_results())

    assert load_needs(payload) == _successful_results()
