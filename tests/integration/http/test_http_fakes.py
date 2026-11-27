"""Verify HTTP fakes use real HTTPX2 transports and application clients.

The tests exercise the facade and injected client within local app scopes.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from titanspan.contracts.http import (
    HttpClient,
    HttpClientResponse,
    OutgoingRequest,
)
from titanspan.facades import Http
from titanspan.foundation import Application
from titanspan.http import (
    HttpFakeError,
    HttpPoolRequest,
    HttpRequestPool,
    UnexpectedHttpRequestError,
)
from titanspan.http._backends.client import HttpxClientAdapter
from titanspan.http.client.pending_request import PendingRequest
from titanspan.http.configuration import ClientConfiguration

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping
    from typing import Self

    from titanspan.contracts.http import JsonValue, ServerSentEvent

_EXPECTED_REQUESTS = 2
_POOL_LIMIT = 2
_POOL_START_TIMEOUT = 2
_LOCAL_REQUEST_FAILURE = "local request failure"
_POOL_CLOSE_FAILURE = "pool close failure"


class _ClosingResponse(HttpClientResponse):
    """Track the pool's cleanup call without creating transport resources.

    Other response operations remain uncalled by the pool cleanup path.
    """

    def __init__(self, *, fail_close: bool = False) -> None:
        """Start the test response in an open state.

        The pool test observes the asynchronous close transition.
        """
        self.closed = False
        self.fail_close = fail_close

    @property
    def status_code(self) -> int:
        """Return a successful status for the cleanup-only response.

        The pool does not inspect status during resource finalization.
        """
        return HTTPStatus.OK

    @property
    def headers(self) -> Mapping[str, str]:
        """Return empty response headers.

        No transport metadata is needed for cleanup verification.
        """
        return {}

    @property
    def cookies(self) -> Mapping[str, str]:
        """Return empty response cookies.

        The test response does not represent a server exchange.
        """
        return {}

    def body(self) -> bytes:
        """Return an empty body for contract completeness.

        The pool only calls the asynchronous cleanup method.
        """
        return b""

    def text(self) -> str:
        """Return empty text for contract completeness.

        The pool only calls the asynchronous cleanup method.
        """
        return ""

    def json(self) -> JsonValue:
        """Return JSON null for contract completeness.

        The pool only calls the asynchronous cleanup method.
        """
        return None

    def successful(self) -> bool:
        """Report success for the fixed status code.

        No status predicate participates in cleanup verification.
        """
        return True

    def failed(self) -> bool:
        """Report that the fixed status code is not an error.

        No status predicate participates in cleanup verification.
        """
        return False

    def server_error(self) -> bool:
        """Report that the fixed status code is not a server error.

        No status predicate participates in cleanup verification.
        """
        return False

    def throw(self) -> Self:
        """Return this successful test response.

        The method is unused by the pool cleanup path.
        """
        return self

    def header(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        """Return the fallback value for any header name.

        This response does not carry headers.
        """
        _ = name
        return default

    def iter_bytes(self) -> Iterator[bytes]:
        """Return an empty synchronous byte iterator.

        The pool does not consume response bodies.
        """
        return iter(())

    def iter_bytes_async(self) -> AsyncIterator[bytes]:
        """Return an empty asynchronous byte iterator.

        The pool does not consume response bodies.
        """

        async def chunks() -> AsyncIterator[bytes]:
            """Yield each response chunk through the async interface.

            The helper preserves the contract's async iterator shape.
            """
            for chunk in self.iter_bytes():
                yield chunk

        return chunks()

    def iter_sse(self) -> Iterator[ServerSentEvent]:
        """Return an empty synchronous SSE iterator.

        The pool does not consume response event streams.
        """
        return iter(())

    def iter_sse_async(self) -> AsyncIterator[ServerSentEvent]:
        """Return an empty asynchronous SSE iterator.

        The pool does not consume response event streams.
        """

        async def events() -> AsyncIterator[ServerSentEvent]:
            """Yield each response event through the async interface.

            The helper preserves the contract's async iterator shape.
            """
            for event in self.iter_sse():
                yield event

        return events()

    def close(self) -> None:
        """Record synchronous cleanup for contract completeness.

        The pool uses asynchronous cleanup for this test response.
        """
        self.closed = True

    async def aclose(self) -> None:
        """Record asynchronous response cleanup.

        The test response has no underlying network resource.
        """
        self.closed = True
        if self.fail_close:
            raise RuntimeError(_POOL_CLOSE_FAILURE)

    closed: bool
    fail_close: bool


def test_sync_fake_uses_httpx2_mock_transport() -> None:
    """Intercept blocking calls and release the application transport.

    The synchronous path uses the same native fake matching rules.
    """
    client = HttpxClientAdapter(ClientConfiguration())
    try:
        with Http.fake(
            {
                "https://example.test/sync": Http.fake_response(
                    {"mode": "sync"},
                ),
            }
        ):
            response = PendingRequest(client).get(
                "https://example.test/sync",
            )
            assert response.json() == {"mode": "sync"}
            Http.assert_sent_count(1)
            response.close()
        with Http.fake(
            {
                "https://example.test/sync-stream": Http.fake_response(
                    b"streamed",
                ),
            }
        ) as fake:
            with PendingRequest(client).stream(
                "GET",
                "https://example.test/sync-stream",
            ) as response:
                assert list(response.iter_bytes()) == [b"streamed"]
            fake.assert_sent_count(1)
    finally:
        anyio.run(client.aclose)


@pytest.mark.anyio
async def test_fake_covers_facade_injected_client_and_request_assertions() -> (
    None
):
    """Intercept both service access paths using the same fake session.

    Each response comes from HTTPX2 MockTransport and cannot reach the network.
    """
    application = Application(config={"app": {"name": "HTTP fake"}})
    async with application:
        client = application.make(HttpClient)
        with Http.fake(
            {
                "https://example.test/*": Http.fake_response(
                    {"status": "ok"},
                ),
            }
        ) as fake:
            facade_response = await Http.with_header(
                "X-Source", "facade"
            ).get_async(
                "https://example.test/facade",
            )
            injected_response = await client.request_async(
                OutgoingRequest(
                    method="POST",
                    url="https://example.test/injected",
                    data=b"payload",
                )
            )

            assert facade_response.json() == {"status": "ok"}
            assert injected_response.json() == {"status": "ok"}
            Http.assert_sent_count(2)
            Http.assert_sent(
                Http.request_pattern(
                    method="GET",
                    url="https://example.test/facade",
                    headers={"x-source": "facade"},
                )
            )
            Http.assert_not_sent("https://other.test/*")
            assert Http.sent_requests() == fake.requests
            assert len(fake.requests) == _EXPECTED_REQUESTS
            assert fake.requests[1].body == b"payload"
            await facade_response.aclose()
            await injected_response.aclose()

    with pytest.raises(HttpFakeError, match="active fake context"):
        Http.assert_sent()


@pytest.mark.anyio
async def test_fake_sequences_restore_nested_and_isolate_task_contexts() -> (
    None
):
    """Restore nested fakes and isolate sibling request contexts.

    Each sibling task installs its own fake before sending a request.
    """
    application = Application(config={"app": {"name": "HTTP isolation"}})
    async with application:
        client = application.make(HttpClient)
        first = Http.fake_response({"sequence": 1})
        second = Http.fake_response({"sequence": 2}, status=201)
        with Http.fake(
            {"https://example.test/sequence": [first, second]}
        ) as outer:
            first_result = await Http.get_async(
                "https://example.test/sequence",
            )
            with Http.fake(
                {
                    "https://example.test/nested": Http.fake_response(
                        {"scope": "nested"},
                    ),
                }
            ) as nested:
                nested_result = await Http.get_async(
                    "https://example.test/nested",
                )
                nested.assert_sent_count(1)
            second_result = await Http.get_async(
                "https://example.test/sequence",
            )
            assert first_result.status_code == HTTPStatus.OK
            assert second_result.status_code == HTTPStatus.CREATED
            assert nested_result.json() == {"scope": "nested"}
            outer.assert_sent_count(2)

        async def isolated_request(path: str) -> None:
            """Resolve one fake inside a child task context.

            Args:
                path: Unique path that selects this task's fake response.
            """
            with Http.fake(
                {
                    f"https://example.test/{path}": Http.fake_response(
                        {"path": path},
                    ),
                }
            ) as fake:
                response = await client.request_async(
                    OutgoingRequest(
                        method="GET",
                        url=f"https://example.test/{path}",
                    )
                )
                assert response.json() == {"path": path}
                fake.assert_sent_count(1)
                await response.aclose()

        async with anyio.create_task_group() as group:
            group.start_soon(isolated_request, "one")
            group.start_soon(isolated_request, "two")

        for response in (first_result, second_result, nested_result):
            await response.aclose()


@pytest.mark.anyio
async def test_fake_blocks_unmatched_requests_without_network_fallback() -> (
    None
):
    """Raise a native error when no configured URL pattern matches.

    The fake transport must never fall through to a real network client.
    """
    application = Application(config={"app": {"name": "HTTP deny"}})
    async with application:
        with Http.fake(
            {
                "https://allowed.test/*": Http.fake_response({"ok": True}),
            }
        ):
            with pytest.raises(UnexpectedHttpRequestError):
                await Http.get_async("https://unmatched.test/path")


@pytest.mark.anyio
async def test_application_fake_does_not_intercept_another_application() -> (
    None
):
    """Reject cross-application fake use while restoring the outer owner.
    """  # fmt: skip
    first = Application(config={"app": {"name": "http-fake-first"}})
    second = Application(config={"app": {"name": "http-fake-second"}})
    async with first:
        first_client = first.make(HttpClient)
        with Http.fake(
            {
                "https://example.test/*": Http.fake_response(
                    {"owner": "first"},
                ),
            }
        ) as fake:
            first_response = await first_client.request_async(
                OutgoingRequest(
                    method="GET",
                    url="https://example.test/first",
                )
            )
            assert first_response.json() == {"owner": "first"}

            async with second:
                second_client = second.make(HttpClient)
                with pytest.raises(
                    HttpFakeError,
                    match="another application",
                ):
                    await second_client.request_async(
                        OutgoingRequest(
                            method="GET",
                            url="https://example.test/second",
                        )
                    )

            assert len(fake.requests) == 1
            restored_response = await first_client.request_async(
                OutgoingRequest(
                    method="GET",
                    url="https://example.test/restored",
                )
            )
            assert restored_response.json() == {"owner": "first"}
            fake.assert_sent_count(2)
            await first_response.aclose()
            await restored_response.aclose()


@pytest.mark.anyio
async def test_fake_sequence_exhaustion_is_a_recorded_mismatch() -> None:
    """Fail closed when a configured response sequence runs out.

    Exhausted calls remain visible to the active request assertions.
    """
    application = Application(config={"app": {"name": "HTTP sequence"}})
    async with application:
        with Http.fake(
            {
                "https://example.test/once": [
                    Http.fake_response({"ok": True}),
                ],
            }
        ) as fake:
            response = await Http.get_async(
                "https://example.test/once",
            )
            await response.aclose()
            with pytest.raises(UnexpectedHttpRequestError):
                await Http.get_async("https://example.test/once")
            fake.assert_sent_count(2)


@pytest.mark.anyio
async def test_fake_stream_can_be_consumed_as_server_sent_events() -> None:
    """Stream and parse SSE through HTTPX2 without buffering the response.

    The response context retains and releases the streaming connection.
    """
    application = Application(config={"app": {"name": "HTTP SSE client"}})
    async with application:
        with Http.fake(
            {
                "https://example.test/events": Http.fake_response(
                    b"data: first\ndata: second\n\n: keepalive\n\n"
                    b"event: ready\nid: event-1\ndata: done\n\n",
                    headers={"Content-Type": "text/event-stream"},
                ),
            }
        ):
            async with Http.stream_async(
                "GET",
                "https://example.test/events",
            ) as response:
                events = [event async for event in response.iter_sse_async()]

        assert [event.data for event in events] == [
            "first\nsecond",
            "done",
        ]
        assert events[1].event == "ready"
        assert events[1].identifier == "event-1"


@pytest.mark.anyio
async def test_async_fake_context_encodes_text_and_empty_responses() -> None:
    """Encode text and bodyless fake responses with ordinary HTTPX2 access.

    Async context management restores the active fake on exit.
    """
    application = Application(config={"app": {"name": "HTTP fake bodies"}})
    async with (
        application,
        Http.fake(
            {
                "https://example.test/text": Http.fake_response("plain text"),
                "https://example.test/empty": Http.fake_response(None),
            }
        ) as fake,
    ):
        text_response = await Http.get_async(
            "https://example.test/text",
        )
        empty_response = await Http.get_async(
            "https://example.test/empty",
        )
        assert text_response.text() == "plain text"
        assert text_response.header("content-type") == (
            "text/plain; charset=utf-8"
        )
        assert empty_response.body() == b""
        fake.assert_sent_count(2)
        await text_response.aclose()
        await empty_response.aclose()


@pytest.mark.anyio
async def test_request_pool_bounds_work_and_preserves_named_results() -> None:
    """Run named callbacks with a fixed number of active HTTP operations.

    Results retain their mapping keys after worker completion.
    """
    application = Application(config={"app": {"name": "HTTP pool"}})
    async with application:
        active = 0
        peak = 0
        started = anyio.Event()
        release = anyio.Event()

        async def request(path: str) -> HttpClientResponse:
            """Hold one request until the pool reaches its concurrency cap.

            Args:
                path: Unique fake endpoint selected by this operation.
            """
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == _POOL_LIMIT:
                started.set()
            await release.wait()
            try:
                return await Http.get_async(f"https://example.test/{path}")
            finally:
                active -= 1

        with Http.fake(
            {
                "https://example.test/*": Http.fake_response(
                    {"status": "ok"},
                ),
            }
        ):
            pool = Http.pool(max_concurrency=_POOL_LIMIT)
            assert isinstance(pool, HttpRequestPool)
            outputs: list[Mapping[str, HttpClientResponse | Exception]] = []

            async def run_pool() -> None:
                """Collect keyed responses after each callback completes.

                Pool output is assigned after all worker tasks finish.
                """
                outputs.append(
                    await pool.run(
                        {
                            path: HttpPoolRequest(
                                lambda path=path: request(path),
                            )
                            for path in ("one", "two", "three", "four")
                        },
                        fail_fast=False,
                    )
                )

            async with anyio.create_task_group() as group:
                group.start_soon(run_pool)
                with anyio.fail_after(_POOL_START_TIMEOUT):
                    await started.wait()
                assert active == _POOL_LIMIT
                release.set()

            assert peak == _POOL_LIMIT
            assert len(outputs) == 1
            results = outputs[0]
            assert tuple(results) == ("one", "two", "three", "four")
            for value in results.values():
                assert not isinstance(value, Exception)
                assert value.json() == {"status": "ok"}
                await value.aclose()


@pytest.mark.anyio
async def test_request_pool_collects_errors_and_fail_fast_raises() -> None:
    """Support explicit partial-result and fail-fast policies.

    Callers choose whether a failed callback cancels its siblings.
    """
    application = Application(config={"app": {"name": "HTTP pool errors"}})
    async with application:

        async def fail() -> HttpClientResponse:
            """Raise one deterministic request failure.

            The exception drives both pool failure policies.
            """
            raise ValueError(_LOCAL_REQUEST_FAILURE)

        with Http.fake(
            {
                "https://example.test/success": Http.fake_response(
                    {"ok": True},
                ),
            }
        ):
            requests = {
                "failed": HttpPoolRequest(fail),
                "success": HttpPoolRequest(
                    lambda: Http.get_async("https://example.test/success"),
                ),
            }
            results = await HttpRequestPool(2).run(
                requests,
                fail_fast=False,
            )
            assert isinstance(results, dict)
            assert isinstance(results["failed"], ValueError)
            success = results["success"]
            assert not isinstance(success, Exception)
            assert success.json() == {"ok": True}
            await success.aclose()

            with pytest.raises(ValueError, match=_LOCAL_REQUEST_FAILURE):
                await HttpRequestPool(2).run(
                    [HttpPoolRequest(fail)],
                )


@pytest.mark.anyio
async def test_request_pool_closes_completed_responses_on_fail_fast() -> None:
    """Close completed responses after a sibling operation fails.

    Fail-fast cancellation must not transfer partial results to the caller.
    """
    completed = anyio.Event()
    response = _ClosingResponse()

    async def success() -> HttpClientResponse:
        """Complete before the sibling request fails.

        Returns:
            A response whose close call is observable by this test.
        """
        completed.set()
        return response

    async def fail() -> HttpClientResponse:
        """Wait for a completed response and then raise one failure.

        The ordering ensures cleanup runs on a partially completed pool.
        """
        await completed.wait()
        raise ValueError(_LOCAL_REQUEST_FAILURE)

    with pytest.raises(ValueError, match=_LOCAL_REQUEST_FAILURE):
        await HttpRequestPool(_POOL_LIMIT).run(
            {
                "success": HttpPoolRequest(success),
                "failure": HttpPoolRequest(fail),
            },
        )

    assert response.closed


@pytest.mark.anyio
async def test_fail_fast_pool_stops_callbacks_without_checkpoints() -> None:
    """Do not start new callbacks after a fail-fast worker reports failure.

    Async callbacks that do not suspend cannot observe task cancellation.
    """
    accepted: list[int] = []

    async def fail() -> HttpClientResponse:
        """Raise before yielding control to another worker.

        The immediate exception exposes cancellation checkpoint gaps.
        """
        raise ValueError(_LOCAL_REQUEST_FAILURE)

    async def callback(index: int) -> HttpClientResponse:
        """Record whether the pool started this callback.

        No await occurs, so cancellation alone cannot stop this function.
        """
        accepted.append(index)
        return _ClosingResponse()

    with pytest.raises(ValueError, match=_LOCAL_REQUEST_FAILURE):
        await HttpRequestPool(1).run(
            [
                HttpPoolRequest(fail),
                HttpPoolRequest(lambda: callback(1)),
                HttpPoolRequest(lambda: callback(2)),
            ],
        )

    assert accepted == []


@pytest.mark.anyio
async def test_request_pool_applies_timeouts_and_propagates_cancellation() -> (
    None
):
    """Bound individual callbacks and preserve external cancellation.

    AnyIO owns timeout and cancellation propagation for each worker task.
    """
    pool = HttpRequestPool(1)

    async def never_finishes() -> HttpClientResponse:
        """Wait until the request-level deadline cancels this task.

        The pool must convert the timeout into a collected result.
        """
        await anyio.sleep_forever()
        return _ClosingResponse()

    results = await pool.run(
        {"timed": HttpPoolRequest(never_finishes, timeout=0.01)},
        fail_fast=False,
    )
    assert isinstance(results["timed"], TimeoutError)

    started = anyio.Event()
    cancelled = anyio.Event()

    async def cancel_me() -> HttpClientResponse:
        """Wait until external cancellation reaches this worker.

        The finalizer records that cancellation was propagated.
        """
        started.set()
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.set()
        return _ClosingResponse()

    async def run_pool() -> None:
        """Keep the pool active within its owning task group.

        The parent test cancels the group after the worker starts.
        """
        await pool.run([HttpPoolRequest(cancel_me)])

    async with anyio.create_task_group() as group:
        group.start_soon(run_pool)
        await started.wait()
        group.cancel_scope.cancel()

    assert cancelled.is_set()


@pytest.mark.anyio
async def test_request_pool_validates_bounds_and_cleanup_errors() -> None:
    """Validate pool bounds and report cleanup failures after cancellation.

    The original request failure remains the primary pool exception.
    """

    async def unused_request() -> HttpClientResponse:
        """Return a cleanup response for invalid-input construction checks.

        The callback is never invoked by this test.
        """
        return _ClosingResponse()

    with pytest.raises(ValueError, match="positive integer"):
        HttpRequestPool(0)
    with pytest.raises(ValueError, match="finite and positive"):
        HttpPoolRequest(unused_request, timeout=0)
    with pytest.raises(ValueError, match="finite and positive"):
        HttpPoolRequest(unused_request, timeout=float("inf"))
    with pytest.raises(ValueError, match="positive integer"):
        HttpRequestPool(cast("int", 1.5))

    response = _ClosingResponse(fail_close=True)
    completed = anyio.Event()

    async def fail_after_success() -> HttpClientResponse:
        """Raise after a sibling has returned a cleanup-owned response.

        The pool should close the successful response before raising.
        """
        await completed.wait()
        raise ValueError(_LOCAL_REQUEST_FAILURE)

    async def succeed() -> HttpClientResponse:
        """Return one response and release the failing sibling.

        The event orders completion before the fail-fast error.
        """
        completed.set()
        return response

    with pytest.raises(ValueError, match=_LOCAL_REQUEST_FAILURE) as failure:
        await HttpRequestPool(_POOL_LIMIT).run(
            [HttpPoolRequest(fail_after_success), HttpPoolRequest(succeed)]
        )
    assert response.closed
    assert any(
        "failed to close" in note
        for note in getattr(failure.value, "__notes__", ())
    )

    cancelled_response = _ClosingResponse(fail_close=True)
    cancel_scope: anyio.CancelScope

    async def cancel_after_response() -> HttpClientResponse:
        """Cancel the outer operation after producing a response.

        The pool must shield cleanup while preserving cancellation.
        """
        cancel_scope.cancel()
        return cancelled_response

    async def wait_until_cancelled() -> HttpClientResponse:
        """Remain active until the parent pool scope is cancelled.

        The callback has no response to transfer before cancellation.
        """
        await anyio.sleep_forever()
        return _ClosingResponse()

    cancelled_error: BaseException | None = None
    with anyio.CancelScope() as cancel_scope:
        with pytest.raises(anyio.get_cancelled_exc_class()) as cancelled:
            await HttpRequestPool(_POOL_LIMIT).run(
                [
                    HttpPoolRequest(cancel_after_response),
                    HttpPoolRequest(wait_until_cancelled),
                ]
            )
        cancelled_error = cancelled.value
    assert cancel_scope.cancel_called
    assert cancelled_error is not None
    assert any(
        "failed to close" in note
        for note in getattr(cancelled_error, "__notes__", ())
    )
    assert cancelled_response.closed
