"""Exercise the installed-package smoke application's native composition.

The test runs the same Application path used by the clean-install CI job.
"""

import pytest
from scripts.ci.runtime_smoke import run_smoke

pytestmark = pytest.mark.integration
_HTTP_UNPROCESSABLE_STATUS = 422


@pytest.mark.anyio
async def test_runtime_smoke_uses_native_routing_and_injected_services() -> (
    None
):
    """Resolve provider services through a real native ASGI request.

    The installed-package CI job runs this smoke outside the source tree.
    """
    result = await run_smoke()

    assert result["health"] == {
        "status": "ok",
        "application": "Document Processor",
    }
    assert result["documents"] == {"resource": "Document"}
    assert result["json_metadata"] == {"category": "guides"}
    assert result["uploaded_document"] == {
        "path": "guides/reference.txt",
        "bytes": 26,
        "event_count": 1,
    }


@pytest.mark.anyio
async def test_runtime_smoke_processes_a_validated_document_upload() -> None:
    """Exercise fakes, hashing, validation, and document processing together.

    The smoke runs against the installed distribution in the mandatory
    clean-environment runtime job.
    """
    result = await run_smoke()

    assert result["uploaded_document"] == {
        "path": "guides/reference.txt",
        "bytes": 26,
        "event_count": 1,
    }
    invalid_upload = result["invalid_upload"]
    assert invalid_upload["status"] == _HTTP_UNPROCESSABLE_STATUS
    assert "runtime-smoke-secret" not in repr(invalid_upload["body"])
    assert result["component_fakes"] == {
        "storage_isolated": True,
        "event_count": 1,
        "log_captured": True,
        "http_status": 200,
    }
    assert result["password_hash_verified"] is True
    assert result["json_validation_safe"] is True
    assert result["response_cookie_verified"] is True
    assert result["middleware_verified"] is True
    assert result["console_document_count"] == 1
    assert result["testing_context_verified"] is True
