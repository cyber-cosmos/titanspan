# Basics

The supported foundation currently includes:

- `Application` from `titanspan`, exposing a FastAPI app at `.asgi`.
- `Settings` from `titanspan.config`, using the `TITANSPAN_` environment
  prefix.
- The `titanspan` CLI with `--help` and `--version`.
- Dishka provider resolution and app-scoped resource cleanup during ASGI
  lifespan shutdown.
- The initial `titanspan.support` array utilities and reusable conditional
  and macro registration primitives.

Use native FastAPI APIs for routes and middleware. Service-provider discovery,
facades, fluent routing, and configuration repositories are planned.
