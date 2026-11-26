---
title: "ADR 0004: FastAPI Web Foundation"
---

<span id="adr-0004-fastapi-web-foundation"></span>

- Status: Accepted
- Date: 2026-11-24

## Context

The framework needs an ASGI-native web foundation, typed endpoint integration,
middleware support, and a clear application lifespan hook.

## Decision

Use FastAPI and Starlette as the HTTP and ASGI foundation. Titanspan owns
application conventions and integration lifecycle, while applications retain
direct access to FastAPI routers, requests, responses, and middleware.

## Alternatives considered

- A custom ASGI server or router: rejected because it duplicates mature
  infrastructure.
- Another web framework: not selected because FastAPI matches the intended
  async and typing model and integrates with Dishka.

## Consequences

FastAPI is a mandatory dependency. Titanspan should avoid wrapping every
FastAPI concept and preserve direct interoperability.

The current test environment uses HTTPX2 only as Starlette's test transport.
It is not a framework HTTP client API; that future choice will be revisited
when the HTTP module is implemented.

## Risks

FastAPI and Starlette evolve. Validate minimum supported versions and lifespan
behavior in CI before widening compatibility claims.

## References

- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Starlette](https://www.starlette.io/)
- [Starlette TestClient](https://www.starlette.io/testclient/)
