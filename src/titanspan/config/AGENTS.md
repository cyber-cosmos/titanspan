# Configuration module instructions

Follow root `AGENTS.md` and `src/titanspan/AGENTS.md`. This module owns typed
application settings and configuration conventions using Pydantic Settings.

- Validate environment and file input at configuration boundaries.
- Keep secrets out of defaults, logs, exceptions, and examples. Never commit
  real credentials.
- Prefer explicit, typed settings and documented precedence. Avoid hidden
  process-global mutation and import-time environment reads.
- Test valid values, invalid values, defaults, precedence, and secret-safe
  error behavior.
- Consult `ARCHITECTURE.md` and ADRs 0003 and 0010. Run `make test`,
  `make types`, and `make check` for applicable changes.
