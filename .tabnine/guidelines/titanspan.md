# Titanspan repository guidelines

Read the root `AGENTS.md`, relevant scoped instructions, `ARCHITECTURE.md`,
applicable ADRs, and `docs/src/content/docs/development/standards.md`. `AGENTS.md` is the
canonical source; this file is a short Tabnine adapter.

Titanspan is early-stage, async-first Python. Verify implementation before
claiming behavior. Prefer mature libraries and thin typed integrations;
preserve module boundaries, cancellation, bounded work, explicit resource
cleanup, strict typing, tests, and quality gates. Use uv and existing Make
targets. Do not invent APIs or results, add unneeded dependencies, weaken
checks, commit secrets, alter developer model/provider settings, or publish,
push, deploy, or modify unrelated assets without authorization.
