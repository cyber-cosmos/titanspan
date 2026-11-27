"""Measure native HTTP and Routing operations against local workloads.

The benchmarks use in-process ASGI clients and a loopback HTTP server. They
report measurements without enforcing timing thresholds.
"""

from __future__ import annotations

import asyncio
import tracemalloc
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING, Protocol, cast

import httpx2
import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    HttpRequest,
    HttpResponse,
    OutgoingRequest,
    RequestHandler,
)
from titanspan.foundation import Application
from titanspan.http import HttpPoolRequest, HttpRequestPool, PendingRequest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from pytest_benchmark.fixture import BenchmarkFixture

_APPLICATION_ROUTE_COUNT = 24
_HTTP_BATCH_SIZE = 16
_HTTP_CONCURRENCY = 4
_HTTP_MAX_CONNECTIONS = 100
_HTTP_MAX_KEEPALIVE_CONNECTIONS = 20
_HTTP_KEEPALIVE_EXPIRY_SECONDS = 5.0
_HTTP_TIMEOUT_SECONDS = 5.0
_STREAM_CHUNK_SIZE = 16_384
_STREAM_CHUNK_COUNT = 128
_SERVER_JOIN_TIMEOUT_SECONDS = 2
_SMALL_RESPONSE = b'{"status":"ok"}'
_STREAM_CHUNK = b"x" * _STREAM_CHUNK_SIZE
_STREAM_LENGTH = _STREAM_CHUNK_SIZE * _STREAM_CHUNK_COUNT
_HTTP_BENCHMARK_FAILURE = "The local HTTP benchmark failed."


class _MemoryBenchmarkFixture(Protocol):
    """Describe the supported pytest-benchmark memory measurement calls.

    The plugin types its dynamically provided methods incompletely.
    """

    extra_info: dict[str, object]

    def pedantic(
        self,
        target: Callable[..., object],
        *,
        args: tuple[object, ...],
        rounds: int,
        iterations: int,
    ) -> object:
        """Run fixed samples for an expensive memory measurement.

        Args:
            target: Measurement operation repeated by the fixture.
            args: Arguments passed to the measured operation.
            rounds: Number of independent samples.
            iterations: Calls made during each sample.

        Returns:
            The final operation result.
        """
        ...


class _BenchmarkCatalog:
    """Provide a small service for native route dependency injection.

    This service keeps handler work stable across benchmark samples.
    """

    def label(self, document_id: int) -> str:
        """Return one deterministic label for a route parameter.

        Args:
            document_id: Integer value parsed from the route path.

        Returns:
            A stable document label.
        """
        return f"document-{document_id}"


class _PassThroughMiddleware:
    """Exercise the native middleware pipeline without extra application work.

    The benchmark isolates dispatch composition overhead.
    """

    async def handle(
        self,
        request: HttpRequest,
        next_handler: RequestHandler,
    ) -> HttpResponse:
        """Call the next handler without changing request or response data.

        Args:
            request: Active request provided by the native ASGI boundary.
            next_handler: Next middleware or route handler in the pipeline.

        Returns:
            The downstream response.
        """
        return await next_handler(request)


class _LocalHttpHandler(BaseHTTPRequestHandler):
    """Serve fixed small and streaming responses for local measurements.

    The server uses HTTP/1.1 so clients can reuse pooled connections.
    """

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        """Return a small payload or a bounded multi-chunk response.

        The response length is explicit so each connection remains reusable.
        """
        if self.path == "/stream":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", str(_STREAM_LENGTH))
            self.end_headers()
            for _ in range(_STREAM_CHUNK_COUNT):
                self.wfile.write(_STREAM_CHUNK)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(_SMALL_RESPONSE)))
        self.end_headers()
        self.wfile.write(_SMALL_RESPONSE)

    def log_request(
        self,
        code: int | str = "-",
        size: int | str = "-",
    ) -> None:
        """Suppress per-request server logs during benchmark sampling.

        Args:
            code: Response status code provided by the server implementation.
            size: Optional response size provided by the server implementation.
        """
        _ = code, size


@pytest.fixture(scope="module")
def loopback_server() -> Iterator[str]:
    """Start one HTTP/1.1 server for the benchmark module.

    Yields:
        The local server origin used by native and backend clients.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalHttpHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)


@pytest.fixture
def plain_asgi_client() -> Iterator[TestClient]:
    """Build a started native application with one JSON endpoint.

    Yields:
        A TestClient that exercises Foundation and native Routing dispatch.
    """
    application = Application()
    application.router.get("/health", _health)
    with TestClient(application.asgi) as client:
        yield client


@pytest.fixture
def injected_asgi_client() -> Iterator[TestClient]:
    """Build an application with an automatically injected route service.

    Yields:
        A TestClient that exercises native parameter and service injection.
    """
    application = Application()
    application.router.get("/documents/{document_id}", _show_document)
    with TestClient(application.asgi) as client:
        yield client


@pytest.fixture
def middleware_asgi_client() -> Iterator[TestClient]:
    """Build an application with one native pass-through middleware.

    Yields:
        A TestClient that exercises middleware and route dispatch together.
    """
    application = Application(http_middleware=(_PassThroughMiddleware,))
    application.router.get("/health", _health)
    with TestClient(application.asgi) as client:
        yield client


@pytest.fixture
def native_client() -> Iterator[HttpClient]:
    """Resolve the application-owned pooled client through its contract.

    Yields:
        The live client used by sync, async, and streaming measurements.
    """
    application = Application()
    with TestClient(application.asgi):
        yield application.container.make(HttpClient)


@pytest.fixture
def fanout_asgi_client(loopback_server: str) -> Iterator[TestClient]:
    """Build an application that fans out through its injected HTTP client.

    Args:
        loopback_server: Local HTTP/1.1 server shared by this module.

    Yields:
        A client whose route uses the native bounded request pool.
    """
    application = Application()

    async def fan_out(client: HttpClient) -> dict[str, int]:
        """Run a fixed batch of requests through the native request pool.

        Args:
            client: Application-owned asynchronous HTTP client.

        Returns:
            Number of successful operations in the fixed batch.
        """

        async def send() -> HttpClientResponse:
            """Send one request to the local benchmark endpoint.

            Pool workers reuse this callback for each bounded operation.
            """
            return await client.request_async(
                OutgoingRequest(
                    method="GET",
                    url=f"{loopback_server}/small",
                )
            )

        requests = tuple(HttpPoolRequest(send) for _ in range(_HTTP_BATCH_SIZE))
        results = await HttpRequestPool(_HTTP_CONCURRENCY).run(requests)
        completed = 0
        for result in results:
            if isinstance(result, Exception):
                raise result
            if result.status_code != HTTPStatus.OK:
                raise RuntimeError(_HTTP_BENCHMARK_FAILURE)
            await result.aclose()
            completed += 1
        return {"completed": completed}

    application.router.get("/fan-out", fan_out)
    with TestClient(application.asgi) as client:
        yield client


def _health() -> dict[str, str]:
    """Return the fixed JSON payload used by basic dispatch cases.

    Returns:
        One small JSON-compatible response value.
    """
    return {"status": "ok"}


def _show_document(
    document_id: int,
    catalog: _BenchmarkCatalog,
) -> dict[str, object]:
    """Return one route parameter and injected service result.

    Args:
        document_id: Integer extracted from the route path.
        catalog: Application-owned service injected by the Container.

    Returns:
        JSON-compatible data used to verify the benchmark endpoint.
    """
    return {
        "document_id": document_id,
        "label": catalog.label(document_id),
    }


def _peak_memory(operation: Callable[[], object]) -> int:
    """Measure peak traced memory while one operation runs.

    Args:
        operation: A bounded streaming or buffering operation.

    Returns:
        Peak Python-allocated bytes observed by tracemalloc.
    """
    tracemalloc.start()
    try:
        operation()
        _, peak_bytes = tracemalloc.get_traced_memory()
        return peak_bytes
    finally:
        tracemalloc.stop()


def _consume_stream(client: HttpClient, url: str) -> int:
    """Consume one native HTTP response without buffering its body.

    Args:
        client: Application-owned pooled HTTP service.
        url: Local streaming endpoint URL.

    Returns:
        Total bytes consumed incrementally.
    """
    byte_count = 0
    with client.stream(OutgoingRequest(method="GET", url=url)) as response:
        for chunk in response.iter_bytes():
            byte_count += len(chunk)
    return byte_count


def _consume_buffered(client: HttpClient, url: str) -> int:
    """Read one native HTTP response into a complete byte string.

    Args:
        client: Application-owned pooled HTTP service.
        url: Local response endpoint URL.

    Returns:
        Number of response bytes returned by the buffered API.
    """
    response = client.request(OutgoingRequest(method="GET", url=url))
    try:
        return len(response.body())
    finally:
        response.close()


@pytest.mark.benchmark
def test_route_dispatch(
    benchmark: BenchmarkFixture, plain_asgi_client: TestClient
) -> None:
    """Measure warm ASGI dispatch through a native JSON endpoint.

    Args:
        benchmark: Fixture that repeats the synchronous request operation.
        plain_asgi_client: Started application client prepared outside timing.
    """
    result = plain_asgi_client.get("/health")
    assert result.status_code == HTTPStatus.OK
    assert result.json() == {"status": "ok"}
    benchmark(plain_asgi_client.get, "/health")


@pytest.mark.benchmark
def test_dependency_injected_route_dispatch(
    benchmark: BenchmarkFixture,
    injected_asgi_client: TestClient,
) -> None:
    """Measure warm route dispatch with Container injection.

    Args:
        benchmark: Fixture that repeats the synchronous request operation.
        injected_asgi_client: Started application with a concrete service.
    """
    result = injected_asgi_client.get("/documents/42")
    assert result.status_code == HTTPStatus.OK
    assert result.json() == {
        "document_id": 42,
        "label": "document-42",
    }
    benchmark(injected_asgi_client.get, "/documents/42")


@pytest.mark.benchmark
def test_middleware_route_dispatch(
    benchmark: BenchmarkFixture,
    middleware_asgi_client: TestClient,
) -> None:
    """Measure warm ASGI dispatch through one native middleware.

    Args:
        benchmark: Fixture that repeats the synchronous request operation.
        middleware_asgi_client: Started app with pass-through middleware.
    """
    result = middleware_asgi_client.get("/health")
    assert result.status_code == HTTPStatus.OK
    benchmark(middleware_asgi_client.get, "/health")


@pytest.mark.benchmark
def test_application_route_compilation_startup(
    benchmark: BenchmarkFixture,
    tmp_path: Path,
) -> None:
    """Measure cold application startup and route compilation.

    Args:
        benchmark: Fixture that repeats a complete cold lifecycle.
        tmp_path: Isolated application root prepared outside timing.
    """
    runner = asyncio.Runner()

    async def start_and_stop() -> None:
        """Create, compile, and close one application instance.

        The measured operation includes native composition and provider boot.
        """
        application = Application(base_path=tmp_path)
        for route_index in range(_APPLICATION_ROUTE_COUNT):
            application.router.get(
                f"/items/{route_index}",
                _health,
            )
        await application.startup()
        await application.shutdown()

    def run_lifecycle() -> None:
        """Run one lifecycle on a persistent event loop.

        Persistent loop setup stays outside each benchmark sample.
        """
        runner.run(start_and_stop())

    try:
        benchmark(run_lifecycle)
    finally:
        runner.close()


@pytest.mark.benchmark
def test_httpx2_pooled_request(
    benchmark: BenchmarkFixture,
    loopback_server: str,
) -> None:
    """Measure one warm request through the native HTTPX2 client baseline.

    Args:
        benchmark: Fixture that repeats the pooled request operation.
        loopback_server: Local HTTP/1.1 server shared by this module.
    """
    limits = httpx2.Limits(
        max_connections=_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=_HTTP_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=_HTTP_KEEPALIVE_EXPIRY_SECONDS,
    )
    timeout = httpx2.Timeout(
        _HTTP_TIMEOUT_SECONDS,
        connect=_HTTP_TIMEOUT_SECONDS,
    )
    with httpx2.Client(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        verify=True,
        http2=False,
    ) as client:
        response = client.get(f"{loopback_server}/small")
        assert response.status_code == HTTPStatus.OK
        response.close()

        def request() -> None:
            """Send and close one request through the warm backend pool.

            Closing the response allows HTTPX2 to reuse the connection.
            """
            response = client.get(f"{loopback_server}/small")
            response.close()

        benchmark(request)


@pytest.mark.benchmark
def test_titanspan_pooled_request(
    benchmark: BenchmarkFixture,
    loopback_server: str,
    native_client: HttpClient,
) -> None:
    """Measure a warm request through the native HttpClient contract.

    Args:
        benchmark: Fixture that repeats the pooled request operation.
        loopback_server: Local HTTP/1.1 server shared by this module.
        native_client: Application-owned pooled client resolved by contract.
    """
    pending = PendingRequest(native_client)
    response = pending.get(f"{loopback_server}/small")
    assert response.status_code == HTTPStatus.OK
    response.close()

    def request() -> None:
        """Send and close one request through the native request builder.

        Closing the response allows the application pool to reuse it.
        """
        response = pending.get(f"{loopback_server}/small")
        response.close()

    benchmark(request)


@pytest.mark.benchmark
def test_bounded_http_pool_batch(
    benchmark: BenchmarkFixture,
    fanout_asgi_client: TestClient,
) -> None:
    """Measure a bounded fan-out of pooled requests through one ASGI route.

    Args:
        benchmark: Fixture that measures one fixed-size request batch.
        fanout_asgi_client: Started application with HTTP fan-out routing.
    """
    result = fanout_asgi_client.get("/fan-out")
    assert result.json() == {"completed": _HTTP_BATCH_SIZE}
    benchmark(fanout_asgi_client.get, "/fan-out")


@pytest.mark.benchmark
def test_native_http_stream_peak_memory(
    benchmark: BenchmarkFixture,
    loopback_server: str,
    native_client: HttpClient,
) -> None:
    """Report peak memory while consuming a pooled response incrementally.

    Args:
        benchmark: Fixture that records fixed memory measurement samples.
        loopback_server: Local server streaming a two-megabyte response.
        native_client: Application-owned pooled HTTP client.
    """
    url = f"{loopback_server}/stream"
    assert _consume_stream(native_client, url) == _STREAM_LENGTH
    memory_benchmark = cast("_MemoryBenchmarkFixture", benchmark)
    peak_bytes = cast(
        "int",
        memory_benchmark.pedantic(
            _peak_memory,
            args=((lambda: _consume_stream(native_client, url)),),
            rounds=3,
            iterations=1,
        ),
    )
    memory_benchmark.extra_info.update(
        {
            "body_bytes": _STREAM_LENGTH,
            "stream_chunk_bytes": _STREAM_CHUNK_SIZE,
            "peak_bytes": peak_bytes,
        }
    )
    assert peak_bytes > 0


@pytest.mark.benchmark
def test_native_http_buffered_peak_memory(
    benchmark: BenchmarkFixture,
    loopback_server: str,
    native_client: HttpClient,
) -> None:
    """Report peak memory while buffering the same local response.

    Args:
        benchmark: Fixture that records fixed memory measurement samples.
        loopback_server: Local server returning a two-megabyte response.
        native_client: Application-owned pooled HTTP client.
    """
    url = f"{loopback_server}/stream"
    assert _consume_buffered(native_client, url) == _STREAM_LENGTH
    memory_benchmark = cast("_MemoryBenchmarkFixture", benchmark)
    peak_bytes = cast(
        "int",
        memory_benchmark.pedantic(
            _peak_memory,
            args=((lambda: _consume_buffered(native_client, url)),),
            rounds=3,
            iterations=1,
        ),
    )
    memory_benchmark.extra_info.update(
        {
            "body_bytes": _STREAM_LENGTH,
            "peak_bytes": peak_bytes,
        }
    )
    assert peak_bytes > 0


__all__ = []
