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
- `docs/src/content/docs/development/standards.md`
- `docs/src/content/docs/development/writing-standards.md` and
  `docs/src/content/docs/development/glossary.md`
- Relevant implementation, tests, and official dependency documentation

## Procedure

1. Inspect implemented code and tests before writing claims.
2. Identify the right authoritative document and avoid duplicating large
   instruction sets.
3. Update the smallest set of pages and navigation needed.
4. Check every command, file path, public API, and relative link.
5. Label planned behavior and limitations explicitly.
6. Build the Starlight site and run the agent configuration checker when
   those areas change.
7. Run the Vale prose, terminology, and rule regression targets after prose
   changes.

## Failure modes

- Inventing APIs, feature status, performance, adoption, or test outcomes.
- Duplicating canonical agent instructions into every harness file.
- Leaving obsolete commands or broken local links.
- Writing examples that rely on paid services or unimplemented modules.
- Forgetting documentation navigation or packaging implications.

## Validation

Run `make docs-build` and `make docs-test` for Starlight changes. Run
`make agents-check` for instructions, skills, profiles, and adapters. Run
`make prose-check`, `make terminology-check`, and `make prose-test` after
prose changes. Run relevant framework checks for examples that execute Python
code.

## Completion criteria

Documentation matches implementation, references are valid, the appropriate
site/config checks pass, and planned work remains clearly identified.
