---
title: "ADR 0016: Native Python API naming"
---

<span id="adr-0016-native-python-api-naming"></span>

- Status: Accepted
- Date: 2026-11-25

## Context

Earlier component work exposed camelCase aliases and separate contracts to
mirror conventions from external frameworks. Titanspan is an independent
Python framework, and these duplicate names complicated discovery, typing,
documentation, and repository-wide policy enforcement. The project has no
published package releases that require preserving these aliases.

## Decision

- Use PEP 8 naming for all Titanspan APIs, implementations, tests, examples,
  benchmarks, and development scripts.
- Keep one canonical `snake_case` spelling for each operation. Remove
  compatibility-only aliases, wrappers, overloads, and protocol declarations.
- Keep Ruff naming rule families enabled. Do not suppress N802, N803, N806,
  N815, N816, A001, A002, or A003 to retain external framework spellings.
- Allow exact naming exceptions only when a Python protocol requires the
  spelling; record the path and rule in the native API policy test.
- Use a narrowly documented exception only when Python itself or a concrete
  external protocol requires a specific name.
- Retain useful behavior and meaningful regression coverage while removing
  assertions that solely compare duplicate names.
- Follow native component specifications as the behavior authority.
  External projects may inform design, but their APIs and language semantics
  are not API requirements.
- Preserve legal third-party notices and attribution independently of public
  API policy.

## Consequences

This is a breaking change for callers of removed aliases and external
compatibility-only protocols. Titanspan is pre-release and has no published
package API to preserve. All application examples and internal callers use
the canonical Python names. Repository Ruff checks fail on newly introduced
mixed-case method, argument, and class attribute names.

## Risks and mitigation

Callers may have adopted early aliases from unreleased source. The migration
is documented in the changelog, and the native method names remain available.
The repository does not provide a temporary compatibility layer because
that would preserve the duplicate API this decision removes.

## Verification

`tests/unit/test_native_api_names.py` confirms representative removed aliases
are absent and their native spellings remain available. Ruff applies the
enabled naming rules across the repository; a policy test limits exceptions
to the exact standard-library overrides.
