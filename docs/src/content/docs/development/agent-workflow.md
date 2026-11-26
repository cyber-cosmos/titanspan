---
title: "AI-assisted development workflow"
---

<span id="ai-assisted-development-workflow"></span>

This workflow applies to meaningful code, documentation, architecture, and
repository-policy changes. Root `AGENTS.md` remains the canonical instruction
source; this document defines the working sequence.

## 1. Understand

- Read the request and inspect `git status` before editing. Preserve user work.
- Read root `AGENTS.md`, applicable scoped instructions, and relevant parts of
  `ARCHITECTURE.md`, `ROADMAP.md`, `CONTRIBUTING.md`, `SECURITY.md`, and ADRs.
- Read the writing standard and glossary when changing maintained prose.
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

- Use small, cohesive changes and Red-Green-Refactor for every meaningful
  behavior change. Write a failing regression test before implementation and
  confirm that it fails for the intended reason.
- Preserve useful behavior and user changes. When a pre-release public name
  conflicts with the native Python API policy, update its callers, tests, and
  documentation together and record the breaking change. Avoid speculative
  features and unnecessary dependencies.
- Fully type and document every declaration. Require physically multi-line
  docstrings and meaningful comments explaining non-obvious decisions.
- Keep async behavior bounded and cancellation-safe. Make ownership and
  cleanup explicit.
- Keep integrations thin. Expose underlying library objects only through an
  explicit, documented interoperability boundary; ordinary Titanspan APIs
  should remain framework-owned.
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
make ci
```

`make check` includes the complete applicable unit and integration suite and
enforces line and branch coverage independently. Run security, stress, or
benchmark commands when relevant. Do not run unstable performance thresholds
on shared CI. Do not weaken any policy to make a check pass or claim a command
passed unless it completed successfully in the current work.

## 6. Review

Inspect the complete diff, not only the last edit. Check correctness, security,
resource cleanup, error handling, architecture, async behavior, memory use,
typing, public API semantics, test adequacy, docs, and development-only
packaging. Verify that a built wheel contains only intended runtime files.

## 7. Document

Update user-facing docs, changelog, ADRs, and roadmap status as needed. Verify
all examples against the current implementation. Run `make prose-check`,
`make terminology-check`, and `make prose-test` after prose changes. Keep
planned functionality clearly marked as planned.

## 8. Report

Summarize what changed and why, tests/checks and their observed results,
remaining limitations, risks, and unresolved items. State which requested
checks were not run. Never fabricate evidence or conceal failures.
