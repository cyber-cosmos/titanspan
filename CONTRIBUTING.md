# Contributing to Titanspan

Titanspan is early-stage open source software. Contributions should move one
coherent capability forward without presenting planned functionality as
available.

## Before opening an issue

Search current issues and Discussions. For a defect, include the Titanspan and
Python versions, operating system, relevant dependency versions, reproduction
steps, a minimal example, expected and actual behavior, and relevant logs.
Performance reports should also include a reproducible benchmark and workload,
baseline, concurrency, and memory details.

Use Discussions for design questions. Open an issue for a reproducible defect
or a focused proposal.

## Development setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), GNU Make, and
Node.js/npm for documentation work. Docker is optional.

```sh
uv sync --locked
make help
make check
```

Run `make docs-build` when changing documentation. Use `make integration-test`
for integration coverage and `make security` for a local dependency audit.

## Engineering workflow

- Read [ARCHITECTURE.md](ARCHITECTURE.md) and relevant ADRs before changing
  module boundaries or public APIs.
- Use test-driven development: write a focused failing test, verify the
  failure, implement the smallest change, and rerun the suite.
- Add type annotations, public API docstrings, and tests for meaningful
  behavior and failure paths.
- Keep Python formatting at 80 columns and follow Ruff and strict Pyright.
- Prefer mature libraries over new infrastructure abstractions.
- Preserve native library access and propagate cancellation.
- Update user documentation and the changelog for public behavior changes.
- Record major architectural decisions in a new ADR.

## Pull requests

Describe the purpose, related issues, architecture impact, compatibility and
breaking changes, tests, documentation, security, performance, and dependency
effects. Keep each change focused and address review conversations before
merging.

## License

By contributing, you agree that your contributions are licensed under the
project's MIT License.
