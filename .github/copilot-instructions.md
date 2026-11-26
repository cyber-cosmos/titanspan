# Titanspan repository instructions

Use root [`AGENTS.md`](../AGENTS.md) as the canonical development policy.
Read the relevant scoped instructions, `ARCHITECTURE.md`, ADRs, and
[`docs/src/content/docs/development/standards.md`](../docs/src/content/docs/development/standards.md) before
changing code or repository policy.

For meaningful behavior, use test-driven development and verify the initial
test fails for the intended reason. Keep APIs strictly typed, idiomatic,
async-safe, and thin over mature dependencies. Add comprehensive unit and
real integration tests, physically multi-line Google-style docstrings, and
comments that explain non-obvious implementation decisions.

Do not weaken lint, formatting, typing, documentation, security, architecture,
test, or coverage requirements. Run `make check` for code changes and report
only checks that actually ran. Preserve user changes; do not make commits,
push, publish, deploy, install agents, or use paid services unless explicitly
authorized by the current task.
