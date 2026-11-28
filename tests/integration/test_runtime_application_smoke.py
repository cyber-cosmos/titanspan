"""Exercise the installed-package smoke application's native composition.

The test runs the same Application path used by the clean-install CI job.
"""

import pytest
from scripts.ci.runtime_smoke import (
    SmokeResult,
    require_smoke_success,
    run_smoke,
)

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

    assert result["database_verified"] is True
    assert result["number_utilities_verified"] is True
    assert result["health"] == {
        "status": "ok",
        "application": "Document Processor",
    }
    assert result["documents"] == {"resource": "Document"}
    assert result["json_metadata"] == {"category": "guides"}
    assert result["conventional_route_verified"] is True
    assert result["queue_dispatch_verified"] is True
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
    assert result["concurrent_request_scope_verified"] is True
    assert result["custom_exception_verified"] is True
    assert result["safe_failure_verified"] is True


def test_installed_smoke_rejects_a_failed_integration_check() -> None:
    """Fail the installed-package job when a reported check is false.

    Returning a result object alone must not let a broken integration pass.
    """
    result: SmokeResult = {
        "health": {},
        "documents": {},
        "uploaded_document": {},
        "invalid_upload": {"status": _HTTP_UNPROCESSABLE_STATUS, "body": {}},
        "json_metadata": {},
        "json_validation_safe": True,
        "database_verified": True,
        "number_utilities_verified": True,
        "response_cookie_verified": True,
        "middleware_verified": True,
        "component_fakes": {
            "storage_isolated": True,
            "event_count": 1,
            "log_captured": True,
            "http_status": 200,
        },
        "password_hash_verified": True,
        "console_document_count": 1,
        "testing_context_verified": True,
        "conventional_route_verified": True,
        "concurrent_request_scope_verified": False,
        "custom_exception_verified": True,
        "safe_failure_verified": True,
        "queue_dispatch_verified": True,
    }

    with pytest.raises(RuntimeError, match="request scope isolation"):
        require_smoke_success(result)
