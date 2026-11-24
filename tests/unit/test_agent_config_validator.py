"""Tests for repository development configuration validation."""

import importlib.util
from pathlib import Path
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/check_agent_configs.py"
SPEC = importlib.util.spec_from_file_location(
    "agent_config_checker", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_repository_agent_configuration_is_valid() -> None:
    """Accept the checked-in instruction and adapter set."""
    assert CHECKER.validate_repository(REPOSITORY_ROOT) == []


def test_skill_validator_requires_metadata_and_workflow_sections(
    tmp_path: Path,
) -> None:
    """Reject skills without required Agent Skills metadata and sections."""
    skill = tmp_path / "example-skill" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        """---
name: example-skill
description: A short description.
---

# Example

## When to use
## References
## Procedure
## Failure modes
## Validation
## Completion criteria
""",
        encoding="utf-8",
    )
    assert CHECKER.validate_skill(skill) == []

    skill.write_text("# Missing metadata\n", encoding="utf-8")
    assert CHECKER.validate_skill(skill)


def test_packaging_config_excludes_scoped_agent_instructions(
    tmp_path: Path,
) -> None:
    """Require source instructions to stay out of the runtime wheel."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.uv.build-backend]\nwheel-exclude = ["**/AGENTS.md"]\n',
        encoding="utf-8",
    )
    assert CHECKER.validate_packaging_config(pyproject) == []

    pyproject.write_text(
        "[tool.uv.build-backend]\nwheel-exclude = []\n",
        encoding="utf-8",
    )
    assert CHECKER.validate_packaging_config(pyproject)


def test_wheel_validator_rejects_agent_instructions(
    tmp_path: Path,
) -> None:
    """Reject development instruction files in a runtime wheel."""
    wheel = tmp_path / "titanspan.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("titanspan/__init__.py", "")
        archive.writestr("titanspan/AGENTS.md", "development rules")

    assert CHECKER.validate_wheel(wheel)


def test_wheel_validator_accepts_runtime_only_contents(
    tmp_path: Path,
) -> None:
    """Accept wheel members that contain only package runtime files."""
    wheel = tmp_path / "titanspan.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("titanspan/__init__.py", "")
        archive.writestr("titanspan/py.typed", "")

    assert CHECKER.validate_wheel(wheel) == []
