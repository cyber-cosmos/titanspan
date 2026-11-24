# Foundation module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns
application construction, startup, shutdown, and service-provider lifecycle.

- Keep composition explicit. Do not add implicit module scanning or mutable
  global application instances.
- Treat startup and shutdown as paired resource lifecycles. Finalize resources
  in failure and cancellation paths as well as normal shutdown.
- Preserve FastAPI/Starlette interoperability and native application access.
- Keep application registrations stable after boot; do not mutate shared
  production containers at runtime.
- Test startup, shutdown, partial startup failure, cleanup, and concurrent
  request behavior that changes.
- Consult `ARCHITECTURE.md`, ADRs 0001, 0004, and 0005. Run `make test`,
  `make types`, and `make check` for applicable changes.
