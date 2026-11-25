"""Test Python distribution contents and agent-file exclusions.

The package audit treats wheel and source distribution contents as
independent deliverables with different required files.
"""

import pytest
from scripts.ci.check_distributions import validate_sdist, validate_wheel

pytestmark = pytest.mark.unit


def test_wheel_contains_metadata_typing_and_cli_contracts() -> None:
    """Accept a wheel with installable package metadata and no dev assets.

    The wheel must include the runtime typing marker and preserve metadata
    needed for installation, licensing, and the console entry point.
    """
    members = [
        "titanspan/__init__.py",
        "titanspan/py.typed",
        "titanspan-1.2.3.dist-info/METADATA",
        "titanspan-1.2.3.dist-info/entry_points.txt",
        "titanspan-1.2.3.dist-info/licenses/LICENSE",
        "titanspan-1.2.3.dist-info/licenses/THIRD_PARTY_NOTICES.md",
    ]
    metadata = "Name: titanspan\nVersion: 1.2.3\nRequires-Python: >=3.12\n"
    entry_points = "[console_scripts]\ntitanspan = titanspan.console.cli:main\n"

    assert validate_wheel(members, metadata, entry_points) == []


def test_wheel_rejects_missing_runtime_contracts_and_agent_files() -> None:
    """Report missing package files and development-only instructions.

    Repository guidance must remain outside the installed runtime package.
    """
    errors = validate_wheel(
        [
            "titanspan/__init__.py",
            "titanspan/AGENTS.md",
            "titanspan-1.2.3.dist-info/METADATA",
        ],
        "Name: titanspan\nVersion: 1.2.3\n",
        "",
    )

    assert any("py.typed" in error for error in errors)
    assert any("AGENTS.md" in error for error in errors)
    assert any("console_scripts" in error for error in errors)


def test_sdist_contains_build_inputs_without_development_governance() -> None:
    """Accept a source archive with source and required legal metadata.

    The distribution excludes repository-specific agent instructions while
    retaining the files needed to rebuild and attribute the package.
    """
    members = [
        "titanspan-1.2.3/pyproject.toml",
        "titanspan-1.2.3/src/titanspan/__init__.py",
        "titanspan-1.2.3/LICENSE",
        "titanspan-1.2.3/THIRD_PARTY_NOTICES.md",
    ]

    assert validate_sdist(members) == []


def test_sdist_rejects_repository_instructions_and_missing_license() -> None:
    """Reject development instruction files or missing source metadata.

    A source archive must not distribute agent policy as runtime material.
    """
    errors = validate_sdist(
        [
            "titanspan-1.2.3/pyproject.toml",
            "titanspan-1.2.3/src/titanspan/__init__.py",
            "titanspan-1.2.3/src/titanspan/AGENTS.md",
        ]
    )

    assert any("AGENTS.md" in error for error in errors)
    assert any("LICENSE" in error for error in errors)


def test_sdist_validator_rejects_empty_inventory() -> None:
    """Fail closed if archive inspection returns no members.

    Empty inventories can otherwise appear valid when required checks are
    based only on absence of forbidden paths.
    """
    with pytest.raises(ValueError, match="must not be empty"):
        validate_sdist([])
