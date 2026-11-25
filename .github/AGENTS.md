# GitHub configuration instructions

Follow root `AGENTS.md`, `SECURITY.md`, and `CONTRIBUTING.md`. This directory
contains repository governance and CI, not framework runtime code.

- Use least-privilege workflow permissions and pin third-party actions to
  verified immutable commits where practical.
- Keep required checks aligned with `make check`; preserve locked uv installs.
- Keep CI aligned with `make check`, the locked uv install, architecture and
  source policy checks, coverage, and repository hooks.
- Preserve every independent mandatory job and the fail-closed `ci-gate`.
  A policy validator, test, matrix, or security job cannot be made optional to
  accommodate an implementation.
- Verify changes with `make workflows-check` and update
  `docs/development/continuous-integration.md` when the job graph, gate
  inventory, compatibility range, or artifact flow changes.
- Do not weaken required CI, dependency auditing, secret detection, or
  repository protection to make a change pass. Policy edits need explicit
  justification and independent review.
- Do not add action tokens, secrets, model/provider configuration, MCP
  servers, arbitrary hooks, or blanket command permissions.
- Keep issue forms, pull request templates, workflows, and Copilot agent
  profiles accurate and reviewable. Copilot profiles must remain optional,
  omit model identifiers, and use read-only tools for reviewers.
- Verify action versions, schemas, and platform behavior against official
  documentation before changing workflow configuration.
- Run `make agents-check`, `make yaml-check`, and `make hooks-check` after
  agent or workflow changes. Report unavailable validation rather than
  claiming it passed.
