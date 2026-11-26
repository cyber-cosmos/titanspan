"""Validate the complete set of required GitHub Actions job results.

The gate fails closed when a job is missing, malformed, skipped, cancelled,
or unsuccessful. Its inventory is also checked against the workflow graph.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

EXPECTED_JOBS = (
    "lint",
    "format",
    "docblocks",
    "comments",
    "technical-documentation",
    "line-length",
    "syntax",
    "typecheck",
    "architecture",
    "cross-component",
    "public-api",
    "agent-configurations",
    "lockfile",
    "workflows",
    "unit-tests",
    "integration-tests",
    "feature-tests",
    "regression-tests",
    "concurrency-tests",
    "security-tests",
    "component-api-tests",
    "platform-smoke",
    "coverage",
    "dependency-audit",
    "secret-scanning",
    "license-compliance",
    "codeql",
    "build",
    "installation",
    "cli-smoke",
    "application-smoke",
    "docker-smoke",
    "docs-build",
)
VALID_RESULTS = {"success", "failure", "cancelled", "skipped"}

__all__ = [
    "EXPECTED_JOBS",
    "GateInputError",
    "format_summary",
    "load_needs",
    "main",
    "validate_needs",
]


class GateInputError(ValueError):
    """Describe invalid or incomplete JSON passed to the final CI gate.

    The error keeps environment parsing separate from gate evaluation so the
    validator can be tested without a GitHub Actions runner.
    """


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow a parsed JSON object to a dictionary with string keys.

    Args:
        value: Untrusted top-level or nested JSON value.

    Returns:
        A string-keyed dictionary, or ``None`` for an invalid shape.
    """
    if not isinstance(value, dict):
        return None

    raw_mapping = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def load_needs(payload: str) -> dict[str, object]:
    """Parse the GitHub ``needs`` context from its JSON environment value.

    Args:
        payload: Serialized object supplied by ``toJSON(needs)``.

    Returns:
        The string-keyed job result mapping.

    Raises:
        GateInputError: If input is empty, invalid JSON, or not an object.
    """
    if not payload.strip():
        reason = "CI_NEEDS_JSON is empty"
        raise GateInputError(reason)

    try:
        value: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        reason = f"CI_NEEDS_JSON is invalid JSON: {exc}"
        raise GateInputError(reason) from exc

    mapping = _string_mapping(value)
    if mapping is None:
        reason = "CI_NEEDS_JSON must be a JSON object"
        raise GateInputError(reason)
    return mapping


def _job_result(value: object) -> str | None:
    """Return a valid GitHub job result from one untrusted entry.

    Args:
        value: JSON value associated with a job identifier.

    Returns:
        A recognized result string, or ``None`` for malformed data.
    """
    mapping = _string_mapping(value)
    if mapping is None:
        return None
    result = mapping.get("result")
    if not isinstance(result, str) or result not in VALID_RESULTS:
        return None
    return result


def validate_needs(results: object) -> list[str]:
    """Reject incomplete or unsuccessful results for mandatory CI jobs.

    Args:
        results: Parsed ``needs`` mapping from GitHub Actions.

    Returns:
        Diagnostic messages. An empty list means every mandatory job passed.
    """
    mapping = _string_mapping(results)
    if mapping is None:
        return ["job results must be a string-keyed object"]

    errors: list[str] = []
    expected = set(EXPECTED_JOBS)
    actual = set(mapping)
    errors.extend(
        f"missing mandatory job result: {job_id}"
        for job_id in sorted(expected - actual)
    )
    errors.extend(
        f"unexpected job result: {job_id}"
        for job_id in sorted(actual - expected)
    )

    for job_id in EXPECTED_JOBS:
        if job_id not in mapping:
            continue
        result = _job_result(mapping[job_id])
        if result is None:
            errors.append(f"invalid result data for mandatory job: {job_id}")
        elif result != "success":
            errors.append(f"mandatory job {job_id} returned {result}")
    return errors


def format_summary(results: dict[str, object]) -> str:
    """Render the observed result for every expected job as Markdown.

    Args:
        results: Parsed result mapping supplied to the gate.

    Returns:
        A table suitable for ``GITHUB_STEP_SUMMARY``.
    """
    lines = [
        "## Mandatory CI gate",
        "",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for job_id in EXPECTED_JOBS:
        result = _job_result(results.get(job_id))
        display = result if result is not None else "missing or invalid"
        lines.append(f"| `{job_id}` | `{display}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Read job results, write an actual-result summary, and return status.

    The script uses only the runner's environment and standard library so it
    can execute even when dependency installation or setup jobs fail.
    """
    payload = os.environ.get("CI_NEEDS_JSON", "")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    try:
        results = load_needs(payload)
    except GateInputError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    summary = format_summary(results)
    if summary_path:
        try:
            with Path(summary_path).open("a", encoding="utf-8") as stream:
                stream.write(summary)
        except OSError as exc:
            sys.stderr.write(f"ERROR: cannot write job summary: {exc}\n")
            return 1

    errors = validate_needs(results)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write("All mandatory CI jobs succeeded.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
