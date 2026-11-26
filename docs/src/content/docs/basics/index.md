---
title: "Basics"
---

<span id="basics"></span>

The supported foundation currently includes:

- `Application` from `titanspan`, exposing a FastAPI app at `.asgi`.
- `Settings` from `titanspan.config`, using the `TITANSPAN_` environment
  prefix.
- The `titanspan` CLI with `--help` and `--version`.
- Dishka provider resolution and app-scoped resource cleanup during ASGI
  lifespan shutdown.
- The initial `titanspan.support` array utilities and reusable conditional
  and macro registration primitives.

Use Titanspan Routing for application-owned route definitions and dispatch.
FastAPI remains available for explicit interoperability. Service providers,
facades, and the configuration repository are also implemented.
