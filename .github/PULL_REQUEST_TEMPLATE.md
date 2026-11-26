## Purpose

Describe the change and the user problem it solves.

## Related issues

Link related issues or write "None".

## Architectural impact

Describe module boundaries, integration changes, or write "None".

## Breaking changes

Describe public API impact or write "None".

## Validation

- [ ] The focused test failed for the expected reason before implementation.
- [ ] Unit tests cover behavior and meaningful failure cases.
- [ ] Real integration tests cover each affected implemented boundary.
- [ ] Regression tests cover each bug fix.
- [ ] Tests cover async failure, cancellation, timeouts, scope isolation, and
      cleanup where applicable.
- [ ] `make check` passes, including 95% line and 90% branch coverage.
- [ ] Every Python declaration has strict annotations and a physically
      multi-line Google-style docstring.
- [ ] Comments explain non-obvious implementation decisions and invariants.
- [ ] Documentation and runnable examples reflect implemented behavior.
- [ ] Review security implications and input/resource boundaries.
- [ ] Review performance implications. Make each benchmark reproducible.
- [ ] Justify dependency changes and update `uv.lock` with uv.
- [ ] Keep every quality gate, test, coverage threshold, and security rule intact.
