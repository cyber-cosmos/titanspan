"""Test the structural policy applied to GitHub Actions workflows.

The policy checks make workflow safety and the mandatory gate reviewable
without depending on the online Actions service.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from scripts.ci.check_gate import EXPECTED_JOBS
from scripts.ci.check_workflow_policy import (
    COVERAGE_INPUT_JOBS,
    PYTHON_MATRIX,
    TECHNICAL_DOCUMENTATION_JOB,
    TECHNICAL_DOCUMENTATION_NAME,
    validate_action_references,
    validate_ci_workflow,
    validate_repository,
)

pytestmark = pytest.mark.unit


def _mapping(value: object) -> dict[str, object]:
    """Narrow test workflow mappings while preserving strict static types.

    Args:
        value: A value expected to be a YAML-like dictionary.

    Returns:
        The input as a string-keyed mapping after a runtime assertion.
    """
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _workflow() -> dict[str, object]:
    """Build a structurally valid workflow fixture for policy tests.

    The fixture contains every mandatory job and a final gate that depends on
    each job while allowing the gate to run after failures.
    """
    jobs: dict[str, object] = {
        job_id: {
            "runs-on": "ubuntu-latest",
            "timeout-minutes": "10",
        }
        for job_id in EXPECTED_JOBS
    }
    _mapping(jobs[TECHNICAL_DOCUMENTATION_JOB])["name"] = (
        TECHNICAL_DOCUMENTATION_NAME
    )
    jobs["cross-component"] = {
        "name": "Architecture: Cross-component integration",
        "runs-on": "ubuntu-latest",
        "timeout-minutes": "20",
        "env": {"COVERAGE": "collect"},
        "steps": [
            {"run": "make architecture-integration-test"},
            {
                "uses": (
                    "actions/upload-artifact@"
                    "cf430e030ddbb5b0abf9"  # pragma: allowlist secret
                    "3d22962f4752f3646cd9"  # pragma: allowlist secret
                ),
                "with": {"name": "coverage-cross-component"},
            },
        ],
    }
    jobs["license-compliance"] = {
        "runs-on": "ubuntu-latest",
        "timeout-minutes": "10",
        "steps": [
            {
                "run": "make license-check | tee license-report.txt",
                "shell": "bash",
            },
        ],
    }
    for job_id in ("unit-tests", "integration-tests"):
        job = _mapping(jobs[job_id])
        job["strategy"] = {
            "fail-fast": False,
            "matrix": {"python-version": list(PYTHON_MATRIX)},
        }
    platform_job = _mapping(jobs["platform-smoke"])
    platform_job["strategy"] = {
        "fail-fast": False,
        "matrix": {"os": ["macos-latest", "windows-latest"]},
    }
    jobs["coverage"] = {
        "if": "always()",
        "needs": list(COVERAGE_INPUT_JOBS),
        "runs-on": "ubuntu-latest",
        "timeout-minutes": "10",
        "steps": [
            {
                "run": (
                    "uv run coverage report --fail-under=0\n"
                    "uv run coverage json --fail-under=0 -o coverage.json\n"
                    "uv run coverage xml --fail-under=0 -o coverage.xml"
                ),
            },
            {
                "run": (
                    "uv run diff-cover coverage.xml --include "
                    "src/titanspan/** --fail-under=95 "
                    "--markdown-report=diff-coverage.md"
                ),
            },
        ],
    }
    jobs["ci-gate"] = {
        "if": "always()",
        "name": "Gate: All mandatory CI checks",
        "needs": list(EXPECTED_JOBS),
        "runs-on": "ubuntu-latest",
        "timeout-minutes": "5",
        "steps": [
            {
                "run": "python3 -m scripts.ci.check_gate",
                "env": {"CI_NEEDS_JSON": "${{ toJSON(needs) }}"},
            },
        ],
    }
    return {
        "permissions": {"contents": "read"},
        "on": {
            "push": None,
            "pull_request": None,
            "workflow_dispatch": None,
            "merge_group": None,
        },
        "concurrency": {
            "cancel-in-progress": "${{ github.event_name == 'pull_request' }}",
        },
        "jobs": jobs,
    }


def test_workflow_policy_accepts_complete_mandatory_graph() -> None:
    """Accept a workflow with all jobs explicitly included in the gate.

    Every primary-workflow job must be a required dependency of ``ci-gate``.
    """
    assert validate_ci_workflow(_workflow()) == []


def test_workflow_policy_requires_technical_documentation_job_name() -> None:
    """Keep technical writing as an independently named mandatory job.

    Returns:
        None.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    job = _mapping(jobs[TECHNICAL_DOCUMENTATION_JOB])
    job["name"] = "Quality: Prose"

    errors = validate_ci_workflow(workflow)

    assert any("technical-documentation" in error for error in errors)


def test_workflow_policy_rejects_job_missing_from_gate() -> None:
    """Reject a mandatory job omitted from final gate dependencies.

    The gate must explicitly depend on every required CI job.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    gate = _mapping(jobs["ci-gate"])
    gate["needs"] = list(EXPECTED_JOBS[:-1])

    errors = validate_ci_workflow(workflow)

    assert any("ci-gate needs" in error for error in errors)


def test_workflow_policy_rejects_missing_job_and_no_always_gate() -> None:
    """Reject incomplete job inventories and gates skipped on failure.

    The graph must expose all expected jobs and run the gate unconditionally.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    jobs.pop(EXPECTED_JOBS[0])
    gate = _mapping(jobs["ci-gate"])
    gate["if"] = "success()"

    errors = validate_ci_workflow(workflow)

    assert any(EXPECTED_JOBS[0] in error for error in errors)
    assert any("always()" in error for error in errors)


def test_workflow_policy_rejects_missing_timeouts() -> None:
    """Require explicit time limits on each mandatory job.

    Jobs without a timeout can consume runner capacity indefinitely.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    job = _mapping(jobs[EXPECTED_JOBS[0]])
    job.pop("timeout-minutes")

    errors = validate_ci_workflow(workflow)

    assert any("timeout-minutes" in error for error in errors)


def test_workflow_policy_requires_real_cross_component_integration() -> None:
    """Reject a decorative architecture job with no executable test.

    The visible cross-component status must execute its dedicated target and
    contribute branch coverage to the aggregate coverage job.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    cross_component = _mapping(jobs["cross-component"])
    cross_component["steps"] = []

    errors = validate_ci_workflow(workflow)

    assert any("cross-component" in error for error in errors)


def test_workflow_policy_rejects_paths_that_hide_required_statuses() -> None:
    """Require the primary workflow to run without path-filter omissions.

    Required CI statuses must be emitted even when a change affects only
    documentation, agent instructions, or build configuration.
    """
    workflow = _workflow()
    triggers = _mapping(workflow["on"])
    triggers["push"] = {"paths": ["src/**"]}

    errors = validate_ci_workflow(workflow)

    assert any("path filters" in error for error in errors)


def test_workflow_policy_rejects_incomplete_or_fail_fast_matrices() -> None:
    """Require complete Python coverage and non-canceling matrix behavior.

    A failing early interpreter must not cancel remaining compatibility
    entries.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    unit = _mapping(jobs["unit-tests"])
    strategy = _mapping(unit["strategy"])
    strategy["fail-fast"] = True
    matrix = _mapping(strategy["matrix"])
    matrix["python-version"] = ["3.12"]

    errors = validate_ci_workflow(workflow)

    assert any("unit-tests" in error and "matrix" in error for error in errors)
    assert any("fail-fast" in error for error in errors)


def test_workflow_policy_rejects_continue_on_error_in_mandatory_job() -> None:
    """Reject a mandatory job that masks unsuccessful execution.

    Required statuses must preserve their actual result for the final gate.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    job = _mapping(jobs[EXPECTED_JOBS[0]])
    job["continue-on-error"] = True

    errors = validate_ci_workflow(workflow)

    assert any("continue-on-error" in error for error in errors)


def test_workflow_policy_rejects_masked_license_pipeline() -> None:
    """Require the license audit pipeline to preserve the checker status.

    GitHub's explicit Bash shell enables ``pipefail`` for pipelines ending in
    ``tee``. The checker must not pass when the license audit fails.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    license_job = _mapping(jobs["license-compliance"])
    steps = cast("list[object]", license_job["steps"])
    audit_step = _mapping(steps[0])
    audit_step.pop("shell")

    errors = validate_ci_workflow(workflow)

    assert any("license audit pipeline" in error for error in errors)


def test_workflow_policy_requires_changed_source_coverage() -> None:
    """Reject a coverage job that omits the changed-line threshold.

    Overall coverage cannot conceal untested lines in a change.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    coverage = _mapping(jobs["coverage"])
    steps = coverage["steps"]
    assert isinstance(steps, list)
    typed_steps = cast("list[object]", steps)
    step = _mapping(typed_steps[1])
    step["run"] = "uv run diff-cover coverage.xml --fail-under=80"

    errors = validate_ci_workflow(workflow)

    assert any("changed source line coverage" in error for error in errors)


def test_workflow_policy_rejects_combined_coverage_floor() -> None:
    """Keep report generation from masking independent metric checks.

    The dedicated validator checks line and branch thresholds separately, so
    report commands must not enforce coverage.py's combined percentage.
    """
    workflow = _workflow()
    jobs = _mapping(workflow["jobs"])
    coverage = _mapping(jobs["coverage"])
    steps = cast("list[object]", coverage["steps"])
    report_step = _mapping(steps[0])
    report_step["run"] = (
        "uv run coverage report --fail-under=0\n"
        "uv run coverage json -o coverage.json\n"
        "uv run coverage xml --fail-under=0 -o coverage.xml"
    )

    errors = validate_ci_workflow(workflow)

    assert any("combined coverage floor" in error for error in errors)


def test_checked_in_workflow_inventory_is_valid() -> None:
    """Validate the real repository workflows and action references.

    This integration test ensures that the structural checker accepts the
    project's actual matrix, timeouts, and final gate configuration.
    """
    root = Path(__file__).resolve().parents[2]

    assert validate_repository(root) == []


def test_action_policy_accepts_immutable_versioned_references() -> None:
    """Accept an action reference pinned to a full SHA and release tag.

    The release annotation remains human-readable while the SHA is immutable.
    """
    workflow_text = (
        "uses: actions/checkout@"
        "3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
    )

    assert validate_action_references(workflow_text) == []


@pytest.mark.parametrize(
    "reference",
    [
        "uses: actions/checkout@v7\n",
        "uses: actions/checkout@0123 # v1\n",
        "uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n",
    ],
)
def test_action_policy_rejects_unpinned_or_unannotated_actions(
    reference: str,
) -> None:
    """Reject mutable references and hashes without release annotations.

    Args:
        reference: Workflow action reference with an unsafe pin format.
    """
    assert validate_action_references(reference)
