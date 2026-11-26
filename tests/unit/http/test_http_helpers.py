"""Verify HTTP helpers resolve from the active application container.

Local fixtures keep these assertions deterministic.
"""

from typing import cast

import pytest

from titanspan._application_context import bind_application_context
from titanspan.container import Container
from titanspan.contracts.http import ResponseFactory
from titanspan.foundation import Application
from titanspan.http.exceptions import HttpContextError
from titanspan.http.helpers import request, response
from titanspan.http.response import Response

pytestmark = pytest.mark.unit
_ACCEPTED_STATUS = 202


def test_request_and_response_helpers_require_application_context() -> None:
    """Reject helper access outside the application composition context.

    The assertions verify the public result and its error paths.
    """
    with pytest.raises(HttpContextError, match="active HTTP request"):
        request()
    with pytest.raises(HttpContextError, match="Bind an application"):
        response()
    with pytest.raises(HttpContextError, match="Bind an application"):
        response("body")


def test_helpers_translate_missing_service_bindings() -> None:
    """Translate absent container services into actionable HTTP errors.

    The assertions verify the public result and its error paths.
    """
    container = Container()
    with bind_application_context(object(), container):
        with pytest.raises(HttpContextError, match="active HTTP request"):
            request()
        with pytest.raises(HttpContextError, match="application context"):
            response()


def test_response_helper_uses_the_active_application_factory() -> None:
    """Create responses through the same registered application factory.

    The assertions verify the public result and its error paths.
    """
    application = Application(config={"app": {"name": "helper test"}})

    with application.context():
        factory = response()
        plain = response("ready", status=_ACCEPTED_STATUS)
        empty = response(None)

        assert factory is application.make(ResponseFactory)
        assert isinstance(plain, Response)
        assert plain.body == b"ready"
        assert plain.status_code == _ACCEPTED_STATUS
        assert isinstance(empty, Response)
        assert empty.body == b""
        with pytest.raises(TypeError, match="Plain response content"):
            response(cast("str | bytes | None", object()))
