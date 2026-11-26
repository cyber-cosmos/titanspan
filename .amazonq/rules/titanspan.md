# Titanspan project instructions

Read and follow the repository root `AGENTS.md` and relevant architecture
documents before making changes. The canonical project instructions and
engineering standards are in `AGENTS.md` and `docs/src/content/docs/development/`.

Titanspan is an async-first Python framework in early development. Verify each
feature before describing or extending it. Prefer mature libraries and thin,
typed integrations. Preserve native library APIs, module boundaries,
cancellation, bounded concurrency, resource cleanup, and existing public APIs.

Use uv and existing Make targets. Write meaningful tests. Keep strict Ruff and
Pyright checks. Report only checks you ran. Do not weaken quality gates or
invent APIs and results. Protect secrets. Do not change provider or model
settings or run paid services. Publish, deploy, commit, and push only when the
active task authorizes those actions.
