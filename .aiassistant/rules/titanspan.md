# Titanspan project instructions

Set this project rule to **Always** in JetBrains AI Assistant's project rule
settings. The repository cannot encode that UI selection in Markdown.

Read and follow root `AGENTS.md`, scoped instructions, `ARCHITECTURE.md`, ADRs,
and `docs/src/content/docs/development/standards.md`.

Titanspan is an async-first Python framework in early development. Verify each
feature before describing it as available. Prefer mature libraries and thin,
typed integrations. Preserve module boundaries, cancellation, bounded
concurrency, resource cleanup, tests, strict Ruff and Pyright, and existing
public APIs.

Use uv and existing Make targets. Do not weaken quality gates or invent APIs
and test results. Protect secrets. Do not change provider or model settings or
use paid services. Publish, deploy, commit, and push only when the active task
authorizes those actions.
