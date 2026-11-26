"""Verify HTTP services share the native application composition root.

The integration uses real components and local test services.
"""

import pytest

from titanspan.contracts.http import HttpClient, OutgoingRequest
from titanspan.facades import Config, Http
from titanspan.foundation import Application
from titanspan.http import HttpConfiguration
from titanspan.support import config

pytestmark = pytest.mark.integration


class HttpClientConsumer:
    """Capture the client injected from the application service registry.

    The integration uses real components and local test services.
    """

    def __init__(self, client: HttpClient) -> None:
        """Retain the resolved application-owned client contract.

        The integration uses real components and local test services.
        """
        self.client = client

    client: HttpClient


@pytest.mark.anyio
async def test_http_config_and_client_share_application_owned_services() -> (
    None
):
    """Resolve configured HTTP services through DI, facade, and helpers.

    The integration uses real components and local test services.
    """
    application = Application(
        config={
            "app": {"name": "HTTP service test"},
            "http": {"client": {"timeout": 11.0}},
        }
    )

    async with application:
        client = application.make(HttpClient)
        consumer = application.make(HttpClientConsumer)

        assert consumer.client is client
        assert Http.client() is client
        assert application.make(HttpConfiguration) is (
            application.http_configuration
        )
        assert application.config is Config.repository()
        assert application.config is config()
        assert Config.get("http.client.timeout") == HTTP_TIMEOUT_SECONDS

    with pytest.raises(RuntimeError, match="client is closed"):
        await client.request_async(
            OutgoingRequest(
                method="GET",
                url="http://127.0.0.1/never-sent",
            )
        )


HTTP_TIMEOUT_SECONDS = 11.0
