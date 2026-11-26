# Engineering standards

These requirements apply to every contributor and coding agent. Instructions
do not replace enforcement: `pyproject.toml`, repository scripts, pre-commit,
Make, and GitHub Actions implement the checks. A failed required check must be
fixed; contributors must not bypass or weaken a policy to finish sooner.

## Architecture and native APIs

- Read `ARCHITECTURE.md`, the nearest scoped `AGENTS.md`, and applicable ADRs
  before changing module boundaries, public APIs, lifecycle, or integrations.
- Build on maintained libraries. Keep Titanspan wrappers thin, domain-named,
  typed, and interoperable with native APIs. Do not duplicate their engines.
- Titanspan is an independent Python framework. Follow native Titanspan API
  specifications and Python conventions; external framework compatibility is
  not a requirement.
- Keep optional integrations out of core dependency direction. Avoid cycles,
  global mutable state, speculative abstractions, and unrelated refactors.
- Preserve documented public behavior where applicable. Record consequential
  decisions as ADRs and explain breaking changes.
- Verify unfamiliar and version-sensitive APIs through official docs and the
  installed, locked package before relying on them.
- A component is not complete because its API exists or isolated unit tests
  pass. It must satisfy its canonical contracts, participate in the owning
  application lifecycle, and have real integration tests with implemented
  dependencies. Record unavailable dependencies as limitations rather than
  simulating completion with disconnected abstractions.

## Python source policy

Apply the policy to runtime modules, tests, benchmarks, examples, stubs, and
repository-maintained Python scripts:

- UTF-8 source, LF line endings, four-space indentation, and at most 80
  characters per physical line.
- PEP 8 names: `snake_case` for functions, methods, and variables;
  `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants.
- Keep Ruff's naming rules active for all first-party files. Do not suppress
  N802, N803, N806, N815, N816, A001, A002, or A003 to preserve external
  framework spellings. Permit only a narrowly reviewed exception required by
  an external Python protocol, with an exact file and rule allowlist.
- Use explicit, descriptive names, absolute imports, and explicit public
  exports. Do not use wildcard imports, unused names, dead code, or commented
  out implementations.
- Use comprehensive parameter, return, attribute, callback, and generic
  annotations. Keep Pyright in strict mode. Avoid `Any`, bare containers,
  unsafe casts, and suppressions except at narrow, explained library edges.
- Avoid mutable defaults, unexplained values, unnecessary duplication,
  blocking work in async paths, and broad or swallowed exceptions.
- Use `pathlib`, context managers, typed protocols, and immutable structures
  where they make lifecycle and ownership clearer.
- Add trailing commas in multi-line collections and calls where appropriate.

Ruff is the central linter and formatter. It checks correctness, imports,
annotations, docstrings, security, async use, exceptions, complexity, tests,
paths, resource handling, logging, and modern Python syntax. E501 is enabled;
the formatter is not considered proof of line-length compliance. A separate
read-only AST/source check rejects lines over 80 characters, including URLs
and comments, and requires each module, class, and function or method to have
a physically multi-line docstring.

The documented Ruff exceptions are narrow: D200 conflicts with the required
multi-line docstring form; D418 discourages docstrings on overload
declarations, while this project requires each declaration to be documented
and the source checker enforces it; S101 is allowed only in tests and
benchmarks because assertions are their test contract. Any new exception
requires a focused explanation and review. Do not add blanket exclusions or
type ignores.

Two integration overrides retain names required by the Python standard
library: the monthly log handler must override `computeRollover(currentTime)`,
and its local HTTP test server must match `BaseHTTPRequestHandler`'s
`log_message(format, ...)` signature. The exact Ruff rule and file allowlist
is tested in `tests/unit/test_native_api_names.py`; adding another naming
exception requires the same focused review.

Run the canonical checks:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python scripts/check_python_standards.py
uv run --locked pyright
```

## Docstrings and implementation comments

Use Google-style, physically multi-line docstrings for modules, classes,
protocols, functions, methods, properties, decorators, fixtures, and tests.
Document non-trivial private helpers as well as public APIs. Explain
responsibility and relevant inputs, outputs, exceptions, side effects,
resource ownership, lifecycle, concurrency, cancellation, and transaction
semantics. Omit sections that do not apply. Do not write redundant prose that
merely repeats a signature or statement.

Use comments to explain why an implementation exists, an invariant, a
concurrency or security constraint, an error-recovery choice, or a subtle
compatibility/performance decision. Place the comment at the decision it
explains. Do not narrate simple statements or add comments to inflate a
comment count. Ruff and the source checker enforce docstring form; meaningful
comment content requires code review because a linter cannot judge intent.

## Test-driven development and test quality

For every meaningful behavior change, use Red-Green-Refactor:

1. Write a focused test for the desired contract or reproduced defect.
2. Run it and confirm the failure is for the intended reason.
3. Implement the smallest correct change and make the test pass.
4. Add applicable failure, boundary, cleanup, cancellation, isolation, and
   concurrency cases, then refactor with tests remaining green.

Bug fixes require a regression test. Cover every meaningful public behavior
and internal decision. Use unit tests for isolated behavior and real
integration tests at implemented library boundaries. Do not mock the behavior
the test is supposed to prove. Fakes may isolate external providers and paid
services; no default test may require production credentials or billable AI.

Use markers declared in `pyproject.toml`: `unit`, `integration`, `feature`,
`regression`, `security`, `benchmark`, `stress`, and `slow`. Add directories
only as corresponding functionality is implemented. Keep async tests
deterministic: use synchronization primitives and explicit deadlines instead
of arbitrary sleeps. Test cancellation, timeouts, task/resource cleanup, and
scope isolation when they apply.

Hypothesis is available for invariant-heavy inputs such as collections,
parsing, reducers, transformations, and retry policies. Bound generated work
so property tests remain deterministic and suitable for CI.

Coverage thresholds are enforced independently: at least 95% statement
coverage and 90% branch coverage for `src/titanspan`. Use meaningful
assertions; coverage percentage alone does not establish correctness. Do not
exclude production code or lower thresholds to get a green build. Critical
behavior still requires direct assertions and integration coverage.

## Async, concurrency, and performance

- Keep async I/O explicit and avoid blocking the event loop. Offload blocking
  work only through an appropriate, bounded mechanism.
- Give tasks an owner. Prefer structured concurrency and propagate
  cancellation, timeouts, and failures.
- Bound task fan-out, buffers, retries, connections, and memory. Apply
  backpressure and process large input incrementally.
- Do not share mutable SQLAlchemy `AsyncSession` objects across concurrent
  tasks; keep transaction boundaries explicit.
- Separate I/O concurrency, CPU parallelism, and distributed execution.
- Ensure failures and cancellation release resources and do not duplicate
  non-idempotent work on retry.
- Never infer scalability from async syntax. Performance claims require a
  reproducible workload, native-library baseline where relevant, and recorded
  environment, versions, throughput, latency distribution, concurrency, and
  peak memory. Shared-runner timing is informational, not a brittle gate.

## Documentation, security, and dependencies

- Keep docs, examples, and changelog accurate to tested implementation.
  Clearly label planned work and verify every public API example.
- Check dependency maintenance, Python support, async behavior, license, and
  advisories before adding or upgrading a package. Use `uv add` / `uv lock`;
  never hand-edit `uv.lock` or install globally.
- Keep secrets out of source, logs, fixtures, examples, and history. Validate
  untrusted input, bind database parameters, and preserve authorization and
  tenant boundaries.
- Do not disable security checks, tests, hooks, CI, typing, lint, formatting,
  coverage, or architecture validation to make a change pass.
- Do not use paid infrastructure or services without explicit authorization.

## Standard commands

Use the uv-managed environment and the Makefile as the contributor interface:

```bash
make lint
make format-check
make types
make unit-test
make integration-test
make coverage
make architecture-check
make agents-check
make check
make ci
```

`make check` is read-only and the standard local gate. It includes lint,
formatting, line/docstring checks, strict types, architecture validation,
agent configuration checks, and the test suite with both coverage thresholds.
`make ci` adds the repository's full documentation, security, packaging, and
stress validation. Use `make fix` only for safe Ruff fixes and formatting;
inspect the resulting diff before accepting it. CI is authoritative, and
unavailable or failed checks must be reported as such.
