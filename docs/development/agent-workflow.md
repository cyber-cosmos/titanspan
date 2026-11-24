# AI-assisted development workflow

This workflow applies to meaningful code, documentation, architecture, and
repository-policy changes. Root `AGENTS.md` remains the canonical instruction
source; this document defines the working sequence.

## 1. Understand

- Read the request and inspect `git status` before editing. Preserve user work.
- Read root `AGENTS.md`, applicable scoped instructions, and relevant parts of
  `ARCHITECTURE.md`, `ROADMAP.md`, `CONTRIBUTING.md`, `SECURITY.md`, and ADRs.
- Inspect the implementation, tests, package configuration, and current
  commands. Do not infer support from a placeholder module or roadmap entry.

## 2. Investigate

- Verify unfamiliar or version-sensitive library APIs using official
  documentation, installed package source, and relevant changelogs.
- Identify existing functionality, contracts, and integration boundaries.
- Determine whether the change affects a public API, dependency, security
  boundary, resource lifecycle, or supported Python version.
- Avoid making external requests or billable calls unless the task authorizes
  them.

## 3. Plan

For non-trivial changes, identify scope, affected modules, intended behavior,
architecture impact, test approach, risks, and acceptance criteria. Keep work
focused. Ask for missing information only when the decision cannot be inferred
and would materially change the implementation; continue independent work.

## 4. Implement

- Use small, cohesive changes and test-driven development for behavior.
- Preserve existing APIs and user changes. Avoid speculative features and
  unnecessary dependencies.
- Keep async behavior bounded and cancellation-safe. Make ownership and
  cleanup explicit.
- Make integrations thin and preserve access to the underlying library.
- Do not present placeholders, mocks, TODOs, or roadmap work as implemented.

## 5. Validate

Run targeted checks first, then applicable project checks. Standard commands
include:

```bash
make lint
make format-check
make types
make test
make check
make agents-check
make build
make docs-build
```

Run security, integration, stress, or benchmark checks when relevant. Do not
run unstable performance thresholds on shared CI. Do not claim a command
passed unless it completed successfully in the current work.

## 6. Review

Inspect the complete diff, not only the last edit. Check correctness, security,
resource cleanup, error handling, architecture, async behavior, memory use,
typing, public compatibility, test adequacy, docs, and development-only
packaging. Verify that a built wheel contains only intended runtime files.

## 7. Document

Update user-facing docs, changelog, ADRs, and roadmap status as needed. Verify
all examples against the current implementation. Keep planned functionality
clearly marked as planned.

## 8. Report

Summarize what changed and why, tests/checks and their observed results,
remaining limitations, risks, and unresolved items. State which requested
checks were not run. Never fabricate evidence or conceal failures.
