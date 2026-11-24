---
name: service-container-development
description: Change the Titanspan service container or dependency scopes while preserving Dishka resolution and resource cleanup.
---

# Service container development

## When to use

Use for dependency bindings, provider registration, resolution, scopes,
overrides, or container lifecycle work.

## References

- Root and `src/titanspan/container/AGENTS.md`
- `ARCHITECTURE.md`
- ADRs 0005 and 0009
- Installed Dishka documentation and source

## Procedure

1. Trace the current registration, scope, resolve, and finalization paths.
2. Verify the relevant Dishka APIs against the pinned/locked version.
3. Define scope ownership and behavior for application, request, job, or
   standalone execution. Do not assume every lifecycle is a linear hierarchy.
4. Add a focused failing test for resolution or lifecycle behavior.
5. Keep Dishka as the resolver and avoid global mutable container state.
6. Test successful resolution, invalid graphs, overrides, scope isolation,
   cancellation, and resource cleanup as applicable.
7. Update architecture docs if lifecycle semantics change.

## Failure modes

- Building a second dependency resolution engine.
- Mutating production registrations after application startup.
- Sharing request or mutable database state across concurrent executions.
- Losing exception causes or leaking resources after partial startup.
- Advertising a scope that has no implemented semantics.

## Validation

Run focused container tests, `make test`, `make types`, and `make check`.
Run lifecycle integration tests for application startup/shutdown changes.

## Completion criteria

The scope contract is explicit, Dishka interoperability is preserved, graph
and cleanup behavior are tested, and docs match the implementation.
