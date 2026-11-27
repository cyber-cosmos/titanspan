"""Compose a small document intake application with Titanspan.

The application validates multipart metadata, transforms uploads through a
Pipeline, stores them through the application Filesystem, and dispatches an
application event after persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
from pydantic import BaseModel, ConfigDict, Field

from titanspan import Application, app
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.filesystem import StorageManager  # noqa: TC001
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.http import (
    HttpMiddleware,
    HttpRequest,
    HttpResponse,
    MiddlewareDeclaration,
    ParameterizedHttpMiddleware,
    RequestHandler,
    ResponseFactory,
)
from titanspan.contracts.logging import LogWriter  # noqa: TC001
from titanspan.contracts.validation import ValidationService  # noqa: TC001
from titanspan.http import RequestBodyTooLargeError, RequestInputError
from titanspan.pipeline import Pipeline
from titanspan.validation import ValidationRule

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from titanspan.console import Console
    from titanspan.contracts.container import ServiceRegistry
    from titanspan.routing import Router

_APPLICATION_NAME = "Document Processor"
_DEFAULT_MAX_DOCUMENT_BYTES = 1_048_576
_DOCUMENT_TOO_LARGE_ERROR = "The uploaded document exceeds the size limit."
_MISSING_UPLOAD_ERROR = "A document file is required."
_INVALID_PATH_ERROR = "The uploaded filename cannot be used as a path."
_STORE_FAILED_ERROR = "The document could not be stored."
_DOCUMENT_NOT_FOUND_DETAIL = "The requested document does not exist."
_PRIVATE_FAILURE_DETAIL = "private-reference-diagnostic"


class DocumentMetadata(BaseModel):
    """Validate the application-owned document category.

    The category is restricted to safe path characters before storage.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True, slots=True)
class DocumentStored:
    """Describe a successfully stored document.

    Attributes:
        path: Application-relative key written to the selected disk.
        byte_count: Number of bytes stored after processing.
    """

    path: str
    byte_count: int


class DocumentAudit:
    """Retain event results for this application's document workflow.

    Attributes:
        records: Events recorded by the injected application listener.
    """

    __slots__ = ("records",)

    def __init__(self) -> None:
        """Create an empty application-owned event record list.

        Each registered application receives its own audit service.
        """
        self.records: list[DocumentStored] = []


class _RequestScopeProbe:
    """Expose one identity owned by a single HTTP request scope.

    The reference route uses this service to demonstrate request isolation.
    """

    __slots__ = ("token",)

    def __init__(self) -> None:
        """Create an identity that cannot collide across live requests.

        UUID tokens make scope identities stable across overlapping requests.
        """
        self.token = uuid4().hex


class DocumentNotFoundError(Exception):
    """Represent a deliberately safe public document lookup failure.

    The exception carries no user-controlled path or identifier.
    """


class _RequestIdMiddleware:
    """Expose the native request identifier on every response.

    The request identifier comes from Foundation's active HTTP scope.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Add the active request identifier after downstream handling.

        Args:
            request: Native request owned by the active ASGI scope.
            next_handler: Continuation for the next middleware or route.

        Returns:
            The downstream response with one correlation header.
        """
        response = await next_handler(request)
        return response.with_header("X-Request-ID", request.request_id)


class _OperationMiddleware:
    """Add route-declared operation metadata to a response.

    The immutable route declaration carries each operation name.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Continue routes without operation-specific parameters.

        Args:
            request: Native request for the current execution.
            next_handler: Continuation for downstream request handling.

        Returns:
            The downstream response without additional metadata.
        """
        return await next_handler(request)

    async def handle_with_parameters(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
        parameters: tuple[str, ...],
    ) -> HttpResponse:
        """Attach one route-declared operation name to the response.

        Args:
            request: Native request for the current execution.
            next_handler: Continuation for downstream request handling.
            parameters: Immutable operation metadata from this route.

        Returns:
            The downstream response with its operation name.
        """
        if len(parameters) != 1:
            message = "Operation middleware requires one route parameter."
            raise ValueError(message)
        response = await next_handler(request)
        return response.with_header("X-Operation", parameters[0])


_REQUEST_ID_MIDDLEWARE: type[HttpMiddleware] = _RequestIdMiddleware
_OPERATION_MIDDLEWARE: type[ParameterizedHttpMiddleware] = _OperationMiddleware


class DocumentReceipt(BaseModel):
    """Describe the result returned after document persistence.

    Attributes:
        path: Safe key of the stored document.
        bytes: Number of bytes stored by the workflow.
        event_count: Number of matching events handled by this application.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    bytes: int
    event_count: int


class DocumentProcessor:
    """Coordinate validation, processing, storage, events, and logging.

    All collaborators come from Foundation's canonical application graph.
    """

    def __init__(
        self,
        configuration: ConfigRepository,
        events: EventDispatcher,
        logger: LogWriter,
        storage: StorageManager,
        validation: ValidationService,
        audit: DocumentAudit,
    ) -> None:
        """Retain application-owned services and validate the byte limit.

        Args:
            configuration: Canonical repository for application settings.
            events: Application-owned event dispatcher.
            logger: Structured application logger.
            storage: Application-owned storage manager.
            validation: Canonical Pydantic-backed validation service.
            audit: Application-owned event result recorder.

        Raises:
            ValueError: If the document size limit is invalid.
        """
        maximum = configuration.get(
            "documents.max_bytes",
            _DEFAULT_MAX_DOCUMENT_BYTES,
        )
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum <= 0
        ):
            message = "documents.max_bytes must be a positive integer."
            raise ValueError(message)
        self._events = events
        self._logger = logger
        self._maximum = maximum
        self._storage = storage
        self._validation = validation
        self._audit = audit

    async def store(self, request: HttpRequest) -> DocumentReceipt:
        """Validate and persist one bounded multipart document.

        Args:
            request: Request-owned form and upload access.

        Returns:
            A typed receipt for the processed document.

        Raises:
            RequestInputError: If the required file is missing.
            RequestBodyTooLargeError: If the upload exceeds the configured
                byte limit.
            ValidationException: If multipart metadata is invalid.
            RuntimeError: If the selected disk rejects the write.
        """
        values = await request.form()
        metadata = self._validation.validate(
            {"category": values.get("category")},
            DocumentMetadata,
        )
        upload = await request.file("document")
        if upload is None:
            raise RequestInputError(_MISSING_UPLOAD_ERROR)
        content = await upload.read(self._maximum + 1)
        if len(content) > self._maximum:
            raise RequestBodyTooLargeError(_DOCUMENT_TOO_LARGE_ERROR)

        filename = upload.safe_filename
        if filename in {"", ".", ".."} or "/" in filename or "\\" in filename:
            raise RequestInputError(_INVALID_PATH_ERROR)
        processed = (
            Pipeline[bytes, bytes]()
            .send(content)
            .pipe(_trim_document)
            .pipe(_append_line_ending)
            .then_return()
        )
        path = f"{metadata.category}/{filename}"
        stored = await self._storage.disk().put_async(
            path,
            processed,
            overwrite=False,
        )
        if not stored:
            raise RuntimeError(_STORE_FAILED_ERROR)

        event = DocumentStored(path=path, byte_count=len(processed))
        await self._events.dispatch_async(event)
        self._logger.info(
            "Document stored",
            path=path,
            byte_count=len(processed),
        )
        return DocumentReceipt(
            path=path,
            bytes=len(processed),
            event_count=len(self._audit.records),
        )

    _audit: DocumentAudit
    _events: EventDispatcher
    _logger: LogWriter
    _maximum: int
    _storage: StorageManager
    _validation: ValidationService


class _DocumentProvider(ServiceProvider):
    """Register document services and middleware in the native Container.

    Foundation composes these bindings into the application's service graph.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind a request processor and app audit recorder.

        Args:
            container: Canonical service registry owned by Foundation.
        """
        container.singleton(DocumentAudit, DocumentAudit)
        container.singleton(_OperationMiddleware, _OperationMiddleware)
        container.scoped(_RequestScopeProbe, _RequestScopeProbe)
        # Request scope lets each execution resolve its active log service.
        container.scoped(DocumentProcessor, DocumentProcessor)


def _record_document(
    event: DocumentStored,
    audit: DocumentAudit,
) -> None:
    """Record a persisted document through native listener injection.

    Args:
        event: Event dispatched after the storage operation succeeds.
        audit: Application-owned event recorder resolved by the Container.
    """
    audit.records.append(event)


def _is_supported_document_category(value: object) -> bool:
    """Allow only the category configured by this small reference app.

    Args:
        value: Schema-validated category passed to the application rule.

    Returns:
        Whether the value matches the supported reference category.
    """
    return isinstance(value, DocumentMetadata) and value.category == "guides"


def register_console_commands(
    console: Console,
) -> None:
    """Register one native, injected document-count command.

    Args:
        console: Titanspan Console receiving the application command.
    """
    document_commands = console.add_group("documents")

    @document_commands.command(
        "count",
        description="Count documents stored by this application.",
    )
    def count_documents(
        audit: DocumentAudit,
        logger: LogWriter,
    ) -> None:
        """Log the count from the application-owned audit service.

        Args:
            audit: Canonical service resolved by the active Container.
            logger: Canonical application logger resolved by the Container.
        """
        logger.info(
            "Document count inspected",
            document_count=len(audit.records),
        )


def _trim_document(content: bytes) -> bytes:
    """Remove surrounding whitespace from one uploaded document.

    Args:
        content: Bytes uploaded by the client.

    Returns:
        Content with surrounding whitespace removed.
    """
    return content.strip()


def _append_line_ending(content: bytes) -> bytes:
    """Ensure processed text ends with one newline.

    Args:
        content: Trimmed bytes from the preceding Pipeline stage.

    Returns:
        Content with one terminal newline.
    """
    return content if content.endswith(b"\n") else content + b"\n"


async def _health(request: HttpRequest) -> dict[str, str]:
    """Return readiness and verify request context setup.

    Args:
        request: Request scoped to the current ASGI execution.

    Returns:
        A small readiness object.

    Raises:
        RuntimeError: If Foundation did not assign a request identifier.
    """
    if not request.request_id:
        message = "The active request has no request identifier."
        raise RuntimeError(message)
    return {"status": "ok", "application": _APPLICATION_NAME}


async def _discovered_status() -> dict[str, str]:
    """Return a response from the conventional route module.

    Returns:
        A marker showing that Foundation loaded the trusted route file.
    """
    return {"status": "discovered"}


def register_discovered_routes(router: Router) -> None:
    """Register one route through the conventional route-file hook.

    Args:
        router: Application-owned router supplied by route discovery.
    """
    router.get(
        "/runtime/discovered",
        _discovered_status,
    ).name("runtime.discovered")


async def _request_scope_probe(
    probe: _RequestScopeProbe,
    request: HttpRequest,
) -> dict[str, str | bool]:
    """Show request scope identity through concurrent ASGI execution.

    Args:
        probe: Request-scoped service injected into this handler.
        request: Native request for the same execution scope.

    Returns:
        The request identifier and scope identity check.
    """
    resolved_probe = app().make(_RequestScopeProbe)
    await anyio.lowlevel.checkpoint()
    return {
        "request_id": request.request_id,
        "scope_token": probe.token,
        "same_instance": probe is resolved_probe,
    }


async def _missing_document() -> None:
    """Raise an application exception with an intentional public result.

    Raises:
        DocumentNotFoundError: The example has no such document.
    """
    raise DocumentNotFoundError


async def _unexpected_failure() -> None:
    """Raise a private failure to verify safe production handling.

    Raises:
        RuntimeError: A synthetic diagnostic that must remain private.
    """
    raise RuntimeError(_PRIVATE_FAILURE_DETAIL)


def _render_document_not_found(
    request: HttpRequest,
    exception: DocumentNotFoundError,
    response_factory: ResponseFactory,
) -> HttpResponse:
    """Render a fixed public response through native HTTP contracts.

    Args:
        request: Active request for the exception.
        exception: Safe application exception without user input.
        response_factory: Canonical response service from the Container.

    Returns:
        A public not-found response with no internal diagnostic data.
    """
    _ = request, exception
    return response_factory.json(
        {"detail": _DOCUMENT_NOT_FOUND_DETAIL},
        status=404,
    )


def _register_runtime_routes(application: Application) -> None:
    """Register lifecycle probes and safe failure examples.

    Args:
        application: Reference application receiving the native routes.
    """
    application.add_exception_handler(
        DocumentNotFoundError,
        _render_document_not_found,
    )
    application.router.get("/health", _health).name("runtime.health")
    application.router.get(
        "/runtime/request-scope",
        _request_scope_probe,
    ).name("runtime.request-scope")
    application.router.get(
        "/runtime/missing-document",
        _missing_document,
    ).name("runtime.missing-document")
    application.router.get(
        "/runtime/failure",
        _unexpected_failure,
    ).name("runtime.failure")


def create_application(base_path: Path) -> Application:
    """Build the document application for one trusted project root.

    Args:
        base_path: Root for local files and application-owned resources.

    Returns:
        A native Application with provider-backed routes and services.
    """
    application = Application(
        base_path=base_path,
        config={
            "app": {
                "debug": False,
                "name": _APPLICATION_NAME,
            },
            "documents": {"max_bytes": _DEFAULT_MAX_DOCUMENT_BYTES},
            "filesystem": {
                "default": "local",
                "disks": {
                    "local": {
                        "driver": "local",
                        "root": "storage/documents",
                    },
                },
            },
        },
        service_providers=(_DocumentProvider(),),
        http_middleware=(_REQUEST_ID_MIDDLEWARE,),
    )

    async def store_document(
        request: HttpRequest,
        processor: DocumentProcessor,
    ) -> dict[str, str | int]:
        """Delegate one upload to the injected document workflow.

        Args:
            request: Native request contract for this ASGI execution.
            processor: Application-owned workflow service.

        Returns:
            JSON-compatible receipt returned by the document processor.
        """
        receipt = await processor.store(request)
        return {
            "path": receipt.path,
            "bytes": receipt.bytes,
            "event_count": receipt.event_count,
        }

    async def accept_metadata(
        metadata: DocumentMetadata,
    ) -> dict[str, str]:
        """Accept typed JSON metadata after application rule checks.

        Args:
            metadata: Pydantic-validated document metadata.

        Returns:
            The accepted document category.
        """
        return {"category": metadata.category}

    async def issue_document_cookie(
        response_factory: ResponseFactory,
    ) -> HttpResponse:
        """Return a JSON response with a securely configured cookie.

        Args:
            response_factory: Canonical native HTTP response factory.

        Returns:
            A JSON response carrying two HTTP-only secure cookies.
        """
        return (
            response_factory.json(
                {"status": "issued"},
            )
            .with_cookie("document_session", "opaque")
            .with_cookie(
                "document_preference",
                "compact",
            )
        )

    def register_document_listener() -> None:
        """Register the document listener after provider boot.

        The callback runs in this application's active startup context.
        """
        dispatcher = application.make(EventDispatcher)
        _ = dispatcher.listen(DocumentStored, _record_document)

    application.on_startup(register_document_listener)
    _register_runtime_routes(application)
    application.router.post(
        "/documents",
        store_document,
    ).name("documents.store").middleware(
        MiddlewareDeclaration(
            _OPERATION_MIDDLEWARE,
            ("document-upload",),
        ),
    )
    application.router.post(
        "/documents/metadata",
        accept_metadata,
    ).name("documents.metadata").validate_input(
        "metadata",
        rules=(
            ValidationRule(
                field="category",
                check=_is_supported_document_category,
                message="The document category is not supported.",
            ),
        ),
    ).middleware(
        MiddlewareDeclaration(
            _OPERATION_MIDDLEWARE,
            ("metadata-json",),
        ),
    )
    application.router.get(
        "/documents/session-cookie",
        issue_document_cookie,
    ).name("documents.session-cookie")
    return application


def create_asgi_app() -> ASGIApp:
    """Build an ASGI host rooted at the process's selected project path.

    Returns:
        FastAPI's ASGI host configured by the Titanspan application.
    """
    return create_application(Path.cwd()).asgi


__all__ = [
    "DocumentAudit",
    "DocumentMetadata",
    "DocumentProcessor",
    "DocumentReceipt",
    "DocumentStored",
    "create_application",
    "create_asgi_app",
    "register_console_commands",
    "register_discovered_routes",
]
