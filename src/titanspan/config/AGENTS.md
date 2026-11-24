# Configuration module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns typed
application settings and configuration conventions using Pydantic Settings.

- Validate environment and file input at configuration boundaries.
- Keep secrets out of defaults, logs, exceptions, and examples. Never commit
  real credentials.
- Prefer explicit, typed settings and documented precedence. Avoid hidden
  process-global mutation and import-time environment reads.
- Use test-driven changes; cover valid and invalid values, defaults,
  precedence, boundary inputs, and secret-safe errors.
- Annotate every declaration and use a multi-line Google-style docstring.
  Comments should explain validation or precedence decisions that are not
  evident from Pydantic's field declarations.
- Consult `ARCHITECTURE.md` and ADRs 0003 and 0010. Run `make test`,
  `make types`, and `make check` for applicable changes.
