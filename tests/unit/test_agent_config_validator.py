"""Test repository governance validation and runtime packaging boundaries.

The tests exercise real configuration files and temporary archives without
mocking the policy implementation.
"""

from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import check_agent_configs

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


@pytest.mark.security
def test_repository_agent_configuration_is_valid() -> None:
    """Reject unsafe or inconsistent repository agent configurations.

    This policy check covers least-privilege review profiles and development
    asset separation from the framework runtime package.
    """
    assert check_agent_configs.validate_repository(REPOSITORY_ROOT) == []


def test_skill_validator_requires_metadata_and_workflow_sections(
    tmp_path: Path,
) -> None:
    """Require valid Agent Skills metadata and procedure sections.

    Args:
        tmp_path: Isolated directory used to construct skill documents.
    """
    skill = tmp_path / "example-skill" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\n"
        "name: example-skill\n"
        "description: A short description.\n"
        "---\n\n"
        "# Example\n\n"
        "## When to use\n"
        "## References\n"
        "## Procedure\n"
        "## Failure modes\n"
        "## Validation\n"
        "## Completion criteria\n",
        encoding="utf-8",
    )
    assert check_agent_configs.validate_skill(skill) == []

    skill.write_text("# Missing metadata\n", encoding="utf-8")
    assert check_agent_configs.validate_skill(skill)


def test_packaging_config_excludes_scoped_agent_instructions(
    tmp_path: Path,
) -> None:
    """Keep scoped agent instructions outside the distributed wheel.

    Args:
        tmp_path: Isolated directory for temporary project configuration.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.uv.build-backend]\nwheel-exclude = ["**/AGENTS.md"]\n',
        encoding="utf-8",
    )
    assert check_agent_configs.validate_packaging_config(pyproject) == []

    pyproject.write_text(
        "[tool.uv.build-backend]\nwheel-exclude = []\n",
        encoding="utf-8",
    )
    assert check_agent_configs.validate_packaging_config(pyproject)


def test_wheel_validator_rejects_agent_instructions(
    tmp_path: Path,
) -> None:
    """Reject development instruction files from runtime archives.

    Args:
        tmp_path: Isolated directory used to construct a wheel fixture.
    """
    wheel = tmp_path / "titanspan.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("titanspan/__init__.py", "")
        archive.writestr("titanspan/AGENTS.md", "development rules")

    assert check_agent_configs.validate_wheel(wheel)


def test_wheel_validator_accepts_runtime_only_contents(
    tmp_path: Path,
) -> None:
    """Accept runtime files that omit development-only instructions.

    Args:
        tmp_path: Isolated directory used to construct a wheel fixture.
    """
    wheel = tmp_path / "titanspan.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("titanspan/__init__.py", "")
        archive.writestr("titanspan/py.typed", "")

    assert check_agent_configs.validate_wheel(wheel) == []
