"""Verify routing bindings, WebSockets, and generated OpenAPI schemas.

The cases exercise a real FastAPI host and the native application container.
"""

from collections.abc import AsyncIterator
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated

import anyio
import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.types import Message
from starlette.types import Scope as ASGIScope
from starlette.websockets import WebSocket, WebSocketDisconnect

from titanspan._application_context import active_application_context
from titanspan.contracts.container import Scope, ServiceRegistry
from titanspan.contracts.routing import UriUrlGenerator
from titanspan.foundation import Application
from titanspan.routing import InvalidRouteError, RouteUrlError

pytestmark = pytest.mark.integration
_TWO_CONNECTIONS = 2
_POLICY_VIOLATION_CODE = 1008
_WEBSOCKET_FAILURE = "synthetic WebSocket failure"


class BoundDocument:
    """Represent a value resolved by an explicit route binder.

    The handler receives this typed object instead of a raw path string.
    """

    def __init__(self, document_id: str) -> None:
        """Keep the canonical identifier returned by binding.

        Args:
            document_id: String identifier extracted from the route path.
        """
        self.document_id = document_id


class RouteState(StrEnum):
    """Provide enum values for typed path conversion.

    FastAPI rejects values outside this declared set.
    """

    OPEN = "open"
    CLOSED = "closed"


class CreateDocument(BaseModel):
    """Describe request content accepted by the create route.

    FastAPI validates this model and publishes it in OpenAPI.
    """

    name: str


class CreatedDocument(BaseModel):
    """Describe validated output documented by OpenAPI.

    The route uses this model as its response schema.
    """

    document_id: int
    name: str


class DocumentWriter:
    """Provide an application dependency used by route dispatch.

    Its constructor-injected instance must not appear as request input.
    """

    def create(self, payload: CreateDocument, limit: int) -> CreatedDocument:
        """Build one response value from injected and request values.

        Args:
            payload: Validated JSON body.
            limit: Query parameter selected by the client.

        Returns:
            A typed response model.
        """
        return CreatedDocument(document_id=limit, name=payload.name)


class DocumentWriterProvider:
    """Register one writer through the canonical service registry.

    The application owns this instance for the provider's lifetime.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Contribute the application-owned document writer.

        Args:
            container: Registry shared by Foundation and component providers.
        """
        container.instance(DocumentWriter, DocumentWriter())


class ConnectionValue:
    """Represent a resource whose lifetime belongs to one WebSocket.

    The integration test checks its identity and scope finalization.
    """

    def __init__(self) -> None:
        """Assign an identity that the route can send to its client.

        The identity makes distinct connection scopes observable.
        """
        self.identity = id(self)
        self.closed = False


class ConnectionValueProvider:
    """Register one connection-scoped application value.

    The generator records cleanup when each WebSocket scope exits.
    """

    def __init__(self, values: list[ConnectionValue]) -> None:
        """Retain values so tests can verify connection scope cleanup.

        Args:
            values: Test-owned list populated by the scoped provider.
        """
        self._values = values

    def register(self, container: ServiceRegistry) -> None:
        """Bind the value to the existing connection scope.

        Args:
            container: Native application service registry.
        """
        container.scoped(
            ConnectionValue,
            self._connection_value,
            scope=Scope.CONNECTION,
        )

    async def _connection_value(self) -> AsyncIterator[ConnectionValue]:
        """Yield one observable value until its connection scope exits.

        Yields:
            The value owned by one WebSocket connection.
        """
        value = ConnectionValue()
        self._values.append(value)
        try:
            yield value
        finally:
            value.closed = True

    _values: list[ConnectionValue]


def test_explicit_sync_and_async_bindings_convert_or_return_not_found() -> None:
    """Resolve bound path values before native controller injection.

    Missing bound records return a native 404 response without echoing input.
    """
    application = Application()

    def bind_document(value: str) -> BoundDocument | None:
        """Resolve one document from its route identifier.

        Args:
            value: Untrusted path segment supplied by the client.

        Returns:
            A bound document or ``None`` when the record is absent.
        """
        if value == "missing":
            return None
        return BoundDocument(value)

    async def bind_async(value: str) -> BoundDocument:
        """Resolve one value through an asynchronous lookup boundary.

        Args:
            value: Path segment supplied by the client.

        Returns:
            A bound document carrying the selected identifier.
        """
        return BoundDocument(f"async-{value}")

    def show(document: BoundDocument) -> dict[str, str]:
        """Return the document produced by the explicit binder.

        Args:
            document: Value returned by the registered path binder.

        Returns:
            A JSON mapping containing the bound identifier.
        """
        return {"document_id": document.document_id}

    def show_async(
        async_document: BoundDocument,
    ) -> dict[str, str]:
        """Return the value produced by the asynchronous binder.

        Args:
            async_document: Value returned by its registered binder.

        Returns:
            A JSON mapping containing the bound identifier.
        """
        return {"document_id": async_document.document_id}

    application.router.bind("document", bind_document)
    application.router.bind("async_document", bind_async)
    application.router.get("/documents/{document}", show)
    application.router.get("/async/{async_document}", show_async)

    with TestClient(application.asgi) as client:
        found = client.get("/documents/42")
        missing = client.get("/documents/missing")
        resolved_async = client.get("/async/42")

    assert found.status_code == HTTPStatus.OK
    assert found.json() == {"document_id": "42"}
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert resolved_async.status_code == HTTPStatus.OK
    assert resolved_async.json() == {"document_id": "async-42"}


def test_enum_path_parameters_use_fastapi_conversion() -> None:
    """Convert typed route segments through the existing FastAPI adapter.

    Values outside the enum return the backend's normal validation response.
    """
    application = Application()

    def show_state(state: RouteState) -> dict[str, str]:
        """Return the converted enum value.

        Args:
            state: Enum member parsed from the route path.

        Returns:
            The lowercase state string accepted by the enum.
        """
        return {"state": state.value}

    application.router.get("/states/{state}", show_state)

    with TestClient(application.asgi) as client:
        valid = client.get("/states/open")
        invalid = client.get("/states/unknown")

    assert valid.status_code == HTTPStatus.OK
    assert valid.json() == {"state": "open"}
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_optional_path_parameters_match_and_generate_backend_routes() -> None:
    """Match optional trailing segments through paired FastAPI routes.

    Native metadata stays singular while generated paths dispatch to it.
    """
    application = Application()

    def show(item: str | None = None) -> dict[str, str | None]:
        """Return the optional value selected by the route matcher.

        Args:
            item: Optional trailing path segment.

        Returns:
            The matched or absent path value.
        """
        return {"item": item}

    def show_typed(item: int = 7) -> dict[str, int]:
        """Return the converted optional value and route default.

        Args:
            item: Integer path value or configured integer default.

        Returns:
            The selected integer path value.
        """
        return {"item": item}

    application.router.get("/optional/{item?}", show).name("optional")
    application.router.get("/default/{item?}", show).name(
        "optional.default",
    ).defaults({"item": "guest"})
    application.router.get("/typed/{item?}", show_typed).name(
        "optional.typed",
    ).where_number("item").defaults({"item": "7"})

    with TestClient(application.asgi) as client:
        absent = client.get("/optional")
        present = client.get("/optional/42")
        defaulted = client.get("/default")
        typed_default = client.get("/typed")
        typed_present = client.get("/typed/8")
        generator = application.container.make(UriUrlGenerator)
        generated_absent = generator.route("optional", {}, False)
        generated_present = generator.route(
            "optional",
            {"item": 42},
            False,
        )
        generated_default = generator.route("optional.default", {}, False)
        generated_typed_default = generator.route(
            "optional.typed",
            {},
            False,
        )
        generated_absent_response = client.get(generated_absent)
        generated_present_response = client.get(generated_present)

    assert absent.json() == {"item": None}
    assert present.json() == {"item": "42"}
    assert defaulted.json() == {"item": "guest"}
    assert typed_default.json() == {"item": 7}
    assert typed_present.json() == {"item": 8}
    assert generated_absent == "/optional"
    assert generated_present == "/optional/42"
    assert generated_default == "/default/guest"
    assert generated_typed_default == "/typed/7"
    assert generated_absent_response.json() == {"item": None}
    assert generated_present_response.json() == {"item": "42"}


def test_converter_urls_validate_and_dispatch_through_starlette() -> None:
    """Reverse built-in path converters with the same matcher semantics.

    Invalid converter values must fail before producing a non-matching URL.
    """
    application = Application()

    def show_number(number: int) -> dict[str, int]:
        """Return the integer parsed by the native route converter.

        Args:
            number: Integer path value selected by Starlette.

        Returns:
            The parsed number for the JSON response.
        """
        return {"number": number}

    application.router.get(
        "/numbers/{number:int}",
        show_number,
    ).name("numbers.show")

    with TestClient(application.asgi) as client:
        generator = application.container.make(UriUrlGenerator)
        generated = generator.route(
            "numbers.show",
            {"number": 42},
            False,
        )
        response = client.get(generated)
        with pytest.raises(RouteUrlError):
            generator.route(
                "numbers.show",
                {"number": "not-a-number"},
                False,
            )
        with pytest.raises(RouteUrlError):
            generator.route(
                "numbers.show",
                {"number": -1},
                False,
            )

    assert generated == "/numbers/42"
    assert response.json() == {"number": 42}


def test_unicode_named_url_generation_matches_asgi_route_dispatch() -> None:
    """Quote Unicode path values and dispatch the generated URL correctly.

    Starlette owns route reversal and matching for the same declared path.
    """
    application = Application()

    def show_name(name: str) -> dict[str, str]:
        """Return the decoded Unicode path parameter.

        Args:
            name: Unicode segment decoded by the ASGI route matcher.

        Returns:
            The route parameter as a JSON object.
        """
        return {"name": name}

    application.router.get("/names/{name}", show_name).name("names.show")

    with TestClient(application.asgi) as client:
        generator = application.container.make(UriUrlGenerator)
        generated = generator.route(
            "names.show",
            {"name": "café 東京"},
            False,
        )
        response = client.get(generated)

    assert generated == "/names/caf%C3%A9%20%E6%9D%B1%E4%BA%AC"
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"name": "café 東京"}


def test_openapi_documents_models_and_hides_container_services() -> None:
    """Document request data while leaving container services private.

    FastAPI owns schemas and request validation for supported Pydantic models.
    """
    application = Application(
        service_providers=(DocumentWriterProvider(),),
    )

    async def create(
        payload: CreateDocument,
        limit: Annotated[int, Query()],
        writer: DocumentWriter,
    ) -> object:
        """Create a document through both request data and native DI.

        Args:
            payload: Validated request model supplied in JSON.
            limit: Query parameter converted by FastAPI.
            writer: Application service resolved by the native container.

        Returns:
            The response model produced by the service.
        """
        return writer.create(payload, limit)

    application.router.post("/documents", create).name(
        "documents.create",
    ).tags(["documents"]).summary("Create a document").description(
        "Create one document from validated input.",
    ).deprecated().status_code(HTTPStatus.CREATED).response_model(
        CreatedDocument,
    ).responses({HTTPStatus.CONFLICT: {"description": "Conflict"}})

    with TestClient(application.asgi) as client:
        schema = client.get("/openapi.json").json()
        response = client.post(
            "/documents?limit=17",
            json={"name": "notes"},
        )

    operation = schema["paths"]["/documents"]["post"]
    parameters = [item["name"] for item in operation["parameters"]]

    assert operation["operationId"] == "documents.create"
    assert operation["tags"] == ["documents"]
    assert operation["summary"] == "Create a document"
    assert operation["description"] == (
        "Create one document from validated input."
    )
    assert operation["deprecated"] is True
    assert parameters == ["limit"]
    assert "requestBody" in operation
    assert "201" in operation["responses"]
    assert operation["responses"]["409"]["description"] == "Conflict"
    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {"document_id": 17, "name": "notes"}


def test_invalid_typed_route_default_fails_during_application_startup() -> None:
    """Reject configured values that cannot satisfy their handler annotation.

    FastAPI receives only defaults already converted by the routing adapter.
    """
    application = Application()

    def show(item: int) -> dict[str, int]:
        """Return the integer route value used by the invalid default.

        Args:
            item: Integer path value or configured default.

        Returns:
            The converted route value.
        """
        return {"item": item}

    application.router.get("/items/{item}", show).defaults(
        {"item": "not-an-integer"},
    )

    with (
        pytest.raises(InvalidRouteError, match="cannot be converted"),
        TestClient(application.asgi),
    ):
        pass


def test_websocket_parameter_binding_closes_missing_resources() -> None:
    """Close a connection when explicit path binding finds no resource.

    The Starlette connection API owns the WebSocket close handshake.
    """
    application = Application()

    def bind_room(value: str) -> str | None:
        """Return no room for the missing test identifier.

        Args:
            value: Untrusted room name from the matched path.

        Returns:
            No bound value for the missing room.
        """
        _ = value
        return None

    async def connect(websocket: WebSocket, room: str) -> None:
        """Accept a connection only after route binding succeeds.

        Args:
            websocket: Starlette connection owned by one client.
            room: Bound room value supplied by the native binder.
        """
        _ = room
        await websocket.accept()

    application.router.bind("room", bind_room)
    application.router.websocket("/rooms/{room}", connect)

    with (
        TestClient(application.asgi) as client,
        pytest.raises(WebSocketDisconnect) as disconnected,
        client.websocket_connect("/rooms/missing") as websocket,
    ):
        websocket.receive_text()

    assert disconnected.value.code == _POLICY_VIOLATION_CODE


def test_websocket_routes_reject_invalid_handlers() -> None:
    """Require asynchronous WebSocket handlers with one connection input.

    Invalid declarations fail when Foundation compiles the application routes.
    """
    synchronous = Application()

    def sync_handler(websocket: WebSocket) -> None:
        """Provide a synchronous declaration rejected by the adapter.

        Args:
            websocket: Unused connection placeholder.
        """
        _ = websocket

    synchronous.router.websocket("/sync", sync_handler)
    with (
        pytest.raises(InvalidRouteError, match="must be asynchronous"),
        TestClient(synchronous.asgi),
    ):
        pass

    missing = Application()

    async def no_connection(room_id: int) -> None:
        """Provide an async declaration with no connection parameter.

        Args:
            room_id: Path value that cannot replace a connection input.
        """
        _ = room_id

    missing.router.websocket("/rooms/{room_id}", no_connection)
    with (
        pytest.raises(InvalidRouteError, match="one typed connection"),
        TestClient(missing.asgi),
    ):
        pass


def test_websocket_routes_use_connection_scoped_dependencies() -> None:
    """Accept messages and finalize distinct dependencies on disconnect.

    FastAPI and Starlette own protocol behavior while Container owns cleanup.
    """
    values: list[ConnectionValue] = []
    disconnected: list[int] = []
    application = Application(
        service_providers=(ConnectionValueProvider(values),),
    )

    async def echo(
        websocket: WebSocket,
        room_id: int,
        value: ConnectionValue,
    ) -> None:
        """Echo one text message and expose the scoped service identity.

        Args:
            websocket: Starlette connection used by FastAPI's route adapter.
            room_id: Integer path parameter converted by FastAPI.
            value: Dependency owned by this WebSocket connection.
        """
        await websocket.accept()
        await websocket.send_text(f"{room_id}:{value.identity}")
        message = await websocket.receive_text()
        await websocket.send_text(message)
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            disconnected.append(value.identity)

    application.router.websocket("/rooms/{room_id}", echo).name(
        "rooms.connect",
    )

    with TestClient(application.asgi) as client:
        for room_id in (8, 9):
            with client.websocket_connect(f"/rooms/{room_id}") as websocket:
                first = websocket.receive_text()
                websocket.send_text("hello")
                second = websocket.receive_text()
                assert first.startswith(f"{room_id}:")
                assert second == "hello"

    assert len(values) == _TWO_CONNECTIONS
    assert values[0].identity != values[1].identity
    assert all(value.closed for value in values)
    assert disconnected == [value.identity for value in values]


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_cancelled_websocket_closes_connection_dependencies() -> None:
    """Finalize connection dependencies when ASGI cancels a WebSocket task.

    The ASGI app runs directly so cancellation reaches the route task itself.
    """
    values: list[ConnectionValue] = []
    handler_started = anyio.Event()
    application = Application(
        service_providers=(ConnectionValueProvider(values),),
    )

    async def wait_for_cancellation(
        websocket: WebSocket,
        value: ConnectionValue,
    ) -> None:
        """Hold the connection open after resolving its scoped dependency.

        Args:
            websocket: Starlette connection accepted by the handler.
            value: Dependency owned until cancellation exits the route scope.
        """
        _ = value
        await websocket.accept()
        handler_started.set()
        await anyio.sleep_forever()

    application.router.websocket(
        "/rooms/cancel",
        wait_for_cancellation,
    )
    await application.startup()
    scope: ASGIScope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rooms/cancel",
        "raw_path": b"/rooms/cancel",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 45000),
        "server": ("testserver", 80),
        "subprotocols": [],
        "extensions": {},
        "state": {},
    }
    cancellation_scopes: list[anyio.CancelScope] = []
    first_receive = True

    async def receive() -> Message:
        """Provide the ASGI connection event required before acceptance.

        A disconnect is available if the backend requests another message.
        """
        nonlocal first_receive
        if first_receive:
            first_receive = False
            return {"type": "websocket.connect"}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message: Message) -> None:
        """Accept backend output without simulating protocol behavior.

        Args:
            message: WebSocket ASGI message produced by Starlette.
        """
        _ = message

    async def dispatch() -> None:
        """Run one cancellable application-owned ASGI connection task.

        The local cancel scope makes task ownership explicit in the test.
        """
        with anyio.CancelScope() as cancel_scope:
            cancellation_scopes.append(cancel_scope)
            await application.asgi(scope, receive, send)

    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(dispatch)
            await handler_started.wait()
            cancellation_scopes[0].cancel()
    finally:
        await application.shutdown()

    assert len(values) == 1
    assert values[0].closed


@pytest.mark.anyio
async def test_websocket_failure_finalizes_scope() -> None:
    """Finalize connection resources when a handler fails after acceptance.

    The ASGI server owns connection failure reporting after acceptance.
    """
    values: list[ConnectionValue] = []
    application = Application(
        service_providers=(ConnectionValueProvider(values),),
    )

    async def fail_after_accept(
        websocket: WebSocket,
        value: ConnectionValue,
    ) -> None:
        """Raise after the server accepts the scoped connection.

        Args:
            websocket: Active connection managed by the ASGI host.
            value: Connection-owned dependency finalized on handler failure.
        """
        _ = value
        await websocket.accept()
        raise RuntimeError(_WEBSOCKET_FAILURE)

    application.router.websocket(
        "/rooms/failure",
        fail_after_accept,
    )
    await application.startup()
    scope: ASGIScope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rooms/failure",
        "raw_path": b"/rooms/failure",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 45000),
        "server": ("testserver", 80),
        "subprotocols": [],
        "extensions": {},
        "state": {},
    }
    messages: list[Message] = []
    first_receive = True

    async def receive() -> Message:
        """Provide the connection event required before WebSocket acceptance.

        A later receive reports a disconnect if the host requests one.
        """
        nonlocal first_receive
        if first_receive:
            first_receive = False
            return {"type": "websocket.connect"}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message: Message) -> None:
        """Record messages sent by the actual ASGI application.

        Args:
            message: ASGI protocol message emitted by Starlette.
        """
        messages.append(message)

    try:
        with pytest.raises(RuntimeError, match=_WEBSOCKET_FAILURE):
            await application.asgi(scope, receive, send)
        assert active_application_context() is None
    finally:
        await application.shutdown()

    assert [message["type"] for message in messages] == ["websocket.accept"]
    assert len(values) == 1
    assert values[0].closed
