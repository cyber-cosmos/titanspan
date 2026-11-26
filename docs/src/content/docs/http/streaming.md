---
title: "Streaming"
---

<span id="streaming"></span>

## Incoming request bodies

`await request.body()` buffers within `http.server.max_body_size`. For large
uploads or data processing, use the asynchronous `request.stream()` iterator
to preserve backpressure and avoid collecting the complete body. The stream
is single-consumption. A prior buffered body is replayed as a single chunk;
form parsing owns and caches its parsed form.

Multipart parsing has independent `max_form_files`, `max_form_fields`, and
`max_part_size` limits. The complete request is scoped through ASGI response
transmission, so uploaded files and request-local dependencies remain usable
inside a streaming response generator. Client disconnects and cancellation
propagate through the ASGI call, and the request scope closes in a shielded
cleanup block.

## Streaming responses and events

Pass an `AsyncIterable[bytes | str]` to `response().stream` or an async event
source to `response().event_stream`. Chunks are encoded as they are yielded;
Titanspan does not collect the full response. `StreamResponse` closes an
async-generator source when transmission completes or is cancelled.

`ServerSentEvent` supports event name, data, identifier, and retry delay.
JSON-compatible values are encoded as one data field. The event response sets
`text/event-stream`, disables proxy buffering, and adds `Cache-Control:
no-cache`.

Once response headers have been sent, a later generator exception cannot be
replaced with a different HTTP status. Handle domain errors before returning
the streaming response or encode an application-level error event.

## Outgoing response streams

Use the explicit context manager so connection ownership is visible:

```python
async with Http.stream_async("GET", url) as result:
    async for chunk in result.iter_bytes_async():
        await sink.write(chunk)
```

The response context closes the connection on normal completion, early exit,
failure, and cancellation. Buffered accessors on a streamed response raise a
native `HttpClientError` if content has not been buffered.
