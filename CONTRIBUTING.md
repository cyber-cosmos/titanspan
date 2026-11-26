# Contributing to Titanspan

Titanspan is early-stage open source software. Contributions should move one
coherent capability forward without presenting planned functionality as
available.

## Before opening an issue

Search current issues and Discussions before opening a report. For defects,
include Titanspan and Python versions, the operating system, dependency
versions, and reproduction steps. Add a minimal example, expected and actual
behavior, and relevant logs. For performance reports, include a reproducible
benchmark, workload, baseline, concurrency, and memory details.

Use Discussions for design questions. Open an issue for a reproducible defect
or a focused proposal.

## Development setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), GNU Make, and
Node.js 22.23.4+ with npm for documentation work. Docker is optional.

```sh
uv sync --locked
make help
make check
```

`make check` is the required, read-only local gate. It runs Ruff, strict
Pyright, YAML and lockfile checks, architecture checks, and agent validation.
It also runs applicable tests and enforces statement and branch coverage
separately. The minimums are 95% for statements and 90% for branches.

Run `make docs-build` when changing documentation and `make docs-test` to
verify the rendered site in Playwright. Use `make ci` for the complete local CI
suite, including dependency and secret audits, documentation build and browser
verification, packaging, Docker, and hook checks. Do not skip, weaken, or
bypass a required check to complete a contribution sooner.

Follow the [technical writing standards](docs/src/content/docs/development/writing-standards.md)
and canonical [glossary](docs/src/content/docs/development/glossary.md) when
adding prose. Install the pinned Vale release with `make vale-install`, fetch
its reviewed rules with `make vale-sync`, then run `make prose-check`,
`make terminology-check`, and `make prose-test` before submitting content.
`make check` also includes the prose and terminology gates.

See the [CI architecture](docs/src/content/docs/development/continuous-integration.md) for the
required job inventory, compatibility matrices, artifact flow, and fail-closed
gate. Changes to CI policy must explain why each affected status remains
mandatory and preserve independent verification.

## Engineering workflow

- Read [ARCHITECTURE.md](ARCHITECTURE.md) and relevant ADRs before changing
  module boundaries or public APIs.
- Use Red-Green-Refactor for meaningful behavior changes. Write a focused
  failing test and verify its failure. Implement the smallest change. Refactor
  with tests passing. Add a regression test for every bug fix.
- Add comprehensive unit tests and real integration tests for implemented
  dependency boundaries. Cover failure, validation, cleanup, cancellation,
  scope isolation, and concurrency where applicable.
- Fully annotate production, tests, examples, benchmarks, and development
  scripts. Every module, class, function, method, fixture, and test needs a
  physically multi-line Google-style docstring. Add concise comments that
  explain non-obvious rationale, invariants, and lifecycle behavior.
- Keep Python formatting at 80 columns and follow Ruff and strict Pyright.
- Use UTF-8 and LF. Indent Python with four spaces and YAML with two. Use tabs
  only for GNU Make recipes.
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
