# Container module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns
Titanspan's dependency registration API and lifecycle integration over
Dishka.

- Keep Dishka as the graph resolver and resource finalizer. Do not implement
  a competing dependency-resolution engine.
- Keep public names domain-oriented (currently `container/container.py`), not
  vendor-oriented. State clearly that graph resolution is delegated to Dishka.
- Preserve native Dishka provider and container interoperability.
- Validate registration graphs before serving. Freeze production
  registrations after boot; avoid shared mutable runtime mutation.
- Model transient, application, request, job, workflow, and tool lifecycles
  only where concrete code and scope semantics justify them.
- Ensure scoped objects do not leak across concurrent requests or jobs, and
  finalize resources on failure and cancellation.
- Test resolution, missing dependencies, scope isolation, overrides, startup
  failure, and cleanup as applicable.
- Consult `ARCHITECTURE.md` and ADRs 0005 and 0009. Run `make test`,
  `make types`, and `make check` for applicable changes.
