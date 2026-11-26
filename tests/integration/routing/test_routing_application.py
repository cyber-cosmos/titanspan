"""Verify native routing through the application lifecycle.

These tests exercise the actual application container and ASGI host.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.http import HttpRequest
from titanspan.foundation import Application

pytestmark = pytest.mark.integration


class DocumentCatalog:
    """Provide one application service used by the route integration.

    The service is deliberately registered through Foundation composition.
    """

    def find(self, document_id: int) -> str:
        """Return the requested document label.

        Args:
            document_id: Identifier extracted from the matched route.

        Returns:
            A stable label suitable for the integration assertion.
        """
        return f"document-{document_id}"


class CatalogProvider:
    """Register a real application service for native route injection.

    The provider participates in the same service registry as HTTP services.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Contribute a concrete catalog instance to the app graph.

        Args:
            container: The canonical application service registry.
        """
        container.instance(DocumentCatalog, DocumentCatalog())


def test_application_routes_dispatch_with_native_dependency_injection() -> None:
    """Resolve path parameters and services through one ASGI application.

    The route must use the application-owned registry and request scope.
    """
    application = Application(service_providers=(CatalogProvider(),))

    async def show_document(
        document_id: int,
        catalog: DocumentCatalog,
        request: HttpRequest,
    ) -> dict[str, object]:
        """Return route, dependency, and request data for verification.

        Args:
            document_id: Integer converted from the path segment.
            catalog: Application service injected by the native container.
            request: Request-scoped native HTTP contract.

        Returns:
            JSON-compatible route and service information.
        """
        return {
            "document": catalog.find(document_id),
            "path": request.path,
        }

    application.router.get(
        "/documents/{document_id}",
        show_document,
    ).name("documents.show")

    with TestClient(application.asgi) as client:
        result = client.get("/documents/42")

    assert result.status_code == HTTPStatus.OK
    assert result.json() == {
        "document": "document-42",
        "path": "/documents/42",
    }
