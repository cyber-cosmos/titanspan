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

`make check` is the required, read-only local gate. It runs strict Ruff
linting and formatting checks, the 80-column and multi-line-docstring
validator, strict Pyright, YAML and lockfile checks, architecture boundaries,
agent configuration validation, the full applicable test suite, and separate
95% statement and 90% branch coverage thresholds.

Run `make docs-build` when changing documentation. Use `make ci` for the
complete local CI suite, including dependency and secret audits, documentation
build, packaging audit, and stress checks. Do not skip, weaken, or bypass a
required check to complete a contribution sooner.

See the [CI architecture](docs/development/continuous-integration.md) for the
required job inventory, compatibility matrices, artifact flow, and fail-closed
gate. Changes to CI policy must explain why each affected status remains
mandatory and preserve independent verification.

## Engineering workflow

- Read [ARCHITECTURE.md](ARCHITECTURE.md) and relevant ADRs before changing
  module boundaries or public APIs.
- Use Red-Green-Refactor for every meaningful behavior: write a focused
  failing test, verify the failure is relevant, implement the smallest
  change, and refactor with tests passing. Bug fixes require regression tests.
- Add comprehensive unit tests and real integration tests for implemented
  dependency boundaries. Cover failure, validation, cleanup, cancellation,
  scope isolation, and concurrency where applicable.
- Fully annotate production, tests, examples, benchmarks, and development
  scripts. Every module, class, function, method, fixture, and test needs a
  physically multi-line Google-style docstring. Add concise comments that
  explain non-obvious rationale, invariants, and lifecycle behavior.
- Keep Python formatting at 80 columns and follow Ruff and strict Pyright.
- Use UTF-8, LF, four-space Python indentation, two-space YAML indentation,
  and GNU Make's required tab indentation for recipes.
- Prefer mature libraries over new infrastructure abstractions.
- Preserve native library access and propagate cancellation.
- Update user documentation and the changelog for public behavior changes.
- Record major architectural decisions in a new ADR.
- Do not lower coverage, disable quality policies, skip failing tests, or add
  blanket exclusions/suppressions to make a change pass. Policy changes need a
  focused justification and independent maintainer review.

## Pull requests

Describe the purpose, related issues, architecture impact, compatibility and
breaking changes, tests, documentation, security, performance, and dependency
effects. Keep each change focused and address review conversations before
merging.

## License

By contributing, you agree that your contributions are licensed under the
project's MIT License.
