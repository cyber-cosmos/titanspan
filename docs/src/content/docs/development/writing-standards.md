---
title: "Technical writing standards"
---

<span id="technical-writing-standards"></span>

Use this standard for public documentation, repository instructions, agent
skills, architecture records, Python docstrings, and implementation comments.
Keep each claim accurate for the current implementation.

## Writing principles

- Write clear, concise, unambiguous American English.
- Prefer active voice when it makes the actor clear.
- Give each sentence one primary idea.
- Use direct verbs and direct procedural instructions.
- Keep one topic in each paragraph.
- Use the canonical terms in the [glossary](/titanspan/development/glossary/).
- Preserve exact identifiers, commands, URLs, and technical meaning.
- Explain why non-obvious code exists; do not narrate each statement.
- Distinguish implemented, planned, unsupported, and partially verified work.

Treat 20 words as a target for procedural sentences and 25 words as a target
for descriptive sentences. Revise longer sentences when the meaning remains
clear. Keep longer sentences when splitting them would reduce technical
accuracy or make the relationship harder to understand.

These principles draw on ASD-STE100 Simplified Technical English, Issue 9.
Titanspan does not claim formal ASD-STE100 compliance. Use its emphasis on
controlled terms, direct instructions, and concise sentences as guidance.

## Documentation structure

Organize user documentation with Diátaxis where the material fits:

- Tutorials help readers learn through a guided example.
- How-to guides help readers complete a specific task.
- Reference pages describe exact APIs and behavior.
- Explanation pages give context and design rationale.

Choose the form that serves the reader. Do not force a page into a category
that does not fit its purpose. Keep architecture records focused on decisions,
alternatives, consequences, and limitations.

## Python docstrings and comments

Follow PEP 257 and the repository's Google-style convention. Give every
module, class, function, method, fixture, and test a physically multiline
docstring. Document responsibility, relevant inputs and outputs, errors,
side effects, ownership, and lifecycle. Omit sections that do not apply.

Place implementation comments beside the decision they explain. Use comments
for rationale, invariants, resource ownership, concurrency, cancellation,
security boundaries, and recovery behavior. Do not repeat code in prose.

Keep exact identifiers intact. Format identifiers and commands as code when
they appear in Markdown. In Python docstrings, use reStructuredText literals
such as `` ``name`` `` for identifiers.

## Examples

Prefer direct wording:

```text
The application closes its container after providers stop.
```

Avoid passive wording when the actor is known:

```text
The container is closed after providers are stopped.
```

Give each procedural step one action:

```text
1. Register the provider.
2. Start the application.
```

Avoid combining unrelated actions in one step:

```text
1. Register the provider, start the application, and inspect the logs.
```

## Vale checks

Vale is a development-only prose linter. The repository pins Vale in
`.vale-version` and installs it from an official release after checking the
published SHA-256 digest. Vale reads Markdown with its syntax parser. Its
Python View checks comments and docstrings while leaving executable code
alone.

Run `make vale-sync` once after installing Vale. The command retrieves the
pinned Std rules and Vale's Python grammar. Validation targets do not sync or
modify files.

```bash
make vale-install
make vale-sync
make prose-check
make terminology-check
make prose-test
```

Error-level findings enforce canonical terminology, Titanspan capitalization,
and prohibited expressions such as filler and canned conclusion headings.
Warnings flag spelling, passive
voice, and sentence length. Suggestions flag word choice and repeated words.
Only error-level findings fail `prose-check`; `terminology-check` reports the
canonical terminology rules. `prose-test` runs Vale's native rule cases,
checks configuration errors, and verifies rule coverage.

Vale skips fenced and inline code and link targets. The repository runner
checks maintained Markdown and Python files, including AGENTS files, skills,
architecture records, and source comments. It excludes generated paths,
third-party notices, Vale configuration, and rule fixtures. Rule regression
examples live in `tests/prose/Repository.test.yml`.

The initial advisory backlog includes spelling findings for technical names,
passive-voice suggestions, and long sentences in existing documentation and
instructions. The Vale job reports live counts and examples. These findings
do not block CI; correct them when the change touches the affected prose.

Vale is a style aid, not a technical validator. Review its findings and
preserve correct APIs, identifiers, citations, and implementation meaning.
