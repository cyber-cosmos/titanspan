---
name: code-review
description: Perform a read-only review of a Titanspan change for correctness, regressions, and maintainability.
---

# Code review

## When to use

Use after implementation or when asked to assess a patch, pull request, or
uncommitted diff.

## References

- Root and nearest scoped `AGENTS.md`
- `ARCHITECTURE.md`, relevant ADRs, and `SECURITY.md`
- Tests and documentation for affected behavior
- `docs/src/content/docs/development/standards.md`
- `docs/src/content/docs/development/writing-standards.md` for prose and docstring findings

## Procedure

1. Inspect the full diff and working tree. Read enough surrounding code to
   understand the changed contract.
2. Check correctness, failure cases, cleanup, concurrency, security, type
   quality, and API compatibility.
3. Check tests prove the intended contract rather than only mock behavior;
   verify test-first evidence and real integration coverage at changed
   dependency boundaries.
4. Check strict annotations, 80-column formatting, multi-line docstrings,
   and comments that explain non-obvious reasoning rather than narrate code.
5. Check docs, examples, changelog, ADR, and roadmap status for accuracy.
6. Check dependencies, packaging, CI, and quality policy for scope and safety.
7. Report actionable findings by severity with file and line references.

## Failure modes

- Rewriting code while asked to review.
- Reporting style preferences as defects.
- Reporting issues without a triggering scenario or evidence.
- Treating configured CI as proof it ran or passed.
- Approving based on a partial diff or a passing test command alone.

## Validation

Review actual command output and hosted CI status if available. If validation
was not run or is inaccessible, say so. Do not modify the patch during a
read-only review.

## Completion criteria

Provide only evidence-backed findings, or state that no actionable issue was
found within the inspected scope and list unverified checks.
