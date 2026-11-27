"""Exercise the installed-package smoke application's native composition.

The test runs the same Application path used by the clean-install CI job.
"""

import pytest
from scripts.ci.runtime_smoke import EXPECTED_RESPONSE, run_smoke

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_runtime_smoke_uses_native_routing_and_injected_services() -> (
    None
):
    """Resolve provider services through a real native ASGI request.

    The installed-package CI job runs this smoke outside the source tree.
    """
    result = await run_smoke()

    assert result == {
        "health": EXPECTED_RESPONSE,
        "documents": {"resource": "Document"},
    }
