"""Tests for the small, supported package API."""

from importlib.metadata import version

from titanspan import Application, __version__


def test_package_version_comes_from_distribution_metadata() -> None:
    """Expose the installed distribution version from the package root."""
    assert __version__ == version("titanspan")
    assert isinstance(Application, type)
