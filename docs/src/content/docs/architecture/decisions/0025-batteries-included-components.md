---
title: "ADR 0025: Batteries-Included Native Components"
---

<span id="adr-0025-batteries-included-components"></span>

- Status: Proposed, pending independent maintainer review
- Date: 2026-11-28

## Context

Titanspan is a batteries-included framework. Optional installation of a native
component's required libraries makes its documented APIs unavailable in a
standard install and fragments provider and Console behavior. ADR 0010
previously limited dependencies to the initial core, before native Database
and Number capabilities were established.

## Decision

Every implemented native component is a first-class framework capability.
Libraries required by its native APIs are mandatory runtime dependencies.
Native providers and Console commands register by default where applicable.
Internal module independence describes dependency direction; it does not make
a built-in capability an optional installation.

The Database component must achieve comprehensive behavioral parity with
Laravel 13.x Database and Eloquent features that apply to Titanspan. Public
APIs remain idiomatic Python and do not reproduce PHP compatibility syntax.

Optional extras are reserved for external database drivers, integrations,
and provider-specific SDKs. Dependencies for unfinished components are not
installed until those components are implemented. When Workflows is
implemented, LangGraph is a mandatory dependency of that native component.

Database is a built-in component. Its standard install provides the native
Database APIs and SQLite sync and async support. The provider owns lazy,
application-scoped resources; ordinary application construction does not
open physical connections. Babel and num2words are mandatory for native
Number utilities.

This decision supersedes ADR 0010 and retains that record as history.

## Alternatives considered

- Keep all integrations optional: rejected because native APIs would be
  unavailable in the standard installation.
- Install dependencies for every planned component: rejected because it
  adds unused dependencies before there is implemented functionality.
- Keep optional-import fallbacks for native capabilities: rejected because
  they obscure incomplete installations and split the supported API.

## Consequences

The standard package metadata, lockfile, installed-wheel checks, and CI must
cover each implemented native component. External drivers remain separately
installable and require backend-specific verification before support claims.

## Risks

Mandatory dependencies increase standard installation size. Keep those
dependencies focused on implemented native behavior and review their
compatibility, licensing, security, and maintenance status.

## References

- [ADR 0010: Optional dependencies (superseded)](/framework/architecture/decisions/0010-optional-dependencies/)
- [PEP 621 optional dependencies](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dependencies-optional-dependencies)
- [uv dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/)
