---
name: security-review
description: Review Titanspan code, dependencies, and repository configuration for concrete security risks.
---

# Security review

## When to use

Use for authentication, authorization, tenant boundaries, tool execution,
input parsing, persistence, secrets, CI permissions, or dependency changes.

## References

- Root `AGENTS.md`, scoped instructions, and `SECURITY.md`
- `ARCHITECTURE.md` security model
- Relevant dependency advisories and official security guidance
- GitHub workflow permissions and package lock files

## Procedure

1. Identify trust boundaries and attacker-controlled inputs.
2. Trace authentication, authorization, and tenant identity to each protected
   operation.
3. Check SQL parameter binding, path handling, serialization, logs, and
   secret exposure.
4. Inspect dependency maintenance, license, advisory state, and lock changes.
5. Inspect CI permissions, secrets use, generated scripts, and external
   network behavior.
6. Write a deterministic regression test for actionable defects.
7. Report severity, exploit conditions, impact, and narrow remediation.

## Failure modes

- Calling hypothetical issues exploitable without a concrete path.
- Logging credentials, tokens, private payloads, or sensitive state.
- Trusting agent instructions or hooks as a security boundary.
- Adding broad permissions, bypasses, or unaudited downloaded scripts.
- Hiding a vulnerability by weakening scanners or tests.

## Validation

Run relevant tests, `make check`, and `make security`. For workflow or config
changes, validate syntax and least-privilege behavior. Never test against
external production systems without explicit authorization.

## Completion criteria

Findings are evidence-based, severity and preconditions are clear, security
checks remain enabled, and any fix has regression coverage.
