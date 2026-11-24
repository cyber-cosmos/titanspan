# Titanspan project instructions

Read and follow the repository root `AGENTS.md` and relevant architecture
documents before making changes. The canonical project instructions and
engineering standards are in `AGENTS.md` and `docs/development/`.

Titanspan is an early-stage, async-first Python framework. Verify the current
implementation before describing or extending a feature. Prefer mature
libraries and thin, typed integrations; preserve native library APIs, module
boundaries, cancellation, bounded concurrency, resource cleanup, and
backward compatibility.

Use uv and existing Make targets. Write meaningful tests, keep strict Ruff and
Pyright checks, and report only checks actually run. Do not weaken quality
gates, invent APIs or results, commit secrets, change provider or model
settings, run paid services, or publish, deploy, commit, or push without
authorization from the active task.
