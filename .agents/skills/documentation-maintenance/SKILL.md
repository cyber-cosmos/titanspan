---
name: documentation-maintenance
description: Update Titanspan guides, API examples, architecture docs, or agent instructions accurately.
---

# Documentation maintenance

## When to use

Use when public behavior, examples, architecture decisions, development
commands, or repository instructions change.

## References

- Root and nearest scoped `AGENTS.md`
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, and `CHANGELOG.md`
- `docs/development/standards.md`
- Relevant implementation, tests, and official dependency documentation

## Procedure

1. Inspect implemented code and tests before writing claims.
2. Identify the right authoritative document and avoid duplicating large
   instruction sets.
3. Update the smallest set of pages and navigation needed.
4. Check every command, file path, public API, and relative link.
5. Label planned behavior and limitations explicitly.
6. Build the VitePress site and run the agent configuration checker when
   those areas change.

## Failure modes

- Inventing APIs, feature status, performance, adoption, or test outcomes.
- Duplicating canonical agent instructions into every harness file.
- Leaving obsolete commands or broken local links.
- Writing examples that rely on paid services or unimplemented modules.
- Forgetting documentation navigation or packaging implications.

## Validation

Run `make docs-build` for VitePress changes and `make agents-check` for
instructions, skills, profiles, and adapters. Run relevant framework checks
for examples that execute Python code.

## Completion criteria

Documentation matches implementation, references are valid, the appropriate
site/config checks pass, and planned work remains clearly identified.
