"""Compose a small document intake application with Titanspan.

The application validates multipart metadata, transforms uploads through a
Pipeline, stores them through the application Filesystem, and dispatches an
application event after persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from titanspan import Application
from titanspan.contracts.config import ConfigRepository  # noqa: TC001
from titanspan.contracts.events import EventDispatcher
from titanspan.contracts.filesystem import StorageManager  # noqa: TC001
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.http import HttpRequest  # noqa: TC001
from titanspan.contracts.logging import LogWriter  # noqa: TC001
from titanspan.contracts.validation import ValidationService  # noqa: TC001
from titanspan.http import RequestBodyTooLargeError, RequestInputError
from titanspan.pipeline import Pipeline

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from titanspan.contracts.container import ServiceRegistry

_APPLICATION_NAME = "Document Processor"
_DEFAULT_MAX_DOCUMENT_BYTES = 1_048_576
_DOCUMENT_TOO_LARGE_ERROR = "The uploaded document exceeds the size limit."
_MISSING_UPLOAD_ERROR = "A document file is required."
_INVALID_PATH_ERROR = "The uploaded filename cannot be used as a path."
_STORE_FAILED_ERROR = "The document could not be stored."


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
    """Register document services in the native Container.

    Foundation composes these bindings into the application's service graph.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind one processor and audit recorder to the application graph.

        Args:
            container: Canonical service registry owned by Foundation.
        """
        container.singleton(DocumentAudit, DocumentAudit)
        container.singleton(DocumentProcessor, DocumentProcessor)


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
    )

    async def health(request: HttpRequest) -> dict[str, str]:
        """Return a health response and verify request context setup.

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

    def register_document_listener() -> None:
        """Register the document listener after provider boot.

        The callback runs in this application's active startup context.
        """
        dispatcher = application.make(EventDispatcher)
        _ = dispatcher.listen(DocumentStored, _record_document)

    application.on_startup(register_document_listener)
    application.router.get("/health", health).name("runtime.health")
    application.router.post(
        "/documents",
        store_document,
    ).name("documents.store")
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
]
