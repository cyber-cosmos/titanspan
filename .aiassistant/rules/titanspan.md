# Titanspan project instructions

This project rule must be set to **Always** in JetBrains AI Assistant's
project rule settings to apply automatically. The repository cannot encode
that UI selection in this Markdown file.

Read and follow root `AGENTS.md`, relevant scoped instructions, `ARCHITECTURE.md`,
ADRs, and `docs/src/content/docs/development/standards.md`. Titanspan is an early-stage,
async-first Python framework. Verify implementation before describing a
feature as available. Prefer mature libraries and thin, typed integrations.
Preserve module boundaries, cancellation, bounded concurrency, explicit
resource cleanup, tests, strict Ruff and Pyright, and backward compatibility.

Use uv and the existing Makefile. Do not weaken quality gates, invent APIs or
test results, commit secrets, change provider or model settings, introduce
paid services, or publish, deploy, commit, or push without authorization from
the active task.
