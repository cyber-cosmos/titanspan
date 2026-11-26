---
title: "ADR 0022: Native application bootstrap and lifecycle hooks"
---

<span id="adr-0022-native-foundation-bootstrap"></span>

- Status: Accepted
- Date: 2026-11-26

## Context

Foundation already owns one application Container and an ASGI lifecycle.
Application setup still required a long constructor call. Applications also
lacked a standard path API, environment inspection, and native exception
rendering hooks.

## Decision

- Keep `Application` as the only composition root.
- Add a typed builder that collects constructor options and creates that
  `Application`.
- Discover optional providers only through an explicitly selected Python
  entry-point group. Treat those packages as trusted executable code.
- Add path and environment accessors backed by the selected configuration
  repository and `ConfigManager` root.
- Pass the effective application root to route discovery. An explicit
  `routing.path` setting remains the route discovery override.
- Add zero-argument startup and shutdown callbacks. Keep dependency-injected
  initialization in service-provider boot hooks.
- Add exception handlers through native HTTP contracts. Keep FastAPI and
  Starlette request and response types inside the Foundation adapter.
- Render native `ValidationException` values as safe HTTP 422 responses
  through the canonical response factory.
- Route standalone operations through the same startup and shutdown methods
  used by ASGI hosting.

## Consequences

The builder does not create a registry, scan modules, merge configuration
implicitly, or load arbitrary filesystem paths. Provider entry points run
installed Python code and require trusted distributions. Shutdown callbacks
use captured references because the Container rejects resolution after
shutdown begins.

Unhandled request exceptions are reported through the application logger and
rendered with a generic response body. Applications can register a typed
native renderer before startup.

## Verification

Unit tests cover builder paths, environment values, entry-point loading, and
invalid providers. Integration tests cover standalone lifecycle callbacks,
startup rollback, handler injection, safe error rendering, and application
context restoration.
