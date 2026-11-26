---
title: "Testing"
---

<span id="testing"></span>

The repository uses Pytest, Ruff, strict Pyright, and independent minimums of
95 percent statement coverage and 90 percent branch coverage for implemented
first-party code. Tests include real integration boundaries and require no
paid infrastructure or live AI model APIs. See
[`docs/src/content/docs/development/standards.md`](/titanspan/development/standards/) for TDD,
docstring, comment, typing, and quality-gate requirements.

From a checkout, run:

```sh
uv sync --locked
make check
make integration-test
```

Performance measurements are informational. Shared runner timing is not a
stable performance gate.
