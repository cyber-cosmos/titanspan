"""Test the package root's intentionally small public surface.

The assertion verifies import metadata and the supported application symbol.
"""

from importlib.metadata import version

import pytest

from titanspan import Application, __version__

pytestmark = pytest.mark.unit


def test_package_version_comes_from_distribution_metadata() -> None:
    """Expose installed distribution metadata through the package root.

    The framework does not hard-code its version in the runtime package.
    """
    assert __version__ == version("titanspan")
    assert isinstance(Application, type)
