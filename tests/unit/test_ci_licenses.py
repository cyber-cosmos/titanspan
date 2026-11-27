"""Test dependency license inventory parsing and explicit policy checks.

The audit accepts only reviewed license identifiers and reports unknown
metadata for maintainer review.
"""

import json

import pytest
from scripts.ci.check_licenses import (
    parse_exported_requirements,
    validate_license_inventory,
)

pytestmark = pytest.mark.unit
EXPECTED_LICENSE_RECORDS = 4


def test_runtime_requirement_export_yields_normalized_package_names() -> None:
    """Parse locked requirement names and ignore comments and options.

    Name normalization follows Python package metadata conventions.
    """
    requirements = (
        "# Generated lock export\n"
        "AnyIO==4.16.0 \\\n"
        "    --hash=sha256:abc\n"
        "titanspan==0.1.0 ; python_version >= '3.12'\n"
    )

    assert parse_exported_requirements(requirements) == {
        "anyio",
        "titanspan",
    }


def test_license_inventory_accepts_reviewed_runtime_licenses() -> None:
    """Accept known runtime package licenses and return report rows.

    The runtime email-validation dependencies use reviewed licenses.
    """
    payload = json.dumps(
        [
            {"Name": "AnyIO", "License": "MIT"},
            {
                "Name": "num2words",
                "License": (
                    "GNU Library or Lesser General Public License (LGPL)"
                ),
            },
            {"Name": "dnspython", "License": "ISC"},
            {
                "Name": "email-validator",
                "License": "The Unlicense (Unlicense)",
            },
        ]
    )

    rows, errors = validate_license_inventory(
        payload,
        expected_packages={
            "anyio",
            "num2words",
            "dnspython",
            "email-validator",
        },
    )

    assert len(rows) == EXPECTED_LICENSE_RECORDS
    assert errors == []


def test_license_inventory_accepts_official_cffi_mit_zero_license() -> None:
    """Accept CFFI's reviewed MIT No Attribution SPDX identifier.

    CFFI reports this official permissive license in the locked runtime set.
    """
    payload = json.dumps([{"Name": "cffi", "License": "MIT-0"}])

    rows, errors = validate_license_inventory(
        payload,
        expected_packages={"cffi"},
    )

    assert rows == [("cffi", "MIT-0")]
    assert errors == []


def test_license_inventory_uses_verified_locked_license_metadata() -> None:
    """Accept licenses verified from the locked package artifacts.

    aiohttp declares its combined SPDX expression. Taskiq's helper wheel
    includes an MIT license file but omits machine-readable license metadata.
    """
    payload = json.dumps(
        [
            {
                "Name": "aiohttp",
                "Version": "3.14.5",
                "License": "Apache-2.0 AND MIT",
            },
            {
                "Name": "taskiq-dependencies",
                "Version": "1.5.7",
                "License": "UNKNOWN",
            },
        ]
    )

    rows, errors = validate_license_inventory(
        payload,
        expected_packages={"aiohttp", "taskiq-dependencies"},
    )

    assert rows == [
        ("aiohttp", "Apache-2.0 AND MIT"),
        ("taskiq-dependencies", "MIT"),
    ]
    assert errors == []


def test_license_inventory_rejects_unreviewed_helper_version() -> None:
    """Do not transfer a reviewed license override to later releases.
    """  # fmt: skip
    payload = json.dumps(
        [
            {
                "Name": "taskiq-dependencies",
                "Version": "1.5.8",
                "License": "UNKNOWN",
            }
        ]
    )

    _, errors = validate_license_inventory(
        payload,
        expected_packages={"taskiq-dependencies"},
    )

    assert errors == ["unknown license metadata for taskiq-dependencies"]


def test_license_inventory_rejects_unreviewed_and_missing_data() -> None:
    """Report metadata gaps and licenses outside the reviewed policy.

    New or changed dependency licenses require a policy review before CI can
    pass.
    """
    payload = json.dumps(
        [
            {"Name": "AnyIO", "License": "Unknown"},
            {"Name": "unlisted", "License": "Proprietary"},
        ]
    )

    _, errors = validate_license_inventory(
        payload,
        expected_packages={"anyio", "missing"},
    )

    assert any("unreviewed license" in error for error in errors)
    assert any("unknown license metadata" in error for error in errors)
    assert any("unexpected package" in error for error in errors)
    assert any("missing package" in error for error in errors)
