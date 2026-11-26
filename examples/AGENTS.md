# Example application instructions

Follow root `AGENTS.md`, `docs/src/content/docs/development/standards.md`, and the nearest
framework module instructions. Examples demonstrate only implemented APIs.

- Keep each example runnable, minimal, typed, and explicit about required
  local setup. Do not require paid services or credentials by default.
- Use physically multi-line docstrings for Python modules and declarations.
  Add comments for non-obvious setup or lifecycle decisions.
- Test runnable behavior through a real local framework boundary where
  practical. Keep assertions deterministic and update corresponding guides.
- Keep sample secrets fake, clearly marked, and nonfunctional. Do not include
  generated environments, data dumps, or private user data.
- Run `make python-standards`, `make types`, `make integration-test`,
  `make docs-build`, and `make check` when applicable.
