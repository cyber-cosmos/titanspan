## Purpose

Describe the change and the user problem it solves.

## Related issues

Link related issues or write "None".

## Architectural impact

Describe module boundaries, integration changes, or write "None".

## Breaking changes

Describe public API impact or write "None".

## Validation

- [ ] TDD was used; the focused test failed for the expected reason first.
- [ ] Unit tests cover behavior and meaningful failure cases.
- [ ] Real integration tests cover each affected implemented boundary.
- [ ] Regression tests are included for bug fixes.
- [ ] Async failure, cancellation, timeout, scope isolation, and cleanup are
      tested where applicable.
- [ ] `make check` passes, including 95% line and 90% branch coverage.
- [ ] Every Python declaration has strict annotations and a physically
      multi-line Google-style docstring.
- [ ] Comments explain non-obvious implementation decisions and invariants.
- [ ] Documentation and runnable examples reflect implemented behavior.
- [ ] Security implications and input/resource boundaries are reviewed.
- [ ] Performance implications are reviewed; any benchmark is reproducible.
- [ ] Dependency changes are justified and `uv.lock` is updated with uv.
- [ ] No quality gate, test, coverage threshold, or security rule was weakened.
