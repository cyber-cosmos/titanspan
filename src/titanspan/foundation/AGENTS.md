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
- Keep `ApplicationBuilder` as an option collector for the canonical
  `Application`. Provider discovery must use an explicit trusted entry-point
  group, not module scanning or filesystem imports.
- Keep path helpers descriptive. Do not treat them as validation for
  untrusted filesystem paths.
- Keep provider boot injection in service providers. Application lifecycle
  callbacks have no injected parameters; shutdown callbacks use captured
  references after the Container stops accepting work.
- Test startup, shutdown, partial startup failure, cleanup, and concurrent
  request behavior that changes.
- Write the regression or lifecycle test first and run it before
  implementation. Include real FastAPI/Dishka integration coverage for
  changes to their boundary.
- Keep every declaration strictly annotated and physically multi-line
  documented. Comment the ownership and ordering of non-obvious cleanup.
- Consult `ARCHITECTURE.md`, ADRs 0001, 0004, 0005, 0018, and 0022. Run `make test`,
  `make integration-test`, `make types`, and `make check` for applicable
  changes.
