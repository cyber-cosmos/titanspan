---
title: "ADR 0023: Container-owned facade overrides"
---

<span id="adr-0023-container-owned-facade-overrides"></span>

- Status: Accepted
- Date: 2026-11-26

## Context

`Config.use()` and `Log.use()` maintained separate ContextVars for production
service selection. Facade calls could therefore return a test replacement
while dependency injection and helpers returned the application's original
service.

## Decision

- Resolve all component facade contracts through one typed `Facade` base.
- Use the active application Container for temporary facade replacements.
- Keep component-specific fake assertion or transport state inside its owner.
- Do not add facade service caches or dynamic attribute forwarding.
- Preserve replacement ownership and safety rules from the Container.

## Consequences

`Config.use()` and `Log.use()` now require an active application context.
Direct resolution, facade calls, and helpers observe the same replacement.
The Container rejects overrides that conflict with active scopes or cached
singleton dependencies. Callers retain ownership of the instance supplied to
`use()`.

This changes standalone test setup. Tests and examples must bind an
application context before using a facade replacement. The package remains
pre-release, so the native behavior is established without a compatibility
adapter.

## Verification

Unit tests verify nested, concurrent, exceptional, and cancelled replacement
scopes. Integration tests verify shared Config and Log identity across
facades, the application Container, and framework helpers.
