# Testing

The repository uses Pytest, Ruff, strict Pyright, and a 90 percent initial
coverage gate for implemented first-party code. Tests run without paid
infrastructure or live AI model APIs.

From a checkout, run:

```sh
uv sync --locked
make check
make integration-test
```

Performance measurements are informational. Shared runner timing is not a
stable performance gate.
