# Titanspan repository guidelines

Read the root `AGENTS.md`, relevant scoped instructions, `ARCHITECTURE.md`,
applicable ADRs, and `docs/src/content/docs/development/standards.md`. `AGENTS.md` is the
canonical source; this file is a short Tabnine adapter.

Titanspan is early-stage, async-first Python. Verify implementation before
claiming behavior. Prefer mature libraries and thin integrations. Preserve
module boundaries, cancellation, concurrency bounds, resource cleanup, strict
typing, tests, and quality gates. Use uv and existing Make targets. Do not
invent APIs or results, add unneeded dependencies, weaken checks, commit
secrets, change developer model settings, or modify unrelated files without
authorization.
