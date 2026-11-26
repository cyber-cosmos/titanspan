# ADR 0005: Dishka Service Container

- Status: Accepted
- Date: 2026-11-24

## Context

Application services need typed dependency resolution, explicit scopes, and
resource cleanup without a Titanspan-owned resolution engine.

## Decision

Use Dishka's async container and FastAPI integration. Keep the
Titanspan-facing construction boundary in
`src/titanspan/container/container.py`. Dishka owns dependency graph resolution
and resource finalization; the filename names the framework module, not a
competing container engine.

The initial application builds registrations at construction time, installs the
FastAPI integration, and closes its app-scoped container in lifespan shutdown.

## Alternatives considered

- A custom container: rejected because it duplicates graph resolution and
  resource management.
- FastAPI dependencies alone: viable for request injection, but not the same
  general application container lifecycle.
- Dishka-specific imports throughout the package: rejected to keep the
  framework boundary small.

## Consequences

Dishka is a mandatory foundation dependency. Provider registrations are fixed
after construction. Future scopes must account for HTTP, jobs, and workflow
execution separately.

## Risks

Integration details may change. Keep Dishka-specific calls in the container
boundary and test cleanup after success and failure.

## References

- [Dishka FastAPI integration](https://dishka.readthedocs.io/en/stable/integrations/fastapi.html)
- [Dishka container lifecycle](https://dishka.readthedocs.io/en/stable/container/)
