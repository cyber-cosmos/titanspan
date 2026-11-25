"""Verify that benchmark artifacts include reproducible environment data.

The report supplements pytest-benchmark machine metadata with installed
distribution versions from the locked development environment.
"""

import json
from importlib.metadata import version
from pathlib import Path
from typing import cast

import pytest
from scripts.ci.benchmark_metadata import annotate_benchmark_report

pytestmark = pytest.mark.unit


def _mapping(value: object) -> dict[str, object]:
    """Narrow parsed JSON objects for strict test assertions.

    Args:
        value: Parsed JSON value expected to be an object.

    Returns:
        A string-keyed mapping after validating its runtime shape.
    """
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def test_benchmark_report_records_platform_and_dependency_versions(
    tmp_path: Path,
) -> None:
    """Record interpreter, platform, and installed package versions.

    Args:
        tmp_path: Isolated directory for a representative benchmark report.
    """
    report_path = tmp_path / "results.json"
    report_path.write_text(
        json.dumps(
            {
                "benchmarks": [],
                "commit_info": {},
                "machine_info": {"machine": "test-host"},
                "version": "5.3.1",
            }
        ),
        encoding="utf-8",
    )

    distribution_count = annotate_benchmark_report(report_path)
    parsed: object = json.loads(report_path.read_text(encoding="utf-8"))
    report = _mapping(parsed)
    environment = _mapping(report["environment"])
    installed_distributions = _mapping(environment["distributions"])

    assert distribution_count > 0
    assert environment["python_version"]
    assert environment["platform"]
    assert installed_distributions["pytest-benchmark"] == version(
        "pytest-benchmark"
    )


def test_benchmark_report_rejects_invalid_json(tmp_path: Path) -> None:
    """Reject malformed reports rather than writing partial metadata.

    Args:
        tmp_path: Isolated directory containing malformed JSON.
    """
    report_path = tmp_path / "invalid.json"
    report_path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot read benchmark report"):
        annotate_benchmark_report(report_path)


def test_benchmark_report_rejects_incomplete_structure(
    tmp_path: Path,
) -> None:
    """Reject JSON that is not a pytest-benchmark report.

    Args:
        tmp_path: Isolated directory for an incomplete JSON object.
    """
    report_path = tmp_path / "incomplete.json"
    report_path.write_text(json.dumps({"benchmarks": []}), encoding="utf-8")

    with pytest.raises(TypeError, match="machine_info"):
        annotate_benchmark_report(report_path)
