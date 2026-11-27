"""Verify native routing behavior through the real ASGI application.

The cases cover matching, middleware, facade identity, and response streams.
"""

from collections.abc import AsyncIterator
from http import HTTPStatus
from threading import get_ident

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_serializer

from titanspan import app, route
from titanspan.container import Scope
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.http import (
    HttpRequest,
    HttpResponse,
    RequestHandler,
    ResponseFactory,
)
from titanspan.facades import Route
from titanspan.foundation import Application
from titanspan.http import Request
from titanspan.routing import EndpointResponseError

pytestmark = pytest.mark.integration

_TRACE: list[str] = []
_ROUTE_MIDDLEWARE_NAMES: list[str] = []
_EXPECTED_PATH = "/documents/create"
_MIDDLEWARE_THREAD_IDS: list[int] = []
_PRIVATE_FIELD_VALUE = "sensitive-omitted-value"


class DocumentCatalog:
    """Provide an injected service used by a controller action.

    The application provider registers this exact object in the native graph.
    """

    def lookup(self, document_id: int) -> str:
        """Return a stable document label for one integer identifier.

        Args:
            document_id: Identifier converted from the matched route path.

        Returns:
            A safe label representing the selected document.
        """
        return f"document-{document_id}"


class CatalogProvider:
    """Register the catalog service through application composition.

    Route controllers resolve this object through the canonical container.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Contribute an application-owned catalog instance.

        Args:
            container: The application's shared service registry.
        """
        container.instance(DocumentCatalog, DocumentCatalog())


class RequestMarker:
    """Represent one request-owned service used by sync route dispatch.

    Each HTTP execution must receive its own instance.
    """


class RequestMarkerProvider:
    """Register a request-owned service through the native container.

    The router must resolve this binding inside its active request scope.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind a request marker to the request lifecycle.

        Args:
            container: Application-owned service registry.
        """
        container.scoped(RequestMarker, scope=Scope.REQUEST)


class DocumentController:
    """Demonstrate request-time controller construction and injection.

    The Router stores the class and method without constructing this object.
    """

    def __init__(self, catalog: DocumentCatalog) -> None:
        """Retain the service resolved for the current application.

        Args:
            catalog: Catalog service registered by ``CatalogProvider``.
        """
        self._catalog = catalog

    async def show(
        self,
        document_id: int,
        request: HttpRequest,
    ) -> dict[str, object]:
        """Return an injected service result and current route metadata.

        Args:
            document_id: Integer parsed from the route path.
            request: Request-scoped native HTTP contract.

        Returns:
            JSON-safe values proving controller and request injection.
        """
        current = Route.current()
        return {
            "document": self._catalog.lookup(document_id),
            "path": request.path,
            "route": None if current is None else current.route_name,
            "route_name": Route.current_route_name(),
        }


class TraceMiddleware:
    """Record route middleware order around endpoint execution.

    The list is reset in each test and is not part of framework state.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Record entry and exit while forwarding the native request.

        Args:
            request: Active request contract.
            next_handler: Remaining route middleware and endpoint.

        Returns:
            Response returned by the downstream route chain.
        """
        route_name = Route.current_route_name()
        if route_name is not None:
            _ROUTE_MIDDLEWARE_NAMES.append(route_name)
        _TRACE.append("before")
        response = await next_handler(request)
        _TRACE.append("after")
        return response


class ThreadMarkerMiddleware:
    """Capture the event-loop thread before a sync endpoint is dispatched.

    The handler must execute on a worker thread rather than block ASGI work.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Record the current thread and continue route processing.

        Args:
            request: Active HTTP request contract.
            next_handler: Remaining route middleware and endpoint.

        Returns:
            Response produced by the downstream route chain.
        """
        _MIDDLEWARE_THREAD_IDS.append(get_ident())
        return await next_handler(request)


class ForwardingMiddleware:
    """Forward a route without changing its response representation.

    The middleware verifies that adding a route layer preserves serialization.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Continue the request and return the downstream response.

        Args:
            request: Native request passed through the middleware chain.
            next_handler: Remaining route dispatch chain.

        Returns:
            The downstream response without transformation.
        """
        return await next_handler(request)


class PublicPayload(BaseModel):
    """Expose public fields from a larger endpoint result.

    FastAPI filters undeclared fields before sending the response.
    """

    name: str


class PublicNestedPayload(BaseModel):
    """Expose only the declared nested response fields.

    Runtime subclasses can carry additional private fields.
    """

    label: str


class PrivateNestedPayload(PublicNestedPayload):
    """Add a nested secret excluded by the public response schema.

    The regression verifies schema-directed nested serialization.
    """

    token: str


class PublicSerializedPayload(BaseModel):
    """Declare aliases and a serializer for a public response shape.

    The declared model must control serialization of runtime subclasses.
    """

    display_name: str = Field(alias="displayName")
    nested: PublicNestedPayload

    @field_serializer("display_name")
    def serialize_display_name(self, value: str) -> str:
        """Apply the declared schema's serializer.

        Args:
            value: Validated public display name.

        Returns:
            The display name in its public wire format.
        """
        return value.upper()


class PrivateSerializedPayload(PublicSerializedPayload):
    """Carry a secret field that the declared response model must omit.

    FastAPI must serialize this instance as its declared parent model.
    """

    password: str


def _ok() -> dict[str, str]:
    """Return a JSON body for simple dispatch assertions.

    Returns:
        A small response object.
    """
    return {"match": "ok"}


def test_static_route_wins_when_dynamic_route_was_registered_first() -> None:
    """Prefer static path segments over an earlier unconstrained parameter.

    FastAPI dispatch must use the native Router's specificity-sorted snapshot.
    """
    application = Application()
    application.router.get("/documents/{document}", _ok)

    def create_document() -> dict[str, str]:
        """Return the static route's distinctive response body.

        Returns:
            A body that distinguishes this action from the dynamic route.
        """
        return {"match": "static"}

    application.router.get("/documents/create", create_document)

    with TestClient(application.asgi) as client:
        response = client.get(_EXPECTED_PATH)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"match": "static"}


def test_constraints_apply_to_partial_method_matches() -> None:
    """Return 404 when a path violates constraints for an unsupported method.

    A constraint failure must not turn into a misleading 405 response.
    Valid values still report method mismatches with the allowed method.
    """
    application = Application()
    application.router.get(
        "/numbers/{number}",
        _ok,
    ).where_number("number")

    with TestClient(application.asgi) as client:
        invalid_get = client.get("/numbers/abc")
        invalid_post = client.post("/numbers/abc")
        valid_post = client.post("/numbers/12")

    assert invalid_get.status_code == HTTPStatus.NOT_FOUND
    assert invalid_post.status_code == HTTPStatus.NOT_FOUND
    assert valid_post.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert valid_post.headers["allow"] == "GET"


def test_path_parameter_named_request_does_not_collide_with_asgi_request() -> (
    None
):
    """Keep an HTTP path value distinct from the private ASGI request object.

    The route adapter must not reserve ordinary application parameter names.
    """
    application = Application()

    def show_record(request: str) -> dict[str, str]:
        """Return the route value whose name matches the common request name.

        Args:
            request: Value captured from the path template.

        Returns:
            A JSON mapping containing the captured path value.
        """
        return {"request": request}

    application.router.get("/records/{request}", show_record)

    with TestClient(application.asgi) as client:
        response = client.get("/records/current")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"request": "current"}


def test_reserved_adapter_parameter_name_can_be_a_route_parameter() -> None:
    """Avoid collisions with the adapter's synthetic Starlette parameter.

    Path values retain their application-facing names after dispatch.
    """
    application = Application()

    def capture(_titanspan_asgi_request: str) -> dict[str, str]:
        """Return the value whose name resembles the private adapter input.

        Args:
            _titanspan_asgi_request: Value captured from the route path.

        Returns:
            The original path parameter under its native name.
        """
        return {"captured": _titanspan_asgi_request}

    application.router.get(
        "/collision/{_titanspan_asgi_request}",
        capture,
    )

    with TestClient(application.asgi) as client:
        result = client.get("/collision/value")

    assert result.json() == {"captured": "value"}


def test_endpoint_with_keyword_rest_accepts_all_path_values() -> None:
    """Forward path parameters to handlers that accept arbitrary keywords.

    The container receives only backend-captured route values.
    """
    application = Application()

    def capture(**values: object) -> dict[str, object]:
        """Return all path values accepted through keyword rest.

        Args:
            **values: Values captured from the route template.

        Returns:
            JSON-compatible route data.
        """
        return values

    application.router.get("/items/{item_id}", capture)

    with TestClient(application.asgi) as client:
        result = client.get("/items/17")

    assert result.json() == {"item_id": "17"}


def test_endpoint_values_normalize_and_reject_arbitrary_objects() -> None:
    """Normalize supported native values through the response factory.

    Unsupported Python objects fail rather than exposing their attributes.
    """
    application = Application()

    def no_content() -> None:
        """Return no content for the response adapter.

        The response factory supplies the correct bodyless status.
        """

    def text() -> str:
        """Return plain text from a synchronous endpoint.

        Returns:
            A stable string response body.
        """
        return "plain"

    def bytes_body() -> bytes:
        """Return byte content from a synchronous endpoint.

        Returns:
            A stable byte response body.
        """
        return b"binary"

    def json_body() -> list[object]:
        """Return a supported JSON collection.

        Returns:
            A list with nested JSON scalar values.
        """
        return ["valid", {"nested": 1}]

    def invalid_json() -> dict[str, object]:
        """Return a mapping containing an unsupported nested object.

        Returns:
            An invalid payload rejected by the native response boundary.
        """
        return {"secret": object()}

    application.router.get("/empty", no_content)
    application.router.get("/text", text)
    application.router.get("/bytes", bytes_body)
    application.router.get("/json", json_body)
    application.router.get("/invalid", invalid_json)

    with TestClient(application.asgi) as client:
        empty = client.get("/empty")
        text_result = client.get("/text")
        bytes_result = client.get("/bytes")
        json_result = client.get("/json")
        with pytest.raises(EndpointResponseError):
            client.get("/invalid")

    assert empty.status_code == HTTPStatus.NO_CONTENT
    assert text_result.text == "plain"
    assert bytes_result.content == b"binary"
    assert json_result.json() == ["valid", {"nested": 1}]


@pytest.mark.parametrize(
    "status",
    [200, 201, 202, 204, 205, 304],
)
def test_none_result_returns_an_empty_response_with_selected_status(
    status: int,
) -> None:
    """Keep empty endpoint results valid for content and bodyless statuses.

    An explicit JSON null remains available through ``ResponseFactory.json``.
    """
    application = Application()

    def empty_result() -> None:
        """Return no representation body.

        Routing chooses an empty response status for this result.
        """

    definition = application.router.get(f"/empty/{status}", empty_result)
    definition.status_code(status)

    with TestClient(application.asgi) as client:
        result = client.get(f"/empty/{status}")

    assert result.status_code == status
    assert result.content == b""


def test_json_null_requires_an_explicit_json_response() -> None:
    """Distinguish JSON null from an empty endpoint result.

    Explicit serialization must preserve the JSON representation.
    """
    application = Application()

    def json_null() -> object:
        """Return JSON null as an explicit representation.

        The response factory must serialize this value as JSON.
        """
        return application.make(ResponseFactory).json(None)

    application.router.get("/json-null", json_null)

    with TestClient(application.asgi) as client:
        result = client.get("/json-null")

    assert result.status_code == HTTPStatus.OK
    assert result.content == b"null"


def test_route_middleware_preserves_response_model_serialization() -> None:
    """Keep media type and model filtering stable when middleware is added.

    Both routes pass through the same response-model serialization contract.
    """
    application = Application()

    def scalar() -> str:
        """Return a scalar response model.

        The route tests model serialization with and without middleware.
        """
        return "plain-value"

    def payload() -> dict[str, str]:
        """Return fields that exercise response filtering.

        FastAPI must omit the field absent from the response model.
        """
        return {"name": "public", "internal": "private"}

    def explicit_response() -> HttpResponse:
        """Return an explicit response that bypasses model serialization.

        The test checks the documented backend response behavior.
        """
        return application.make(ResponseFactory).json(
            {"name": "public", "internal": "explicit"},
        )

    application.router.get("/scalar", scalar).response_model(str)
    application.router.get("/scalar/middleware", scalar).response_model(
        str,
    ).middleware(ForwardingMiddleware)
    application.router.get("/payload", payload).response_model(PublicPayload)
    application.router.get("/payload/middleware", payload).response_model(
        PublicPayload,
    ).middleware(ForwardingMiddleware)
    application.router.get("/explicit", explicit_response).response_model(
        PublicPayload,
    )
    application.router.get(
        "/explicit/middleware",
        explicit_response,
    ).response_model(PublicPayload).middleware(ForwardingMiddleware)

    with TestClient(application.asgi) as client:
        results = [
            client.get(path)
            for path in (
                "/scalar",
                "/scalar/middleware",
                "/payload",
                "/payload/middleware",
                "/explicit",
                "/explicit/middleware",
            )
        ]

    assert results[0].headers["content-type"] == "application/json"
    assert results[1].headers["content-type"] == "application/json"
    assert results[0].content == results[1].content == b'"plain-value"'
    assert results[2].json() == results[3].json() == {"name": "public"}
    assert (
        results[4].json()
        == results[5].json()
        == {
            "name": "public",
            "internal": "explicit",
        }
    )


def test_declared_response_schema_serializes_runtime_subclasses() -> None:
    """Exclude runtime subclass fields through every response path.

    The same Pydantic schema must control direct and middleware responses.
    """
    application = Application()
    payload = PrivateSerializedPayload(
        displayName="public",
        nested=PrivateNestedPayload(
            label="safe",
            token=_PRIVATE_FIELD_VALUE,
        ),
        password=_PRIVATE_FIELD_VALUE,
    )

    def direct_payload() -> PrivateSerializedPayload:
        """Return a subclass instance for the direct response path.

        The declared route model excludes subclass-only fields.
        """
        return payload

    def middleware_payload() -> PrivateSerializedPayload:
        """Return the same subclass instance through route middleware.

        The declared route model must filter all nested subclass fields.
        """
        return payload

    def direct_collection() -> list[PrivateSerializedPayload]:
        """Return subclass instances inside the direct collection path.

        The collection's declared item schema must filter private fields.
        """
        return [payload]

    def middleware_collection() -> list[PrivateSerializedPayload]:
        """Return subclass instances through middleware normalization.

        The collection's declared item schema remains authoritative.
        """
        return [payload]

    application.router.get("/schema/direct", direct_payload).response_model(
        PublicSerializedPayload,
    )
    application.router.get(
        "/schema/middleware",
        middleware_payload,
    ).response_model(PublicSerializedPayload).middleware(
        ForwardingMiddleware,
    )
    application.router.get(
        "/schema/direct-list",
        direct_collection,
    ).response_model(list[PublicSerializedPayload])
    application.router.get(
        "/schema/middleware-list",
        middleware_collection,
    ).response_model(list[PublicSerializedPayload]).middleware(
        ForwardingMiddleware,
    )

    with TestClient(application.asgi) as client:
        results = [
            client.get(path)
            for path in (
                "/schema/direct",
                "/schema/middleware",
                "/schema/direct-list",
                "/schema/middleware-list",
            )
        ]

    expected = {
        "displayName": "PUBLIC",
        "nested": {"label": "safe"},
    }
    assert results[0].json() == results[1].json() == expected
    assert results[2].json() == results[3].json() == [expected]
    for result in results:
        assert _PRIVATE_FIELD_VALUE not in result.text


def test_invalid_response_model_fails_consistently_with_middleware() -> None:
    """Keep invalid response models as server errors on both paths.

    Invalid endpoint output is not reported as client input validation.
    """
    application = Application()

    def invalid_payload() -> dict[str, object]:
        """Return endpoint output that omits a required response field.

        Both response-model paths must reject the invalid value.
        """
        return {"nested": {"label": "safe"}}

    application.router.get(
        "/schema/invalid",
        invalid_payload,
    ).response_model(PublicSerializedPayload)
    application.router.get(
        "/schema/invalid-middleware",
        invalid_payload,
    ).response_model(PublicSerializedPayload).middleware(
        ForwardingMiddleware,
    )

    with TestClient(
        application.asgi,
        raise_server_exceptions=False,
    ) as client:
        direct = client.get("/schema/invalid")
        middleware = client.get("/schema/invalid-middleware")

    assert direct.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert middleware.status_code == direct.status_code


def test_callable_and_classmethod_controllers_resolve() -> None:
    """Construct callable controllers only when their routes are dispatched.

    Classmethod actions and invokable controller classes share native DI.
    """
    application = Application()

    class CallableController:
        """Define an invokable controller without a routing base class.

        Foundation resolves it using the canonical application container.
        """

        def __call__(self) -> str:
            """Return a short marker from an invokable controller.

            Returns:
                Stable text used to identify the dispatched action.
            """
            return "callable"

    class ClassMethodController:
        """Define a controller action bound to its class.

        The router must not treat the class as an already-created service.
        """

        @classmethod
        def show(cls) -> str:
            """Return a marker from a classmethod route action.

            Args:
                cls: Controller type bound by Python's descriptor.

            Returns:
                Stable text used to identify the dispatched action.
            """
            return cls.__name__

    application.router.get("/callable", CallableController)
    application.router.get("/class-method", ClassMethodController.show)

    with TestClient(application.asgi) as client:
        callable_result = client.get("/callable")
        classmethod_result = client.get("/class-method")

    assert callable_result.text == "callable"
    assert classmethod_result.text == "ClassMethodController"


def test_redirect_route_uses_the_native_response_factory() -> None:
    """Build a redirect endpoint through the application-owned factory.

    The relative destination is passed through native redirect validation.
    """
    application = Application()
    application.router.redirect("/old", "/new")

    with TestClient(application.asgi, follow_redirects=False) as client:
        result = client.get("/old")

    assert result.status_code == HTTPStatus.SEE_OTHER
    assert result.headers["location"] == "/new"


def test_constraints_and_method_mismatches_are_distinguished() -> None:
    """Return 404 for a failed parameter constraint and 405 for a method.

    Method errors retain the backend-generated Allow header.
    """
    application = Application()
    application.router.get(
        "/documents/{document_id}",
        _ok,
    ).where_number("document_id")

    with TestClient(application.asgi) as client:
        invalid_path = client.get("/documents/abc")
        wrong_method = client.post("/documents/12")

    assert invalid_path.status_code == HTTPStatus.NOT_FOUND
    assert wrong_method.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert wrong_method.headers["allow"] == "GET"


def test_domain_constraints_match_the_configured_request_host() -> None:
    """Match a route only when the Host header has its configured domain.

    Requests for another hostname must not reach the bound endpoint.
    """
    application = Application()
    application.router.get("/health", _ok).domain("api.example.test")

    with TestClient(application.asgi) as client:
        matched = client.get(
            "/health",
            headers={"host": "api.example.test"},
        )
        rejected = client.get(
            "/health",
            headers={"host": "evil.example.test"},
        )

    assert matched.status_code == HTTPStatus.OK
    assert rejected.status_code == HTTPStatus.NOT_FOUND


def test_controller_facade_and_route_middleware_share_application_state() -> (
    None
):
    """Use the same Router and service instance for facade and HTTP dispatch.

    Controller construction stays request-time and middleware is ordered.
    """
    _TRACE.clear()
    _ROUTE_MIDDLEWARE_NAMES.clear()
    application = Application(service_providers=(CatalogProvider(),))
    application.router.alias_middleware("trace", TraceMiddleware)
    application.router.get(
        "/documents/{document_id}",
        (DocumentController, "show"),
    ).name("documents.show").middleware("trace")

    with application.context():
        assert Route.router() is application.router
        assert route("documents.show", {"document_id": 42}) == ("/documents/42")

    with TestClient(application.asgi) as client:
        response = client.get("/documents/42")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "document": "document-42",
        "path": "/documents/42",
        "route": "documents.show",
        "route_name": "documents.show",
    }
    assert _TRACE == ["before", "after"]
    assert _ROUTE_MIDDLEWARE_NAMES == ["documents.show"]


def test_global_and_route_middleware_wrap_endpoint_in_order() -> None:
    """Run global middleware outside route middleware without deduplication.

    Registering one middleware at both levels is explicit and invokes it twice.
    """
    _TRACE.clear()
    application = Application(http_middleware=(TraceMiddleware,))
    application.router.alias_middleware("trace", TraceMiddleware)

    def endpoint() -> dict[str, str]:
        """Mark endpoint execution between both middleware layers.

        Returns:
            A small successful response body.
        """
        _TRACE.append("endpoint")
        return {"status": "ok"}

    application.router.get("/middleware", endpoint).middleware("trace")

    with TestClient(application.asgi) as client:
        response = client.get("/middleware")

    assert response.status_code == HTTPStatus.OK
    assert _TRACE == ["before", "before", "endpoint", "after", "after"]


def test_sync_endpoint_uses_worker_thread_and_native_dependency_injection() -> (
    None
):
    """Run sync endpoint work away from the ASGI event-loop thread.

    Context-local service resolution must remain available in that worker.
    """
    _MIDDLEWARE_THREAD_IDS.clear()
    application = Application(service_providers=(CatalogProvider(),))
    application.router.alias_middleware("thread", ThreadMarkerMiddleware)

    def show_document(catalog: DocumentCatalog) -> dict[str, object]:
        """Return injected service output and the executing thread identity.

        Args:
            catalog: Native application service injected into the endpoint.

        Returns:
            JSON values proving off-loop execution and successful injection.
        """
        return {
            "document": catalog.lookup(7),
            "thread": get_ident(),
        }

    application.router.get("/sync", show_document).middleware("thread")

    with TestClient(application.asgi) as client:
        response = client.get("/sync")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["document"] == "document-7"
    assert _MIDDLEWARE_THREAD_IDS
    assert response.json()["thread"] != _MIDDLEWARE_THREAD_IDS[0]


def test_sync_endpoint_reuses_request_scoped_injection() -> None:
    """Keep scope identity when a sync endpoint runs in a worker thread.

    The active application and request context must propagate to the worker.
    """
    application = Application(service_providers=(RequestMarkerProvider(),))

    def show(marker: RequestMarker) -> dict[str, bool]:
        """Compare injected and explicitly resolved request services.

        Args:
            marker: Instance resolved for the current request.

        Returns:
            Whether both native resolution paths share the scoped instance.
        """
        return {"same": marker is app().container.make(RequestMarker)}

    application.router.get("/sync-scope", show)

    with TestClient(application.asgi) as client:
        response = client.get("/sync-scope")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"same": True}


def test_openapi_exposes_path_inputs_but_not_injected_services() -> None:
    """Build API parameters from route paths rather than DI annotations.

    Application services must stay outside the public HTTP request schema.
    """
    application = Application(service_providers=(CatalogProvider(),))
    application.router.get(
        "/documents/{document_id}",
        (DocumentController, "show"),
    ).name("documents.show").summary("Show one document")

    with TestClient(application.asgi) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/documents/{document_id}"]["get"]
    parameter_names = [item["name"] for item in operation["parameters"]]

    assert parameter_names == ["document_id"]
    assert operation["summary"] == "Show one document"


def test_streaming_response_keeps_request_scope_alive_until_transmission() -> (
    None
):
    """Keep request attributes and current route available during iteration.

    ASGI scope cleanup occurs only after the streaming body has been sent.
    """
    observed: list[tuple[str, str | None]] = []
    application = Application()

    async def stream(
        request: Request,
        factory: ResponseFactory,
    ) -> HttpResponse:
        """Construct a stream whose later chunk reads active request state.

        Args:
            request: Request object owned by the active request scope.
            factory: Native response factory owned by the application.

        Returns:
            A streaming response whose body checks its active context.
        """

        async def chunks() -> AsyncIterator[bytes]:
            """Yield content while recording route context between chunks.

            The iterator executes as the ASGI response is transmitted.
            """
            yield b"first"
            observed.append(
                (request.path, Route.current_route_name()),
            )
            yield b"second"

        return factory.stream(chunks(), content_type="text/plain")

    application.router.get("/stream", stream).name("stream")

    with TestClient(application.asgi) as client:
        response = client.get("/stream")

    assert response.content == b"firstsecond"
    assert observed == [("/stream", "stream")]


def test_applications_own_distinct_route_collections() -> None:
    """Keep registrations isolated when two applications coexist.

    The Route facade follows the active application context.
    """
    first = Application()
    second = Application()
    first.router.get("/first", _ok).name("first")
    second.router.get("/second", _ok).name("second")

    with first.context():
        assert Route.router() is first.router
        assert route("first") == "/first"

    with second.context():
        assert Route.router() is second.router
        assert route("second") == "/second"

    assert first.router.has("first")
    assert not first.router.has("second")
