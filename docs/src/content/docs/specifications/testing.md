---
title: "Testing behavioral specification"
---

# Testing behavioral specification

This specification records application testing helpers in
`titanspan.testing`. Pytest remains the runner. The helpers use the production
Application, Container, providers, HTTP middleware, and ASGI application.

## Capability inventory

| Capability | Status | Evidence |
| --- | --- | --- |
| Synchronous application test lifecycle | Implemented | `ApplicationTest` starts and shuts down through the real ASGI lifespan |
| Asynchronous application test lifecycle | Implemented | `AsyncApplicationTest` uses Foundation startup and shutdown with HTTPX2 ASGI transport; the installed-wheel smoke verifies injected request handling |
| Temporary or explicit application root | Implemented | Roots are created per test; temporary roots are removed on context exit |
| Configuration and typed settings | Implemented | Values pass to the production Application constructor |
| Provider and middleware registration | Implemented | The ordinary Foundation composition path receives them |
| Per-application service replacement | Implemented | Replacement instances register through a provider before Container composition |
| Request, response, cookie, and file assertions | Delegated | Returned clients use Starlette and HTTPX2 response APIs |
| Storage, Event, HTTP, and Logging fakes | Delegated | Each component owns its fake and isolation policy |
| Console testing | Implemented | `ConsoleTester` invokes the native parser and lifecycle |
| Cross-test process environment mutation | Unsupported | Helpers do not modify `os.environ` |

## Public API

| API | Behavior |
| --- | --- |
| `ApplicationTest(...)` | Construct one application and synchronous ASGI test context |
| `AsyncApplicationTest(...)` | Construct one application and asynchronous ASGI test context |
| `application` | Access the real Foundation Application before or during the test |
| `client` | Access the client only while the test context is active |
| `base_path` | Return the resolved application root |
| `replacements` | Bind test instances through the same application Container |

When no root is supplied, each helper owns a temporary directory. It also
creates the conventional `routes` directory. An explicit root remains after
context exit. The helper never changes the process working directory.

## Lifecycle and ownership

The synchronous helper lets Starlette's in-process ASGI client run the
application lifespan. The asynchronous helper calls Foundation startup and
shutdown directly, then uses HTTPX2's ASGI transport. Both close the client
before they finalize the Application and remove any temporary root.

Test replacements enter the ordinary service provider sequence. They are
application-owned values, so Container cleanup follows its normal ownership
policy. The helper does not hold a Container override across application
shutdown. Container rejects shutdown while an override is active.

Settings and dotenv input use the selected application root. The helper does
not rewrite process environment variables. Tests that alter process-wide
environment state must serialize those changes through their test runner.

## Limitations

The returned clients expose Starlette and HTTPX2 testing APIs. This boundary
avoids a duplicate request builder and response assertion system. Test
replacements are values, not async factories. Register complex test resources
through a provider when they need custom initialization or cleanup. Component
fakes remain managed by their owning components.

## Verification

- Real lifecycle and service replacement: `tests/integration/testing/`.
- Console lifecycle: `tests/integration/console/`.
- Component fakes: the owning component test suites.
