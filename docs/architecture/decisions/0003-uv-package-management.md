# ADR 0003: uv Package Management

- Status: Accepted
- Date: 2026-11-24

## Context

The project needs one tool for Python dependency resolution, environments,
locking, building, and future publishing.

## Decision

Use uv exclusively for Python dependency and environment management. Commit
uv.lock, use PEP 621 project metadata, and use the PEP 517 uv_build backend.
Keep Node/npm limited to the VitePress documentation toolchain.

## Alternatives considered

- Poetry, Pipenv, and Conda: not selected because they add competing Python
  workflows.
- Setuptools or Hatchling: valid PEP 517 backends; uv_build is a good fit for
  this pure-Python package and is maintained with uv.

## Consequences

Local and CI installs use locked uv sync. uv_build is suitable while Titanspan
remains pure Python; extension modules would trigger a backend review.

## Risks

The local executable must meet the build backend requirement. CI pins a tested
uv release, and the backend is bounded below 0.14.

## References

- [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)
- [uv projects](https://docs.astral.sh/uv/guides/projects/)
- [PEP 621](https://peps.python.org/pep-0621/)
