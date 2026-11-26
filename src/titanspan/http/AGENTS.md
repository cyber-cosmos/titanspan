# HTTP component instructions

Follow the repository root instructions and `ARCHITECTURE.md`.

- Keep public APIs native, typed, and snake_case. Keep Starlette, FastAPI,
  and HTTPX2 implementation objects in private adapters unless an explicit
  interoperability boundary is documented.
- Use the canonical contracts in `titanspan.contracts.http` and the active
  application container. Do not add a separate request, configuration, or
  client registry.
- Request metadata is synchronous; body parsing, streaming, and async
  network operations are explicitly asynchronous. Never start an event loop
  or block an active loop inside a synchronous method.
- Preserve request scopes until the complete ASGI response, including a
  streaming body, has finished or been cancelled. Test upload cleanup,
  cancellation, and partial initialization.
- Keep connection counts, request body size, multipart fields, retries, and
  streamed data bounded. Do not treat URL string validation as SSRF
  protection.
- Add focused unit tests and real ASGI or loopback integration tests for
  behavior at each implemented boundary. Do not mock HTTPX2 when verifying
  transport integration.
- Update the HTTP specification and Starlight sidebar when documentation
  changes. Do not advertise features marked pending in
  `docs/src/content/docs/specifications/http.md`.
