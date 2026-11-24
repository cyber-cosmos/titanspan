---
name: Titanspan repository standards
alwaysApply: true
---

Before changing this repository, read and follow the root `AGENTS.md`, the
nearest scoped `AGENTS.md`, and relevant architecture documents and ADRs.
Treat `AGENTS.md` as canonical; this adapter adds no separate policy.

Keep APIs idiomatic Python and async-safe. Use thin wrappers over the
established libraries. Preserve module boundaries, strict Ruff and Pyright,
tests, resource cleanup, and user changes. Use uv and existing Make targets.
Never invent APIs or results, weaken quality gates, commit secrets, bypass
user approval settings, or present planned work as implemented.
