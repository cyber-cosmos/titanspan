# Console module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns the
`titanspan` command-line interface using Typer and Rich.

- Keep commands explicit and provide useful help and failure messages.
- Do not perform destructive actions, network access, package publication, or
  implicit project modifications without an explicit user command.
- Keep CLI startup lightweight and ensure runtime templates, if introduced,
  are included in the installed distribution intentionally.
- Test command output, exit codes, errors, and distribution entry points.
- Consult `ARCHITECTURE.md`, `ROADMAP.md`, and `CONTRIBUTING.md`. Run
  `make test`, `make types`, and `make check` for applicable changes.
