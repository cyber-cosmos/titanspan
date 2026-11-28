"""Verify built-in runtime capabilities are declared in package metadata.

The standard distribution must install native component dependencies without
requiring optional extras or development groups.
"""

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit


def test_database_and_number_dependencies_are_runtime_requirements() -> None:
    """Require native Database and Number libraries in the base install.

    Optional extras and development groups must not hide required runtime
    dependencies from users of the standard distribution.
    """
    project_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    metadata = tomllib.loads(project_path.read_text(encoding="utf-8"))
    project = metadata["project"]
    required = {
        "aiosqlite",
        "alembic",
        "babel",
        "num2words",
        "sqlalchemy",
    }
    runtime_names = {
        Requirement(value).name.lower() for value in project["dependencies"]
    }
    development_names = {
        Requirement(value).name.lower()
        for value in metadata["dependency-groups"]["dev"]
    }

    assert required <= runtime_names
    assert not required & development_names
    assert not {"database", "numbers"} & project["optional-dependencies"].keys()
