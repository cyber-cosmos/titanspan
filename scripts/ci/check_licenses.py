"""Audit licenses for locked runtime dependencies and optional extras.

The script exports the locked runtime dependency profile, then asks
``pip-licenses`` to inspect only those installed packages. Development-only
tools do not change the licenses users receive with Titanspan.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from typing import cast

from packaging.requirements import InvalidRequirement, Requirement

REQUIREMENT_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")
ALLOWED_LICENSES = {
    "Apache-2.0",
    "Apache-2.0 OR BSD-2-Clause",
    "Apache Software License",
    "BSD License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GNU Library or Lesser General Public License (LGPL)",
    "ISC",
    "ISC License (ISCL)",
    "MIT",
    "MIT License",
    "MIT OR Apache-2.0",
    "MPL-2.0",
    "MIT-0",
    "PSF-2.0",
    "Python Software Foundation License",
    "The Unlicense (Unlicense)",
}

__all__ = [
    "ALLOWED_LICENSES",
    "main",
    "parse_exported_requirements",
    "validate_license_inventory",
]


def _normalize_package_name(name: str) -> str:
    """Normalize a distribution name as defined by Python packaging rules.

    Args:
        name: Distribution name from a lock export or license report.

    Returns:
        Lowercase canonical form with runs of separators replaced by ``-``.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_exported_requirements(requirements: str) -> set[str]:
    """Extract pinned distribution names from a locked uv export.

    Args:
        requirements: Requirements-format output from ``uv export``.

    Returns:
        Canonical package names, excluding comments and hash continuation
        lines.
    """
    names: set[str] = set()
    for line in requirements.splitlines():
        normalized_line = line.strip().removesuffix("\\")
        match = REQUIREMENT_LINE.match(normalized_line)
        if match is None:
            continue
        try:
            requirement = Requirement(normalized_line)
        except InvalidRequirement:
            continue
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        names.add(_normalize_package_name(match.group(1)))
    return names


def _string_mapping(value: object) -> dict[str, object] | None:
    """Narrow an untrusted JSON object to a string-keyed mapping.

    Args:
        value: Parsed license-report item.

    Returns:
        Valid string-keyed object or ``None`` for malformed data.
    """
    if not isinstance(value, dict):
        return None
    raw_mapping = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw_mapping):
        return None
    return cast("dict[str, object]", raw_mapping)


def validate_license_inventory(
    payload: str,
    *,
    expected_packages: set[str],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Compare reported runtime licenses with locked packages and policy.

    Args:
        payload: JSON output from ``pip-licenses --format=json``.
        expected_packages: Canonical runtime package names from uv export.

    Returns:
        Sorted package/license rows and policy diagnostics.
    """
    try:
        parsed: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        reason = f"license report contains invalid JSON: {exc}"
        return [], [reason]
    if not isinstance(parsed, list):
        return [], ["license report must be a JSON list"]

    records = cast("list[object]", parsed)
    observed: dict[str, str] = {}
    errors: list[str] = []
    for record in records:
        mapping = _string_mapping(record)
        name = mapping.get("Name") if mapping else None
        license_name = mapping.get("License") if mapping else None
        if not isinstance(name, str) or not isinstance(license_name, str):
            errors.append("license report contains an invalid package record")
            continue
        normalized = _normalize_package_name(name)
        observed[normalized] = license_name.strip()

    errors.extend(
        f"missing package license metadata: {package}"
        for package in sorted(expected_packages - set(observed))
    )
    errors.extend(
        f"unexpected package in runtime license report: {package}"
        for package in sorted(set(observed) - expected_packages)
    )

    for package, license_name in sorted(observed.items()):
        if not license_name or license_name.casefold() in {
            "unknown",
            "unknown license",
            "unlicensed",
        }:
            errors.append(f"unknown license metadata for {package}")
        elif license_name not in ALLOWED_LICENSES:
            errors.append(f"unreviewed license for {package}: {license_name}")

    rows = sorted(observed.items())
    return rows, errors


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a fixed local verification command and preserve its diagnostics.

    Args:
        command: Argument vector without shell interpretation.

    Returns:
        Captured standard output and error streams.
    """
    # The executable and arguments come from PATH and fixed project policy;
    # shell parsing is deliberately disabled for both subprocesses.
    return subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def main() -> int:
    """Audit locked runtime dependencies and emit a license inventory.

    Return a nonzero process status when dependency metadata is incomplete,
    a license is unreviewed, or a required tool fails.
    """
    uv = shutil.which("uv")
    pip_licenses = shutil.which("pip-licenses")
    if uv is None or pip_licenses is None:
        sys.stderr.write("ERROR: uv and pip-licenses must be installed.\n")
        return 1

    export = _run_command(
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--all-extras",
            "--no-emit-project",
            "--format",
            "requirements.txt",
        ]
    )
    if export.returncode != 0:
        sys.stderr.write(export.stderr)
        return export.returncode
    packages = parse_exported_requirements(export.stdout)
    if not packages:
        sys.stderr.write("ERROR: locked runtime dependency profile is empty.\n")
        return 1

    report = _run_command(
        [
            pip_licenses,
            "--from=mixed",
            "--format=json",
            "--packages",
            *sorted(packages),
        ]
    )
    if report.returncode != 0:
        sys.stderr.write(report.stderr)
        return report.returncode

    rows, errors = validate_license_inventory(
        report.stdout,
        expected_packages=packages,
    )
    for name, license_name in rows:
        sys.stdout.write(f"{name}: {license_name}\n")
    for error in errors:
        sys.stderr.write(f"ERROR: {error}\n")
    if errors:
        return 1

    sys.stdout.write(f"Audited {len(rows)} locked runtime dependencies.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
