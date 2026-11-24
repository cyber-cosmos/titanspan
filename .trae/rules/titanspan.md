---
alwaysApply: true
---

# Titanspan project rules

Read and follow the repository root `AGENTS.md`, the nearest scoped
`AGENTS.md`, and relevant architecture documents and ADRs. Root `AGENTS.md`
is canonical; this file is only a discovery adapter.

Verify implementation before describing capabilities as available. Keep
Python idiomatic, APIs typed, async paths non-blocking and bounded, resources
closed, and module dependencies acyclic. Prefer thin integrations over mature
libraries. Use uv and the existing Makefile. Preserve tests and strict quality
gates. Do not invent APIs or results, commit secrets, weaken checks, or alter
model, provider, approval, or permission settings.
