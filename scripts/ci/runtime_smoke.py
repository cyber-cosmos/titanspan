"""Exercise the installed Titanspan package through a reference application.

The script runs outside the repository import path. It invokes the installed
CLI generator and sends native ASGI requests through the installed wheel.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast

import anyio
from pydantic import BaseModel
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titanspan.console import Console
from titanspan.contracts.filesystem import StorageManager
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.queue import QueueDispatcher
from titanspan.contracts.routing import ControllerAction, UriUrlGenerator
from titanspan.database import (
    DatabaseConnectionError,
    DatabaseManager,
    MigrationManager,
    Model,
    Schema,
    Seeder,
    assert_database_has_async,
    bind_model,
    has_many,
    unique_rule,
)
from titanspan.facades import (
    DB,
    Event,
    Hash,
    Http,
    Log,
    Queue,
    Storage,
    Validation,
)
from titanspan.foundation import Application
from titanspan.queue import Job, QueueManager, QueueServiceProvider
from titanspan.support import Number
from titanspan.testing import AsyncApplicationTest
from titanspan.validation import ValidationException

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from starlette.types import ASGIApp, Message, Scope

    from titanspan.contracts.container import ServiceRegistry

_DOCUMENT_CONTROLLER_NAME = "DocumentController"
_DOCUMENT_CONTROLLER_ACTION = "index"
_GENERATOR_TIMEOUT_SECONDS = 30
_GENERATED_CONTROLLER_MODULE = "_titanspan_installed_document_controller"
_REFERENCE_APPLICATION_MODULE = "_titanspan_document_processor_example"
_REFERENCE_APPLICATION_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "document_processor.py"
)
_MULTIPART_BOUNDARY = "titanspan-installed-reference-boundary"
_INVALID_CATEGORY = "runtime-smoke-secret/../"
_UNSUPPORTED_JSON_CATEGORY = "private-report-token"
_DOCUMENT_CONTENT = b"native reference workflow"
_EXPECTED_STORED_CONTENT = b"native reference workflow\n"
_CONVENTIONAL_ROUTE_MODULE_LINES = (
    '"""Register routes through the installed reference application hook.',
    '"""',
    "",
    "from _titanspan_document_processor_example import (",
    "    register_discovered_routes,",
    ")",
    "from titanspan.routing import Router",
    "",
    "",
    "def register_routes(router: Router) -> None:",
    '    """Register route declarations during application startup.',
    '    """',
    "    register_discovered_routes(router)",
)
_FAKE_DOCUMENT_PATH = "guides/fake-reference.txt"
_FAKE_DOCUMENT_CONTENT = b"isolated fake workflow\n"
_FAKE_HTTP_URL = "https://service.example.test/status"
_HASH_SAMPLE_TEXT = "local reference password sample"
_EXPECTED_HEALTH = {
    "status": "ok",
    "application": "Document Processor",
}
_EXPECTED_GENERATED_DOCUMENT = {"resource": "Document"}
_EXPECTED_DISCOVERED_ROUTE = {"status": "discovered"}
_EXPECTED_JSON_METADATA = {"category": "guides"}
_EXPECTED_COOKIE_RESPONSE = {"status": "issued"}
_EXPECTED_COOKIE_COUNT = 2
_EXPECTED_REQUEST_SCOPE_COUNT = 8
_EXPECTED_QUEUE_JOBS = 2
_EXPECTED_MISSING_DOCUMENT = {
    "detail": "The requested document does not exist.",
}
_EXPECTED_INTERNAL_FAILURE = {"detail": "Internal server error."}
_PRIVATE_FAILURE_DETAIL = "private-reference-diagnostic"
_HTTP_NOT_FOUND_STATUS = 404
_HTTP_INTERNAL_ERROR_STATUS = 500
_HEADER_PAIR_LENGTH = 2
_EXPECTED_DATABASE_USER_COUNT = 2
_RUNTIME_USER_NAME = "Ada"
_RUNTIME_FACTORY_NAME = "Factory User"
_RUNTIME_SEEDED_NAME = "Seeded"
_RUNTIME_ROLLBACK_NAME = "Rollback"
_EXPECTED_UPLOADED_DOCUMENT = {
    "path": "guides/reference.txt",
    "bytes": len(_EXPECTED_STORED_CONTENT),
    "event_count": 1,
}
_HTTP_OK_STATUS = 200
_HTTP_UNPROCESSABLE_STATUS = 422


class _SmokeRollbackError(RuntimeError):
    """Request a deterministic rollback in the installed Database smoke.
    """  # fmt: skip


class _InstalledRuntimeError(RuntimeError):
    """Report a failed assertion from the installed-package smoke.
    """  # fmt: skip

    def __init__(self) -> None:
        """Set one generic message without exposing smoke input values.
        """  # fmt: skip
        super().__init__("Installed Database smoke verification failed.")


class _InstalledRuntimePost(Model):
    """Represent a post in the installed Database smoke application.

    The mapping verifies that relationship loading works from the wheel.
    """

    table = "runtime_posts"
    fillable = ("user_id", "title")

    user_id: Mapped[int] = mapped_column(ForeignKey("runtime_users.id"))
    title: Mapped[str]
    user: Mapped[_InstalledRuntimeUser] = relationship(
        back_populates="posts",
    )


class _InstalledRuntimeUser(Model):
    """Represent one user for installed-package persistence verification.

    The mapped collection exercises native eager relationship loading.
    """

    table = "runtime_users"
    fillable = ("name",)
    factory_attributes: ClassVar[Mapping[str, object]] = {
        "name": _RUNTIME_FACTORY_NAME,
    }

    name: Mapped[str]
    posts: Mapped[list[_InstalledRuntimePost]] = has_many(
        _InstalledRuntimePost,
        back_populates="user",
    )


class _InstalledRuntimeSeeder(Seeder):
    """Insert a row through the installed transactional Seeder API.
    """  # fmt: skip

    async def run_async(self) -> None:
        """Create one row in the seeder's application transaction.
        """  # fmt: skip
        await _InstalledRuntimeUser.create_async(
            {"name": _RUNTIME_SEEDED_NAME},
        )


class _RuntimeNameInput(BaseModel):
    """Validate a name used by the installed Database rule smoke.
    """  # fmt: skip

    name: str


async def _show_runtime_user(
    user: _InstalledRuntimeUser,
) -> dict[str, object]:
    """Return safe fields from a model resolved by route binding.

    Args:
        user: Database model loaded through the installed route binder.

    Returns:
        Safe model data serialized by the native route integration.
    """
    return {"name": user.name}


class _ValidationRejection(TypedDict):
    """Describe one safe validation error observed by the smoke.

    Attributes:
        status: HTTP response status for invalid metadata.
        body: Safe framework validation response.
    """

    status: int
    body: object


class SmokeResult(TypedDict):
    """Describe the observable results from the reference application.

    Attributes:
        health: Readiness endpoint payload.
        documents: Generated controller endpoint payload.
        uploaded_document: Successful document workflow receipt.
        invalid_upload: Status and payload for rejected input.
        json_metadata: Validated typed JSON metadata response.
        json_validation_safe: Whether invalid JSON receives a safe 422.
        response_cookie_verified: Whether native cookies retain attributes.
        middleware_verified: Whether global and route middleware ran.
        component_fakes: Results from application-scoped fake services.
        password_hash_verified: Whether native hashing verifies its result.
        console_document_count: Count returned through an injected command.
        testing_context_verified: Whether native app testing served a route.
        conventional_route_verified: Whether startup discovered a trusted
            route file under the application root.
        concurrent_request_scope_verified: Whether concurrent requests kept
            distinct scoped services and matching Container resolution.
        custom_exception_verified: Whether a public exception used its
            registered native renderer.
        safe_failure_verified: Whether unexpected failure details stayed
            private in both the response and log record.
        queue_dispatch_verified: Whether native Queue access paths shared
            one manager and executed injected job services.
        database_verified: Whether the built-in provider, SQLite modes,
            schema, transactions, models, and relationships worked.
        number_utilities_verified: Whether Number formatting and spelling
            worked from the standard package installation.
    """

    health: object
    documents: object
    uploaded_document: object
    invalid_upload: _ValidationRejection
    json_metadata: object
    json_validation_safe: bool
    response_cookie_verified: bool
    middleware_verified: bool
    component_fakes: _ComponentFakeResults
    password_hash_verified: bool
    console_document_count: int
    testing_context_verified: bool
    conventional_route_verified: bool
    concurrent_request_scope_verified: bool
    custom_exception_verified: bool
    safe_failure_verified: bool
    queue_dispatch_verified: bool
    database_verified: bool
    number_utilities_verified: bool


class _ComponentFakeResults(TypedDict):
    """Summarize fake-backed application service observations.

    Attributes:
        storage_isolated: Whether the fake write stayed out of local storage.
        event_count: Number of document events captured by the event fake.
        log_captured: Whether the active fake logger captured the request.
        http_status: Status returned by the fake outgoing HTTP transport.
    """

    storage_isolated: bool
    event_count: int
    log_captured: bool
    http_status: int


@dataclass(frozen=True, slots=True)
class _AsgiResponse:
    """Retain one JSON response emitted by the reference application.

    Attributes:
        status: HTTP status code from the ASGI response start event.
        body: Decoded JSON response value.
        raw_body: Response bytes used for safe-data assertions.
        headers: All response headers, preserving repeated values.
    """

    status: int
    body: object
    raw_body: bytes
    headers: tuple[tuple[bytes, bytes], ...]


class _SmokeRoutes(TypedDict):
    """Store named paths resolved from the reference route catalog.

    Attributes:
        health: Health endpoint path.
        generated: Path for the generated controller action.
        discovered: Path for the conventionally discovered endpoint.
        upload: Multipart upload path.
        metadata: Typed JSON metadata path.
        cookie: Response-cookie path.
        scope_probe: Request-scope inspection path.
        missing_document: Public exception path.
        failure: Unexpected exception path.
    """

    health: str
    generated: str
    discovered: str
    upload: str
    metadata: str
    cookie: str
    scope_probe: str
    missing_document: str
    failure: str


class _PrimaryHttpResults(TypedDict):
    """Retain core application request results from real ASGI calls.

    Attributes:
        health: Health endpoint response.
        discovered: Conventional route endpoint response.
        generated: Generated controller response.
        upload: Successful multipart workflow response.
        invalid_upload: Safe rejection for invalid multipart input.
        middleware_verified: Whether global and upload middleware ran.
    """

    health: _AsgiResponse
    discovered: _AsgiResponse
    generated: _AsgiResponse
    upload: _AsgiResponse
    invalid_upload: _AsgiResponse
    middleware_verified: bool


class _NativeHttpResults(TypedDict):
    """Retain JSON, cookie, and middleware integration observations.

    Attributes:
        json_metadata: Typed JSON metadata response body.
        json_validation_safe: Whether JSON rejection omits user input.
        response_cookie_verified: Whether cookie headers preserve attributes.
        middleware_verified: Whether metadata route middleware ran.
    """

    json_metadata: object
    json_validation_safe: bool
    response_cookie_verified: bool
    middleware_verified: bool


async def run_smoke() -> SmokeResult:
    """Run CLI generation and a local document workflow through ASGI.

    Raises:
        RuntimeError: If route reversal, response behavior, validation
            safety, or storage verification fails.
        TypeError: If dynamic CLI registration or ASGI output is malformed.

    Returns:
        Application, fake-service, hashing, and rejection results.
    """
    with TemporaryDirectory(prefix="titanspan-reference-") as directory:
        base_path = Path(directory)
        (base_path / "routes").mkdir()
        generated_path = await anyio.to_thread.run_sync(
            _generate_document_controller,
            base_path,
            abandon_on_cancel=False,
        )
        _write_conventional_route_module(base_path)
        application = _load_reference_application(base_path)
        application.router.get(
            "/generated-documents",
            _load_document_action(generated_path),
        ).name("generated.documents.index")

        async with application.asgi.router.lifespan_context(application.asgi):
            routes = _resolve_smoke_routes(application)
            primary_http = await _exercise_primary_http(application, routes)
            native_http = await _exercise_native_http(application, routes)

            fake_results = await _exercise_application_fakes(
                application,
                routes["upload"],
            )
            password_hash_verified = await _verify_application_hasher(
                application,
            )
            console_document_count = await _run_document_count_command(
                application,
            )
            testing_context_verified = await _verify_application_testing()
            concurrent_request_scope_verified = (
                await _verify_concurrent_request_scopes(
                    application,
                    routes["scope_probe"],
                )
            )
            custom_exception_verified = await _verify_public_exception(
                application,
                routes["missing_document"],
            )
            safe_failure_verified = await _verify_safe_unexpected_failure(
                application,
                routes["failure"],
            )
        queue_dispatch_verified = await _verify_installed_queue(base_path)
        database_verified = await _verify_installed_database(base_path)
        number_utilities_verified = (
            Number.format(1234.5) == "1,234.5"
            and Number.spell(42) == "forty-two"
        )

    result: SmokeResult = {
        "health": primary_http["health"].body,
        "documents": primary_http["generated"].body,
        "uploaded_document": primary_http["upload"].body,
        "invalid_upload": {
            "status": primary_http["invalid_upload"].status,
            "body": primary_http["invalid_upload"].body,
        },
        "json_metadata": native_http["json_metadata"],
        "json_validation_safe": native_http["json_validation_safe"],
        "response_cookie_verified": native_http["response_cookie_verified"],
        "middleware_verified": (
            primary_http["middleware_verified"]
            and native_http["middleware_verified"]
        ),
        "component_fakes": fake_results,
        "password_hash_verified": password_hash_verified,
        "console_document_count": console_document_count,
        "testing_context_verified": testing_context_verified,
        "conventional_route_verified": (
            primary_http["discovered"].body == _EXPECTED_DISCOVERED_ROUTE
        ),
        "concurrent_request_scope_verified": (
            concurrent_request_scope_verified
        ),
        "custom_exception_verified": custom_exception_verified,
        "safe_failure_verified": safe_failure_verified,
        "queue_dispatch_verified": queue_dispatch_verified,
        "database_verified": database_verified,
        "number_utilities_verified": number_utilities_verified,
    }
    require_smoke_success(result)
    return result


async def _verify_installed_database(base_path: Path) -> bool:
    """Exercise native Database behavior through the installed package.

    Args:
        base_path: Temporary application root used by the runtime smoke.

    Returns:
        Whether the built-in provider stayed lazy and real SQLite operations
        succeeded through sync and async APIs.
    """
    database_root = base_path / "database-smoke"
    database_root.mkdir()
    database_path = database_root / "runtime.sqlite"
    application = Application(
        base_path=database_root,
        config={
            "database": {
                "default": "sqlite",
                "connections": {
                    "sqlite": {
                        "driver": "sqlite",
                        "database": database_path.name,
                    },
                },
            },
        },
    )
    application.router.get(
        "/runtime-users/{user}",
        _show_runtime_user,
    )
    bind_model(
        application.router,
        _InstalledRuntimeUser,
        parameter="user",
    )
    manager: DatabaseManager
    async with application:
        manager = await application.container.make_async(DatabaseManager)
        _ensure_runtime_check(DB.resolve_service() is manager)
        _ensure_runtime_check(not database_path.exists())

        await _create_runtime_database_schema()
        user = await _create_runtime_database_user()
        _ensure_runtime_check(await _verify_runtime_database_validation())
        await _verify_runtime_database_route(application, user.id)
        await _InstalledRuntimeSeeder().execute_async()
        _ensure_runtime_check(
            await DB.table("runtime_users").count_async()
            == _EXPECTED_DATABASE_USER_COUNT
        )
        await _verify_runtime_migrations(application)
        _ensure_runtime_check(await _verify_runtime_rollback())
        _ensure_runtime_check(
            await anyio.to_thread.run_sync(
                _verify_sync_database,
                application,
            ),
        )

    try:
        manager.engine("sqlite")
    except DatabaseConnectionError:
        return True
    _ensure_runtime_check(False)
    return True


def _ensure_runtime_check(condition: bool) -> None:
    """Fail the installed-package smoke when a behavior check is false.

    Args:
        condition: Result of a real installed-package operation.
    """
    if not condition:
        raise _InstalledRuntimeError


async def _create_runtime_database_schema() -> None:
    """Create the temporary SQLite schema used by the installed smoke.
    """  # fmt: skip
    async with Schema.create("runtime_users") as table:
        table.id()
        table.string("name", length=120)
        table.timestamps()
    async with Schema.create("runtime_posts") as table:
        table.id()
        table.foreign_id("user_id")
        table.string("title", length=120)
        table.timestamps()
        table.foreign(
            "user_id",
            references="runtime_users",
            on_delete="cascade",
        )


async def _create_runtime_database_user() -> _InstalledRuntimeUser:
    """Create and eager-load a model through the installed factory API.

    Returns:
        The persisted model loaded with its related post.
    """
    transient = _InstalledRuntimeUser.factory().make()
    _ensure_runtime_check(not transient.exists)
    _ensure_runtime_check(transient.name == _RUNTIME_FACTORY_NAME)

    user = await (
        _InstalledRuntimeUser.factory()
        .state({"name": _RUNTIME_USER_NAME})
        .create_async()
    )
    await _InstalledRuntimePost.create_async(
        {"user_id": user.id, "title": "First"},
    )
    loaded_user = await (
        _InstalledRuntimeUser.query().with_("posts").find_async(user.id)
    )
    if loaded_user is None:
        raise _InstalledRuntimeError
    _ensure_runtime_check(len(loaded_user.posts) == 1)
    _ensure_runtime_check(loaded_user.posts[0].title == "First")
    await assert_database_has_async(
        "runtime_users",
        {"name": _RUNTIME_USER_NAME},
    )
    return loaded_user


async def _verify_runtime_database_validation() -> bool:
    """Reject a duplicate through Database-backed Validation rules.
    """  # fmt: skip
    duplicate_name = unique_rule(
        _InstalledRuntimeUser,
        "name",
        field="name",
    )
    try:
        await Validation.validate_async(
            {"name": _RUNTIME_USER_NAME},
            _RuntimeNameInput,
            async_rules=(duplicate_name,),
        )
    except ValidationException:
        return True
    return False


async def _verify_runtime_database_route(
    application: Application,
    user_id: int,
) -> None:
    """Resolve a model through the installed route binding integration.

    Args:
        application: Started Application with its Database connection.
        user_id: Persisted user primary key used as the route parameter.
    """
    response = await _send_request(
        application.asgi,
        f"/runtime-users/{user_id}",
    )
    _ensure_runtime_check(response.status == _HTTP_OK_STATUS)
    _ensure_runtime_check(
        response.body == {"name": _RUNTIME_USER_NAME},
    )


async def _verify_runtime_migrations(application: Application) -> None:
    """Apply and roll back a generated Alembic revision.

    Args:
        application: Active Application that owns the migration manager.
    """
    migrations = await application.container.make_async(MigrationManager)
    migration_path = migrations.create_revision("runtime smoke table")
    _prepare_runtime_migration(migration_path)
    await migrations.upgrade_async()
    _ensure_runtime_check(
        await Schema.has_table_async("runtime_migrations"),
    )
    await migrations.rollback_async()
    _ensure_runtime_check(
        not await Schema.has_table_async("runtime_migrations"),
    )


async def _verify_runtime_rollback() -> bool:
    """Confirm a failed transaction leaves no inserted database row.
    """  # fmt: skip
    try:
        async with DB.transaction_async():
            await DB.table("runtime_users").insert_async(
                {"name": _RUNTIME_ROLLBACK_NAME},
            )
            # Leave the transaction body so its context manager rolls back.
            raise _SmokeRollbackError  # noqa: TRY301
    except _SmokeRollbackError:
        pass
    count = await (
        DB.table("runtime_users")
        .where("name", _RUNTIME_ROLLBACK_NAME)
        .count_async()
    )
    return count == 0


def _prepare_runtime_migration(path: Path) -> None:
    """Populate a generated migration with reversible smoke schema changes.

    Args:
        path: Revision generated inside the temporary Application root.
    """
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "from titanspan.database import Migration, run_migration",
        "from titanspan.database import Migration, Schema, run_migration",
    )
    source = source.replace(
        "    def up(self) -> None:\n"
        '        """Apply this revision\'s schema changes."""\n'
        "        pass\n",
        "    def up(self) -> None:\n"
        '        """Apply this revision\'s schema changes."""\n'
        '        with Schema.create("runtime_migrations") as table:\n'
        "            table.id()\n"
        '            table.string("label", length=120)\n',
    )
    source = source.replace(
        "    def down(self) -> None:\n"
        '        """Reverse this revision\'s schema changes."""\n'
        "        pass\n",
        "    def down(self) -> None:\n"
        '        """Reverse this revision\'s schema changes."""\n'
        '        with Schema.drop_if_exists("runtime_migrations"):\n'
        "            pass\n",
    )
    path.write_text(source, encoding="utf-8")


def _verify_sync_database(application: Application) -> bool:
    """Create and query a table through the synchronous SQLite API.

    Args:
        application: Started Application owning the installed smoke database.

    Returns:
        Whether the synchronous schema and query operations round-trip a row.
    """
    with application.context():
        with Schema.create("runtime_sync_values") as table:
            table.id()
            table.string("value", length=40)
        DB.table("runtime_sync_values").insert({"value": "sync"})
        rows = DB.table("runtime_sync_values").select("value").get()
    return len(rows) == 1 and rows[0].get("value") == "sync"


def _resolve_smoke_routes(application: Application) -> _SmokeRoutes:
    """Resolve the reference routes through the canonical URI contract.

    Args:
        application: Reference application with its routes registered.

    Returns:
        Relative paths from the application's authoritative route catalog.

    Raises:
        RuntimeError: If a named route produces an unexpected path.
    """
    generator = application.make(UriUrlGenerator)
    routes: _SmokeRoutes = {
        "health": generator.route("runtime.health", {}, absolute=False),
        "generated": generator.route(
            "generated.documents.index",
            {},
            absolute=False,
        ),
        "discovered": generator.route(
            "runtime.discovered",
            {},
            absolute=False,
        ),
        "upload": generator.route("documents.store", {}, absolute=False),
        "metadata": generator.route(
            "documents.metadata",
            {},
            absolute=False,
        ),
        "cookie": generator.route(
            "documents.session-cookie",
            {},
            absolute=False,
        ),
        "scope_probe": generator.route(
            "runtime.request-scope",
            {},
            absolute=False,
        ),
        "missing_document": generator.route(
            "runtime.missing-document",
            {},
            absolute=False,
        ),
        "failure": generator.route(
            "runtime.failure",
            {},
            absolute=False,
        ),
    }
    expected = {
        "health": "/health",
        "generated": "/generated-documents",
        "discovered": "/runtime/discovered",
        "upload": "/documents",
        "metadata": "/documents/metadata",
        "cookie": "/documents/session-cookie",
        "scope_probe": "/runtime/request-scope",
        "missing_document": "/runtime/missing-document",
        "failure": "/runtime/failure",
    }
    if routes != expected:
        message = "The reference application's named routes are invalid."
        raise RuntimeError(message)
    return routes


async def _exercise_primary_http(
    application: Application,
    routes: _SmokeRoutes,
) -> _PrimaryHttpResults:
    """Exercise health, generated, and multipart routes through ASGI.

    Args:
        application: Started application using production HTTP services.
        routes: Named paths from the canonical route catalog.

    Returns:
        Core successful and rejected request responses.

    Raises:
        RuntimeError: If routing, middleware, validation, or storage fails.
    """
    health = await _send_request(application.asgi, routes["health"])
    _expect_response(
        health,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_HEALTH,
    )
    request_ids = _header_values(health, "x-request-id")
    if len(request_ids) != 1 or not request_ids[0]:
        message = "Global middleware omitted the request identifier."
        raise RuntimeError(message)

    discovered = await _send_request(
        application.asgi,
        routes["discovered"],
    )
    _expect_response(
        discovered,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_DISCOVERED_ROUTE,
    )

    generated = await _send_request(application.asgi, routes["generated"])
    _expect_response(
        generated,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_GENERATED_DOCUMENT,
    )

    upload_body = _multipart_body(
        category="guides",
        filename="../../reference.txt",
        content=_DOCUMENT_CONTENT,
    )
    upload = await _send_request(
        application.asgi,
        routes["upload"],
        method="POST",
        headers=_multipart_headers(upload_body),
        body=upload_body,
    )
    _expect_response(
        upload,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_UPLOADED_DOCUMENT,
    )
    _expect_header(upload, "x-operation", "document-upload")

    invalid_upload_body = _multipart_body(
        category=_INVALID_CATEGORY,
        filename="rejected.txt",
        content=b"must not be stored",
    )
    invalid_upload = await _send_request(
        application.asgi,
        routes["upload"],
        method="POST",
        headers=_multipart_headers(invalid_upload_body),
        body=invalid_upload_body,
    )
    _expect_validation_rejection(invalid_upload)

    disk = application.make(StorageManager).disk()
    stored_content = await disk.get_bytes_async("guides/reference.txt")
    if stored_content != _EXPECTED_STORED_CONTENT:
        message = "The document was not stored with processed bytes."
        raise RuntimeError(message)
    if await disk.exists_async("guides/rejected.txt"):
        message = "Invalid document input reached application storage."
        raise RuntimeError(message)

    return {
        "health": health,
        "discovered": discovered,
        "generated": generated,
        "upload": upload,
        "invalid_upload": invalid_upload,
        "middleware_verified": True,
    }


async def _exercise_native_http(
    application: Application,
    routes: _SmokeRoutes,
) -> _NativeHttpResults:
    """Exercise typed JSON, safe failures, and native response cookies.

    Args:
        application: Started application using production HTTP services.
        routes: Named paths from the canonical route catalog.

    Returns:
        Typed JSON and cookie integration observations.

    Raises:
        RuntimeError: If validation, middleware, or cookie behavior differs.
    """
    metadata_body = json.dumps({"category": "guides"}).encode("utf-8")
    metadata = await _send_request(
        application.asgi,
        routes["metadata"],
        method="POST",
        headers=_json_headers(metadata_body),
        body=metadata_body,
    )
    _expect_response(
        metadata,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_JSON_METADATA,
    )
    _expect_header(metadata, "x-operation", "metadata-json")

    invalid_body = json.dumps(
        {"category": _UNSUPPORTED_JSON_CATEGORY},
    ).encode("utf-8")
    invalid = await _send_request(
        application.asgi,
        routes["metadata"],
        method="POST",
        headers=_json_headers(invalid_body),
        body=invalid_body,
    )
    json_validation_safe = (
        invalid.status == _HTTP_UNPROCESSABLE_STATUS
        and _UNSUPPORTED_JSON_CATEGORY.encode("utf-8") not in invalid.raw_body
    )
    if not json_validation_safe:
        message = "JSON validation exposed rejected input."
        raise RuntimeError(message)

    cookie_response = await _send_request(
        application.asgi,
        routes["cookie"],
    )
    _expect_response(
        cookie_response,
        status=_HTTP_OK_STATUS,
        body=_EXPECTED_COOKIE_RESPONSE,
    )
    cookie_values = _header_values(cookie_response, "set-cookie")
    response_cookie_verified = _secure_cookies_are_preserved(cookie_values)
    if not response_cookie_verified:
        message = "Native response cookies lost values or attributes."
        raise RuntimeError(message)

    return {
        "json_metadata": metadata.body,
        "json_validation_safe": json_validation_safe,
        "response_cookie_verified": response_cookie_verified,
        "middleware_verified": True,
    }


def _secure_cookies_are_preserved(values: Sequence[str]) -> bool:
    """Check duplicate cookie values and default security attributes.

    Args:
        values: Set-Cookie field values from the ASGI response.

    Returns:
        Whether both distinct cookies preserve secure defaults.
    """
    return (
        len(values) == _EXPECTED_COOKIE_COUNT
        and all("secure" in value.lower() for value in values)
        and all("httponly" in value.lower() for value in values)
        and any("document_session=opaque" in value for value in values)
        and any("document_preference=compact" in value for value in values)
    )


async def _exercise_application_fakes(
    application: Application,
    upload_url: str,
) -> _ComponentFakeResults:
    """Substitute application services around real endpoint execution.

    Args:
        application: Started document application using installed services.
        upload_url: Relative URL generated from the application's route table.

    Returns:
        Results that prove fakes intercepted the normal service paths.

    Raises:
        RuntimeError: If a fake leaks into production storage or requests.
    """
    with (
        application.context(),
        Storage.fake() as storage_fake,
        Event.fake() as event_fake,
        Log.fake() as log_fake,
    ):
        fake_body = _multipart_body(
            category="guides",
            filename="fake-reference.txt",
            content=b"isolated fake workflow",
        )
        fake_upload = await _send_request(
            application.asgi,
            upload_url,
            method="POST",
            headers=_multipart_headers(fake_body),
            body=fake_body,
        )
        _expect_response(
            fake_upload,
            status=_HTTP_OK_STATUS,
            body={
                "path": _FAKE_DOCUMENT_PATH,
                "bytes": len(_FAKE_DOCUMENT_CONTENT),
                "event_count": 1,
            },
        )
        storage_fake.assert_stored(
            _FAKE_DOCUMENT_PATH,
            _FAKE_DOCUMENT_CONTENT,
        )
        event_fake.assert_dispatched(object, times=1)
        event_count = len(event_fake.dispatched())
        log_record = log_fake.assert_logged(
            message="Document stored",
            context={"path": _FAKE_DOCUMENT_PATH},
        )
        log_captured = log_record.message == "Document stored"

    production_disk = application.make(StorageManager).disk()
    storage_isolated = not await production_disk.exists_async(
        _FAKE_DOCUMENT_PATH,
    )
    if not storage_isolated:
        message = "The storage fake wrote to the local disk."
        raise RuntimeError(message)

    with application.context():
        async with Http.fake(
            {
                _FAKE_HTTP_URL: Http.fake_response(
                    {"status": "available"},
                ),
            },
        ) as http_fake:
            http_response = await Http.get_async(_FAKE_HTTP_URL)
            http_status = http_response.status_code
            if not http_response.successful():
                message = "The application HTTP fake returned an error."
                raise RuntimeError(message)
            http_fake.assert_sent(
                Http.request_pattern(
                    url=_FAKE_HTTP_URL,
                    method="GET",
                ),
            )

    return {
        "storage_isolated": storage_isolated,
        "event_count": event_count,
        "log_captured": log_captured,
        "http_status": http_status,
    }


async def _verify_concurrent_request_scopes(
    application: Application,
    path: str,
) -> bool:
    """Verify isolated request services through concurrent ASGI execution.

    Args:
        application: Started reference application.
        path: Route exposing a request-scoped service identity.

    Returns:
        Whether every request had its own scope and stable local identity.
    """
    ready = anyio.Event()
    release = anyio.Event()
    lock = anyio.Lock()
    responses: list[_AsgiResponse] = []
    ready_count = 0

    async def send_request() -> None:
        """Wait for the batch, then send one overlapping ASGI request.

        The shared start event releases every task before ASGI dispatch.
        """
        nonlocal ready_count
        async with lock:
            ready_count += 1
            if ready_count == _EXPECTED_REQUEST_SCOPE_COUNT:
                ready.set()
        await release.wait()
        responses.append(await _send_request(application.asgi, path))

    async with anyio.create_task_group() as task_group:
        for _ in range(_EXPECTED_REQUEST_SCOPE_COUNT):
            task_group.start_soon(send_request)
        await ready.wait()
        release.set()

    payloads = [_request_scope_payload(response) for response in responses]
    verified = [payload for payload in payloads if payload is not None]
    return (
        len(responses) == _EXPECTED_REQUEST_SCOPE_COUNT
        and len(verified) == _EXPECTED_REQUEST_SCOPE_COUNT
        and all(response.status == _HTTP_OK_STATUS for response in responses)
        and all(same_instance for _, _, same_instance in verified)
        and len({request_id for request_id, _, _ in verified})
        == _EXPECTED_REQUEST_SCOPE_COUNT
        and len({token for _, token, _ in verified})
        == _EXPECTED_REQUEST_SCOPE_COUNT
    )


def _request_scope_payload(
    response: _AsgiResponse,
) -> tuple[str, str, bool] | None:
    """Read the typed fields returned by the scope-probe endpoint.

    Args:
        response: Captured response from one concurrent request.

    Returns:
        Request identifier, scope token, and identity result when valid.
    """
    body = response.body
    if not isinstance(body, Mapping):
        return None
    # JSON object keys decode as strings at this response boundary.
    payload = cast("Mapping[str, object]", body)
    request_id = payload.get("request_id")
    scope_token = payload.get("scope_token")
    same_instance = payload.get("same_instance")
    if (
        not isinstance(request_id, str)
        or not isinstance(scope_token, str)
        or not isinstance(same_instance, bool)
    ):
        return None
    return request_id, scope_token, same_instance


async def _verify_public_exception(
    application: Application,
    path: str,
) -> bool:
    """Verify a registered application exception renderer through ASGI.

    Args:
        application: Started reference application.
        path: Route raising the deliberately public document exception.

    Returns:
        Whether the renderer emitted the documented safe 404 response.
    """
    response = await _send_request(application.asgi, path)
    return (
        response.status == _HTTP_NOT_FOUND_STATUS
        and response.body == _EXPECTED_MISSING_DOCUMENT
    )


async def _verify_safe_unexpected_failure(
    application: Application,
    path: str,
) -> bool:
    """Verify production failures hide details from responses and logs.

    Args:
        application: Started reference application with debug disabled.
        path: Route raising a synthetic unexpected exception.

    Returns:
        Whether the response and selected log record omit private text.
    """
    with application.context(), Log.fake() as log_fake:
        response = await _send_request(
            application.asgi,
            path,
            expect_internal_error=True,
        )
        record = log_fake.assert_logged(
            "error",
            "Application operation failed",
        )
    return (
        response.status == _HTTP_INTERNAL_ERROR_STATUS
        and response.body == _EXPECTED_INTERNAL_FAILURE
        and _PRIVATE_FAILURE_DETAIL.encode("utf-8") not in response.raw_body
        and record.context.get("exception_type") == "RuntimeError"
        and record.exception is None
        and _PRIVATE_FAILURE_DETAIL not in repr(record)
    )


async def _verify_application_hasher(application: Application) -> bool:
    """Verify generated password data through the application Hasher.

    Args:
        application: Started application with its default hashing provider.

    Returns:
        Whether the hasher accepts the exact text used to create the hash.
    """
    with application.context():
        password_hash = await Hash.make_async(_HASH_SAMPLE_TEXT)
        return await Hash.check_async(_HASH_SAMPLE_TEXT, password_hash)


async def _run_document_count_command(
    application: Application,
) -> int:
    """Run the example command with the active application's audit service.

    Args:
        application: Started application containing document audit records.

    Returns:
        Count read by the Console handler through native injection.

    Raises:
        RuntimeError: If command execution fails.
        TypeError: If the example does not expose its command registration.
    """
    module = sys.modules.get(_REFERENCE_APPLICATION_MODULE)
    register = (
        None
        if module is None
        else getattr(
            module,
            "register_console_commands",
            None,
        )
    )
    if not callable(register):
        message = "The reference application has no Console registration."
        raise TypeError(message)

    console = Console()
    register_console = cast(
        "Callable[[Console], None]",
        register,
    )
    register_console(console)
    with application.context(), Log.fake() as log_fake:
        status = await console.execute_async("documents count")
        log_fake.assert_logged_times(
            1,
            level="info",
            message="Document count inspected",
            context={"document_count": 1},
        )
        record = log_fake.assert_logged(
            level="info",
            message="Document count inspected",
            context={"document_count": 1},
        )
    if status != 0:
        message = "The injected document count command did not complete."
        raise RuntimeError(message)
    document_count = record.context["document_count"]
    if isinstance(document_count, bool) or not isinstance(document_count, int):
        message = "The injected command did not log an integer document count."
        raise TypeError(message)
    return document_count


async def _verify_application_testing() -> bool:
    """Exercise the public async testing context and production ASGI route.

    Returns:
        Whether the test context served the route with an injected service.

    Raises:
        RuntimeError: If application startup, injection, or request fails.
    """
    testing = AsyncApplicationTest()
    testing.application.router.get("/test-probe", _test_probe)
    async with testing as active:
        response = await active.client.get("/test-probe")
        if response.status_code != _HTTP_OK_STATUS:
            message = "The native application test route failed."
            raise RuntimeError(message)
        if response.json() != {"status": "ready"}:
            message = "The native test route returned an unexpected payload."
            raise RuntimeError(message)
    return True


class _RuntimeProbe:
    """Provide a zero-argument service for native test-client injection.

    Attributes:
        status: Safe test value returned through the actual application.
    """

    def __init__(self) -> None:
        """Create a deterministic value for the installed test context.

        The value makes dependency resolution observable in the test route.
        """
        self.status = "ready"

    status: str


async def _test_probe(probe: _RuntimeProbe) -> dict[str, str]:
    """Return a value from a Container-injected test service.

    Args:
        probe: Application service resolved for the test request.

    Returns:
        Small response proving native injection and ASGI execution.
    """
    return {"status": probe.status}


class _QueueSmokeProbe:
    """Record job execution through an application-injected service.
    """  # fmt: skip

    def __init__(self) -> None:
        """Create an empty record owned by one smoke application.
        """  # fmt: skip
        self.values = []

    values: list[str]


@dataclass
class _QueueSmokeJob(Job):
    """Carry one string into an installed-package Queue execution path.
    """  # fmt: skip

    value: str

    async def handle(self, probe: _QueueSmokeProbe) -> None:
        """Record job data through the application Container.

        Args:
            probe: Singleton service registered by the smoke application.
        """
        probe.values.append(self.value)


class _QueueSmokeProvider(ServiceProvider):
    """Register one observer for the installed Queue smoke application.
    """  # fmt: skip

    def __init__(self, probe: _QueueSmokeProbe) -> None:
        """Retain a service instance owned by the smoke application.

        Args:
            probe: Service resolved by each job attempt.
        """
        self._probe = probe

    def register(self, container: ServiceRegistry) -> None:
        """Bind the observer through Foundation's canonical registry.

        Args:
            container: Application-owned Titanspan service registry.
        """
        container.instance(_QueueSmokeProbe, self._probe)

    _probe: _QueueSmokeProbe


async def _verify_installed_queue(base_path: Path) -> bool:
    """Exercise Queue facade, contract, Container, and sync driver together.

    Args:
        base_path: Temporary root used by the installed reference app.

    Returns:
        Whether both public dispatch paths use one canonical manager.
    """
    queue_path = base_path / "queue-smoke"
    queue_path.mkdir()
    probe = _QueueSmokeProbe()
    application = Application(
        base_path=queue_path,
        config={"app": {"name": "installed-queue-reference"}},
        service_providers=(
            _QueueSmokeProvider(probe),
            QueueServiceProvider(jobs=(_QueueSmokeJob,)),
        ),
    )
    async with application:
        manager = application.make(QueueManager)
        dispatcher = application.make(QueueDispatcher)
        contract_receipt = await dispatcher.dispatch_async(
            _QueueSmokeJob("contract")
        )
        facade_receipt = await Queue.dispatch_async(_QueueSmokeJob("facade"))
        return (
            manager is dispatcher
            and Queue.manager() is manager
            and contract_receipt.state == "executed"
            and facade_receipt.state == "executed"
            and probe.values == ["contract", "facade"]
            and len(probe.values) == _EXPECTED_QUEUE_JOBS
        )


def _generate_document_controller(base_path: Path) -> Path:
    """Generate one controller through the installed Titanspan CLI.

    Args:
        base_path: Isolated application root used as the CLI working directory.

    Returns:
        The generated controller path inside ``base_path``.

    Raises:
        RuntimeError: If CLI execution or artifact creation fails.
    """
    # Fixed argv keeps this installed CLI check shell-free and trusted.
    result = run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "titanspan",
            "make:controller",
            "documents.DocumentController",
        ],
        cwd=base_path,
        capture_output=True,
        text=True,
        timeout=_GENERATOR_TIMEOUT_SECONDS,
        check=False,
    )
    generated_path = (
        base_path
        / "app"
        / "controllers"
        / "documents"
        / "document_controller.py"
    )
    if result.returncode != 0 or not generated_path.is_file():
        message = (
            "The installed Titanspan controller generator failed "
            f"(status {result.returncode})."
        )
        raise RuntimeError(message)
    return generated_path


def _write_conventional_route_module(base_path: Path) -> None:
    """Create a trusted conventional route hook for the reference app.

    Args:
        base_path: Isolated project root containing its routes directory.
    """
    route_path = base_path / "routes" / "web.py"
    source = "\n".join(_CONVENTIONAL_ROUTE_MODULE_LINES) + "\n"
    route_path.write_text(source, encoding="utf-8")


def _load_document_action(generated_path: Path) -> ControllerAction:
    """Import one generated controller and select its native action.

    Args:
        generated_path: Controller file created by the installed CLI.

    Returns:
        A controller action for registration with the native Router.

    Raises:
        RuntimeError: If generated source cannot provide the expected class.
    """
    spec = spec_from_file_location(
        _GENERATED_CONTROLLER_MODULE,
        generated_path,
    )
    if spec is None or spec.loader is None:
        message = "The generated controller could not be imported."
        raise RuntimeError(message)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = getattr(module, _DOCUMENT_CONTROLLER_NAME, None)
    if not isinstance(controller, type):
        message = "The generated controller class is missing."
        raise TypeError(message)
    # This narrow cast marks the generated module as the dynamic boundary.
    return cast("ControllerAction", (controller, _DOCUMENT_CONTROLLER_ACTION))


def _load_reference_application(base_path: Path) -> Application:
    """Import the example and create an application at the selected root.

    Args:
        base_path: Isolated project root shared with the installed CLI.

    Returns:
        The example's native Foundation application.

    Raises:
        RuntimeError: If the example does not expose its factory.
    """
    spec = spec_from_file_location(
        _REFERENCE_APPLICATION_MODULE,
        _REFERENCE_APPLICATION_PATH,
    )
    if spec is None or spec.loader is None:
        message = "The document processor example could not be imported."
        raise RuntimeError(message)
    module = module_from_spec(spec)
    sys.modules[_REFERENCE_APPLICATION_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[_REFERENCE_APPLICATION_MODULE]
        raise
    factory = getattr(module, "create_application", None)
    if not callable(factory):
        message = "The document processor example has no application factory."
        raise TypeError(message)
    typed_factory = cast("Callable[[Path], Application]", factory)
    return typed_factory(base_path)


def _multipart_headers(body: bytes) -> tuple[tuple[bytes, bytes], ...]:
    """Return headers for the fixed local multipart request boundary.

    Args:
        body: Complete multipart payload sent by the smoke client.

    Returns:
        Content type and byte length headers for the selected boundary.
    """
    return (
        (
            b"content-type",
            f"multipart/form-data; boundary={_MULTIPART_BOUNDARY}".encode(),
        ),
        (b"content-length", str(len(body)).encode()),
    )


def _json_headers(body: bytes) -> tuple[tuple[bytes, bytes], ...]:
    """Return content type and length for one local JSON request.

    Args:
        body: Complete JSON request body sent to the local ASGI application.

    Returns:
        Headers declaring the JSON media type and exact body length.
    """
    return (
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    )


def _multipart_body(
    *,
    category: str,
    filename: str,
    content: bytes,
) -> bytes:
    """Encode one fixed multipart upload without an external client.

    Args:
        category: Form value validated by the native Validation service.
        filename: Client filename used to verify path sanitization.
        content: Upload content passed through the real ASGI parser.

    Returns:
        One complete multipart request body.
    """
    boundary = _MULTIPART_BOUNDARY.encode()
    return b"".join(
        (
            b"--",
            boundary,
            b'\r\nContent-Disposition: form-data; name="category"\r\n\r\n',
            category.encode(),
            b"\r\n--",
            boundary,
            b'\r\nContent-Disposition: form-data; name="document"; filename="',
            filename.encode(),
            b'"\r\nContent-Type: text/plain\r\n\r\n',
            content,
            b"\r\n--",
            boundary,
            b"--\r\n",
        ),
    )


async def _send_request(
    application: ASGIApp,
    path: str,
    *,
    method: str = "GET",
    headers: Sequence[tuple[bytes, bytes]] = (),
    body: bytes = b"",
    expect_internal_error: bool = False,
) -> _AsgiResponse:
    """Send one request through the real ASGI host and capture its response.

    Args:
        application: Native host assembled by Foundation.
        path: Local path selected from the application's URL generator.
        method: HTTP method used for this request.
        headers: Request headers in ASGI byte form.
        body: Complete request body for bounded local smoke payloads.
        expect_internal_error: Whether to accept a completed generic 500
            response followed by the server error middleware re-raise.

    Returns:
        Status and decoded JSON body emitted by the ASGI application.

    Raises:
        RuntimeError: If ASGI emits a malformed or non-JSON response.
    """
    messages: list[Message] = []
    request_sent = False

    async def receive() -> Message:
        """Provide the request body once, then report disconnection.

        Returns:
            One ASGI request or disconnect message.
        """
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        """Capture response events for deterministic smoke assertions.

        Args:
            message: Response start or body event emitted by ASGI.
        """
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": list(headers),
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
    }
    try:
        await application(scope, receive, send)
    except Exception:
        # Starlette re-raises after sending a complete server-error response.
        if not (
            expect_internal_error
            and _has_complete_internal_error_response(messages)
        ):
            raise
    return _decode_response(messages)


def _has_complete_internal_error_response(
    messages: Sequence[Message],
) -> bool:
    """Check that ASGI transmitted a complete generic server error.

    Args:
        messages: Response events observed before the application re-raised.

    Returns:
        Whether a 500 response started and its body completed.
    """
    started = any(
        message.get("type") == "http.response.start"
        and message.get("status") == _HTTP_INTERNAL_ERROR_STATUS
        for message in messages
    )
    completed = any(
        message.get("type") == "http.response.body"
        and message.get("more_body", False) is False
        for message in messages
    )
    return started and completed


def _decode_response(messages: Sequence[Message]) -> _AsgiResponse:
    """Decode the captured ASGI message sequence as a JSON response.

    Args:
        messages: Response events emitted by the native application.

    Returns:
        One status and JSON body from the completed response.

    Raises:
        RuntimeError: If ASGI emits an invalid HTTP response.
        TypeError: If ASGI response fields have invalid types.
    """
    start_events = [
        message
        for message in messages
        if message.get("type") == "http.response.start"
    ]
    body_events = [
        message
        for message in messages
        if message.get("type") == "http.response.body"
    ]
    if len(start_events) != 1 or not body_events:
        observed = [message.get("type") for message in messages]
        reason = f"Malformed ASGI response events: {observed}"
        raise RuntimeError(reason)
    status = start_events[0].get("status")
    if not isinstance(status, int):
        message = "ASGI response start has an invalid status."
        raise TypeError(message)
    chunks = [event.get("body", b"") for event in body_events]
    if not all(isinstance(chunk, bytes) for chunk in chunks):
        message = "ASGI response body chunks must be bytes."
        raise RuntimeError(message)
    raw_body = b"".join(chunk for chunk in chunks if isinstance(chunk, bytes))
    header_value = start_events[0].get("headers", [])
    if not isinstance(header_value, list):
        message = "ASGI response start has invalid headers."
        raise TypeError(message)
    headers: list[tuple[bytes, bytes]] = []
    for header in cast("list[object]", header_value):
        if not isinstance(header, tuple):
            message = "ASGI response header entries must be tuples."
            raise TypeError(message)
        header_pair = cast("tuple[object, ...]", header)
        if (
            len(header_pair) != _HEADER_PAIR_LENGTH
            or not isinstance(header_pair[0], bytes)
            or not isinstance(header_pair[1], bytes)
        ):
            message = "ASGI response header entries must contain bytes."
            raise TypeError(message)
        headers.append((header_pair[0], header_pair[1]))
    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = "ASGI response body is not valid JSON."
        raise RuntimeError(message) from error
    return _AsgiResponse(status, body, raw_body, tuple(headers))


def _header_values(response: _AsgiResponse, name: str) -> tuple[str, ...]:
    """Return every response value for one case-insensitive header name.

    Args:
        response: ASGI response captured by the reference smoke.
        name: Header name to select.

    Returns:
        Decoded values in the order emitted by the ASGI application.
    """
    encoded_name = name.encode("ascii").lower()
    return tuple(
        value.decode("latin-1")
        for header_name, value in response.headers
        if header_name.lower() == encoded_name
    )


def _expect_header(
    response: _AsgiResponse,
    name: str,
    expected: str,
) -> None:
    """Require one exact value for a response header.

    Args:
        response: ASGI response captured by the reference smoke.
        name: Header name to select.
        expected: Exact value required by the smoke.

    Raises:
        RuntimeError: If the selected header differs from its expectation.
    """
    if _header_values(response, name) != (expected,):
        message = f"The reference response omitted the {name} header."
        raise RuntimeError(message)


def _expect_response(
    response: _AsgiResponse,
    *,
    status: int,
    body: object,
) -> None:
    """Fail the installed-package smoke when a response differs.

    Args:
        response: Actual response emitted by the reference application.
        status: Expected HTTP status code.
        body: Expected decoded JSON body.

    Raises:
        RuntimeError: If the status or body does not match.
    """
    if response.status != status or response.body != body:
        message = (
            "The reference application returned an unexpected response "
            f"(status {response.status})."
        )
        raise RuntimeError(message)


def _expect_validation_rejection(response: _AsgiResponse) -> None:
    """Verify safe validation output for a rejected secret-shaped value.

    Args:
        response: Response emitted for invalid multipart metadata.

    Raises:
        RuntimeError: If invalid input is accepted or echoed to the client.
    """
    if response.status != _HTTP_UNPROCESSABLE_STATUS:
        message = "Invalid document metadata did not return HTTP 422."
        raise RuntimeError(message)
    if _INVALID_CATEGORY.encode() in response.raw_body:
        message = "The validation response exposed submitted field content."
        raise RuntimeError(message)


def main() -> int:
    """Run the installed-package smoke and report its process status.

    Returns:
        Zero after the real application and installed CLI pass.

    Raises:
        RuntimeError: If any installed application integration check fails.
    """
    anyio.run(run_smoke)
    sys.stdout.write("Installed Titanspan reference application passed.\n")
    return 0


def require_smoke_success(result: SmokeResult) -> None:
    """Fail the installed smoke if an integration result is false.

    Args:
        result: Observations returned by the real application run.

    Raises:
        RuntimeError: If any expected cross-component behavior is absent.
    """
    fake_results = result["component_fakes"]
    checks = {
        "route discovery": result["conventional_route_verified"],
        "middleware": result["middleware_verified"],
        "storage isolation": fake_results["storage_isolated"],
        "event dispatch": fake_results["event_count"] == 1,
        "logging substitution": fake_results["log_captured"],
        "outgoing HTTP fake": fake_results["http_status"] == _HTTP_OK_STATUS,
        "password hashing": result["password_hash_verified"],
        "Console injection": result["console_document_count"] == 1,
        "native application testing": result["testing_context_verified"],
        "request scope isolation": result["concurrent_request_scope_verified"],
        "public exception rendering": result["custom_exception_verified"],
        "safe unexpected failure": result["safe_failure_verified"],
        "installed Queue integration": result["queue_dispatch_verified"],
        "installed Database integration": result["database_verified"],
        "Number utilities": result["number_utilities_verified"],
        "typed JSON validation": result["json_validation_safe"],
        "response cookie handling": result["response_cookie_verified"],
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    if failed:
        message = (
            "Installed reference checks failed: " + ", ".join(failed) + "."
        )
        raise RuntimeError(message)


if __name__ == "__main__":
    raise SystemExit(main())
