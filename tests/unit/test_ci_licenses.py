"""Test dependency license inventory parsing and explicit policy checks.

The audit accepts only reviewed license identifiers and reports unknown
metadata for maintainer review.
"""

import json

import pytest
from scripts.ci.check_licenses import (
    parse_exported_requirements,
    parse_exported_versions,
    validate_license_inventory,
)

pytestmark = pytest.mark.unit
EXPECTED_LICENSE_RECORDS = 4
EXPECTED_DATABASE_LICENSES = 3


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
    assert parse_exported_versions(requirements) == {
        "anyio": "4.16.0",
        "titanspan": "0.1.0",
    }


def test_license_inventory_uses_exact_locked_license_overrides() -> None:
    """Fill omitted package rows only for reviewed locked versions.

    The database and broker drivers publish release licenses while omitting
    metadata consumed by pip-licenses.
    """
    payload = "[]"
    versions = {
        "aio-pika": "10.2.3",
        "aiormq": "7.2.5",
        "asyncmy": "0.2.18",
        "pamqp": "5.0.0",
        "pymysql": "1.2.4",
        "taskiq-aio-pika": "0.6.1",
        "taskiq-redis": "1.2.4",
    }

    rows, errors = validate_license_inventory(
        payload,
        expected_packages=set(versions),
        expected_versions=versions,
    )

    assert rows == [
        ("aio-pika", "Apache-2.0"),
        ("aiormq", "Apache-2.0"),
        ("asyncmy", "Apache-2.0"),
        ("pamqp", "BSD-3-Clause"),
        ("pymysql", "MIT"),
        ("taskiq-aio-pika", "MIT"),
        ("taskiq-redis", "MIT"),
    ]
    assert errors == []


def test_license_inventory_rejects_unreviewed_omitted_package_version() -> None:
    """Reject omitted license metadata after a package version changes.

    License review is pinned to exact locked versions.
    """
    _, errors = validate_license_inventory(
        "[]",
        expected_packages={"aio-pika"},
        expected_versions={"aio-pika": "10.2.4"},
    )

    assert errors == ["missing package license metadata: aio-pika"]


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


def test_license_inventory_accepts_reviewed_database_licenses() -> None:
    """Accept only the reviewed SQLAlchemy driver license expressions.

    greenlet includes both declared license files. Psycopg and its binary
    package carry their LGPL-3.0-only license files in their distributions.
    """
    payload = json.dumps(
        [
            {"Name": "greenlet", "License": "MIT AND PSF-2.0"},
            {"Name": "psycopg", "License": "LGPL-3.0-only"},
            {"Name": "psycopg-binary", "License": "LGPL-3.0-only"},
        ]
    )

    rows, errors = validate_license_inventory(
        payload,
        expected_packages={"greenlet", "psycopg", "psycopg-binary"},
    )

    assert len(rows) == EXPECTED_DATABASE_LICENSES
    assert errors == []


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
