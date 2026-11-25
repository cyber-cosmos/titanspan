"""Attach interpreter and dependency metadata to benchmark JSON reports.

pytest-benchmark records hardware, runtime, commit, and measurement data.
This development-only tool adds the installed distribution inventory.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from importlib.metadata import distributions
from pathlib import Path
from typing import cast

__all__ = ["annotate_benchmark_report", "main"]


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow untrusted JSON data to a string-keyed mapping.

    Args:
        value: A parsed JSON value expected to be an object.

    Returns:
        The mapping with string keys, or ``None`` for another shape.
    """
    if not isinstance(value, dict):
        return None
    raw_mapping = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw_mapping):
        return None
    return cast("dict[str, object]", raw_mapping)


def _distribution_inventory() -> dict[str, str]:
    """Return normalized names and versions for installed distributions.

    Returns:
        A deterministic package-name to version mapping.
    """
    inventory: dict[str, str] = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        if name is None:
            continue
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        inventory[normalized_name] = distribution.version
    return dict(sorted(inventory.items()))


def annotate_benchmark_report(path: Path) -> int:
    """Add reproducibility metadata to a pytest-benchmark JSON artifact.

    Args:
        path: Existing pytest-benchmark JSON report to enrich.

    Returns:
        Number of installed distributions recorded in the report.

    Raises:
        ValueError: If the report is unreadable or has an invalid structure.
        TypeError: If required report fields have unsupported types.
        OSError: If the validated report cannot be written.
    """
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        reason = f"cannot read benchmark report {path}: {exc}"
        raise ValueError(reason) from exc

    report = _string_mapping(parsed)
    if report is None:
        reason = "benchmark report must be a JSON object"
        raise ValueError(reason)
    if not isinstance(report.get("benchmarks"), list):
        reason = "benchmark report must include a benchmarks list"
        raise TypeError(reason)
    if _string_mapping(report.get("machine_info")) is None:
        reason = "benchmark report must include machine_info metadata"
        raise TypeError(reason)
    if "environment" in report:
        reason = "benchmark report already contains environment metadata"
        raise ValueError(reason)

    # Only package names and versions are attached; no env vars, paths,
    # credentials, or runner-specific secrets are collected.
    environment: dict[str, object] = {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "distributions": _distribution_inventory(),
    }
    report["environment"] = environment
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
    return len(cast("dict[str, str]", environment["distributions"]))


def main() -> int:
    """Enrich the benchmark artifact and report recorded package count.

    Return a nonzero process status for malformed reports or write failures.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        type=Path,
        nargs="?",
        default=Path("benchmark-results/results.json"),
        help="pytest-benchmark JSON output path",
    )
    args = parser.parse_args()

    try:
        count = annotate_benchmark_report(args.report)
    except (OSError, TypeError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    sys.stdout.write(f"Recorded {count} installed package versions.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
