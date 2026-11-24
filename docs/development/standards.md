# Development standards

These standards apply to human contributors and coding agents. The executable
checks live in `pyproject.toml`, `.pre-commit-config.yaml`, the `Makefile`, and
GitHub Actions. Instructions explain the intent; they do not replace checks.

## Architecture and public APIs

- Read `ARCHITECTURE.md` and the relevant ADRs before changing module
  boundaries, integration lifecycles, or public APIs.
- Prefer an existing, maintained library over a competing implementation.
  A Titanspan abstraction should add clear API ergonomics, conventions,
  lifecycle, a contract, or a test seam.
- Keep wrappers thin and preserve access to the underlying library. Document
  what Titanspan owns and what the dependency provides.
- Prefer composition, explicit providers, protocols, and typed APIs. Avoid
  deep inheritance, unnecessary metaprogramming, premature interfaces, and
  speculative abstractions.
- Keep dependencies flowing toward framework primitives and contracts. Core
  modules must not depend on optional infrastructure integrations. Prevent
  circular imports.
- Use idiomatic Python and domain-oriented Titanspan filenames. Public module
  filenames should describe the framework capability, not merely the package
  being wrapped. For example, prefer `container/container.py`; explain the
  Dishka integration in its implementation and documentation.
- Distinguish implemented behavior from roadmap items. Do not publish an API
  whose implementation is a stub or TODO.
- Record consequential decisions in an ADR with alternatives, consequences,
  risks, and official references.

## Python style and types

- Target Python 3.12 or later versions supported by CI.
- Use four spaces, an 80-character maximum line length, and PEP 8 naming.
- Annotate parameters and return values. Keep Pyright strict; use `Any`, casts,
  and ignores only at narrow, documented third-party boundaries.
- Write concise Google-style docstrings for public modules, classes, functions,
  methods, and protocols. Explain invariants or non-obvious behavior in
  comments; do not narrate the code.
- Prefer `pathlib`, context managers, protocols for structural boundaries,
  immutable values where suitable, and explicit side effects.
- Avoid mutable defaults, wildcard imports, unexplained constants, broad
  exception handling, swallowed exceptions, unnecessary global state, and
  blocking calls in async paths.
- Use timezone-aware datetimes.

## Async and resource lifecycle

- Keep asynchronous I/O explicit. Never block the event loop; use an
  appropriate offloading mechanism when unavoidable.
- Prefer structured concurrency. Bound fan-out, queues, buffers, retries, and
  resource use. Apply backpressure and stream large workloads incrementally.
- Propagate cancellation and deadlines. Finalize resources after success,
  failure, cancellation, and shutdown.
- Do not share unsafe mutable database sessions between concurrent tasks.
  Keep transaction boundaries explicit and database relationship I/O visible.
- Separate I/O concurrency, CPU parallelism, and distributed execution.
- Make retries safe for non-idempotent work. Never claim scalability from
  `async` syntax alone.

## Dependencies and packaging

- Use uv for Python dependency, environment, lock, build, and publishing
  operations. Keep `uv.lock` committed and reproducible; update it using
  `uv lock`, never by hand.
- Check maintenance, Python support, async behavior, license, and advisories
  before adding a dependency. Prefer optional extras for integrations.
- Do not install packages globally or introduce another Python package
  manager.
- Keep AI instructions, skills, harness settings, and development scripts out
  of `src/titanspan/`, except narrowly scoped Markdown instructions where
  discovery requires them. Build and inspect the wheel to ensure these files
  are not distributed.

## Testing and quality

- Use Pytest and TDD for meaningful behavior. Start with a focused failing
  test; then cover success, failures, cleanup, cancellation, scope isolation,
  concurrency, and input validation where they apply.
- Test public contracts, not only mocked implementation details. Keep tests
  deterministic and independent of paid services or live AI providers.
- Use fakes at integration boundaries. Do not weaken tests or quality gates to
  get a green result.
- Add property-based, integration, performance, or stress checks when the
  behavior warrants them. Performance changes need a reproducible workload and
  baseline; shared-runner wall-clock thresholds are not stable gates.
- Do not invent test or benchmark results. Report commands and outcomes that
  were actually observed.

## Documentation and configuration

- Keep examples runnable against implemented APIs. Mark planned capabilities
  plainly and include limitations that affect users.
- Update the relevant guide, README, changelog, and ADR when public behavior
  or architecture changes.
- YAML uses two spaces and valid, consistent syntax. JSON and TOML must parse.
- Keep harness adapters short and link to `AGENTS.md` and the relevant
  architecture documents. Keep canonical skills progressive and task-specific.
- Do not create redundant configs, modify user-level agent settings, change
  model/provider choices, or loosen approval settings.
- Do not add hooks that run shell commands automatically unless a narrowly
  justified change is reviewed independently. Never use hooks as the only
  enforcement layer.

## Security, git, and policy

- Never add real secrets, weaken security checks, bypass hooks, or commit
  private user data.
- Preserve existing work. Avoid destructive resets, force pushes, history
  rewrites, unrelated cleanup, and changes to organization permissions.
- Do not modify tests, coverage, typing, lint, security, or architecture rules
  merely to bypass a failure. Such policy changes need focused rationale and
  independent review.
- Only commit, push, publish, release, deploy, or send external messages when
  explicitly authorized by the active task.

## Validation commands

Use the existing targets; run only checks relevant to the change and report
their real outcomes.

```bash
make lint
make format-check
make types
make test
make check
make agents-check
make docs-build
make integration-test
make security
make build
```

`make check` must remain read-only and match CI. Inspect `make help` and the
Makefile before referencing a target that may have changed.
